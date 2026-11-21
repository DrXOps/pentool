"""Toolbar — единый класс-контейнер для тулбаров во всех экранах.

Заменяет:
    with Horizontal(id="toolbar"/"top-bar"/"recon-toolbar"):
        ...

CSS: наследует стили через DEFAULT_CSS — не нужно дублировать в screen.tcss.

Использование:

    yield Toolbar(
        ToolbarButton("▶ Start", "btn-start", classes="active"),
        ToolbarButton("■ Stop",  "btn-stop",  classes="inactive disabled"),
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

    def __init__(self, *children: ComposeResult, id: str | None = None) -> None:
        # No default id: every module screen is mounted at once inside the
        # app's ContentSwitcher, so a shared id="toolbar" made
        # ``query_one("#toolbar")`` resolve to whichever screen came first in
        # composition order (REPORT F-006). Textual generates a unique id
        # when ``id`` is None.
        super().__init__(*children, id=id)

    # ── Статические хелперы ──────────────────────────────────────────

    @staticmethod
    def sep() -> Static:
        """Разделитель | между кнопками."""
        return Static(" │ ", classes="toolbar-sep")

    @staticmethod
    def grouped(*buttons) -> list:
        """Кнопки через пробел, без разделителей.

        Разделители `│` убраны из интерфейса целиком (2026-11-21): строка
        кнопок читается по расстоянию, а черты дробили один ряд действий на
        «группы», которых в модели нет. Метод сохранён, чтобы существующие
        вызовы не переписывать.

        Example:
            Toolbar(*Toolbar.grouped(btn_add, btn_remove, btn_clear))
        """
        return list(buttons)

    @staticmethod
    def buttons(*buttons):
        """То же, что ``grouped``, но для ``yield from`` в compose."""
        yield from Toolbar.grouped(*buttons)

    @staticmethod
    def group_buttons(*buttons) -> list:
        """Кнопки БЕЗ разделителей внутри — одна логическая группа."""
        return list(buttons)

    @staticmethod
    def row(*groups) -> list:
        """Строка тулбара из групп: разделители только МЕЖДУ группами.

        Это и есть «правильный базовый класс» для разделителей:
          Toolbar.row(
              Toolbar.group_buttons(label, first),      # подпись + первая кнопка
              Toolbar.group_buttons(add, remove, clear),  # действия над списком
              Toolbar.group_buttons(load, generate),    # импорт/генерация
          )
        Внутри группы черта не нужна (это одно действие с разными кнопками),
        между группами — нужна. ``grouped`` ставит черту между каждой парой и
        подходит для плоского списка равнозначных действий.
        """
        items: list = []
        for index, group in enumerate(groups):
            if index:
                items.append(Static(" │ ", classes="toolbar-sep"))
            items.extend(group)
        return items

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
        yield ToolbarButton(start_label, start_id, classes="active")
        yield Static(" │ ", classes="toolbar-sep")
        yield ToolbarButton(stop_label, stop_id, classes="inactive disabled")
