"""Helpers for the bottom hints row (Global / Module scope).

The row itself is composed in `PentoolApp.compose()` from the shared widgets
(`ToolbarButton` + `Static`) — the same way every screen builds its toolbar — and
the app owns the scope state. This module keeps the pure parts: the scope
constants, the global key colours and the module display name.
"""

from __future__ import annotations

SCOPE_GLOBAL = "global"
SCOPE_MODULE = "module"

#: Key colours for the global scope (module-switching keys).
GLOBAL_KEY_COLORS: dict[str, str] = {
    "H": "#88ccff",  # Dash
    "P": "#66dd88",  # Proxy
    "R": "#ff9944",  # Repeater
    "I": "#ff6666",  # Intruder
    "S": "#aa66ff",  # Scanner
    "T": "#66ccff",  # Target
    "D": "#ddbb44",  # Decoder
    "C": "#ff88cc",  # Comparer
    "Q": "#77dddd",  # Sequencer
    "E": "#aaaaaa",  # Extensions
}


def render_global_entry(keys: str, description: str) -> str:
    """One global entry: coloured key + muted description."""
    color = GLOBAL_KEY_COLORS.get(keys, "$text")
    desc = f"[dim]{description}[/]" if description else ""
    return f"[bold {color}]{keys}[/] {desc}"


def module_label(module_id: str) -> str:
    """Display name of a module (``Proxy``); falls back to a title-cased id."""
    from pentool.tui.widgets.module_tabs import MODULES

    for mod_id, label, _hotkey in MODULES:
        if mod_id == module_id:
            return label
    return module_id.replace("_", " ").title()
