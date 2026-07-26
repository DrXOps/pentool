"""LRUCache — in-memory cache for full HTTP records."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


class LRUCache:
    """In-memory LRU cache. Eviction follows the Least Recently Used principle.

    Used in HttpStorage to cache get_full_entry() calls:
    repeated requests for the same row do not hit SQLite.
    """

    def __init__(self, max_size: int = 500) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[int, Any] = OrderedDict()

    def get(self, key: int) -> Any | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: int, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
            return
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # removes the oldest entry

    def invalidate(self, key: int) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: int) -> bool:
        return key in self._cache
