import logging
import math
import time
from typing import Tuple, Optional

logger = logging.getLogger("duck-bno055")

# BNO055 Register Map (simplified)
BNO055_ADDRESS = 0x28  # Default I2C address
BNO055_CHIP_ID_ADDR = 0x00
BNO055_CHIP_ID = 0xA0

BNO055_OPR_MODE_ADDR = 0x3D
OPR_MODE_CONFIG = 0x00
OPR_MODE_NDOF = 0x0C  # 9 degrees of freedom sensor fusion mode

BNO055_QUA_DATA_W_LSB = 0x20
BNO055_GYR_DATA_X_LSB = 0x14
BNO055_ACC_DATA_X_LSB = 0x08
BNO055_SYS_TRIGGER_ADDR = 0x3F

class BNO055Driver:
    """
    BNO055 Intelligent 9-axis Absolute Orientation Sensor Driver.
    Communicates via I2C SMBus on Raspberry Pi 5.
    Falls back to simulated orientation outputs on non-RPi platforms.
    """
    def __init__(self, bus_id: int = 1, address: int = BNO055_ADDRESS):
        self.bus_id = bus_id
        self.address = address
        self.bus = None
        self.is_hardware = False
        
        self.connect()

    def connect(self) -> bool:
        try:
            import smbus2
            self.bus = smbus2.SMBus(self.bus_id)
            # Verify chip ID
            chip_id = self.bus.read_byte_data(self.address, BNO055_CHIP_ID_ADDR)
            if chip_id != BNO055_CHIP_ID:
                logger.warning(f"BNO055 chip ID mismatch: expected {hex(BNO055_CHIP_ID)}, got {hex(chip_id)}")
                return False
                
            # Set CONFIG mode to configure registers
            self.bus.write_byte_data(self.address, BNO055_OPR_MODE_ADDR, OPR_MODE_CONFIG)
            time.sleep(0.02)
            
            # Set NDOF mode (Absolute Orientation)
            self.bus.write_byte_data(self.address, BNO055_OPR_MODE_ADDR, OPR_MODE_NDOF)
            time.sleep(0.02)
            
            self.is_hardware = True
            logger.info(f"Successfully connected to BNO055 IMU on I2C bus {self.bus_id} at address {hex(self.address)}")
            return True
        except Exception as e:
            self.is_hardware = False
            logger.warning(f"Could not open I2C bus {self.bus_id} ({e}). Falling back to BNO055 simulation mode.")
            return False

    def _read_vector16(self, reg_addr: int) -> Optional[Tuple[float, float, float]]:
        """Reads 6 bytes starting at reg_addr and parses into 3 signed 16-bit integers."""
        if not self.is_hardware:
            return None
            
        try:
            # Read block of 6 bytes (LSB/MSB for X, Y, Z)
            data = self.bus.read_i2c_block_data(self.address, reg_addr, 6)
            if len(data) < 6:
                return None
                
            def to_signed16(low: int, high: int) -> int:
                val = low | (high << 8)
                return val - 65536 if val > 32767 else val
                
            x = to_signed16(data[0], data[1])
            y = to_signed16(data[2], data[3])
            z = to_signed16(data[4], data[5])
            return float(x), float(y), float(z)
        except Exception as e:
            logger.error(f"Error reading from BNO055: {e}")
            return None

    def read_quaternion(self) -> Tuple[float, float, float, float]:
        """
        Reads absolute orientation quaternion (w, x, y, z).
        Units: 1 quaternion = 2^14 units
        """
        if not self.is_hardware:
            # Return simulated walking orientation (a small oscillation centered around upright)
            t = time.time()
            roll = 0.05 * math.sin(t * 8.0)
            pitch = 0.03 * math.cos(t * 16.0)
            yaw = 0.0
            
            # Convert Euler to Quat (w, x, y, z)
            cy = math.cos(yaw * 0.5)
            sy = math.sin(yaw * 0.5)
            cp = math.cos(pitch * 0.5)
            sp = math.sin(pitch * 0.5)
            cr = math.cos(roll * 0.5)
            sr = math.sin(roll * 0.5)

            qw = cr * cp * cy + sr * sp * sy
            qx = sr * cp * cy - cr * sp * sy
            qy = cr * sp * cy + sr * cp * sy
            qz = cr * cp * sy - sr * sp * cy
            return qw, qx, qy, qz

        try:
            # Read 8 bytes of quaternion data (w, x, y, z)
            data = self.bus.read_i2c_block_data(self.address, BNO055_QUA_DATA_W_LSB, 8)
            if len(data) < 8:
                return 1.0, 0.0, 0.0, 0.0
                
            def to_signed16(low: int, high: int) -> int:
                val = low | (high << 8)
                return val - 65536 if val > 32767 else val
                
            w = to_signed16(data[0], data[1])
            x = to_signed16(data[2], data[3])
            y = to_signed16(data[4], data[5])
            z = to_signed16(data[6], data[7])
            
            # Normalize with scale factor 2^14
            scale = 1.0 / 16384.0
            return w * scale, x * scale, y * scale, z * scale
        except Exception as e:
            logger.error(f"Error reading quaternion from BNO055: {e}")
            return 1.0, 0.0, 0.0, 0.0

    def read_gyroscope(self) -> Tuple[float, float, float]:
        """Reads angular velocities in rad/s."""
        raw = self._read_vector16(BNO055_GYR_DATA_X_LSB)
        if raw is None:
            # Return zero simulated gyro
            return 0.0, 0.0, 0.0
            
        # LSB = 16 LSB per degree per second (default configuration)
        # Convert to radians/s
        scale = math.radians(1.0 / 16.0)
        return raw[0] * scale, raw[1] * scale, raw[2] * scale

    def read_accelerometer(self) -> Tuple[float, float, float]:
        """Reads linear acceleration in m/s^2."""
        raw = self._read_vector16(BNO055_ACC_DATA_X_LSB)
        if raw is None:
            # Return simulated gravity acceleration
            return 0.0, 0.0, 9.81
            
        # LSB = 100 LSB per m/s^2 (default configuration)
        scale = 1.0 / 100.0
        return raw[0] * scale, raw[1] * scale, raw[2] * scale
