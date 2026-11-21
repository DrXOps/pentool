"""Utils — Decoder, Comparer and Sequencer in one module with sub-tabs.

The three utilities are tools, not project data: each had its own top-level tab,
which made the module strip 12 entries wide and pushed the names into ellipsis on
a 90-column terminal. They now live under one module (`Utils`) with sub-tab chips
in the header — the same pattern Proxy uses for Intercept / HTTP / WS.

The screens themselves are unchanged: `DecoderScreen`, `ComparerScreen` and
`SequencerScreen` are plain widgets, so each becomes the body of one sub-tab.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from pentool.core.logging import get_logger
from pentool.tui.header import HeaderSpec, HeaderTab
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.screens.decoder.screen import DecoderScreen
from pentool.tui.screens.sequencer.screen import SequencerScreen

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

#: Sub-tab id → (label, widget class). Order defines the strip.
UTILS_TABS: tuple[tuple[str, str, type[Widget]], ...] = (
    ("utils-decoder", "Decoder", DecoderScreen),
    ("utils-comparer", "Comparer", ComparerScreen),
    ("utils-sequencer", "Sequencer", SequencerScreen),
)


class UtilsScreen(AppMixin, Widget):
    """One module for the three standalone tools, one sub-tab each."""

    DEFAULT_CSS = _CSS

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_kind: str = UTILS_TABS[0][0]

    def compose(self) -> ComposeResult:
        with TabbedContent(initial=UTILS_TABS[0][0], id="utils-tabs"):
            for tab_id, label, screen_cls in UTILS_TABS:
                with TabPane(label, id=tab_id):
                    yield screen_cls(id=f"{tab_id}-body")

    # ── Sub-tab selection (hotkeys D / C / Q) ─────────────────────────────
    def select_subtab(self, kind: str) -> None:
        """Open the sub-tab whose id ends with *kind* (``decoder``/``comparer``/``sequencer``).

        Called both by the header chips and by the module hotkeys, so a hotkey
        from another module lands on the right tool with one keystroke.
        """
        tab_id = next((tid for tid, _label, _cls in UTILS_TABS if tid == f"utils-{kind}"), None)
        if tab_id is None:
            logger.warning("utils: unknown sub-tab %r", kind)
            return
        try:
            self.query_one("#utils-tabs", TabbedContent).active = tab_id
        except NoMatches as exc:
            logger.debug("utils: sub-tab %s not applied: %s", tab_id, exc)
            return
        self._active_kind = tab_id
        self._refresh_header_now()

    def active_kind(self) -> str:
        """Active sub-tab id (e.g. ``utils-decoder``)."""
        return self._active_kind

    # ── Module header ─────────────────────────────────────────────────────
    def header_spec(self) -> HeaderSpec:
        tabs = tuple(HeaderTab(tab_id, label) for tab_id, label, _cls in UTILS_TABS)
        return HeaderSpec(tabs=tabs, active_tab=self._active_kind)

    def header_action(self, action_id: str) -> None:
        """No header actions of its own: the tools have their own toolbars."""
        return None

    def header_tab_selected(self, tab_id: str) -> None:
        """A sub-tab chip was clicked in the header."""
        try:
            self.query_one("#utils-tabs", TabbedContent).active = tab_id
        except NoMatches as exc:
            logger.debug("utils: header tab %s not applied: %s", tab_id, exc)
            return
        self._active_kind = tab_id
        self._refresh_header_now()

    @on(TabbedContent.TabActivated, "#utils-tabs")
    def _on_subtab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Keep the header chips in sync whatever changed the sub-tab."""
        tab_id = getattr(event, "tab", None)
        tab_id = getattr(tab_id, "id", "") or ""
        if tab_id.startswith("--content-tab-"):
            tab_id = tab_id.removeprefix("--content-tab-")
        if tab_id:
            self._active_kind = tab_id
        self._refresh_header_now()

    def _refresh_header_now(self) -> None:
        refresh = getattr(self.app, "refresh_header", None)
        if refresh is not None:
            refresh()
