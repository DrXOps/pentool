"""`NotifyMixin` is the single way to notify, and the direct calls may only shrink."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pentool.tui.mixins.notify import NotifyMixin
from pentool.tui.screens.module_screen import ModuleScreen

ROOT = Path(__file__).resolve().parents[3]
SCREENS = ROOT / "pentool/tui/screens"

#: Call sites that still reach for `self.app.notify(...)` directly. Migrate screens one by one;
#: this number may only go down.
DIRECT_NOTIFY_BUDGET = 77


def _direct_calls() -> int:
    result = subprocess.run(
        ["grep", "-rho", "self.app.notify(", str(SCREENS)],
        capture_output=True,
        text=True,
        check=False,
    )
    return len(result.stdout.splitlines())


def test_module_screen_exposes_the_mixin() -> None:
    assert issubclass(ModuleScreen, NotifyMixin), "ModuleScreen должен наследовать NotifyMixin"
    assert hasattr(ModuleScreen, "notify_user"), "нет единого метода уведомления"


def test_notify_never_raises_without_an_app() -> None:
    class _Bare(NotifyMixin):
        pass

    _Bare().notify_user("сообщение")  # no app, no exception — the message is only logged


def test_direct_app_notify_calls_do_not_grow() -> None:
    calls = _direct_calls()
    assert calls <= DIRECT_NOTIFY_BUDGET, (
        f"прямых self.app.notify(...) стало больше: {calls} (было {DIRECT_NOTIFY_BUDGET}); используйте notify_user()"
    )
