# План миграции: pip → uv

**Ветка:** `feature/migrate-pip-to-uv`  
**Дата:** 2026-08-13  
**Статус:** черновик

---

## Зачем

| Критерий | pip + venv | uv |
|---|---|---|
| Скорость install | ~30–60 с | ~2–5 с (10–30× быстрее) |
| Lockfile | нет (только requirements.txt) | `uv.lock` (cross-platform, детерминированный) |
| Виртуальное окружение | нужен отдельный шаг | `uv sync` создаёт автоматически |
| `pyproject.toml` | требует setuptools как build-backend | совместим с любым |
| Повторяемость CI | ~75% | 100% (lockfile) |
| Установка одной командой | `pip install pentool` | `uv tool install pentool` |

---

## Затронутые файлы

### Инфраструктура (5 файлов)
| Файл | Что меняется |
|---|---|
| `pyproject.toml` | Добавить `[tool.uv]` секцию, поднять `requires-python` |
| `requirements.txt` | Удалить (заменяется `uv.lock` + `[project].dependencies`) |
| `requirements-dev.txt` | Удалить (заменяется `[project.optional-dependencies].dev`) |
| `uv.lock` | Создать (`uv lock`) |
| `scripts/smoke_test.sh` | Заменить `python -m venv` + `pip install` → `uv` |

### CI Workflows (4 файла)
| Файл | Что меняется |
|---|---|
| `.github/workflows/ci.yml` | Заменить `setup-python` + pip → `astral-sh/setup-uv` + uv |
| `.github/workflows/tests.yml` | То же + убрать ручной `Cache pip` шаг (uv кэширует сам) |
| `.github/workflows/dev-build.yml` | pip install build twine → uv build + uv run twine |
| `.github/workflows/publish.yml` | То же |

### Документация (18 файлов)

#### Корень
- `README.md`

#### docs/
- `docs/INSTALLATION.md`
- `docs/QUICKSTART.md`
- `docs/index.html` — **сайт**
- `docs/pricing.html` — проверить наличие pip-блоков

#### docs/i18n/ (все языки: en, ru, zh, hi)
- `docs/i18n/README.md` (мультиязычный индекс)
- `docs/i18n/en/README.md` *(нет — только INSTALLATION/QUICKSTART/FIRST_RUN/USER_GUIDE)*
- `docs/i18n/en/INSTALLATION.md`
- `docs/i18n/en/QUICKSTART.md`
- `docs/i18n/en/FIRST_RUN.md`
- `docs/i18n/ru/README.md`
- `docs/i18n/ru/INSTALLATION.md`
- `docs/i18n/ru/QUICKSTART.md`
- `docs/i18n/ru/FIRST_RUN.md`
- `docs/i18n/zh/README.md`
- `docs/i18n/zh/INSTALLATION.md`
- `docs/i18n/zh/QUICKSTART.md`
- `docs/i18n/zh/FIRST_RUN.md`
- `docs/i18n/hi/README.md`
- `docs/i18n/hi/INSTALLATION.md`
- `docs/i18n/hi/QUICKSTART.md`
- `docs/i18n/hi/FIRST_RUN.md`

---

## Шаги миграции

### Шаг 1 — Установить uv локально и сгенерировать lockfile

```bash
# Установить uv (если не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Сгенерировать uv.lock из текущего pyproject.toml
uv lock

# Проверить, что зависимости резолвятся
uv sync
uv sync --extra dev
```

**Результат:** появляется `uv.lock` (коммитится в репо).

---

### Шаг 2 — Обновить `pyproject.toml`

Добавить секцию `[tool.uv]` и уточнить dev-зависимости:

```toml
# --- ДОБАВИТЬ в конец pyproject.toml ---

[tool.uv]
# Позволяет uv управлять виртуальным окружением автоматически
dev-dependencies = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-mock>=3.12.0",
    "pytest-cov>=4.1.0",
    "pytest-timeout>=2.1.0",
    "pytest-textual-snapshot>=0.4.0",
    "aioresponses>=0.7.6",
    "coverage>=7.3.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "flake8>=6.1.0",
    "pre-commit>=3.4.0",
    "textual[dev]>=8.0.0",
]
```

> **Примечание:** `requirements.txt` и `requirements-dev.txt` можно удалить после
> того как убедимся, что все CI пайплайны переключены.  
> Пока — оставить как резервные.

---

### Шаг 3 — Обновить `scripts/smoke_test.sh`

**До:**
```bash
VENV_DIR="$(mktemp -d)/pentool-smoke-venv"
python -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$WHEEL"
"$VENV_DIR/bin/python" -c "..."
"$VENV_DIR/bin/pentool" --help > /dev/null
```

**После:**
```bash
VENV_DIR="$(mktemp -d)/pentool-smoke-venv"
uv venv "$VENV_DIR" --quiet
uv pip install --quiet --python "$VENV_DIR/bin/python" "$WHEEL"
"$VENV_DIR/bin/python" -c "..."
"$VENV_DIR/bin/pentool" --help > /dev/null
```

> `uv venv` + `uv pip install` — без апгрейда pip, без warmup, ~5× быстрее.

---

### Шаг 4 — Обновить CI workflows

#### `ci.yml` и `tests.yml` — шаблон одного job:

**До:**
```yaml
- name: Set up Python ${{ matrix.python-version }}
  uses: actions/setup-python@v5
  with:
    python-version: ${{ matrix.python-version }}

- name: Cache pip
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}

- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -e ".[dev]"
    pip install aioresponses
```

**После:**
```yaml
- name: Set up uv
  uses: astral-sh/setup-uv@v4
  with:
    version: "latest"
    python-version: ${{ matrix.python-version }}  # uv сам устанавливает Python
    enable-cache: true                             # встроенный кэш uv

- name: Install dependencies
  run: uv sync --frozen --extra dev
```

> `--frozen` = использовать `uv.lock` без пересчёта; `enable-cache: true` заменяет
> ручной `Cache pip` шаг — удалить его.

#### `dev-build.yml` — сборка и публикация:

**До:**
```yaml
- name: Install build dependencies
  run: |
    python -m pip install --upgrade pip
    pip install build twine
```

**После:**
```yaml
- name: Set up uv
  uses: astral-sh/setup-uv@v4
  with:
    version: "latest"
    python-version: '3.11'
    enable-cache: true

- name: Build package
  run: uv build          # вместо python -m build

- name: Check package metadata
  run: uvx twine check dist/*   # uvx = ephemeral tool run без install
```

> `uv build` встроен, `python -m build` больше не нужен.  
> `uvx twine` запускает twine без постоянной установки.

#### `publish.yml` — аналогично `dev-build.yml`.

---

### Шаг 5 — Обновить документацию (MD-файлы)

Единый паттерн замен во **всех** языковых версиях:

#### A. Установка (вместо `pip install pentool`)

```bash
# Рекомендуемый способ — uv tool (изолированно, одна команда)
uv tool install pentool

# Или через pip (всё ещё работает)
pip install pentool
```

#### B. Виртуальное окружение из исходников

**До:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

**После:**
```bash
# uv создаёт .venv автоматически и активировать необязательно
uv sync --extra dev

# Запустить команды через uv:
uv run pentool
uv run pytest
```

#### C. pipx → uv tool

**До:**
```bash
pip install pipx
pipx install pentool
```

**После:**
```bash
# uv tool заменяет pipx для изолированных CLI-инструментов
uv tool install pentool
pentool
```

#### D. Системные зависимости (Linux/macOS)

**До:**
```bash
sudo apt install python3 python3-pip python3-venv
pip3 install pentool
```

**После:**
```bash
sudo apt install python3          # python3-pip и python3-venv больше не нужны
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install pentool
```

#### E. Обновление pip → обновление uv

**До:**
```bash
pip install --upgrade pip
pip install pentool --no-cache-dir
```

**После:**
```bash
uv self update                 # обновить сам uv
uv tool upgrade pentool        # обновить pentool
```

---

### Шаг 6 — Обновить сайт (`docs/index.html`)

Затронутые блоки (по строкам в текущем файле):

| Место | До | После |
|---|---|---|
| `<meta og:description>` | `pip install pentool` | `uv tool install pentool` |
| CTA-кнопка (строка ~324) | `📦 pip install pentool` | `📦 uv tool install pentool` |
| Terminal-блок (строка ~350) | `$ pip install pentool` | `$ uv tool install pentool` |
| h3-заголовок (строка ~406) | `pip install — done` | `uv tool install — done` |
| copy-подсказка (строка ~426-427) | `pip install pentool` | `uv tool install pentool` |

> Сохранить вторичный блок `pip install pentool` как альтернативный метод (для
> пользователей без uv), чтобы не потерять часть аудитории.

---

### Шаг 7 — Удалить устаревшие файлы

После того как все CI переключены и `uv.lock` стабилен:

```bash
git rm requirements.txt requirements-dev.txt
git commit -m "chore: remove legacy requirements files (replaced by uv.lock)"
```

---

## Порядок выполнения

```
1. Шаг 1 — uv lock локально         ← можно сделать сразу
2. Шаг 2 — pyproject.toml           ← вместе с шагом 1
3. Шаг 3 — smoke_test.sh            ← вместе с шагом 2
4. Шаг 4 — CI workflows             ← после успешного локального sync
5. Шаг 5 — все MD-документы         ← независимо, можно параллельно с 4
6. Шаг 6 — index.html / сайт        ← после шага 5
7. Шаг 7 — удалить requirements.*   ← последним, после зелёного CI
```

---

## Проверка после миграции

```bash
# 1. Чистый sync
uv sync --frozen --extra dev

# 2. Тесты
uv run pytest tests/unit/ -q

# 3. Smoke-test сборки
uv build
bash scripts/smoke_test.sh

# 4. Убедиться, что lockfile актуален
uv lock --check   # завершится с ошибкой если uv.lock устарел
```

В CI: зелёный `tests.yml` на ветке `feature/migrate-pip-to-uv` = готово к merge в `develop`.

---

## Обратная совместимость

- `pip install pentool` **продолжит работать** — мы не меняем сборку, только инструменты разработки.
- `uv.lock` **не обязателен** для конечных пользователей — он только для CI и разработчиков.
- Пользователи без uv могут по-прежнему ставить через `pip install pentool`.

---

## Ссылки

- [uv docs](https://docs.astral.sh/uv/)
- [astral-sh/setup-uv Action](https://github.com/astral-sh/setup-uv)
- [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)
