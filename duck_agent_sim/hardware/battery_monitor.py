import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("duck-battery-monitor")

# Battery Specifications for a 3S LiPo battery
CELLS = 3
NOMINAL_CELL_VOLTAGE = 3.7
CRITICAL_CELL_VOLTAGE = 3.3  # 9.9V total
WARNING_CELL_VOLTAGE = 3.5   # 10.5V total
FULL_CELL_VOLTAGE = 4.2      # 12.6V total

ADS1115_ADDRESS = 0x48

class BatteryMonitor:
    """
    Battery Telemetry Monitor for 3S LiPo.
    Reads voltage from an ADS1115 I2C ADC (channel 0) on Raspberry Pi 5.
    Falls back to a nominal 11.8V simulation on non-RPi hosts.
    """
    def __init__(self, bus_id: int = 1, address: int = ADS1115_ADDRESS, channel: int = 0):
        self.bus_id = bus_id
        self.address = address
        self.channel = channel
        self.bus = None
        self.is_hardware = False
        self._start_time = time.time()
        
        # High-Fidelity simulated battery states (3S LiPo)
        self._capacity_mah = 1500.0
        self._temperature_c = 25.0
        self._last_time = time.time()
        self._last_voltage = 12.6
        
        self.connect()

    def connect(self) -> bool:
        try:
            import smbus2
            self.bus = smbus2.SMBus(self.bus_id)
            # Perform a test read from config register (0x01)
            self.bus.read_word_data(self.address, 0x01)
            self.is_hardware = True
            logger.info(f"Successfully connected to ADS1115 Battery ADC on I2C bus {self.bus_id} at address {hex(self.address)}")
            return True
        except Exception as e:
            self.is_hardware = False
            logger.warning(f"Could not open ADS1115 I2C connection ({e}). Falling back to simulated battery telemetry.")
            return False

    def read_voltage(self, current_amps: float = 0.0) -> float:
        """
        Reads total battery voltage.
        In simulated mode, it updates capacity based on current load, models internal resistance
        voltage dip, and models battery temperature rise.
        """
        if not self.is_hardware:
            now = time.time()
            dt = max(0.001, now - self._last_time)
            self._last_time = now
            
            # Prevent huge time jumps if first run / debugging
            if dt > 1.0:
                dt = 0.02
                
            # Update battery capacity: current_amps * dt (seconds) converted to mAh
            discharged_mah = current_amps * dt / 3.6
            self._capacity_mah = max(0.0, self._capacity_mah - discharged_mah)
            
            # State of Charge (SoC) from 0.0 to 1.0
            soc = self._capacity_mah / 1500.0
            
            # Nominal voltage varies from 9.9V (empty) to 12.6V (full)
            v_nominal = 9.9 + 2.7 * soc
            
            # Internal resistance voltage dip: V = V_nominal - I * R_internal
            r_internal = 0.05  # Ohms
            v_actual = v_nominal - current_amps * r_internal
            
            # Battery temperature heating (I^2 * R) and cooling (convective to ambient 25C)
            p_loss = (current_amps ** 2) * r_internal
            dT = 0.02 * p_loss - 0.002 * (self._temperature_c - 25.0)
            self._temperature_c = max(25.0, self._temperature_c + dT * dt)
            
            self._last_voltage = max(5.0, v_actual)
            return self._last_voltage

        try:
            # Configure ADS1115 to read channel 0 with FSR = 6.144V
            # Config register value (0xC1C3): Single-shot, AIN0, FSR = 6.144V, 128SPS
            # Since battery voltage is up to 12.6V, a resistor divider is mandatory (e.g. 1/3 scaling to AIN0).
            # Assume 1/3 divider ratio (measured = battery / 3.0)
            divider_ratio = 3.0
            
            # Write to config register
            # AIN0, FSR = 6.144V, Single-Shot
            config = [0xC1, 0x83]
            self.bus.write_i2c_block_data(self.address, 0x01, config)
            time.sleep(0.01)  # wait for conversion
            
            # Read conversion register (0x00)
            data = self.bus.read_i2c_block_data(self.address, 0x00, 2)
            raw = (data[0] << 8) | data[1]
            # Convert to signed 16-bit
            if raw > 32767:
                raw -= 65536
                
            # LSB value for 6.144V FSR is 0.1875 mV
            measured_volts = raw * 0.0001875
            battery_volts = measured_volts * divider_ratio
            self._last_voltage = max(0.0, battery_volts)
            return self._last_voltage
        except Exception as e:
            logger.error(f"Error reading battery ADC: {e}")
            self._last_voltage = 11.5  # Safe nominal fallback on read error
            return self._last_voltage

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic battery state telemetry."""
        volts = self._last_voltage
        cell_volts = volts / CELLS
        
        # Calculate approximate charge percentage
        # 3.3V = 0%, 4.2V = 100%
        pct = (cell_volts - CRITICAL_CELL_VOLTAGE) / (FULL_CELL_VOLTAGE - CRITICAL_CELL_VOLTAGE)
        pct = max(0.0, min(100.0, pct * 100.0))
        
        status = "normal"
        if volts < CRITICAL_CELL_VOLTAGE * CELLS:
            status = "critical"
        elif volts < WARNING_CELL_VOLTAGE * CELLS:
            status = "low"
            
        return {
            "total_voltage": round(volts, 2),
            "cell_voltage": round(cell_volts, 2),
            "percentage": round(pct, 1),
            "status": status,
            "is_critical": status == "critical",
            "is_low": status == "low" or status == "critical",
            "temperature": round(self._temperature_c, 1)
        }
