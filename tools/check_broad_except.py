#!/usr/bin/env python3
"""Ratchet against new blind ``except Exception`` in ``pentool/``.

Why a ratchet and not a wipe
----------------------------
ADR-6 (docs/DECISIONS.md) closed the two worst shapes of the
problem mechanically: ``except Exception: pass`` cannot grow
(``tools/check_silent_except.py``, now at zero) and handlers in
``on_*``/``action_*``/``watch_*``/workers must write a traceback
(``tests/unit/tui/test_handler_exceptions_logged.py``). What is left is the
broad catch that neither logs nor re-raises — it does *something* (returns a
default, sets a flag, notifies) and hides the cause. That is exactly what ruff's
``BLE001`` reports, and it is 585 sites on 92 files.

A mass rewrite is a week of edits with real regression risk, so the backlog is
frozen instead: the per-file counts live in ``tools/broad_except_baseline.json``,
a file whose count **grows** fails the check, and ``--update`` lowers the
numbers as the debt is paid down. When the total reaches zero, ``BLE`` moves
into ``select`` in ``pyproject.toml`` and this tool retires.

Detection is delegated to ruff on purpose: its ``BLE001`` already exempts the
two shapes ADR-6 accepts — handlers that re-raise, and handlers that log — and
re-implementing that heuristic here would drift from the linter.

Usage::

    python tools/check_broad_except.py            # exit 1 on growth
    python tools/check_broad_except.py --update   # rewrite the baseline
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "pentool"


def _default_packages() -> list:
    """Packages to check: the main one and PRO (if the submodule is installed).

    Computed on each call: the tests patch PACKAGE/ROOT to a temporary
    directory, and a cached list would break them.
    """
    found = [PACKAGE]
    pro_package = ROOT / "pro" / "pentool"
    if pro_package.is_dir():
        found.append(pro_package)
    return found


BASELINE = ROOT / "tools" / "broad_except_baseline.json"
RULE = "BLE001"


def scan(package_list: list[Path] | Path | None = None, root: Path = ROOT) -> dict[str, int]:
    """Per-file count of ``BLE001`` findings across packages, relative to *root*.

    The first argument accepts either a single path or a list: the historical
    ``scan(package, root)`` call from the tests must keep working.
    """
    if package_list is None:
        targets = _default_packages()
    elif isinstance(package_list, (str, Path)):
        targets = [Path(package_list)]
    else:
        targets = list(package_list)

    counts: dict[str, int] = {}
    for package in targets:
        for path, count in _scan_one(package, root).items():
            counts[path] = counts.get(path, 0) + count
    return counts


def _scan_one(package: Path, root: Path) -> dict[str, int]:
    """One package: what ruff reports as ``BLE001``, counted per file."""
    procedure = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--select",
        RULE,
        "--output-format",
        "json",
        str(package),
    ]
    result = subprocess.run(procedure, cwd=root, capture_output=True, text=True)
    # 0 = clean, 1 = findings; anything else is a broken invocation, not a verdict.
    if result.returncode not in (0, 1):
        print(
            f"check_broad_except: ruff failed ({result.returncode}):\n{result.stderr}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    counts: dict[str, int] = {}
    for finding in json.loads(result.stdout or "[]"):
        if finding.get("code") != RULE:
            continue
        path = Path(finding["filename"]).resolve().relative_to(root).as_posix()
        counts[path] = counts.get(path, 0) + 1
    return counts


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ratchet against new blind except clauses.")
    parser.add_argument("--update", action="store_true", help="rewrite the baseline (downward only)")
    args = parser.parse_args(argv)

    current = scan()
    baseline = load_baseline()

    if args.update:
        # Downward only: a paid-down file tightens, a grown file keeps its old
        # number so the growth still fails on the next plain run.
        merged = {
            path: min(current.get(path, 0), baseline.get(path, current.get(path, 0)))
            for path in set(current) | set(baseline)
        }
        merged = {path: count for path, count in merged.items() if count}
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n", encoding="utf-8")
        print(f"check_broad_except: baseline updated — {sum(merged.values())} blind handlers in {len(merged)} files")
        return 0

    grown = {path: (baseline.get(path, 0), count) for path, count in current.items() if count > baseline.get(path, 0)}
    if grown:
        print(
            f"check_broad_except: new blind `except Exception` that neither logs nor re-raises ({RULE}, ADR-6):",
            file=sys.stderr,
        )
        for path, (was, now) in sorted(grown.items()):
            print(f"  {path}: {was} -> {now}", file=sys.stderr)
        print(
            "Narrow the exception to what the code can actually raise, or log it "
            "(logger.exception / err(exc, ...)) and re-raise or return deliberately. "
            "If a baseline entry was removed on purpose, run --update.",
            file=sys.stderr,
        )
        return 1

    total_now = sum(current.values())
    total_base = sum(baseline.values())
    print(
        f"check_broad_except: OK — {total_now} blind handlers "
        f"(baseline {total_base}, {'down' if total_now <= total_base else 'up'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
