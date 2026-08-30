"""LRUCache — in-memory cache."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """In-memory LRU cache. Eviction follows the Least Recently Used principle.

    Generic over key/value types so it serves both keyed storage (e.g.
    HttpStorage's row-id → full-entry cache) and string-keyed caches such as
    the SSL-context cache in utils/cert.py (domain → SSLContext), replacing
    the copy that used to live there (Этап 7.4 consolidation).
    """

    def __init__(self, max_size: int = 500) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: K, value: V) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
            return
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # removes the oldest entry

    def invalidate(self, key: K) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: K) -> bool:
        return key in self._cache
