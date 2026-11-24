"""The 14-day trial must be reachable from the interface, not only from the server.

Context: `pentool.core.license.start_trial()` existed since the licence service was
written but nothing ever called it. The site, the README and the "Scanner is a PRO
feature" screen pointed users at `pentool license trial` — a command the CLI does not
have — so the trial was, in practice, unobtainable. These tests pin the button, the
worker and the two outcomes (issued / already used).
"""

from __future__ import annotations

import inspect

import pytest

from pentool.core.license import LicenseInfo
from pentool.tui.screens.settings.screen import SettingsScreen


class _FakeApp:
    def __init__(self) -> None:
        self.notes: list[str] = []
        self.tab_lock_refreshes = 0

    def notify(self, message: str, severity: str = "information", timeout: float | None = None) -> None:
        self.notes.append(message)

    def _refresh_tab_locks(self) -> None:
        self.tab_lock_refreshes += 1


class _FakeScreen:
    """The minimum SettingsScreen needs: app.notify, err and a UI refresh."""

    def __init__(self) -> None:
        self.app = _FakeApp()
        self.refreshed = 0
        self.errors: list[tuple[str, str]] = []

    def call_after_refresh(self, callback) -> None:  # noqa: ANN001 - Textual API
        callback()

    def _refresh_license_ui(self) -> None:
        self.refreshed += 1

    def err(self, exc: Exception, title: str = "") -> None:
        self.errors.append((title, str(exc)))


def test_trial_button_is_declared_in_the_license_pane() -> None:
    source = inspect.getsource(SettingsScreen.compose)
    assert "btn-license-trial" in source, "the trial has no button in Settings → License"
    assert "Start 14-day trial" in source


def test_trial_button_has_a_handler() -> None:
    handler = getattr(SettingsScreen, "on_btn_license_trial", None)
    assert handler is not None, "the trial button posts Pressed but nothing handles it"
    assert "#btn-license-trial" in inspect.getsource(handler)
    assert hasattr(SettingsScreen, "_do_start_trial")
    assert hasattr(SettingsScreen, "_async_start_trial")


@pytest.mark.asyncio
async def test_trial_worker_reports_success_and_unlocks_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    issued = LicenseInfo(
        valid=True,
        plan="pro",
        features=["scanner_pro", "ai_discovery"],
        expires="2026-12-09",
        machine_id="machine-1",
        license_key="PTOOL-TEST-TEST-TEST",
    )

    async def fake_start_trial() -> LicenseInfo:
        return issued

    monkeypatch.setattr("pentool.core.license.start_trial", fake_start_trial)
    monkeypatch.setattr("pentool.core.license.get_session_license", lambda: LicenseInfo())
    monkeypatch.setattr("pentool.core.license.refresh_session_license", lambda info=None: None)

    screen = _FakeScreen()
    await SettingsScreen._async_start_trial(screen)

    assert not screen.errors, screen.errors
    assert any("Trial started" in note for note in screen.app.notes), screen.app.notes
    assert any("14 days" in note for note in screen.app.notes)
    assert screen.app.tab_lock_refreshes == 1, "the PRO tabs must be re-checked after a trial"
    assert screen.refreshed == 1


@pytest.mark.asyncio
async def test_trial_worker_shows_the_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_start_trial() -> LicenseInfo:
        return LicenseInfo(valid=False, plan="free", machine_id="machine-1", error="trial already used")

    monkeypatch.setattr("pentool.core.license.start_trial", fake_start_trial)
    monkeypatch.setattr("pentool.core.license.get_session_license", lambda: LicenseInfo())
    monkeypatch.setattr("pentool.core.license.refresh_session_license", lambda info=None: None)

    screen = _FakeScreen()
    await SettingsScreen._async_start_trial(screen)

    assert screen.errors, "a failed trial must be reported, not swallowed"
    assert "trial already used" in screen.errors[0][1]
    assert screen.refreshed == 1


@pytest.mark.asyncio
async def test_trial_is_not_requested_when_pro_is_already_active(monkeypatch: pytest.MonkeyPatch) -> None:
    started = False

    async def fake_start_trial() -> LicenseInfo:
        nonlocal started
        started = True
        return LicenseInfo(valid=True, plan="pro")

    monkeypatch.setattr("pentool.core.license.start_trial", fake_start_trial)
    monkeypatch.setattr(
        "pentool.core.license.get_session_license",
        lambda: LicenseInfo(valid=True, plan="pro", features=["scanner_pro"]),
    )

    screen = _FakeScreen()
    await SettingsScreen._async_start_trial(screen)

    assert started is False, "the server allows one trial per machine — do not spend it blindly"
    assert any("already active" in note for note in screen.app.notes)


def test_trial_mentions_no_cli_command_that_does_not_exist() -> None:
    """The old texts sent users to `pentool license trial`; the CLI has no such group."""
    from pentool.tui.screens.scanner_unavailable import ScannerUnavailableScreen

    text = inspect.getsource(ScannerUnavailableScreen.compose) + inspect.getsource(SettingsScreen.compose)
    assert "pentool license" not in text
    # Sanity: the placeholder screen still tells the user where the trial lives.
    assert "14-day trial" in text or "Start 14-day trial" in text
