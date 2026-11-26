"""Documentation layout rules (docs/DOC_RULES.md) — checked, not remembered.

Catches the three ways the docs rot:

* a file in ``docs/audit/`` without a date in its name (history must be dated and frozen);
* a reference to the removed ``docs/tui-audit/`` folder anywhere in the repository;
* a working plan (MYPLANS-style content: Russian words for plan/backlog/status) written
  into ``docs/`` — that folder is published on the site and holds product docs only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
AUDIT = DOCS / "audit"

DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
PLAN_WORDS = ("план работ", "бэклог", "статус: в работе", "статус: в плане")  # i18n-ok: search data


def main() -> int:
    problems: list[str] = []

    for path in sorted(AUDIT.glob("*.md")):
        if path.name in {"README.md"}:
            continue
        if not DATE_PREFIX.match(path.name):
            problems.append(f"{path.relative_to(ROOT).as_posix()}: имя без даты (история должна быть датирована)")

    for path in list(DOCS.glob("*.md")) + list((ROOT / "pentool").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "docs/tui-audit" in text:
            problems.append(f"{path.relative_to(ROOT).as_posix()}: ссылка на удалённую docs/tui-audit/")

    for path in sorted(DOCS.glob("*.md")):
        lowered = path.read_text(encoding="utf-8").lower()
        for word in PLAN_WORDS:
            if word in lowered:
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}: рабочий план в docs/ ({word!r}) — место в MYPLANS/"
                )

    if problems:
        print("check_docs: нарушения правил документации:", file=sys.stderr)
        for problem in problems:
            print("  •", problem, file=sys.stderr)
        print("Правила: docs/DOC_RULES.md", file=sys.stderr)
        return 1
    print("check_docs: OK — правила документации соблюдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
