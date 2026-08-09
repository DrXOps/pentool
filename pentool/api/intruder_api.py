"""Public API of the Intruder module for TUI and CLI."""

from __future__ import annotations

import asyncio

from pentool.api.base_api import ExportableAPI
from pentool.modules.intruder import (
    AttackType,
    IntruderAttack,
    IntruderConfig,
    IntruderResult,
    count_markers,
    extract_marker_defaults,
    generate_char_payloads,
    generate_numeric_payloads,
    load_payloads_from_file,
    process_payload,
)

__all__ = [
    "IntruderAPI",
    "AttackType",
    "IntruderAttack",
    "IntruderConfig",
    "IntruderResult",
    "count_markers",
    "extract_marker_defaults",
    "generate_char_payloads",
    "generate_numeric_payloads",
    "load_payloads_from_file",
    "process_payload",
]


class IntruderAPI(ExportableAPI):

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._attack: IntruderAttack | None = None
        self._task: asyncio.Task | None = None
        self._restored_results: list = []

    async def start_attack(
        self,
        config: IntruderConfig,
        on_result=None,
        on_progress=None,
        turbo_mode: bool = False,
    ) -> str:
        """Run the attack to completion and return its attack_id.

        NOTE: this method awaits the whole attack — it does NOT return as
        soon as the attack starts. Before this fix it fired the attack via
        `asyncio.create_task(...)` and returned immediately without
        awaiting it, so a caller doing `await api.start_attack(...)` got
        control back right after the attack merely started, not when it
        finished — `get_results()` called right after would see a near-
        empty/partial result set (see IntruderService.start_attack, which
        relies on start_attack() having completed the attack before it
        reads get_results() and emits IntruderFinished). The task handle is
        still kept on self._task so stop()/pause()/resume() and callers
        that want to cancel mid-attack (via self._task) keep working the
        same way as before.
        """
        if turbo_mode:
            # Turbo Mode: connection pooling + Keep-Alive
            from pentool.modules.intruder_turbo import TurboIntruderAttack
            self._attack = TurboIntruderAttack(config)
        else:
            # Standard mode
            self._attack = IntruderAttack(config, db_path=self._db_path)

        _on_result = on_result if on_result else lambda r: None
        _on_progress = on_progress if on_progress else lambda d, t: None

        self._task = asyncio.create_task(self._attack.run(_on_result, _on_progress))
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return self._attack.attack_id if hasattr(self._attack, 'attack_id') else "turbo"

    async def pause(self) -> None:
        if self._attack:
            await self._attack.pause()

    async def resume(self) -> None:
        """Resume the attack after a pause."""
        if self._attack:
            await self._attack.resume()

    async def stop(self) -> None:
        if self._attack:
            await self._attack.stop()

    def get_results(self) -> list[IntruderResult]:
        if self._attack:
            # Turbo mode uses get_results(), standard mode uses results property
            if hasattr(self._attack, 'get_results'):
                return self._attack.get_results()
            return self._attack.results
        # Fallback: восстановленные из БД данные
        return list(getattr(self, '_restored_results', []))

    def get_progress(self) -> tuple[int, int]:
        if self._attack:
            return self._attack.progress
        return (0, 0)

    @property
    def is_running(self) -> bool:
        return bool(self._attack and self._attack.is_running)

    async def load_payloads(self, path: str) -> list[str]:
        return load_payloads_from_file(path)

    async def generate_numeric(self, start: int, end: int, step: int = 1) -> list[str]:
        return generate_numeric_payloads(start, end, step)

    async def generate_chars(
        self, charset: str, min_len: int, max_len: int
    ) -> list[str]:
        return generate_char_payloads(charset, min_len, max_len)

    def export_csv(self, path: str) -> None:
        if self._attack:
            self._attack.export_csv(path)

    # ── State persistence (tabs) ───────────────────────────────────────────────

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
        import json

        from pentool.core.database import get_db

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
        import json

        from pentool.core.database import get_db

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
        import json

        from pentool.core.database import get_db

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

    async def get_results_from_db(
        self,
        attack_id: str | None = None,
        limit: int = 1000,
    ) -> list[IntruderResult]:
        """Load intruder results from DB."""
        if not self._db_path:
            return []
        import json
        from datetime import datetime, timezone

        from pentool.core.database import get_db

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

    # ── Project persistence ────────────────────────────────────────────────────

    def export_project_data(self) -> dict:
        results = self.get_results()
        return {
            "results": [
                {
                    "id": r.id,
                    "attack_id": r.attack_id,
                    "request_number": r.request_number,
                    "payload_values": r.payload_values,
                    "request_raw": r.request_raw,
                    "response_raw": r.response_raw,
                    "response_status": r.response_status,
                    "response_length": r.response_length,
                    "response_time_ms": r.response_time_ms,
                    "error": r.error,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in results
            ]
        }

    def import_project_data(self, data: dict) -> int:
        from datetime import datetime, timezone

        from pentool.modules.intruder import IntruderResult

        results_data = data.get("results", [])
        # Reset restored results list
        self._restored_results = []

        loaded = 0
        for rd in results_data:
            try:
                ts_raw = rd.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except Exception:
                    ts = datetime.now(timezone.utc)
                result = IntruderResult(
                    id=rd.get("id", ""),
                    attack_id=rd.get("attack_id", ""),
                    request_number=rd.get("request_number", 0),
                    payload_values=rd.get("payload_values", []),
                    request_raw=rd.get("request_raw", ""),
                    response_raw=rd.get("response_raw"),
                    response_status=rd.get("response_status"),
                    response_length=rd.get("response_length"),
                    response_time_ms=rd.get("response_time_ms"),
                    error=rd.get("error"),
                    timestamp=ts,
                )
                if hasattr(self, "_restored_results"):
                    self._restored_results.append(result)
                loaded += 1
            except Exception as exc:
                from pentool.core.logging import get_logger
                get_logger(__name__).warning(
                    "IntruderAPI.import_project_data: skip result: %s", exc
                )
        return loaded
