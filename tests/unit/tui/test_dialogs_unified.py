"""Every TUI dialog inherits ``BaseDialog``; each one can be cancelled (F-024).

Eleven dialogs were plain ``ModalScreen`` subclasses. Each copy-pasted
``align: center middle`` and a ``#dialog`` block into its own ``.tcss``, and
each reached ``dismiss()`` through its own binding form (``escape`` →
``close`` / ``cancel`` / ``dismiss(None)`` / ``dismiss_dialog``). One dialog —
``ColorPickScreen`` — had no centring rule at all and no escape binding, so it
opened in the top-left corner and could only be closed with the mouse.

``BaseDialog`` already supplies the geometry, ``action_cancel()`` and the
Escape binding. This test keeps new dialogs on that base and pins the two
properties the migration was for: the base is in the MRO, and Escape resolves
to a real action.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from textual.binding import Binding
from textual.screen import ModalScreen

import pentool
from pentool.tui.dialogs.base_dialog import BaseDialog


def _pentool_screens() -> list[type[ModalScreen]]:
    """Every ``ModalScreen`` subclass defined inside ``pentool`` (not Textual's)."""
    found: dict[str, type[ModalScreen]] = {}
    for info in pkgutil.walk_packages(pentool.__path__, "pentool."):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # pragma: no cover - optional/PRO packages
            continue
        for member in vars(module).values():
            if inspect.isclass(member) and issubclass(member, ModalScreen) and member.__module__.startswith("pentool."):
                found[member.__name__] = member
    return list(found.values())


def test_every_dialog_inherits_base_dialog() -> None:
    offenders = [
        f"{cls.__module__}.{cls.__name__}"
        for cls in _pentool_screens()
        if cls is not BaseDialog and not issubclass(cls, BaseDialog)
    ]
    assert not offenders, "dialogs must inherit BaseDialog (geometry + Escape→cancel live there):\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize("dialog", _pentool_screens(), ids=lambda c: c.__name__)
def test_dialog_escape_reaches_an_action(dialog: type[ModalScreen]) -> None:
    """Escape must be bound, and the action it names must exist on the dialog."""
    escape = [b for b in getattr(dialog, "BINDINGS", []) if isinstance(b, Binding) and b.key == "escape"]
    assert escape, f"{dialog.__name__} has no Escape binding"
    for binding in escape:
        # "cancel", "close", "dismiss_dialog", "dismiss(None)" — all valid
        # action syntax; the part before "(" is the method name.
        action = binding.action.split("(", 1)[0]
        assert hasattr(dialog, f"action_{action}") or action.startswith(
            "dismiss"
        ), f"{dialog.__name__}: Escape → {binding.action!r} names no action method"


def test_color_pick_now_centres_and_cancels() -> None:
    """The dialog that motivated the migration: it had neither rule nor binding."""
    from pentool.tui.dialogs.color_pick import ColorPickScreen

    assert issubclass(ColorPickScreen, BaseDialog)
    keys = {b.key for b in ColorPickScreen.BINDINGS if isinstance(b, Binding)}
    assert "escape" in keys, "a modal with no Escape binding can only be closed by mouse"
