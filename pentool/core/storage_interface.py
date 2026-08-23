"""Storage interface — abstraction layer for future database backends.

This module is deliberately kept as a pure abstract contract only. It
exists as a *blueprint* for a future PostgreSQL/SaaS backend: when the
desktop SQLite path outgrows single-writer limits, a real implementation
can be written against this interface — but nothing in the running
application consumes it today (all live SQLite access goes through the
concrete `BaseSqliteStorage` family in storage/).

See wiki/storage_architecture.md for the current connection architecture
and the rationale for leaving this interface unimplemented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StorageInterface(ABC):
    """Abstract base class for storage implementations.

    Implementations:
    - (current): BaseSqliteStorage family (storage/base_sqlite_storage.py)
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


__all__ = [
    "StorageInterface",
]
