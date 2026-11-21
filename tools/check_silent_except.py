#!/usr/bin/env python3
"""Ratchet against new silent ``except Exception: pass`` in the TUI layer.

Why a ratchet and not a wipe
----------------------------
ADR-6 (docs/tui-audit/DECISIONS.md) records the policy: in handlers an
``except Exception`` must carry ``logger.exception``, and ``pass`` without a
log is not allowed. The codebase has hundreds of historical breaches (F-009:
601 ``except Exception`` in ``pentool/tui``, 278 of them bare ``pass``). A mass
rewrite is a week of edits with a real regression risk, so ADR-6 fixes them
"at the next touch" instead. This tool enforces that promise mechanically:

* the per-file counts of *silent* handlers are frozen in a baseline file;
* a file whose count **grows** fails the check, so new code cannot add one;
* a file whose count **shrinks** is fine; ``--update`` rewrites the baseline
  to the current (lower) numbers, which is how the ratchet tightens.

Silent handler = ``except Exception`` (or ``BaseException``) whose body is only
``pass``/``continue``/``...``/a bare string (a docstring used as ``pass``).

Usage::

    python tools/check_silent_except.py            # exit 1 on growth
    python tools/check_silent_except.py --update   # rewrite the baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TUI = ROOT / "pentool" / "tui"


def tui_roots() -> list:
    """TUI roots: the main package and PRO, if the submodule is installed."""
    roots = [TUI]
    pro_tui = ROOT / "pro" / "pentool" / "tui"
    if pro_tui.is_dir():
        roots.append(pro_tui)
    return roots


BASELINE = ROOT / "tools" / "silent_except_baseline.json"

_SILENT_BODY = (ast.Pass, ast.Continue)


def _is_silent(handler: ast.ExceptHandler) -> bool:
    """True when the handler swallows the exception without any logging."""
    if len(handler.body) != 1:
        # Several statements: only silent if every one of them is pass/continue
        # or a constant string (a stray docstring). Anything else — an assignment,
        # a return, a call — is not "silent" for this ratchet.
        return all(
            isinstance(stmt, _SILENT_BODY) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
            for stmt in handler.body
        )
    stmt = handler.body[0]
    return isinstance(stmt, _SILENT_BODY) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))


def _is_blind(handler: ast.ExceptHandler) -> bool:
    """``except Exception`` / ``except BaseException`` / bare ``except:``."""
    if handler.type is None:
        return True
    names: list[str] = []
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in types:
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
    return any(name in {"Exception", "BaseException"} for name in names)


def count_silent(tree: ast.AST) -> int:
    return sum(
        1 for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and _is_blind(node) and _is_silent(node)
    )


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(p for tui in tui_roots() for p in tui.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - defensive
            print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
            continue
        count = count_silent(tree)
        if count:
            counts[str(path.relative_to(ROOT)).replace("\\", "/")] = count
    return counts


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args(argv)

    current = scan()
    baseline = load_baseline()

    if args.update:
        # Only keep files that still have silent handlers; the ratchet tightens
        # to the current numbers, both down and (deliberately) not up.
        merged = {
            path: min(current.get(path, 0), baseline.get(path, current.get(path, 0)))
            for path in set(current) | set(baseline)
        }
        merged = {path: n for path, n in merged.items() if n}
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n", encoding="utf-8")
        total = sum(merged.values())
        print(f"check_silent_except: baseline updated — {total} silent handlers in {len(merged)} files")
        return 0

    grown = {path: (baseline.get(path, 0), count) for path, count in current.items() if count > baseline.get(path, 0)}
    if grown:
        print("check_silent_except: new silent `except Exception: pass` (ADR-6):", file=sys.stderr)
        for path, (was, now) in sorted(grown.items()):
            print(f"  {path}: {was} -> {now}", file=sys.stderr)
        print(
            "Log the exception (logger.debug at minimum) or fix the handler; "
            "if the removal of a baseline entry was intentional, run --update.",
            file=sys.stderr,
        )
        return 1

    total_now = sum(current.values())
    total_base = sum(baseline.values())
    print(
        f"check_silent_except: OK — {total_now} silent handlers "
        f"(baseline {total_base}, {'down' if total_now <= total_base else 'up'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
