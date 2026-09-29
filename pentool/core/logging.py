"""Logging system setup with module-level filter control.

Usage::

    from pentool.core.logging import get_logger
    logger = get_logger(__name__)
    logger.debug("...")   # respects per-module filters
    logger.info("...")
    logger.warning("...")
    logger.error("...")   # error всегда проходит

В Settings → [logging.rules] можно точечно отключить/включить уровни::

    [logging.rules]
    pentool.proxy.client = -debug
    pentool.modules.scanner.engine = -debug,-info
    pentool.tui = +error

Правила:
    +level — включить уровень (кроме error — всегда включён)
    -level — выключить уровень
    off    — выключить всё кроме error
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


def setup_logging(log_file: str, level: str = "INFO") -> logging.Logger:
    """Configure logging: write to file (DEBUG) and to console (given level)."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger("pentool")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _load_logging_rules(logger)

    return logger


def _load_logging_rules(root_logger: logging.Logger) -> None:
    """Read [logging.rules] from config and apply to _NamedLogger."""
    try:
        from pentool.core.config import get_config
        cfg = get_config()
        rules_section = getattr(cfg, "logging_rules", None) or {}
        _NamedLogger.configure(rules_section)
    except Exception as exc:
        root_logger.debug("No logging.rules in config: %s", exc)


def get_logger(name: str = "pentool") -> logging.Logger:
    return logging.getLogger(name)