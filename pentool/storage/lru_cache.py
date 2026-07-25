"""LRUCache — кэш полных HTTP-записей в памяти."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


class LRUCache:
    """In-memory LRU-кэш. Вытеснение по принципу Least Recently Used.

    Используется в HttpStorage для кеширования get_full_entry():
    повторный запрос той же строки не идёт в SQLite.
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
            self._cache.popitem(last=False)  # удаляет самый старый

    def invalidate(self, key: int) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: int) -> bool:
        return key in self._cache
