"""Unit tests: api/repeater_api.py and api/intruder_api.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse


class TestRepeaterAPI:
    @pytest_asyncio.fixture
    async def api(self, tmp_path: Path):
        from pentool.core.db_schema import init_db
        from pentool.api.repeater_api import RepeaterAPI
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        rp_api = RepeaterAPI(db_path=db_path, timeout=5.0, verify_ssl=False)
        try:
            yield rp_api
        finally:
            await rp_api.close()

    @pytest.mark.asyncio
    async def test_import(self) -> None:
        from pentool.api.repeater_api import RepeaterAPI, RepeaterEntry
        assert RepeaterAPI is not None
        assert RepeaterEntry is not None

    @pytest.mark.asyncio
    async def test_history_empty_initially(self, api) -> None:
        history = await api.get_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_save_and_get_history(self, api) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK", body="hello")
        await api.save_to_history(req, resp, tab_name="Test Tab")
        history = await api.get_history()
        assert len(history) == 1
        assert history[0].tab_name == "Test Tab"

    @pytest.mark.asyncio
    async def test_save_returns_entry_id(self, api) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        entry_id = await api.save_to_history(req, resp)
        assert isinstance(entry_id, int)
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_get_entry_by_id(self, api) -> None:
        req = ParsedRequest(method="POST", url="http://example.com/login", headers={})
        resp = ParsedResponse(status=302, reason="Found")
        entry_id = await api.save_to_history(req, resp, tab_name="Login")
        entry = await api.get_entry(entry_id)
        assert entry is not None
        assert entry.method == "POST"
        assert entry.tab_name == "Login"

    @pytest.mark.asyncio
    async def test_get_entry_nonexistent(self, api) -> None:
        result = await api.get_entry(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_entry(self, api) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        entry_id = await api.save_to_history(req, resp)
        await api.delete_entry(entry_id)
        assert await api.get_entry(entry_id) is None

    @pytest.mark.asyncio
    async def test_get_history_limit(self, api) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        for _ in range(5):
            await api.save_to_history(req, resp)
        history = await api.get_history(limit=2)
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_send_delegates_to_repeater(self, api) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        mock_response = ParsedResponse(status=200, reason="OK", body="ok")

        with patch.object(api._repeater, "send", new=AsyncMock(return_value=mock_response)):
            resp = await api.send(req, save=False)

        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_switch_db_points_at_new_file(self, tmp_path: Path) -> None:
        """switch_db must close the old connection and open the new project DB."""
        from pentool.core.db_schema import init_db
        from pentool.api.repeater_api import RepeaterAPI
        db1 = str(tmp_path / "project1.db")
        db2 = str(tmp_path / "project2.db")
        await init_db(db1)
        await init_db(db2)

        api = RepeaterAPI(db_path=db1, timeout=5.0, verify_ssl=False)
        try:
            req = ParsedRequest(method="GET", url="http://one.example/", headers={})
            await api.save_to_history(req, ParsedResponse(status=200, reason="OK"), tab_name="One")

            # Switch to a fresh project DB — history must now be empty (new file).
            await api.switch_db(db2)
            assert await api.get_history() == []

            # Switch back — the original entry must still be there.
            await api.switch_db(db1)
            history = await api.get_history()
            assert len(history) == 1
            assert history[0].tab_name == "One"
        finally:
            await api.close()

    @pytest.mark.asyncio
    async def test_close_releases_connection(self, tmp_path: Path) -> None:
        """close() must not raise and must allow a clean re-open via switch_db."""
        from pentool.core.db_schema import init_db
        from pentool.api.repeater_api import RepeaterAPI
        db = str(tmp_path / "close.db")
        await init_db(db)

        api = RepeaterAPI(db_path=db, timeout=5.0, verify_ssl=False)
        await api.close()  # closing when never opened is a safe no-op
        await api.save_to_history(
            ParsedRequest(method="GET", url="http://x.example/", headers={}),
            ParsedResponse(status=200, reason="OK"),
            tab_name="After close",
        )
        history = await api.get_history()
        assert len(history) == 1
        await api.close()


class TestIntruderAPI:
    def test_import(self) -> None:
        from pentool.api.intruder_api import IntruderAPI, IntruderConfig, IntruderResult, AttackType
        assert IntruderAPI is not None

    def test_initial_state(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        assert api.is_running is False
        assert api.get_results() == []
        assert api.get_progress() == (0, 0)

    @pytest.mark.asyncio
    async def test_load_payloads(self, tmp_path: Path) -> None:
        from pentool.api.intruder_api import IntruderAPI
        f = tmp_path / "payloads.txt"
        f.write_text("admin\nroot\ntest\n")
        api = IntruderAPI()
        result = await api.load_payloads(str(f))
        assert "admin" in result
        assert "root" in result

    @pytest.mark.asyncio
    async def test_generate_numeric(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        result = await api.generate_numeric(1, 4)
        assert result == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_generate_chars(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        result = await api.generate_chars("ab", 1, 1)
        assert "a" in result
        assert "b" in result

    @pytest.mark.asyncio
    async def test_stop_without_attack_no_error(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        await api.stop()  # no error if not running

    @pytest.mark.asyncio
    async def test_pause_without_attack_no_error(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        await api.pause()  # no error if not running

    @pytest.mark.asyncio
    async def test_pause_with_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        from unittest.mock import MagicMock
        api = IntruderAPI()
        attack = MagicMock()
        attack.pause = AsyncMock()
        api._attack = attack
        await api.pause()
        attack.pause.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pause_attack_without_pause_support(self) -> None:
        # Turbo attack has no pause() attribute — must not crash
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        api._attack = object()  # no pause attr
        await api.pause()  # no-op, no crash

    @pytest.mark.asyncio
    async def test_resume_with_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        from unittest.mock import MagicMock
        api = IntruderAPI()
        attack = MagicMock()
        attack.resume = AsyncMock()
        api._attack = attack
        await api.resume()
        attack.resume.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_with_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        from unittest.mock import MagicMock
        api = IntruderAPI()
        attack = MagicMock()
        attack.stop = AsyncMock()
        api._attack = attack
        await api.stop()
        attack.stop.assert_awaited_once()

    def test_get_results_from_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        attack = MagicMock()
        attack.get_results.return_value = ["r"]
        api._attack = attack
        assert api.get_results() == ["r"]

    def test_get_results_fallback_restored(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        api._restored_results = ["old"]
        assert api.get_results() == ["old"]

    def test_get_progress_no_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        assert api.get_progress() == (0, 0)

    def test_is_running_no_attack(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        assert api.is_running is False

    def test_export_csv_calls_attack(self, tmp_path) -> None:
        from pentool.api.intruder_api import IntruderAPI
        from unittest.mock import MagicMock
        api = IntruderAPI()
        attack = MagicMock()
        api._attack = attack
        api.export_csv(str(tmp_path / "r.csv"))
        attack.export_csv.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_attack_standard_mode(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from pentool.api import intruder_api as m
        api = m.IntruderAPI()
        attack = MagicMock()
        attack.run = AsyncMock()
        attack.attack_id = "aid-1"
        with patch.object(m, "IntruderAttack", return_value=attack), \
             patch.object(m.asyncio, "create_task",
                          side_effect=lambda coro: asyncio.ensure_future(coro)):
            aid = await api.start_attack(MagicMock(), on_result=None, on_progress=None, turbo_mode=False)
        assert aid == "aid-1"

    @pytest.mark.asyncio
    async def test_start_attack_turbo_mode(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from pentool.api import intruder_api as m
        api = m.IntruderAPI()
        turbo = MagicMock()
        turbo.run = AsyncMock()
        turbo.attack_id = "turbo-1"
        with patch("pentool.modules.intruder_turbo.TurboIntruderAttack", return_value=turbo), \
             patch.object(m.asyncio, "create_task",
                          side_effect=lambda coro: asyncio.ensure_future(coro)):
            aid = await api.start_attack(MagicMock(), on_result=None, on_progress=None, turbo_mode=True)
        assert aid == "turbo-1"

    @pytest.mark.asyncio
    async def test_state_proxy_methods(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        from unittest.mock import AsyncMock, MagicMock
        api = IntruderAPI()
        repo = MagicMock()
        repo.save_state = AsyncMock(return_value=None)
        repo.load_state = AsyncMock(return_value={"template": "x"})
        repo.get_tabs = AsyncMock(return_value=[{"tab_uid": "u", "tab_name": "n"}])
        repo.delete_tab = AsyncMock(return_value=None)
        repo.switch_db = AsyncMock(return_value=None)
        repo.close = AsyncMock(return_value=None)
        repo.save_result = AsyncMock(return_value=None)
        repo.get_results = AsyncMock(return_value=["res"])
        api._repo = repo

        await api.save_state("t", "tmpl", "sniper", [["a"]], tab_uid="u")
        repo.save_state.assert_awaited_once()

        loaded = await api.load_state("t", tab_uid="u")
        assert loaded == {"template": "x"}

        tabs = await api.get_tabs()
        assert tabs == [{"tab_uid": "u", "tab_name": "n"}]

        await api.delete_tab("u")
        repo.delete_tab.assert_awaited_once()

        await api.switch_db("/some/db")
        repo.switch_db.assert_awaited_once()

        await api.close()
        repo.close.assert_awaited_once()

        from datetime import datetime, timezone
        from pentool.modules.intruder import IntruderResult
        res = IntruderResult(
            id="1", attack_id="a", request_number=0, payload_values=[],
            request_raw="", response_raw="", response_status=0,
            response_length=0, response_time_ms=0, error=None,
            timestamp=datetime.now(timezone.utc),
        )
        await api.save_result(res, project_id=1, tab_uid="u")
        repo.save_result.assert_awaited_once()

        results = await api.get_results_from_db("a", limit=5, tab_uid="u")
        assert results == ["res"]

    def test_export_project_data(self) -> None:
        from datetime import datetime, timezone
        from pentool.api.intruder_api import IntruderAPI
        from pentool.modules.intruder import IntruderResult
        api = IntruderAPI()
        res = IntruderResult(
            id="x", attack_id="a", request_number=1, payload_values=["p"],
            request_raw="R", response_raw="S", response_status=200,
            response_length=5, response_time_ms=7, error=None,
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        from unittest.mock import MagicMock
        attack = MagicMock()
        attack.get_results.return_value = [res]
        api._attack = attack
        data = api.export_project_data()
        assert data["results"][0]["attack_id"] == "a"

    def test_import_project_data(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        data = {"results": [{
            "id": "r", "attack_id": "a", "request_number": 0,
            "payload_values": ["x"], "request_raw": "", "response_raw": "",
            "response_status": 200, "response_length": 0, "response_time_ms": 0,
            "error": None, "timestamp": "2020-01-01T00:00:00+00:00",
        }]}
        n = api.import_project_data(data)
        assert n == 1

    def test_import_project_data_bad_timestamp(self) -> None:
        from pentool.api.intruder_api import IntruderAPI
        api = IntruderAPI()
        data = {"results": [{"id": "r", "attack_id": "a", "timestamp": "not-a-date"}]}
        n = api.import_project_data(data)
        assert n == 1
