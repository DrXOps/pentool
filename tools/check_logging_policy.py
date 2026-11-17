#!/usr/bin/env python3
"""Ratchet: a failure in a data path must not disappear from the log.

Why this rule exists
--------------------
ADR-6 closed two shapes of invisible failure: ``except Exception: pass``
(``tools/check_silent_except.py``, now at zero) and handlers that log a string
instead of a traceback (``tests/unit/tui/test_handler_exceptions_logged.py``).
What is left is a broad catch that *does something sensible* and takes the
cause with it: 551 sites, of which 472 wrote nothing or only ``debug``.

For most of them that is fine — a tooltip that failed to update is a cosmetic
miss, and ``debug`` is the right level. For a **data path** it is not: when the
code that saves, loads, restores or applies state swallows the cause, the user
sees "saved" while nothing was saved, and the log is silent. Those are the sites
this ratchet cares about.

The rule
--------
Inside a function whose name marks a data path (``_DATA_VERBS``), a blind
``except`` (``Exception`` / ``BaseException`` / bare) must satisfy one of:

* re-raise (``raise`` in the handler body);
* ``logger.exception(...)``;
* ``logger.warning/error/critical(..., exc_info=True)``.

Anything else is a violation. A handler that has a reason to stay quiet says so
explicitly with ``# logging-ok: <reason>`` on the ``except`` line — the same
shape as ``pragma: allowlist secret`` for detect-secrets.

Cosmetic functions (``_COSMETIC_WORDS``: theme, layout, tooltip, label, hint,
highlight, …) are out of scope even when their name matches a data verb
(``_apply_theme`` is not a data path).

Why a ratchet and not a wipe
----------------------------
The debt was 149 sites across 29 files. They were paid down file by file through
``.claude/tmp/f009/`` (backup → edit → compile → ruff → module tests → rollback),
nine steps in one day. The baseline in ``tools/logging_policy_baseline.json`` is
now **empty**, so the rule is absolute: any new broad ``except`` in a data path
that hides the cause fails pre-commit and CI, exactly like the silent-handler
ratchet. ``--update`` remains for lowering the baseline if it ever creeps back.

Usage::

    python tools/check_logging_policy.py            # exit 1 on growth
    python tools/check_logging_policy.py --update   # lower the baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "pentool"
BASELINE = ROOT / "tools" / "logging_policy_baseline.json"

#: Имена функций, работающих с состоянием: тут молчание = потеря данных.
_DATA_VERBS = (
    "save",
    "store",
    "persist",
    "commit",
    "restore",
    "load",
    "write",
    "export",
    "import",
    "flush",
    "switch_db",
)

#: Косметика: даже если имя задело глагол (`_apply_theme`), логирование данных тут ни при чём.
_COSMETIC_WORDS = (
    "theme",
    "layout",
    "tooltip",
    "label",
    "hint",
    "highlight",
    "color",
    "colour",
    "cursor",
    "focus",
    "glyph",
    "blink",
    "render",
    "paint",
    "refresh",
    "style",
)

#: Уровни, которые считаются честным логом (при наличии трейсбека).
_LOUD = {"warning", "error", "exception", "critical"}

#: Имена модульных логгеров проекта (кроме них принимается любое `*log`/`*logger`).
_LOGGER_NAMES = {"logger", "log", "root_logger", "_logger", "_log"}

_PRAGMA = "logging-ok"


def _is_blind(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names: list[str] = []
    for node in types:
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
    return any(name in {"Exception", "BaseException"} for name in names)


def _is_data_path(name: str) -> bool:
    lowered = name.lower()
    if any(word in lowered for word in _COSMETIC_WORDS):
        return False
    return any(verb in lowered for verb in _DATA_VERBS)


def _handler_logs_loudly(handler: ast.ExceptHandler, source: str) -> bool:
    """Пробрасывает, или logger.*(… exc_info=True), или logger.exception(…), или err(exc, …)."""
    for stmt in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(stmt, ast.Raise):
            return True
        if not isinstance(stmt, ast.Call):
            continue
        func = stmt.func
        # `err(exc, ...)` / `self.err(exc, ...)`: pentool.core.error_guard печатает
        # traceback и уведомляет пользователя — та же честная форма, что и
        # logger.exception, и гвард слоя 2 её уже признаёт.
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        # `err(exc, ...)` и его алиасы (`_err` — так его импортирует
        # project_manager): error_guard печатает traceback и уведомляет
        # пользователя, это честная форма, её признаёт и гвард слоя 2.
        if name.lstrip("_") == "err" and stmt.args:
            return True
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        # Имя логгера в проекте не всегда `logger`: `log` в services/ai/factory.py,
        # `root_logger` в core/logging.py. Принимаем их и любое `*log`/`*logger`.
        logger_name = func.value.id.lower()
        if logger_name not in _LOGGER_NAMES and not logger_name.endswith(("logger", "log")):
            continue
        if func.attr not in _LOUD:
            continue
        if func.attr == "exception":
            return True
        if any(kw.arg == "exc_info" for kw in stmt.keywords):
            return True
    return False


def _has_pragma(handler: ast.ExceptHandler, lines: list[str]) -> bool:
    """Прагма может оказаться не на строке `except`.

    Форматтер вправе развернуть длинный заголовок в многострочный
    (`except (\n    Exception\n):  # logging-ok: …`), и тогда комментарий
    уезжает со строки `lineno`. Поэтому смотрим ещё пару строк ниже.
    """
    start = handler.lineno - 1
    return any(_PRAGMA in lines[i] for i in range(start, min(start + 3, len(lines))))


def count_violations(tree: ast.AST, source: str) -> int:
    """Сколько широких `except` в путях данных молчат о причине."""
    lines = source.splitlines()
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_data_path(node.name):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.ExceptHandler) or not _is_blind(inner):
                continue
            if _has_pragma(inner, lines):
                continue
            if not _handler_logs_loudly(inner, source):
                count += 1
    return count


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:  # pragma: no cover - defensive
            print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
            continue
        count = count_violations(tree, source)
        if count:
            counts[str(path.relative_to(ROOT)).replace("\\", "/")] = count
    return counts


def list_violations() -> list[tuple[str, int, str]]:
    """(файл, строка, имя функции) для каждого нарушения — для пофайловой чистки."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover - defensive
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _is_data_path(node.name):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.ExceptHandler) or not _is_blind(inner):
                    continue
                if _has_pragma(inner, lines):
                    continue
                if _handler_logs_loudly(inner, source):
                    continue
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                found.append((rel, inner.lineno, node.name))
    return sorted(found)


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the baseline (never raises it)")
    parser.add_argument("--list", action="store_true", help="print every violation with its line and function")
    args = parser.parse_args(argv)

    if args.list:
        for path, line, func in list_violations():
            print(f"{path}:{line}  {func}")
        return 0

    current = scan()
    baseline = load_baseline()

    if args.update:
        merged = {
            path: min(current.get(path, 0), baseline.get(path, current.get(path, 0)))
            for path in set(current) | set(baseline)
        }
        merged = {path: n for path, n in merged.items() if n}
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n", encoding="utf-8")
        print(f"check_logging_policy: baseline updated — {sum(merged.values())} sites in {len(merged)} files")
        return 0

    grown = {path: (baseline.get(path, 0), count) for path, count in current.items() if count > baseline.get(path, 0)}
    if grown:
        print("check_logging_policy: широкий `except` в пути данных молчит о причине:", file=sys.stderr)
        for path, (was, now) in sorted(grown.items()):
            print(f"  {path}: {was} -> {now}", file=sys.stderr)
        print(
            "Логируйте причину: `logger.warning/error(..., exc_info=True)` или `logger.exception(...)`, "
            "либо пробросьте исключение. Если молчание осознанно — `# logging-ok: <причина>` на строке except.",
            file=sys.stderr,
        )
        return 1

    total_now, total_base = sum(current.values()), sum(baseline.values())
    print(
        f"check_logging_policy: OK — {total_now} sites "
        f"(baseline {total_base}, {'down' if total_now <= total_base else 'up'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
