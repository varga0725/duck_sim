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

    def read_voltage(self) -> float:
        """
        Reads total battery voltage.
        In simulated mode, it decays the voltage slowly from 12.4V to simulate battery drain.
        """
        if not self.is_hardware:
            # Simulate battery discharge: decay 0.05V per minute, starting at 12.4V
            elapsed_min = (time.time() - self._start_time) / 60.0
            voltage = max(9.5, 12.4 - elapsed_min * 0.05)
            return voltage

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
            return max(0.0, battery_volts)
        except Exception as e:
            logger.error(f"Error reading battery ADC: {e}")
            return 11.5  # Safe nominal fallback on read error

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic battery state telemetry."""
        volts = self.read_voltage()
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
            "is_low": status == "low" or status == "critical"
        }
