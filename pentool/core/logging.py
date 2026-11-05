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

Сама фабрика ``get_logger`` и класс логгера живут в ``pentool.utils.logging``
(нижний слой, чтобы логгировать могли и utils). Здесь они реэкспортируются,
поэтому старые импорты ``from pentool.core.logging import get_logger`` валидны.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from pentool.utils.logging import _NamedLogger, get_logger

__all__ = ["get_logger", "setup_logging", "_NamedLogger", "_load_logging_rules"]


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
