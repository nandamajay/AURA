"""LRU response cache for LLM completions."""

import hashlib
import json
from functools import lru_cache
from typing import Any


class ResponseCache:
    """Simple in-memory LRU cache for LLM responses.

    Keyed by hash of (model, messages, temperature, seed).
    Size limited by CACHE_SIZE config.
    """

    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self._cache: dict[str, dict[str, Any]] = {}
        self._access_order: list[str] = []
        self._hits = 0
        self._misses = 0

    def _make_key(self, request_data: dict[str, Any]) -> str:
        """Create deterministic cache key from request."""
        canonical = {
            "model": request_data.get("model", "gpt-4o-2024-08-06"),
            "messages": request_data.get("messages", []),
            "temperature": request_data.get("temperature", 0.1),
            "seed": request_data.get("seed", 42),
            "max_tokens": request_data.get("max_tokens", 4000),
        }
        json_bytes = json.dumps(canonical, sort_keys=True).encode()
        return hashlib.sha256(json_bytes).hexdigest()

    def get(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        """Get cached response if available."""
        key = self._make_key(request_data)
        if key in self._cache:
            self._hits += 1
            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, request_data: dict[str, Any], response: dict[str, Any]) -> None:
        """Cache a response."""
        key = self._make_key(request_data)

        # Evict oldest if at capacity
        while len(self._cache) >= self.maxsize and self._access_order:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)

        self._cache[key] = response
        self._access_order.append(key)

    def clear(self) -> int:
        """Clear all cached entries. Returns count cleared."""
        count = len(self._cache)
        self._cache.clear()
        self._access_order.clear()
        return count

    @property
    def stats(self) -> dict[str, int]:
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / (self._hits + self._misses), 4)
            if (self._hits + self._misses) > 0 else 0,
        }
