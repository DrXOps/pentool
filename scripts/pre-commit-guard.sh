#!/usr/bin/env bash
# scripts/pre-commit-guard.sh
#
# Git pre-commit guard. Дублирует логику .claude/hooks/guard-git-staging.sh,
# но проверяет ИНДЕКС, а не команду:
#   git diff --cached --name-only --diff-filter=ACMR
#
# ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ `source ../.claude/hooks/...`
# pre-commit запускается в свежем клоне, часто до установки starter kit, и в
# окружении, где .claude/ может отсутствовать (CI, чужая машина, `git commit`
# из IDE). Хук не должен зависеть от файла, которого может не быть.
#
# ЦЕНА: списки нужно править в ДВУХ местах. Это осознанно — см.
# README-starter-kit.md, раздел «Синхронизация списков».
#
# Выход: 0 — можно коммитить; 1 — коммит отклонён (pre-commit ожидает ненулевой код).
# Обход только осознанно: `git commit --no-verify` (или GUARD_GIT_ALLOW).
#
# Режимы:
#   scripts/pre-commit-guard.sh                 # проверяет индекс (pre-commit)
#   scripts/pre-commit-guard.sh --files-from F  # проверяет список путей из файла (CI)
#   scripts/pre-commit-guard.sh --stdin         # проверяет список путей из stdin

set -uo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0

# Файлы, попадающие в коммит. ACMR: Added, Copied, Modified, Renamed.
case "${1:-}" in
  --files-from)
    files=$(cat "${2:?--files-from требует путь}" 2>/dev/null || true)
    ;;
  --stdin)
    files=$(cat 2>/dev/null || true)
    ;;
  *)
    files=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
    ;;
esac
[ -z "${files//[[:space:]]/}" ] && exit 0

# ---------------------------------------------------------------------------
# Списки — ДОЛЖНЫ совпадать с .claude/hooks/guard-git-staging.sh
# ---------------------------------------------------------------------------
in_blacklist() {
  local p="$1" base comp rest level
  base=${p##*/}
  # Шаблоны перечислены явно, а не взяты из строки через `$VAR`: bash НЕ
  # разбирает `|` из значения переменной как альтернацию внутри `case`
  # (`P='a|b'; case b in $P)` не совпадает). Поэтому единый «список строкой»
  # здесь невозможен — списки дублируются как шаблоны в обоих guard-скриптах.
  # `core` и `core.<pid>` — дампы памяти ядра. Шаблон `core.*` сюда не годится:
  # он ловит `wiki/core.md` — обычную страницу вики, а не артефакт.
  case "$base" in
    *.tmp | *.bak | *.old | *.orig | *.rej | *.log | *.swp | *.swo | *~ | \
    *.pyc | *.pyo | *.pid | *.cache | *.dmp | core | core.[0-9]* | \
    .DS_Store | Thumbs.db | desktop.ini) return 0 ;;
  esac
  # Каждый компонент пути проверяется отдельно. Имена, однозначные на любой
  # глубине (`__pycache__`, `.venv`), блокируются где угодно; неоднозначные
  # (`build`, `target`, `dist`, `out`, `tmp`, `debug`) — только в корне и на
  # первом уровне: в репозитории живёт `pentool/tui/screens/target/` (экран
  # Target), и это исходники, а не артефакт сборки.
  rest="$p"
  level=0
  while [ -n "$rest" ]; do
    comp=${rest%%/*}
    case "$comp" in
      __pycache__ | .pytest_cache | .ruff_cache | .mypy_cache | .tox | \
      .venv | venv | node_modules | .next | .nuxt | htmlcov) return 0 ;;
    esac
    if [ "$level" -le 1 ]; then
      case "$comp" in
        tmp | scratch | scratchpad | debug | drafts | dist | build | target | \
        out | coverage) [ "$comp" != "$base" ] && return 0 ;;
      esac
    fi
    case "$rest" in
      */*) rest=${rest#*/}; level=$((level + 1)) ;;
      *) break ;;
    esac
  done
  case "$p" in
    .claude/tmp/* | .claude/state/* | .git/* | ai/logs/* | .worktrees/*) return 0 ;;
  esac
  return 1
}

in_whitelist() {
  local p="$1"
  case "$p" in
    src/* | pentool/* | tests/* | test/* | docs/* | wiki/* | prompts/* | scripts/* | \
    templates/* | ai/* | \
    tools/* | screens/* | tui-lab/* | \
    bin/* | config/* | configs/* | assets/* | infra/* | deploy/* | \
    migrations/* | .github/* | .gitlab/* | .devcontainer/* | \
    .claude/hooks/* | .claude/settings.json | .claude/commands/* | .claude/agents/*) return 0 ;;
  esac
  case "$p" in
    */*) return 1 ;;
    README* | CLAUDE.md | LICENSE* | CHANGELOG* | CONTRIBUTING* | SECURITY.md | \
    CODE_OF_CONDUCT* | AUTHORS | NOTICE | ailog.sh | pro | \
    pyproject.toml | setup.py | setup.cfg | requirements*.txt | tox.ini | pytest.ini | \
    .python-version | .ruff.toml | ruff.toml | mkdocs.yml | \
    package.json | tsconfig.json | jsconfig.json | package-lock.json | yarn.lock | \
    pnpm-lock.yaml | .nvmrc | .tool-versions | \
    Cargo.toml | Cargo.lock | go.mod | go.sum | Gemfile | Gemfile.lock | Rakefile | \
    composer.json | composer.lock | build.gradle* | settings.gradle* | pom.xml | \
    CMakeLists.txt | Makefile | justfile | Justfile | Taskfile* | \
    Dockerfile* | docker-compose*.yml | docker-compose*.yaml | compose*.yml | \
    uv.lock | \
    .dockerignore | .gitignore | .gitattributes | .gitmodules | .gitkeep | \
    .editorconfig | .pre-commit-config.yaml | .env.example | .env.template | .env.sample | \
    .secrets.baseline) return 0 ;;
  esac
  return 1
}

escape_allowed() {
  local p="$1" list="${GUARD_GIT_ALLOW:-}" pat oldifs
  [ -z "$list" ] && return 1
  oldifs=$IFS; IFS=,
  for pat in $list; do
    pat=${pat#./}; pat=${pat%/}
    [ -n "$pat" ] || continue
    # shellcheck disable=SC2254
    case "$p" in $pat) IFS=$oldifs; return 0 ;; esac
  done
  IFS=$oldifs
  return 1
}

blocked=""
while IFS= read -r p; do
  [ -z "$p" ] && continue
  p=${p#./}
  escape_allowed "$p" && continue
  if in_blacklist "$p"; then
    blocked+="  $p  [временный/кэш/сборка]"$'\n'
  elif ! in_whitelist "$p"; then
    blocked+="  $p  [вне белого списка]"$'\n'
  fi
done < <(printf '%s\n' "$files" | sort -u)

[ -z "$blocked" ] && exit 0

cat >&2 <<EOF
pre-commit-guard: коммит отклонён.

В индексе есть файлы, не относящиеся к проекту:
$blocked
Что делать:
- Артефакт сборки/кэш  ->  git rm --cached -- <путь>  и добавить в .gitignore
- Черновик/отладка     ->  mv <путь> .claude/tmp/    (каталог в .gitignore)
- Нужен в репозитории  ->  добавить путь в белый список
                           scripts/pre-commit-guard.sh И .claude/hooks/guard-git-staging.sh,
                           обосновать в CLAUDE.md
- Разово               ->  GUARD_GIT_ALLOW="<путь>" git commit ...
EOF
exit 1
