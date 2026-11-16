"""Helpers for the screenshot suite.

Сравнением и хранением эталонов занимается `pytest-textual-snapshot` (F-032).
Здесь только то, чего библиотека знать не может:

* **Замороженные часы.** Статус-бар печатает время раз в секунду, поэтому два
  запуска никогда не совпадут по байтам. Приложение принимает часы через шов
  `PentoolApp(now=...)`; стирать время регуляркой из SVG нельзя — вместе с ним
  исчезла бы и настоящая регрессия формата времени.
* **Ожидание готовности и покоя.** Кадр для эталона снимается, когда экран уже
  собрался (`ready`) и перестал меняться (`quiet` подряд одинаковых экспортов).
  Скриншот после угаданного числа `pilot.pause()` — это лотерея: тело вкладки
  Repeater собирается цепочкой `call_after_refresh`, и половина прогонов
  фотографировала пустой редактор.
"""

from __future__ import annotations

from datetime import datetime

#: Полное окно: ни один виджет не обрезан.
SNAP_SIZE = (200, 50)


class FrozenClock(datetime):
    """``datetime``, у которого ``now()`` фиксирован.

    Наследование, а не подмена модуля: остальные classmethod'ы
    (`fromtimestamp`, `strptime`) продолжают работать, поэтому виджеты,
    печатающие mtime файлов, ведут себя как в продакшене.
    """

    @classmethod
    def now(cls, tz=None) -> datetime:
        return cls(2026, 1, 1, 12, 0, 0)


def make_app():
    """Свежее приложение на замороженных часах."""
    from pentool.tui.app import PentoolApp

    return PentoolApp(now=FrozenClock.now)


async def wait_for(pilot, predicate, *, frames: int = 60, what: str = "condition") -> None:
    """Ждать выполнения ``predicate()`` кадр за кадром."""
    for _ in range(frames):
        if predicate():
            return
        await pilot.pause()
    raise AssertionError(f"{what} did not become true within {frames} frames")


async def settle(pilot, ready=None, *, quiet: int = 3, frames: int = 60, what: str = "screen") -> None:
    """Дождаться кадра, который достоин стать эталоном.

    Нужны оба условия. Готовность (`ready`) — потому что неподвижный экран ещё
    не значит правильный: несобранное тело вкладки тоже неподвижно. Покой
    (`quiet` одинаковых экспортов подряд) — потому что иначе снимок попадает в
    середину анимации или позднего layout.
    """
    if ready is not None:
        await wait_for(pilot, ready, frames=frames, what=f"{what} readiness")
    app = pilot.app
    previous = None
    stable = 0
    for _ in range(frames):
        await pilot.pause()
        current = app.export_screenshot()
        stable = stable + 1 if current == previous else 0
        if stable >= quiet:
            return
        previous = current
    raise AssertionError(
        f"{what} never held still for {quiet} frames in {frames} — a timer or animation is still running"
    )
