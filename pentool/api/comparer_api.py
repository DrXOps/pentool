"""ComparerAPI — публичный интерфейс Comparer для TUI."""

from __future__ import annotations

from pentool.modules.comparer import (  # noqa: F401
    compare,
    compare_lines,
    CompareStats,
    DiffLine,
    DiffResult,
)

__all__ = [
    "compare",
    "compare_lines",
    "CompareStats",
    "DiffLine",
    "DiffResult",
]
