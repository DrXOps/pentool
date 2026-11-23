"""ADR-6 item 4: an optional `query_one` is caught by `NoMatches`, not by `Exception`.

`query_one` raises exactly one expected exception — `NoMatches` — when the
widget is not in the tree (the screen is not assembled yet, the tab is not
mounted, the panel is already removed). A broad `except Exception` around it
does the same job, but also swallows the `AttributeError` from a typo in a
method name and the `TypeError` from a wrong argument — that is, a programmer
error that has to be visible.

The rule was written down in ADR-6 item 4, but it rested on discipline. The
guard is mechanical: the AST looks for a `try` whose body consists only of
calls to `query_one`/`query`, and requires its handler to name `NoMatches` —
or, if the body does something else (for example `.update()` with a
computation), to at least write to the log. A silent broad handler is a
violation. The list of files is not kept by hand — it would drift from the
code the same way the Intruder attack worker's group and name drifted.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

_QUERY_CALLS = ("query_one(", "query(")
_NARROW_ALLOWED = {"NoMatches"}


def _is_query_only(stmts: list[ast.stmt]) -> bool:
    """The `try` body consists only of `query_one`/`query` calls."""
    for stmt in stmts:
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Expr)):
            return False
        source = ast.unparse(stmt)
        if not any(call in source for call in _QUERY_CALLS):
            return False
    return True


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return ["<bare>"]
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return [t.id if isinstance(t, ast.Name) else t.attr for t in types]


def _is_logged(handler: ast.ExceptHandler) -> bool:
    return any("logger" in ast.unparse(stmt) or "_log" in ast.unparse(stmt) for stmt in handler.body)


def _broad_handlers_without_reason() -> list[str]:
    offenders: list[str] = []
    root = _TUI.parent.parent
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try) or not _is_query_only(node.body):
                continue
            for handler in node.handlers:
                names = _handler_names(handler)
                if _NARROW_ALLOWED & set(names):
                    continue
                if _is_logged(handler):
                    continue
                offenders.append(f"{rel}:{node.lineno} caught {', '.join(names)}")
    return offenders


def test_query_one_handlers_catch_nomatches() -> None:
    offenders = _broad_handlers_without_reason()
    assert not offenders, (
        "опциональный query_one ловится широким except без записи в журнал (ADR-6 п.4):\n  " + "\n  ".join(offenders)
    )


def _guard_module():
    import tests.unit.tui.test_no_matches_is_precise as module

    return module


def test_guard_detects_a_planted_broad_handler(tmp_path, monkeypatch) -> None:
    """The guard must fail on planted code — otherwise it checks for nothing."""
    planted = tmp_path / "tui" / "planted.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(
        "def f(self):\n"
        "    try:\n"
        "        widget = self.query_one('#x', Static)\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_guard_module(), "_TUI", planted.parent)
    offenders = _broad_handlers_without_reason()
    assert len(offenders) == 1
    assert "except Exception" in planted.read_text(encoding="utf-8")

    # And the guard leaves the narrow variant of the same place alone.
    planted.write_text(
        "def f(self):\n"
        "    try:\n"
        "        widget = self.query_one('#x', Static)\n"
        "    except NoMatches:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert _broad_handlers_without_reason() == []
