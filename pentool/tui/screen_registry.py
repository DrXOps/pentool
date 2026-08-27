"""Screen registry — maps module_id -> widget class.

Centralises the module-to-screen mapping previously hardcoded as _SCREEN_MAP
in the app (Этап 5.1, screen_registry domain). Keeps the App class thin and
gives a single place to look up "which screen does module X open".
"""

from __future__ import annotations

from pentool.tui.screens import (
    ComparerScreen,
    DashboardScreen,
    DecoderScreen,
    ExtensionsScreen,
    IntruderScreen,
    ProxyScreen,
    RepeaterScreen,
    ScannerScreen,
    SequencerScreen,
    TerminalScreen,
    SettingsScreen,
    TargetScreen,
)

# Mapping module_id → widget class
SCREEN_MAP: dict[str, type] = {
    "dashboard":  DashboardScreen,
    "proxy":      ProxyScreen,
    "repeater":   RepeaterScreen,
    "intruder":   IntruderScreen,
    "scanner":    ScannerScreen,
    "target":     TargetScreen,
    "decoder":    DecoderScreen,
    "comparer":   ComparerScreen,
    "sequencer":  SequencerScreen,
    "extensions": ExtensionsScreen,
    "terminal":   TerminalScreen,
    "settings":   SettingsScreen,
}


def get_screen_class(module_id: str) -> type | None:
    """Return the screen class for a module_id, or None if unknown."""
    return SCREEN_MAP.get(module_id)
