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
- Форматтер: `ruff format pentool/` (line-length 120 — один стандарт с
  black/isort, задан в `[tool.ruff]`; до 2026-11-16 здесь стояло 100, и
  форматтер переписывал файлы вопреки black)
- Слои: `python tools/check_layers.py`
- TUI CSS ↔ DOM: `uv run python tools/check_tui_css.py` (селектор без
  соответствующего id/класса/типа в Python — блокирует CI и pre-commit)
- Молчаливые исключения: `uv run python tools/check_silent_except.py`
  (трещотка ADR-6; `--update` понижает baseline)
- Широкие исключения: `uv run python tools/check_broad_except.py`
  (вторая трещотка ADR-6 по всему `pentool/` — считает `ruff BLE001`,
  потолок на файл в `tools/broad_except_baseline.json`, `--update` понижает)
- Логирование в путях данных: `uv run python tools/check_logging_policy.py`
  (третья трещотка ADR-6: широкий `except` внутри save/load/restore/apply
  обязан пробрасывать или писать `warning`+ с трейсбеком; база
  `tools/logging_policy_baseline.json` **пуста** с 2026-11-17, поэтому новый
  такой обработчик роняет коммит). Как выбирать уровень и чем слои
  отличаются — `wiki/tui.md` §8а
- Хуки pre-commit: `uvx pre-commit run --files $(git diff --name-only HEAD)`.
  **Не `--all-files`**: репозиторий исторически накопил расхождение с
  форматтерами (на 2026-11-16 `ruff format` при 120 хотел бы переписать 84
  файла из 198), поэтому `--all-files` утащит в дифф весь проект.

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

Белый список проекта: `pentool/ tests/ docs/ wiki/ prompts/ scripts/ tools/
screens/ tui-lab/ bin/ ai/` и корневые файлы. Каталог `ai/` в белом списке,
потому что это часть репозитория (движок автоматизации и конфиг моделей),
но `ai/logs/` — в чёрном: журналы выполнения не коммитятся.

Коммиты и пуш — только по явной просьбе пользователя.

### Секреты

`protect-secrets.sh` запрещает агенту читать/писать `.env`, ключи, `.netrc`
и т.п. Исключения — `*.example`, `*.template`, `*.sample`, `*.dist`.
`detect-secrets` (pre-commit, CI) сверяется с `.secrets.baseline`;
ложное срабатывание помечается `pragma: allowlist secret`.

### Хуки и обход

Не отключай и не редактируй хуки `.claude/hooks/`, чтобы «просто завершить
сессию». Не используй `--no-verify`.

## DeepSeek Harness (DSH)

- Те же хуки работают и под DSH: их вызывает нативный плагин профиля
  `@local/pentool-hooks` через `.claude/dsh/dispatch.sh` внутри WSL.
  Скрипты `.claude/hooks/*.sh` не менялись и остаются единственным
  источником правил; плагин только доставляет их вызовы.
- Команды проекта выполняются в WSL: `wsl -e bash -lc 'cd /mnt/d/PROJECTS/pentool && …'`.
  Сэндбокс DSH блокирует `wsl.exe`, поэтому нужен полный доступ к файловой
  системе — в ограниченных режимах хуки и тесты не запустятся.
- `format-on-edit.sh` в DSH **включён** (`formatHook: true`): после каждой
  правки файла через агента он приводит файл к стандарту проекта. Раньше был
  выключен, потому что `ruff format` шёл по 100, а black — по 120; с 2026-11-17
  форматтер один (ruff, 120), и хук не расходится с pre-commit.
- Проверка моста без агента: `wsl -e bash /mnt/d/PROJECTS/pentool/.claude/dsh/selftest.sh`
  (ожидается `7 passed, 0 failed`).
- События `PreCompact` в DSH нет: `context-state.sh --save` не вызывается,
  `.claude/state/context/latest.md` обновляется только в Claude Code.

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
