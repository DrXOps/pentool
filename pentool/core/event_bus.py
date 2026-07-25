"""Event Bus — внутренняя шина событий приложения."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque
from typing import Callable, TypeVar

from pentool.core.events import AppEvent
from pentool.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=AppEvent)


class EventBus:
    """Thread-safe шина событий с историей.

    Attributes:
        _subscribers:  Словарь type → список обработчиков.
        _history:      Кольцевой буфер всех эмиченных событий.
        _lock:         RLock для thread-safe операций.
    """

    def __init__(self, max_history: int = 10_000) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._history: deque[AppEvent] = deque(maxlen=max_history)
        self._lock = threading.RLock()

    # ── subscribe / unsubscribe ────────────────────────────────────────────────

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Подписаться на события заданного типа.

        Args:
            event_type: Класс события (подкласс AppEvent).
            handler:    Функция-обработчик, принимающая экземпляр события.
        """
        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """Отписаться от событий.

        Безопасен при повторном вызове — не бросает исключение если
        обработчик не был подписан.
        """
        with self._lock:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

    def unsubscribe_all(self, handler: Callable) -> None:
        """Отписать обработчик от всех типов событий сразу."""
        with self._lock:
            for handlers in self._subscribers.values():
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass

    # ── emit ──────────────────────────────────────────────────────────────────

    def emit(self, event: AppEvent) -> None:
        """Синхронный emit из основного потока.

        Вызывает всех подписчиков немедленно (в том же потоке).
        Сохраняет событие в историю.

        Args:
            event: Экземпляр события (подкласс AppEvent).
        """
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(type(event), []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "EventBus: handler %s raised %s for event %s",
                    handler, exc, type(event).__name__,
                )

    def emit_threadsafe(
        self,
        event: AppEvent,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Thread-safe emit из worker-потока.

        Сохраняет событие в историю немедленно (под локом),
        затем планирует вызов обработчиков в event loop через
        call_soon_threadsafe.

        Args:
            event: Экземпляр события.
            loop:  Event loop основного потока (app._loop).
        """
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(type(event), []))

        if not handlers:
            return

        def _dispatch() -> None:
            for handler in handlers:
                try:
                    handler(event)
                except Exception as exc:
                    logger.warning(
                        "EventBus: threadsafe handler %s raised %s for %s",
                        handler, exc, type(event).__name__,
                    )

        try:
            loop.call_soon_threadsafe(_dispatch)
        except RuntimeError:
            # loop закрыт — приложение завершается
            pass

    # ── history / replay ──────────────────────────────────────────────────────

    def get_history(
        self,
        event_type: type | None = None,
        limit: int = 0,
    ) -> list[AppEvent]:
        with self._lock:
            events = list(self._history)

        if event_type is not None:
            events = [e for e in events if isinstance(e, event_type)]

        if limit > 0:
            events = events[-limit:]

        return events

    def replay(
        self,
        handler: Callable,
        event_type: type,
        limit: int = 0,
    ) -> None:
        """Воспроизвести историю событий для нового подписчика.

        Вызывает handler для каждого сохранённого события заданного типа.
        Полезно при инициализации экрана, который подключился позже
        (например, Dashboard после запуска сканирования).

        Args:
            handler:    Функция-обработчик.
            event_type: Тип событий для replay.
            limit:      Максимум событий (0 = все).
        """
        events = self.get_history(event_type=event_type, limit=limit)
        for event in events:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "EventBus.replay: handler %s raised %s", handler, exc
                )

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ── stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Статистика для отладки."""
        with self._lock:
            return {
                "history_size":    len(self._history),
                "subscriber_types": len(self._subscribers),
                "total_handlers":  sum(len(v) for v in self._subscribers.values()),
            }


# ── Глобальный синглтон ────────────────────────────────────────────────────────

_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """Сбросить глобальный синглтон (только для тестов)."""
    global _bus
    with _bus_lock:
        _bus = None
