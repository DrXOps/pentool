"""Widget ID constants for TUI — single source of truth for string identifiers.

Only identifiers that are *imported* live here. The file used to hold 61 names,
53 of which were never imported anywhere: the screens wrote their ids as
literals, so the constant was decoration and could not catch a typo, a
duplicate id or a dead CSS selector (REPORT.md F-007/F-006/F-008).

Rule: a constant is added here when a second module needs it (a screen id is
referenced from ``app.py``, a mixin or the PRO plugin). Ids used inside exactly
one screen stay as literals next to the widget they name — a constant that only
its own module reads adds indirection, not safety.

``tests/unit/tui/test_constants_are_used.py`` enforces this: every constant
must be imported somewhere, otherwise it is rotting again.
"""

from __future__ import annotations

SCREEN_PROXY = "#screen-proxy"
SCREEN_REPEATER = "#screen-repeater"
SCREEN_INTRUDER = "#screen-intruder"
SCREEN_SCANNER = "#screen-scanner"
SCREEN_TARGET = "#screen-target"
SCREEN_DECODER = "#screen-decoder"
SCREEN_COMPARER = "#screen-comparer"
SCREEN_DASHBOARD = "#screen-dashboard"
