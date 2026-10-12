"""
QUANTA — High-Performance In-Memory Cache Utility
=================================================
Implements a fast, thread-safe In-Memory TTL Cache for user analytics and records.
Eliminates redundant network roundtrips to Firestore, reducing latency from ~1000ms to < 1ms.
"""

import time
import threading

class SimpleTTLCache:
    def __init__(self, default_ttl_seconds: float = 12.0):
        self.default_ttl = default_ttl_seconds
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            val, expire_time = entry
            if time.time() > expire_time:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, value, ttl: float = None):
        if ttl is None:
            ttl = self.default_ttl
        expire_time = time.time() + ttl
        with self._lock:
            self._cache[key] = (value, expire_time)

    def invalidate_prefix(self, prefix: str):
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]

    def clear(self):
        with self._lock:
            self._cache.clear()

# Global cache instance for QUANTA analytics
user_data_cache = SimpleTTLCache(default_ttl_seconds=12.0)
