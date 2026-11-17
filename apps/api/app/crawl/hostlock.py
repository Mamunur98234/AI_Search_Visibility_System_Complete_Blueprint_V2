"""Per-host politeness lock: at most one active crawl per hostname across ALL tenants and workers."""
from __future__ import annotations

import threading

import redis

from app.core.config import get_settings

LOCK_TTL_SECONDS = 120
_local: dict[str, str] = {}
_mutex = threading.Lock()


def _redis() -> redis.Redis | None:
    url = get_settings().redis_url
    return redis.Redis.from_url(url) if url else None


def acquire(host: str, owner: str) -> bool:
    r = _redis()
    if r is not None:
        key = f"crawl-host:{host}"
        if r.set(key, owner, nx=True, ex=LOCK_TTL_SECONDS):
            return True
        return bool(r.get(key) == owner.encode())
    with _mutex:
        if _local.get(host) not in (None, owner):
            return False
        _local[host] = owner
        return True


def refresh(host: str, owner: str) -> None:
    r = _redis()
    if r is not None and r.get(f"crawl-host:{host}") == owner.encode():
        r.expire(f"crawl-host:{host}", LOCK_TTL_SECONDS)


def release(host: str, owner: str) -> None:
    r = _redis()
    if r is not None:
        key = f"crawl-host:{host}"
        if r.get(key) == owner.encode():
            r.delete(key)
        return
    with _mutex:
        if _local.get(host) == owner:
            del _local[host]
