import os
import time
import math
import numpy as np
import cv2

class CameraDevice:
    """
    Abstacted Camera Device for the Duck Agent Simulation.
    Extracts RGB frames from MuJoCo simulator when active, or generates mock frames.
    """
    def __init__(self, simulator):
        self.simulator = simulator
        self._renderer = None
        self._webcam_cap = None

    def capture_frame(self) -> np.ndarray:
        sim_mode = os.getenv("DUCK_SIM_MODE", "mock").lower()
        if sim_mode == "real":
            return self._capture_real_frame()
        elif sim_mode == "webcam":
            return self._capture_webcam_frame()
        else:
            return self._capture_mock_frame()

    def _capture_webcam_frame(self) -> np.ndarray:
        # Lazily initialize cv2 VideoCapture to avoid camera lock when not in use
        if self._webcam_cap is None:
            self._webcam_cap = cv2.VideoCapture(0)
            self._webcam_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._webcam_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
        ret, frame = self._webcam_cap.read()
        if not ret or frame is None:
            # Fall back to blank gray frame if camera frame could not be read
            return np.zeros((480, 640, 3), dtype=np.uint8) + 128
            
        # OpenCV captures in BGR, we must return RGB for YOLO and UI encoding
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Guarantee exact 640x480 shape by resizing if required (some webcams return native size)
        if rgb_frame.shape[0] != 480 or rgb_frame.shape[1] != 640:
            rgb_frame = cv2.resize(rgb_frame, (640, 480), interpolation=cv2.INTER_LINEAR)
            
        return rgb_frame

    def close(self):
        """Releases webcam resources if they were initialized."""
        if self._webcam_cap is not None:
            try:
                self._webcam_cap.release()
                self._webcam_cap = None
            except Exception:
                pass

    def _capture_real_frame(self) -> np.ndarray:
        import mujoco
        if not hasattr(self.simulator, "model") or not hasattr(self.simulator, "data"):
            # Return empty frame if simulator is not fully initialized
            return np.zeros((480, 640, 3), dtype=np.uint8)

        # Thread-safe frame extraction using the simulator lock
        with self.simulator._lock:
            if self._renderer is None:
                self._renderer = mujoco.Renderer(self.simulator.model, height=480, width=640)
            
            try:
                self._renderer.update_scene(self.simulator.data, camera="fpv")
            except ValueError:
                # Some Open Duck scenes do not expose the fpv camera name
                # after model compilation. Fall back to MuJoCo's free/default camera
                # so /vision/frame remains usable in real mode.
                self._renderer.update_scene(self.simulator.data)
            frame = self._renderer.render()
            return frame.copy()

    def _capture_mock_frame(self) -> np.ndarray:
        if hasattr(self.simulator, "_state"):
            sim_time = self.simulator._state.sim_time
        else:
            sim_time = time.time()
            
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Wall background (light gray)
        frame[:, :] = [240, 240, 240]
        # Floor (greenish gray)
        cv2.rectangle(frame, (0, 300), (640, 480), (180, 200, 180), -1)
        
        # Calculate moving coordinates to simulate object tracking
        offset_x = int(30 * math.sin(sim_time * 0.5))
        person_x = int(450 + 40 * math.cos(sim_time * 0.3))
        
        # Chair
        cv2.rectangle(frame, (150 + offset_x, 280), (220 + offset_x, 350), (165, 42, 42), -1)
        cv2.line(frame, (160 + offset_x, 350), (160 + offset_x, 400), (165, 42, 42), 5)
        cv2.line(frame, (210 + offset_x, 350), (210 + offset_x, 400), (165, 42, 42), 5)
        
        # Person
        cv2.circle(frame, (person_x, 200), 30, (255, 105, 180), -1)
        cv2.rectangle(frame, (person_x - 40, 230), (person_x + 40, 380), (30, 144, 255), -1)
        
        return frame

# Global lazy-initialized active camera reference
_active_camera = None

def get_active_camera() -> CameraDevice:
    global _active_camera
    if _active_camera is None:
        from duck_agent_sim.simulator.instance import active_simulator
        _active_camera = CameraDevice(active_simulator)
    return _active_camera
