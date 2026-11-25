"""Forwarding fields for the active Intruder tab.

`IntruderScreen` keeps per-tab state in `_IntruderTabState` objects, but a lot of code
(handlers, tests, the attack runner) reads and writes it as if it lived on the screen.
That produced eight identical `@property`/`@setter` pairs — same body, different attribute
name — which is both noise and a place where a default could quietly diverge.

One descriptor replaces them:

    _attack_type = _ActiveTabField("attack_type", AttackType.SNIPER)

The default is a value or a factory: pass ``list``/``int``/``bool`` for mutable or
zero values so every read gets a fresh one (a shared default list would leak between
tabs), or a constant such as ``None``/an enum member.
"""

from __future__ import annotations

from typing import Any


class _ActiveTabField:
    """Read/write an attribute of the active tab; fall back to a default when there is none."""

    def __init__(self, attribute: str, default: Any) -> None:
        self._attribute = attribute
        self._default = default

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        tab = instance._active_tab
        if tab is None:
            return self._default() if callable(self._default) else self._default
        return getattr(tab, self._attribute)

    def __set__(self, instance: Any, value: Any) -> None:
        tab = instance._active_tab
        if tab is not None:
            setattr(tab, self._attribute, value)
