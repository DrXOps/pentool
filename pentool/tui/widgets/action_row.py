"""Action buttons drawn inside a tool's own row instead of the module header.

The header used to render them on the same line as the sub-tab chips. The chips keep
their place; the buttons are drawn by the tool itself, from the same `HeaderAction` specs
it hands to the header — one definition, two consumers.
"""

from __future__ import annotations

from collections.abc import Iterator

from pentool.tui.header import HeaderAction
from pentool.tui.widgets.toolbar_button import ToolbarButton


def action_buttons(actions: tuple[HeaderAction, ...]) -> Iterator[ToolbarButton]:
    """Yield one button per action, tagged so the owning screen can dispatch it."""
    for action in actions:
        button = ToolbarButton(action.label, f"tool-act-{action.action}", classes="tool-act")
        button.data_action = action.action  # type: ignore[attr-defined]
        button.disabled = not action.enabled
        yield button


def action_of(button: ToolbarButton) -> str:
    return str(getattr(button, "data_action", ""))
