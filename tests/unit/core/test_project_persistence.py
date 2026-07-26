"""Unit tests for core/project.py and API export/import_project_data."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pentool.core.project import load_project, save_project


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ── save_project ───────────────────────────────────────────────────────────────

class TestSaveProject:
    def test_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        save_project(p, {"proxy": {"scope": []}})
        assert p.exists()

    def test_saved_at_present(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        save_project(p, {})
        data = json.loads(p.read_text())
        assert "saved_at" in data

    def test_payload_preserved(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        save_project(p, {"scanner": {"findings": [{"id": "abc"}]}})
        data = json.loads(p.read_text())
        assert data["scanner"]["findings"][0]["id"] == "abc"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "deep" / "dir" / "proj.json"
        save_project(p, {})
        assert p.exists()

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        save_project(p, {"v": 1})
        save_project(p, {"v": 2})
        data = json.loads(p.read_text())
        assert data["v"] == 2


# ── load_project ───────────────────────────────────────────────────────────────

class TestLoadProject:
    def test_load_valid(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        _write_json(p, {"scanner": {"findings": []}})
        data, err = load_project(p)
        assert err == ""
        assert "scanner" in data

    def test_file_not_found(self, tmp_path: Path) -> None:
        data, err = load_project(tmp_path / "missing.json")
        assert data == {}
        assert "not found" in err.lower()

    def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON", encoding="utf-8")
        data, err = load_project(p)
        assert data == {}
        assert "parse error" in err.lower()

    def test_load_roundtrip(self, tmp_path: Path) -> None:
        p = tmp_path / "proj.json"
        original = {
            "proxy": {"scope": ["a.com"], "match_replace": []},
            "http_history": [],
            "scanner": {"findings": [{"id": "x", "type": "sqli", "name": "N",
                                       "url": "http://a.com", "severity": "high"}]},
            "intruder": {"results": []},
            "spider": {"sessions": []},
            "target": {"sitemap": {}},
        }
        save_project(p, original)
        data, err = load_project(p)
        assert err == ""
        assert data["scanner"]["findings"][0]["id"] == "x"
        assert data["proxy"]["scope"] == ["a.com"]


# ── ScannerAPI.export_project_data / import_project_data ──────────────────────

class TestScannerAPIProjectData:
    def test_export_empty(self) -> None:
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path="")
        data = api.export_project_data()
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_import_restores_findings(self) -> None:
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path="")
        blob = {
            "findings": [
                {
                    "id": "f1",
                    "type": "xss",
                    "name": "XSS",
                    "url": "http://x.com",
                    "severity": "medium",
                }
            ]
        }
        count = api.import_project_data(blob)
        assert count == 1

    def test_import_skips_invalid(self) -> None:
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path="")
        blob = {
            "findings": [
                {"id": "ok", "type": "xss", "name": "X", "url": "http://x.com", "severity": "low"},
                {"broken": True},
            ]
        }
        count = api.import_project_data(blob)
        assert count >= 1

    def test_import_empty_blob(self) -> None:
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path="")
        count = api.import_project_data({})
        assert count == 0


# ── TargetAPI.export_project_data / import_project_data ───────────────────────

class TestTargetAPIProjectData:
    def test_export_empty(self) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path="")
        data = api.export_project_data()
        assert "sitemap" in data
        assert isinstance(data["sitemap"], dict)

    def test_import_empty(self) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path="")
        count = api.import_project_data({})
        assert count == 0

    def test_import_restores_nodes(self) -> None:
        from pentool.api.target_api import TargetAPI
        api = TargetAPI(db_path="")
        blob = {
            "sitemap": {
                "example.com": [
                    {
                        "id": "n1",
                        "host": "example.com",
                        "path": "/api",
                        "methods": ["GET", "POST"],
                        "request_count": 5,
                        "last_seen": "2024-01-01T00:00:00+00:00",
                        "in_scope": True,
                    }
                ]
            }
        }
        count = api.import_project_data(blob)
        assert count == 1
        nodes = api.get_paths("example.com")
        assert len(nodes) == 1
        assert nodes[0].path == "/api"
        assert nodes[0].in_scope is True

    def test_roundtrip(self) -> None:
        from pentool.api.target_api import TargetAPI
        from pentool.utils.parser import ParsedRequest
        api = TargetAPI(db_path="")
        req = ParsedRequest(
            method="GET",
            url="http://example.com/path",
            headers={},
            body="",
        )
        api.add_request(req)
        exported = api.export_project_data()

        api2 = TargetAPI(db_path="")
        count = api2.import_project_data(exported)
        assert count == 1
        assert api2.get_paths("example.com")


# ── IntruderAPI.export_project_data / import_project_data ─────────────────────

class TestIntruderAPIProjectData:
    def test_export_no_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        data = api.export_project_data()
        assert "results" in data
        assert data["results"] == []

    def test_import_empty(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        count = api.import_project_data({})
        assert count == 0

    def test_import_restores_results(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        blob = {
            "results": [
                {
                    "id": "r1",
                    "attack_id": "a1",
                    "request_number": 1,
                    "payload_values": ["admin"],
                    "request_raw": "GET / HTTP/1.1",
                    "response_status": 200,
                    "response_length": 1234,
                    "response_time_ms": 142,
                    "error": None,
                    "timestamp": "2024-01-01T00:00:00+00:00",
                }
            ]
        }
        count = api.import_project_data(blob)
        assert count == 1

    def test_import_handles_missing_timestamp(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        blob = {
            "results": [
                {
                    "id": "r2",
                    "attack_id": "a1",
                    "request_number": 2,
                    "payload_values": ["test"],
                    "request_raw": "",
                    "response_status": 404,
                    "response_length": 0,
                    "response_time_ms": 50,
                    "error": None,
                }
            ]
        }
        count = api.import_project_data(blob)
        assert count == 1
