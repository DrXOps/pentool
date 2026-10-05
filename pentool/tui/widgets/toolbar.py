"""Toolbar — единый класс-контейнер для тулбаров во всех экранах.

Заменяет:
    with Horizontal(id="toolbar"/"top-bar"/"recon-toolbar"):
        ...

CSS: наследует стили через DEFAULT_CSS — не нужно дублировать в screen.tcss.

Использование:

    yield Toolbar(
        ToolbarButton("▶ Start", "btn-start", variant="success"),
        ToolbarButton("■ Stop",  "btn-stop",  classes="disabled"),
        Toolbar.sep(),
        ToolbarButton("Export", "btn-export"),
        Toolbar.sep(),
        Toolbar.progress("my-progress"),
        Toolbar.counter("my-counter"),
    )

Можно класть любые виджеты — Input, Label, Checkbox, Select, Static — Toolbar
просто контейнер (Horizontal) с едиными стилями.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, ProgressBar, Static

from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "toolbar.tcss").read_text(encoding="utf-8")


class Toolbar(Horizontal):
    """Единый тулбар для всех экранов.

    Автоматически применяет стили .toolbar.
    """

    DEFAULT_CSS = _CSS

    def __init__(self, *children: ComposeResult, id: str = "toolbar") -> None:
        super().__init__(*children, id=id)

    # ── Статические хелперы ──────────────────────────────────────────

    @staticmethod
    def sep() -> Static:
        """Разделитель | между кнопками."""
        return Static(" │ ", classes="toolbar-sep")

    @staticmethod
    def progress(id: str = "progress", total: int = 100, **kw) -> ProgressBar:
        """Прогресс-бар с предустановками."""
        return ProgressBar(total=total, show_percentage=False, id=id, **kw)

    @staticmethod
    def counter(id: str = "counter", initial: str = "0 req") -> Label:
        """Счётчик запросов."""
        return Label(initial, id=id)

    @staticmethod
    def start_stop(
        start_id: str = "btn-start",
        stop_id: str = "btn-stop",
        start_label: str = "▶ Start",
        stop_label: str = "■ Stop",
    ):
        """Стандартная пара Start + Stop с сепаратором между."""
        yield ToolbarButton(start_label, start_id, variant="success")
        yield Static(" │ ", classes="toolbar-sep")
        yield ToolbarButton(stop_label,  stop_id,  variant="error", classes="disabled")