"""Guard: comments and docstrings in code must be English (ratchet).

Why: this codebase was written with Russian comments, and new edits keep copying
the style of the file instead of following the rule. Measured 2026-11-19:
**1842 comment lines** with Cyrillic (163 files); with docstrings — 3466 lines
in 221 files.

Why a ratchet and not a ban: translating everything at once means rewriting one
and a half thousand lines mixed with logic in a single commit. The debt is paid
down per file (like F-009), and this guard keeps the ceiling: a new Russian
comment fails pre-commit and CI.

Rule: inside `.py` files, comments (`# ...`) and docstrings are English.
Russian is allowed in data (UI strings, test fixtures, localisation) — when it
is deliberate, mark the line with `# i18n-ok: <reason>`.

Usage:
    python tools/check_english_comments.py            # check
    python tools/check_english_comments.py --list     # every violation with lines
    python tools/check_english_comments.py --update   # lower the ceiling (down only)
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tools" / "english_comments_baseline.json"

#: Where to look. PRO is optional: the submodule may be absent in CI.
TARGETS = [ROOT / "pentool", ROOT / "pro" / "pentool", ROOT / "tools", ROOT / "tests"]

#: Cyrillic main block plus yo/yo capital outside it.
CYRILLIC = re.compile(r"[\u0400-\u04FF\u0451\u0401]")

#: Escape hatch for deliberately Russian prose.
PRAGMA = "# i18n-ok"


def _relative(path: Path) -> str:
    """Path relative to the repository root; tests point TARGETS at tmp_path."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _candidate_files() -> list[Path]:
    """Every .py under the target roots (PRO only when installed)."""
    found: list[Path] = []
    for root in TARGETS:
        if root.is_dir():
            found.extend(sorted(root.rglob("*.py")))
    return found


def _docstring_lines(tree: ast.AST) -> set[int]:
    """Line numbers occupied by docstrings (module/class/function)."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if not isinstance(first.value.value, str):
            continue
        start = first.lineno
        text = first.value.value
        for offset in range(text.count("\n") + 1):
            lines.add(start + offset)
    return lines


def count_cyrillic_prose(path: Path) -> list[int]:
    """Lines of *path* where Cyrillic appears in a comment or a docstring."""
    source = path.read_text(encoding="utf-8")
    hits: set[int] = set()

    # 1. Comments via tokenize: a "#" inside a string literal is not a comment.
    try:
        with io.BytesIO(source.encode("utf-8")) as buffer:
            for token in tokenize.tokenize(buffer.readline):
                if token.type != tokenize.COMMENT:
                    continue
                if not CYRILLIC.search(token.string):
                    continue
                if PRAGMA in token.string:
                    continue
                hits.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []

    # 2. Docstrings via ast — tokenize sees them as strings, not comments.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return sorted(hits)
    doc_lines = _docstring_lines(tree)
    if doc_lines:
        source_lines = source.splitlines()
        pragma_lines = {lineno for lineno, text in enumerate(source_lines, start=1) if PRAGMA in text}
        for lineno in sorted(doc_lines):
            if lineno in pragma_lines:
                continue
            if lineno <= len(source_lines) and CYRILLIC.search(source_lines[lineno - 1]):
                hits.add(lineno)
    return sorted(hits)


def scan() -> dict[str, int]:
    """How many such lines each file has (paths relative to the repo root)."""
    counts: dict[str, int] = {}
    for path in _candidate_files():
        hits = count_cyrillic_prose(path)
        if hits:
            counts[_relative(path)] = len(hits)
    return counts


def list_violations() -> list[tuple[str, int]]:
    """Flat (file, line) list for `--list` and for tests."""
    rows: list[tuple[str, int]] = []
    for path in _candidate_files():
        relative = _relative(path)
        rows.extend((relative, lineno) for lineno in count_cyrillic_prose(path))
    return rows


def load_baseline() -> dict[str, int]:
    if not BASELINE.is_file():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ratchet against Russian comments in code.")
    parser.add_argument("--update", action="store_true", help="rewrite the baseline (downward only)")
    parser.add_argument("--list", action="store_true", help="print every violation with its line")
    args = parser.parse_args(argv)

    current = scan()
    baseline = load_baseline()

    if args.list:
        for path, lineno in list_violations():
            print(f"{path}:{lineno}")
        print(f"check_english_comments: {sum(current.values())} lines in {len(current)} files")
        return 0

    if args.update:
        # Downward only: growth must fail on the next plain run.
        merged = {
            path: min(current.get(path, 0), baseline.get(path, current.get(path, 0)))
            for path in set(current) | set(baseline)
        }
        merged = {path: count for path, count in merged.items() if count}
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=2) + "\n", encoding="utf-8")
        print(f"check_english_comments: baseline updated — {sum(merged.values())} lines in {len(merged)} files")
        return 0

    grown = {path: (baseline.get(path, 0), count) for path, count in current.items() if count > baseline.get(path, 0)}
    if grown:
        print(
            "check_english_comments: new Russian comments/docstrings (rule: code is English, see MYPLANS T-018):",
            file=sys.stderr,
        )
        for path, (was, now) in sorted(grown.items()):
            print(f"  {path}: {was} -> {now}", file=sys.stderr)
        print(
            "Translate the comment to English. If Cyrillic is data (UI locale, "
            "test fixture), mark the line with `# i18n-ok: <reason>`.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_english_comments: OK — {sum(current.values())} lines in "
        f"{len(current)} files (baseline {sum(baseline.values())}, down)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
