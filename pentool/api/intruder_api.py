"""Public API of the Intruder module for TUI and CLI."""

from __future__ import annotations

import asyncio

from pentool.api.base_api import ExportableAPI
from pentool.api.intruder_repository import IntruderRepository
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

    def __init__(self, db_path: str | None = None, http_client=None) -> None:
        self._db_path = db_path
        # Optional injected HTTPClient (DIP — see
        # MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.2).
        # IntruderAttack already accepted this as an optional constructor
        # param (reusing one HTTPClient/connection pool across the whole
        # attack — see the БАГ-D fix in modules/intruder.py) but IntruderAPI
        # had no way to pass one in — it always let IntruderAttack create
        # its own from scratch. Threading it through here just extends the
        # existing `http_client=None` pattern one layer up, matching how
        # ScannerAPI(db_path, http_client) already works. Does not apply to
        # Turbo mode — TurboIntruderAttack manages its own aiohttp session
        # pool internally by design (Keep-Alive tuning specific to Turbo),
        # unrelated to this DI change.
        self._http_client = http_client
        self._attack: IntruderAttack | None = None
        self._task: asyncio.Task | None = None
        self._restored_results: list = []
        # SQL for tab state / attack results lives in IntruderRepository
        # (see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.6)
        # — mirrors ScannerTabRepository, the same extraction already done
        # for Scanner. IntruderAPI keeps its existing public method names
        # as a thin facade so no caller needs to change.
        self._repo = IntruderRepository(db_path=db_path)

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
            self._attack = IntruderAttack(config, db_path=self._db_path, http_client=self._http_client)

        _on_result = on_result if on_result else lambda r: None
        _on_progress = on_progress if on_progress else lambda d, t: None

        self._task = asyncio.create_task(self._attack.run(_on_result, _on_progress))
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return self._attack.attack_id if hasattr(self._attack, 'attack_id') else "turbo"

    async def pause(self) -> None:
        """Pause the running attack, if supported.

        TurboIntruderAttack has no pause/resume — Turbo mode intentionally
        runs to completion or stop() only (see modules/intruder_turbo.py).
        Before this API method was actually reachable from IntruderScreen,
        turbo_mode was silently never honored there (a pre-existing bug —
        see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.7),
        so Pause/Resume during a real Turbo run was never exercised. Guard
        with hasattr so enabling real Turbo mode doesn't crash Pause.
        """
        if self._attack and hasattr(self._attack, "pause"):
            await self._attack.pause()

    async def resume(self) -> None:
        """Resume the attack after a pause, if supported (see pause() note)."""
        if self._attack and hasattr(self._attack, "resume"):
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
        await self._repo.save_state(tab_name, template, attack_type, payloads)

    async def load_state(self, tab_name: str) -> dict | None:
        """Load Intruder tab state from DB."""
        return await self._repo.load_state(tab_name)

    async def save_result(self, result: IntruderResult, project_id: int | None = None) -> None:
        """Save a single intruder result to DB."""
        await self._repo.save_result(result, project_id)

    async def get_results_from_db(
        self,
        attack_id: str | None = None,
        limit: int = 1000,
    ) -> list[IntruderResult]:
        """Load intruder results from DB."""
        return await self._repo.get_results(attack_id, limit)

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
