"""Настройка системы логирования."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_file: str, level: str = "INFO") -> logging.Logger:
    """Настроить логирование: запись в файл (DEBUG) и в консоль (указанный уровень).

    Args:
        log_file: Путь к лог-файлу.
        level: Уровень логирования для консоли (DEBUG/INFO/WARNING/ERROR).

    Returns:
        Настроенный корневой логгер.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger("pentool")
    logger.setLevel(logging.DEBUG)

    # Очистить существующие хендлеры, чтобы избежать дублирования
    logger.handlers.clear()

    # FileHandler — пишет всё (DEBUG и выше), дописывает в лог (не очищает)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # StreamHandler — пишет в stderr на указанном уровне
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(message)s")
    )

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "pentool") -> logging.Logger:
    return logging.getLogger(name)
