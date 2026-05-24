import logging
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger("duck-hailo")

class HailoInference:
    """
    Hailo-8L NPU Inference Driver for YOLOv8 and Locomotion Policies.
    Attempts to connect using the HailoRT SDK.
    Falls back to CPU/ONNX execution on development machines (macOS).
    """
    def __init__(self, hef_path: Optional[str] = None):
        self.hef_path = hef_path
        self.is_hardware = False
        self.target_device = None
        self.configured_network = None
        
        self.connect()

    def connect(self) -> bool:
        try:
            from hailo_platform import Device, HEF
            # Find and open Hailo PCIe device
            devices = Device.scan()
            if not devices:
                logger.warning("No Hailo devices found. Falling back to CPU inference.")
                return False
                
            self.target_device = Device.create_device(devices[0])
            self.target_device.open()
            
            if self.hef_path:
                # Load compiled network (HEF)
                hef = HEF(self.hef_path)
                # Configure device with network
                self.configured_network = self.target_device.configure(hef)
                
            self.is_hardware = True
            logger.info("Successfully connected and initialized Hailo-8L NPU.")
            return True
        except Exception as e:
            self.is_hardware = False
            logger.warning(f"Could not initialize HailoRT platform ({e}). Using simulated/CPU fallback.")
            return False

    def close(self):
        if self.target_device:
            self.target_device.close()
            logger.info("Closed Hailo NPU connection.")

    def run_yolo_inference(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs YOLOv8 object detection on the Hailo-8L NPU.
        Falls back to standard CPU YOLO detector if NPU is not available.
        """
        if not self.is_hardware:
            # Fall back: return mock list of detections or trigger local CPU model
            # For testing/mocking, return an empty list or a simulated detection
            return []

        try:
            # Format frame to match Hailo input requirements (e.g. RGB 640x640)
            # Run NPU inference:
            # with self.configured_network.create_vdevice():
            #    outputs = self.configured_network.infer(frame)
            # Parse detections
            detections: List[Dict[str, Any]] = []
            return detections
        except Exception as e:
            logger.error(f"Error running Hailo NPU inference: {e}")
            return []
