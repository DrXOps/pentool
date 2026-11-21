"""Toolbar — a single container class for toolbars across all screens.

Replaces:
    with Horizontal(id="toolbar"/"top-bar"/"recon-toolbar"):
        ...

CSS: inherits styles via DEFAULT_CSS — no need to duplicate them in screen.tcss.

Usage:

    yield Toolbar(
        ToolbarButton("▶ Start", "btn-start", classes="active"),
        ToolbarButton("■ Stop",  "btn-stop",  classes="inactive disabled"),
        Toolbar.sep(),
        ToolbarButton("Export", "btn-export"),
        Toolbar.sep(),
        Toolbar.progress("my-progress"),
        Toolbar.counter("my-counter"),
    )

Any widgets can be put inside — Input, Label, Checkbox, Select, Static — Toolbar
is just a container (Horizontal) with unified styles.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, ProgressBar, Static

from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "toolbar.tcss").read_text(encoding="utf-8")


class Toolbar(Horizontal):
    """A single toolbar for all screens.

    Automatically applies the .toolbar styles.
    """

    DEFAULT_CSS = _CSS

    def __init__(self, *children: ComposeResult, id: str | None = None) -> None:
        # No default id: every module screen is mounted at once inside the
        # app's ContentSwitcher, so a shared id="toolbar" made
        # ``query_one("#toolbar")`` resolve to whichever screen came first in
        # composition order (REPORT F-006). Textual generates a unique id
        # when ``id`` is None.
        super().__init__(*children, id=id)

    # ── Static helpers ───────────────────────────────────────────────

    @staticmethod
    def sep() -> Static:
        """Separator | between buttons."""
        return Static(" │ ", classes="toolbar-sep")

    @staticmethod
    def grouped(*buttons) -> list:
        """Buttons separated by a space, without separators.

        The `│` separators were removed from the interface entirely (2026-11-21):
        a row of buttons reads by distance, while the bars split one row of
        actions into "groups" that the model does not have. The method is kept
        so existing call sites do not have to be rewritten.

        Example:
            Toolbar(*Toolbar.grouped(btn_add, btn_remove, btn_clear))
        """
        return list(buttons)

    @staticmethod
    def buttons(*buttons):
        """Same as ``grouped``, but for ``yield from`` in compose."""
        yield from Toolbar.grouped(*buttons)

    @staticmethod
    def group_buttons(*buttons) -> list:
        """Buttons WITHOUT separators inside — a single logical group."""
        return list(buttons)

    @staticmethod
    def row(*groups) -> list:
        """A toolbar row made of groups: separators only BETWEEN groups.

        This is the "correct base class" for separators:
          Toolbar.row(
              Toolbar.group_buttons(label, first),      # caption + first button
              Toolbar.group_buttons(add, remove, clear),  # actions on the list
              Toolbar.group_buttons(load, generate),    # import/generation
          )
        Inside a group the bar is not needed (it is one action with different
        buttons), between groups it is needed. ``grouped`` puts a bar between
        every pair and suits a flat list of equivalent actions.
        """
        items: list = []
        for index, group in enumerate(groups):
            if index:
                items.append(Static(" │ ", classes="toolbar-sep"))
            items.extend(group)
        return items

    @staticmethod
    def progress(id: str = "progress", total: int = 100, **kw) -> ProgressBar:
        """Progress bar with presets."""
        return ProgressBar(total=total, show_percentage=False, id=id, **kw)

    @staticmethod
    def counter(id: str = "counter", initial: str = "0 req") -> Label:
        """Request counter."""
        return Label(initial, id=id)

    @staticmethod
    def start_stop(
        start_id: str = "btn-start",
        stop_id: str = "btn-stop",
        start_label: str = "▶ Start",
        stop_label: str = "■ Stop",
    ):
        """Standard Start + Stop pair with a separator in between."""
        yield ToolbarButton(start_label, start_id, classes="active")
        yield Static(" │ ", classes="toolbar-sep")
        yield ToolbarButton(stop_label, stop_id, classes="inactive disabled")
