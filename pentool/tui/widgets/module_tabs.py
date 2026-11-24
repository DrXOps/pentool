"""Horizontal module navigation tab bar (Burp-style)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Tab, Tabs

from pentool.core.logging import get_logger
from pentool.tui import module_catalog
from pentool.tui.messages import ModuleSelected

logger = get_logger(__name__)

#: Module list for the tab bar: (id, label). Derived from ``module_catalog`` — the
#: single description of the modules; adding one there adds the tab here.
MODULES: list[tuple[str, str]] = module_catalog.tab_entries()

#: Modules available in basic (no-project) mode.
BASIC_MODULES: frozenset[str] = module_catalog.basic_ids()

_CSS = (Path(__file__).parent / "module_tabs.tcss").read_text(encoding="utf-8")


class ModuleTabs(Widget):
    """Horizontal module navigation tabs.

    Posts the same ModuleSelected message as SideMenu —
    app.on_module_selected requires no changes.
    """

    DEFAULT_CSS = _CSS

    active_module: reactive[str] = reactive("proxy")

    def compose(self) -> ComposeResult:
        tabs = [Tab(label, id=f"tab-{mod_id}") for mod_id, label in MODULES]
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
        except NoMatches as exc:
            # `active_module` is already assigned but the tab highlight is not:
            # the tab row and the content now disagree.
            logger.debug("tabs: %r not selected: %s", module_id, exc)

    def set_mode(self, mode: str) -> None:
        try:
            tabs = self.query_one("#module-tabs-inner", Tabs)
            for mod_id, _label in MODULES:
                tab_id = f"tab-{mod_id}"
                try:
                    tab = tabs.query_one(f"#{tab_id}", Tab)
                    if mode == "basic" and mod_id not in BASIC_MODULES:
                        tab.styles.display = "none"
                    else:
                        tab.styles.display = "block"
                except NoMatches as exc:
                    # One tab did not switch visibility: Basic mode will show
                    # it when it should not (or the other way around).
                    logger.debug("tabs: mode %r not applied to %s: %s", mode, mod_id, exc)
            tabs.refresh()
        except Exception as exc:
            # The whole UI mode was not applied — the Settings toggle stays silent.
            logger.debug("tabs: mode %r not applied at all: %s", mode, exc)

    def set_module_locked(self, module_id: str, locked: bool) -> None:
        """Grey out a module tab whose PRO feature is not licensed.

        locked=True  → tab is disabled (CSS class 'tab-locked'), tooltip shown on hover.
        locked=False → normal.
        """
        try:
            tabs = self.query_one("#module-tabs-inner", Tabs)
            tab = tabs.query_one(f"#tab-{module_id}", Tab)
            if locked:
                tab.add_class("tab-locked")
                # Never print a command here: the licence is activated from the app
                # itself (Settings → License). The old tooltip pointed at a CLI
                # command that does not exist.
                tab.tooltip = (
                    f"{module_catalog.label(module_id)} is a PRO feature. Activate a key in Settings → License."
                )
            else:
                tab.remove_class("tab-locked")
                tab.tooltip = None
            tabs.refresh()
        except Exception as exc:
            # The tab looks available without a licence (or locked with a valid
            # one) — this diverges from the check in `_switch_to`.
            logger.debug("tabs: %s lock %s not applied: %s", module_id, locked, exc)

    def flash(self, message: str, severity: str = "information", timeout: float = 2.5) -> None:
        """Flash a short message on the right of the module row for *timeout* seconds.

        severity: "information" | "warning" | "error" | "success"
        """
        colors = {
            "information": "$primary",
            "warning": "$warning",
            "error": "$error",
            "success": "$success",
        }
        color = colors.get(severity, "$primary")
        try:
            tip = self.query_one("#tooltip2", Static)
            tip.update(f"[{color}]{message}[/{color}]")
            tip.display = True
            # Cancel the previous tooltip timer, if any.
            if hasattr(self, "_tooltip2_timer") and self._tooltip2_timer is not None:
                try:
                    self._tooltip2_timer.stop()
                except Exception as exc:
                    # The timer already fired — nothing to stop; the reference
                    # below is overwritten with a new one.
                    logger.debug("tabs: flash timer already gone: %s", exc)
            self._tooltip2_timer = self.set_timer(timeout, self._hide_tooltip2)
        except Exception as exc:
            # The message never reached the user — the most expensive of the
            # silent outcomes here.
            logger.debug("tabs: flash %r not shown: %s", message, exc)

    def _hide_tooltip2(self) -> None:
        try:
            tip = self.query_one("#tooltip2", Static)
            tip.update("")
            tip.display = False
        except Exception as exc:
            # The flash message will stay on screen forever.
            logger.debug("tabs: flash not hidden: %s", exc)
        self._tooltip2_timer = None
