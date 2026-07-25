"""Публичный API Intruder-модуля для TUI и CLI."""

from __future__ import annotations



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


class IntruderAPI:

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._attack: IntruderAttack | None = None

    async def start_attack(
        self,
        config: IntruderConfig,
        on_result=None,
        on_progress=None,
        turbo_mode: bool = False,
    ) -> str:
        if turbo_mode:
            # Turbo Mode: connection pooling + Keep-Alive
            from pentool.modules.intruder_turbo import TurboIntruderAttack
            self._attack = TurboIntruderAttack(config)
        else:
            # Обычный режим
            self._attack = IntruderAttack(config, db_path=self._db_path)

        _on_result = on_result if on_result else lambda r: None
        _on_progress = on_progress if on_progress else lambda d, t: None

        import asyncio
        asyncio.create_task(self._attack.run(_on_result, _on_progress))
        return self._attack.attack_id if hasattr(self._attack, 'attack_id') else "turbo"

    async def pause(self) -> None:
        if self._attack:
            await self._attack.pause()

    async def resume(self) -> None:
        """Возобновить атаку после паузы."""
        if self._attack:
            await self._attack.resume()

    async def stop(self) -> None:
        if self._attack:
            await self._attack.stop()

    def get_results(self) -> list[IntruderResult]:
        if self._attack:
            # Turbo mode использует get_results(), обычный - results property
            if hasattr(self._attack, 'get_results'):
                return self._attack.get_results()
            return self._attack.results
        return []

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
        # Создаём фиктивный attack для хранения результатов
        # без реального запуска атаки
        if self._attack is None:
            # Ленивая инициализация — просто храним в атрибуте
            self._restored_results: list[IntruderResult] = []
        else:
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
