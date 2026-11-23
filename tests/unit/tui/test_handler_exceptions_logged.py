"""ADR-6 item 1: in a handler `except Exception` carries a traceback, not a string.

ADR-6 item 1 requires `on_*`/`action_*`/`watch_*`/worker, having caught an
`Exception`, to record it via `logger.exception(...)` — with a traceback. The string
`logger.debug("...: %s", exc)` is not acceptable: it shows *what* failed but not
*where*, and in the TUI a handler is almost always the only place where a failure
can be seen at all.

The rule rested on discipline: 85 handlers logged a string,
and nothing stopped a new one from doing the same. The guard is mechanical and exact in
form: exactly four constructs give a traceback —

* ``logger.exception(...)`` / ``_log.exception(...)`` / ``log.exception(...)``;
* ``logger.error(..., exc_info=True)`` — the same thing, written the long way;
* ``err(exc, ...)`` / ``self.err(exc, ...)`` — ``pentool.core.error_guard``
  prints ``traceback.format_exception`` and notifies the user;
* ``raise`` — the exception goes to the dispatcher, which prints the traceback.

Everything else is a violation. Not "any log", but specifically a traceback: `debug` with
`%s` passes the guard only if `exc_info=True` is nearby.

The scope is as in ADR-6: methods named `on_`/`action_`/`watch_` and methods
whose body contains `run_worker` or the `@work` decorator (the worker entry point).
"""

from __future__ import annotations

import ast
from pathlib import Path

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

_HANDLER_PREFIXES = ("on_", "action_", "watch_")

#: Forms that yield a traceback in the log or at the dispatcher.
_TRACEBACK_FORMS = (
    "logger.exception",
    "_log.exception",
    "log.exception",
    "exc_info=True",
)
_ERR_CALLS = ("err(exc", "err(e,")


def _is_blind(handler: ast.ExceptHandler) -> bool:
    """``except Exception`` / ``except BaseException`` / bare ``except:``."""
    if handler.type is None:
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names = [t.id if isinstance(t, ast.Name) else getattr(t, "attr", "") for t in types]
    return any(name in {"Exception", "BaseException"} for name in names)


def _is_handler_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if node.name.startswith(_HANDLER_PREFIXES):
        return True
    source = ast.unparse(node)
    return "run_worker" in source or "@work" in source


def _has_traceback(handler: ast.ExceptHandler) -> bool:
    if any(isinstance(stmt, ast.Raise) for stmt in handler.body):
        return True
    body = "\n".join(ast.unparse(stmt) for stmt in handler.body)
    if any(form in body for form in _TRACEBACK_FORMS):
        return True
    return any(call in body for call in _ERR_CALLS)


def _offenders() -> list[str]:
    found: list[str] = []
    root = _TUI.parent.parent
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_handler_method(node):
                continue
            for handler in ast.walk(node):
                if not isinstance(handler, ast.ExceptHandler) or not _is_blind(handler):
                    continue
                if not _has_traceback(handler):
                    found.append(f"{rel}:{handler.lineno} in {node.name}()")
    return found


def test_handlers_log_a_traceback() -> None:
    offenders = _offenders()
    assert not offenders, (
        "хендлер в on_*/action_*/watch_*/воркере ловит `Exception` без трейсбека "
        "(ADR-6 п.1). Нужен `logger.exception(...)`, `err(exc, ...)`, "
        "`exc_info=True` или `raise`:\n  " + "\n  ".join(offenders)
    )


def _guard_module():
    import tests.unit.tui.test_handler_exceptions_logged as module

    return module


def test_guard_detects_a_planted_handler_without_traceback(tmp_path, monkeypatch) -> None:
    """The guard must fail on planted code — otherwise it checks nothing."""
    planted = tmp_path / "tui" / "planted.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(
        "def on_action(self, event):\n"
        "    try:\n"
        "        self.do_work()\n"
        "    except Exception as exc:\n"
        "        logger.debug('failed: %s', exc)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_guard_module(), "_TUI", planted.parent)
    offenders = _offenders()
    assert len(offenders) == 1
    assert "on_action" in offenders[0]

    # The guard leaves each of the four allowed forms alone.
    for body in (
        "        logger.exception('failed')\n",
        "        logger.error('failed: %s', exc, exc_info=True)\n",
        "        self.err(exc, 'failed')\n",
        "        raise\n",
    ):
        planted.write_text(
            "def on_action(self, event):\n    try:\n        self.do_work()\n    except Exception as exc:\n" + body,
            encoding="utf-8",
        )
        assert _offenders() == [], body

    # A handler outside the scope of the rule (not on_*/action_*/watch_* and not a
    # worker) is none of its business either: this is a helper method, its exception propagates.
    planted.write_text(
        "def helper(self):\n"
        "    try:\n"
        "        self.do_work()\n"
        "    except Exception as exc:\n"
        "        logger.debug('failed: %s', exc)\n",
        encoding="utf-8",
    )
    assert _offenders() == []
