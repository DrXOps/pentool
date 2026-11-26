"""Guard: module screens are mounted lazily, and only through the lifecycle API.

Why this exists
---------------
Until 2026-11-20 all thirteen module screens were built in ``PentoolApp.compose()``
and stayed in the DOM for the whole session (~1600 widgets). Textual runs an
idle/refresh sweep on every interaction that costs roughly five message dispatches
per mounted widget, so a single click cost ~1.4 s (develop/DONE.md (T-002) / measured
2026-11-20: 1444 ms with all screens mounted, 238 ms with the lazy policy).

Screens are now mounted on demand by ``pentool/tui/screen_lifecycle.py``. That
change broke an assumption the whole TUI was written on — "the screen exists" —
and the three mistakes below are easy to make and invisible until a user hits
the exact path:

1. **Direct screen lookups.** ``query_one(SCREEN_PROXY, ProxyScreen)`` raises
   ``NoMatches`` for a module the user has not opened. Handlers then log a
   misleading "not switched", or silently do nothing (a lost "Send to
   Repeater"). Use ``app.module_screen()`` (None-safe), ``app.require_module_screen()``
   (same, but raises ``ScreenNotMounted``, a ``NoMatches``) or
   ``await app.ensure_module_screen()`` (get-or-mount).
2. **Eager mounting in ``PentoolApp.compose()``.** Building module screens there
   re-creates the tree this whole change removed.
3. **An unchecked ``module_screen()`` result.** The lookup is legal, the following
   attribute access is not: it raises ``AttributeError`` in an event handler,
   usually swallowed into a log line nobody reads.

What it does not check: whether a handler *should* have used ``ensure_module_screen``
because it carries user data ("Send to Scanner"). That is a design decision per
handler, documented in ``wiki/tui.md`` §12.

Usage::

    python tools/check_lazy_screens.py           # check (exit 1 on findings)
    python tools/check_lazy_screens.py --list    # print every finding

Exit codes: 0 — clean, 1 — findings.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the TUI lives. PRO is optional: the submodule may be absent in CI.
TARGETS = [ROOT / "pentool" / "tui", ROOT / "pro" / "pentool" / "tui"]

#: Screen ids as module-level constants — a ``query_one`` on one of these is a
#: direct DOM lookup of a lazily mounted screen.
SCREEN_CONSTANTS = (
    "SCREEN_DASHBOARD",
    "SCREEN_PROXY",
    "SCREEN_REPEATER",
    "SCREEN_INTRUDER",
    "SCREEN_SCANNER",
    "SCREEN_TARGET",
    "SCREEN_DECODER",
    "SCREEN_COMPARER",
    "SCREEN_SEQUENCER",
    "SCREEN_EXTENSIONS",
    "SCREEN_SETTINGS",
)

#: The literal selector form, ``query_one("#screen-proxy", ProxyScreen)``.
#: Matched without the surrounding quotes: ``ast.unparse`` may emit either kind.
SCREEN_SELECTOR_LITERAL = "#screen-"

#: Module screen classes: ``query_one(ProxyScreen)`` (by type) is the same direct
#: DOM lookup as the constant form and must go through the lifecycle too.
SCREEN_CLASSES = (
    "DashboardScreen",
    "ProxyScreen",
    "RepeaterScreen",
    "IntruderScreen",
    "ScannerScreen",
    "TargetScreen",
    "DecoderScreen",
    "ComparerScreen",
    "SequencerScreen",
    "ExtensionsScreen",
    "SettingsScreen",
    "ReconScreen",
)

#: Lookups that bypass the lifecycle manager.
FORBIDDEN_LOOKUPS = ("query_one", "get_child_by_id", "query_exactly_one")

#: ``PentoolApp.compose()`` may build these screens (the start screen only).
COMPOSE_ALLOWED_SCREENS = frozenset({"DashboardScreen"})

#: Calls whose result may be None and therefore needs a guard before use.
NONE_RETURNING_LOOKUPS = ("module_screen", "screen", "ensure_module_screen")


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _candidate_files(roots: list[Path] | None = None) -> list[Path]:
    """Every .py under the target roots (tests point ``roots`` at a tmp_path)."""
    found: list[Path] = []
    for root in TARGETS if roots is None else roots:
        if root.is_dir():
            found.extend(sorted(root.rglob("*.py")))
    return found


# ── Rule 1: no direct screen lookups ────────────────────────────────────────


def _direct_lookup_findings(path: Path, tree: ast.AST) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in FORBIDDEN_LOOKUPS:
            continue
        for argument in node.args[:2]:
            text = ast.unparse(argument)
            if any(marker in text for marker in (*SCREEN_CONSTANTS, SCREEN_SELECTOR_LITERAL, *SCREEN_CLASSES)):
                findings.append(
                    (
                        node.lineno,
                        f"{node.func.attr}({text}) — a lazily mounted screen is not in the DOM; "
                        "use app.module_screen() / app.require_module_screen() / await app.ensure_module_screen()",
                    )
                )
    return findings


# ── Rule 2: PentoolApp.compose() builds only the start screen ───────────────


def _compose_findings(path: Path, tree: ast.AST) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != "PentoolApp":
            continue
        for member in cls.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) or member.name != "compose":
                continue
            built = [
                node.func.id
                for node in ast.walk(member)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.endswith("Screen")
            ]
            unexpected = sorted(set(built) - COMPOSE_ALLOWED_SCREENS)
            if unexpected:
                findings.append(
                    (
                        member.lineno,
                        "PentoolApp.compose() builds "
                        f"{', '.join(unexpected)} — module screens are mounted on demand by "
                        "LazyScreenManager (screen_lifecycle.py); only the start screen belongs here",
                    )
                )
            if len([name for name in built if name in COMPOSE_ALLOWED_SCREENS]) > 1:
                findings.append((member.lineno, "PentoolApp.compose() builds the start screen more than once"))
    return findings


# ── Rule 3: module_screen() results are None-checked before use ────────────────


def _names_from_none_returning(source_lines: list[str], func: ast.AST) -> dict[str, int]:
    """Local names assigned from module_screen()/screen()/ensure_module_screen(), with lines."""
    names: dict[str, int] = {}
    for node in ast.walk(func):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)):
            continue
        if value.func.attr not in NONE_RETURNING_LOOKUPS:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names[target.id] = node.lineno
    return names


def _guard_lines(func: ast.AST, names: dict[str, int]) -> dict[str, list[int]]:
    """Lines of ``if``/``assert``/``while`` tests that guard each name."""
    guards: dict[str, list[int]] = {name: [] for name in names}
    for node in ast.walk(func):
        if isinstance(node, (ast.If, ast.While, ast.Assert)):
            test = node.test
            for mention in ast.walk(test):
                if isinstance(mention, ast.Name) and mention.id in names:
                    guards[mention.id].append(node.lineno)
    return guards


def _none_check_findings(path: Path, tree: ast.AST) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = _names_from_none_returning([], func)
        if not names:
            continue
        guards = _guard_lines(func, names)
        for node in ast.walk(func):
            if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
                continue
            name = node.value.id
            if name not in names:
                continue
            assigned_at = names[name]
            if any(assigned_at < guard_line < node.lineno for guard_line in guards[name]):
                continue
            findings.append(
                (
                    node.lineno,
                    f"'{name}' comes from {assigned_at} and may be None — "
                    f"'{name}.{node.attr}' can raise AttributeError; guard it "
                    "(`if {0} is None: return`)".format(name),
                )
            )
    return findings


# ── Aggregation ─────────────────────────────────────────────────────────────


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    """Findings for one file as ``(path, line, message)``."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []
    relative = _relative(path)
    rows = [
        (relative, line, message)
        for line, message in (
            _direct_lookup_findings(path, tree) + _compose_findings(path, tree) + _none_check_findings(path, tree)
        )
    ]
    return sorted(rows, key=lambda row: row[1])


def scan(roots: list[Path] | None = None) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in _candidate_files(roots):
        findings.extend(scan_file(path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard against eager/unsafe module-screen access.")
    parser.add_argument("--list", action="store_true", help="print every finding")
    args = parser.parse_args(argv)

    findings = scan()
    if not findings:
        files = len(_candidate_files())
        print(f"check_lazy_screens: OK — {files} files, module screens go through screen_lifecycle")
        return 0

    print(
        "check_lazy_screens: module screens must be mounted lazily (see wiki/tui.md §12, develop/DONE.md (T-002)):",
        file=sys.stderr,
    )
    for path, line, message in findings:
        if args.list:
            print(f"  {path}:{line}: {message}", file=sys.stderr)
        else:
            print(f"  {path}:{line}: {message.split(' — ')[0]}", file=sys.stderr)
    print(
        "Ways out: app.module_screen() (None-safe), app.require_module_screen() (raises "
        "ScreenNotMounted, a NoMatches) or `await app.ensure_module_screen()` (get-or-mount). "
        "Re-run with --list for full messages.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
