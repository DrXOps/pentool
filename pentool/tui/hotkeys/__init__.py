"""Hotkey system for Pentool TUI.

Centralised hotkey registry that replaces ad-hoc BINDINGS / on_key spread
across screens.  Every screen registers its actions at mount() time; the
registry produces Binding lists for Textual, handles key rebinding without
restart, and controls which keys are shown in the Footer.

Usage in a Screen::

    from pentool.tui.hotkeys import registry, get_group_bindings_map

    class MyScreen(Screen):
        BINDINGS = []  # placeholder, filled in on_mount

        def on_mount(self) -> None:
            registry.register("myscreen", [
                HotkeyEntry("ctrl+r", "send_to_repeater", "Send to Repeater"),
            ])
            self._bindings = get_group_bindings_map("myscreen")

Typical flow:
  1. App boots → ``init_hotkeys()`` loads defaults.
  2. Each Screen mounts → ``registry.register(group, entries)``.
  3. App Footer picks up ``show=True`` entries automatically.
  4. User rebinds in Settings → ``registry.rebind(action, new_keys)`` →
     all screens with that action refresh bindings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
        group: Logical group (``"global"``, ``"proxy"``, …).  Used to
            isolate bindings per screen.
        show: Whether the entry appears in the Footer.
        priority: ``True`` means the binding fires even if a child widget
            has focus and would normally consume the key.
        keychain: For multi-key sequences like ``"P,h"`` (shift+P then h).
    """

    keys: str
    action: str
    description: str
    group: str = "global"
    show: bool = True
    priority: bool = False
    keychain: str | None = None

    def to_binding(self) -> Binding:
        return Binding(
            key=self.keys,
            action=self.action,
            description=self.description,
            show=self.show,
            priority=self.priority,
        )

    def to_bindings_map(self) -> BindingsMap:
        """Build a ``BindingsMap`` from a single entry."""
        from textual.binding import BindingsMap as _BM
        bm = _BM()
        bm.bind(self.keys, self.action, self.description,
                show=self.show, priority=self.priority)
        return bm


class HotkeyRegistry:
    """Central registry of all hotkeys in the application.

    Screens register their own keybindings at mount time.  The App Footer
    reads ``get_all_bindings(show_only=True)`` to display the active keys.
    """

    _instance: ClassVar[HotkeyRegistry | None] = None

    def __init__(self) -> None:
        self._entries: dict[str, list[HotkeyEntry]] = {}
        self._action_index: dict[str, HotkeyEntry] = {}  # action → entry

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
        """Register *entries* under *group*.

        Later registrations of the same action within the same group
        **replace** earlier ones (for runtime rebinding).
        """
        existing = {e.action for e in self._entries.get(group, ())}
        # Remove stale action index entries for this group's old entries
        for old in self._entries.get(group, ()):
            self._action_index.pop(old.action, None)

        self._entries[group] = list(entries)
        for e in entries:
            self._action_index[e.action] = e

    def get_entries(self, group: str) -> list[HotkeyEntry]:
        """Return registered entries for *group* (empty list if unknown)."""
        return self._entries.get(group, [])

    def get_all_entries(self) -> list[HotkeyEntry]:
        """Return every registered entry across all groups."""
        result: list[HotkeyEntry] = []
        for entries in self._entries.values():
            result.extend(entries)
        return result

    # ------------------------------------------------------------------
    # Binding production for Textual
    def get_bindings(self, group: str) -> list[Binding]:
        """Return Binding list for a specific group (e.g. for a Screen)."""
        return [e.to_binding() for e in self._entries.get(group, ())]

    def get_all_bindings(self, show_only: bool = False) -> list[Binding]:
        """Return Binding list for all groups.

        If *show_only* is ``True``, only entries with ``show=True`` are
        returned (suitable for the App Footer / help overlay).
        """
        result: list[Binding] = []
        for entries in self._entries.values():
            for e in entries:
                if show_only and not e.show:
                    continue
                result.append(e.to_binding())
        return result

    # ------------------------------------------------------------------
    # Runtime rebinding
    def rebind(self, action: str, new_keys: str) -> HotkeyEntry | None:
        """Change the key(s) for *action* across all groups.

        Returns the updated ``HotkeyEntry``, or ``None`` if *action* was
        never registered.
        """
        entry = self._action_index.get(action)
        if entry is None:
            return None

        updated = HotkeyEntry(
            keys=new_keys,
            action=entry.action,
            description=entry.description,
            group=entry.group,
            show=entry.show,
            priority=entry.priority,
            keychain=entry.keychain,
        )
        # Replace in the group list
        group_entries = self._entries[entry.group]
        for i, e in enumerate(group_entries):
            if e.action == action:
                group_entries[i] = updated
                break
        self._action_index[action] = updated
        return updated

    def set_show(self, action: str, show: bool) -> None:
        """Toggle visibility of *action* in the Footer."""
        entry = self._action_index.get(action)
        if entry is None:
            return
        updated = HotkeyEntry(
            keys=entry.keys,
            action=entry.action,
            description=entry.description,
            group=entry.group,
            show=show,
            priority=entry.priority,
            keychain=entry.keychain,
        )
        group_entries = self._entries[entry.group]
        for i, e in enumerate(group_entries):
            if e.action == action:
                group_entries[i] = updated
                break
        self._action_index[action] = updated

    def get_by_action(self, action: str) -> HotkeyEntry | None:
        """Lookup a single entry by action name."""
        return self._action_index.get(action)


# ── Module-level helpers ─────────────────────────────────────────────────


def build_bindings_map(bindings: list[Binding]) -> BindingsMap:
    """Convert a list of Binding objects into a BindingsMap.

    Textual's ``_bindings`` attribute must be a ``BindingsMap`` for the
    Footer to resolve active bindings correctly.
    """
    bm = BindingsMap()
    for b in bindings:
        bm.bind(b.key, b.action, b.description or "",
                show=b.show, priority=b.priority)
    return bm


def get_group_bindings_map(group: str) -> BindingsMap:
    """Convenience: build a BindingsMap for a single registered group."""
    return build_bindings_map(registry.get_bindings(group))


# Module-level convenience
registry = HotkeyRegistry.get_instance()