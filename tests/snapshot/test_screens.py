"""Snapshot tests: TUI visual regressions.

Run (first time — create baseline):
    pytest tests/snapshot/ -v

Subsequent run (compare with baseline):
    pytest tests/snapshot/ -v

Update baseline after intentional UI changes:
    pytest tests/snapshot/ --snapshot-update

Window size is always 200x50 — full screen without widget clipping.
Snapshots are stored in tests/snapshot/snaps/*.svg

Two determinism rules, both enforced here rather than hidden in normalisation:

* the clock is frozen (``PentoolApp(now=...)``) — the status bar prints the
  wall time every second, and erasing it with a regex would also erase a
  change to the time format;
* the screenshot is taken once the screen stops changing (``settle``) —
  a guessed number of ``pilot.pause()`` calls is what made the Repeater
  baseline flaky, because its editor fills one frame after the layout.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from pentool.core.config import Config, set_config
from tests.snapshot.conftest import settle

# Standard size for all snapshots: full window
SNAP_SIZE = (200, 50)


class _FrozenClock(datetime):
    """``datetime`` whose ``now()`` is fixed.

    Subclassing rather than stubbing keeps the other classmethods —
    ``fromtimestamp``/``strptime`` — working, so widgets that format file
    mtimes (dashboard, file selector) still behave like production.
    """

    @classmethod
    def now(cls, tz=None) -> datetime:
        return cls(2026, 1, 1, 12, 0, 0)


def _app():
    """A fresh app on the frozen clock."""
    from pentool.tui.app import PentoolApp

    return PentoolApp(now=_FrozenClock.now)


def _repeater_ready(app):
    """The active Repeater tab has mounted its editor *and* its request text.

    Both halves matter. Without the editor there is nothing to photograph but
    the layout; without the text the editor paints an empty box, which is a
    stable frame — a "has the screen stopped changing" poll returns it
    immediately and commits an empty baseline.
    """
    from textual.css.query import NoMatches

    from pentool.tui.screens.repeater.screen import RepeaterScreen

    screen = app.query_one(RepeaterScreen)
    try:
        return bool(screen._editor().get_text())
    except (NoMatches, LookupError):
        return False


def _intruder_ready(app):
    """Intruder's template editor is mounted and holds the request."""
    from textual.css.query import NoMatches

    from pentool.tui.screens.intruder.screen import IntruderScreen

    screen = app.query_one(IntruderScreen)
    try:
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
@pytest.mark.asyncio
async def test_repeater_screen(assert_snapshot) -> None:
    """Repeater screen: TabbedContent with Tab 1, two editors."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("R")
        svg = await settle(app, pilot, ready=lambda: _repeater_ready(app), what="Repeater tab")
    assert_snapshot(svg, "repeater_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_intruder_screen(assert_snapshot) -> None:
    """Intruder screen: Start/Pause/Stop toolbar, Positions+Payloads, Results."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("I")
        svg = await settle(app, pilot, ready=lambda: _intruder_ready(app), what="Intruder template")
    assert_snapshot(svg, "intruder_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_decoder_screen(assert_snapshot) -> None:
    """Decoder screen: Coming in Stage 13 stub."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("D")
        svg = await settle(app, pilot)
    assert_snapshot(svg, "decoder_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_settings_screen(assert_snapshot) -> None:
    """Settings screen: Interface/Proxy/Hotkeys/Project subtabs."""
    app = _app()
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+comma")
        svg = await settle(app, pilot)
    assert_snapshot(svg, "settings_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_proxy_intercept_tab(assert_snapshot) -> None:
    """Proxy → Intercept tab: empty intercept."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("P")
        svg = await settle(app, pilot)
    assert_snapshot(svg, "proxy_intercept_tab")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_repeater_with_request(assert_snapshot) -> None:
    """Repeater: real HTTP request loaded into editor."""
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    from pentool.utils.parser import ParsedRequest, build_http_request

    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()

        req = ParsedRequest(
            method="POST",
            url="http://target.example.com/api/login",
            headers={
                "Host": "target.example.com",
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJ0eXAiOiJKV1Q...",
            },
            body='{"username":"admin","password":"secret123"}',
        )
        screen = app.query_one(RepeaterScreen)
        screen.load_request(build_http_request(req))
        svg = await settle(app, pilot, ready=lambda: _repeater_ready(app), what="Repeater tab")
    assert_snapshot(svg, "repeater_with_request")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_intruder_with_markers(assert_snapshot) -> None:
    """Intruder: request with §§ markers loaded into Positions."""
    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.utils.parser import ParsedRequest, build_http_request

    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("I")
        await pilot.pause()

        req = ParsedRequest(
            method="POST",
            url="http://target.example.com/login",
            headers={"Host": "target.example.com"},
            body="user=§admin§&pass=§secret§",
        )
        screen = app.query_one(IntruderScreen)
        screen.load_request(build_http_request(req))
        svg = await settle(app, pilot, ready=lambda: _intruder_ready(app), what="Intruder template")
    assert_snapshot(svg, "intruder_with_markers")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_comparer_screen(assert_snapshot) -> None:
    """Comparer screen: side-by-side diff."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("C")
        svg = await settle(app, pilot)
    assert_snapshot(svg, "comparer_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_sequencer_screen(assert_snapshot) -> None:
    """Sequencer screen: token entropy analysis toolbar."""
    app = _app()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("Q")
        svg = await settle(app, pilot)
    assert_snapshot(svg, "sequencer_screen")
