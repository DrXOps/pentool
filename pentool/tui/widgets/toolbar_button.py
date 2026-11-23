"""ToolbarButton — unified flat button for toolbars across all screens."""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widgets import Static

_CSS = (Path(__file__).parent / "toolbar_button.tcss").read_text(encoding="utf-8")


class ToolbarButton(Static):
    """Flat toolbar button — no border, height 1.

    CSS classes:
        .active   — green color (enabled / active)
        .inactive — red color (disabled)
        .disabled — grey color, click is ignored
        .warn     — orange color (warning)
        .sending  — yellow color (waiting for response)
    """

    DEFAULT_CSS = _CSS

    #: Set by the module header: which screen action / sub-tab this button
    #: stands for. Kept as plain attributes so one widget class serves both
    #: the fixed toolbar slots and the header's recycled slots.
    data_action: str = ""
    data_tab: str = ""

    class Pressed(Message):
        """Button press message."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, button: "ToolbarButton") -> None:
            super().__init__()
            self.button = button

        @property
        def control(self) -> "ToolbarButton":
            """Allows @on(ToolbarButton.Pressed, "#btn-id") CSS selector."""
            return self.button

    def __init__(
        self,
        label: str,
        btn_id: str,
        classes: str = "",
        tooltip: str | None = None,
        variant: str = "default",
    ) -> None:
        super().__init__(label, id=btn_id, classes=classes)
        self._label = label
        self._disabled = "disabled" in classes.split()
        self._apply_variant(variant)
        if tooltip:
            self.tooltip = tooltip

    def _apply_variant(self, variant: str) -> None:
        """Semantic colouring of the button (PRO modules pass `variant=`).

        The classes are written as literals rather than built from an f-string:
        the `check_tui_css.py` gate checks every `.tcss` class against literals
        in Python, and a built name is rightly considered "unused" by it.
        """
        if variant == "success":
            self.add_class("variant-success")
        elif variant == "warning":
            self.add_class("variant-warning")
        elif variant == "error":
            self.add_class("variant-error")

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = value
        self.update(value)

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        # Assigning the same value must not touch the CSS class: `add_class` with
        # `update=True` re-runs the whole stylesheet pass, and the module header
        # assigns `disabled` to ~19 slots on every redraw (twice during startup).
        if value == self._disabled and self.has_class("disabled") == bool(value):
            return
        self._disabled = value
        if value:
            self.add_class("disabled")
        else:
            self.remove_class("disabled")

    def on_click(self) -> None:
        """Posts Pressed only if the button is not disabled."""
        if not self._disabled:
            self.post_message(self.Pressed(self))
