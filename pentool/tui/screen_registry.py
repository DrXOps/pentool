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
    "settings":   SettingsScreen,
}

# Recon screen — PRO-only, conditional import + license gate
try:
    from pro.pentool.tui.screens.recon.screen import ReconScreen  # type: ignore[import-untyped]
    # License gate: same pattern as ScannerScreen — only register when
    # the user has a valid PRO license with ai_discovery feature.
    try:
        from pentool.core.license import get_session_license
        lic = get_session_license()
        if lic and lic.valid and lic.has_feature("ai_discovery"):
            SCREEN_MAP["recon"] = ReconScreen
    except Exception:
        # If license check fails (no PRO license), fall through silently
        # so the module stays hidden. Without this check, every dev
        # checkout (which has the pro/ submodule) would see ReconScreen
        # even without an active PRO license.
        pass
except (ImportError, ModuleNotFoundError):
    pass


def get_screen_class(module_id: str) -> type | None:
    """Return the screen class for a module_id, or None if unknown."""
    return SCREEN_MAP.get(module_id)
