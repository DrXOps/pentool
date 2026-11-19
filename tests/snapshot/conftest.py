"""Snapshot suite: deterministic environment.

Two sources of nondeterminism were found (2026-11-19):

1. **Wall-clock timers.** Blinking indicators and cursor blink are driven by
   `time.monotonic()`, so two runs of the same screen produced different
   baselines. Widgets consult ``PENTOOL_SNAPSHOT=1`` and stop their timers; the
   flag is set here, before any app is created.

2. **Leaked project database.** Screens resolve the project DB through
   `AppMixin._get_db_path()`, i.e. the real `~/.config/pentool/pentool.db`.
   Autosave workers from one test then left tabs behind for the next one, and
   the same test passed alone but failed inside the suite. The path is redirected
   to "no database" here, exactly as `tests/unit/tui/conftest.py` does.
"""

from __future__ import annotations

import os

import pytest

from pentool.tui.mixins.app_mixin import AppMixin

os.environ["PENTOOL_SNAPSHOT"] = "1"


@pytest.fixture(autouse=True)
def _no_project_database(monkeypatch):
    """Screens must not read or write the user's real project DB."""
    monkeypatch.setattr(AppMixin, "_get_db_path", lambda _self: "")
