"""`pentool license` — the commands the docs claimed for months.

The regression these tests guard against is not "a wrong string": the group existed in
name only. Activation was reachable from the TUI and nowhere else, while the site, the
README and the PRO screens told users to run `pentool license activate`. Everything here
runs through CliRunner, i.e. exactly the path a user takes.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pentool.cli import license_cmd
from pentool.cli.main import cli
from pentool.core.license import LicenseInfo

PRO = LicenseInfo(
    valid=True,
    plan="pro",
    features=["scanner_pro", "ai_discovery"],
    expires="2026-12-09",
    machine_id="m-1",
    license_key="PTOOL-AAAA-BBBB-CCCC",
)


def _invoke(*args: str):
    return CliRunner().invoke(cli, ["license", *args])


def _output(result) -> str:
    return result.output + (getattr(result, "stderr", "") or "")


def test_group_is_reachable_from_the_root_cli() -> None:
    assert "license" in cli.commands
    result = _invoke("--help")
    assert result.exit_code == 0
    for command in ("activate", "deactivate", "status", "trial"):
        assert command in result.output


def test_status_free_licence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(license_cmd, "get_session_license", lambda: LicenseInfo())
    monkeypatch.setattr(license_cmd, "get_machine_id", lambda: "machine-42")

    result = _invoke("status")

    assert result.exit_code == 0
    assert "FREE" in result.output
    assert "pentool license activate" in result.output
    assert "pentool license trial" in result.output


def test_status_json_is_machine_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(license_cmd, "get_session_license", lambda: PRO)
    monkeypatch.setattr(license_cmd, "get_machine_id", lambda: "machine-42")

    result = _invoke("status", "--json")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["plan"] == "pro"
    assert payload["expires_at"] == "2026-12-09"
    assert payload["features"] == ["scanner_pro", "ai_discovery"]
    assert payload["machine_id"] == "machine-42"
    # The full key must never be printed — it is the licence itself.
    assert payload["key"] != PRO.license_key
    assert "…" in payload["key"]


def test_activate_reports_success_and_the_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_activate(key: str) -> LicenseInfo:
        assert key == "PTOOL-AAAA-BBBB-CCCC"
        return PRO

    monkeypatch.setattr(license_cmd, "activate_license", fake_activate)
    monkeypatch.setattr(license_cmd, "get_machine_id", lambda: "machine-42")

    result = _invoke("activate", PRO.license_key)

    assert result.exit_code == 0
    assert "PRO" in result.output
    assert "Restart Pentool" in result.output


def test_activate_failure_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_activate(key: str) -> LicenseInfo:
        return LicenseInfo(valid=False, plan="free", error="key not found")

    monkeypatch.setattr(license_cmd, "activate_license", fake_activate)

    result = _invoke("activate", "PTOOL-NOPE")

    assert result.exit_code == license_cmd.EXIT_FAILED
    assert "key not found" in _output(result)


def test_activate_slots_in_use_points_at_reassign(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_activate(key: str) -> LicenseInfo:
        return LicenseInfo(valid=False, plan="free", error="all slots in use (3/3)")

    monkeypatch.setattr(license_cmd, "activate_license", fake_activate)

    result = _invoke("activate", "PTOOL-AAAA-BBBB-CCCC")

    assert result.exit_code == license_cmd.EXIT_FAILED
    assert "--reassign" in _output(result)


def test_activate_reassign_flag_calls_reassign(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def fake_reassign(key: str) -> LicenseInfo:
        called.append(key)
        return PRO

    async def fake_activate(key: str) -> LicenseInfo:  # pragma: no cover - must not run
        raise AssertionError("activate must not be used with --reassign")

    monkeypatch.setattr(license_cmd, "reassign_license", fake_reassign)
    monkeypatch.setattr(license_cmd, "activate_license", fake_activate)
    monkeypatch.setattr(license_cmd, "get_machine_id", lambda: "machine-42")

    result = _invoke("activate", "--reassign", PRO.license_key)

    assert result.exit_code == 0
    assert called == [PRO.license_key]


def test_trial_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_trial() -> LicenseInfo:
        return PRO

    monkeypatch.setattr(license_cmd, "start_trial", fake_trial)
    monkeypatch.setattr(license_cmd, "get_machine_id", lambda: "machine-42")

    result = _invoke("trial")

    assert result.exit_code == 0
    assert "Trial started" in result.output
    assert "14 days" in result.output


def test_trial_already_used(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_trial() -> LicenseInfo:
        return LicenseInfo(valid=False, plan="free", error="trial already used on this machine")

    monkeypatch.setattr(license_cmd, "start_trial", fake_trial)

    result = _invoke("trial")

    assert result.exit_code == license_cmd.EXIT_FAILED
    assert "trial already used" in _output(result)


def test_deactivate_calls_the_core_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_deactivate() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(license_cmd, "deactivate_license", fake_deactivate)

    result = _invoke("deactivate")

    assert result.exit_code == 0
    assert called is True
    assert "slot is free" in result.output


def test_deactivate_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_deactivate() -> None:
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(license_cmd, "deactivate_license", fake_deactivate)

    result = _invoke("deactivate")

    assert result.exit_code == license_cmd.EXIT_FAILED
    assert "server unreachable" in _output(result)
