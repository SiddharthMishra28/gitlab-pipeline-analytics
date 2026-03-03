import threading


class InMemoryLocker:
    def __init__(self):
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, key: str) -> bool:
        with self._lock:
            if key in self._active:
                return False
            self._active.add(key)
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._active.discard(key)
