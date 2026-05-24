import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("duck-sts3215")

# STS3215 Register Address Map
REG_TORQUE_ENABLE = 0x28
REG_ACCELERATION = 0x29
REG_TARGET_POSITION = 0x2A
REG_TARGET_SPEED = 0x2E
REG_TORQUE_LIMIT = 0x24  # Torque limit (Max Torque)
REG_LOCK = 0x37
REG_PRESENT_POSITION = 0x38
REG_PRESENT_SPEED = 0x3C
REG_PRESENT_LOAD = 0x3E
REG_PRESENT_VOLTAGE = 0x3F
REG_PRESENT_TEMPERATURE = 0x40
REG_PRESENT_CURRENT = 0x42

# Feetech Instruction Set
INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03
INST_REG_WRITE = 0x04
INST_ACTION = 0x05
INST_SYNC_WRITE = 0x83
INST_SYNC_READ = 0x82

class STS3215Driver:
    """
    Feetech STS3215 Smart Servo Driver.
    Supports physical serial communication on Raspberry Pi 5
    and falls back to a simulated mock mode when running on macOS/development hosts.
    """
    def __init__(self, port: str = "/dev/ttyAMA0", baudrate: int = 1000000, timeout: float = 0.05):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self.is_hardware = False
        self._mock_positions: Dict[int, int] = {i: 2048 for i in range(1, 15)}  # 2048 is middle position (180 deg)
        self._mock_torque: Dict[int, bool] = {i: False for i in range(1, 15)}
        self._mock_temperatures: Dict[int, int] = {i: 35 for i in range(1, 15)}
        self._mock_currents: Dict[int, float] = {i: 0.0 for i in range(1, 15)}
        
        # High-Fidelity kinetic simulation states
        self._target_positions: Dict[int, int] = {i: 2048 for i in range(1, 15)}
        self._present_positions: Dict[int, float] = {i: 2048.0 for i in range(1, 15)}
        self._last_update_time: Dict[int, float] = {i: time.time() for i in range(1, 15)}
        
        self.connect()

    def connect(self) -> bool:
        try:
            import serial
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            self.is_hardware = True
            logger.info(f"Successfully connected to Feetech STS3215 servo bus on {self.port} at {self.baudrate} baud.")
            return True
        except Exception as e:
            self.is_hardware = False
            logger.warning(f"Could not open serial port {self.port} ({e}). Falling back to STS3215 simulation mode.")
            return False

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info("Closed Feetech STS3215 serial bus connection.")

    def _calculate_checksum(self, packet: List[int]) -> int:
        # Checksum = ~(ID + Length + Instruction + Parameter1 + ... + ParameterN) & 0xFF
        total = sum(packet[2:])  # Skip headers [0xFF, 0xFF]
        return (~total) & 0xFF

    def _write_packet(self, servo_id: int, instruction: int, parameters: List[int]):
        if not self.is_hardware:
            return
            
        length = len(parameters) + 2
        packet = [0xFF, 0xFF, servo_id, length, instruction] + parameters
        checksum = self._calculate_checksum(packet)
        packet.append(checksum)
        
        self.serial.write(bytes(packet))
        # Flush Tx buffer to make sure it is sent
        self.serial.flush()

    def _read_response(self, expected_params_len: int) -> Optional[List[int]]:
        if not self.is_hardware:
            return None
            
        # Feetech response frame: [0xFF, 0xFF, ID, Length, Error, Param1, ..., ParamN, Checksum]
        header = self.serial.read(5)
        if len(header) < 5 or header[0] != 0xFF or header[1] != 0xFF:
            return None
            
        length = header[3]
        error = header[4]
        
        params_and_checksum_len = length - 1
        data = self.serial.read(params_and_checksum_len)
        if len(data) < params_and_checksum_len:
            return None
            
        packet = list(header) + list(data)
        checksum = packet[-1]
        
        calc_checksum = self._calculate_checksum(packet[:-1])
        if checksum != calc_checksum:
            logger.error("Feetech packet checksum mismatch!")
            return None
            
        return packet[5:-1]  # Return parameters only

    def set_torque(self, servo_id: int, enable: bool) -> bool:
        """Sets the torque status of a specific servo (0x28)."""
        val = 1 if enable else 0
        if not self.is_hardware:
            self._mock_torque[servo_id] = enable
            return True
            
        self._write_packet(servo_id, INST_WRITE, [REG_TORQUE_ENABLE, val])
        # STS write doesn't return response unless explicitly queried, or depending on Servo config (ACK policy)
        return True

    def set_torque_broadcast(self, enable: bool) -> bool:
        """Broadcasts a torque state to all servos (ID 0xFE)."""
        val = 1 if enable else 0
        if not self.is_hardware:
            for s_id in self._mock_torque:
                self._mock_torque[s_id] = enable
            return True
            
        self._write_packet(0xFE, INST_WRITE, [REG_TORQUE_ENABLE, val])
        return True

    def write_position(self, servo_id: int, position_ticks: int, speed_ticks: int = 0, accel_ticks: int = 0) -> bool:
        """Writes target position (0-4095) for a servo."""
        # Clamp position
        position_ticks = max(0, min(4095, position_ticks))
        
        if not self.is_hardware:
            self._target_positions[servo_id] = position_ticks
            return True
            
        pos_h, pos_l = (position_ticks >> 8) & 0xFF, position_ticks & 0xFF
        spd_h, spd_l = (speed_ticks >> 8) & 0xFF, speed_ticks & 0xFF
        acc = accel_ticks & 0xFF
        
        # STS write position target starting at target position register (0x2A)
        # Register sequence: Target position (2 bytes), Acceleration (1 byte, optional but we can group write)
        params = [REG_TARGET_POSITION, pos_l, pos_h]
        self._write_packet(servo_id, INST_WRITE, params)
        return True

    def write_positions_sync(self, servo_targets: List[Tuple[int, int]]):
        """
        Uses SYNC_WRITE (0x83) to write position targets to multiple servos in a single broadcast.
        servo_targets is a list of tuples: (servo_id, target_position_ticks)
        """
        if not servo_targets:
            return
            
        if not self.is_hardware:
            for servo_id, pos in servo_targets:
                self._target_positions[servo_id] = pos
            return
            
        # INST_SYNC_WRITE parameter format:
        # [Starting Register, Data Length, Servo1_ID, Servo1_Data1, Servo1_Data2, Servo2_ID, ...]
        start_reg = REG_TARGET_POSITION
        data_len = 2  # target position is 2 bytes (low byte, high byte)
        
        params = [start_reg, data_len]
        for servo_id, position in servo_targets:
            position = max(0, min(4095, int(position)))
            pos_h, pos_l = (position >> 8) & 0xFF, position & 0xFF
            params += [servo_id, pos_l, pos_h]
            
        self._write_packet(0xFE, INST_SYNC_WRITE, params)

    def read_servo_telemetry(self, servo_id: int) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        Reads position, current (load), and temperature for a single servo.
        Returns: (position_ticks, load_ticks, temp_c)
        """
        if not self.is_hardware:
            import math
            import random
            
            now = time.time()
            dt = max(0.001, now - self._last_update_time.get(servo_id, now))
            self._last_update_time[servo_id] = now
            if dt > 1.0:
                dt = 0.02
                
            target = self._target_positions.get(servo_id, 2048)
            present = self._present_positions.get(servo_id, 2048.0)
            
            # Max speed of 4096 ticks per second (approx 6.28 rad/s)
            max_step = 4096.0 * dt
            diff = target - present
            if abs(diff) <= max_step:
                present = float(target)
                speed_rad_s = 0.0
            else:
                step = max_step if diff > 0 else -max_step
                present += step
                speed_rad_s = (abs(step) / 4096.0) * 2 * math.pi / dt

            self._present_positions[servo_id] = present
            self._mock_positions[servo_id] = int(round(present))
            
            # Estimate torque based on tracking error (1 tick = 2*pi/4096 = 0.00153 rad)
            error_rad = abs(target - present) * 0.00153
            torque_load = min(3.23, 5.0 * error_rad)
            
            # If torque enabled
            is_enabled = self._mock_torque.get(servo_id, True)  # Default True for simulation robustness
            if is_enabled:
                i_idle = 0.05
                i_active = i_idle + 0.1 * speed_rad_s + 0.6 * torque_load
            else:
                i_active = 0.0
                
            self._mock_currents[servo_id] = i_active
            
            # Winding heating winding resistance is 1.5 Ohms
            p_loss = (i_active ** 2) * 1.5
            temp = self._mock_temperatures.get(servo_id, 35)
            dT = 0.05 * p_loss - 0.005 * (temp - 25.0)
            new_temp = temp + dT * dt
            new_temp = max(20.0, min(100.0, new_temp))
            self._mock_temperatures[servo_id] = int(round(new_temp))
            
            # Load returned as load ticks (current in centiamperes)
            load = int(i_active * 100) + random.randint(-2, 2)
            load = max(0, load)
            
            return int(round(present)), load, int(round(new_temp))

        # Read starting at REG_PRESENT_POSITION (0x38), length = 9 bytes:
        # Position (2 bytes), Speed (2 bytes), Load (2 bytes), Voltage (1 byte), Temp (1 byte), Current (2 bytes)
        self._write_packet(servo_id, INST_READ, [REG_PRESENT_POSITION, 9])
        response = self._read_response(9)
        if not response or len(response) < 9:
            return None, None, None
            
        # Parse Position
        pos = response[0] | (response[1] << 8)
        
        # Parse Load (signed 16-bit)
        load_raw = response[4] | (response[5] << 8)
        load = load_raw - 65536 if load_raw > 32767 else load_raw
        
        # Parse Temperature
        temp = response[7]
        
        return pos, load, temp

    def read_voltage(self, servo_id: int) -> Optional[float]:
        """Reads present voltage (0x3F) in Volts from a servo."""
        if not self.is_hardware:
            return 11.8  # Normal mock 3S voltage
            
        self._write_packet(servo_id, INST_READ, [REG_PRESENT_VOLTAGE, 1])
        response = self._read_response(1)
        if not response or len(response) < 1:
            return None
            
        # Value is 0.1V units
        return float(response[0]) / 10.0
