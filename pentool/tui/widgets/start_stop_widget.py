"""StartStopWidget — a self-contained Start/Pause/Resume/Stop button widget.

Unlike StartStopMixin, this is a Widget rather than a mixin:
- @on decorators work natively (Textual builds _textual_on from the widget)
- _running / _paused live inside the widget and do not clash with MessagePump
- The screen receives signals through StartRequested / StopRequested messages

Usage inside a screen's compose():

    yield StartStopWidget()

Usage with @on:

    @on(StartStopWidget.StartRequested)
    def on_start_stop_start(self, event: StartStopWidget.StartRequested) -> None:
        self.start_attack()

    @on(StartStopWidget.StopRequested)
    def on_start_stop_stop(self, event: StartStopWidget.StopRequested) -> None:
        self.stop_attack()

Screen API for driving state:
    start_stop_widget.set_running(True / False)  — UI synchronisation
    start_stop_widget.running / start_stop_widget.paused  — state readers
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import on
from textual.message import Message
from textual.widget import Widget

from pentool.core.logging import get_logger
from pentool.tui.widgets.toolbar import Toolbar
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)


class StartStopWidget(Widget):
    """Start/Pause/Resume/Stop buttons with a self-contained UI.

    Does not need _running / _paused from the screen.
    Does not need @on proxies.
    """

    class StartRequested(Message):
        """The user pressed Start (while IDLE)."""

        ALLOW_SELECTOR_MATCH = True

        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class PauseRequested(Message):
        """The user pressed Pause (while RUNNING)."""

        ALLOW_SELECTOR_MATCH = True

        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class ResumeRequested(Message):
        """The user pressed Resume (while PAUSED)."""

        ALLOW_SELECTOR_MATCH = True

        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    class StopRequested(Message):
        """The user pressed Stop."""

        ALLOW_SELECTOR_MATCH = True

        @property
        def control(self) -> "StartStopWidget":
            return self._widget  # type: ignore

    DEFAULT_CSS = (Path(__file__).parent / "start_stop_widget.tcss").read_text(encoding="utf-8")

    # ── ID constants ─────────────────────────────────────────────────
    ID_START: ClassVar[str] = "btn-start"
    ID_STOP: ClassVar[str] = "btn-stop"

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._running: bool = False
        self._paused: bool = False

    def compose(self) -> ...:
        yield Toolbar(
            ToolbarButton("▶ Start", self.ID_START, classes="active"),
            Toolbar.sep(),
            ToolbarButton("■ Stop", self.ID_STOP, classes="disabled"),
        )

    # ── Properties for reading state ────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return self._paused

    # ── UI synchronisation (called by the screen) ───────────────────

    def set_running(self, running: bool) -> None:
        """Switch the UI between Start<->Pause and Stop active<->disabled.

        Does not reset _paused — the screen manages pause on its own.
        """
        self._running = running
        try:
            btn_start = self.query_one(f"#{self.ID_START}", ToolbarButton)
            btn_stop = self.query_one(f"#{self.ID_STOP}", ToolbarButton)
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
        except Exception as exc:
            # The buttons kept their previous appearance: the attack is running while
            # the UI shows «▶ Start» (or the reverse), and Stop may be unavailable.
            logger.debug("start/stop: running state %s not shown: %s", running, exc)

    def set_paused(self, paused: bool) -> None:
        """Switch the UI between Pause <-> Resume (without touching _running).

        Lifting the pause returns the button to «⏸ Pause» only if the attack is
        genuinely running. Otherwise "not paused" also means "stopped", and the
        label has to stay «▶ Start»: the screen synchronises state with the pair
        ``set_running(False)`` + ``set_paused(False)``, and the second call must
        not cancel out the first (F-031: a fresh Intruder tab displayed «⏸ Pause»
        before the first run).
        """
        self._paused = paused
        try:
            btn_start = self.query_one(f"#{self.ID_START}", ToolbarButton)
            if paused:
                btn_start.label = "▶ Resume"
                btn_start.remove_class("warn")
                btn_start.add_class("active")
            elif self._running:
                btn_start.label = "⏸ Pause"
                btn_start.remove_class("active")
                btn_start.add_class("warn")
            else:
                btn_start.label = "▶ Start"
                btn_start.remove_class("warn")
                btn_start.add_class("active")
        except Exception as exc:
            # The button label does not reflect the pause: the next click on
            # «⏸ Pause» will lift the pause instead of setting it — the opposite.
            logger.debug("start/stop: paused state %s not shown: %s", paused, exc)

    # ── Click handling ─────────────────────────────────────────────

    @on(ToolbarButton.Pressed, f"#{ID_START}")
    def _on_start_pressed(self, _: ToolbarButton.Pressed) -> None:
        """Start / Pause / Resume — depending on the current state."""
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
