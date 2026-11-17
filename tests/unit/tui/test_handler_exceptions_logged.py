"""ADR-6 п.1: в хендлере `except Exception` несёт трейсбек, а не строку.

Пункт 1 ADR-6 требует, чтобы `on_*`/`action_*`/`watch_*`/воркер, поймав
`Exception`, записал её через `logger.exception(...)` — с трейсбеком. Строка
`logger.debug("...: %s", exc)` не годится: по ней видно, *что* упало, но не
*где*, а в TUI обработчик — это почти всегда единственное место, где сбой
вообще можно увидеть.

Правило держалось на дисциплине: 85 хендлеров писали в журнал строкой,
и ничто не мешало новому сделать так же. Гвард механический и точный по
форме: трейсбек дают ровно четыре записи —

* ``logger.exception(...)`` / ``_log.exception(...)`` / ``log.exception(...)``;
* ``logger.error(..., exc_info=True)`` — то же самое, записанное длинно;
* ``err(exc, ...)`` / ``self.err(exc, ...)`` — ``pentool.core.error_guard``
  печатает ``traceback.format_exception`` и уведомляет пользователя;
* ``raise`` — исключение уходит диспетчеру, трейсбек напечатает он.

Всё остальное — нарушение. Не «любой лог», а именно трейсбек: `debug` с
`%s` проходит гвард только если рядом есть `exc_info=True`.

Область — как в ADR-6: методы с именами `on_`/`action_`/`watch_` и методы,
в теле которых есть `run_worker` или декоратор `@work` (точка входа воркера).
"""

from __future__ import annotations

import ast
from pathlib import Path

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

_HANDLER_PREFIXES = ("on_", "action_", "watch_")

#: Формы, дающие трейсбек в журнале или у диспетчера.
_TRACEBACK_FORMS = (
    "logger.exception",
    "_log.exception",
    "log.exception",
    "exc_info=True",
)
_ERR_CALLS = ("err(exc", "err(e,")


def _is_blind(handler: ast.ExceptHandler) -> bool:
    """``except Exception`` / ``except BaseException`` / голый ``except:``."""
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
    """Гвард обязан падать на подсаженном коде — иначе он проверяет пустоту."""
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

    # Каждая из четырёх разрешённых форм гвард не трогает.
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

    # Хендлер вне области правила (не on_*/action_*/watch_* и не воркер) —
    # тоже не его дело: это вспомогательный метод, его исключение всплывает.
    planted.write_text(
        "def helper(self):\n"
        "    try:\n"
        "        self.do_work()\n"
        "    except Exception as exc:\n"
        "        logger.debug('failed: %s', exc)\n",
        encoding="utf-8",
    )
    assert _offenders() == []
