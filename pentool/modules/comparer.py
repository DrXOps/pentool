"""Comparer — side-by-side diff of two texts with difference highlighting."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

__all__ = ["compare", "compare_lines", "CompareStats", "DiffLine", "DiffResult"]


@dataclass
class DiffLine:
    """One line of the diff result."""

    tag: str           # "equal" | "replace" | "insert" | "delete"
    left: str          # left side text (empty if insert)
    right: str         # right side text (empty if delete)
    line_left: int     # left line number (0 if absent)
    line_right: int    # right line number (0 if absent)


@dataclass
class CompareStats:
    """Comparison statistics."""

    total_left: int
    total_right: int
    equal_lines: int
    added_lines: int
    removed_lines: int
    changed_lines: int
    similarity: float  # 0.0–1.0

    @property
    def similarity_pct(self) -> int:
        return int(self.similarity * 100)


@dataclass
class DiffResult:
    """Comparison result: diff lines + statistics."""

    lines: list[DiffLine]
    stats: CompareStats

    def rich_text(self) -> str:
        """Build a Rich-markup string for RichLog."""
        parts: list[str] = []
        for dl in self.lines:
            if dl.tag == "equal":
                parts.append(f"[dim]  {dl.left}[/dim]")
            elif dl.tag == "insert":
                parts.append(f"[green]+ {dl.right}[/green]")
            elif dl.tag == "delete":
                parts.append(f"[red]- {dl.left}[/red]")
            elif dl.tag == "replace":
                parts.append(f"[red]- {dl.left}[/red]")
                parts.append(f"[green]+ {dl.right}[/green]")
        return "\n".join(parts)


def compare(left: str, right: str) -> DiffResult:
    """Compare two texts line by line.

    Args:
        left: Left text.
        right: Right text.

    Returns:
        DiffResult with per-line differences and statistics.
    """
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    return compare_lines(left_lines, right_lines)


def compare_lines(left_lines: list[str], right_lines: list[str]) -> DiffResult:
    """Compare two lists of lines.

    Args:
        left_lines: Left side lines.
        right_lines: Right side lines.

    Returns:
        DiffResult with per-line differences and statistics.
    """
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
    opcodes = matcher.get_opcodes()

    diff_lines: list[DiffLine] = []
    equal = added = removed = changed = 0

    ln_left = 1
    ln_right = 1

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                diff_lines.append(DiffLine(
                    tag="equal",
                    left=left_lines[i1 + k],
                    right=right_lines[j1 + k],
                    line_left=ln_left + k,
                    line_right=ln_right + k,
                ))
            equal += i2 - i1
            ln_left += i2 - i1
            ln_right += j2 - j1

        elif tag == "replace":
            # Show removed lines on left, added lines on right
            left_chunk = left_lines[i1:i2]
            right_chunk = right_lines[j1:j2]
            max_len = max(len(left_chunk), len(right_chunk))
            for k in range(max_len):
                l_text = left_chunk[k] if k < len(left_chunk) else ""
                r_text = right_chunk[k] if k < len(right_chunk) else ""
                if l_text and r_text:
                    diff_lines.append(DiffLine(
                        tag="replace",
                        left=l_text, right=r_text,
                        line_left=ln_left + k if k < len(left_chunk) else 0,
                        line_right=ln_right + k if k < len(right_chunk) else 0,
                    ))
                elif l_text:
                    diff_lines.append(DiffLine(
                        tag="delete", left=l_text, right="",
                        line_left=ln_left + k, line_right=0,
                    ))
                else:
                    diff_lines.append(DiffLine(
                        tag="insert", left="", right=r_text,
                        line_left=0, line_right=ln_right + k,
                    ))
            changed += max(len(left_chunk), len(right_chunk))
            ln_left += i2 - i1
            ln_right += j2 - j1

        elif tag == "delete":
            for k in range(i2 - i1):
                diff_lines.append(DiffLine(
                    tag="delete",
                    left=left_lines[i1 + k], right="",
                    line_left=ln_left + k, line_right=0,
                ))
            removed += i2 - i1
            ln_left += i2 - i1

        elif tag == "insert":
            for k in range(j2 - j1):
                diff_lines.append(DiffLine(
                    tag="insert",
                    left="", right=right_lines[j1 + k],
                    line_left=0, line_right=ln_right + k,
                ))
            added += j2 - j1
            ln_right += j2 - j1

    similarity = matcher.ratio()
    stats = CompareStats(
        total_left=len(left_lines),
        total_right=len(right_lines),
        equal_lines=equal,
        added_lines=added,
        removed_lines=removed,
        changed_lines=changed,
        similarity=similarity,
    )
    return DiffResult(lines=diff_lines, stats=stats)


def compare_bytes(left: bytes, right: bytes) -> DiffResult:
    """Compare two byte streams (decoded as UTF-8 with replacement)."""
    return compare(
        left.decode("utf-8", errors="replace"),
        right.decode("utf-8", errors="replace"),
    )
