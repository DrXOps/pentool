"""Гейт для новых файлов: решение «в репозиторий» или «в .gitignore».

Проблема, которую он закрывает: в удалённый репозиторий попадали случайные
файлы — черновики, скриншоты с именами вроде `aaaaaaaaaaaa.png`, скрипты «на
пять минут», пустые подпроекты, локальные инструкции агента. `pre-commit-guard`
проверяет только *каталог* файла, поэтому внутри разрешённого каталога мусор
проходил молча.

Правило: каждый файл, добавляемый в индекс (`git diff --cached --diff-filter=A`),
обязан иметь **явное** решение в `.claude/state/new-file-decisions.tsv`:

    <путь><TAB>keep     — файл нужен в репозитории
    <путь><TAB>ignore   — файл локальный; путь обязан быть в .gitignore

Решения — локальные (каталог `.claude/state/` в .gitignore): это рабочий журнал
агента, а не часть продукта. Решение `ignore` без соответствующего правила в
`.gitignore` считается ошибкой: иначе «локальный» файл всё равно уедет в origin
при следующем `git add -A`.

Использование:
    python tools/review_new_files.py                 # проверить (код возврата 0/1)
    python tools/review_new_files.py --list          # показать добавленные и решения
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
    """Файлы, добавленные в индекс (новые, не правки существующих)."""
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
    """Реально ли путь игнорируется git (а не только записан в решении)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    return result.returncode == 0


def load_decisions(path: Path | None = None) -> dict[str, str]:
    # Путь берём во время вызова, а не в момент определения функции: иначе
    # подмена DECISIONS в тестах не действует (проверено тестом).
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
    """Вернуть список проблем (пустой — всё решено). Чистая функция для тестов."""
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
