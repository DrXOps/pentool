"""One way to notify: `notify_user()` from `NotifyMixin` (step 9).

Three mechanisms used to coexist — `self.app.notify(...)` in screens, a `_notify()` wrapper in
one screen, `ModuleScreen.notify_to_user()` in the base — with different defaults and different
behaviour without an attached app. The migration is mechanical, so the guard is structural: no
screen/dialog/widget calls `app.notify` directly, and no wrapper with those names comes back.
`PentoolApp` itself stays the one place allowed to call Textual's `notify` (it is the
implementation `NotifyMixin` reaches for).
"""

from __future__ import annotations

import ast
from pathlib import Path

TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"


def _python_files():
    for path in sorted(TUI.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_no_screen_calls_app_notify_directly() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if path.name == "app.py":
            continue  # PentoolApp.notify is the implementation, not a caller
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            func = node.func
            # `.app.notify(...)` / `screen.app.notify(...)`: the three old paths.
            if func.attr == "notify" and isinstance(func.value, ast.Attribute) and func.value.attr == "app":
                offenders.append(f"{path.relative_to(TUI.parents[2]).as_posix()}:{node.lineno}")
    assert not offenders, (
        "toasts идут только через NotifyMixin.notify_user(); прямой app.notify обходит его "
        "поведение без приложения:\n  " + "\n  ".join(offenders)
    )


def test_old_notify_wrappers_are_gone() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"notify_to_user", "_notify"}:
                offenders.append(f"{path.relative_to(TUI.parents[2]).as_posix()}:{node.lineno} {node.name}")
    assert not offenders, (
        "второй способ уведомлять вернулся — используйте NotifyMixin.notify_user():\n  " + "\n  ".join(offenders)
    )
