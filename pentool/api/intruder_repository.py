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
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pentool.core.database import get_db
from pentool.modules.intruder import IntruderResult


class IntruderRepository:
    """CRUD for `intruder_state` and `intruder_results`, scoped to one project DB."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    async def save_state(
        self,
        tab_name: str,
        template: str,
        attack_type: str,
        payloads: list[list[str]],
    ) -> None:
        """Save Intruder tab state (template, attack type, payloads) to DB."""
        if not self._db_path:
            return

        async with get_db(self._db_path) as db:
            # Delete old state for this tab
            await db.execute("DELETE FROM intruder_state WHERE tab_name = ?", (tab_name,))
            # Insert new state
            await db.execute(
                """INSERT INTO intruder_state (tab_name, template, attack_type, payloads_json, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (tab_name, template, attack_type, json.dumps(payloads)),
            )
            await db.commit()

    async def load_state(self, tab_name: str) -> dict | None:
        """Load Intruder tab state from DB."""
        if not self._db_path:
            return None

        async with get_db(self._db_path) as db:
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

    async def save_result(self, result: IntruderResult, project_id: int | None = None) -> None:
        """Save a single intruder result to DB."""
        if not self._db_path:
            return

        async with get_db(self._db_path) as db:
            await db.execute(
                """INSERT INTO intruder_results
                   (project_id, attack_id, request_number, payload_values, request_raw,
                    response_raw, response_status, response_length, response_time_ms, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                ),
            )
            await db.commit()

    async def get_results(
        self,
        attack_id: str | None = None,
        limit: int = 1000,
    ) -> list[IntruderResult]:
        """Load intruder results from DB."""
        if not self._db_path:
            return []

        async with get_db(self._db_path) as db:
            if attack_id:
                cursor = await db.execute(
                    """SELECT id, attack_id, request_number, payload_values, request_raw,
                              response_raw, response_status, response_length, response_time_ms, error, timestamp
                       FROM intruder_results WHERE attack_id = ?
                       ORDER BY request_number LIMIT ?""",
                    (attack_id, limit),
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
