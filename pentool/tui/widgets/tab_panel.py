"""TabbedContentPanel — a generic tab container with isolation.

Each tab gets its own TabPane with widgets built by build_tab_ui().
The owning module:
1. Defines the TabState dataclass
2. Passes build_tab_ui (builds the TabPane synchronously), save_tab, load_tabs
3. Subscribes to TabActivated / TabDeactivated messages

NB: Internal widget IDs are MEANINGLESS to the screen's @on decorators —
all communication goes through TabbedContentPanel messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, TypeVar

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, TabbedContent, TabPane

from pentool.core.logging import get_logger
from pentool.tui.mixins.tab_rename import TabRenameMixin

logger = get_logger(__name__)

# ── Hooks (optional) ─────────────────────────────────────────────────
# A module may pass a callable that is invoked on specific events.
# For example, on tab creation — persist it to the DB.
# They are optional: the module can subscribe to messages instead.


@dataclass
class _TabMeta:
    """Internal state of a tab inside the container."""

    tab_id: str
    pane: TabPane
    name: str


TState = TypeVar("TState")


class TabbedContentPanel(TabRenameMixin, Widget, Generic[TState]):
    """Generic container with isolated tabs.

    Generic[TState] — the module passes in its own dataclass (e.g. _IntruderTabState).

    Args:
        id: container ID in the DOM (needed for @on filtering).
        tab_id_prefix: prefix for generated tab_id (e.g. "intruder-tab-").
        build_tab_ui: (state, tab_id) -> TabPane. Builds the widgets synchronously.
        save_tab: (state) -> Awaitable. Persist the tab state.
        load_tabs: () -> Awaitable[list[state]]. Load all tabs.
    """

    # ── Messages ───────────────────────────────────────────────────────
    # All messages take the owner (the TabbedContentPanel itself) and expose it
    # via `control`. This is required by @on(TabActivated, "#intruder-tabs"):
    # the decorator matches the CSS selector against message.control, so control
    # must return the panel widget itself (following Textual's TabbedContent).

    class TabCreated(Message):
        """Posted AFTER a tab is created."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner

        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabActivated(Message):
        """Posted AFTER switching to a new tab."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner

        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabDeactivated(Message):
        """Posted BEFORE switching to another tab (the old one is still active)."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner

        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabClosed(Message):
        """Posted AFTER a tab is closed."""

        ALLOW_SELECTOR_MATCH = True

        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner

        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    # ── Configuration ────────────────────────────────────────────────────

    def __init__(
        self,
        *,
        id: str = "tcp",
        tab_id_prefix: str = "tcp-tab-",
        build_tab_ui: Callable[[TState, str], TabPane] | None = None,
        mount_tab_ui: Callable[[TState, str], None] | None = None,
        save_tab: Callable[[TState], Awaitable[None]] | None = None,
        load_tabs: Callable[[], Awaitable[list[TState]]] | None = None,
        rename_input_id: str = "tcp-rename-input",
        # Minimum number of tabs (1 = the last one cannot be closed)
        min_tabs: int = 1,
    ) -> None:
        super().__init__(id=id)
        self._tab_id_prefix = tab_id_prefix
        self._build_tab_ui = build_tab_ui
        self._mount_tab_ui = mount_tab_ui
        self._save_tab = save_tab
        self._load_tabs_fn = load_tabs
        self._rename_input_id = rename_input_id
        self._min_tabs = min_tabs

        # ── State ──────────────────────────────────────────────────────
        self._states: dict[str, TState] = {}  # tab_id → state
        self._meta: dict[str, _TabMeta] = {}  # tab_id → meta
        self._counter: int = 0
        self._active_tab_id: str | None = None
        self._generation: int = 0

        # ── Generation guard ────────────────────────────────────────────
        # Protects against stale callbacks when the project changes.
        # The screen calls set_generation_guard() before load_tabs_from_storage().
        self._tabs_generation: int = 0

    # ── compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield TabbedContent(id=f"{self.id}-content")
        # Class in addition to id: screens style the field with a single `.tab-rename`
        # rule instead of a copy of that rule per screen with its own id.
        inp_rename = Input(id=self._rename_input_id, classes="tab-rename", placeholder="Tab name...", compact=True)
        inp_rename.display = False
        yield inp_rename

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def tabs_content(self) -> TabbedContent:
        return self.query_one(f"#{self.id}-content", TabbedContent)

    @property
    def active_tab_id(self) -> str | None:
        return self._active_tab_id

    @property
    def active_state(self) -> TState | None:
        if self._active_tab_id is None:
            return None
        return self._states.get(self._active_tab_id)

    @property
    def tab_count(self) -> int:
        return len(self._states)

    @property
    def all_states(self) -> list[TState]:
        return list(self._states.values())

    # ── Generation guard ──────────────────────────────────────────────────

    def set_generation(self, gen: int) -> None:
        """Set the generation used for stale protection on project change."""
        self._tabs_generation = gen

    def _is_stale(self) -> bool:
        """Check whether the generation changed (stale callback)."""
        return self._tabs_generation == 0  # simplified; screen sets it

    # ── Lifecycle: create / close / switch ───────────────────────────────

    def action_new_tab(self, *, state: TState | None = None, name: str | None = None) -> str:
        """Create a new tab.

        Args:
            state: prebuilt TabState (from load_tabs or default).
            name: tab name (ignored when state is passed).

        Returns:
            tab_id.
        """
        # Creating a tab makes it active just like switching does, but
        # TabDeactivated never arrives on this path: ``tc.active = tab_id``
        # is set before the pane is in the DOM, so Textual does not post
        # TabActivated for this panel at all (verified: the
        # on_tabbed_content_tab_activated handler is never called), which means
        # the "deactivate the old one" branch never fires either. The owner never
        # learns that the previous tab stopped being active — and everything it
        # kept "per tab" outside of state (the global Intruder toolbar:
        # Threads/Delay/Turbo) stays unsaved. Hence we post it ourselves while
        # _active_tab_id still points at the old tab.
        previous_id = self._active_tab_id
        if previous_id and previous_id in self._states:
            self.post_message(self.TabDeactivated(self, previous_id, self._states[previous_id]))

        self._counter += 1
        tab_id = f"{self._tab_id_prefix}{self._counter}"
        if state is None:
            name = name or f"Tab {self._counter}"
            import uuid

            state = self._make_default_state(tab_id, name)
            state.tab_id = tab_id
            if hasattr(state, "tab_uid"):
                state.tab_uid = uuid.uuid4().hex
            if hasattr(state, "name"):
                state.name = name
        elif hasattr(state, "tab_id"):
            # A caller-supplied state comes from persistence and either has no
            # tab_id or one from a previous run. The per-tab widget ids are
            # built from ``state.tab_id`` by the owner (``_wid(tab_id, …)``), so
            # leaving it stale means the tab body mounts under a different id
            # than the one every lookup uses — the pane stays an empty
            # placeholder forever. ``tab_uid`` is the persistence key and is
            # deliberately left alone.
            state.tab_id = tab_id

        # Step 1: build the TabPane (children via *args get mounted when added).
        pane_id = getattr(state, "name", f"Tab {self._counter}")
        if self._build_tab_ui is not None:
            pane = self._build_tab_ui(state, tab_id)
            if pane is None:
                pane = TabPane(pane_id, id=tab_id)
        else:
            pane = TabPane(pane_id, id=tab_id)
        self._states[tab_id] = state
        meta = _TabMeta(tab_id=tab_id, pane=pane, name=pane_id)
        self._meta[tab_id] = meta

        try:
            tc = self.tabs_content
            # Two separate hazards, both fatal for the whole app (`NoMatches`
            # inside Textual's own callback):
            #  * `add_pane()` asks the inner `Tabs` for `#tabs-list`, which on a
            #    lazily mounted screen may not exist yet;
            #  * setting `tc.active` right after `add_pane()` makes Textual look
            #    up the ContentTab for that id before the pane's tab is mounted.
            #    Add when the strip is ready, then activate on the next frame.
            if tc.query("#tabs-list"):
                tc.add_pane(pane)
                self._activate_later(tc, tab_id)
            else:
                self._defer_add_pane(tc, pane, tab_id)
        except Exception:
            # The new tab was added to `_states`, but its pane is not in the DOM:
            # switching to it will show an empty body and the tab cannot be closed.
            logger.exception("action_new_tab setup failed for %s", tab_id)

        self._active_tab_id = tab_id

        # Build per-tab UI and notify the owner once the widget is in the DOM.
        self.call_after_refresh(self._post_tab_messages, tab_id, state)
        return tab_id

    def _set_active(self, tc: TabbedContent, tab_id: str) -> None:
        """Assign ``TabbedContent.active`` without racing the pane mount.

        Textual raises ``ValueError("No Tab with id …")`` while the pane's ``ContentTab``
        is not registered yet (``add_pane`` mounts it one pass later) and ``NoMatches``
        when the pane is already gone. Both mean "not now", so a failed assignment is
        retried on the next frame — as long as the tab still exists.
        """

        try:
            tc.active = tab_id
            return
        except (NoMatches, ValueError) as exc:
            logger.debug("tab panel: active %s postponed: %s", tab_id, exc)

        def retry() -> None:
            if tab_id not in self._states:
                return  # closed meanwhile
            try:
                tc.active = tab_id
            except (NoMatches, ValueError) as exc:
                # The state says this tab is active while another one is on screen.
                logger.warning("tab panel: tab %s never became active: %s", tab_id, exc)

        self.call_after_refresh(retry)

    def _activate_later(self, tc: TabbedContent, tab_id: str) -> None:
        """Select the tab after its content tab has been mounted.

        `TabbedContent.add_pane()` mounts the `ContentTab` asynchronously; assigning
        `active` in the same tick makes Textual resolve the content tab id before it
        exists. Depending on the Textual version that surfaces as `NoMatches`
        (`'#--content-tab-…' on ContentTabs()`) or as `ValueError('No Tab with id …')` —
        both closed the whole TUI, which is what `_set_active` now prevents.
        """

        def activate() -> None:
            if tab_id not in self._states:
                return  # closed meanwhile
            self._set_active(tc, tab_id)

        self.call_after_refresh(activate)

    def _defer_add_pane(self, tc: TabbedContent, pane: TabPane, tab_id: str, attempts: int = 5) -> None:
        """Retry `add_pane` on the next frame until the tab strip exists.

        `TabbedContent.add_pane()` asks the inner `Tabs` for `#tabs-list`, which
        is mounted one pass after the panel itself. On a lazily mounted screen the
        first tab can be created earlier than that, and Textual raised
        `NoMatches` as a fatal exception — the whole TUI went down.
        """

        def attempt() -> None:
            if tab_id not in self._states:
                return  # closed meanwhile
            if not tc.query("#tabs-list"):
                if attempts > 0:
                    self.call_after_refresh(lambda: self._defer_add_pane(tc, pane, tab_id, attempts=attempts - 1))
                else:
                    logger.error("tab panel: #tabs-list never appeared for %s", tab_id)
                return
            try:
                tc.add_pane(pane)
            except Exception:
                logger.exception("action_new_tab setup failed for %s", tab_id)
                return
            self._activate_later(tc, tab_id)

        self.call_after_refresh(attempt)

    def _post_tab_messages(self, tab_id: str, state: TState) -> None:
        """Post messages after widget is ready."""
        # If the pane was built via build_tab_ui (with children) — no mount needed.
        # Otherwise we finish building it through _mount_tab_ui.
        self._do_build_ui(tab_id, state)
        # Post the messages meant for the screen
        self.post_message(self.TabCreated(self, tab_id, state))
        self.post_message(self.TabActivated(self, tab_id, state))

    def _do_build_ui(self, tab_id: str, state: TState) -> None:
        """Mount the per-tab widgets into the TabPane (the TabPane is already in the DOM)."""
        if tab_id not in self._states:
            return
        # If the pane was already built with children via build_tab_ui — nothing to do.
        existing = self._meta[tab_id].pane if tab_id in self._meta else None
        if existing is not None and list(existing.children):
            return
        if self._mount_tab_ui:
            self._mount_tab_ui(state, tab_id)

    def _make_default_state(self, tab_id: str, name: str) -> TState:
        """Create an empty TabState (when the module did not supply one)."""
        if hasattr(self, "_default_state_factory") and self._default_state_factory is not None:
            return self._default_state_factory(tab_id, name)

        @dataclass
        class _DummyState:
            tab_id: str = ""
            name: str = ""
            template_text: str = ""

        return _DummyState(tab_id=tab_id, name=name)  # type: ignore[return-value]

    def set_default_state_factory(self, factory):
        """Set the factory used to create the default TabState."""
        self._default_state_factory = factory

    def action_close_tab(self) -> None:
        """Close the active tab (when > min_tabs)."""
        if len(self._states) <= self._min_tabs:
            return
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        state = self._states.get(tab_id)
        try:
            tc = self.tabs_content
            tc.remove_pane(tab_id)
        except NoMatches as exc:
            # The pane stays in the DOM even though it was already removed from
            # `_states` just below — the tab is visible but cannot be switched to.
            # `NoMatches` — the tab container is not in the tree (screen teardown).
            logger.debug("tab_panel: pane %s not removed: %s", tab_id, exc)
        self._states.pop(tab_id, None)
        self._meta.pop(tab_id, None)
        # Switch to last remaining tab
        if self._states:
            new_id = list(self._states.keys())[-1]
            self._active_tab_id = new_id
            try:
                tc = self.tabs_content
            except NoMatches as exc:
                # The container is not in the tree (screen leaving).
                logger.debug("tab_panel: container gone, cannot switch to %s: %s", new_id, exc)
            else:
                self._set_active(tc, new_id)
        else:
            self._active_tab_id = None
        if state is not None:
            self.post_message(self.TabClosed(self, tab_id, state))

    def switch_to(self, tab_id: str) -> None:
        """Switch to a tab by id programmatically."""
        if tab_id not in self._states:
            return
        # Deactivate old
        old_id = self._active_tab_id
        if old_id and old_id in self._states and old_id != tab_id:
            old_state = self._states[old_id]
            self.post_message(self.TabDeactivated(self, old_id, old_state))
        # Activate new
        self._active_tab_id = tab_id
        try:
            tc = self.tabs_content
        except NoMatches as exc:
            # The state considers the tab active while the screen shows the previous
            # one — edits will go to the wrong place.
            logger.debug("tab_panel: switch to %s not shown: %s", tab_id, exc)
        else:
            self._set_active(tc, tab_id)
        state = self._states.get(tab_id)
        if state is not None:
            self.post_message(self.TabActivated(self, tab_id, state))

    def get_any_tab_id(self) -> str | None:
        """Return any tab_id (for tests)."""
        if self._states:
            return next(iter(self._states))
        return None

    async def close_all(self) -> None:
        """Close all tabs (on project change).

        IMPORTANT: every remove_pane() is awaited. Previously the discard-style
        approach meant: reload_from_project calls close_all() and then
        action_new_tab() right away, and if the pane with the same id is still
        being removed from the DOM, the new add_pane with the old id failed (id
        already taken) → the header was not added, and subsequent "+" clicks drifted.
        As in Repeater: await remove_pane() — to avoid a race with action_new_tab().
        """
        for tab_id, state in list(self._states.items()):
            try:
                tc = self.tabs_content
                await tc.remove_pane(tab_id)
            except Exception as exc:
                # This is exactly the race described in the docstring above: a pane
                # that was not removed with the same id breaks the next add_pane.
                logger.debug("tab_panel: pane %s not removed in close_all: %s", tab_id, exc)
            if state is not None:
                self.post_message(self.TabClosed(self, tab_id, state))
        self._states.clear()
        self._meta.clear()
        self._counter = 0
        self._active_tab_id = None

    async def load_from_storage(self) -> None:
        """Load tabs from storage (via load_tabs)."""
        if self._load_tabs_fn is None:
            return
        try:
            states = await self._load_tabs_fn()
        except Exception:
            # The tabs did not come back from storage — the panel stays empty even
            # though the data is in the DB. Silence here = "the tabs are gone".
            logger.warning("tab_panel: tabs not loaded from storage", exc_info=True)
            return
        if not states:
            return
        for st in states:
            tab_id = getattr(st, "tab_id", "")
            if not tab_id:
                continue
            # Avoid duplicates
            existing_tab_id = self._find_by_tab_uid(st)
            if existing_tab_id:
                continue
            self.action_new_tab(state=st)

    def _find_by_tab_uid(self, state: TState) -> str | None:
        """Find a tab by tab_uid (so that no duplicate is created)."""
        uid = getattr(state, "tab_uid", None)
        if not uid:
            return None
        for tid, st in self._states.items():
            if getattr(st, "tab_uid", None) == uid:
                return tid
        return None

    # ── Rename (double-click) ───────────────────────────────────────────

    # Rename (double-click / F2) comes from TabRenameMixin: the same four handlers lived
    # here and in BaseModuleScreen, and a third time in RepeaterScreen.
    def _rename_state(self, tab_id: str) -> object | None:
        """A tab of this panel, if it has state (the mixin uses it for name + ownership)."""
        return self._states.get(tab_id)

    def _apply_tab_rename(self, tab_id: str, new_name: str) -> None:
        state = self._states.get(tab_id)
        if state is None:
            return
        if hasattr(state, "name"):
            state.name = new_name
        self._update_tab_label(tab_id, new_name)

    def _update_tab_label(self, tab_id: str, name: str) -> None:
        try:
            tc = self.tabs_content
            tab_widget = tc.get_tab(tab_id)
            if tab_widget is not None:
                tab_widget.label = name
        except Exception as exc:
            # The name changed in the state but the header still shows the old one:
            # the rename looks like it was never applied.
            logger.debug("tab_panel: label not updated for %s: %s", tab_id, exc)

    def update_tab_label(self, tab_id: str, label: str) -> None:
        """Public method to update the label (e.g. with a * dirty marker)."""
        self._update_tab_label(tab_id, label)

    # ── TabActivated (from Textual) ─────────────────────────────────────

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id != f"{self.id}-content":
            return
        pane = event.pane
        if pane is None or pane.id is None:
            return
        new_tab_id = pane.id

        # Deactivate old
        old_id = self._active_tab_id
        if old_id and old_id in self._states and old_id != new_tab_id:
            old_state = self._states.get(old_id)
            if old_state is not None:
                self.post_message(self.TabDeactivated(self, old_id, old_state))

        # Activate new
        self._active_tab_id = new_tab_id
        new_state = self._states.get(new_tab_id)
        if new_state is not None:
            self.post_message(self.TabActivated(self, new_tab_id, new_state))

    # ── Get state ───────────────────────────────────────────────────────

    def get_state(self, tab_id: str) -> TState | None:
        return self._states.get(tab_id)

    def get_tab_id_by_uid(self, tab_uid: str) -> str | None:
        """Find the tab_id by tab_uid (for DB loading)."""
        for tid, st in self._states.items():
            if getattr(st, "tab_uid", None) == tab_uid:
                return tid
        return None
