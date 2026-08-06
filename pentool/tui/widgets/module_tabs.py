"""Horizontal module navigation tab bar (Burp-style)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Tab, Tabs

from pentool.tui.messages import ModuleSelected

# Module list: (id, display name, hotkey)
MODULES: list[tuple[str, str, str]] = [
    ("dashboard",  "Dashboard",  "^H"),
    ("proxy",      "Proxy",      "^P"),
    ("repeater",   "Repeater",   "^R"),
    ("intruder",   "Intruder",   "^I"),
    ("scanner",    "Scanner",    "^S"),
    ("target",     "Target",     "^T"),
    ("decoder",    "Decoder",    "^D"),
    ("comparer",   "Comparer",   "^C"),
    ("sequencer",  "Sequencer",  "^Q"),
    ("extensions", "Extensions", "^E"),
    ("settings",   "Settings",   "^,"),
]

# Modules available in basic (no-project) mode
BASIC_MODULES = {"dashboard", "proxy", "repeater", "intruder", "settings"}

_CSS = (Path(__file__).parent / "module_tabs.tcss").read_text(encoding="utf-8")


class ModuleTabs(Widget):
    """Horizontal module navigation tabs.

    Posts the same ModuleSelected message as SideMenu —
    app.on_module_selected requires no changes.
    """

    DEFAULT_CSS = _CSS

    active_module: reactive[str] = reactive("proxy")

    def compose(self) -> ComposeResult:
        tabs = [Tab(label, id=f"tab-{mod_id}") for mod_id, label, _ in MODULES]
        yield Tabs(*tabs, id="module-tabs-inner")
        yield Static("", id="tooltip2", markup=True)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tab is None:
            return
        tab_id = event.tab.id or ""
        if tab_id.startswith("tab-"):
            module_id = tab_id[4:]
            self.active_module = module_id
            self.post_message(ModuleSelected(module_id))

    def select_module(self, module_id: str) -> None:
        """Programmatically switch tab (without posting event)."""
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

    def set_scanner_locked(self, locked: bool) -> None:
        """Grey-out the Scanner tab when no valid license is present.

        locked=True  → tab is disabled (CSS class 'tab-locked'), tooltip shown on hover.
        locked=False → normal.
        """
        try:
            tabs = self.query_one("#module-tabs-inner", Tabs)
            tab = tabs.query_one("#tab-scanner", Tab)
            if locked:
                tab.add_class("tab-locked")
                tab.tooltip = "Scanner is a PRO feature. Activate a license: pentool license trial"
            else:
                tab.remove_class("tab-locked")
                tab.tooltip = None
            tabs.refresh()
        except Exception:
            pass

    def flash(self, message: str, severity: str = "information", timeout: float = 2.5) -> None:
        """Показать краткое сообщение справа в строке модулей на timeout секунд.

        severity: "information" | "warning" | "error" | "success"
        """
        colors = {
            "information": "$primary",
            "warning":     "$warning",
            "error":       "$error",
            "success":     "$success",
        }
        color = colors.get(severity, "$primary")
        try:
            tip = self.query_one("#tooltip2", Static)
            tip.update(f"[{color}]{message}[/{color}]")
            tip.display = True
            # Отменяем предыдущий таймер если есть
            if hasattr(self, "_tooltip2_timer") and self._tooltip2_timer is not None:
                try:
                    self._tooltip2_timer.stop()
                except Exception:
                    pass
            self._tooltip2_timer = self.set_timer(timeout, self._hide_tooltip2)
        except Exception:
            pass

    def _hide_tooltip2(self) -> None:
        try:
            tip = self.query_one("#tooltip2", Static)
            tip.update("")
            tip.display = False
        except Exception:
            pass
        self._tooltip2_timer = None
