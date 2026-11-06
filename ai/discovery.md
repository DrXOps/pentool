# ai/discovery.md — что найдено автоматически (2026-11-05)

Отчёт о разведке окружения. Всё, что здесь помечено **[предположение]**,
не подтверждено источником — меняется через `ai/models.yaml` без правки кода.

## Основной проект

| | |
|---|---|
| Каталог | `/mnt/d/PROJECTS/pentool` (`/home/docx/PROJECTS` — симлинк) |
| Признаки | `.git`, `pyproject.toml`, `README.md`, пакет `pentool/` |
| Стек | Python ≥3.10, Textual/aiohttp/aiosqlite, `uv` |
| Ветка | `develop` |

## Стартеркит

| | |
|---|---|
| Каталог | `/mnt/d/PROJECTS/starterkit` — sibling основного проекта |
| Признаки | `README-starter-kit.md`, `CLAUDE.md` («КАРКАС. Заполните блоки…»), `.claude/hooks/*`, `prompts/`, `wiki/` |
| Git | 2 коммита: `05e3f83 Initial starter kit`, `fdbd54c Add CI workflow` |
| Механизм генерации | **отсутствует** — kit копируется вручную (`cp -r starterkit/. .`), см. README → «Установка» |

Вывод: точки расширения — файлы-шаблоны и `INSTALL.md`-процедура; добавлю
`scripts/ai/install` (идемпотентный установщик) и флаг, чтобы kit остался
opt-in.

## Эндпоинты

| # | Что | Откуда подтверждено | Состояние |
|---|---|---|---|
| 1 | Ollama `http://127.0.0.1:11434` | `OLLAMA_ENDPOINT` в env; `GET /api/version` → `0.40.13` | ✅ отвечает |
| 2 | LLM-gateway `$ANTHROPIC_BASE_URL` (`http://172.18.208.1:3456` — хост WSL) | env `ANTHROPIC_BASE_URL`; `GET /health` → `{"status":"ok"}`; `GET /v1/models` → 4 модели | ✅ отвечает |
| 3 | `routerai.ru` (внешний апстрим) | `/mnt/d/PROJECTS/airouter/README.md` + `config.yaml.example` | ⚠️ наружу не проверял: в gateway он уже проксируется |
| 4 | LM Studio `:1234`, vLLM `:8000`, `:8080` | перебор портов | ❌ не слушают |

## Модели (фактический список, не выдуманный)

### Локальные (Ollama, `GET /api/tags`)

| Модель | Размер | Параметры | Квантование | Контекст | Capabilities |
|---|---|---|---|---|---|
| `qwen2.5-coder:7b` | 4.7 GB | 7.6 B | Q4_K_M | **32768** (`qwen2.context_length` из `/api/show`) | `completion`, `tools`, `insert` |

Единственная локальная модель. `tools` поддерживается — годится для рутины
с вызовами инструментов.

**Ограничение:** на этой машине WSL2 4 vCPU / 7 GB RAM; первый запрос
(загрузка 4.7 GB в RAM) не уложился в 90 с. Отсюда: локальные вызовы идут с
таймаутом `local_timeout_sec` и при превышении **эскалируют**, а не ждут.

### Облачные (gateway, `GET /v1/models`)

| id в `/v1/models` | рабочий id для POST | Роль | Проверка POST |
|---|---|---|---|
| `routerai.ru/anthropic/claude-haiku-5.5` | — | лёгкая облачная | ❌ **400** |
| `routerai.ru/deepseek/deepseek-v4.1-flash` | `deepseek/deepseek-v4.1-flash` | лёгкая/быстрый код | ✅ `PONG` |
| `routerai.ru/deepseek/deepseek-v4-pro-0813` | `deepseek/deepseek-v4-pro-0813` | сложный анализ/архитектура | ✅ `PONG` |
| `routerai.ru/qwen/qwen3.7-flash` | `qwen/qwen3.7-flash` | запасная лёгкая | ✅ `PONG` |

**Важно (проверено запросами, не догадка):**

1. `GET /v1/models` отдаёт id **с префиксом** `routerai.ru/`, а `POST
   /v1/messages` принимает id **без** него. С префиксом — 400 «model … is not
   configured for target provider».
2. `anthropic/claude-haiku-5.5` числится в списке, но не маршрутизируется:
   `400 model "anthropic/claude-haiku-5.5" conflicts with target provider
   routerai.ru::openai_chat_completions` (провайдер `openai`, а модель
   `anthropic`). То же для `claude-haiku-5.5` и `claude-haiku-4.5`.
   В `ai/models.yaml` у модели `haiku` стоит `enabled: false`, из цепочек она
   исключена. Это ограничение **прокси**, а не нашей автоматизации.

Роли назначены по именам (`pro` ↔ сильная, `flash` ↔ быстрая) и по конфигу
`/mnt/d/PROJECTS/airouter` (там используется связка Haiku + DeepSeek).
Точных лимитов контекста gateway через API не отдаёт — **[предположение]**
128 000 токенов для DeepSeek/Qwen; значения — в `ai/models.yaml` →
`context_tokens`, правятся одним числом.

### Что даёт облачный ответ

Ответ `deepseek-v4.1-flash` на `/v1/messages` содержит два блока:
`{"type":"thinking",…}` и `{"type":"text","text":"PONG"}`. Поэтому
`ai/runner.py` склеивает только блоки `type == "text"`; иначе в вывод
попадали бы рассуждения модели.

## Маршрутизация, уже существующая в окружении

`/mnt/d/PROJECTS/airouter` — Go-роутер (`llm-router`), правила в `rules.d/`:
tool_calls → deepseek, инженерные ключевые слова → deepseek, контекст
>2000 токенов → deepseek, короткий вопрос → haiku, fallback → haiku.

**Вывод:** маршрутизацию по `anthropic`-трафику уже делает прокси. Наша
автоматизация не дублирует её: она маршрутизирует **собственные задачи**
(линт/тесты/доки/анализ) до вызова API, а через gateway ходит только как
клиент. Роли согласованы с правилами роутера, чтобы не было двойного
переключения моделей.

## Секреты

Токены не читались и не логировались. `ai/run` берёт их только из env:
`ANTHROPIC_AUTH_TOKEN` (gateway), `LLM_ROUTER_API_KEY` (routerai, если
появится), `OLLAMA_*` (локально не нужен). В репозиторий — только
`.env.example` с заглушками.

## Что осталось неопределённым

- Точные контексты облачных моделей (см. выше) — **[предположение]**.
- Цены за 1K токенов — **[предположение]**, нужны только для оценки
  экономии в `ai/report`; при отсутствии цены экономия считается как «вызовы,
  не ушедшие в облако».
- Время первого токена у локальной модели на этой машине не измерено
  (модель не успела загрузиться за 90 с).
