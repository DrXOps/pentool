"""Снапшоты экранов TUI: визуальные регрессии.

Первый прогон (создать эталоны):
    pytest tests/snapshot/ --snapshot-update

Обычный прогон (сравнить с эталоном):
    pytest tests/snapshot/

Обновить эталон после осознанного изменения интерфейса:
    pytest tests/snapshot/ --snapshot-update

Окно всегда 200x50 — полный экран без обрезки виджетов. Эталоны хранит
`pytest-textual-snapshot`; кадр снимается только на замороженных часах и после
того, как экран перестал меняться (см. `helpers.py`).
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config
from tests.snapshot.helpers import SNAP_SIZE, make_app, settle


def _repeater_ready(app):
    """Активная вкладка Repeater собрала редактор *и* получила текст запроса.

    Обе половины важны: без редактора фотографировать нечего, кроме layout, а
    без текста редактор рисует пустую рамку — кадр устойчивый, поэтому проверка
    «экран перестал меняться» вернула бы его сразу и эталон закрепил бы пустоту.
    """
    from textual.css.query import NoMatches

    from pentool.tui.screens.repeater.screen import RepeaterScreen

    try:
        screen = app.query_one(RepeaterScreen)
        return bool(screen._editor().get_text())
    except (NoMatches, LookupError):
        return False


def _intruder_ready(app):
    """Редактор шаблона Intruder собран и держит запрос."""
    from textual.css.query import NoMatches

    from pentool.tui.screens.intruder.screen import IntruderScreen

    try:
        screen = app.query_one(IntruderScreen)
        return bool(screen._template_editor().get_text())
    except (NoMatches, LookupError):
        return False


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19095,
    )
    set_config(cfg)
    return cfg


@pytest.mark.snapshot
def test_repeater_screen(snap_compare) -> None:
    """Repeater: TabbedContent с вкладкой Tab 1 и двумя редакторами."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["R"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, ready=lambda: _repeater_ready(pilot.app), what="Repeater tab"),
    )


@pytest.mark.snapshot
def test_intruder_screen(snap_compare) -> None:
    """Intruder: тулбар Start/Pause/Stop, Positions+Payloads, Results."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["I"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, ready=lambda: _intruder_ready(pilot.app), what="Intruder template"),
    )


@pytest.mark.snapshot
def test_decoder_screen(snap_compare) -> None:
    """Decoder: заглушка этапа 13."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["D"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Decoder"),
    )


@pytest.mark.snapshot
def test_settings_screen(snap_compare) -> None:
    """Settings: подтабы Interface/Proxy/Hotkeys/Project."""
    app = make_app()
    assert snap_compare(
        app,
        press=["ctrl+comma"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Settings"),
    )


@pytest.mark.snapshot
def test_proxy_intercept_tab(snap_compare) -> None:
    """Proxy → вкладка Intercept: пустой перехват."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["P"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Proxy intercept"),
    )


@pytest.mark.snapshot
def test_repeater_with_request(snap_compare) -> None:
    """Repeater: реальный HTTP-запрос в редакторе."""
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    from pentool.utils.parser import ParsedRequest, build_http_request

    app = make_app()
    app._skip_project_guard = True

    async def load(pilot) -> None:
        await settle(pilot, what="Repeater before load")
        request = ParsedRequest(
            method="POST",
            url="http://target.example.com/api/login",
            headers={
                "Host": "target.example.com",
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJ0eXAiOiJKV1Q...",
            },
            body='{"username":"admin","password":"secret123"}',
        )
        pilot.app.query_one(RepeaterScreen).load_request(build_http_request(request))
        await settle(pilot, ready=lambda: _repeater_ready(pilot.app), what="Repeater tab")

    assert snap_compare(app, press=["R"], terminal_size=SNAP_SIZE, run_before=load)


@pytest.mark.snapshot
def test_intruder_with_markers(snap_compare) -> None:
    """Intruder: запрос с маркерами §§, разобранный в Positions."""
    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.utils.parser import ParsedRequest, build_http_request

    app = make_app()
    app._skip_project_guard = True

    async def load(pilot) -> None:
        await settle(pilot, what="Intruder before load")
        request = ParsedRequest(
            method="POST",
            url="http://target.example.com/login",
            headers={"Host": "target.example.com"},
            body="user=§admin§&pass=§secret§",
        )
        pilot.app.query_one(IntruderScreen).load_request(build_http_request(request))
        await settle(pilot, ready=lambda: _intruder_ready(pilot.app), what="Intruder template")

    assert snap_compare(app, press=["I"], terminal_size=SNAP_SIZE, run_before=load)


@pytest.mark.snapshot
def test_comparer_screen(snap_compare) -> None:
    """Comparer: сравнение двух ответов бок о бок."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["C"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Comparer"),
    )


@pytest.mark.snapshot
def test_sequencer_screen(snap_compare) -> None:
    """Sequencer: тулбар анализа энтропии токена."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["Q"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Sequencer"),
    )
