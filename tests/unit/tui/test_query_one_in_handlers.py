"""Guards for `query_one` in event handlers (T-016).

Context: the TUI now mounts screens and sub-tabs lazily, so "the widget is not in the
tree yet" is a normal state, not a bug. An unprotected `query_one` in a timer tick, a
header redraw or a node handler therefore crashes the app on a legitimate race.

The rule this test enforces is not "never call `query_one`": a dialog's `on_mount`
reads widgets its own `compose()` created, and a missing one there IS a programmer
error that must stay loud. So there is a small, explicit allowlist (dialogs whose
children are created by the same compose) and a ratchet on everything else: the count
may only go down.

The migrated sites (status bar ticks, the header redraw, Target's details panel,
Intruder's toolbar buttons, PRO scanner export) use `safe_query_one` or read the
object from the event instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROOTS = [ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui"]

#: Handlers allowed to use a bare `query_one`: the widgets are created by the very
#: same `compose()`, so absence means the dialog is broken and must be seen in a
#: traceback rather than swallowed.
ALLOWED_FILES = {
    "pentool/tui/dialogs/comment_dialog.py",
    "pentool/tui/dialogs/file_selector.py",
    "pentool/tui/dialogs/intruder_generate.py",
    "pentool/tui/dialogs/intruder_input.py",
    "pentool/tui/dialogs/load_from_proxy.py",
    "pentool/tui/dialogs/project_dialog.py",
    "pentool/tui/screens/settings/hotkeys.py",
}

#: Ratchet: the current number of bare `query_one` calls in handlers outside the
#: allowlist. Lower it when a site is migrated; never raise it.
MAX_UNPROTECTED = 0

HANDLER_MARKERS = ("_on_", "_tick", "_flush", "_refresh", "_sync", "_update")


def _protected_lines(tree: ast.AST) -> set[int]:
    covered: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handlers = " ".join(ast.dump(handler) for handler in node.handlers)
            if any(marker in handlers for marker in ("NoMatches", "Exception", "WrongType")):
                start = node.lineno
                end = max((child.lineno for child in ast.walk(node) if hasattr(child, "lineno")), default=start)
                covered.update(range(start, end + 1))
    return covered


def _find_unprotected() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for base in ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in ALLOWED_FILES:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            guarded = _protected_lines(tree)
            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                is_handler = func.name.startswith(("on_", "_on_")) or any(
                    marker in func.name for marker in HANDLER_MARKERS
                )
                if not is_handler:
                    continue
                for node in ast.walk(func):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "query_one"
                        and node.lineno not in guarded
                    ):
                        rows.append((relative, node.lineno, func.name))
    return rows


def test_unprotected_query_one_count_does_not_grow() -> None:
    rows = _find_unprotected()
    assert len(rows) <= MAX_UNPROTECTED, (
        "a bare query_one appeared in an event handler — a lazy mount will crash it "
        "(use safe_query_one, or read the widget from the event):\n  "
        + "\n  ".join(f"{path}:{line} in {func}()" for path, line, func in sorted(rows))
    )


def test_allowlist_is_limited_to_dialog_compose_children() -> None:
    """The allowlist must stay small and explainable: dialogs only."""
    for relative in ALLOWED_FILES:
        assert "dialogs/" in relative or "settings/hotkeys" in relative, (
            f"{relative} does not belong in the allowlist: outside a dialog, a missing "
            "widget is a lazy-mount race, not a programmer error"
        )
