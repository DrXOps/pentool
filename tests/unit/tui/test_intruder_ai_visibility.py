"""Intruder: the AI-gated control follows the AI mode on every tab (F-022).

The Smart… payload button exists once per tab. It used to be toggled by
``self.query(".pro-locked")`` — a class query over the whole screen. Two things
were wrong with that:

* a class name that says nothing about what the control gates, and whose DOM
  contract was never defined (REPORT.md F-008/F-022);
* a tab created *after* the last ``AiModeChanged`` started with the button
  visible in every mode, because nothing re-applied visibility on mount.

The fix addresses controls by id (``btn-payload-smart-<tab_id>``) and re-applies
visibility when a tab's UI mounts. These tests pin both halves without building
the full app: they exercise the selection logic on a bare screen instance, the
same way ``test_intruder_filter_bar.py`` does.
"""

from __future__ import annotations

import types
from unittest.mock import patch

from textual.css.query import NoMatches

from pentool.tui.screens.intruder.screen import IntruderScreen


def _bare_screen(tab_ids: list[str]) -> IntruderScreen:
    """A screen with just the state ``_sync_ai_ui`` walks over."""
    screen = object.__new__(IntruderScreen)
    screen._tabs = [types.SimpleNamespace(tab_id=tab_id) for tab_id in tab_ids]
    return screen


def test_sync_covers_every_tab_by_id() -> None:
    """`_sync_ai_ui` addresses each tab's own control, never a screen-wide class."""
    screen = _bare_screen(["t-1", "t-2", "t-3"])
    seen: list[tuple[str, bool]] = []
    screen._sync_ai_ui_for_tab = lambda tab_id, ai_on: seen.append((tab_id, ai_on))  # type: ignore[method-assign]

    cfg = types.SimpleNamespace(ai_enabled=False)
    with patch("pentool.core.config.get_config", return_value=cfg):
        screen._sync_ai_ui()

    assert seen == [("t-1", False), ("t-2", False), ("t-3", False)]


def test_control_id_is_per_tab() -> None:
    """The gated control is found by ``btn-payload-smart-<tab_id>``."""
    screen = _bare_screen([])
    looked_up: list[str] = []

    class _Button:
        display = True

    def _query_one(selector: str, cls=None):
        looked_up.append(selector)
        return _Button()

    screen.query_one = _query_one  # type: ignore[method-assign]
    screen._sync_ai_ui_for_tab("abc", True)

    assert looked_up == ["#btn-payload-smart-abc"]


def test_visibility_follows_ai_mode() -> None:
    """On -> shown, off -> hidden."""
    screen = _bare_screen([])
    button = types.SimpleNamespace(display=True)
    screen.query_one = lambda *a, **k: button  # type: ignore[method-assign]

    screen._sync_ai_ui_for_tab("abc", False)
    assert button.display is False

    screen._sync_ai_ui_for_tab("abc", True)
    assert button.display is True


def test_unmounted_tab_is_skipped_not_crashing() -> None:
    """A tab being rebuilt has no control yet — that must not raise."""
    screen = _bare_screen([])

    def _raise(*_a, **_k):
        raise NoMatches("no #btn-payload-smart-abc in the DOM")

    screen.query_one = _raise  # type: ignore[method-assign]
    screen._sync_ai_ui_for_tab("abc", True)  # no exception


def test_mount_hook_reapplies_current_mode() -> None:
    """A tab mounted after the last AiModeChanged still gets the right state."""
    screen = _bare_screen([])
    seen: list[tuple[str, bool]] = []
    screen._sync_ai_ui_for_tab = lambda tab_id, ai_on: seen.append((tab_id, ai_on))  # type: ignore[method-assign]

    cfg = types.SimpleNamespace(ai_enabled=False)
    with patch("pentool.core.config.get_config", return_value=cfg):
        screen._apply_ai_visibility_after_mount("fresh-tab")

    assert seen == [("fresh-tab", False)]
