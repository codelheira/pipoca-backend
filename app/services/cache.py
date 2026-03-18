import time
from typing import Any, Optional
from ..core.config import settings

class MemoryCache:
    def __init__(self, expiration: int = settings.CACHE_EXPIRATION):
        self._cache = {}
        self.expiration = expiration

    def set(self, key: str, value: Any, custom_expiration: Optional[int] = None):
        exp = custom_expiration if custom_expiration else self.expiration
        self._cache[key] = (time.time(), value, exp)

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            timestamp, data, exp = self._cache[key]
            if time.time() - timestamp < exp:
                return data
            else:
                del self._cache[key]
        return None

    def clear(self):
        self._cache = {}

# Global cache instance
cache = MemoryCache()
