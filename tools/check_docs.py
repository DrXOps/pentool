"""Rewrite check_docs.py for the develop/ layout: index ⇄ files must agree.

Four checks, exactly the rules the owner gave:

1. `docs/` holds no development documents (audits, plans, ADR, state, internal rules);
2. every file under `develop/` except README/DONE is linked from develop/README.md;
3. README.md links nothing that does not exist;
4. `develop/plans/` mentions no completed work — finished items are deleted, not marked.

The last rule is the one that failed before: a finished step stayed in the plan, marked done.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DEVELOP = ROOT / "develop"

LINK = re.compile(r"\]\(([^)]+\.md)\)")
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
DONE_MARKS = ("✅", "**сделано**", "сделано ✅", "закрыто:")  # i18n-ok: markers to search for


def main() -> int:
    if not DEVELOP.is_dir():
        print("check_docs: develop/ отсутствует — проверять нечего")
        return 0

    problems: list[str] = []

    # 1. docs/ is the published product documentation only
    for path in DEVELOP.glob("**/*.md"):
        pass  # (the mirror rule is checked below)
    for path in DOCS.glob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        plan_markers = (
            "план работ",
            "статус: в работе",
            "## этап",
            "реестр находок",
        )  # i18n-ok: Russian phrases a dev doc uses
        if any(word in text for word in plan_markers):
            problems.append(f"{path.relative_to(ROOT).as_posix()}: документ про разработку в docs/")

    # 2/3. index and files agree
    index = DEVELOP / "README.md"
    if not index.is_file():
        problems.append("develop/README.md отсутствует — нет единственного входа")
    else:
        index_text = index.read_text(encoding="utf-8")
        linked: set[Path] = set()
        for target in LINK.findall(index_text):
            resolved = (index.parent / target).resolve()
            linked.add(resolved)
            if not resolved.is_file():
                problems.append(f"develop/README.md: ссылка в никуда — {target}")

        for path in sorted(DEVELOP.glob("**/*.md")):
            if path.name in {"README.md"} or path.parent == DEVELOP and path.name in {"DONE.md"}:
                continue
            if path.resolve() not in linked:
                problems.append(f"{path.relative_to(ROOT).as_posix()}: файл не указан в develop/README.md")

    # 4. plans contain only unfinished work
    for path in sorted((DEVELOP / "plans").glob("*.md")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(mark in line for mark in DONE_MARKS):
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}:{line_no}: отметка о сделанном в плане "
                    "(пункт удаляется, запись идёт в develop/DONE.md)"
                )

    # history files stay dated
    for path in sorted((DEVELOP / "audits").glob("*.md")):
        if not DATE_PREFIX.match(path.name):
            problems.append(f"{path.relative_to(ROOT).as_posix()}: имя аудита без даты")

    if problems:
        print("check_docs: нарушения правил документации:", file=sys.stderr)
        for problem in problems:
            print("  •", problem, file=sys.stderr)
        print("Правила: develop/rules.md", file=sys.stderr)
        return 1
    print("check_docs: OK — правила соблюдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
