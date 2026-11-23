"""TUI screen snapshots: visual regressions.

First run (create the baselines):
    pytest tests/snapshot/ --snapshot-update

Regular run (compare against the baseline):
    pytest tests/snapshot/

Update the baseline after an intentional UI change:
    pytest tests/snapshot/ --snapshot-update

The window is always 200x50 — the full screen with no widget clipping. Baselines
are stored by `pytest-textual-snapshot`; a frame is captured only on the frozen
clock and after the screen has stopped changing (see `helpers.py`).
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config
from tests.snapshot.helpers import SNAP_SIZE, make_app, settle


def _repeater_ready(app):
    """The active Repeater tab has assembled its editor *and* received the request text.

    Both halves matter: without the editor there is nothing to photograph but the layout, and
    without the text the editor draws an empty frame — the frame is stable, so the "screen
    stopped changing" check would return it at once and the baseline would pin the emptiness.
    """
    from textual.css.query import NoMatches

    from pentool.tui.screens.repeater.screen import RepeaterScreen

    try:
        screen = app.query_one(RepeaterScreen)
        return bool(screen._editor().get_text())
    except (NoMatches, LookupError):
        return False


def _intruder_ready(app):
    """The Intruder template editor is assembled and holds the request."""
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
    """Repeater: TabbedContent with the Tab 1 tab and two editors."""
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
    """Intruder: Start/Pause/Stop toolbar, Positions+Payloads, Results."""
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
    """Decoder: stage 13 placeholder."""
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
    """Settings: Interface/Proxy/Hotkeys/Project subtabs."""
    app = make_app()
    assert snap_compare(
        app,
        press=["ctrl+comma"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Settings"),
    )


@pytest.mark.snapshot
def test_proxy_intercept_tab(snap_compare) -> None:
    """Proxy → Intercept tab: empty interception."""
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
    """Repeater: a real HTTP request in the editor."""
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
    """Intruder: a request with §§ markers parsed into Positions."""
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
    """Comparer: side-by-side comparison of two responses."""
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
    """Sequencer: token entropy analysis toolbar."""
    app = make_app()
    app._skip_project_guard = True
    assert snap_compare(
        app,
        press=["Q"],
        terminal_size=SNAP_SIZE,
        run_before=lambda pilot: settle(pilot, what="Sequencer"),
    )
