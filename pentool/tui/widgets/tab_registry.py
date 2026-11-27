"""Document-tab bookkeeping as its own object (step 11).

Scanner and Repeater used to keep a document-tab list inside the screen (Plus tab id bookkeeping,
active tab, persistence). This object owns that half: "which tabs exist, which is active, what
happens when one is added/closed/renamed". Repeater reads and writes through it now; the widget it
drives is still a plain `TabbedContent` until the screens move to `TabbedContentPanel`.
"""

from __future__ import annotations

from typing import Generic, TypeVar

TState = TypeVar("TState")


class TabRegistry(Generic[TState]):
    """Ordered document tabs with an active id — the state half of a tabbed screen.

    Deliberately free of Textual: screens own widgets, this owns bookkeeping, so it can be
    extracted and tested before any widget changes.
    """

    def __init__(self) -> None:
        self._states: dict[str, TState] = {}
        self._active: str | None = None

    # ── queries ───────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._states)

    def __contains__(self, tab_id: object) -> bool:
        return tab_id in self._states

    @property
    def ids(self) -> list[str]:
        """Tab ids in insertion order (the order the tabs are shown)."""
        return list(self._states)

    @property
    def states(self) -> list[TState]:
        """States in the same order as `ids` — the read-only view screens iterate."""
        return list(self._states.values())

    @property
    def active_id(self) -> str | None:
        return self._active

    def get(self, tab_id: str) -> TState | None:
        return self._states.get(tab_id)

    @property
    def active(self) -> TState | None:
        return self._states.get(self._active) if self._active else None

    # ── mutations ─────────────────────────────────────────────────────────

    def add(self, tab_id: str, state: TState, *, activate: bool = True) -> None:
        """Append a tab; a new tab becomes active unless told otherwise."""
        if tab_id in self._states:
            raise ValueError(f"tab {tab_id!r} already exists")
        self._states[tab_id] = state
        if activate or self._active is None:
            self._active = tab_id

    def activate(self, tab_id: str) -> TState:
        if tab_id not in self._states:
            raise KeyError(f"tab {tab_id!r} does not exist")
        self._active = tab_id
        return self._states[tab_id]

    def close(self, tab_id: str) -> TState | None:
        """Remove a tab; the active one hands over to its next tab, else to the previous.

        "Next, else previous" is Textual's own rule when the active tab is removed
        (`Tabs.remove_tab`): the user sees the tab to the right become active, or the left one
        when the closed tab was last. Returns the removed state (the screen needs it for the
        "tab closed" notification) or ``None`` when the id is unknown. The last remaining tab
        cannot be closed by the registry: the owner of the screen decides whether an empty
        screen is allowed.
        """
        ids = self.ids
        state = self._states.pop(tab_id, None)
        if state is None:
            return None
        if self._active == tab_id:
            idx = ids.index(tab_id)
            remaining = self.ids
            self._active = remaining[min(idx, len(remaining) - 1)] if remaining else None
        return state

    def rename(self, tab_id: str, name: str) -> TState | None:
        """Write the display name into the state when it carries one."""
        state = self._states.get(tab_id)
        if state is None:
            return None
        if hasattr(state, "name"):
            state.name = name  # type: ignore[attr-defined]
        return state

    def replace_all(self, pairs: list[tuple[str, TState]], *, active: str | None = None) -> None:
        """Load a whole set (project restore) and pick the active tab."""
        self._states = dict(pairs)
        self._active = active if active in self._states else (self.ids[-1] if self._states else None)
