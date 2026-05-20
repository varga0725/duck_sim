import threading
import time
import logging
from typing import Optional
from duck_agent_sim.vision.camera import CameraDevice
from duck_agent_sim.vision.frame_buffer import FrameBuffer
from duck_agent_sim.vision.yolo_detector import YOLODetector
from duck_agent_sim.vision.tracker import CentroidTracker
from duck_agent_sim.vision.perception_state import PerceptionState

logger = logging.getLogger("duck-agent-sim-vision")

class VisionLoop:
    """
    Background Vision Loop.
    Executes frame capture, YOLOv8 object detection, centroid tracking, and state updates
    independently at a target frequency (5-15 FPS) without locking or slowing the physics stepping thread.
    """
    def __init__(self, camera_device: CameraDevice, frame_buffer: FrameBuffer, detector: YOLODetector, tracker: CentroidTracker, state: PerceptionState, target_fps: float = 10.0):
        self.camera_device = camera_device
        self.frame_buffer = frame_buffer
        self.detector = detector
        self.tracker = tracker
        self.state = state
        self.target_fps = target_fps
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
    def start(self):
        """Starts the background perception thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="VisionPerceptionLoop")
        self._thread.start()
        logger.info("Vision perception background thread started.")
        
    def stop(self):
        """Halts the background perception thread cleanly."""
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Vision perception background thread stopped.")
        
    def _run_loop(self):
        period = 1.0 / self.target_fps
        while self.running:
            start_time = time.time()
            try:
                # 1. Capture and buffer latest frame
                frame = self.camera_device.capture_frame()
                if frame is not None:
                    self.frame_buffer.push(frame)
                    
                    # 2. Retrieve latest buffered frame for detection
                    latest_frame = self.frame_buffer.get()
                    if latest_frame is not None:
                        # 3. YOLO detection
                        detections = self.detector.detect(latest_frame)
                        
                        # 4. Nearest-center tracking
                        detections = self.tracker.update(detections)
                        
                        # 5. Update thread-safe shared state
                        h, w, _ = latest_frame.shape
                        self.state.update(detections, width=w, height=h)
            except Exception as e:
                logger.error(f"Error in background vision loop: {e}", exc_info=True)
                
            elapsed = time.time() - start_time
            sleep_time = max(0.001, period - elapsed)
            time.sleep(sleep_time)
