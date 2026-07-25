"""IntruderService — оркестрирует IntruderAttack → EventBus."""

from __future__ import annotations

from typing import Callable

from pentool.api.intruder_api import IntruderAPI, IntruderConfig, IntruderResult
from pentool.core.event_bus import EventBus, get_event_bus
from pentool.core.events import IntruderFinished, IntruderResultAdded
from pentool.core.logging import get_logger

logger = get_logger(__name__)


class IntruderService:
    """Оркестрирует IntruderAttack + emit событий в EventBus.

    Не знает о Textual. Запускается через async @work.

    Использование:
        service = IntruderService(intruder_api, event_bus)
        await service.start_attack(config, on_result, on_progress)
    """

    def __init__(
        self,
        intruder_api: IntruderAPI,
        event_bus: EventBus | None = None,
        tui_loop=None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self._api = intruder_api
        self._bus = event_bus or get_event_bus()
        self._tui_loop = tui_loop
        self._on_log = on_log

    async def start_attack(
        self,
        config: IntruderConfig,
        on_result: Callable[[IntruderResult], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        turbo_mode: bool = False,
    ) -> list[IntruderResult]:
        def _on_result(result: IntruderResult) -> None:
            self._emit(IntruderResultAdded(result=result, source="intruder"))
            if on_result:
                try:
                    on_result(result)
                except Exception:
                    pass

        def _on_progress(done: int, total: int) -> None:
            if on_progress:
                try:
                    on_progress(done, total)
                except Exception:
                    pass

        try:
            await self._api.start_attack(config, _on_result, _on_progress, turbo_mode=turbo_mode)
            results = self._api.get_results()
            self._emit(IntruderFinished(
                total_results=len(results),
                stopped_early=False,
                source="intruder",
            ))
            return results
        except Exception as exc:
            logger.warning("IntruderService.start_attack error: %s", exc)
            self._emit(IntruderFinished(total_results=0, stopped_early=True, source="intruder"))
            return []

    def pause(self) -> None:
        self._api.pause()

    def resume(self) -> None:
        self._api.resume()

    def stop(self) -> None:
        self._api.stop()
        self._emit(IntruderFinished(
            total_results=len(self._api.get_results()),
            stopped_early=True,
            source="intruder",
        ))

    def _emit(self, event) -> None:
        try:
            if self._tui_loop and not self._tui_loop.is_closed():
                self._bus.emit_threadsafe(event, self._tui_loop)
            else:
                self._bus.emit(event)
        except Exception as exc:
            logger.debug("IntruderService._emit error: %s", exc)
