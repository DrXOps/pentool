"""F-015: закрытие вкладки Intruder обязано остановить её атаку.

`action_start_attack` создаёт атаку, кладёт её в состояние таба и запускает
воркер. Закрытие вкладки раньше только убирало pane из `TabbedContent`:
атака продолжала слать запросы по цели, которых пользователь уже не видит, а
воркер жил до конца `attack.run()`. То же при уходе с экрана — и там
`query_one("#intruder-tabs")` в `on_unmount` вообще не находил DOM, так что
даже список табов не читался.

Тесты держат настоящую атаку-двойника: она не завершается сама, поэтому
«остановили» и «не остановили» различимы по счётчику `stop()`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.widgets import ContentSwitcher

from pentool.tui.screens.intruder.screen import IntruderScreen


class _SpyAttack:
    """Атака-двойник: висит, пока её не отпустят.

    ``stop()`` только считает вызов. Отпускает ли он ``run()`` — параметр:
    с ``releases=False`` воркер снимается исключительно через
    ``workers.cancel_group``, и тогда тест различает «попросили встать» и
    «сняли воркер». Настоящая атака ведёт себя именно так: ``stop()``
    поднимает флаг внутри сетевого цикла и возвращается не сразу.
    """

    def __init__(self, releases: bool = True) -> None:
        self.stopped = 0
        self.started = 0
        self._releases = releases
        self._release = asyncio.Event()

    async def run(self, on_result, on_progress) -> None:
        self.started += 1
        await self._release.wait()

    async def stop(self) -> None:
        self.stopped += 1
        if self._releases:
            self._release.set()

    async def pause(self) -> None:
        return None

    async def resume(self) -> None:
        return None


@dataclass
class _FakeApi:
    attack: _SpyAttack

    def make_attack(self, config, turbo_mode: bool = False) -> _SpyAttack:
        return self.attack


class _App(App):
    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()


async def _settle(pilot, cycles: int = 8) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _screen_with_running_attack(pilot, releases: bool = True):
    """Довести экран до состояния «атака идёт» без сети и без БД."""
    screen = pilot.app.query_one(IntruderScreen)
    spy = _SpyAttack(releases=releases)
    screen._api = _FakeApi(attack=spy)  # type: ignore[assignment]
    screen._get_api = lambda: screen._api  # type: ignore[method-assign]

    tab = screen._active_tab
    assert tab is not None, "the screen must open with one tab"
    tab.attack_type = tab.attack_type  # noqa: B018 — keep the state object
    tab.template_text = "GET /§§ HTTP/1.1\r\nHost: example.com\r\n\r\n"

    # Минимальный путь без UI-валидации: то же, что делает action_start_attack
    # после сборки конфига.
    tab.attack = spy  # type: ignore[assignment]
    tab.running = True
    screen._live_attacks[tab.tab_id] = spy
    group = screen._attack_group(tab.tab_id)
    screen.run_worker(screen._run_attack(tab, spy), exclusive=False, name=group, group=group)
    await _settle(pilot)
    return screen, tab, spy


class TestClosingATabStopsItsAttack:
    async def test_closing_the_tab_asks_the_attack_to_stop(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot)
            assert spy.started == 1, "precondition: the attack worker must be running"

            # Нужна вторая вкладка: закрывать последнюю панель не даёт.
            screen._tc_panel.action_new_tab()
            await _settle(pilot)
            screen._tc_panel.switch_to(tab.tab_id)
            await _settle(pilot)

            screen._tc_panel.action_close_tab()
            await _settle(pilot)

            assert spy.stopped >= 1, (
                "the tab was closed but its attack kept running — the worker is "
                "cancelled only by name, and closing a tab never asked it to stop"
            )
            assert tab.tab_id not in screen._live_attacks, (
                "a closed tab's attack stayed registered — on_unmount would try to stop an attack that no longer exists"
            )
            assert tab.running is False

    async def test_the_worker_is_cancelled_not_just_asked(self) -> None:
        """Снять группу — значит не дождаться конца `attack.run()`.

        ``releases=False``: `stop()` не отпускает `run()`, поэтому воркер
        исчезает только если его действительно отменили.
        """
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot, releases=False)

            screen._stop_tab_attack(tab)
            await _settle(pilot)

            groups = {w.group for w in screen.workers._workers if w.group}
            assert screen._attack_group(tab.tab_id) not in groups, (
                "the attack worker is still registered: cancel_group never reached it"
            )


class TestLeavingTheScreenStopsAttacks:
    async def test_unmount_reaches_an_attack_whose_dom_is_already_gone(self) -> None:
        """`on_unmount` не может искать табы в DOM — только в своём словаре."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen, tab, spy = await _screen_with_running_attack(pilot)

            screen.on_unmount()
            await _settle(pilot)

            assert spy.stopped >= 1, "leaving the screen left its attack running"
            assert screen._live_attacks == {}
