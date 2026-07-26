"""Logging system setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_file: str, level: str = "INFO") -> logging.Logger:
    """Configure logging: write to file (DEBUG) and to console (given level).

    Args:
        log_file: Path to the log file.
        level: Logging level for console (DEBUG/INFO/WARNING/ERROR).

    Returns:
        Configured root logger.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger("pentool")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to avoid duplication
    logger.handlers.clear()

    # FileHandler — writes everything (DEBUG and above), appends to log
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # StreamHandler — writes to stderr at the given level
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
