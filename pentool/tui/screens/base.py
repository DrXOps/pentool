"""BaseModuleScreen — common base for tabbed module screens.

Absorbs TabRenameMixin logic so that RepeaterScreen and ScannerScreen
no longer need to import a separate mixin.
"""

from __future__ import annotations

from textual.events import Click
from textual.widget import Widget
from textual.widgets import Input, Tab, TabbedContent

from pentool.core.logging import get_logger

_log = get_logger(__name__)


class BaseModuleScreen(Widget):
    """Base widget for all tabbed module screens.

    Provides double-click-to-rename tab behaviour (previously in TabRenameMixin).

    Subclasses must set class attributes:
        _rename_input_id: str        — id of the rename Input widget
        _rename_tab_prefix: str      — expected pane_id prefix
        _rename_tabs_widget_id: str  — id of the TabbedContent that owns the tabs

    Subclasses must implement:
        _start_rename(tab_id: str) -> None
        _rename_tab(tab_id: str, new_name: str) -> None
    """

    # ── Config (set in subclass) ───────────────────────────────────────────────
    _rename_input_id: str = "rename-input"
    _rename_tab_prefix: str = ""
    _rename_tabs_widget_id: str = ""

    # ── Double-click → rename ─────────────────────────────────────────────────

    def on_click(self, event: Click) -> None:
        """Double-click on Tab (chain=2) → rename."""
        if event.chain < 2:
            return

        widget = event.widget
        _log.debug(
            "BaseModuleScreen.on_click: chain=%d widget=%r type=%s",
            event.chain, widget, type(widget).__name__,
        )

        if not isinstance(widget, Tab):
            return

        # Derive pane_id from tab.id: "--content-tab-{pane_id}"
        tab_widget_id = widget.id or ""
        pane_id = tab_widget_id.removeprefix("--content-tab-")

        _log.debug(
            "BaseModuleScreen: pane_id=%r prefix=%r",
            pane_id, self._rename_tab_prefix,
        )

        # Filter by prefix
        if self._rename_tab_prefix and not pane_id.startswith(self._rename_tab_prefix):
            _log.debug(
                "BaseModuleScreen: pane_id %r does not match prefix %r",
                pane_id, self._rename_tab_prefix,
            )
            return

        # Filter: Tab must be inside our TabbedContent
        if self._rename_tabs_widget_id:
            try:
                tc = self.query_one(
                    f"#{self._rename_tabs_widget_id}", TabbedContent
                )
                ancestor = widget.parent
                found = False
                while ancestor is not None:
                    if ancestor is tc:
                        found = True
                        break
                    ancestor = getattr(ancestor, "parent", None)
                if not found:
                    _log.debug(
                        "BaseModuleScreen: Tab is not a descendant of %r",
                        self._rename_tabs_widget_id,
                    )
                    return
            except Exception as e:
                _log.debug("BaseModuleScreen: error finding TabbedContent: %s", e)
                return

        _log.debug("BaseModuleScreen: DOUBLE CLICK → _start_rename(%r)", pane_id)
        event.stop()
        self._start_rename(pane_id)

    # ── Input events ──────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != self._rename_input_id:
            return
        tab_id = getattr(event.input, "_rename_tab_id", None)
        new_name = event.value.strip()
        event.input.display = False
        if tab_id and new_name:
            self._rename_tab(tab_id, new_name)

    def on_input_blur(self, event: Input.Blurred) -> None:
        try:
            inp = self.query_one(f"#{self._rename_input_id}", Input)
            if inp.display:
                inp.display = False
        except Exception:
            pass

    # ── Abstract interface ────────────────────────────────────────────────────

    def _start_rename(self, tab_id: str) -> None:  # type: ignore[empty-body]
        raise NotImplementedError

    def _rename_tab(self, tab_id: str, new_name: str) -> None:  # type: ignore[empty-body]
        raise NotImplementedError
