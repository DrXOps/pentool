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
import logging.handlers
import os
import sys
from pathlib import Path

from pentool.utils.logging import _NamedLogger, get_logger

__all__ = ["get_logger", "setup_logging", "_NamedLogger", "_load_logging_rules"]

#: Journal rotation (T-021). Without it the file grew linearly: a week of work
#: with traffic brought it to 4.7 GB, after which `grep` over it stopped being
#: usable and every write became I/O on the capture path. 50 MB × 10 archives
#: caps the directory at roughly 550 MB.
DEFAULT_LOG_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 10


def _rotation_limits() -> tuple[int, int]:
    """File size ceiling and archive count; overridable for tests and CI.

    ``PENTOOL_LOG_MAX_BYTES=0`` disables rotation — tests care that a record is
    written, not how the files are laid out on disk.
    """
    max_bytes = int(os.environ.get("PENTOOL_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES))
    backup_count = int(os.environ.get("PENTOOL_LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT))
    return max_bytes, max(1, backup_count)


def setup_logging(log_file: str, level: str = "INFO") -> logging.Logger:
    """Настроить логирование.

    `PENTOOL_LOG_FILE` переопределяет путь: тесты пишут в /tmp, а не в
    настоящий журнал на 9p — иначе DEBUG-запись на каждый зонд делает прогон
    в разы медленнее (замер: 8 мин против 3).
    """
    log_file = os.environ.get("PENTOOL_LOG_FILE", log_file)
    # `PENTOOL_LOG_LEVEL` — для тестов и CI: прогон с DEBUG на каждый зонд
    # пишет тысячи записей и замедляет набор втрое.
    level = os.environ.get("PENTOOL_LOG_LEVEL", level)
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
    max_bytes, backup_count = _rotation_limits()
    if max_bytes > 0:
        # Rotation instead of one ever-growing file (T-021): 50 MB per file,
        # 10 archives, the oldest is dropped. The journal stays greppable and
        # cannot fill the disk on its own.
        file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            mode="a",
        )
    else:
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
    except Exception:
        # Секция [logging.rules] не прочиталась — правила остались прежними.
        # Это не потеря данных, но и не норма: warning с трейсбеком, иначе
        # сломанный конфиг логирования выглядит как его отсутствие.
        root_logger.warning("logging.rules not applied", exc_info=True)
