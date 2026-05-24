import threading
import time
from typing import List, Dict, Any

class PerceptionState:
    """
    Thread-safe repository storing the latest object detections and performance metrics.
    Provides robust non-blocking read access to other threads (e.g. FastAPI / Agents).
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.detections: List[Dict[str, Any]] = []
        self.last_update_time: float = 0.0
        self.width: int = 640
        self.height: int = 480
        self.fps: float = 0.0
        self._frame_count = 0
        self._fps_start_time = time.time()
        
    def update(self, detections: List[Dict[str, Any]], width: int = 640, height: int = 480):
        """Updates the shared state thread-safely and computes running perception FPS."""
        import os
        if os.getenv("DUCK_MULTIPROCESS", "false").lower() == "true":
            try:
                from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
                bus = SharedTelemetryBus(create=False)
                vision_ref = bus.get_vision_ref()
                now = time.time()
                vision_ref.timestamp = now
                
                # FPS calculation
                self._frame_count += 1
                elapsed = now - self._fps_start_time
                if elapsed >= 2.0:
                    self.fps = self._frame_count / elapsed
                    self._frame_count = 0
                    self._fps_start_time = now
                vision_ref.fps = self.fps
                
                vision_ref.num_detections = min(len(detections), 10)
                for i, det in enumerate(detections[:10]):
                    det_struct = vision_ref.detections[i]
                    det_struct.label = det["label"].encode("utf-8")[:32]
                    det_struct.confidence = float(det["confidence"])
                    for j in range(4):
                        det_struct.bbox[j] = float(det["bbox"][j])
                    for j in range(2):
                        det_struct.center[j] = float(det["center"][j])
                    det_struct.tracking_id = int(det.get("tracking_id", -1))
                bus.close()
            except Exception:
                pass

        with self._lock:
            now = time.time()
            self.detections = detections
            self.last_update_time = now
            self.width = width
            self.height = height
            
            # FPS tracking over a rolling window
            self._frame_count += 1
            elapsed = now - self._fps_start_time
            if elapsed >= 2.0:
                self.fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start_time = now
                
    def get_summary(self) -> Dict[str, Any]:
        """Returns a snapshot summary conforming to the /vision/state schema."""
        import os
        if os.getenv("DUCK_MULTIPROCESS", "false").lower() == "true":
            try:
                from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
                bus = SharedTelemetryBus(create=False)
                vision_ref = bus.get_vision_ref()
                num_dets = vision_ref.num_detections
                detections = []
                for i in range(num_dets):
                    det_struct = vision_ref.detections[i]
                    label = det_struct.label.decode("utf-8").strip('\x00')
                    detections.append({
                        "label": label,
                        "tracking_id": det_struct.tracking_id,
                    })
                last_update_time = vision_ref.timestamp
                fps = vision_ref.fps
                bus.close()
                
                tracked_ids = [d["tracking_id"] for d in detections if d.get("tracking_id", -1) != -1]
                labels = list(set([d["label"] for d in detections]))
                last_update_sec = time.time() - last_update_time if last_update_time > 0 else -1.0
                
                return {
                    "num_objects": len(detections),
                    "tracked_ids": tracked_ids,
                    "labels": labels,
                    "vision_fps": round(fps, 1) if fps > 0 else 10.0,
                    "last_update_sec": round(last_update_sec, 3) if last_update_sec >= 0 else 0.0
                }
            except Exception:
                pass

        with self._lock:
            tracked_ids = [d["tracking_id"] for d in self.detections if d.get("tracking_id", -1) != -1]
            labels = list(set([d["label"] for d in self.detections]))
            last_update_sec = time.time() - self.last_update_time if self.last_update_time > 0 else -1.0
            
            return {
                "num_objects": len(self.detections),
                "tracked_ids": tracked_ids,
                "labels": labels,
                "vision_fps": round(self.fps, 1) if self.fps > 0 else 10.0, # default/running estimate
                "last_update_sec": round(last_update_sec, 3) if last_update_sec >= 0 else 0.0
            }
            
    def get_detections(self) -> List[Dict[str, Any]]:
        """Returns a deep-copied list of current active detections (thread-safe)."""
        import os
        if os.getenv("DUCK_MULTIPROCESS", "false").lower() == "true":
            try:
                from duck_agent_sim.runtime.shared_telemetry_bus import SharedTelemetryBus
                bus = SharedTelemetryBus(create=False)
                vision_ref = bus.get_vision_ref()
                num_dets = vision_ref.num_detections
                detections = []
                for i in range(num_dets):
                    det_struct = vision_ref.detections[i]
                    label = det_struct.label.decode("utf-8").strip('\x00')
                    bbox = [det_struct.bbox[j] for j in range(4)]
                    center = [det_struct.center[j] for j in range(2)]
                    detections.append({
                        "label": label,
                        "confidence": det_struct.confidence,
                        "bbox": bbox,
                        "center": center,
                        "tracking_id": det_struct.tracking_id,
                    })
                bus.close()
                return detections
            except Exception:
                pass

        with self._lock:
            return [d.copy() for d in self.detections]
