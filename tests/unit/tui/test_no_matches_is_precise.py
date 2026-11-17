"""ADR-6 п.4: опциональный `query_one` ловится `NoMatches`, а не `Exception`.

`query_one` бросает ровно одно ожидаемое исключение — `NoMatches`, когда
виджета нет в дереве (экран ещё не собран, вкладка не смонтирована, панель
уже снята). Широкий `except Exception` вокруг него делает то же самое, но
заодно проглатывает `AttributeError` от опечатки в имени метода и `TypeError`
от неверного аргумента — то есть ошибку программиста, которую надо видеть.

Правило было записано в ADR-6 п.4, но держалось на дисциплине. Гвард
механический: AST ищет `try`, чьё тело состоит только из обращения к
`query_one`/`query`, и требует, чтобы его хендлер называл `NoMatches` —
либо, если тело делает ещё что-то (например, `.update()` с вычислением),
чтобы он хотя бы писал в журнал. Молчаливый широкий хендлер — нарушение.
Список файлов руками не ведётся — он разошёлся бы с кодом так же, как
разошлись group и name у воркера атаки Intruder.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"

_QUERY_CALLS = ("query_one(", "query(")
_NARROW_ALLOWED = {"NoMatches"}


def _is_query_only(stmts: list[ast.stmt]) -> bool:
    """Тело `try` состоит только из обращений к `query_one`/`query`."""
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
    """Гвард обязан падать на подсаженном коде — иначе он проверяет пустоту."""
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

    # И точечный вариант того же места гвард не трогает.
    planted.write_text(
        "def f(self):\n"
        "    try:\n"
        "        widget = self.query_one('#x', Static)\n"
        "    except NoMatches:\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert _broad_handlers_without_reason() == []
