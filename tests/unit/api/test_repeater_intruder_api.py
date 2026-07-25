"""Unit-тесты: api/repeater_api.py и api/intruder_api.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse


class TestRepeaterAPI:
    @pytest_asyncio.fixture
    async def api(self, tmp_path: Path):
        from pentool.core.database import init_db
        from pentool.api.repeater_api import RepeaterAPI
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        return RepeaterAPI(db_path=db_path, timeout=5.0, verify_ssl=False)

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
