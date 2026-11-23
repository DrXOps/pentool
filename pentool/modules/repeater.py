"""Repeater — manual HTTP request sending with history."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlite3 import OperationalError, ProgrammingError

from pentool.core.logging import get_logger
from pentool.storage.base_sqlite_storage import BaseSqliteStorage
from pentool.utils.http_client import HTTPClient
from pentool.utils.parser import ParsedRequest, ParsedResponse, build_http_request

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


class Repeater(BaseSqliteStorage):
    """Repeater — send requests and save results to DB.

    Connection lifecycle: inherits `BaseSqliteStorage` (see
    pentool/storage/base_sqlite_storage.py). History methods open ONE
    persistent aiosqlite connection lazily on first use (`ensure_open()`)
    and reuse it instead of opening/closing a fresh connection via
    `core.db_schema.get_db()` on every call — the same consolidation already
    applied to HttpStorage, IntruderStorage and SiteMap. `ensure_open()`
    returns False (safe no-op) when `db_path` is falsy.

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
        super().__init__(db_path=db_path)
        self._project_id = project_id
        self._timeout = timeout
        self._verify_ssl = verify_ssl

    async def init_db(self, path: str) -> None:
        """Open/create the connection and ensure the `repeater_entries` table exists."""
        # Applied on the SAME persistent connection (not a second get_db()),
        # reusing the shared DDL from core.db_schema so repeater_entries stays
        # defined in one place. Idempotent (CREATE TABLE/INDEX IF NOT EXISTS).
        await self._connect(path)
        from pentool.core.db_schema import _SCHEMA

        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def send(
        self,
        request: ParsedRequest,
        tab_name: str = "Tab",
        save: bool = True,
    ) -> ParsedResponse:
        async with HTTPClient(timeout=self._timeout, verify_ssl=self._verify_ssl) as client:
            logger.info("REPEATER: sending %s %s", request.method, request.url)
            logger.debug("REPEATER: extra_headers=%s", client._extra_headers)
            response = await client.send(request)
            logger.info(
                "REPEATER: response %s %s -> %d (%d bytes)",
                request.method,
                request.url,
                response.status,
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
        if not await self.ensure_open():
            return 0
        cursor = await self._db.execute(
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
        await self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_history(
        self,
        limit: int = 50,
        project_id: int | None = None,
    ) -> list[RepeaterEntry]:
        if not await self.ensure_open():
            return []
        pid = project_id if project_id is not None else self._project_id
        if pid is not None:
            cursor = await self._db.execute(
                "SELECT * FROM repeater_entries WHERE project_id=? ORDER BY id DESC LIMIT ?",
                (pid, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM repeater_entries ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()

        return [_row_to_entry(row) for row in rows]

    async def get_entry(self, entry_id: int) -> RepeaterEntry | None:
        if not await self.ensure_open():
            return None
        cursor = await self._db.execute(
            "SELECT * FROM repeater_entries WHERE id=?",
            (entry_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None
        return _row_to_entry(row)

    async def delete_entry(self, entry_id: int) -> None:
        if not await self.ensure_open():
            return
        await self._db.execute(
            "DELETE FROM repeater_entries WHERE id=?",
            (entry_id,),
        )
        await self._db.commit()

    # ── Tabs ────────────────────────────────────────────────────────────────
    # `repeater_entries` is the SEND HISTORY: one row per send,
    # append-only. The set of open tabs lives in `repeater_tabs` under a
    # stable `tab_uid` (as in Scanner and Intruder). Deriving tabs from the
    # history is wrong: closing forgot the tab in memory only, and after a
    # restart it came back (F-053).

    async def save_tab(
        self,
        tab_uid: str,
        tab_name: str,
        request_text: str,
        sort_order: int = 0,
    ) -> None:
        """Upsert a single tab identified by its stable `tab_uid`.

        Name and text are replaceable: `tab_uid` is created once per tab lifetime,
        and renaming is cosmetic — it must not create a new row.
        """
        if not tab_uid or not await self.ensure_open():
            return
        try:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO repeater_tabs
                    (tab_uid, project_id, tab_name, request_text, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (tab_uid, self._project_id, tab_name, request_text, sort_order),
            )
            await self._db.commit()
        except (OperationalError, ProgrammingError) as exc:
            # Same race class as in IntruderStorage: close()/switch_db()
            # could happen between execute() and commit().
            logger.debug("save_tab failed (likely race): %s", exc)

    async def get_tabs(self) -> list[dict]:
        """Every saved tab of the project, in creation order."""
        if not await self.ensure_open():
            return []
        cursor = await self._db.execute(
            "SELECT tab_uid, tab_name, request_text, sort_order FROM repeater_tabs "
            "WHERE project_id IS ? ORDER BY sort_order, id",
            (self._project_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "tab_uid": row[0],
                "tab_name": row[1],
                "request_text": row[2],
                "sort_order": row[3],
            }
            for row in rows
        ]

    async def delete_tab(self, tab_uid: str) -> None:
        """Forget a tab. The history (`repeater_entries`) stays — it is a log."""
        if not tab_uid or not await self.ensure_open():
            return
        await self._db.execute("DELETE FROM repeater_tabs WHERE tab_uid = ?", (tab_uid,))
        await self._db.commit()

    async def seed_tabs_from_history(self) -> list[dict]:
        """One-time migration: rebuild the tab registry from the send history.

        Until 2026-11-16 the set of tabs was the last 20 rows of
        `repeater_entries`, grouped by `tab_name`. In an existing project
        there are no rows in `repeater_tabs`, and after the upgrade it would open
        with a single empty tab — the user would lose what they saw before.


        So with an empty registry the tabs are rebuilt once from the history (same
        grouping rules: newest row per name) and written to the registry.
        After that the registry alone is the source of truth, and closing a tab
        becomes final. A repeated call does nothing.
        """
        existing = await self.get_tabs()
        if existing:
            return existing

        entries = await self.get_history(limit=20)
        if not entries:
            return []

        newest_per_name: dict[str, RepeaterEntry] = {}
        for entry in reversed(entries):  # oldest first → newest wins
            newest_per_name[entry.tab_name] = entry

        for order, (name, entry) in enumerate(newest_per_name.items()):
            await self.save_tab(
                uuid.uuid4().hex,
                name,
                build_http_request(entry.request),
                order,
            )
        logger.info("REPEATER: реестр вкладок собран из истории (%d)", len(newest_per_name))
        return await self.get_tabs()


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
