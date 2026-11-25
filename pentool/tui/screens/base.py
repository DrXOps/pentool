"""BaseModuleScreen — common base for tabbed module screens.

Absorbs TabRenameMixin logic so that RepeaterScreen and ScannerScreen
no longer need to import a separate mixin.
"""

from __future__ import annotations

from textual.widget import Widget

from pentool.core.logging import get_logger
from pentool.tui.mixins.tab_rename import TabRenameMixin

_log = get_logger(__name__)


class BaseModuleScreen(TabRenameMixin, Widget):
    """Base for tabbed module screens (double-click-to-rename).

    Subclasses set _rename_input_id, _rename_tab_prefix, _rename_tabs_widget_id.
    Subclasses implement _start_rename and _rename_tab.
    """

    # ── Config (set in subclass) ───────────────────────────────────────────────
    _rename_input_id: str = "rename-input"
    _rename_tab_prefix: str = ""
    _rename_tabs_widget_id: str = ""

    # ── Rename contract (see pentool/tui/mixins/tab_rename.py) ────────────────
    # The four handlers used to live here; they are in TabRenameMixin now, together
    # with the copies that grew in TabbedContentPanel and RepeaterScreen.

    _rename_input_id: str = "rename-input"

    def _rename_state(self, tab_id: str) -> object | None:
        """Screens whose tab state lives elsewhere override this (Repeater, panel users)."""
        return None

    def _apply_tab_rename(self, tab_id: str, new_name: str) -> None:
        """Default: nothing to write. A screen with tab state overrides it."""
        _log.debug("BaseModuleScreen: rename of %r ignored (no state hook)", tab_id)
