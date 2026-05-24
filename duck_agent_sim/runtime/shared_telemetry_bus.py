import ctypes
import logging
from multiprocessing import shared_memory
from typing import Dict, Tuple, Optional

logger = logging.getLogger("duck-shared-bus")

# C-type Structures for High-Performance Lock-Free IPC

class SensorsTelemetryStruct(ctypes.Structure):
    _fields_ = [
        ("sim_time", ctypes.c_double),
        ("timestamp", ctypes.c_double),
        ("battery_voltage", ctypes.c_double),
        ("left_contact", ctypes.c_bool),
        ("right_contact", ctypes.c_bool),
        ("accel_x", ctypes.c_double),
        ("accel_y", ctypes.c_double),
        ("accel_z", ctypes.c_double),
        ("gyro_x", ctypes.c_double),
        ("gyro_y", ctypes.c_double),
        ("gyro_z", ctypes.c_double),
        ("quat_w", ctypes.c_double),
        ("quat_x", ctypes.c_double),
        ("quat_y", ctypes.c_double),
        ("quat_z", ctypes.c_double),
    ]

class ServosTelemetryStruct(ctypes.Structure):
    _fields_ = [
        ("present_pos", ctypes.c_double * 14),
        ("present_vel", ctypes.c_double * 14),
        ("present_load", ctypes.c_double * 14),
        ("present_temp", ctypes.c_double * 14),
        ("target_pos", ctypes.c_double * 14),
        ("torque_enabled", ctypes.c_bool * 14),
    ]

class RobotStateStruct(ctypes.Structure):
    _fields_ = [
        ("fsm_state", ctypes.c_char * 32),
        ("pos_x", ctypes.c_double),
        ("pos_y", ctypes.c_double),
        ("pos_z", ctypes.c_double),
        ("vel_x", ctypes.c_double),
        ("vel_y", ctypes.c_double),
        ("vel_z", ctypes.c_double),
        ("roll", ctypes.c_double),
        ("pitch", ctypes.c_double),
        ("yaw", ctypes.c_double),
        ("status", ctypes.c_char * 32),
        ("fallen", ctypes.c_bool),
    ]

class CommandQueueStruct(ctypes.Structure):
    _fields_ = [
        ("cmd_type", ctypes.c_char * 32),
        ("linear_x", ctypes.c_double),
        ("linear_y", ctypes.c_double),
        ("yaw", ctypes.c_double),
        ("duration_sec", ctypes.c_double),
        ("state_override", ctypes.c_char * 32),
        ("heartbeat", ctypes.c_double),
    ]

class SharedTelemetryBus:
    """
    Manages shared memory segments for low-latency, lock-free telemetry.
    Initializes and cleans up memory-mapped C structures.
    """
    def __init__(self, create: bool = False, namespace: str = "duck_robot"):
        self.create = create
        self.namespace = namespace
        self.shm_blocks: Dict[str, shared_memory.SharedMemory] = {}
        
        # Structure sizes
        self.sizes = {
            "sensors": ctypes.sizeof(SensorsTelemetryStruct),
            "servos": ctypes.sizeof(ServosTelemetryStruct),
            "state": ctypes.sizeof(RobotStateStruct),
            "command": ctypes.sizeof(CommandQueueStruct),
        }
        
        self.init_shm()

    def init_shm(self):
        for key, size in self.sizes.items():
            shm_name = f"{self.namespace}_{key}"
            try:
                if self.create:
                    # Attempt to clean up old segment if it exists
                    try:
                        temp = shared_memory.SharedMemory(name=shm_name)
                        temp.close()
                        temp.unlink()
                    except Exception:
                        pass
                    shm = shared_memory.SharedMemory(name=shm_name, create=True, size=size)
                    # Initialize memory to zero
                    shm.buf[:size] = b'\x00' * size
                else:
                    shm = shared_memory.SharedMemory(name=shm_name, create=False)
                
                self.shm_blocks[key] = shm
                logger.info(f"Initialized shared memory block '{shm_name}' (size: {size} bytes).")
            except Exception as e:
                logger.critical(f"Failed to initialize shared memory block '{shm_name}': {e}")
                raise

    def get_sensors_ref(self) -> SensorsTelemetryStruct:
        shm = self.shm_blocks["sensors"]
        return SensorsTelemetryStruct.from_buffer(shm.buf)

    def get_servos_ref(self) -> ServosTelemetryStruct:
        shm = self.shm_blocks["servos"]
        return ServosTelemetryStruct.from_buffer(shm.buf)

    def get_state_ref(self) -> RobotStateStruct:
        shm = self.shm_blocks["state"]
        return RobotStateStruct.from_buffer(shm.buf)

    def get_command_ref(self) -> CommandQueueStruct:
        shm = self.shm_blocks["command"]
        return CommandQueueStruct.from_buffer(shm.buf)

    def close(self):
        for key, shm in list(self.shm_blocks.items()):
            try:
                shm.close()
                if self.create:
                    shm.unlink()
                logger.info(f"Closed shared memory block for {key}.")
            except Exception as e:
                logger.error(f"Error closing shm block {key}: {e}")
        self.shm_blocks.clear()
