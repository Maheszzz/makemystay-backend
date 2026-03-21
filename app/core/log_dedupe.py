import threading
import time

_RECENT_LOGS: dict[str, float] = {}
_RECENT_LOGS_LOCK = threading.Lock()


def should_log_once(key: str, window_seconds: int = 60) -> bool:
    """Return True only once per key/window to suppress noisy duplicate logs."""
    now = time.time()
    with _RECENT_LOGS_LOCK:
        last_logged = _RECENT_LOGS.get(key)
        if last_logged is not None and now - last_logged < window_seconds:
            return False
        _RECENT_LOGS[key] = now
        return True
