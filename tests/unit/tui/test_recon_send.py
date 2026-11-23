"""Stage 1 of the Recon integration: the "send to Recon" surface.

The rules under test:

* without the `ai_discovery` feature the app refuses politely and the context menu does
  not offer Recon at all — a menu item that only leads to "buy a licence" is noise;
* with the feature, `open_recon()` mounts the module and calls `prepare_recon()` with the
  requested stage, and `run=True` is passed only for stage modes;
* the menu item takes the host out of the raw request, not the whole URL.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin


def _license(features: list[str], plan: str = "pro", valid: bool = True) -> SimpleNamespace:
    def has_feature(name: str) -> bool:
        return valid and name in features

    return SimpleNamespace(
        valid=valid,
        plan=plan,
        features=features,
        has_feature=has_feature,
        is_pro=lambda: valid and plan in ("pro", "enterprise"),
    )


class _ReconScreenStub:
    def __init__(self) -> None:
        self.prepare_recon = MagicMock(return_value=True)


def _app_stub(screen: _ReconScreenStub | None) -> MagicMock:
    app = MagicMock()
    app.ensure_module_screen = MagicMock(return_value=screen)

    async def ensure(module_id: str):
        return screen

    app.ensure_module_screen = MagicMock(side_effect=ensure)
    return app


def test_open_recon_without_feature_returns_false_and_explains() -> None:
    from pentool.tui.app import PentoolApp

    app = PentoolApp.__new__(PentoolApp)
    app.notify = MagicMock()
    app.action_switch_module = MagicMock()
    app.ensure_module_screen = MagicMock()

    with patch("pentool.core.license.get_session_license", return_value=_license([], plan="free")):
        started = asyncio.run(app.open_recon("example.com", mode="subdomains", run=True))

    assert started is False
    app.ensure_module_screen.assert_not_called()
    app.action_switch_module.assert_not_called()
    (message,) = app.notify.call_args.args
    assert "PRO" in message


def test_open_recon_prepares_screen_with_mode_and_run_flag() -> None:
    from pentool.tui.app import PentoolApp

    screen = _ReconScreenStub()
    app = PentoolApp.__new__(PentoolApp)
    app.notify = MagicMock()
    app.action_switch_module = MagicMock()
    app.ensure_module_screen = MagicMock(side_effect=lambda module_id: asyncio.sleep(0, result=screen))

    with patch(
        "pentool.core.license.get_session_license",
        return_value=_license(["ai_discovery"]),
    ):
        started = asyncio.run(app.open_recon("https://example.com/path", mode="fuzz", run=True))

    assert started is True
    app.action_switch_module.assert_called_once_with("recon")
    screen.prepare_recon.assert_called_once_with("https://example.com/path", mode="fuzz", run=True)


def test_open_recon_reports_missing_module() -> None:
    from pentool.tui.app import PentoolApp

    app = PentoolApp.__new__(PentoolApp)
    app.notify = MagicMock()
    app.action_switch_module = MagicMock()
    app.ensure_module_screen = MagicMock(side_effect=lambda module_id: asyncio.sleep(0, result=None))

    with patch("pentool.core.license.get_session_license", return_value=_license(["ai_discovery"])):
        started = asyncio.run(app.open_recon("example.com"))

    assert started is False
    assert "unavailable" in app.notify.call_args.args[0].lower()


class _MenuHost(RequestContextMenuMixin):
    """Minimal host: only what the mixin touches when building items."""

    def __init__(self) -> None:
        self.app = MagicMock()

    def _cm_get_raw_request(self) -> str:
        return "GET /a HTTP/1.1\r\nHost: api.example.com\r\n\r\n"


def _actions(host: _MenuHost) -> list[str]:
    return [action for action, _label in host._cm_build_items()]


def test_menu_hides_recon_without_the_feature() -> None:
    host = _MenuHost()
    with patch("pentool.core.license.get_session_license", return_value=_license([], plan="free")):
        actions = _actions(host)
    assert not [action for action in actions if action.startswith("recon_")]


def test_menu_shows_all_recon_stages_with_the_feature() -> None:
    host = _MenuHost()
    with patch("pentool.core.license.get_session_license", return_value=_license(["ai_discovery"])):
        actions = _actions(host)
    assert [action for action in actions if action.startswith("recon_")] == [
        "recon_domain",
        "recon_subdomains",
        "recon_endpoints",
        "recon_realip",
        "recon_fuzz",
    ]


def test_recon_menu_action_sends_only_the_host() -> None:
    host = _MenuHost()
    calls: list[tuple[str, str, bool]] = []

    async def open_recon(target: str, mode: str, run: bool) -> bool:
        calls.append((target, mode, run))
        return True

    host.app.open_recon = open_recon

    asyncio.run(host._cm_do_send_recon("GET /x HTTP/1.1\r\nHost: api.example.com\r\n\r\n", "domain"))

    assert calls == [("api.example.com", "domain", False)]


def test_recon_stage_action_starts_the_run() -> None:
    host = _MenuHost()
    calls: list[tuple[str, str, bool]] = []

    async def open_recon(target: str, mode: str, run: bool) -> bool:
        calls.append((target, mode, run))
        return True

    host.app.open_recon = open_recon

    asyncio.run(host._cm_do_send_recon("GET /x HTTP/1.1\r\nHost: api.example.com\r\n\r\n", "subdomains"))

    assert calls == [("api.example.com", "subdomains", True)]
