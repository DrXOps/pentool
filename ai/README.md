# ai/ — маршрутизация моделей, эскалация, изоляция, наблюдаемость

Зачем: агент должен сам выбирать модель под задачу — дешёвая локальная для
рутины, лёгкая облачная для текстов, сильная для сложного анализа — и
эскалировать при неудаче, не теряя работу и оставляя след для отчёта.

Что здесь:

| Файл | Что |
|---|---|
| `discovery.md` | что найдено в окружении, чем подтверждено, где предположения |
| `models.yaml` | модели, роли, цепочки задач, пороги сжатия, параметры логов |
| `runner.py` | движок: маршрут → вызов → эскалация → журнал (stdlib-only) |
| `run` | обёртка (`ai/run <команда> ...`), читает `.env` |
| `logs/events.jsonl` | журнал вызовов (в `.gitignore`) |

Связанные скрипты: `scripts/ai/worktree` (изолированные копии),
`scripts/ai/agent` (запуск агента внутри), `.claude/hooks/context-state.sh`
(состояние задачи между сжатиями контекста).

## Быстрый старт

```bash
ai/run health                      # какие эндпоинты живы
ai/run models --tasks              # модели и цепочки
ai/run run lint -p "проверь импорты"
echo "объясни diff" | ai/run run explain -p -
ai/run run debug -f /tmp/prompt.txt --json
ai/run report                      # экономия и распределение по моделям
```

## Политика (ai/models.yaml → tasks)

| Задача | Цепочка |
|---|---|
| `lint`, `explain`, `small-edit` | локальная → облачная-быстрая |
| `test-fix` | локальная → flash → pro |
| `docs`, `commit-msg` | облачная-быстрая → запасная |
| `debug`, `code-review` | flash → pro |
| `architecture`, `escalation` | pro |

Правило: **рутина — локальная, текст — лёгкая облачная, сложное — сильная.**
Ошибка конфигурации (нет токена) не эскалируется — она не лечится сменой
модели. Эскалируются `timeout`, `network`, `http_5xx`, `empty_response`,
`tool_call_invalid` (`ai/models.yaml` → `escalation.retry_on`).

## Роли моделей и как их менять

Роли — это ключи в `models.<name>`; имя модели берётся из `model_env`,
эндпоинт — из `endpoint_env`. Поэтому смена провайдера — правка `.env`,
а не кода. Текущее назначение и что из него — предположение, см.
`discovery.md`.

## Наблюдаемость

Каждая попытка пишется в `ai/logs/events.jsonl`:
`event` (`attempt_ok` / `attempt_failed`), `task`, `model`, `provider`,
`duration_sec`, `prompt_tokens`, `completion_tokens`, `escalated`,
`escalation_reason`, `error_kind`. Тела запросов и ответов **не пишутся**
(`logging.capture_prompts: false`). Ротация — по размеру
(`max_bytes`, `keep_files`).

`ai/run report` считает: долю локальных вызовов, число эскалаций, причины
неудач, сэкономленные вызовы и (если в `models.yaml` заданы цены) оценку
экономии в долларах.

## Контекст и авто-сжатие

`.claude/settings.json`:

```json
{ "autoCompactEnabled": true, "autoCompactWindow": 300000 }
```

Claude Code берёт минимум из этого значения и реального окна модели.
Приоритет: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` > `modelSettings.<model>` >
`autoCompactWindow`. Отключить: `DISABLE_AUTO_COMPACT=1`.

Хуки (`context-state.sh`):

| Событие | Режим | Назначение |
|---|---|---|
| `PreCompact` | `--save` | снапшот состояния в `.claude/state/context/` + stdout = инструкции для сжатия |
| `SessionStart` | `--restore` | краткая сводка в stdout → попадает в контекст модели |
| `PostCompact` | `--log` | запись факта сжатия (наблюдение, без влияния) |

Идемпотентность: повторный `--save` без изменений снапшот не создаёт.
Ротация: `CONTEXT_KEEP` (20 по умолчанию). Восстановление ограничено
`CONTEXT_RESTORE_CHARS` (4000), чтобы сводка не съела больше, чем сэкономит.

Ручные заметки для восстановления: `.claude/state/context/task.md`
(цели, решения, открытые вопросы) — они попадают в снапшот целиком.

## Troubleshooting

| Симптом | Причина | Что делать |
|---|---|---|
| `ai: модель X: не задан эндпоинт` | нет `ANTHROPIC_BASE_URL` | задать в `.env` |
| `config: нет ANTHROPIC_AUTH_TOKEN` | нет токена | задать в `.env` (не в конфиг) |
| локальная модель всегда эскалирует | Ollama не запущена или модель не влезла в RAM | `curl $OLLAMA_ENDPOINT/api/tags`; взять модель меньше |
| `400 model … conflicts with target provider` | шлюз не маршрутизирует `anthropic/*` | см. `discovery.md`; использовать `deepseek/*`, `qwen/*` |
| `chain: неизвестная модель` | опечатка в `tasks` | `ai/run models --tasks` |
| worktree не удаляется | остались правки | это защита; `scripts/ai/worktree remove <name> --force` |

## Отключение

```bash
rm -rf ai/ scripts/ai/ .claude/hooks/context-state.sh
# и убрать три блока хуков из .claude/settings.json (PreCompact/SessionStart/PostCompact)
```

Бизнес-логика проекта от этого не зависит: автоматизация не импортируется
кодом `pentool/` и не меняет его настройки.
