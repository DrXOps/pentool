"""Screen registry — maps module_id -> widget class.

Centralises the module-to-screen mapping previously hardcoded as _SCREEN_MAP
in the app (Stage 5.1, screen_registry domain). Keeps the App class thin and
gives a single place to look up "which screen does module X open".
"""

from __future__ import annotations

from pentool.core.logging import get_logger
from pentool.tui.screens import (
    DashboardScreen,
    ExtensionsScreen,
    IntruderScreen,
    ProxyScreen,
    RepeaterScreen,
    ScannerScreen,
    SettingsScreen,
    TargetScreen,
    UtilsScreen,
)

logger = get_logger(__name__)

# Mapping module_id → widget class
SCREEN_MAP: dict[str, type] = {
    "dashboard": DashboardScreen,
    "proxy": ProxyScreen,
    "repeater": RepeaterScreen,
    "intruder": IntruderScreen,
    "scanner": ScannerScreen,
    "target": TargetScreen,
    # Decoder / Comparer / Sequencer are sub-tabs of one module now.
    "utils": UtilsScreen,
    "extensions": ExtensionsScreen,
    "settings": SettingsScreen,
}


def _load_recon_screen() -> type | None:
    """Load the PRO Recon screen on demand.

    Doing this at module level is not an option: the Recon screen pulls in
    widgets that import `pentool.tui.app`, and the registry is read from that
    same `app` — that makes a cycle, an `ImportError` the old code swallowed
    silently, and the module "simply did not exist": the tab opened as an empty
    window (diagnosis 2026-11-17). Now the import runs on first access, when
    `app` is already built, and the reason for a failure goes to the log.
    """
    try:
        # Important: no `pro.` prefix — `pentool.__init__._bootstrap_pro()`
        # extends `pentool.__path__` with `pro/pentool`, so the screen lives
        # as `pentool.tui.screens.recon.screen`. Importing `pro.pentool.…`
        # never works: what lands on sys.path is the `pro/` directory itself,
        # not a package of that name (verified: ModuleNotFoundError).
        from pentool.tui.screens.recon.screen import ReconScreen  # type: ignore[import-untyped]
    except (ImportError, ModuleNotFoundError):
        logger.warning("screen_registry: PRO-экран recon недоступен (PRO не установлен или устарел)", exc_info=True)
        return None
    SCREEN_MAP["recon"] = ReconScreen
    logger.debug("screen_registry: PRO-экран recon зарегистрирован")
    return ReconScreen


def get_screen_class(module_id: str) -> type | None:
    """Return the screen class for a module_id, or None if unknown."""
    if module_id == "recon" and "recon" not in SCREEN_MAP:
        _load_recon_screen()
    return SCREEN_MAP.get(module_id)
