"""Regression T-019: saving an attack result must not crash the screen.

The log of 2026-11-19 repeated:
``FATAL EXCEPTION: IntruderScreen._auto_save_result() takes 2 positional
arguments but 3 were given`` — the call passed ``tab`` as the second argument
while the method accepted only ``result``. The attack died on its first
response.

The test does not mount Textual: it pins the call contract (arguments) and that
``tab_uid`` reaches the API — exactly what was broken.
"""

from __future__ import annotations

from typing import Any

import pytest

from pentool.tui.screens.intruder.screen import IntruderScreen


class _FakeTab:
    tab_uid = "intruder-tab-7"


class _FakeApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def save_result(self, result, project_id=None, tab_uid=""):  # noqa: ANN001, ANN201
        self.calls.append({"result": result, "project_id": project_id, "tab_uid": tab_uid})
        return "coro"


@pytest.fixture()
def bare_screen(monkeypatch):
    """Screen without mounting: only the parts the save path needs."""
    screen = object.__new__(IntruderScreen)
    api = _FakeApi()
    saved: list[tuple[Any, str]] = []

    monkeypatch.setattr(screen, "_get_api", lambda: api, raising=False)
    monkeypatch.setattr(
        screen,
        "_start_save_worker",
        lambda coro, name: saved.append((coro, name)),
        raising=False,
    )
    # `app` is a read-only Textual property, so patch it on the class.
    monkeypatch.setattr(IntruderScreen, "app", property(lambda _self: type("App", (), {"project_id": 42})()))
    return screen, api, saved


def test_auto_save_result_accepts_tab_argument(bare_screen) -> None:
    """Exactly the call that used to fail: (result, tab)."""
    screen, api, _ = bare_screen
    screen._auto_save_result("result-object", _FakeTab())  # no TypeError

    assert len(api.calls) == 1
    assert api.calls[0]["project_id"] == 42


def test_auto_save_result_passes_tab_uid_to_api(bare_screen) -> None:
    screen, api, _ = bare_screen
    screen._auto_save_result("r", _FakeTab())

    assert api.calls[0]["tab_uid"] == "intruder-tab-7", "the result must land in its own tab"


def test_auto_save_result_without_tab_still_works(bare_screen) -> None:
    """A call without ``tab`` (the old path) must stay valid."""
    screen, api, _ = bare_screen
    screen._auto_save_result("r")

    assert api.calls[0]["tab_uid"] == ""


def test_auto_save_result_survives_api_failure(bare_screen, monkeypatch) -> None:
    """A save failure is logged but does not escape."""
    screen, _, _ = bare_screen

    def boom(*_a, **_kw):
        raise RuntimeError("db is gone")

    monkeypatch.setattr(screen, "_get_api", lambda: type("Api", (), {"save_result": boom})())
    screen._auto_save_result("r", _FakeTab())  # must not raise
