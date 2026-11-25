"""Rules for the planning area: statuses are links to facts, history is fenced off.

Why this exists: `MYPLANS/` accumulated documents that read like current state but were
point-in-time: a handoff said "e-mail does not work" long after it worked, a subplan said
"in progress" for finished steps. Nothing failed when they went stale, so they stayed.

The rules below make staleness loud:

1. ``PLAN.md`` and ``subplans/*.md`` may not restate reality: every "done" mark must be
   backed by a fact id from ``tools/facts.yml`` — ``✅ (facts: <id>)``.
2. Files under ``MYPLANS/archive/`` are history. They must open with the snapshot banner,
   and a broken-state glyph (``❌``) is allowed only there.
3. The tracks table in ``PLAN.md`` uses a fixed status vocabulary, so "in progress" and
   "done" cannot be confused with prose.

The checker is silent when ``MYPLANS/`` is absent: the directory is local by design
(``.gitignore``), the tools themselves are part of the repository.

Usage::

    python tools/check_plans.py            # check
    python tools/check_plans.py --list     # show what was parsed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "MYPLANS"
FACTS = ROOT / "tools" / "facts.yml"

#: Allowed beginning of the status cell in the tracks table of PLAN.md.
STATUS_WORDS = ("идея", "в плане", "идёт", "сделано", "закрыт")

DONE_MARK = "✅"
FACT_LINK = re.compile(r"✅[^\n]*?\(facts:\s*([a-z0-9_.\-]+)\)")
BROKEN_MARK = "❌"
SNAPSHOT_BANNER = "> **СНИМОК"


def _fact_ids() -> set[str]:
    import yaml

    if not FACTS.is_file():
        return set()
    data = yaml.safe_load(FACTS.read_text(encoding="utf-8")) or {}
    return {fact["id"] for fact in data.get("facts") or []}


def _plan_docs() -> list[Path]:
    docs = [PLANS / "PLAN.md"]
    docs += sorted((PLANS / "subplans").glob("*.md"))
    return [path for path in docs if path.is_file()]


def _archive_docs() -> list[Path]:
    archive = PLANS / "archive"
    return sorted(archive.rglob("*.md")) if archive.is_dir() else []


def check() -> list[str]:
    problems: list[str] = []
    known = _fact_ids()
    if not known:
        return ["tools/facts.yml отсутствует или пуст — статусы не к чему привязать"]

    for path in _plan_docs():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        # 1. every ✅ carries a fact id. Inline-code spans are skipped: the rules
        # themselves quote the marker (`✅ (facts: <id>)`) and must not be flagged.
        for line_no, line in enumerate(text.splitlines(), 1):
            prose = re.sub(r"`[^`]*`", "", line)
            if DONE_MARK not in prose:
                continue
            links = FACT_LINK.findall(prose)
            if len(links) < prose.count(DONE_MARK):
                problems.append(f"{relative}:{line_no}: «сделано» без (facts: <id>)")
            for fact_id in links:
                if fact_id not in known:
                    problems.append(f"{relative}:{line_no}: неизвестный факт {fact_id!r}")
        # 2. no broken-state glyph outside the archive
        for line_no, line in enumerate(text.splitlines(), 1):
            if BROKEN_MARK in line:
                problems.append(f"{relative}:{line_no}: ❌ вне архива — состояние живёт в facts.yml")

    # 3. tracks table vocabulary
    plan = PLANS / "PLAN.md"
    if plan.is_file():
        for line_no, line in enumerate(plan.read_text(encoding="utf-8").splitlines(), 1):
            if not line.startswith("| **"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3:
                continue
            status = cells[-1].lower()
            if not any(status.startswith(word) for word in STATUS_WORDS):
                problems.append(
                    f"MYPLANS/PLAN.md:{line_no}: статус трека вне словаря {STATUS_WORDS}: {cells[-1][:40]!r}"
                )

    # 4. archive files must announce themselves as history
    for path in _archive_docs():
        relative = path.relative_to(ROOT).as_posix()
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:4])
        if SNAPSHOT_BANNER not in head:
            problems.append(f"{relative}: архивный файл без баннера «{SNAPSHOT_BANNER[2:]}» в первых строках")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="показать разобранные файлы")
    args = parser.parse_args(argv)

    if not PLANS.is_dir():
        print("check_plans: MYPLANS/ нет (локальный каталог) — проверить нечего")
        return 0

    if args.list:
        for path in _plan_docs():
            print("план:   ", path.relative_to(ROOT).as_posix())
        for path in _archive_docs():
            print("архив:  ", path.relative_to(ROOT).as_posix())
        return 0

    problems = check()
    if problems:
        print("check_plans: нарушения в плановой части:", file=sys.stderr)
        for problem in problems:
            print("  •", problem, file=sys.stderr)
        print(
            "\nПравила: «сделано» подтверждается фактом из tools/facts.yml — `✅ (facts: <id>)`;"
            " ❌ допустим только в MYPLANS/archive/; статус трека — из словаря"
            f" {STATUS_WORDS}.",
            file=sys.stderr,
        )
        return 1
    print(f"check_plans: OK — {len(_plan_docs())} планов, {len(_archive_docs())} архивных файлов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
