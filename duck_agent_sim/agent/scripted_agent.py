import time
import logging
import math
from typing import Dict, Any, List, Tuple

from duck_agent_sim.schemas import RobotCommand, RobotState, SafetyConfig

logger = logging.getLogger("scripted-agent")

class ScriptedAgent:
    """
    A deterministic scripting agent that controls a Duck simulator.
    Can be run directly via local Python calls or later integrated via REST HTTP clients.
    """

    def __init__(self, simulator_or_client: Any):
        # Can accept the active simulator instance or a mock client
        self.simulator = simulator_or_client

    def run_basic_walk(self) -> List[RobotState]:
        """
        Executes a basic walk scenario:
        1. Check state, reset if fallen
        2. Walk forward for 2.0 seconds
        3. Stop
        """
        logger.info("Starting Basic Walk scenario...")
        state = self.simulator.get_state()
        history = [state]

        if state.fallen:
            logger.info("Robot is fallen. Issuing reset command first...")
            self.simulator.reset()
            state = self.simulator.get_state()
            history.append(state)

        # Walk forward
        cmd_walk = RobotCommand(
            command="walk_forward",
            speed=0.25,
            turn=0.0,
            duration_sec=2.0,
            safety=SafetyConfig()
        )
        logger.info("Executing walk_forward for 2.0s...")
        res = self.simulator.apply_command(cmd_walk)
        history.append(res.state)

        if res.state.fallen:
            logger.warning("Robot fell during walk forward step!")
            return history

        # Stop
        cmd_stop = RobotCommand(
            command="stop",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        logger.info("Executing stop...")
        res_stop = self.simulator.apply_command(cmd_stop)
        history.append(res_stop.state)

        logger.info("Basic Walk scenario completed.")
        return history

    def run_walk_square(self) -> List[RobotState]:
        """
        Executes a 4-sided square route:
        - Walk forward 3 sec
        - Turn left 1.5 sec
        - Repeat 4 times
        - Stop
        """
        logger.info("Starting Walk Square scenario...")
        self.simulator.reset()
        history = [self.simulator.get_state()]

        steps = [
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("turn_left", 1.57, 1.0),
            ("walk_forward", 3.0, 0.0),
            ("stop", 1.0, 0.0)
        ]

        for idx, (command, duration, turn) in enumerate(steps):
            cmd = RobotCommand(
                command=command,
                speed=0.25 if command != "stop" else 0.0,
                turn=turn,
                duration_sec=duration,
                safety=SafetyConfig()
            )
            logger.info(f"Step {idx+1}: Executing {command} (duration={duration}s, turn={turn})...")
            res = self.simulator.apply_command(cmd)
            history.append(res.state)

            if res.state.fallen:
                logger.error(f"Safety violation! Robot fell at Step {idx+1} ({command}). Aborting.")
                break

        logger.info("Walk Square scenario completed.")
        return history

    def run_recover_test(self) -> List[RobotState]:
        """
        Tests the safety and recovery loop:
        1. Force a fallen state in mock mode
        2. Verify subsequent walk commands are rejected
        3. Issue reset and verify recovery to idle state
        """
        logger.info("Starting Recover Test scenario...")
        self.simulator.reset()

        # Force a fall by calling simulator tilt method directly
        if hasattr(self.simulator, "force_tilt"):
            logger.info("Injecting severe roll (50 deg) to trigger fall safety...")
            self.simulator.force_tilt(roll=50.0, pitch=0.0)
        else:
            logger.warning("Simulator does not support direct force_tilt injection. Skipping tilt injection.")

        state_before = self.simulator.get_state()
        # Verify it registers as fallen
        logger.info(f"Fallen state registered? {state_before.fallen} (Status: {state_before.status})")

        # Try to walk forward - should be rejected by safety layers
        cmd_walk = RobotCommand(
            command="walk_forward",
            speed=0.25,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        logger.info("Attempting to walk while fallen...")
        res = self.simulator.apply_command(cmd_walk)
        logger.info(f"Command accepted? {res.accepted} (Status: {res.state.status})")

        # Issue reset recovery
        logger.info("Issuing recovery reset command...")
        cmd_reset = RobotCommand(
            command="reset",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        res_reset = self.simulator.apply_command(cmd_reset)
        logger.info(f"Recovered? Fallen={res_reset.state.fallen} (Status: {res_reset.state.status}, Pos Z: {res_reset.state.position[2]}m)")

        return [state_before, res.state, res_reset.state]

    def _trigger_local_vision(self):
        if hasattr(self.simulator, "spatial_model") and self.simulator.spatial_model is not None:
            try:
                from duck_agent_sim.vision.yolo_detector import YOLODetector
                import numpy as np
                state = self.simulator.get_state()
                dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                detector = YOLODetector()
                detections = detector.detect(dummy_frame)
                self.simulator.spatial_model.update(
                    robot_x=state.position[0],
                    robot_y=state.position[1],
                    robot_yaw_deg=state.orientation.yaw_deg,
                    detections=detections,
                    img_w=640,
                    img_h=480
                )
            except Exception as e:
                logger.error(f"Failed to manually trigger local vision: {e}")

    def _is_obstacle_ahead(self, state: RobotState, spatial_model, check_dist_m: float = 0.5) -> bool:
        if spatial_model is None:
            return False
            
        rx, ry = state.position[0], state.position[1]
        ryaw_rad = math.radians(state.orientation.yaw_deg)
        
        # Check coordinates along the forward ray at 0.1m intervals
        steps = int(check_dist_m / 0.1)
        for i in range(1, steps + 1):
            dist = i * 0.1
            cx = rx + dist * math.cos(ryaw_rad)
            cy = ry + dist * math.sin(ryaw_rad)
            
            # Check cell and neighbors
            gx, gy = spatial_model.world_to_grid(cx, cy)
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    nx = gx + dx
                    ny = gy + dy
                    if 0 <= nx < spatial_model.grid_size and 0 <= ny < spatial_model.grid_size:
                        if spatial_model.grid[ny][nx] == 2: # Occupied
                            return True
        return False

    def run_patrol_landmarks(self) -> List[RobotState]:
        """
        Executes a landmark discovery and patrol scenario:
        1. Rotate 360 degrees to scan the room and map landmarks.
        2. Inspect the Spatial World Model and pick the closest mapped landmark.
        3. Navigate towards the landmark's coordinates until within 0.3m.
        4. Stop.
        5. Return to start position (0, 0) and stop.
        """
        logger.info("Starting Patrol Landmarks scenario...")
        self.simulator.reset()
        history = [self.simulator.get_state()]
        
        # Step 1: Discover landmarks by spinning
        logger.info("Step 1: Discovering landmarks by spinning...")
        for _ in range(5):
            cmd_turn = RobotCommand(
                command="turn_left",
                speed=0.0,
                turn=0.6,
                duration_sec=0.6,
                safety=SafetyConfig()
            )
            res = self.simulator.apply_command(cmd_turn)
            history.append(res.state)
            self._trigger_local_vision()
            
        # Inspect landmarks
        map_data = self.simulator.spatial_model.get_map_data()
        landmarks = map_data.get("landmarks", {})
        logger.info(f"Discovered landmarks: {list(landmarks.keys())}")
        
        if not landmarks:
            logger.warning("No landmarks discovered during scan. Aborting patrol.")
            return history
            
        # Select the closest landmark
        state = self.simulator.get_state()
        rx, ry = state.position[0], state.position[1]
        
        closest_lm_key = None
        min_dist = float("inf")
        
        for k, lm in landmarks.items():
            # Skip base class entries without instances (prefix matched keys are like 'chair_1')
            if "_" not in k:
                continue
            dist = math.hypot(lm["x"] - rx, lm["y"] - ry)
            if dist < min_dist:
                min_dist = dist
                closest_lm_key = k
                
        if closest_lm_key is None:
            # Fall back to any landmark if no instance key format found
            if landmarks:
                closest_lm_key = list(landmarks.keys())[0]
                min_dist = math.hypot(landmarks[closest_lm_key]["x"] - rx, landmarks[closest_lm_key]["y"] - ry)
                
        target_lm = landmarks[closest_lm_key]
        tx, ty = target_lm["x"], target_lm["y"]
        logger.info(f"Step 2: Selected closest landmark '{closest_lm_key}' at ({tx:.2f}, {ty:.2f}) (distance: {min_dist:.2f}m)")
        
        # Step 3: Navigate to target
        logger.info("Step 3: Navigating to landmark...")
        
        max_steps = 15
        for step_idx in range(max_steps):
            state = self.simulator.get_state()
            rx, ry = state.position[0], state.position[1]
            ryaw = state.orientation.yaw_deg
            
            dx = tx - rx
            dy = ty - ry
            dist = math.hypot(dx, dy)
            
            if dist < 0.3:
                logger.info(f"Arrived at target landmark (dist: {dist:.2f}m).")
                break
                
            # Compute bearing
            target_yaw_rad = math.atan2(dy, dx)
            target_yaw_deg = math.degrees(target_yaw_rad)
            diff_yaw = target_yaw_deg - ryaw
            diff_yaw = (diff_yaw + 180) % 360 - 180
            
            # Formulate command based on orientation difference
            if abs(diff_yaw) > 15.0:
                direction = "turn_left" if diff_yaw > 0 else "turn_right"
                turn_val = 0.4 if diff_yaw > 0 else -0.4
                cmd = RobotCommand(
                    command=direction,
                    speed=0.0,
                    turn=turn_val,
                    duration_sec=0.5,
                    safety=SafetyConfig()
                )
            else:
                speed_val = min(0.25, dist / 2.0)
                turn_val = (diff_yaw / 15.0) * 0.1
                cmd = RobotCommand(
                    command="walk_forward",
                    speed=speed_val,
                    turn=turn_val,
                    duration_sec=0.5,
                    safety=SafetyConfig()
                )
                
            res = self.simulator.apply_command(cmd)
            history.append(res.state)
            self._trigger_local_vision()
            
        # Step 4: Return to start (0, 0)
        logger.info("Step 4: Returning to home position (0, 0)...")
        tx, ty = 0.0, 0.0
        for step_idx in range(max_steps):
            state = self.simulator.get_state()
            rx, ry = state.position[0], state.position[1]
            ryaw = state.orientation.yaw_deg
            
            dx = tx - rx
            dy = ty - ry
            dist = math.hypot(dx, dy)
            
            if dist < 0.2:
                logger.info(f"Arrived back home (dist: {dist:.2f}m).")
                break
                
            # Compute bearing
            target_yaw_rad = math.atan2(dy, dx)
            target_yaw_deg = math.degrees(target_yaw_rad)
            diff_yaw = target_yaw_deg - ryaw
            diff_yaw = (diff_yaw + 180) % 360 - 180
            
            if abs(diff_yaw) > 15.0:
                direction = "turn_left" if diff_yaw > 0 else "turn_right"
                turn_val = 0.4 if diff_yaw > 0 else -0.4
                cmd = RobotCommand(
                    command=direction,
                    speed=0.0,
                    turn=turn_val,
                    duration_sec=0.5,
                    safety=SafetyConfig()
                )
            else:
                speed_val = min(0.25, dist / 2.0)
                turn_val = (diff_yaw / 15.0) * 0.1
                cmd = RobotCommand(
                    command="walk_forward",
                    speed=speed_val,
                    turn=turn_val,
                    duration_sec=0.5,
                    safety=SafetyConfig()
                )
                
            res = self.simulator.apply_command(cmd)
            history.append(res.state)
            self._trigger_local_vision()
            
        # Step 5: Stop
        logger.info("Step 5: Stopping robot.")
        cmd_stop = RobotCommand(
            command="stop",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        res = self.simulator.apply_command(cmd_stop)
        history.append(res.state)
        self._trigger_local_vision()
        
        logger.info("Patrol Landmarks scenario completed.")
        return history

    def run_obstacle_avoidance(self, duration_sec: float = 5.0) -> List[RobotState]:
        """
        Executes a reactive obstacle avoidance scenario:
        - Walk forward.
        - Poll the occupancy grid.
        - If an obstacle is detected within 0.5m ahead, execute a turn to the side to clear it.
        - Repeat until total duration has elapsed.
        """
        logger.info("Starting Obstacle Avoidance scenario...")
        self.simulator.reset()
        history = [self.simulator.get_state()]
        
        # Populating the map with initial vision trigger
        self._trigger_local_vision()
        
        step_duration = 0.5
        total_steps = int(duration_sec / step_duration)
        
        for step_idx in range(total_steps):
            state = self.simulator.get_state()
            if state.fallen:
                logger.error("Robot fell during obstacle avoidance scenario! Aborting.")
                break
                
            # Check if obstacle is ahead
            obstacle_ahead = self._is_obstacle_ahead(state, self.simulator.spatial_model)
            
            if obstacle_ahead:
                logger.info(f"Obstacle detected ahead! Executing avoidance turn...")
                cmd = RobotCommand(
                    command="turn_left",
                    speed=0.0,
                    turn=0.5,
                    duration_sec=0.8,
                    safety=SafetyConfig()
                )
            else:
                logger.info(f"Path clear. Walking forward...")
                cmd = RobotCommand(
                    command="walk_forward",
                    speed=0.25,
                    turn=0.0,
                    duration_sec=step_duration,
                    safety=SafetyConfig()
                )
                
            res = self.simulator.apply_command(cmd)
            history.append(res.state)
            self._trigger_local_vision()
            
        # Final stop
        cmd_stop = RobotCommand(
            command="stop",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        res = self.simulator.apply_command(cmd_stop)
        history.append(res.state)
        self._trigger_local_vision()
        
        logger.info("Obstacle Avoidance scenario completed.")
        return history

    def run_navigate_map(self, target_world_coords: Tuple[float, float]) -> List[RobotState]:
        """
        Executes global navigation to target_world_coords:
        - Plans a global path using AStarPlanner.
        - Commands the robot to follow the waypoints using PurePursuitTracker.
        - Runs in a loop, polling state and applying steering controls.
        """
        logger.info(f"Starting Navigate Map scenario to target {target_world_coords}...")
        
        # Reset simulator and trigger initial vision update
        self.simulator.reset()
        self._trigger_local_vision()
        
        state = self.simulator.get_state()
        history = [state]
        
        if state.fallen:
            logger.info("Robot is fallen. Issuing reset command first...")
            self.simulator.reset()
            state = self.simulator.get_state()
            history.append(state)
            
        spatial_model = getattr(self.simulator, "spatial_model", None)
        if spatial_model is None:
            # Fallback if no spatial model: straight line
            logger.warning("Spatial model not found on simulator. Executing straight command fallback.")
            cmd = RobotCommand(
                command="walk_forward",
                speed=0.25,
                turn=0.0,
                duration_sec=2.0,
                safety=SafetyConfig()
            )
            res = self.simulator.apply_command(cmd)
            history.append(res.state)
            return history
            
        from duck_agent_sim.simulator.path_planner import AStarPlanner, PurePursuitTracker
        
        # 1. Plan path using A*
        start_coords = (state.position[0], state.position[1])
        planner = AStarPlanner(spatial_model)
        path = planner.plan_path(start_coords, target_world_coords)
        
        if not path:
            logger.warning("No path found by A*. Aborting.")
            return history
            
        tracker = PurePursuitTracker(lookahead_distance=0.4, max_speed=0.25, max_yaw_speed=0.5)
        
        # 2. Follow waypoints
        max_steps = 40  # prevent infinite loops
        step_duration = 0.5
        
        for step in range(max_steps):
            state = self.simulator.get_state()
            if state.fallen:
                logger.error("Robot fell during navigate map scenario! Aborting.")
                break
                
            # Get current pose
            pose = (state.position[0], state.position[1], state.orientation.yaw_deg)
            
            # Compute steering command
            linear_x, yaw_rate, arrived = tracker.get_steering_command(pose, path)
            
            if arrived:
                logger.info("Destination reached successfully.")
                break
                
            # Map linear_x and yaw_rate to RobotCommand
            if linear_x == 0.0:
                cmd_type = "turn_left" if yaw_rate > 0 else "turn_right"
                cmd = RobotCommand(
                    command=cmd_type,
                    speed=0.0,
                    turn=yaw_rate,
                    duration_sec=step_duration,
                    safety=SafetyConfig()
                )
            else:
                cmd = RobotCommand(
                    command="walk_forward",
                    speed=linear_x,
                    turn=yaw_rate,
                    duration_sec=step_duration,
                    safety=SafetyConfig()
                )
                
            res = self.simulator.apply_command(cmd)
            history.append(res.state)
            self._trigger_local_vision()
            
        # Final stop
        cmd_stop = RobotCommand(
            command="stop",
            speed=0.0,
            turn=0.0,
            duration_sec=1.0,
            safety=SafetyConfig()
        )
        res = self.simulator.apply_command(cmd_stop)
        history.append(res.state)
        self._trigger_local_vision()
        
        logger.info("Navigate Map scenario completed.")
        return history

