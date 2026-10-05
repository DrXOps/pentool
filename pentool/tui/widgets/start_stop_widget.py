"""StartStopWidget — независимый виджет кнопок Start/Pause/Resume/Stop.

Отличается от StartStopMixin тем, что это Widget, а не mixin:
- @on декораторы работают нативно (Textual собирает _textual_on из виджета)
- _running / _paused живут внутри виджета, не конфликтуют с MessagePump
- Экран получает сигналы через сообщения StartRequested / StopRequested

Использование в compose() экрана:

    yield StartStopWidget()

Использование в @on:

    @on(StartStopWidget.StartRequested)
    def on_start_stop_start(self, event: StartStopWidget.StartRequested) -> None:
        self.start_attack()

    @on(StartStopWidget.StopRequested)
    def on_start_stop_stop(self, event: StartStopWidget.StopRequested) -> None:
        self.stop_attack()

API экрана для управления состоянием:
    start_stop_widget.set_running(True / False)  — синхронизация UI
    start_stop_widget.running / start_stop_widget.paused  — чтение состояния
"""

from __future__ import annotations

from typing import ClassVar

from textual import on
from textual.message import Message
from textual.widget import Widget

from pentool.tui.widgets.toolbar import Toolbar
from pentool.tui.widgets.toolbar_button import ToolbarButton


class StartStopWidget(Widget):
    """Кнопки Start/Pause/Resume/Stop с самодостаточным UI.

    Не требует от экрана _running / _paused.
    Не требует @on-прокси.
    """

    class StartRequested(Message):
        """Пользователь нажал Start (когда был IDLE)."""
        ALLOW_SELECTOR_MATCH = True
        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class PauseRequested(Message):
        """Пользователь нажал Pause (когда был RUNNING)."""
        ALLOW_SELECTOR_MATCH = True
        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class ResumeRequested(Message):
        """Пользователь нажал Resume (когда был PAUSED)."""
        ALLOW_SELECTOR_MATCH = True
        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class StopRequested(Message):
        """Пользователь нажал Stop."""
        ALLOW_SELECTOR_MATCH = True
        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    DEFAULT_CSS = """
    StartStopWidget {
        height: 1;
        layout: horizontal;
    }
    """

    # ── ID constants ─────────────────────────────────────────────────
    ID_START: ClassVar[str] = "btn-start"
    ID_STOP:  ClassVar[str] = "btn-stop"

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._running: bool = False
        self._paused: bool = False

    def compose(self) -> ...:
        yield Toolbar(
            ToolbarButton("▶ Start",   self.ID_START, classes="active"),
            Toolbar.sep(),
            ToolbarButton("■ Stop",    self.ID_STOP,  classes="disabled"),
        )

    # ── Свойства для чтения состояния ────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return self._paused

    # ── Синхронизация UI (вызывается экраном) ────────────────────────

    def set_running(self, running: bool) -> None:
        """Переключить UI между Start<->Pause и Stop active<->disabled."""
        self._running = running
        self._paused = False
        try:
            btn_start = self.query_one(f"#{self.ID_START}", ToolbarButton)
            btn_stop  = self.query_one(f"#{self.ID_STOP}",  ToolbarButton)
            if running:
                btn_start.label = "⏸ Pause"
                btn_start.remove_class("active")
                btn_start.add_class("warn")
                btn_stop.disabled = False
            else:
                btn_start.label = "▶ Start"
                btn_start.remove_class("warn")
                btn_start.add_class("active")
                btn_stop.disabled = True
        except Exception:
            pass

    def set_paused(self, paused: bool) -> None:
        """Переключить UI между Pause <-> Resume (не меняя _running)."""
        self._paused = paused
        try:
            btn_start = self.query_one(f"#{self.ID_START}", ToolbarButton)
            if paused:
                btn_start.label = "▶ Resume"
                btn_start.remove_class("warn")
                btn_start.add_class("active")
            else:
                btn_start.label = "⏸ Pause"
                btn_start.remove_class("active")
                btn_start.add_class("warn")
        except Exception:
            pass

    # ── Обработка нажатий ──────────────────────────────────────────

    @on(ToolbarButton.Pressed, f"#{ID_START}")
    def _on_start_pressed(self, _: ToolbarButton.Pressed) -> None:
        """Start / Pause / Resume — в зависимости от состояния."""
        if self._paused:
            self.post_message(self.ResumeRequested())
        elif self._running:
            self.post_message(self.PauseRequested())
        else:
            self.post_message(self.StartRequested())

    @on(ToolbarButton.Pressed, f"#{ID_STOP}")
    def _on_stop_pressed(self, _: ToolbarButton.Pressed) -> None:
        """Stop."""
        self.post_message(self.StopRequested())