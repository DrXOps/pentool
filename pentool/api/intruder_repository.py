"""IntruderRepository — SQL for Intruder tab state and attack result persistence.

Extracted from `IntruderAPI` (see
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md, section 2.6). Pure
data-access: no attack orchestration knowledge, only the `intruder_state`/
`intruder_results` table CRUD that used to live directly on `IntruderAPI`.
Behavior (upsert-by-delete-then-insert for state, column selection/ordering
for results) is unchanged from the original
`IntruderAPI.save_state`/`load_state`/`save_result`/`get_results_from_db`.

Mirrors the pattern already used for Scanner
(`pentool.api.scanner_tab_repository.ScannerTabRepository`, pro/) — same
extraction, applied to the one remaining API class that still wrote raw
SQL directly (`ProxyAPI`/`RepeaterAPI` already delegate all SQL to
`HttpStorage`/`Repeater` in modules/).

Intruder became multi-tab (see IntruderScreen._TabState) — `tab_uid` is the
new stable per-tab identity (mirrors Scanner's tab_uid), persisted/restored
independently of the cosmetic, user-renameable `tab_name`. All `tab_uid`
parameters below default to "" and fall back to the original tab_name-keyed
behavior when omitted, so existing single-tab callers/tests are unaffected.

Connection lifecycle: inherits `BaseSqliteStorage` (see
pentool/storage/base_sqlite_storage.py) instead of opening/closing a fresh
`aiosqlite` connection via `core.database.get_db()` on every call. That old
per-call open/close pattern was the direct cause of a real crash — a fast
Intruder attack calls `save_result()` per HTTP response (thousands/sec),
each one opening+closing its own connection to the same file HttpStorage
already holds open. Every public method here now calls
`await self.ensure_open()` first, which connects once (lazily, on first
use) and reuses that connection for the object's lifetime — the "safe
no-op when db_path is falsy" contract (see TestNoDbPath in
tests/unit/api/test_intruder_repository.py) is preserved because
`ensure_open()` returns False when `self._db_path` is empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pentool.modules.intruder import IntruderResult
from pentool.storage.base_sqlite_storage import BaseSqliteStorage


class IntruderRepository(BaseSqliteStorage):
    """CRUD for `intruder_state` and `intruder_results`, scoped to one project DB."""

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(db_path=db_path)

    async def save_state(
        self,
        tab_name: str,
        template: str,
        attack_type: str,
        payloads: list[list[str]],
        tab_uid: str = "",
    ) -> None:
        """Save Intruder tab state (template, attack type, payloads) to DB.

        When `tab_uid` is given, upserts by that stable identity (matches
        ScannerTabRepository.save_tab's rationale — tab_name alone can't
        distinguish two same-named tabs across restarts). When omitted,
        falls back to the original delete-by-tab_name-then-insert behavior
        for backward compatibility with single-tab callers.
        """
        if not await self.ensure_open():
            return

        db = self._db
        if tab_uid:
            cursor = await db.execute(
                "SELECT id FROM intruder_state WHERE tab_uid = ?", (tab_uid,)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    """UPDATE intruder_state SET tab_name = ?, template = ?,
                       attack_type = ?, payloads_json = ?, updated_at = datetime('now')
                       WHERE tab_uid = ?""",
                    (tab_name, template, attack_type, json.dumps(payloads), tab_uid),
                )
            else:
                await db.execute(
                    """INSERT INTO intruder_state
                       (tab_uid, tab_name, template, attack_type, payloads_json, updated_at)
                       VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                    (tab_uid, tab_name, template, attack_type, json.dumps(payloads)),
                )
        else:
            # Legacy path — delete-then-insert by tab_name. Restricted to
            # rows with no tab_uid so it never clobbers a multi-tab
            # caller's uid-keyed row that happens to share the same name.
            await db.execute(
                "DELETE FROM intruder_state WHERE tab_name = ? AND (tab_uid IS NULL OR tab_uid = '')",
                (tab_name,),
            )
            await db.execute(
                """INSERT INTO intruder_state (tab_name, template, attack_type, payloads_json, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (tab_name, template, attack_type, json.dumps(payloads)),
            )
        await db.commit()

    async def load_state(self, tab_name: str, tab_uid: str = "") -> dict | None:
        """Load Intruder tab state from DB — by tab_uid if given, else tab_name."""
        if not await self.ensure_open():
            return None

        db = self._db
        if tab_uid:
            cursor = await db.execute(
                "SELECT template, attack_type, payloads_json FROM intruder_state WHERE tab_uid = ?",
                (tab_uid,),
            )
        else:
            cursor = await db.execute(
                "SELECT template, attack_type, payloads_json FROM intruder_state WHERE tab_name = ?",
                (tab_name,),
            )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "template": row[0],
            "attack_type": row[1],
            "payloads": json.loads(row[2]),
        }

    async def get_tabs(self) -> list[dict]:
        """List all Intruder tabs that have saved state (tab_uid set), most
        recently updated first — used to restore tabs on project load."""
        if not await self.ensure_open():
            return []

        cursor = await self._db.execute(
            "SELECT tab_uid, tab_name FROM intruder_state "
            "WHERE tab_uid IS NOT NULL AND tab_uid != '' "
            "ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [{"tab_uid": row[0], "tab_name": row[1]} for row in rows]

    async def delete_tab(self, tab_uid: str) -> None:
        """Delete a tab's saved state and results by its stable tab_uid."""
        if not tab_uid or not await self.ensure_open():
            return

        db = self._db
        await db.execute("DELETE FROM intruder_state WHERE tab_uid = ?", (tab_uid,))
        await db.execute("DELETE FROM intruder_results WHERE tab_uid = ?", (tab_uid,))
        await db.commit()

    async def save_result(
        self,
        result: IntruderResult,
        project_id: int | None = None,
        tab_uid: str = "",
    ) -> None:
        """Save a single intruder result to DB."""
        if not await self.ensure_open():
            return

        await self._db.execute(
            """INSERT INTO intruder_results
               (project_id, attack_id, request_number, payload_values, request_raw,
                response_raw, response_status, response_length, response_time_ms, error, timestamp, tab_uid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                result.attack_id,
                result.request_number,
                json.dumps(result.payload_values),
                result.request_raw,
                result.response_raw,
                result.response_status,
                result.response_length,
                result.response_time_ms,
                result.error,
                result.timestamp.isoformat(),
                tab_uid,
            ),
        )
        await self._db.commit()

    async def get_results(
        self,
        attack_id: str | None = None,
        limit: int = 1000,
        tab_uid: str = "",
    ) -> list[IntruderResult]:
        """Load intruder results from DB.

        Filters by attack_id if given, else by tab_uid if given (all results
        across every attack ever run in that tab), else returns the most
        recent `limit` results overall (legacy single-tab behavior).
        """
        if not await self.ensure_open():
            return []

        db = self._db
        if attack_id:
            cursor = await db.execute(
                """SELECT id, attack_id, request_number, payload_values, request_raw,
                          response_raw, response_status, response_length, response_time_ms, error, timestamp
                   FROM intruder_results WHERE attack_id = ?
                   ORDER BY request_number LIMIT ?""",
                (attack_id, limit),
            )
        elif tab_uid:
            cursor = await db.execute(
                """SELECT id, attack_id, request_number, payload_values, request_raw,
                          response_raw, response_status, response_length, response_time_ms, error, timestamp
                   FROM intruder_results WHERE tab_uid = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (tab_uid, limit),
            )
        else:
            cursor = await db.execute(
                """SELECT id, attack_id, request_number, payload_values, request_raw,
                          response_raw, response_status, response_length, response_time_ms, error, timestamp
                   FROM intruder_results
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row[10])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                ts = datetime.now(timezone.utc)
            results.append(
                IntruderResult(
                    id=str(row[0]),
                    attack_id=row[1],
                    request_number=row[2],
                    payload_values=json.loads(row[3]) if row[3] else [],
                    request_raw=row[4],
                    response_raw=row[5],
                    response_status=row[6],
                    response_length=row[7],
                    response_time_ms=row[8],
                    error=row[9],
                    timestamp=ts,
                )
            )
        return results
