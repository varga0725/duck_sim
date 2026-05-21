import threading
from typing import Generic, TypeVar

T = TypeVar("T")

class DoubleBufferedState(Generic[T]):
    """
    Decoupled state representation using Double Buffering.
    Ensures readers (API, WebSockets, telemetry, perception loops) perform
    lock-free, zero-contention atomic reads on a consistent snapshot,
    while writers (background physics threads) safely update a separate write buffer.
    """

    def __init__(self, initial_state: T):
        self._lock = threading.Lock()
        
        # Deep copy helper or model_copy (Pydantic models support model_copy)
        if hasattr(initial_state, "model_copy"):
            self._write_state = initial_state.model_copy(deep=True)
            self._read_state = initial_state.model_copy(deep=True)
        else:
            import copy
            self._write_state = copy.deepcopy(initial_state)
            self._read_state = copy.deepcopy(initial_state)

    def get_read_state(self) -> T:
        """
        Retrieves the current read state.
        This is a lock-free, zero-contention atomic read.
        """
        # Assigning reference is atomic in CPython due to the GIL
        state = self._read_state
        if hasattr(state, "model_copy"):
            return state.model_copy(deep=True)
        import copy
        return copy.deepcopy(state)

    def update_write_state(self, state: T):
        """
        Overwrites the write buffer with a new state.
        """
        with self._lock:
            if hasattr(state, "model_copy"):
                self._write_state = state.model_copy(deep=True)
            else:
                import copy
                self._write_state = copy.deepcopy(state)

    def swap(self):
        """
        Atomically swaps the write buffer to become the active read buffer.
        """
        with self._lock:
            if hasattr(self._write_state, "model_copy"):
                self._read_state = self._write_state.model_copy(deep=True)
            else:
                import copy
                self._read_state = copy.deepcopy(self._write_state)
