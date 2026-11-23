"""Isolation for TUI screen tests.

Screens get the project database path via `AppMixin._get_db_path()`, that is, from
the machine configuration (`~/.config/pentool/pentool.db`). Without isolation a
UNIT-test run writes into the real project history: for example, `Repeater.on_mount`
restores tabs, and autosave then stores them back, and after such a run the user
ends up with tabs he never created.

Here the path is diverted into the void: `""` for screens means "there is no
database", and they work on the default tab. Tests that need a real schema set
their own path (`tmp_path`) and override this substitution — see
`test_repeater_tab_state_survives.py`.
"""

from __future__ import annotations

import pytest

from pentool.tui.mixins.app_mixin import AppMixin


@pytest.fixture(autouse=True)
def _no_project_database(monkeypatch):
    monkeypatch.setattr(AppMixin, "_get_db_path", lambda _self: "")
