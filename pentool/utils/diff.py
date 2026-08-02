"""Text comparison (diff) with Rich/Textual formatting."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Literal


@dataclass
class DiffLine:
    """A single line in a diff result."""

    type: Literal["+", "-", " ", "@"]
    content: str


def diff_texts(text1: str, text2: str, context: int = 3) -> list[DiffLine]:
    """Compare two texts and return a list of diff lines (unified format).

    Args:
        text1: Original text (left / "before").
        text2: Modified text (right / "after").
        context: Number of context lines around changes.

    Returns:
        List of DiffLine objects.
    """
    lines1 = text1.splitlines(keepends=True)
    lines2 = text2.splitlines(keepends=True)

    result: list[DiffLine] = []
    for line in difflib.unified_diff(lines1, lines2, n=context):
        line_stripped = line.rstrip("\n")
        if line_stripped.startswith("+++") or line_stripped.startswith("---"):
            result.append(DiffLine(type="@", content=line_stripped))
        elif line_stripped.startswith("@@"):
            result.append(DiffLine(type="@", content=line_stripped))
        elif line_stripped.startswith("+"):
            result.append(DiffLine(type="+", content=line_stripped[1:]))
        elif line_stripped.startswith("-"):
            result.append(DiffLine(type="-", content=line_stripped[1:]))
        else:
            content = line_stripped[1:] if line_stripped.startswith(" ") else line_stripped
            result.append(DiffLine(type=" ", content=content))

    return result


def diff_to_rich(diff: list[DiffLine]) -> str:
    """Format a diff as a string with Rich markup (colors).

    Args:
        diff: List of DiffLine objects from diff_texts().

    Returns:
        String with Rich markup for display in Textual/Rich.
    """
    lines: list[str] = []
    for dl in diff:
        escaped = dl.content.replace("[", "\\[")
        if dl.type == "+":
            lines.append(f"[green]+{escaped}[/green]")
        elif dl.type == "-":
            lines.append(f"[red]-{escaped}[/red]")
        elif dl.type == "@":
            lines.append(f"[cyan]{escaped}[/cyan]")
        else:
            lines.append(f" {escaped}")
    return "\n".join(lines)

