# Starter kit для Claude Code

Стартовый набор для проекта, который разрабатывается агентом: вики в стиле
Карпатого, обязательные тесты перед завершением хода, защита секретов и
защита от попадания в git посторонних файлов.

## Что внутри

```
.claude/
  settings.json             регистрация четырёх хуков
  hooks/
    require-quality-gate.sh Stop: тесты + вики, exit 2 при провале
    format-on-edit.sh       PostToolUse: быстрый форматтер на изменённый файл
    protect-secrets.sh      PreToolUse: запрет чтения/записи секретов
    guard-git-staging.sh    PreToolUse(Bash): git add/commit/push без мусора
  state/                    маркеры хука (в .gitignore)
  tmp/                      ваша зона для черновиков (в .gitignore)
scripts/
  pre-commit-guard.sh       та же проверка, что guard-git-staging, для индекса
  run-tests.sh              тесты + запись маркера tests-passed
wiki/                       index.md, CONTEXT.md, _template.md, raw/, concepts/, entities/, deps/
prompts/                    karpathy-ingest, test-fix-loop, cross-platform-check, git-hygiene
.github/workflows/ci.yml    guard + pre-commit + тесты ubuntu/windows
.pre-commit-config.yaml     командные гарантии вне Claude Code
CLAUDE.md                   каркас правил для агента
.gitignore                  временные файлы, кэш, секреты
.env.example                TEST_CMD, WIN_HOST, WIN_TEST_SCRIPT
```

## Установка

```bash
cd /path/to/new-project
cp -r /path/to/starterkit/. .
chmod +x .claude/hooks/*.sh scripts/*.sh
cp .env.example .env          # заполнить TEST_CMD
pipx install pre-commit && pre-commit install
```

Зависимости: `bash`, `git`, `jq`, `ssh` (для Windows-тестов). `jq` обязателен —
без него хуки не разбирают JSON, а читают stdin грубым sed-фолбэком.
`shellcheck` не требуется, но полезен: `shellcheck .claude/hooks/*.sh scripts/*.sh`.

Если Claude Code открывается **не из корня** проекта: `${CLAUDE_PROJECT_DIR}` —
это каталог, где началась сессия; хуки используют его, чтобы найти скрипты.
Открывайте сессию из корня репозитория либо замените в `.claude/settings.json`
`${CLAUDE_PROJECT_DIR}` на абсолютные пути.

## Как проверить, что хуки работают

1. **Stop/тесты.** Измените код в `src/` и попросите агента завершить ход.
   Ожидается блокировка (`exit 2`) с текстом «Тесты не запускались…».
   Запустите `scripts/run-tests.sh` — ход завершается.
2. **Stop/вики.** После зелёных тестов хук потребует `wiki/<module>.md`.
   Создайте страницу по `wiki/_template.md` — ход завершается.
3. **PreToolUse/секреты.** Попросите агента прочитать `.env` — ожидается
   `permissionDecision: deny`. `.env.example` читается без блокировки.
4. **PreToolUse/git.** Создайте `scratch.txt` в корне и попросите
   `git add .` — ожидается `deny` со списком `scratch.txt  [вне белого списка]`.
   `git add src/<файл>` проходит.
5. **PreToolUse/git, escape hatch.** `GUARD_GIT_ALLOW=scratch.txt git add .`
   проходит (остальные посторонние файлы всё равно блокируются).
6. **pre-commit.** `git add scratch.txt && git commit -m test` — отклонено
   скриптом `pre-commit-guard.sh`.
7. **Форматтер.** Отредактируйте `.py` при установленном `ruff` — файл
   переформатирован; без форматтера хук молча выходит с 0.
8. **Неблокируемость.** Убедитесь, что хуки не падают в репозитории без git
   (`require-quality-gate.sh` возвращает 0).

## Два рубежа защиты

| | Хуки Claude Code (`.claude/`) | pre-commit / CI |
|---|---|---|
| Для кого | личная эргономика агента в этой сессии | вся команда, свежий клон, CI |
| Когда | во время работы агента | при коммите/пуше, независимо от агента |
| Обходится | `--no-verify` не применим, но правила можно отключить в settings | `--no-verify` (осознанно) |

Критичные проверки дублируются намеренно: агент может не иметь `.claude/`,
человек может коммитить из IDE, CI не знает про хуки Claude Code.

### Синхронизация списков

`guard-git-staging.sh` и `pre-commit-guard.sh` — **разные файлы с одинаковой
логикой**. Одинаковая логика, потому что pre-commit должен работать без
`.claude/` (свежий клон, CI, чужая машина) — `source` запрещён. Поэтому при
изменении чёрного или белого списка правьте **оба** файла. Разница в их
списках — дефект, а не оптимизация.

## Расширение белого списка

Белый список — главный механизм guard: всё, чего в нём нет, блокируется.
Добавлять пути нужно осознанно:

1. Создайте каталог/файл и убедитесь, что он относится к проекту, а не к сборке.
2. Добавьте путь в `in_whitelist()` **обоих** скриптов:
   `.claude/hooks/guard-git-staging.sh` и `scripts/pre-commit-guard.sh`.
3. Добавьте запись в `CLAUDE.md`, раздел «Правила → Git»: что это за каталог
   и почему он в репозитории.
4. Прогоните проверку вручную:
   `echo 'newdir/file.txt' | scripts/pre-commit-guard.sh --stdin` → exit 0.

Разовое исключение без правки списков: `GUARD_GIT_ALLOW="newdir/file.txt" git add newdir/file.txt`.
Переменную можно задать в префиксе команды — хук читает её оттуда, потому что
выполняется до запуска команды.

## Windows-тесты по SSH

`.env`:
```bash
WIN_HOST=user@192.168.1.50
WIN_TEST_SCRIPT=C:\projects\myapp\scripts\run-tests.ps1
```

Подготовка: `ssh-copy-id "$WIN_HOST"`, проверка
`ssh "$WIN_HOST" powershell.exe -Command "echo ok"`. Stop-хук вызывает SSH
только при изменении Windows-специфичных файлов (`*win*`, `*windows*`,
`*.ps1`, `msvc` в пути) и ограничивает вызов 8 секундами: если Windows недоступен,
хук предупреждает, а не блокирует навсегда. Настройка выполняется один раз.

## Состояние внедрения в pentool (2026-11-05)

| Этап | Что | Статус |
|---|---|---|
| 1 | Хуки, `state/`, `wiki/`, `prompts/`, скрипты. Блокировки выключены | Завершён |
| 2 | Заполненная вики, зелёный `tests/unit`, pre-commit + CI, блокирующий Stop | Завершён |

Конкретика:

- `BLOCKING_ENABLED=true` — Stop-хук блокирует завершение хода.
- `TEST_COMMAND="uv run pytest tests/unit -q"` — исключений нет,
  весь набор зелёный (2339 passed, 1 skipped).
- `.pre-commit-config.yaml`: black/isort/flake8/check-layers + `guard-git-staging`
  + `detect-secrets` (baseline `.secrets.baseline`).
- `.github/workflows/ci.yml`: jobs `guard` (диффа в коммите), `secrets`
  (detect-secrets), `test-windows` (нативная Windows-проверка) перед `build`.
- `CODE_ROOT=pentool` — в проекте нет `src/`; маппинг
  `pentool/<module>/` → `wiki/<module>.md`.
- Известные ограничения и техдолг — `MYPLANS/tech_debt.md`.

### Грабли, уже наступленные (не повторять)

- **`|` внутри переменной не работает как альтернация в `case`.**
  `P='a|b'; case b in $P)` — не совпадение. Списки шаблонов в guard'ах
  перечисляются явно.
- **Не искать имена `build|target|dist|out|tmp|debug` на любой глубине.**
  Это обычные слова: в проекте живёт `pentool/tui/screens/target/` —
  исходники экрана Target, а не артефакт сборки.
- **`core.*` ловит `wiki/core.md`.** Дампы ядра — `core` и `core.<pid>`.
- **`*.env` в денилисте ловит `config.env`.** Для секретов достаточно
  `.env` и `.env.*`.
- **Хук `protect-secrets.sh` блокирует собственный файл** (в его денилисте
  есть слова `secret`/`secrets`) — нужен самоисключение, иначе агент не
  может его обслуживать по предписанию самого хука.

## Как добавить правило или хук

- **Правило в `CLAUDE.md`** — раздел «Правила (обязательны)». Если правило
  должно применяться механически, а не только по доброй воле, продублируйте
  его в хуке и в pre-commit — иначе агент его забудет.
- **Новый хук** — скрипт в `.claude/hooks/`, `chmod +x`, регистрация в
  `.claude/settings.json` с `${CLAUDE_PROJECT_DIR}`, затем проверка: событие
  получает JSON в stdin, `PreToolUse` отвечает `hookSpecificOutput` +
  `permissionDecision`, `Stop` блокирует через `exit 2`.
- **Бюджет времени:** `Stop` — ~10 с, `PostToolUse` — ~2 с. Проверка дольше —
  асинхронность через маркер, как в `require-quality-gate.sh`.

## Когда подключать Serena MCP

Порог — около 50 файлов в `src/`. Ниже этого Grep/Glob дешевле и точнее;
выше семантическая навигация (find_symbol, find_references) экономит контекст.

Регистрация — в пользовательской конфигурации (`~/.claude/config.json`) либо
через `@codewizard-dt/bootstrap`, который подключает Serena и другие MCP-серверы.
Сам сервер в starter kit не входит: инструкция и заготовка раздела
«MCP-инструменты» в `CLAUDE.md`.
