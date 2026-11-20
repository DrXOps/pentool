"""Screen registry — maps module_id -> widget class.

Centralises the module-to-screen mapping previously hardcoded as _SCREEN_MAP
in the app (Этап 5.1, screen_registry domain). Keeps the App class thin and
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
    """Загрузить PRO-экран Recon по требованию.

    На уровне модуля это делать нельзя: экран Recon тянет виджеты, которые
    импортируют `pentool.tui.app`, а реестр читается из того же `app` —
    получается цикл, `ImportError`, который прежний код молча проглатывал, и
    модуль «просто не существовал»: вкладка открывалась пустым окном (диагноз
    2026-11-17). Теперь импорт выполняется при первом обращении, когда `app` уже
    собран, а причина отказа пишется в журнал.
    """
    try:
        # Важно: без префикса `pro.` — `pentool.__init__._bootstrap_pro()`
        # расширяет `pentool.__path__` на `pro/pentool`, поэтому экран лежит
        # как `pentool.tui.screens.recon.screen`. Импорт `pro.pentool.…` не
        # работает никогда: на sys.path попадает сам каталог `pro/`, а не
        # пакет с таким именем (проверено: ModuleNotFoundError).
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
