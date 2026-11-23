"""A paid license check does not open access when it fails (ADR-6).

`_switch_to` blocks Scanner and Recon without a license. Both handlers were
written "so that it does not crash": `except Exception: pass` — and that turned
a license read failure into permission. An error in the check opened a paid module.

The opposite is pinned down here: if we could not verify it, we do not let you
in, and the user is told why. A `pass` instead of `notify` would have restored
the old behaviour silently, and that is exactly the class of defects the audit
is cleaning out.

Why the test lives in unit and not e2e: it does not check keys and layout, only
the access decision. Key handling lives in `tests/e2e/test_navigation.py`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp
from pentool.tui.screen_registry import get_screen_class


async def _attempt_switch(module_id: str, app: PentoolApp) -> tuple[str | None, list[str]]:
    """Switch the module and return (what became active, notification texts)."""
    notes: list[str] = []
    original_notify = app.notify

    def _capture(message, **kwargs):
        notes.append(str(message))
        return original_notify(message, **kwargs)

    app.notify = _capture  # type: ignore[method-assign]
    app._switch_to(module_id)
    return app.query_one(ContentSwitcher).current, notes


@pytest.mark.parametrize(
    ("module_id", "screen_id"),
    [
        ("scanner", "screen-scanner"),
        pytest.param(
            "recon",
            "screen-recon",
            marks=pytest.mark.skipif(
                # Ask the getter, not the dict: the PRO screen is registered
                # lazily, and `"recon" in SCREEN_MAP` before the first access
                # gives False even when PRO is installed — the test skipped for nothing.
                get_screen_class("recon") is None,
                reason="Recon живёт в pro-сабмодуле; без него гейт недостижим (_switch_to выходит раньше)",
            ),
        ),
    ],
)
class TestBrokenLicenseCheckDoesNotGrantAccess:
    async def test_a_raising_license_check_blocks_the_module(self, module_id: str, screen_id: str) -> None:
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            with patch(
                "pentool.core.license.get_session_license",
                side_effect=RuntimeError("license file unreadable"),
            ):
                current, notes = await _attempt_switch(module_id, app)
            await pilot.pause()

        assert current != screen_id, (
            f"{module_id} opened although the license check raised — "
            "the handler fails open, and a broken license file becomes a free pass"
        )
        assert any("could not verify the license" in n for n in notes), (
            f"access was denied but the user was not told why; notifications: {notes!r}"
        )

    async def test_an_invalid_license_blocks_the_module(self, module_id: str, screen_id: str) -> None:
        """Control: a plain refusal (no license) still closes the module."""
        from pentool.core.license import LicenseInfo

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            with patch(
                "pentool.core.license.get_session_license",
                return_value=LicenseInfo(valid=False),
            ):
                current, _notes = await _attempt_switch(module_id, app)
            await pilot.pause()

        assert current != screen_id
