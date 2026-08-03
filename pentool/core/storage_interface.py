"""Storage Interface — abstraction layer for database operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pentool.core.database import get_db  # noqa: E402 — needed for patch target


class StorageInterface(ABC):
    """Abstract base class for storage implementations.

    Implementations:
    - SQLiteStorage (current, for desktop)
    - PostgreSQLStorage (future, for SaaS)
    """

    @abstractmethod
    async def init_db(self, path_or_conn_string: str) -> None:
        """Initialize database connection.

        Args:
            path_or_conn_string: File path for SQLite, connection string for PostgreSQL
        """

    @abstractmethod
    async def close(self) -> None:
        """Close database connection."""

    # ── HTTP History operations ────────────────────────────────────────────────

    @abstractmethod
    async def add_request(
        self,
        method: str,
        url: str,
        status_code: int | None,
        request_headers: dict[str, str] | None,
        response_headers: dict[str, str] | None,
        request_body: str | None,
        response_body: str | None,
        **kwargs,
    ) -> int:
        """Add HTTP request/response pair to storage.

        Returns:
            Row ID of inserted record
        """

    @abstractmethod
    async def get_request(self, row_id: int) -> dict[str, Any] | None:
        """Get HTTP request/response by ID."""

    @abstractmethod
    async def get_requests(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        order_by: str = "timestamp DESC",
    ) -> list[dict[str, Any]]:
        """Get list of HTTP requests with filtering and pagination."""

    @abstractmethod
    async def update_response(
        self,
        row_id: int,
        status_code: int,
        response_headers: dict[str, str],
        response_body: str,
    ) -> None:
        """Update response data for existing request."""

    @abstractmethod
    async def delete_request(self, row_id: int) -> None:
        """Delete HTTP request by ID."""

    @abstractmethod
    async def clear_all_requests(self) -> None:
        """Delete all HTTP requests."""

    @abstractmethod
    async def search_requests(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        """Full-text search in requests (FTS5 for SQLite, tsvector for PostgreSQL)."""

    # ── Scanner findings operations ────────────────────────────────────────────

    @abstractmethod
    async def add_finding(
        self,
        severity: str,
        title: str,
        url: str,
        description: str,
        evidence: str | None,
        **kwargs,
    ) -> int:
        """Add vulnerability finding to storage."""

    @abstractmethod
    async def get_findings(
        self,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of findings with filtering."""

    @abstractmethod
    async def update_finding(self, finding_id: int, **kwargs) -> None:
        """Update finding (e.g., mark as false positive)."""

    @abstractmethod
    async def delete_finding(self, finding_id: int) -> None:
        """Delete finding."""

    @abstractmethod
    async def clear_all_findings(self) -> None:
        """Delete all findings."""

    # ── Project/session metadata ───────────────────────────────────────────────

    @abstractmethod
    async def get_metadata(self, key: str) -> Any | None:
        """Get project metadata by key."""

    @abstractmethod
    async def set_metadata(self, key: str, value: Any) -> None:
        """Set project metadata."""

    # ── Statistics ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Get storage statistics (counts, sizes, etc.)."""


class SQLiteStorage(StorageInterface):
    """SQLite implementation (current desktop version).

    This is a thin wrapper around existing HttpStorage for compatibility.
    """

    def __init__(self) -> None:
        from pentool.storage.http_storage import HttpStorage
        self._storage = HttpStorage()

    async def init_db(self, path_or_conn_string: str) -> None:
        await self._storage.init_db(path_or_conn_string)

    async def close(self) -> None:
        await self._storage.close()

    async def add_request(
        self,
        method: str,
        url: str,
        status_code: int | None,
        request_headers: dict[str, str] | None,
        response_headers: dict[str, str] | None,
        request_body: str | None,
        response_body: str | None,
        **kwargs,
    ) -> int:
        # Delegate to existing HttpStorage implementation
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(
            method=method,
            url=url,
            headers=request_headers or {},
            body=request_body or "",
        )

        resp = ParsedResponse(
            status=status_code or 0,
            headers=response_headers or {},
            body=response_body or "",
        ) if status_code else None

        return await self._storage.add_request(req, resp)

    async def get_request(self, row_id: int) -> dict[str, Any] | None:
        return await self._storage.get_request_by_id(row_id)

    async def get_requests(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        order_by: str = "timestamp DESC",
    ) -> list[dict[str, Any]]:
        return await self._storage.get_requests_metadata(
            limit=limit,
            offset=offset,
            order_by=order_by,
        )

    async def update_response(
        self,
        row_id: int,
        status_code: int,
        response_headers: dict[str, str],
        response_body: str,
    ) -> None:
        await self._storage.update_response(
            row_id,
            status_code,
            response_headers,
            response_body,
        )

    async def delete_request(self, row_id: int) -> None:
        await self._storage.delete_request(row_id)

    async def clear_all_requests(self) -> None:
        await self._storage.clear_all()

    async def search_requests(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self._storage.search(query, limit=limit)

    # Scanner findings (delegating to core/database.py via get_db)
    async def add_finding(
        self,
        severity: str,
        title: str,
        url: str,
        description: str,
        evidence: str | None,
        **kwargs,
    ) -> int:
        db_path = self._storage._db_path
        async with get_db(db_path) as db:
            cur = await db.execute(
                """INSERT INTO vulnerabilities
                   (type, name, severity, host, url, description, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    kwargs.get("type", title),
                    title,
                    severity,
                    kwargs.get("host", ""),
                    url,
                    description,
                    evidence or "",
                ),
            )
            await db.commit()
            return cur.lastrowid or 0

    async def get_findings(
        self,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        db_path = self._storage._db_path
        async with get_db(db_path) as db:
            cur = await db.execute(
                "SELECT * FROM vulnerabilities ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def update_finding(self, finding_id: int, **kwargs) -> None:
        db_path = self._storage._db_path
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [finding_id]
        async with get_db(db_path) as db:
            await db.execute(
                f"UPDATE vulnerabilities SET {cols} WHERE id = ?", vals
            )
            await db.commit()

    async def delete_finding(self, finding_id: int) -> None:
        db_path = self._storage._db_path
        async with get_db(db_path) as db:
            await db.execute("DELETE FROM vulnerabilities WHERE id = ?", (finding_id,))
            await db.commit()

    async def clear_all_findings(self) -> None:
        db_path = self._storage._db_path
        async with get_db(db_path) as db:
            await db.execute("DELETE FROM vulnerabilities")
            await db.commit()

    async def get_metadata(self, key: str) -> Any | None:
        """Get project metadata stored in vulnerabilities-adjacent KV (not yet a table)."""
        # Metadata table does not exist yet — return None gracefully
        return None

    async def set_metadata(self, key: str, value: Any) -> None:
        """Set project metadata. No-op until metadata table is added to schema."""

    async def get_stats(self) -> dict[str, Any]:
        db_path = self._storage._db_path
        total_requests = await self._storage.count()
        total_findings = 0
        try:
            async with get_db(db_path) as db:
                cur = await db.execute("SELECT COUNT(*) FROM vulnerabilities")
                row = await cur.fetchone()
                total_findings = row[0] if row else 0
        except Exception:
            pass
        return {
            "total_requests": total_requests,
            "total_findings": total_findings,
        }


# Future: PostgreSQLStorage for SaaS
# class PostgreSQLStorage(StorageInterface):
#     """PostgreSQL implementation for SaaS version."""
#     pass


def create_storage(backend: str = "sqlite") -> StorageInterface:
    """Factory function to create storage instance.

    Args:
        backend: "sqlite" or "postgresql"

    Returns:
        StorageInterface implementation
    """
    if backend == "sqlite":
        return SQLiteStorage()
    elif backend == "postgresql":
        raise NotImplementedError("PostgreSQL storage not yet implemented")
    else:
        raise ValueError(f"Unknown storage backend: {backend}")


__all__ = [
    "StorageInterface",
    "SQLiteStorage",
    "create_storage",
]
