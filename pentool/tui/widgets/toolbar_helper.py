"""Toolbar builder — shared _build_toolbar for all TUI screens.

Every screen repeats the same pattern:

    with Horizontal(id="toolbar"):
        yield ToolbarButton("Label", "btn-id")
        yield Static(" │ ", classes="toolbar-sep")
        yield ToolbarButton("Next", "btn-next")
        ...

This helper eliminates the boilerplate. Use it in compose():

    yield from build_toolbar(
        ("Label", "btn-id"),
        ("Next", "btn-next"),
        ...
    )
"""

from __future__ import annotations

from collections.abc import Generator

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from pentool.tui.widgets.toolbar_button import ToolbarButton


def build_toolbar(
    *items: tuple,
    id: str = "toolbar",
) -> Generator[ComposeResult, None, None]:
    """Yield a Horizontal toolbar with ToolbarButtons separated by │.

    Args:
        *items: (label, id) or (label, id, props_dict) tuples.
        id: widget ID for the Horizontal container.
    """
    with Horizontal(id=id):
        first = True
        for item in items:
            if not first:
                yield Static(" │ ", classes="toolbar-sep")
            first = False
            label, btn_id = item[0], item[1]
            kwargs = dict(item[2]) if len(item) > 2 else {}
            yield ToolbarButton(label, btn_id, **kwargs)