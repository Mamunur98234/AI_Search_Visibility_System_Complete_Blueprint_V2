"""Fixed-window rate limiting. Redis in all shared environments; in-process memory fallback only
for local development/tests (refused in production by config validation)."""
import threading
import time
from typing import Protocol

from app.core.config import get_settings


class _Backend(Protocol):
    def hit(self, key: str, window: int) -> int: ...
    def reset(self, key: str) -> None: ...


class _MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window: int) -> int:
        now = time.monotonic()
        with self._lock:
            count, exp = self._data.get(key, (0, now + window))
            if now >= exp:
                count, exp = 0, now + window
            count += 1
            self._data[key] = (count, exp)
            return count

    def reset(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url)

    def hit(self, key: str, window: int) -> int:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        count, _ = pipe.execute()
        return int(count)

    def reset(self, key: str) -> None:
        self._r.delete(key)


_backend: _Backend | None = None


def backend() -> _Backend:
    global _backend
    if _backend is None:
        url = get_settings().redis_url
        _backend = _RedisBackend(url) if url else _MemoryBackend()
    return _backend


def set_backend(b: _Backend | None) -> None:
    global _backend
    _backend = b


def hit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """Returns (allowed, count)."""
    count = backend().hit(f"rl:{key}", window)
    return count <= limit, count


def reset(key: str) -> None:
    backend().reset(f"rl:{key}")
