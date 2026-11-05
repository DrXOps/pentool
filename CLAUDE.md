# CLAUDE.md — Pentool project configuration

## Role
You are a high-class Python programmer and software architecture engineer for high-load systems. Write only clean code — no stubs, no shortcuts, no hardcode.

## Required reading at every start
1. `wiki/index.md` — вики проекта: модули, концепции, зависимости (начинайте оттуда)
2. `wiki/CONTEXT.md` — схема вики, режим хуков, известные исключения
3. `MYPLANS/*.md` — активные планы и техдолг
4. `docs/audit/*.md` — результаты аудитов
5. `README-starter-kit.md` — как устроены хуки, pre-commit и CI
6. `ai/README.md` и `ai/discovery.md` — модели, эскалация, изоляция worktree

## Tech debt
Single source of truth: `MYPLANS/` — любой файл `*plan*` или `*audit*`.
Новый техдолг → дописать в `MYPLANS/tech_debt.md`.

## Plans
- Storage: `MYPLANS/` (в `.gitignore` — локальные рабочие планы)
- New plans → save there
- Always check existing plans before implementing

## Audit results
- Storage: `docs/audit/` (в `.gitignore`, кроме индекса `README.md`)
- Архив вычищенных аудитов: `.claude/tmp/recovered/`

## Memory
- `/home/docx/.claude/projects/-mnt-d-PROJECTS-pentool/memory/MEMORY.md` — индекс памяти агента (вне репозитория)
- Memory files use YAML frontmatter: `name`, `description`, `type`
- Link related memories with `[[name]]`

## Стек

- Язык: Python 3.10+ (`requires-python = ">=3.10"`, CI 3.10–3.12, локально 3.14)
- Библиотеки: Textual (TUI), aiohttp, aiosqlite, pyarrow, cryptography, click, rich
- Платформы: Linux, macOS, Windows (основная разработка — WSL2 на `D:`)

## Команды

- Установка зависимостей: `uv sync`
- Сборка: `uv build`
- Тесты: `scripts/run-tests.sh` (прогоняет `TEST_COMMAND` из `.claude/hooks/config.env`)
- Полный прогон: `uv run pytest -q` (integration/e2e/snapshot/perf — отдельно)
- Линтер: `ruff check pentool/`
- Форматтер: `ruff format pentool/`
- Слои: `python tools/check_layers.py`
- Хуки pre-commit: `uvx pre-commit run --all-files`

Тесты запускаются **через `scripts/run-tests.sh`**: после успешного прогона
скрипт пишет маркер `.claude/state/tests-passed`, который читает Stop-хук.

## Правила (обязательны)

### Архитектурные слои

Порядок зависимостей: `utils ← core ← modules ← api ← tui/cli`.
Нарушения проверяет `tools/check_layers.py` (pre-commit, CI). Нельзя:
`tui → modules`, `modules → tui/api`, `core → modules/tui/api`, `utils → pentool.*`.
Текущие 4 нарушения и план их разбора — `MYPLANS/tech_debt.md` (P1).

### Вики

После изменения кода в `pentool/<module>/` обнови `wiki/<module>.md` по схеме
из `wiki/CONTEXT.md`. Корень кода — `pentool/`, а не `src/` (задано `CODE_ROOT`
в `.claude/hooks/config.env`).

### Тесты

Перед завершением работы запусти `scripts/run-tests.sh`.
Состояние на 2026-11-05: **2339 passed, 1 skipped, 0 failed** (70 с).
Исключений в `TEST_COMMAND` нет — гейт проверяет весь `tests/unit`.

### Временные файлы

Черновики — только `.claude/tmp/` или `/tmp/`. Не создавай их в корне,
в `pentool/` или `tests/`.

### Git

Перед `git add` / `git commit` / `git push` проверь `git status`.
`guard-git-staging.sh` (хук) и `scripts/pre-commit-guard.sh` (pre-commit, CI)
блокируют временные файлы и артефакты. Списки в этих двух файлах обязаны
совпадать — при правке одного правится и второй. Разово:
`GUARD_GIT_ALLOW="<путь>" git add <путь>`.

Коммиты и пуш — только по явной просьбе пользователя.

### Секреты

`protect-secrets.sh` запрещает агенту читать/писать `.env`, ключи, `.netrc`
и т.п. Исключения — `*.example`, `*.template`, `*.sample`, `*.dist`.
`detect-secrets` (pre-commit, CI) сверяется с `.secrets.baseline`;
ложное срабатывание помечается `pragma: allowlist secret`.

### Хуки и обход

Не отключай и не редактируй хуки `.claude/hooks/`, чтобы «просто завершить
сессию». Не используй `--no-verify`.

## Starter kit

- Установлен поэтапно 2026-11-05; см. `README-starter-kit.md`.
- `.claude/`, `prompts/`, `wiki/` — конфигурация агента. `.claude/` и
  `prompts/` в `.gitignore` (локальные); `wiki/` версионируется.
- Блокирующий режим Stop-хука управляется `BLOCKING_ENABLED` в
  `.claude/hooks/config.env`.

## AI-автоматизация

- **Маршрут задачи** выбирает `ai/models.yaml`: рутина → локальная модель,
  текст → лёгкая облачная, сложный анализ → сильная. Эскалация при
  `timeout`/`network`/`5xx`/пустом ответе.
- Запуск: `ai/run run <task> -p "…"`; проверка окружения — `ai/run health`;
  итоги — `ai/run report`.
- Параллельная работа — только в изолированной копии:
  `scripts/ai/agent <name> [-- <команда>]`. Не запускать двух агентов в
  одном дереве: они делят git index и порты.
- Эндпоинты и токены — **только из `.env`**; в `ai/models.yaml` имён
  секретов и внутренних URL нет.
- Контекст: `autoCompactWindow` в `.claude/settings.json`; состояние задачи
  между сжатиями — `.claude/state/context/` (хуки `context-state.sh`).

## Где искать знания

- `wiki/index.md` — знания о проекте (модули, концепции, зависимости).
- `wiki/CONTEXT.md` — схема вики и известные исключения.
- `docs/*.md` — публичная документация (API, CI/CD, установка, гайд).
- `MYPLANS/tech_debt.md` — техдолг с приоритетами.
- `ai/discovery.md` — карта моделей и эндпоинтов этого окружения.
