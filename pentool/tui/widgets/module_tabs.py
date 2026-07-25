"""Горизонтальная панель вкладок для навигации по модулям (Burp-стиль)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Tab, Tabs

from pentool.tui.widgets.menu import BASIC_MODULES, MODULES, ModuleSelected
from pathlib import Path

_CSS = (Path(__file__).parent / "module_tabs.tcss").read_text(encoding="utf-8")


class ModuleTabs(Widget):
    """Горизонтальные вкладки навигации по модулям.

    Постит тот же ModuleSelected message что и SideMenu —
    app.on_module_selected не требует изменений.
    """

    DEFAULT_CSS = _CSS

    active_module: reactive[str] = reactive("proxy")

    def compose(self) -> ComposeResult:
        tabs = [Tab(label, id=f"tab-{mod_id}") for mod_id, label, _ in MODULES]
        yield Tabs(*tabs, id="module-tabs-inner")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab is None:
            return
        tab_id = event.tab.id or ""
        if tab_id.startswith("tab-"):
            module_id = tab_id[4:]
            self.active_module = module_id
            self.post_message(ModuleSelected(module_id))

    def select_module(self, module_id: str) -> None:
        """Программно переключить вкладку (без постинга события).

        Args:
            module_id: ID модуля из MODULES.
        """
        self.active_module = module_id
        try:
            tabs = self.query_one("#module-tabs-inner", Tabs)
            tabs.active = f"tab-{module_id}"
        except Exception:
            pass

    def set_mode(self, mode: str) -> None:
        try:
            tabs = self.query_one("#module-tabs-inner", Tabs)
            for mod_id, _, _ in MODULES:
                tab_id = f"tab-{mod_id}"
                try:
                    tab = tabs.query_one(f"#{tab_id}", Tab)
                    if mode == "basic" and mod_id not in BASIC_MODULES:
                        tab.styles.display = "none"
                    else:
                        tab.styles.display = "block"
                except Exception:
                    pass
            tabs.refresh()
        except Exception:
            pass
