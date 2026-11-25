"""TabRenameMixin — one implementation of "double-click a tab to rename it".

The audit (REPORT.md, D3) found the same behaviour written three times:
`BaseModuleScreen` (used by Intruder), `TabbedContentPanel` (used by Scanner and by
Intruder's tabs) and `RepeaterScreen`, which mounted its own input field with a
different id. The copies drifted: Repeater created the field on first use, the other two
expect it in `compose()`; the id difference already broke focus once.

The mixin owns the four event handlers and the "show the field and select its text" step.
A screen supplies three things:

* ``_rename_input_id`` — id of the input field holding the new name;
* ``_rename_state(tab_id)`` — the object whose ``name`` is edited (``None`` → not ours);
* ``_apply_tab_rename(tab_id, new_name)`` — write the name and refresh the label.

Optionally ``_rename_input_host`` — selector of a container where the field is mounted on
first use (Repeater creates it lazily; the others ship it in ``compose()``).
"""

from __future__ import annotations

from textual.css.query import NoMatches
from textual.events import Click
from textual.widgets import Input, Tab

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class TabRenameMixin:
    """Double-click (or F2) on a tab opens an inline field; Enter renames it."""

    #: Id of the rename input.
    _rename_input_id: str = "rename-input"

    #: Optional container selector: mount the field on first use instead of requiring it
    #: in `compose()`.
    _rename_input_host: str = ""

    #: Optional filters for "is this tab ours?" — prefix of the pane id and/or the
    #: id of the TabbedContent that must contain the clicked Tab.
    _rename_tab_prefix: str = ""
    _rename_tabs_widget_id: str = ""

    # ── Contract ─────────────────────────────────────────────────────────────

    def _rename_state(self, tab_id: str) -> object | None:  # pragma: no cover - contract
        raise NotImplementedError

    def _apply_tab_rename(self, tab_id: str, new_name: str) -> None:  # pragma: no cover
        raise NotImplementedError

    # ── Events ───────────────────────────────────────────────────────────────

    def on_click(self, event: Click) -> None:
        """Double-click on a Tab → rename it."""
        if event.chain < 2:
            return
        widget = event.widget
        if not isinstance(widget, Tab):
            return
        pane_id = (widget.id or "").removeprefix("--content-tab-")
        if not pane_id:
            return
        if self._rename_tab_prefix and not pane_id.startswith(self._rename_tab_prefix):
            logger.debug("tab rename: %r does not match prefix %r", pane_id, self._rename_tab_prefix)
            return
        if not self._tab_belongs_to_us(widget):
            return
        if self._rename_state(pane_id) is None:
            logger.debug("tab rename: %r has no state", pane_id)
            return
        event.stop()
        self.start_rename(pane_id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != self._rename_input_id:
            return
        tab_id = getattr(event.input, "_rename_tab_id", None)
        new_name = event.value.strip()
        event.input.display = False
        if tab_id and new_name:
            self._apply_tab_rename(tab_id, new_name)

    def on_input_blurred(self, event: Input.Blurred) -> None:
        """Hide the field when it loses focus; it must not stay on top of the tabs."""
        try:
            field = self.query_one(f"#{self._rename_input_id}", Input)
        except NoMatches as exc:
            # The field is not in the tree — nothing to hide.
            logger.debug("tab rename: input not found on blur: %s", exc)
            return
        if field.display:
            field.display = False

    # ── Implementation ───────────────────────────────────────────────────────

    def start_rename(self, tab_id: str) -> None:
        """Show the field with the current name selected (F2 and double-click both land here)."""
        state = self._rename_state(tab_id)
        if state is None:
            return
        try:
            field = self._rename_input()
            field.value = getattr(state, "name", "Tab")
            field.display = True
            field.focus()
            field.action_select_all()
            field._rename_tab_id = tab_id  # type: ignore[attr-defined]
        except Exception:
            # The field did not open: F2 on a tab does nothing, which reads as "broken
            # key". Logged with the traceback because a renamed widget id (a typo in
            # `_rename_input_id`) shows up exactly here and nowhere else.
            logger.warning("tab rename: not started for %s", tab_id, exc_info=True)

    #: Old name, kept because hotkeys, screens and tests call `_start_rename`.
    _start_rename = start_rename

    def _rename_input(self) -> Input:
        """The field, mounted into its host on first use when one is configured."""
        try:
            return self.query_one(f"#{self._rename_input_id}", Input)
        except NoMatches:
            if not self._rename_input_host:
                raise
            # classes="tab-rename" is mandatory: without it the field joins the normal
            # flow and drops to the bottom of the screen instead of overlaying the tabs.
            field = Input(
                id=self._rename_input_id,
                classes="tab-rename",
                placeholder="Tab name...",
                compact=True,
            )
            self.query_one(self._rename_input_host).mount(field)
            return field

    def _tab_belongs_to_us(self, tab: Tab) -> bool:
        """Filter by TabbedContent when one is configured (sub-tabs of other widgets)."""
        if not self._rename_tabs_widget_id:
            return True
        try:
            container = self.query_one(f"#{self._rename_tabs_widget_id}")
        except NoMatches as exc:
            logger.debug("tab rename: tabs widget %r not in tree: %s", self._rename_tabs_widget_id, exc)
            return False
        ancestor = tab.parent
        while ancestor is not None:
            if ancestor is container:
                return True
            ancestor = getattr(ancestor, "parent", None)
        logger.debug("tab rename: tab is not inside %r", self._rename_tabs_widget_id)
        return False
