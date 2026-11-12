"""Hotkey system for Pentool TUI.

One table for every keybinding in the application. ``defaults.py`` fills it at
import time; two consumers read it:

* the screens, which take ``BINDINGS = PROXY_BINDINGS`` and friends — the lists
  Textual dispatches;
* the hint bars, which render ``[Global]`` and ``[InModule]`` from
  ``registry.get_entries(group)``.

Usage::

    from pentool.tui.hotkeys.defaults import PROXY_BINDINGS

    class ProxyScreen(Widget):
        BINDINGS = PROXY_BINDINGS

To add a hotkey, edit ``defaults.py``: the entry belongs to a group, and the
screen's ``BINDINGS`` and both hint bars follow from that one edit. Spelled key
names are checked against Textual's own parser by
``tests/unit/tui/test_hotkey_keys_are_reachable.py`` — ``ctrl-at`` looks fine
and never fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.binding import Binding, BindingsMap


@dataclass(frozen=True)
class HotkeyEntry:
    """One hotkey binding.

    Attributes:
        keys: Key combination (e.g. ``"ctrl+r"``, ``"escape"``).
        action: Action name (e.g. ``"send_to_repeater"``).  Textual calls
            ``action_<name>`` on the Screen/App that owns the binding.
        description: Human-readable label for the Footer / help screen.
        show: Whether the entry appears in the Footer.
        priority: ``True`` means the binding fires even if a child widget
            has focus and would normally consume the key.

    There is no ``group`` field: the registry stores the group as the key
    (``registry.register("proxy", …)``), and a copy on the entry could only
    drift from it — it did, every non-global entry used to claim ``"global"``.
    """

    keys: str
    action: str
    description: str
    show: bool = True
    priority: bool = False

    def to_binding(self) -> Binding:
        return Binding(
            key=self.keys,
            action=self.action,
            description=self.description,
            show=self.show,
            priority=self.priority,
        )


class HotkeyRegistry:
    """The hotkey table, indexed by group.

    Two readers, both of them real:

    * ``defaults.py`` registers every group at import time, and builds the
      ``BINDINGS`` lists Textual actually dispatches;
    * the hint bars (``widgets/keyhintbar.py``) read ``get_entries`` to render
      the ``[Global]`` and ``[InModule]`` lines.

    It used to carry a second half — ``rebind``/``set_show``/``get_by_action``
    and an action index — for a «hotkeys are configurable» feature that was
    never built. Nothing called any of it, and the Settings → Hotkeys tab
    edited a private dict of its own rather than the registry (F-035). Rebind
    is a real feature with real design questions (what persists, when the
    mounted screens refresh); when it is built it can bring its own API.
    """

    _instance: ClassVar[HotkeyRegistry | None] = None

    def __init__(self) -> None:
        self._entries: dict[str, list[HotkeyEntry]] = {}

    # ------------------------------------------------------------------
    # Singleton
    @classmethod
    def get_instance(cls) -> HotkeyRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    def register(self, group: str, entries: list[HotkeyEntry]) -> None:
        """Register *entries* under *group*, replacing that group wholesale."""
        self._entries[group] = list(entries)

    def get_entries(self, group: str) -> list[HotkeyEntry]:
        """Return registered entries for *group* (empty list if unknown)."""
        return self._entries.get(group, [])

    def groups(self) -> list[str]:
        """Registered group names, in registration order.

        ``defaults.py`` registers the module groups in the order of the module
        switcher, so readers get a presentable order for free. Anything that
        lists hotkeys asks the registry instead of keeping its own tuple of
        group names — a hand-kept copy is how a new screen loses its entries.
        """
        return list(self._entries)


# ── Module-level helpers ─────────────────────────────────────────────────


def build_bindings_map(bindings: list[Binding]) -> BindingsMap:
    """Convert a list of Binding objects into a BindingsMap.

    Textual's ``_bindings`` attribute must be a ``BindingsMap`` for the
    Footer to resolve active bindings correctly.
    """
    bm = BindingsMap()
    for b in bindings:
        bm.bind(b.key, b.action, b.description or "", show=b.show, priority=b.priority)
    return bm


def build_status_bar_markup(entries: list[HotkeyEntry]) -> str:
    """Generate status-bar text from hotkey entries.

    Returns a Rich-markup string (e.g. ``"Ctrl+R: Repeater  │  Ctrl+U: Copy URL"``)
    for entries where ``show=True``, sorted by key length (longer combos first
    so ``Ctrl+Enter`` sorts before ``C``).
    """
    shown = [e for e in entries if e.show and e.description]
    if not shown:
        return ""

    def _render(e: HotkeyEntry) -> str:
        key_label = e.keys.replace("ctrl", "Ctrl").replace("escape", "Esc")
        return f"[bold]{key_label}[/]: {e.description}"

    shown.sort(key=lambda e: (-len(e.keys), e.keys))
    return "  │  ".join(_render(e) for e in shown)


# Module-level convenience
registry = HotkeyRegistry.get_instance()
