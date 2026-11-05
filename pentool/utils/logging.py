"""Фабрика логгеров — общая для всех слоёв.

Живёт в ``utils`` намеренно: логгер нужен и ``utils``, и ``core``, и
``modules``, а правило слоёв запрещает пакетам ниже ``core`` импортировать
``core``. ``pentool.core.logging`` реэкспортирует эти имена, поэтому
существующие ``from pentool.core.logging import get_logger`` продолжают
работать без изменений.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import ClassVar


class _NamedLogger(logging.Logger):
    """Логгер с per-module фильтрацией уровней через конфиг.

    Фильтры задаются один раз через ``_NamedLogger.configure(rules)`` и
    работают на все логгеры в системе. ``error`` всегда проходит.
    """

    _filters: ClassVar[dict[str, set[str] | None]] = {}
    _configured: ClassVar[bool] = False

    @classmethod
    def configure(cls, rules: dict[str, str]) -> None:
        """Set per-module level filters from a rules dict.

        Args:
            rules: { "module.name": "-debug,+info" | "off" }
        """
        cls._filters.clear()
        for mod, rule in rules.items():
            rule = rule.strip()
            if rule == "off":
                cls._filters[mod] = set()
                continue
            enabled: set[str] = {"error", "critical"}
            parts = rule.replace(",", " ").split()
            for p in parts:
                p = p.strip()
                if p.startswith("+"):
                    enabled.add(p[1:])
                elif p.startswith("-"):
                    enabled.discard(p[1:])
            cls._filters[mod] = enabled
        cls._configured = True

    @classmethod
    def reset(cls) -> None:
        cls._filters.clear()
        cls._configured = False

    def _check(self, level: str) -> bool:
        if not self._configured:
            return True
        name: str = self.name
        parts = name.split(".")
        if name in self._filters:
            flt = self._filters[name]
            return flt is None or level in flt
        for i in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:i])
            if parent in self._filters:
                flt = self._filters[parent]
                return flt is None or level in flt
        return True

    def debug(self, msg: str, *args, **kwargs) -> None:
        if self._check("debug"):
            super().debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        if self._check("info"):
            super().info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        if self._check("warning"):
            super().warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        super().error(msg, *args, **kwargs)


logging.setLoggerClass(_NamedLogger)


def get_logger(name: str = "pentool") -> logging.Logger:
    """Return a logger that honours the per-module level filters."""
    return logging.getLogger(name)
