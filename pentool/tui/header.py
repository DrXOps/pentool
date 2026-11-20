"""Module header contract: what the app draws above a screen's content.

The header has two fixed levels (see `MYPLANS/plan-redesign-2026-11-20.md`):

* row 1 — the module tabs (owned by the app) and, on the right, the module's
  **state** (``○ Proxy on``, ``⏸ 2``): things the user only reads or flips;
* row 2 — the **actions of the active sub-tab** on the left, the **sub-tab chips**
  in the middle and **rare actions** (plus ``⋯``) on the right.

Screens describe that header instead of composing their own toolbar, so every
module ends up with the same shape and the same widgets. A screen without a spec
(Dashboard, for instance) simply has no second row — the app hides it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class HeaderTab:
    """One sub-tab chip, e.g. ``Intercept``."""

    id: str
    label: str


@dataclass(frozen=True)
class HeaderAction:
    """A header button. ``action`` is the id handed back to the screen."""

    action: str
    label: str
    enabled: bool = True


@dataclass(frozen=True)
class HeaderSpec:
    """Everything the app needs to draw a module's header."""

    #: Right side of row 1 — state toggles and counters, in order.
    state: tuple[HeaderAction, ...] = ()
    #: Extra read-only counters drawn after the state buttons (e.g. ``⏸ 2``).
    counters: tuple[str, ...] = ()
    #: Sub-tab chips; empty when the module has a single view.
    tabs: tuple[HeaderTab, ...] = ()
    #: Active sub-tab id (must match one of ``tabs``).
    active_tab: str = ""
    #: Actions of the active sub-tab, drawn on the left of row 2.
    actions: tuple[HeaderAction, ...] = ()
    #: Rare actions, available through the ``⋯`` menu on the right of row 2.
    more: tuple[HeaderAction, ...] = ()

    def action(self, action_id: str) -> HeaderAction | None:
        """Look the action up in the visible lists (state, actions, more)."""
        for candidate in (*self.state, *self.actions, *self.more):
            if candidate.action == action_id:
                return candidate
        return None

    def is_empty(self) -> bool:
        """True when the module has neither sub-tabs nor actions of its own."""
        return not (self.state or self.counters or self.tabs or self.actions or self.more)


@runtime_checkable
class HeaderProvider(Protocol):
    """A screen that describes its header row to the app."""

    def header_spec(self) -> HeaderSpec | None:
        """Current header description (None → the app hides the header row)."""
        ...

    def header_action(self, action_id: str) -> None:
        """A header button was pressed (state, sub-tab action or ``⋯`` item)."""
        ...

    def header_tab_selected(self, tab_id: str) -> None:
        """A sub-tab chip was clicked."""
        ...


@dataclass
class HeaderState:
    """Mutable holder used by the app to remember the last rendered spec."""

    spec: HeaderSpec | None = None
    provider: HeaderProvider | None = field(default=None)
