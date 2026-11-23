"""Gate for new files: the decision "into the repository" or "into .gitignore".

The problem it closes: random files were getting into the remote repository —
drafts, screenshots named like `aaaaaaaaaaaa.png`, scripts written "in five
minutes", empty subprojects, local agent instructions. `pre-commit-guard`
checks only the *directory* of a file, so junk inside an allowed directory
passed silently.

Rule: every file added to the index (`git diff --cached --diff-filter=A`)
must have an **explicit** decision in `.claude/state/new-file-decisions.tsv`:

    <path><TAB>keep     — the file is needed in the repository
    <path><TAB>ignore   — the file is local; the path must be in .gitignore

Decisions are local (the `.claude/state/` directory is in .gitignore): it is the
agent's working log, not part of the product. An `ignore` decision without a
matching rule in `.gitignore` is treated as an error: otherwise the "local" file
still travels to origin on the next `git add -A`.

Usage:
    python tools/review_new_files.py                 # check (exit code 0/1)
    python tools/review_new_files.py --list          # show added files and decisions
    python tools/review_new_files.py --decide PATH keep|ignore
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DECISIONS = Path(".claude/state/new-file-decisions.tsv")
KEEP = "keep"
IGNORE = "ignore"
VALID = (KEEP, IGNORE)


def staged_added(cwd: Path | None = None) -> list[str]:
    """Files added to the index (new ones, not edits to existing files)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_ignored(path: str, cwd: Path | None = None) -> bool:
    """Whether the path is really ignored by git (not just recorded in a decision)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    return result.returncode == 0


def load_decisions(path: Path | None = None) -> dict[str, str]:
    # Take the path at call time rather than when the function is defined:
    # otherwise patching DECISIONS in tests has no effect (verified by a test).
    path = path or DECISIONS
    if not path.is_file():
        return {}
    decisions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        decisions[parts[0].strip()] = parts[1].strip()
    return decisions


def save_decision(file_path: str, decision: str, path: Path | None = None) -> None:
    if decision not in VALID:
        raise ValueError(f"решение должно быть одним из {VALID}, получено {decision!r}")
    path = path or DECISIONS
    decisions = load_decisions(path)
    decisions[file_path] = decision
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Путь\tрешение (keep — в репозиторий, ignore — локальный файл)"]
    body += [f"{name}\t{value}" for name, value in sorted(decisions.items())]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def check(added: list[str], decisions: dict[str, str], ignored: set[str]) -> list[str]:
    """Return the list of problems (empty means everything is decided). Pure function for tests."""
    problems: list[str] = []
    for name in added:
        decision = decisions.get(name)
        if decision == KEEP:
            continue
        if decision == IGNORE:
            if name not in ignored:
                problems.append(
                    f"{name}: решение «ignore», но путь НЕ в .gitignore — "
                    "добавьте правило, иначе файл всё равно уедет в origin"
                )
            continue
        problems.append(
            f"{name}: нет решения. Запустите\n"
            f"    python tools/review_new_files.py --decide {name} keep|ignore\n"
            "keep — файл нужен в репозитории; ignore — он локальный (тогда путь "
            "обязан быть в .gitignore)"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="показать добавленные файлы и решения")
    parser.add_argument("--decide", nargs=2, metavar=("PATH", "DECISION"), help="записать решение keep|ignore")
    args = parser.parse_args(argv)

    if args.decide:
        file_path, decision = args.decide
        try:
            save_decision(file_path, decision)
        except ValueError as exc:
            print(f"review_new_files: {exc}", file=sys.stderr)
            return 2
        print(f"review_new_files: {file_path} → {decision}")
        return 0

    added = staged_added()
    decisions = load_decisions()
    ignored = {name for name in added if is_ignored(name)}

    if args.list:
        if not added:
            print("review_new_files: новых файлов в индексе нет")
        for name in added:
            print(f"  {name}\t{decisions.get(name, '— нет решения —')}")
        return 0

    if not added:
        return 0

    problems = check(added, decisions, ignored)
    if problems:
        print("review_new_files: новые файлы без решения — коммит остановлен\n")
        for problem in problems:
            print(f"  • {problem}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
