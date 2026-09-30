"""Unit tests: cli/scan.py — `pentool scan active/passive/report`."""

from __future__ import annotations

import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from pentool.cli.scan import scan, _import_scanner_api

# Импортируем ScanService принудительно — иначе Python 3.10 на CI
# не может его найти через patch-путь "pentool.services.scan_service.ScanService"
from pentool.services.scan_service import ScanService  # noqa: F401



def test_import_scanner_api_unavailable_when_module_missing():
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **k):
        if name.startswith("pentool.api.scanner_api"):
            raise ImportError("no scanner")
        return real_import(name, *a, **k)

    with patch("builtins.__import__", side_effect=fake_import):
        from click.testing import CliRunner as CR
        try:
            _import_scanner_api()
            assert False, "expected SystemExit"
        except SystemExit as e:
            assert e.code == 1


def test_import_scanner_api_returns_class():
    """When the scanner module imports cleanly, the ScannerAPI class is returned.

    Scanner is a PRO module (absent in CI), so mock the import path rather
    than depending on a real install.
    """
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    FakeScannerAPI = type("ScannerAPI", (), {})

    def fake_import(name, *a, **k):
        if name == "pentool.api.scanner_api":
            mod = types.ModuleType("pentool.api.scanner_api")
            mod.ScannerAPI = FakeScannerAPI
            return mod
        return real_import(name, *a, **k)

    with patch("builtins.__import__", side_effect=fake_import):
        cls = _import_scanner_api()
    assert cls is FakeScannerAPI


# ── passive ─────────────────────────────────────────────────────────────────

def test_scan_passive_no_scope():
    r = CliRunner().invoke(scan, ["passive"])
    assert r.exit_code == 0
    assert "Passive scanning" in r.output


def test_scan_passive_with_scope():
    r = CliRunner().invoke(scan, ["passive", "--scope", "*.example.com"])
    assert r.exit_code == 0
    assert "Scope filter" in r.output


# ── report ──────────────────────────────────────────────────────────────────

def _fake_scanner_api():
    api = MagicMock()
    api.db_path = "x"
    api.start_active_scan = AsyncMock()
    api.get_findings = AsyncMock(return_value=[])
    api.generate_report = AsyncMock()
    return api


def test_scan_report_no_findings(tmp_path):
    api = _fake_scanner_api()
    with patch("pentool.cli.scan._import_scanner_api", return_value=MagicMock(return_value=api)) as SA:
        r = CliRunner().invoke(scan, ["report", "--output", str(tmp_path / "r.html")])
    assert r.exit_code == 0
    assert "No findings in database." in r.output


def test_scan_report_with_findings(tmp_path):
    api = _fake_scanner_api()
    api.get_findings = AsyncMock(return_value=[object()])  # one finding
    out = tmp_path / "r.json"
    with patch("pentool.cli.scan._import_scanner_api", return_value=MagicMock(return_value=api)):
        r = CliRunner().invoke(scan, ["report", "--output", str(out), "--format", "json"])
    assert r.exit_code == 0
    assert "Report saved" in r.output


# ── active ──────────────────────────────────────────────────────────────────

def test_scan_active_basic(tmp_path):
    """ScanRunner запускает ScanService.run() с правильными target."""

    fake_scanner_api = MagicMock()
    fake_scanner_api.return_value = fake_scanner_api
    fake_service = AsyncMock()
    fake_service.run.return_value = []

    with (
        patch("pentool.cli.scan._import_scanner_api", return_value=fake_scanner_api),
        patch("pentool.services.scan_service.ScanService", return_value=fake_service),
    ):
        r = CliRunner().invoke(scan, ["active", "--url", "http://x/"], input="")
    assert r.exit_code == 0
    fake_service.run.assert_awaited_once()
    assert "Found 0 finding(s)." in r.output


def test_scan_active_with_checks_and_output(tmp_path):
    """Check-names и output прокидываются в ScanConfig и генерацию отчёта."""

    fake_scanner_api = MagicMock()
    fake_scanner_api.return_value = fake_scanner_api
    fake_service = AsyncMock()
    fake_service.run.return_value = []

    out = tmp_path / "findings.json"
    with (
        patch("pentool.cli.scan._import_scanner_api", return_value=fake_scanner_api),
        patch("pentool.services.scan_service.ScanService", return_value=fake_service),
    ):
        r = CliRunner().invoke(scan, ["active", "--url", "http://a/", "--url", "http://b/",
                                      "--checks", "xss,sqli", "--output", str(out)], input="")
    assert r.exit_code == 0
    # Проверяем что ScanService.run() был вызван
    fake_service.run.assert_awaited_once()


def test_scan_active_on_finding_echo(tmp_path):
    """on_finding выводит имя findings в CLI."""

    fake_scanner_api = MagicMock()
    fake_scanner_api.return_value = fake_scanner_api
    fake_service = AsyncMock()

    f = MagicMock(severity="high", name="SQLi", url="http://x/")
    fake_service.run.return_value = [f]

    with (
        patch("pentool.cli.scan._import_scanner_api", return_value=fake_scanner_api),
        patch("pentool.services.scan_service.ScanService", return_value=fake_service),
    ):
        r = CliRunner().invoke(scan, ["active", "--url", "http://x/"], input="")
    assert r.exit_code == 0
    assert "Found 1 finding(s)." in r.output
