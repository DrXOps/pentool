"""Сравнение текстов (diff) с форматированием для Rich/Textual."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Literal


@dataclass
class DiffLine:
    """Одна строка результата diff."""

    type: Literal["+", "-", " ", "@"]
    content: str


def diff_texts(text1: str, text2: str, context: int = 3) -> list[DiffLine]:
    """Сравнить два текста и вернуть список строк diff (unified format).

    Args:
        text1: Исходный текст (левый / «до»).
        text2: Изменённый текст (правый / «после»).
        context: Количество контекстных строк вокруг изменений.

    Returns:
        Список объектов DiffLine.
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
    """Форматировать diff в строку с Rich-разметкой (цвета).

    Args:
        diff: Список DiffLine от diff_texts().

    Returns:
        Строка с Rich markup для отображения в Textual/Rich.
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


def diff_summary(text1: str, text2: str) -> dict[str, int]:
    added = removed = unchanged = 0
    for dl in diff_texts(text1, text2):
        if dl.type == "+":
            added += 1
        elif dl.type == "-":
            removed += 1
        elif dl.type == " ":
            unchanged += 1
    return {"added": added, "removed": removed, "unchanged": unchanged}
