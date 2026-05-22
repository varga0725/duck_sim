import math
import time
import sys
import os
import collections
import threading
import logging
import asyncio
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import numpy as np

from duck_agent_sim.simulator.double_buffered_state import DoubleBufferedState
from duck_agent_sim.simulator.control_plane import DesiredMotionState, ZERO_CONTROL, command_duration
from duck_agent_sim.simulator.timing import SimulationClock
from duck_agent_sim.simulator.legacy_dynamics import LegacyDynamicsController

logger = logging.getLogger("duck-agent-sim")

# Dynamically resolve and append external Open_Duck_Playground to sys.path
open_duck_path = str(Path(__file__).resolve().parents[2] / "external" / "Open_Duck_Playground")
if open_duck_path not in sys.path:
    sys.path.append(open_duck_path)

from duck_agent_sim.schemas import (
    RobotState,
    RobotCommand,
    ControlIntent,
    CommandResponse,
    Orientation,
    FeetContact,
    SafetyConfig,
    SensorsState,
    SensorAvailability
)
from duck_agent_sim.simulator.command_mapper import map_command
from duck_agent_sim.simulator.policy_contract import (
    DOF_VEL_SCALE,
    apply_action_to_targets,
    apply_target_rate_limit,
    clamp_targets_to_ctrlrange,
)
from duck_agent_sim.simulator.safety import is_fallen, should_auto_stop, with_stability
from duck_agent_sim.config import (
    DUCK_DYNAMICS_MODE,
    DUCK_HYBRID_QVEL_XY_SCALE,
    DUCK_HYBRID_Z_FORCE_SCALE,
    DUCK_ONNX_MODEL_PATH,
)



class DummyLock:
    """A dummy lock implementation that does not block, preventing asyncio deadlocks."""
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class DuckSimulator(ABC):
    """
    Abstract Interface for the Duck Simulation.
    Can be backed by either mock kinematic calculations or real MuJoCo integration.
    """

    @abstractmethod
    def reset(self) -> RobotState:
        """Resets the simulation to the initial stable state."""
        pass

    @abstractmethod
    def stop(self) -> RobotState:
        """Immediately stops the robot's motion."""
        pass

    @abstractmethod
    def apply_command(self, command: RobotCommand) -> CommandResponse:
        """Applies a high-level command to the simulator and steps it for the duration."""
        pass

    @abstractmethod
    def get_state(self) -> RobotState:
        """Retrieves the current robot state."""
        pass

    @abstractmethod
    def get_sensor_state(self) -> SensorsState:
        """Retrieves raw sensor state with explicit availability/null markers."""
        pass

    @abstractmethod
    def step(self, control: ControlIntent, dt: float, safety: SafetyConfig) -> RobotState:
        """Steps the physics simulation forward by dt using raw controls."""
        pass
def _vec(values, length: int):
    """Convert MuJoCo/numpy numeric slices to JSON-friendly float tuples."""
    return tuple(float(v) for v in values[:length])


def _unavailable_sensor_state(mode: str, sim_time: float) -> SensorsState:
    return SensorsState(
        mode=mode,
        sim_time=float(sim_time),
        timestamp=time.time(),
        imu=SensorAvailability(available=False),
        feet={
            "left": SensorAvailability(available=False),
            "right": SensorAvailability(available=False),
        },
    )


class MockDuckSimulator(DuckSimulator):
    """
    A deterministic, kinematic mock simulator of the Open Duck Mini v2.
    Simulates waddling, foot contacts, 2D navigation, and safety violations.
    """

    def __init__(self):
        try:
            import duck_agent_sim.simulator.instance as inst
            if hasattr(inst, "active_simulator") and hasattr(inst.active_simulator, "set_instance"):
                inst.active_simulator.set_instance(self)
            else:
                inst.active_simulator = self
        except Exception:
            pass
        self._state = RobotState()
        self._double_buffered_state = DoubleBufferedState(self._state)
        self._command_exec_lock = DummyLock()
        self._intent_lock = threading.RLock()
        self._desired_motion = DesiredMotionState(
            command="stop",
            control=ZERO_CONTROL,
            safety=SafetyConfig(),
            started_at=time.monotonic(),
            expires_at=None,
        )
        self._running = True
        self._clock = SimulationClock("mock-physics", fixed_dt_sec=0.05)
        self._thread = threading.Thread(target=self._simulation_loop, daemon=True, name="MockDuckSimulationLoop")
        self.reset()
        self._thread.start()
        
        # Start background vision loop
        from duck_agent_sim.vision.camera import CameraDevice
        from duck_agent_sim.vision.frame_buffer import FrameBuffer
        from duck_agent_sim.vision.yolo_detector import YOLODetector
        from duck_agent_sim.vision.tracker import CentroidTracker
        from duck_agent_sim.vision import perception_state
        from duck_agent_sim.vision.vision_loop import VisionLoop
        
        self.camera_device = CameraDevice(self)
        self.frame_buffer = FrameBuffer()
        self.detector = YOLODetector()
        self.tracker = CentroidTracker()
        self.vision_loop = VisionLoop(
            self.camera_device,
            self.frame_buffer,
            self.detector,
            self.tracker,
            perception_state,
            target_fps=10.0
        )
        self.vision_loop.start()

    def close(self):
        """Stops background threads and releases resources."""
        self._running = False
        if hasattr(self, "_thread") and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        from duck_agent_sim.vision import follower
        if follower is not None:
            follower.stop()
        if hasattr(self, "vision_loop") and self.vision_loop is not None:
            self.vision_loop.stop()
        if hasattr(self, "camera_device") and self.camera_device is not None:
            self.camera_device.close()

    def reset(self) -> RobotState:
        with self._intent_lock:
            self._desired_motion = DesiredMotionState(
                command="reset",
                control=ZERO_CONTROL,
                safety=SafetyConfig(),
                started_at=time.monotonic(),
                expires_at=None,
            )
        self._state = RobotState(
            robot="open_duck_mini_v2",
            status="idle",
            sim_time=0.0,
            position=(0.0, 0.0, 0.41),
            orientation=Orientation(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0),
            feet_contact=FeetContact(left=True, right=True),
            fallen=False,
            last_command="reset"
        )
        self._double_buffered_state.update_write_state(self._state)
        self._double_buffered_state.swap()
        return self.get_state()

    def stop(self) -> RobotState:
        with self._intent_lock:
            self._desired_motion = DesiredMotionState(
                command="stop",
                control=ZERO_CONTROL,
                safety=SafetyConfig(),
                started_at=time.monotonic(),
                expires_at=None,
            )
        self._state.status = "stopped"
        self._state.last_command = "stop"
        # Zero out any waddling
        self._state.orientation.roll_deg = 0.0
        self._state.orientation.pitch_deg = 0.0
        self._state.feet_contact = FeetContact(left=True, right=True)
        self._double_buffered_state.update_write_state(self._state)
        self._double_buffered_state.swap()
        return self.get_state()

    def get_clock_telemetry(self):
        return self._clock.telemetry()

    def set_desired_control(
        self,
        control: ControlIntent,
        safety: Optional[SafetyConfig] = None,
        *,
        command: str = "external_control",
        duration_sec: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> RobotState:
        now = time.monotonic()
        expires_at = now + duration_sec if duration_sec is not None else None
        with self._intent_lock:
            self._desired_motion = DesiredMotionState(
                command=command,
                control=control.model_copy(deep=True),
                safety=safety or SafetyConfig(),
                started_at=now,
                expires_at=expires_at,
                request_id=request_id,
            )
            self._state.last_command = command
        return self.get_state()

    async def execute_command_async(
        self,
        command: RobotCommand,
        *,
        request_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> CommandResponse:
        if command.command == "reset":
            state = self.reset()
            control = map_command(command)
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=state)

        if command.command == "stop":
            state = self.stop()
            control = map_command(command)
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=state)

        if self.get_state().fallen:
            control = ZERO_CONTROL
            self.stop()
            return CommandResponse(accepted=False, command=command.command, mapped_control=control, state=self.get_state())

        control = map_command(command)
        duration = command_duration(command)
        self.set_desired_control(
            control,
            command.safety,
            command=command.command,
            duration_sec=duration,
            request_id=request_id,
        )
        scheduled_state = self._advance_from_intent(control, self._clock.fixed_dt_sec, command.safety).model_copy(deep=True)

        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                self.stop()
                raise asyncio.CancelledError()
            if self.get_state().fallen:
                break
            await asyncio.sleep(0.01)

        if self.get_state().fallen and command.safety.stop_on_fall:
            self.stop()

        return CommandResponse(
            accepted=True,
            command=command.command,
            mapped_control=control,
            state=self.get_state() if self.get_state().fallen else scheduled_state,
        )

    def _simulation_loop(self) -> None:
        self._clock.reset()
        while self._running:
            dt = self._clock.sleep_until_next_tick()
            with self._intent_lock:
                desired = self._desired_motion
                if desired.expired:
                    desired = DesiredMotionState(
                        command="stop",
                        control=ZERO_CONTROL,
                        safety=SafetyConfig(),
                        started_at=time.monotonic(),
                        expires_at=None,
                        request_id=desired.request_id,
                    )
                    self._desired_motion = desired
            self._advance_from_intent(desired.control, dt, desired.safety)

    def get_state(self) -> RobotState:
        from duck_agent_sim.config import DUCK_SIM_MODE
        state = self._double_buffered_state.get_read_state()
        return with_stability(state, SafetyConfig(), DUCK_SIM_MODE)

    def get_sensor_state(self) -> SensorsState:
        from duck_agent_sim.config import DUCK_SIM_MODE
        state = self._double_buffered_state.get_read_state()
        return _unavailable_sensor_state(DUCK_SIM_MODE, state.sim_time)

    def apply_command(self, command: RobotCommand) -> CommandResponse:
        if command.command in ("reset", "stop"):
            control = map_command(command)
            state = self.reset() if command.command == "reset" else self.stop()
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=state)

        control = map_command(command)
        if self.get_state().fallen:
            self.stop()
            return CommandResponse(accepted=False, command=command.command, mapped_control=ZERO_CONTROL, state=self.get_state())

        if command.speed > 0.8 and command.duration_sec > 5.0:
            self._state.fallen = True
            self._state.status = "fallen"
            self._state.orientation.pitch_deg = 48.0
            self._state.orientation.roll_deg = 20.0
            self._state.position = (self._state.position[0], self._state.position[1], 0.10)
            self._state.feet_contact = FeetContact(left=False, right=False)
            self._double_buffered_state.update_write_state(self._state)
            self._double_buffered_state.swap()
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=self.get_state())

        self.set_desired_control(control, command.safety, command=command.command, duration_sec=command.duration_sec)
        deadline = time.monotonic() + command.duration_sec
        while time.monotonic() < deadline:
            if self.get_state().fallen:
                break
            time.sleep(0.01)
        if self.get_state().fallen and command.safety.stop_on_fall:
            self.stop()
        return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=self.get_state())

    def _legacy_apply_command(self, command: RobotCommand) -> CommandResponse:
        with self._command_exec_lock:
            # 1. Reset if requested
            if command.command == "reset":
                self.reset()
                control = map_command(command)
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 2. Check if already fallen
            if self._state.fallen:
                control = ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0)
                self._state.status = "fallen"
                return CommandResponse(
                    accepted=False,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 3. Map high-level command to low-level controls
            control = map_command(command)
            self._state.last_command = command.command

            # 4. Check for catastrophic fall condition based on extreme speed & duration parameters
            if command.speed > 0.8 and command.duration_sec > 5.0:
                # High speed and long duration causes it to trip
                self._state.fallen = True
                self._state.status = "fallen"
                # Tip the orientation severely
                self._state.orientation.pitch_deg = 48.0
                self._state.orientation.roll_deg = 20.0
                self._state.position = (self._state.position[0], self._state.position[1], 0.10)
                self._state.feet_contact = FeetContact(left=False, right=False)
                self._double_buffered_state.update_write_state(self._state)
                self._double_buffered_state.swap()
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 5. Run simulation stepping for command.duration_sec in steps of 0.05s (dt)
            dt = 0.05
            elapsed = 0.0
            target_duration = command.duration_sec

            while elapsed < target_duration:
                # If a fall occurs mid-step, break immediately
                if self._state.fallen:
                    break
                self.set_desired_control(control, command.safety, command=command.command, duration_sec=dt)
                time.sleep(dt)
                elapsed += dt

            return CommandResponse(
                accepted=True,
                command=command.command,
                mapped_control=control,
                state=self.get_state()
            )

    async def apply_command_async(self, command: RobotCommand) -> CommandResponse:
        return await self.execute_command_async(command)

    async def _legacy_apply_command_async(self, command: RobotCommand) -> CommandResponse:
        with self._command_exec_lock:
            # 1. Reset if requested
            if command.command == "reset":
                self.reset()
                control = map_command(command)
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 2. Check if already fallen
            if self._state.fallen:
                control = ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0)
                self._state.status = "fallen"
                return CommandResponse(
                    accepted=False,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 3. Map high-level command to low-level controls
            control = map_command(command)
            self._state.last_command = command.command

            # 4. Check for catastrophic fall condition based on extreme speed & duration parameters
            if command.speed > 0.8 and command.duration_sec > 5.0:
                # High speed and long duration causes it to trip
                self._state.fallen = True
                self._state.status = "fallen"
                # Tip the orientation severely
                self._state.orientation.pitch_deg = 48.0
                self._state.orientation.roll_deg = 20.0
                self._state.position = (self._state.position[0], self._state.position[1], 0.10)
                self._state.feet_contact = FeetContact(left=False, right=False)
                self._double_buffered_state.update_write_state(self._state)
                self._double_buffered_state.swap()
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 5. Run simulation stepping for command.duration_sec in steps of 0.05s (dt)
            dt = 0.05
            elapsed = 0.0
            target_duration = command.duration_sec

            while elapsed < target_duration:
                # If a fall occurs mid-step, break immediately
                if self._state.fallen:
                    break
                self.set_desired_control(control, command.safety, command=command.command, duration_sec=dt)
                await asyncio.sleep(dt)
                elapsed += dt

            return CommandResponse(
                accepted=True,
                command=command.command,
                mapped_control=control,
                state=self.get_state()
            )

    def step(self, control: ControlIntent, dt: float, safety: SafetyConfig) -> RobotState:
        self.set_desired_control(control, safety, command="external_control", duration_sec=dt)
        return self.get_state()

    def _advance_from_intent(self, control: ControlIntent, dt: float, safety: SafetyConfig) -> RobotState:
        # If already fallen, safety limits movement
        if self._state.fallen:
            self._state.status = "fallen"
            return self._state

        # 1. Update simulation time
        self._state.sim_time += dt

        # 2. Update status based on velocity
        if control.linear_x != 0.0:
            self._state.status = "walking"
        elif control.yaw != 0.0:
            self._state.status = "turning"
        else:
            self._state.status = "idle"

        # 3. Kinematic position/orientation calculations
        yaw_rad = math.radians(self._state.orientation.yaw_deg)
        pos_x, pos_y, pos_z = self._state.position

        # Update 2D position
        pos_x += control.linear_x * dt * math.cos(yaw_rad)
        pos_y += control.linear_x * dt * math.sin(yaw_rad)

        # Update Yaw orientation
        new_yaw_deg = (self._state.orientation.yaw_deg + math.degrees(control.yaw * dt)) % 360.0

        # 4. Waddling Motion Simulation (to make the mock feel alive & wowed)
        # If moving, waddle!
        is_moving = (abs(control.linear_x) > 0.01 or abs(control.yaw) > 0.01)
        if is_moving:
            waddle_freq = 8.0  # radians per second
            waddle_phase = self._state.sim_time * waddle_freq

            # Simulated body swaying
            roll_waddle = 6.0 * math.sin(waddle_phase)
            pitch_waddle = 3.0 * math.cos(2 * waddle_phase) + 2.0  # slight forward lean
            z_bounce = 0.41 + 0.015 * math.sin(2 * waddle_phase)

            # Feet contact pattern alternates based on roll sway
            left_foot_touch = (roll_waddle >= -1.0)
            right_foot_touch = (roll_waddle <= 1.0)

            # Apply
            self._state.orientation.roll_deg = roll_waddle
            self._state.orientation.pitch_deg = pitch_waddle
            self._state.position = (pos_x, pos_y, z_bounce)
            self._state.feet_contact = FeetContact(left=left_foot_touch, right=right_foot_touch)
        else:
            # Stand stable
            self._state.orientation.roll_deg = 0.0
            self._state.orientation.pitch_deg = 0.0
            self._state.position = (pos_x, pos_y, 0.41)
            self._state.feet_contact = FeetContact(left=True, right=True)

        self._state.orientation.yaw_deg = new_yaw_deg

        # 5. Safety Monitoring & Enforcement
        if is_fallen(self._state, safety):
            self._state.fallen = True
            self._state.status = "fallen"
            if safety.stop_on_fall:
                # Stop linear velocities immediately
                control.linear_x = 0.0
                control.linear_y = 0.0
                control.yaw = 0.0
                # Flatten coordinate
                self._state.position = (pos_x, pos_y, 0.12)
                self._state.feet_contact = FeetContact(left=False, right=False)

        self._double_buffered_state.update_write_state(self._state)
        self._double_buffered_state.swap()
        return self.get_state()

    def force_tilt(self, roll: float, pitch: float, z_height: float = 0.41):
        """Helper to inject simulated imbalance for testing safety layers."""
        self._state.orientation.roll_deg = roll
        self._state.orientation.pitch_deg = pitch
        self._state.position = (self._state.position[0], self._state.position[1], z_height)
        
        # Check safety immediately
        if is_fallen(self._state, SafetyConfig()):
            self._state.fallen = True
            self._state.status = "fallen"
            self._state.feet_contact = FeetContact(left=False, right=False)
        self._double_buffered_state.update_write_state(self._state)
        self._double_buffered_state.swap()


class RealDuckSimulator(DuckSimulator):
    """
    Real MuJoCo Simulator for the Open Duck Mini v2.
    Steps physics at 500Hz on a background thread, runs an interactive
    passive rendering viewer, and applies stable direct freejoint command mapping
    coupled with a leg-waddling kinematic oscillator.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless or (os.getenv("DUCK_HEADLESS", "false").lower() == "true")
        self._lock = threading.RLock()
        self._command_exec_lock = DummyLock()
        self._state = RobotState()
        self._double_buffered_state = DoubleBufferedState(self._state)
        self._initialized = False
        self._running = False
        self._thread = None
        self._viewer = None
        self._kinematic_yaw = 0.0
        self._clock = SimulationClock("real-physics", fixed_dt_sec=0.002)
        self._dynamics_mode = DUCK_DYNAMICS_MODE
        self._legacy_dynamics = LegacyDynamicsController(
            mode=self._dynamics_mode,
            hybrid_qvel_xy_scale=DUCK_HYBRID_QVEL_XY_SCALE,
            hybrid_z_force_scale=DUCK_HYBRID_Z_FORCE_SCALE,
        )
        
        # ONNX Control state variables
        self._onnx_active = False
        self._onnx_session = None
        self.num_dofs = 0
        self.gyro_id = -1
        self.gyro_addr = -1
        self.accelerometer_id = -1
        self.accelerometer_addr = -1
        self.actuator_names = []
        self.actuator_joint_ids = []
        self.actuator_joint_qpos_addr = []
        self.actuator_qvel_addr = []
        self.default_actuator = None
        self.motor_targets = None
        self.prev_motor_targets = None
        self.last_action = None
        self.last_last_action = None
        self.last_last_last_action = None
        self.imitation_i = 0.0
        self.imitation_phase = np.array([1.0, 0.0])
        self.nb_steps_in_period = 50

    def _initialize_mujoco(self):
        if self._initialized:
            return

        try:
            import duck_agent_sim.simulator.instance as inst
            if hasattr(inst, "active_simulator") and hasattr(inst.active_simulator, "set_instance"):
                inst.active_simulator.set_instance(self)
            else:
                inst.active_simulator = self
        except Exception:
            pass

        try:
            import mujoco
            import mujoco.viewer
            from playground.open_duck_mini_v2 import base
            from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML
        except ImportError as e:
            raise ImportError(
                "Real MuJoCo simulation dependencies not found.\n"
                "Please run scripts/setup_open_duck.sh and ensure 'mujoco' is installed."
            ) from e

        # Load MjModel and MjData
        xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
        
        # Removed dynamic tracking camera injection because we now use the FPV camera inside the robot's head.
            
        self.model = mujoco.MjModel.from_xml_string(
            xml_text,
            assets=base.get_assets()
        )
        self.model.opt.timestep = 0.002  # 500Hz physics timestep
        self.data = mujoco.MjData(self.model)

        # Set to home keyframe
        home_key = self.model.keyframe("home")
        self.data.qpos[:] = home_key.qpos
        self.data.ctrl[:] = home_key.ctrl

        # Initialize tracking states
        self._target_linear_x = 0.0
        self._target_linear_y = 0.0
        self._target_yaw_rate = 0.0
        self._current_linear_x = 0.0
        self._current_linear_y = 0.0
        self._current_yaw_rate = 0.0
        self._sim_time = 0.0
        self._last_command = "stop"
        self._last_command_time = time.time()
        self._safety_config = SafetyConfig()
        self._ringbuffer = collections.deque(maxlen=500)
        self._kinematic_yaw = 0.0

        # Load and configure ONNX walking policy if configured
        self._onnx_active = False
        if DUCK_ONNX_MODEL_PATH:
            try:
                import onnxruntime
                self._onnx_session = onnxruntime.InferenceSession(
                    DUCK_ONNX_MODEL_PATH, providers=["CPUExecutionProvider"]
                )
                self._onnx_active = True
                logger.info(f"Loaded ONNX policy from: {DUCK_ONNX_MODEL_PATH}")
            except Exception as e:
                logger.error(f"Failed to load ONNX model: {e}")

        # Setup telemetry indexes for ONNX and sensor mappings
        try:
            self.gyro_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, "gyro")
            self.gyro_addr = self.model.sensor_adr[self.gyro_id]
            
            self.accelerometer_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, "accelerometer")
            self.accelerometer_addr = self.model.sensor_adr[self.accelerometer_id]

            self.num_dofs = self.model.nu
            self.actuator_names = [self.model.actuator(k).name for k in range(0, self.model.nu)]
            self.actuator_joint_ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, n) for n in self.actuator_names]
            
            self.actuator_joint_qpos_addr = np.array([self.model.jnt_qposadr[idx] for idx in self.actuator_joint_ids])
            self.actuator_qvel_addr = np.array([self.model.jnt_dofadr[idx] for idx in self.actuator_joint_ids])
            
            self.default_actuator = np.array(self.model.keyframe("home").ctrl)
            self.motor_targets = self.default_actuator.copy()
            self.prev_motor_targets = self.default_actuator.copy()
            
            self.last_action = np.zeros(self.num_dofs)
            self.last_last_action = np.zeros(self.num_dofs)
            self.last_last_last_action = np.zeros(self.num_dofs)
            
            self.imitation_i = 0.0
            self.imitation_phase = np.array([1.0, 0.0])
        except Exception as e:
            logger.error(f"Error mapping telemetry sensor indices: {e}")

        # Start the physics stepping and viewer thread
        self._running = True
        self._thread = threading.Thread(target=self._physics_loop, daemon=True)
        self._thread.start()

        # Start background vision loop
        from duck_agent_sim.vision.camera import CameraDevice
        from duck_agent_sim.vision.frame_buffer import FrameBuffer
        from duck_agent_sim.vision.yolo_detector import YOLODetector
        from duck_agent_sim.vision.tracker import CentroidTracker
        from duck_agent_sim.vision import perception_state
        from duck_agent_sim.vision.vision_loop import VisionLoop
        
        self.camera_device = CameraDevice(self)
        self.frame_buffer = FrameBuffer()
        self.detector = YOLODetector()
        self.tracker = CentroidTracker()
        self.vision_loop = VisionLoop(
            self.camera_device,
            self.frame_buffer,
            self.detector,
            self.tracker,
            perception_state,
            target_fps=10.0
        )
        self.vision_loop.start()

        self._initialized = True

    def _physics_loop(self):
        import mujoco

        viewer = None
        if not self.headless:
            try:
                import mujoco.viewer
                # Spawns the viewer window in a non-blocking passive state
                viewer = mujoco.viewer.launch_passive(
                    self.model,
                    self.data,
                    show_left_ui=False,
                    show_right_ui=False
                )
                
                # Lock viewer to the FPV camera by default
                try:
                    cam_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
                    if cam_id >= 0:
                        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                        viewer.cam.fixedcamid = cam_id
                except Exception as cam_e:
                    logger.warning(f"Could not lock viewer to fpv camera: {cam_e}")
                    
                self._viewer = viewer
            except Exception as e:
                logger.warning(f"Failed to launch passive viewer: {e}")

        self._clock.reset()
        counter = 0

        while self._running:
            # 1. Deadman Timeout Check (Auto-stop if no command for 2 seconds)
            if time.time() - self._last_command_time > 2.0:
                self._target_linear_x = 0.0
                self._target_linear_y = 0.0
                self._target_yaw_rate = 0.0

            with self._lock:
                # 2. Control loop at 50Hz (every 10 steps of 0.002s = 0.020s)
                if counter % 10 == 0:
                    # Command Smoothing Layer (Velocity low-pass filter)
                    self._current_linear_x += (self._target_linear_x - self._current_linear_x) * 0.15
                    self._current_linear_y += (self._target_linear_y - self._current_linear_y) * 0.15
                    self._current_yaw_rate += (self._target_yaw_rate - self._current_yaw_rate) * 0.15

                    if self._onnx_active:
                        self._apply_onnx_inference()
                    else:
                        # Leg waddling kinematic oscillator
                        self._apply_waddle_oscillator()

                # Enforce torso stabilization at 500Hz for perfect stability and upright locomotion
                self._stabilize_torso()

                # 3. Step physics engine (500Hz)
                mujoco.mj_step(self.model, self.data)

                # 4. Extract telemetry and update the state object at 50Hz
                if counter % 10 == 0:
                    self._update_shared_state()

            # 5. Sync the viewer window periodically (approx 33 FPS, every 15 steps)
            if viewer is not None and counter % 15 == 0 and viewer.is_running():
                viewer.sync()

            counter += 1

            self._clock.sleep_until_next_tick()

        # Shutdown sequence
        if viewer is not None:
            viewer.close()

    def _get_onnx_obs(self) -> np.ndarray:
        with self._lock:
            # gyro
            gyro = self.data.sensordata[self.gyro_addr : self.gyro_addr + 3]
            
            # accelerometer
            accelerometer = self.data.sensordata[self.accelerometer_addr : self.accelerometer_addr + 3].copy()
            accelerometer[0] += 1.3  # Offset adjustment from mujoco_infer.py
            
            # command list: [lin_vel_x, lin_vel_y, ang_vel, neck_pitch, head_pitch, head_yaw, head_roll]
            commands = np.array([
                self._current_linear_x,
                self._current_linear_y,
                self._current_yaw_rate,
                0.0, 0.0, 0.0, 0.0  # head and neck targets default to 0.0
            ])
            
            # joints
            joint_angles = self.data.qpos[self.actuator_joint_qpos_addr]
            joint_vel = self.data.qvel[self.actuator_qvel_addr]
            
            # contacts
            left_contact = self.check_contact("foot_assembly", "floor")
            right_contact = self.check_contact("foot_assembly_2", "floor")
            contacts = np.array([float(left_contact), float(right_contact)])
            
            # Scale parameters from policy contract
            dof_vel_scale = DOF_VEL_SCALE
            
            obs = np.concatenate([
                gyro,
                accelerometer,
                commands,
                joint_angles - self.default_actuator,
                joint_vel * dof_vel_scale,
                self.last_action,
                self.last_last_action,
                self.last_last_last_action,
                self.motor_targets,
                contacts,
                self.imitation_phase
            ])
            
            return obs.astype(np.float32)

    def _apply_onnx_inference(self):
        with self._lock:
            # 1. Update imitation phase tracking
            is_moving = (abs(self._current_linear_x) > 0.01 or abs(self._current_yaw_rate) > 0.01)
            if is_moving:
                self._sim_time += 0.020
                self.imitation_i = (self.imitation_i + 1.0) % self.nb_steps_in_period
                
                phase_rad = (self.imitation_i / self.nb_steps_in_period) * 2.0 * math.pi
                self.imitation_phase = np.array([math.cos(phase_rad), math.sin(phase_rad)])
            else:
                self._sim_time = 0.0
                self.imitation_i = 0.0
                self.imitation_phase = np.array([1.0, 0.0])
                
            # 2. Extract observations
            obs = self._get_onnx_obs()
            
            # 3. Run Inference
            input_name = self._onnx_session.get_inputs()[0].name
            outputs = self._onnx_session.run(None, {input_name: [obs]})
            action = outputs[0][0]  # awd=True format
            
            # 4. Filter & scale actions to motor targets
            self.last_last_last_action = self.last_last_action.copy()
            self.last_last_action = self.last_action.copy()
            self.last_action = action.copy()
            
            self.motor_targets = apply_action_to_targets(action)
            
            # Apply motor speed limits after target ctrlrange clipping.
            USE_MOTOR_SPEED_LIMITS = True
            if USE_MOTOR_SPEED_LIMITS:
                self.motor_targets = apply_target_rate_limit(
                    self.motor_targets,
                    self.prev_motor_targets,
                )
                self.prev_motor_targets = self.motor_targets.copy()
            else:
                self.motor_targets = clamp_targets_to_ctrlrange(self.motor_targets)
                self.prev_motor_targets = self.motor_targets.copy()
                
            # Apply control to MuJoCo
            self.data.ctrl[:] = self.motor_targets

            # 5. Stabilized under 500Hz active gyro correction, no local modifications here.
            pass

    def _stabilize_torso(self):
        with self._lock:
            # Phase 2A: all modes preserve legacy behavior; hybrid/dynamic only label
            # diagnostics until their behavior is separately approved.
            self._legacy_dynamics.apply(self)

    def get_dynamics_diagnostics(self):
        return self._legacy_dynamics.snapshot()

    def _apply_waddle_oscillator(self):
        home_ctrl = self.model.keyframe("home").ctrl
        targets = np.array(home_ctrl)

        is_moving = (abs(self._current_linear_x) > 0.01 or abs(self._current_yaw_rate) > 0.01)
        if is_moving:
            # Update the waddling sim time at control rate (0.02s step)
            self._sim_time += 0.020

            # Waddling parameters scaled by speed
            speed_scale = min(1.0, max(0.2, abs(self._current_linear_x) / 0.25))
            waddle_freq = 6.0 + 2.0 * speed_scale
            phase = self._sim_time * waddle_freq

            # Leg swing & lift amplitudes
            swing_amp = 0.3 * speed_scale
            roll_amp = 0.08  # sway hip roll

            # Left leg
            targets[0] = home_ctrl[0] + 0.1 * math.sin(phase)          # left_hip_yaw
            targets[1] = home_ctrl[1] + roll_amp * math.cos(phase)     # left_hip_roll
            targets[2] = home_ctrl[2] + swing_amp * math.sin(phase)    # left_hip_pitch
            targets[3] = home_ctrl[3] + 0.25 * math.cos(phase)         # left_knee
            targets[4] = home_ctrl[4] - 0.15 * math.sin(phase)         # left_ankle

            # Neck & Head sway to feel alive
            targets[5] = home_ctrl[5] + 0.05 * math.sin(phase)         # neck_pitch
            targets[6] = home_ctrl[6] + 0.05 * math.sin(phase)         # head_pitch
            targets[7] = home_ctrl[7] + 0.08 * math.cos(phase)         # head_yaw
            targets[8] = home_ctrl[8] + 0.04 * math.sin(phase)         # head_roll

            # Right leg (opposite phase)
            targets[9] = home_ctrl[9] + 0.1 * math.sin(phase + math.pi)          # right_hip_yaw
            targets[10] = home_ctrl[10] + roll_amp * math.cos(phase)             # right_hip_roll
            targets[11] = home_ctrl[11] + swing_amp * math.sin(phase + math.pi)  # right_hip_pitch
            targets[12] = home_ctrl[12] + 0.25 * math.cos(phase + math.pi)       # right_knee
            targets[13] = home_ctrl[13] - 0.15 * math.sin(phase + math.pi)       # right_ankle
        else:
            # Settle back to stable home posture
            targets = np.array(home_ctrl)
            self._sim_time = 0.0

        self.data.ctrl[:] = targets

    def _update_shared_state(self, last_command=None):
        with self._lock:
            # 1. Extract position
            pos = self.data.qpos[0:3]
            position = (float(pos[0]), float(pos[1]), float(pos[2]))

            # 2. Extract orientation (Euler roll, pitch, yaw)
            qw, qx, qy, qz = self.data.qpos[3:7]
            roll, pitch, yaw = self.quaternion_to_euler(qw, qx, qy, qz)

            # 3. Detect foot contacts
            left_contact = self.check_contact("foot_assembly", "floor")
            right_contact = self.check_contact("foot_assembly_2", "floor")

            # 4. Formulate the new robot state
            if last_command is not None:
                self._last_command = last_command

            # Update high-level status based on target velocity
            is_moving = (abs(self._current_linear_x) > 0.01 or abs(self._current_yaw_rate) > 0.01)
            if self._state.fallen:
                status = "fallen"
            elif self._last_command == "reset":
                status = "idle"
            elif self._last_command == "stop":
                status = "stopped"
            elif is_moving:
                if abs(self._current_yaw_rate) > 0.1 and abs(self._current_linear_x) < 0.05:
                    status = "turning"
                else:
                    status = "walking"
            else:
                status = "idle"

            new_state = RobotState(
                robot="open_duck_mini_v2",
                status=status,
                sim_time=float(self.data.time),
                position=position,
                orientation=Orientation(roll_deg=roll, pitch_deg=pitch, yaw_deg=yaw % 360.0),
                feet_contact=FeetContact(left=left_contact, right=right_contact),
                fallen=self._state.fallen,
                last_command=self._last_command
            )

            # 5. Check if newly fallen based on orientation/height limits
            if not new_state.fallen and is_fallen(new_state, self._safety_config):
                new_state.fallen = True
                new_state.status = "fallen"

            # Update thread-safe reference
            self._state = new_state
            self._double_buffered_state.update_write_state(new_state)
            self._double_buffered_state.swap()

            # 6. Add debug snapshot to Ringbuffer
            snapshot = {
                "sim_time": new_state.sim_time,
                "position": new_state.position,
                "orientation": (roll, pitch, yaw),
                "velocity": (self._current_linear_x, self._current_linear_y, self._current_yaw_rate),
                "feet_contact": (left_contact, right_contact),
                "fallen": new_state.fallen,
                "command": self._last_command,
                "dynamics": self.get_dynamics_diagnostics()
            }
            self._ringbuffer.append(snapshot)

    def check_contact(self, body1_name, body2_name):
        try:
            body1_id = self.model.body(body1_name).id
            body2_id = self.model.body(body2_name).id
        except KeyError:
            return False

        for i in range(self.data.ncon):
            contact = self.data.contact[i]
            g1_body = self.model.geom_bodyid[contact.geom1]
            g2_body = self.model.geom_bodyid[contact.geom2]
            if (g1_body == body1_id and g2_body == body2_id) or \
               (g1_body == body2_id and g2_body == body1_id):
                return True
        return False

    @staticmethod
    def quaternion_to_euler(qw, qx, qy, qz) -> Tuple[float, float, float]:
        # roll (x-axis rotation)
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # pitch (y-axis rotation)
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(sinp)

        # yaw (z-axis rotation)
        siny_cosp = 2 * (qw * qz + qx * qy)
        cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))

    def reset(self) -> RobotState:
        self._initialize_mujoco()
        import mujoco

        with self._lock:
            # Reset MuJoCo physics state
            mujoco.mj_resetData(self.model, self.data)

            # Set qpos to home keyframe
            home_key = self.model.keyframe("home")
            self.data.qpos[:] = home_key.qpos
            self.data.ctrl[:] = home_key.ctrl

            # Apply standard steps to settle
            for _ in range(50):
                mujoco.mj_step(self.model, self.data)

            # Reset tracking states
            self._target_linear_x = 0.0
            self._target_linear_y = 0.0
            self._target_yaw_rate = 0.0
            self._current_linear_x = 0.0
            self._current_linear_y = 0.0
            self._current_yaw_rate = 0.0
            self._sim_time = 0.0
            self._last_command = "reset"
            self._last_command_time = time.time()
            self._kinematic_yaw = 0.0

            # Re-initialize state safely
            self._state = RobotState(
                robot="open_duck_mini_v2",
                status="idle",
                sim_time=0.0,
                position=(float(self.data.qpos[0]), float(self.data.qpos[1]), float(self.data.qpos[2])),
                orientation=Orientation(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0),
                feet_contact=FeetContact(left=True, right=True),
                fallen=False,
                last_command="reset"
            )
            self._update_shared_state(last_command="reset")
        return self.get_state()

    def stop(self) -> RobotState:
        with self._lock:
            self._target_linear_x = 0.0
            self._target_linear_y = 0.0
            self._target_yaw_rate = 0.0
            self._last_command = "stop"
            self._last_command_time = time.time()
            self._update_shared_state(last_command="stop")
        return self.get_state()

    def get_state(self) -> RobotState:
        self._initialize_mujoco()
        from duck_agent_sim.config import DUCK_SIM_MODE

        state = self._double_buffered_state.get_read_state()
        return with_stability(state, self._safety_config, DUCK_SIM_MODE)

    def get_sensor_state(self) -> SensorsState:
        self._initialize_mujoco()
        from duck_agent_sim.config import DUCK_SIM_MODE
        import mujoco

        def read_sensor(name: str, dim: int):
            sensor_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, name)
            if sensor_id < 0:
                return None
            addr = int(self.model.sensor_adr[sensor_id])
            return _vec(self.data.sensordata[addr : addr + dim], dim)

        with self._lock:
            state = self._state.model_copy(deep=True)
            imu_values = {
                "gyro": read_sensor("gyro", 3),
                "accelerometer": read_sensor("accelerometer", 3),
                "local_linvel": read_sensor("local_linvel", 3),
                "global_linvel": read_sensor("global_linvel", 3),
                "global_angvel": read_sensor("global_angvel", 3),
                "position": read_sensor("position", 3),
                "orientation": read_sensor("orientation", 4),
                "upvector": read_sensor("upvector", 3),
                "forwardvector": read_sensor("forwardvector", 3),
            }
            left_values = {
                "position": read_sensor("left_foot_pos", 3),
                "velocity": read_sensor("left_foot_global_linvel", 3),
                "axis": read_sensor("left_foot_upvector", 3),
            }
            right_values = {
                "position": read_sensor("right_foot_pos", 3),
                "velocity": read_sensor("right_foot_global_linvel", 3),
                "axis": read_sensor("right_foot_upvector", 3),
            }

            imu_available = all(value is not None for value in imu_values.values())
            left_available = all(value is not None for value in left_values.values())
            right_available = all(value is not None for value in right_values.values())

            return SensorsState(
                mode=DUCK_SIM_MODE,
                sim_time=state.sim_time,
                timestamp=time.time(),
                imu=SensorAvailability(available=imu_available, **imu_values),
                feet={
                    "left": SensorAvailability(available=left_available, **left_values),
                    "right": SensorAvailability(available=right_available, **right_values),
                },
            )

    def get_clock_telemetry(self):
        return self._clock.telemetry()

    def set_desired_control(
        self,
        control: ControlIntent,
        safety: Optional[SafetyConfig] = None,
        *,
        command: str = "external_control",
        duration_sec: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> RobotState:
        self._initialize_mujoco()
        with self._lock:
            self._target_linear_x = control.linear_x
            self._target_linear_y = control.linear_y
            self._target_yaw_rate = control.yaw
            self._last_command = command
            self._last_command_time = time.time()
            self._safety_config = safety or SafetyConfig()
        return self.get_state()

    async def execute_command_async(
        self,
        command: RobotCommand,
        *,
        request_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> CommandResponse:
        self._initialize_mujoco()
        if command.command == "reset":
            state = self.reset()
            control = map_command(command)
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=state)

        if command.command == "stop":
            state = self.stop()
            control = map_command(command)
            return CommandResponse(accepted=True, command=command.command, mapped_control=control, state=state)

        if self.get_state().fallen:
            self.stop()
            return CommandResponse(accepted=False, command=command.command, mapped_control=ZERO_CONTROL, state=self.get_state())

        control = map_command(command)
        self.set_desired_control(
            control,
            command.safety,
            command=command.command,
            duration_sec=command_duration(command),
            request_id=request_id,
        )
        deadline = time.monotonic() + command_duration(command)
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                self.stop()
                raise asyncio.CancelledError()
            if self.get_state().fallen:
                break
            await asyncio.sleep(0.01)

        if self.get_state().fallen and command.safety.stop_on_fall:
            self.stop()

        return CommandResponse(
            accepted=True,
            command=command.command,
            mapped_control=control,
            state=self.get_state(),
        )

    def apply_command(self, command: RobotCommand) -> CommandResponse:
        self._initialize_mujoco()
        with self._command_exec_lock:
            # 1. Reset if requested
            if command.command == "reset":
                self.reset()
                control = map_command(command)
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 2. Check if already fallen
            if self._state.fallen:
                control = ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0)
                self._target_linear_x = 0.0
                self._target_linear_y = 0.0
                self._target_yaw_rate = 0.0
                return CommandResponse(
                    accepted=False,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 3. Map command to controls and update targets
            control = map_command(command)
            self._target_linear_x = control.linear_x
            self._target_linear_y = control.linear_y
            self._target_yaw_rate = control.yaw
            self._last_command = command.command
            self._last_command_time = time.time()

            # 4. Wait for duration of command, checking if it falls mid-step
            elapsed = 0.0
            dt = 0.05
            while elapsed < command.duration_sec:
                if self._state.fallen:
                    break
                time.sleep(dt)
                elapsed += dt

            # If safety requires stop on fall, we do it
            if self._state.fallen and command.safety.stop_on_fall:
                self._target_linear_x = 0.0
                self._target_linear_y = 0.0
                self._target_yaw_rate = 0.0

            return CommandResponse(
                accepted=True,
                command=command.command,
                mapped_control=control,
                state=self.get_state()
            )

    async def apply_command_async(self, command: RobotCommand) -> CommandResponse:
        self._initialize_mujoco()
        with self._command_exec_lock:
            # 1. Reset if requested
            if command.command == "reset":
                self.reset()
                control = map_command(command)
                return CommandResponse(
                    accepted=True,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 2. Check if already fallen
            if self._state.fallen:
                control = ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0)
                self._target_linear_x = 0.0
                self._target_linear_y = 0.0
                self._target_yaw_rate = 0.0
                return CommandResponse(
                    accepted=False,
                    command=command.command,
                    mapped_control=control,
                    state=self.get_state()
                )

            # 3. Map command to controls and update targets
            control = map_command(command)
            self._target_linear_x = control.linear_x
            self._target_linear_y = control.linear_y
            self._target_yaw_rate = control.yaw
            self._last_command = command.command
            self._last_command_time = time.time()

            # 4. Wait for duration of command, checking if it falls mid-step
            elapsed = 0.0
            dt = 0.05
            while elapsed < command.duration_sec:
                if self._state.fallen:
                    break
                await asyncio.sleep(dt)
                elapsed += dt

            # If safety requires stop on fall, we do it
            if self._state.fallen and command.safety.stop_on_fall:
                self._target_linear_x = 0.0
                self._target_linear_y = 0.0
                self._target_yaw_rate = 0.0

            return CommandResponse(
                accepted=True,
                command=command.command,
                mapped_control=control,
                state=self.get_state()
            )

    def step(self, control: ControlIntent, dt: float, safety: SafetyConfig) -> RobotState:
        self._initialize_mujoco()
        self._target_linear_x = control.linear_x
        self._target_linear_y = control.linear_y
        self._target_yaw_rate = control.yaw
        self._last_command_time = time.time()

        return self.get_state()

    def close(self):
        """Cleans up background threads, stops vision loops, and closes the viewer window."""
        self._running = False
        from duck_agent_sim.vision import follower
        if follower is not None:
            follower.stop()
        if hasattr(self, "vision_loop") and self.vision_loop is not None:
            self.vision_loop.stop()
        if hasattr(self, "camera_device") and self.camera_device is not None:
            self.camera_device.close()
        if hasattr(self, "_thread") and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
