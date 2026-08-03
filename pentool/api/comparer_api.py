"""ComparerAPI — public Comparer interface for TUI."""

from __future__ import annotations

from pentool.modules.comparer import (  # noqa: F401
    CompareStats,
    DiffLine,
    DiffResult,
    compare,
    compare_lines,
)

__all__ = [
    "compare",
    "compare_lines",
    "CompareStats",
    "DiffLine",
    "DiffResult",
]
