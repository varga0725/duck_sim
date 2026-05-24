import logging
import time
from typing import Tuple

logger = logging.getLogger("duck-foot-switch")

class FootSwitchDriver:
    """
    GPIO Foot Switch Driver for Raspberry Pi 5.
    Uses the gpiod library to interface with GPIO pins.
    Falls back to simulated contact patterns on development hosts.
    """
    def __init__(self, left_pin: int = 17, right_pin: int = 27):
        self.left_pin = left_pin
        self.right_pin = right_pin
        self.is_hardware = False
        self.left_line = None
        self.right_line = None
        self.chip = None
        
        self.connect()

    def connect(self) -> bool:
        try:
            import gpiod
            # GPIO chip 0 is default on Pi 5 for primary headers
            self.chip = gpiod.Chip('gpiochip4')  # On Pi 5, RP1 controls headers on gpiochip4
            
            # Request inputs with pull-up resistors enabled
            self.left_line = self.chip.get_line(self.left_pin)
            self.right_line = self.chip.get_line(self.right_pin)
            
            # Request input line config
            self.left_line.request(consumer="duck-left-foot", type=gpiod.LINE_REQ_DIR_IN, flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)
            self.right_line.request(consumer="duck-right-foot", type=gpiod.LINE_REQ_DIR_IN, flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)
            
            self.is_hardware = True
            logger.info(f"Successfully configured foot switch GPIO inputs: Left PIN {self.left_pin}, Right PIN {self.right_pin} on gpiochip4.")
            return True
        except Exception as e:
            self.is_hardware = False
            logger.warning(f"Could not initialize GPIO chip/lines ({e}). Falling back to Foot Switch simulation mode.")
            return False

    def close(self):
        if self.left_line:
            self.left_line.release()
        if self.right_line:
            self.right_line.release()
        if self.chip:
            self.chip.close()

    def read_contacts(self) -> Tuple[bool, bool]:
        """
        Reads foot contact sensors.
        Returns: (left_contact_active, right_contact_active)
        """
        if not self.is_hardware:
            # Simulated contact pattern (alternating based on simple clock phase)
            t = time.time()
            phase = t * 8.0
            left_active = math_sin_wave(phase) >= -0.2
            right_active = math_sin_wave(phase + 3.14159) >= -0.2
            return left_active, right_active

        try:
            # Active low contacts (pulled high, switch connects pin to GND)
            left_val = self.left_line.get_value()
            right_val = self.right_line.get_value()
            
            # Invert values if active low (0 = pressed/contact, 1 = open/no contact)
            left_contact = (left_val == 0)
            right_contact = (right_val == 0)
            return left_contact, right_contact
        except Exception as e:
            logger.error(f"Error reading foot GPIO values: {e}")
            return True, True  # Default to conservative contact state (both on ground)

def math_sin_wave(val: float) -> float:
    import math
    return math.sin(val)
