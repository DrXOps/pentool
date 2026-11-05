"""Fixtures for the scanner-module unit tests.

Every check in `pentool.modules.scanner.checks` is a PRO feature by default
(`BaseCheck.required_feature = "scanner_pro"`), and `ScanEngine` filters
unavailable checks out of `run_active_on_requests()` via `is_available()`.
The root `tests/conftest.py::_pin_clean_session_license` resets the
process-global license cache to `None` (free) before every test, so any
engine-integration test here that does not grant a license itself sees zero
active checks and silently asserts against an empty findings list.

History: the twelve files covering these checks used to each carry a local
autouse fixture setting the license; commit 7d90ff9 removed them as
"duplicates" of the root fixture — which resets to free and therefore is not
the same thing — leaving eleven engine-integration tests silently dead.
Pin the license once, at directory scope, instead of re-copying the same
fixture into every file that needs it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _scanner_pro_trial_license(_pin_clean_session_license):
    """Grant the scanner PRO trial for every test in this directory.

    Depends explicitly on the root `_pin_clean_session_license` fixture so
    the ordering is guaranteed: the root fixture resets the cache to free
    first, then this one sets the trial on top of it.

    `scanner_pro` is exactly what a real trial license carries. Checks that
    need a narrower feature (e.g. `SQLiUnionCheck` → "scanner_sqli_union")
    still grant it themselves — that gate is the behaviour under test there.
    """
    import pentool.core.license as lic_mod

    saved = lic_mod._session_license
    lic_mod._session_license = lic_mod.LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])
    yield
    lic_mod._session_license = saved
