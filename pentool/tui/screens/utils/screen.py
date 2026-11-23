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
from textual.widgets import TabbedContent

from pentool.core.logging import get_logger
from pentool.tui.header import HeaderSpec, HeaderTab
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.screens.comparer.screen import ComparerScreen
from pentool.tui.screens.decoder.screen import DecoderScreen
from pentool.tui.screens.sequencer.screen import SequencerScreen
from pentool.tui.widgets.static_tabs import remember_tab, remembered_tab, static_tabs

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
        # One factory for every module with a fixed set of panes (see
        # `widgets/static_tabs.py`): the strip, the remembered pane and the fallback
        # when a remembered id no longer exists behave the same everywhere.
        yield from static_tabs(
            "utils-tabs",
            [(tab_id, label, self._build_tool_body(tab_id)) for tab_id, label, _cls in UTILS_TABS],
            initial=remembered_tab(self.app, "utils", UTILS_TABS),
        )

    @staticmethod
    def _build_tool_body(tab_id: str):
        """Body builder for one sub-tab: the tool screen mounted under its own id."""

        def build() -> Widget:
            screen_cls = next(cls for tid, _label, cls in UTILS_TABS if tid == tab_id)
            return screen_cls(id=f"{tab_id}-body")

        return build

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
    def _active_tool(self) -> Widget | None:
        """The screen mounted in the active sub-tab (if it is built yet)."""
        try:
            return self.query_one(f"#{self._active_kind}-body")
        except NoMatches:
            return None

    def header_spec(self) -> HeaderSpec:
        """Chips for the three tools + whatever the *active* tool wants to show.

        Utils owns no actions: Start/Stop belong to Sequencer, Run to Decoder. The
        container only merges the tool's spec with its own chips, so the module
        header keeps one shape while the actions follow the visible tool.
        """
        tabs = tuple(HeaderTab(tab_id, label) for tab_id, label, _cls in UTILS_TABS)
        tool = self._active_tool()
        inner = tool.header_spec() if tool is not None and hasattr(tool, "header_spec") else HeaderSpec()
        return HeaderSpec(
            state=inner.state,
            counters=inner.counters,
            tabs=tabs,
            active_tab=self._active_kind,
            actions=inner.actions,
            more=inner.more,
        )

    def header_action(self, action_id: str) -> None:
        """Forward the click to the active tool — it owns the action."""
        tool = self._active_tool()
        handler = getattr(tool, "header_action", None) if tool is not None else None
        if handler is None:
            logger.debug("utils: action %s has no handler on the active tool", action_id)
            return
        handler(action_id)

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
            remember_tab(self.app, "utils", tab_id)
        self._refresh_header_now()

    def _refresh_header_now(self) -> None:
        refresh = getattr(self.app, "refresh_header", None)
        if refresh is not None:
            refresh()
