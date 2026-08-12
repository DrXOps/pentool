"""OptionCycler — button-style option toggle, click cycles through values.

Extracted from `pentool.tui.screens.settings.screen` (originally written for
the Theme/UI-mode toggles there) into a shared widget so other screens can
reuse the same "click to cycle" interaction instead of a `Select` dropdown —
see IntruderScreen._GenerateDialog's mode toggle (Numeric range / Char
brute-force), which used to be a `Select` and was switched to this widget to
match the look/feel of the Settings screen.
"""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widgets import Static

_CSS = (Path(__file__).parent / "option_cycler.tcss").read_text(encoding="utf-8")


class OptionCycler(Static):
    """Option toggle button — each click cycles through values.

    Drop-in-ish replacement for a `Select` with a small, fixed set of
    options where a dropdown is more chrome than the choice needs — the
    label shows the current value directly, and clicking advances to the
    next option (wrapping around), posting a `Changed` message each time.
    """

    DEFAULT_CSS = _CSS

    class Changed(Message):
        def __init__(self, cycler: "OptionCycler", value: str) -> None:
            super().__init__()
            self.option_cycler = cycler
            self.value = value

        @property
        def control(self):  # type: ignore[override]
            return self.option_cycler

    def __init__(self, options: list[tuple[str, str]], initial: str = "", **kwargs) -> None:
        """options: list of (label, value)"""
        super().__init__("", **kwargs)
        self._options = options  # [(label, value), ...]
        self._idx = 0
        for i, (_, v) in enumerate(options):
            if v == initial:
                self._idx = i
                break

    def on_mount(self) -> None:
        self._update_label()

    def _update_label(self) -> None:
        label, _ = self._options[self._idx]
        self.update(label)

    @property
    def value(self) -> str:
        _, v = self._options[self._idx]
        return v

    def set_value(self, value: str) -> None:
        for i, (_, v) in enumerate(self._options):
            if v == value:
                self._idx = i
                self._update_label()
                return

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % len(self._options)
        self._update_label()
        self.post_message(self.Changed(self, self.value))
