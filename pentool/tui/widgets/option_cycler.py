"""OptionCycler — button-style option toggle, click cycles through values.

Extracted from `pentool.tui.screens.settings.screen` (originally written for
the Theme/UI-mode toggles there) into a shared widget so other screens can
reuse the same "click to cycle" interaction instead of a `Select` dropdown —
see IntruderScreen._GenerateDialog's mode toggle (Numeric range / Char
brute-force), which used to be a `Select` and was switched to this widget to
match the look/feel of the Settings screen.

It is also the only cycler in the TUI: `filter_bar_widget.Cycler` was a
second, near-identical implementation that the filter bars used; it had no
CSS of its own, no `@on`-addressable `control`, and duplicated the index
bookkeeping. It was folded into this class with ``allow_empty`` (index 0 is
the "Any" slot) and ``suffix`` (the ``" ▼"`` affordance in filter bars).
"""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widgets import Static

_CSS = (Path(__file__).parent / "option_cycler.tcss").read_text(encoding="utf-8")


class OptionCycler(Static):
    """Click-to-cycle toggle button (lighter alternative to Select for small option sets)."""

    DEFAULT_CSS = _CSS

    class Changed(Message):
        def __init__(self, cycler: "OptionCycler", value: str) -> None:
            super().__init__()
            self.option_cycler = cycler
            self.value = value

        @property
        def control(self):  # type: ignore[override]
            return self.option_cycler

    def __init__(
        self,
        options: list[tuple[str, str]],
        initial: str = "",
        allow_empty: bool = False,
        suffix: str = "",
        **kwargs,
    ) -> None:
        """options: list of (label, value)

        ``allow_empty`` makes index 0 the "no filter" slot: ``value`` then
        returns ``""`` whatever the stored value is, so filter bars can use the
        first option as "Any" without repeating the sentinel in every list.

        ``suffix`` is appended to the rendered label (filter bars use ``" ▼"``
        to signal that the control cycles).
        """
        super().__init__("", **kwargs)
        self._options = options  # [(label, value), ...]
        self._allow_empty = allow_empty
        self._suffix = suffix
        self._idx = 0
        for i, (_, v) in enumerate(options):
            if v == initial:
                self._idx = i
                break

    def on_mount(self) -> None:
        self._update_label()

    def _update_label(self) -> None:
        label, _ = self._options[self._idx]
        self.update(f"{label}{self._suffix}")

    @property
    def value(self) -> str:
        if self._allow_empty and self._idx == 0:
            return ""
        _, v = self._options[self._idx]
        return v

    def set_value(self, value: str) -> None:
        for i, (_, v) in enumerate(self._options):
            if v == value:
                self._idx = i
                self._update_label()
                return

    def reset(self) -> None:
        """Back to the first option — the "Any" slot for ``allow_empty`` cyclers."""
        self._idx = 0
        self._update_label()

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % len(self._options)
        self._update_label()
        self.post_message(self.Changed(self, self.value))
