"""Repeater — manual HTTP request sending with history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from pentool.core.database import get_db
from pentool.core.logging import get_logger
from pentool.utils.http_client import HTTPClient
from pentool.utils.parser import ParsedRequest, ParsedResponse

logger = get_logger(__name__)


@dataclass
class RepeaterEntry:
    """A record in the Repeater history."""

    id: int
    tab_name: str
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: str
    response_status: int | None
    response_headers: dict[str, str]
    response_body: str
    timestamp: datetime
    project_id: int | None = None

    @property
    def request(self) -> ParsedRequest:
        return ParsedRequest(
            method=self.method,
            url=self.url,
            headers=self.request_headers,
            body=self.request_body,
        )

    @property
    def response(self) -> ParsedResponse | None:
        if self.response_status is None:
            return None
        return ParsedResponse(
            status=self.response_status,
            headers=self.response_headers,
            body=self.response_body,
        )


class Repeater:
    """Repeater — send requests and save results to DB.

    Args:
        db_path: Path to the SQLite database.
        project_id: Current project ID (or None).
        timeout: HTTP request timeout in seconds.
        verify_ssl: Whether to verify server SSL.
    """

    def __init__(
        self,
        db_path: str,
        project_id: int | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = False,
    ) -> None:
        self._db_path = db_path
        self._project_id = project_id
        self._timeout = timeout
        self._verify_ssl = verify_ssl

    async def send(
        self,
        request: ParsedRequest,
        tab_name: str = "Tab",
        save: bool = True,
    ) -> ParsedResponse:
        async with HTTPClient(timeout=self._timeout, verify_ssl=self._verify_ssl) as client:
            logger.info("REPEATER: sending %s %s", request.method, request.url)
            response = await client.send(request)
            logger.info(
                "REPEATER: response %s %s -> %d (%d bytes)",
                request.method, request.url, response.status,
                len(response.body) if response.body else 0,
            )

        if save:
            await self.save_to_history(request, response, tab_name)

        return response

    async def save_to_history(
        self,
        request: ParsedRequest,
        response: ParsedResponse,
        tab_name: str = "Tab",
    ) -> int:
        async with get_db(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO repeater_entries
                    (project_id, tab_name, method, url,
                     request_headers, request_body,
                     response_status, response_headers, response_body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    tab_name,
                    request.method,
                    request.url,
                    json.dumps(request.headers),
                    request.body,
                    response.status,
                    json.dumps(response.headers),
                    response.body,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def get_history(
        self,
        limit: int = 50,
        project_id: int | None = None,
    ) -> list[RepeaterEntry]:
        pid = project_id if project_id is not None else self._project_id
        async with get_db(self._db_path) as db:
            if pid is not None:
                cursor = await db.execute(
                    "SELECT * FROM repeater_entries WHERE project_id=? ORDER BY id DESC LIMIT ?",
                    (pid, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM repeater_entries ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()

        return [_row_to_entry(row) for row in rows]

    async def get_entry(self, entry_id: int) -> RepeaterEntry | None:
        async with get_db(self._db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM repeater_entries WHERE id=?",
                (entry_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return _row_to_entry(row)

    async def delete_entry(self, entry_id: int) -> None:
        async with get_db(self._db_path) as db:
            await db.execute(
                "DELETE FROM repeater_entries WHERE id=?",
                (entry_id,),
            )
            await db.commit()


def _row_to_entry(row: object) -> RepeaterEntry:
    """Convert a DB row to a RepeaterEntry."""
    r = dict(row)  # type: ignore[call-overload]
    ts_str = r.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        ts = datetime.now(timezone.utc)

    def _parse_headers(raw: str) -> dict[str, str]:
        try:
            return json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    return RepeaterEntry(
        id=r["id"],
        tab_name=r.get("tab_name", "Tab"),
        method=r["method"],
        url=r["url"],
        request_headers=_parse_headers(r.get("request_headers", "{}")),
        request_body=r.get("request_body", ""),
        response_status=r.get("response_status"),
        response_headers=_parse_headers(r.get("response_headers", "{}")),
        response_body=r.get("response_body", ""),
        timestamp=ts,
        project_id=r.get("project_id"),
    )
