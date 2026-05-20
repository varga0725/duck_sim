import threading
import numpy as np
from typing import Optional

class FrameBuffer:
    """
    Thread-safe, lock-protected, non-blocking shared frame buffer.
    Exposes only the latest frame to prevent queue build-up and OOM errors.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._latest_frame: Optional[np.ndarray] = None
        
    def push(self, frame: np.ndarray):
        """Pushes a new frame into the buffer (thread-safe)."""
        with self._lock:
            self._latest_frame = frame
            
    def get(self) -> Optional[np.ndarray]:
        """
        Retrieves the latest frame from the buffer.
        Uses a non-blocking read mechanism to ensure callers are never stalled.
        """
        acquired = self._lock.acquire(blocking=False)
        if acquired:
            try:
                return self._latest_frame
            finally:
                self._lock.release()
        else:
            return self._latest_frame
