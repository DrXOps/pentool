"""Unit-тесты: modules/repeater.py

Покрывает: Repeater (send, save_to_history, get_history, get_entry, delete_entry).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse


class TestRepeaterHistory:
    @pytest_asyncio.fixture
    async def repeater(self, tmp_path: Path):
        from pentool.core.database import init_db
        from pentool.modules.repeater import Repeater
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        return Repeater(db_path=db_path)

    @pytest.mark.asyncio
    async def test_init(self, repeater) -> None:
        from pentool.modules.repeater import Repeater
        assert isinstance(repeater, Repeater)

    @pytest.mark.asyncio
    async def test_history_empty_initially(self, repeater) -> None:
        history = await repeater.get_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_save_to_history_returns_id(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK", body="OK")
        entry_id = await repeater.save_to_history(req, resp, tab_name="Tab 1")
        assert isinstance(entry_id, int)
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_get_history_after_save(self, repeater) -> None:
        req = ParsedRequest(
            method="POST",
            url="http://example.com/login",
            headers={"Host": "example.com"},
            body='{"user":"admin"}',
        )
        resp = ParsedResponse(status=403, reason="Forbidden", body="Access denied")
        await repeater.save_to_history(req, resp, tab_name="Login test")
        history = await repeater.get_history()
        assert len(history) == 1
        entry = history[0]
        assert entry.method == "POST"
        assert entry.url == "http://example.com/login"
        assert entry.tab_name == "Login test"
        assert entry.response_status == 403

    @pytest.mark.asyncio
    async def test_get_history_multiple_entries(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        for i in range(5):
            await repeater.save_to_history(req, resp, tab_name=f"Tab {i}")
        history = await repeater.get_history()
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_get_history_limit(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        for _ in range(10):
            await repeater.save_to_history(req, resp)
        history = await repeater.get_history(limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_entry_by_id(self, repeater) -> None:
        req = ParsedRequest(
            method="DELETE",
            url="http://example.com/item/1",
            headers={"Authorization": "Bearer token"},
        )
        resp = ParsedResponse(status=204, reason="No Content")
        entry_id = await repeater.save_to_history(req, resp, tab_name="Delete test")
        entry = await repeater.get_entry(entry_id)
        assert entry is not None
        assert entry.method == "DELETE"
        assert entry.tab_name == "Delete test"

    @pytest.mark.asyncio
    async def test_get_entry_nonexistent_returns_none(self, repeater) -> None:
        result = await repeater.get_entry(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_entry(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        entry_id = await repeater.save_to_history(req, resp)
        await repeater.delete_entry(entry_id)
        assert await repeater.get_entry(entry_id) is None
        assert await repeater.get_history() == []

    @pytest.mark.asyncio
    async def test_entry_has_timestamp(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        entry_id = await repeater.save_to_history(req, resp)
        entry = await repeater.get_entry(entry_id)
        assert entry.timestamp is not None

    @pytest.mark.asyncio
    async def test_history_sorted_newest_first(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        resp = ParsedResponse(status=200, reason="OK")
        for i in range(3):
            await repeater.save_to_history(req, resp, tab_name=f"Tab {i}")
        history = await repeater.get_history()
        # Новые записи — первые
        assert history[0].tab_name == "Tab 2"


class TestRepeaterSend:
    @pytest_asyncio.fixture
    async def repeater(self, tmp_path: Path):
        from pentool.core.database import init_db
        from pentool.modules.repeater import Repeater
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        return Repeater(db_path=db_path, timeout=5.0, verify_ssl=False)

    @pytest.mark.asyncio
    async def test_send_calls_http_client(self, repeater) -> None:
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        mock_response = ParsedResponse(status=200, reason="OK", body="body")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.send = AsyncMock(return_value=mock_response)

        with patch("pentool.modules.repeater.HTTPClient", return_value=mock_client):
            resp = await repeater.send(req, save=False)

        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_send_saves_to_history_when_save_true(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        mock_response = ParsedResponse(status=200, reason="OK", body="body")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.send = AsyncMock(return_value=mock_response)

        with patch("pentool.modules.repeater.HTTPClient", return_value=mock_client):
            await repeater.send(req, tab_name="Test", save=True)

        history = await repeater.get_history()
        assert len(history) == 1
        assert history[0].tab_name == "Test"

    @pytest.mark.asyncio
    async def test_send_no_save(self, repeater) -> None:
        req = ParsedRequest(method="GET", url="http://example.com/", headers={})
        mock_response = ParsedResponse(status=200, reason="OK")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.send = AsyncMock(return_value=mock_response)

        with patch("pentool.modules.repeater.HTTPClient", return_value=mock_client):
            await repeater.send(req, save=False)

        history = await repeater.get_history()
        assert len(history) == 0
