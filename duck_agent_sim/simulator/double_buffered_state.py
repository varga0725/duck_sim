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
            # Fast shallow-nested copy optimized for RobotState
            new_copy = state.model_copy(deep=False)
            if hasattr(state, "orientation") and state.orientation is not None:
                new_copy.orientation = state.orientation.model_copy(deep=False)
            if hasattr(state, "feet_contact") and state.feet_contact is not None:
                new_copy.feet_contact = state.feet_contact.model_copy(deep=False)
            if hasattr(state, "stability") and state.stability is not None:
                new_copy.stability = state.stability.model_copy(deep=False)
            return new_copy
        import copy
        return copy.deepcopy(state)

    def update_write_state(self, state: T):
        """
        Overwrites the write buffer with a new state.
        """
        with self._lock:
            if hasattr(state, "model_copy"):
                new_copy = state.model_copy(deep=False)
                if hasattr(state, "orientation") and state.orientation is not None:
                    new_copy.orientation = state.orientation.model_copy(deep=False)
                if hasattr(state, "feet_contact") and state.feet_contact is not None:
                    new_copy.feet_contact = state.feet_contact.model_copy(deep=False)
                if hasattr(state, "stability") and state.stability is not None:
                    new_copy.stability = state.stability.model_copy(deep=False)
                self._write_state = new_copy
            else:
                import copy
                self._write_state = copy.deepcopy(state)

    def swap(self):
        """
        Atomically swaps the write buffer to become the active read buffer.
        """
        with self._lock:
            if hasattr(self._write_state, "model_copy"):
                # No need to deepcopy again during swap if it was copied on write
                self._read_state = self._write_state
            else:
                import copy
                self._read_state = copy.deepcopy(self._write_state)
