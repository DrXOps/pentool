"""Unit tests for pentool/core/storage_interface.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCreateStorage:
    def test_sqlite_backend(self):
        from pentool.core.storage_interface import create_storage, SQLiteStorage
        with patch("pentool.core.storage_interface.SQLiteStorage") as mock:
            mock.return_value = MagicMock()
            storage = create_storage("sqlite")
            mock.assert_called_once()

    def test_unknown_backend_raises(self):
        from pentool.core.storage_interface import create_storage
        with pytest.raises(ValueError, match="Unknown storage backend"):
            create_storage("mongodb")

    def test_postgresql_not_implemented(self):
        from pentool.core.storage_interface import create_storage
        with pytest.raises(NotImplementedError):
            create_storage("postgresql")


class TestSQLiteStorage:
    @pytest.fixture
    def storage(self, tmp_path):
        from pentool.core.storage_interface import SQLiteStorage
        s = SQLiteStorage()
        return s, tmp_path

    @pytest.mark.asyncio
    async def test_init_db(self, storage):
        s, tmp_path = storage
        db_path = str(tmp_path / "test.db")
        s._storage.init_db = AsyncMock()
        await s.init_db(db_path)
        s._storage.init_db.assert_called_once_with(db_path)

    @pytest.mark.asyncio
    async def test_close(self, storage):
        s, _ = storage
        s._storage.close = AsyncMock()
        await s.close()
        s._storage.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_request(self, storage):
        s, _ = storage
        s._storage.add_request = AsyncMock(return_value=42)
        row_id = await s.add_request(
            method="GET",
            url="http://example.com/",
            status_code=200,
            request_headers={"Host": "example.com"},
            response_headers={"Content-Type": "text/html"},
            request_body="",
            response_body="<html>",
        )
        assert row_id == 42

    @pytest.mark.asyncio
    async def test_add_request_no_response(self, storage):
        s, _ = storage
        s._storage.add_request = AsyncMock(return_value=1)
        row_id = await s.add_request(
            method="GET",
            url="http://example.com/",
            status_code=None,
            request_headers=None,
            response_headers=None,
            request_body=None,
            response_body=None,
        )
        assert row_id == 1

    @pytest.mark.asyncio
    async def test_get_request(self, storage):
        s, _ = storage
        s._storage.get_request_by_id = AsyncMock(return_value={"id": 1})
        result = await s.get_request(1)
        assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_get_requests(self, storage):
        s, _ = storage
        # SQLiteStorage.get_requests calls get_requests_metadata or get_metadata_batch
        # depending on the actual implementation — mock both
        s._storage.get_requests_metadata = AsyncMock(return_value=[{"id": 1}])
        s._storage.get_metadata_batch = AsyncMock(return_value=[{"id": 1}])
        result = await s.get_requests(limit=10, offset=0)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_delete_request(self, storage):
        s, _ = storage
        s._storage.delete_request = AsyncMock()
        await s.delete_request(1)
        s._storage.delete_request.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_clear_all_requests(self, storage):
        s, _ = storage
        s._storage.clear_all = AsyncMock()
        await s.clear_all_requests()
        s._storage.clear_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_requests(self, storage):
        s, _ = storage
        s._storage.search = AsyncMock(return_value=[])
        result = await s.search_requests("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_stats(self, storage, tmp_path):
        s, _ = storage
        db_path = str(tmp_path / "test.db")
        s._storage.count = AsyncMock(return_value=5)
        s._storage._db_path = db_path
        # get_stats also queries vulnerabilities table — mock get_db
        with patch("pentool.core.storage_interface.get_db") as mock_get_db:
            mock_conn = AsyncMock()
            mock_cur = AsyncMock()
            mock_cur.fetchone = AsyncMock(return_value=(3,))
            mock_conn.execute = AsyncMock(return_value=mock_cur)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_conn
            stats = await s.get_stats()
        assert stats["total_requests"] == 5
        assert "total_findings" in stats

    @pytest.mark.asyncio
    async def test_add_finding(self, storage, tmp_path):
        """add_finding delegates to vulnerabilities table via get_db."""
        s, _ = storage
        db_path = str(tmp_path / "test.db")
        s._storage._db_path = db_path
        with patch("pentool.core.storage_interface.get_db") as mock_get_db:
            mock_conn = AsyncMock()
            mock_cur = AsyncMock()
            mock_cur.lastrowid = 7
            mock_conn.execute = AsyncMock(return_value=mock_cur)
            mock_conn.commit = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_conn
            row_id = await s.add_finding("high", "XSS", "http://x.com", "desc", None)
        assert row_id == 7

    @pytest.mark.asyncio
    async def test_get_findings(self, storage, tmp_path):
        """get_findings returns list of dicts from vulnerabilities table."""
        s, _ = storage
        db_path = str(tmp_path / "test.db")
        s._storage._db_path = db_path
        with patch("pentool.core.storage_interface.get_db") as mock_get_db:
            mock_conn = AsyncMock()
            mock_cur = AsyncMock()
            mock_cur.fetchall = AsyncMock(return_value=[])
            mock_conn.execute = AsyncMock(return_value=mock_cur)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_conn
            result = await s.get_findings()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_metadata_returns_none(self, storage):
        """get_metadata returns None gracefully (table not yet in schema)."""
        s, _ = storage
        result = await s.get_metadata("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_metadata_noop(self, storage):
        """set_metadata is a no-op until metadata table is added."""
        s, _ = storage
        # Should not raise
        await s.set_metadata("key", "value")

    @pytest.mark.asyncio
    async def test_update_response(self, storage):
        s, _ = storage
        s._storage.update_response = AsyncMock()
        await s.update_response(1, 200, {"Content-Type": "text/html"}, "<html>")
        s._storage.update_response.assert_called_once_with(1, 200, {"Content-Type": "text/html"}, "<html>")
