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
    *items: tuple[str, str],
    id: str = "toolbar",
    btn_props: dict | None = None,
) -> Generator[ComposeResult, None, None]:
    """Yield a Horizontal toolbar with ToolbarButtons separated by │.

    Args:
        *items: (label, id) pairs for ToolbarButton.
        id: widget ID for the Horizontal container.
        btn_props: optional kwargs for every button (e.g. classes="disabled").
    """
    with Horizontal(id=id):
        first = True
        for label, btn_id in items:
            if not first:
                yield Static(" │ ", classes="toolbar-sep")
            first = False
            kwargs = {"id": btn_id, **(btn_props or {})}
            yield ToolbarButton(label, **kwargs)