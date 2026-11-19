# 📦 Руководство по установке Pentool

Полные инструкции по установке для всех платформ.

---

## Системные требования

### Минимальные
- Python 3.10 или выше
- 512 МБ RAM
- 100 МБ на диске
- Linux, macOS или Windows

### Рекомендуемые
- Python 3.11+
- 2 ГБ RAM
- 500 МБ на диске (с историей)
- Современный терминал с поддержкой Unicode

---

## Методы установки

### Метод 1: uv tool (рекомендуется)

[uv](https://docs.astral.sh/uv/) устанавливает pentool в изолированное окружение —
не нужно создавать venv вручную, нет конфликтов с системным Python.

```bash
# Установить uv (если ещё не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# Windows: winget install --id=astral-sh.uv -e

# Установить pentool
uv tool install pentool

# Проверить
pentool --version
```

### Метод 2: pip (альтернатива)

```bash
# Создать виртуальное окружение (рекомендуется)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# или
pentool-env\Scripts\activate     # Windows

# Установить
pip install pentool

# Проверить
pentool --version
```

### Метод 3: Из исходников (разработка)

```bash
# Клонировать репозиторий
git clone https://github.com/DrXOps/pentool.git
cd pentool

# Установить uv (если ещё не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить все зависимости (uv создаёт .venv автоматически)
uv sync

# Проверить
uv run pentool --version
```

---

## JS-рендеринг (необязательно, но рекомендуется)

Краулер Pentool может выполнять JavaScript, чтобы находить SPA-страницы и скрытые
API-эндпоинты. Движок по умолчанию — **Lightpanda**: лёгкий и быстрый
(~20 МБ памяти на запуск), не требует полного Chromium или Node.

Установка бинарника Lightpanda (Linux/macOS, x86_64 / aarch64):

```bash
# 1. скачайте бинарник релиза для вашей платформы из репозитория Lightpanda
#    (lightpanda-io/browser), например для Linux x86_64:
curl -L -o lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/0.3.7/lightpanda-x86_64-linux
chmod +x lightpanda
# 2. положите его в PATH, например:
mkdir -p ~/.local/bin && mv lightpanda ~/.local/bin/
```

Pentool находит бинарник автоматически (PATH, `~/.local/bin`, `/usr/local/bin`,
`/usr/bin` или переменная `LIGHTPANDA_BIN`). Без него краулинг работает, но НЕ
выполняет JavaScript (фолбэк на обычный HTTP).

> **Режим `--smart`** (загрузка страницы через прокси) также использует Lightpanda —
> отдельный Playwright/Chromium не нужен. Lightpanda обрабатывает JS для `--smart`
> и для модуля Spider.

---

## Инструкции для конкретных платформ

### Linux (Ubuntu/Debian)

```bash
# Установить Python (если нужно)
sudo apt update
sudo apt install python3

# Установить uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить pentool
uv tool install pentool

# Запустить
pentool
```

### macOS

```bash
# Установить Homebrew (если не установлен)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Установить uv через Homebrew
brew install uv
# или напрямую:
# curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить pentool
uv tool install pentool

# Запустить
pentool
```

### Windows

```powershell
# Установить uv
winget install --id=astral-sh.uv -e
# или через PowerShell:
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Установить pentool
uv tool install pentool

# Запустить
pentool
```

> **TUI в Windows требует WSL2.** Команд выше достаточно для CLI и headless-сканов
> (`--headless`). Для интерактивного интерфейса — прокси, ANSI-рамок, хуков —
> используйте WSL2: см. [Запуск в Windows через WSL2](#запуск-в-windows-через-wsl2).

---

## Запуск в Windows через WSL2

TUI рассчитывает на POSIX-терминал: прокси, хуки и ANSI-рамки опираются на
UTF-8 локаль. Внутри WSL2 (Ubuntu) всё работает так же, как в Linux. Команды
выполняйте в **оболочке WSL**, а не в PowerShell.

### 1. Установить WSL2 (PowerShell от администратора)

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
wsl --update
wsl --status
```

### 2. Локаль и UTF-8 — от этого зависят ANSI-символы рамок

```bash
sudo apt update
sudo apt install -y locales
sudo locale-gen en_US.UTF-8 ru_RU.UTF-8
sudo update-locale LANG=en_US.UTF-8
exec bash
echo $LANG    # должно быть en_US.UTF-8, а не C и не POSIX
```

`LANG=C`, `POSIX` или пустое значение — обычная причина `?` вместо рамок и
«кракозябр» в кириллице.

### 3. Шрифт, в котором есть нужные глифы

**Сторона Windows** (для Windows Terminal): установите **JetBrains Mono Nerd
Font** или **Cascadia Code NF** и выберите его в профиле терминала. Эмодзи
(`▶ ✖ 💥 🧭`) берутся из **Segoe UI Emoji** как fallback.

**Сторона WSL** (для Kitty):

```bash
sudo apt install -y unzip curl fonts-noto-color-emoji
mkdir -p ~/.local/share/fonts && cd ~/.local/share/fonts
curl -LO https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
unzip -o JetBrainsMono.zip && fc-cache -fv
```

### 4. Kitty (необязательно — Windows Terminal тоже подходит)

```bash
sudo apt install -y kitty
```

`~/.config/kitty/kitty.conf`:

```conf
font_family JetBrainsMono Nerd Font
font_size 12.0
# рамки и блоки
symbol_map U+2500-U+257F JetBrainsMono Nerd Font
# эмодзи
symbol_map U+1F300-U+1FAFF Noto Color Emoji
# более плавная отрисовка через WSLg
sync_to_monitor no
repaint_delay 8
```

Запуск: `kitty pentool`, либо из Windows: `wsl.exe -e kitty pentool`.

Если часть иконок панелей не рисуется — переключите набор в
**Settings → Interface → Panel icons** (`unicode` / `ascii` / `emoji`).

### 5. Проверка, что символы на месте

```bash
python3 -c "print('┌────┬────┐\n│ OK │ 42 │\n└────┴────┘')"
printf '█ ▓ ▒ ░  →  ✔ ✖ ⚠\n'
infocmp -1 | head -3    # TERM должен быть *-256color, не dumb
```

### 6. Если что-то всё равно не так

| Симптом | Причина | Лечение |
|---|---|---|
| Рамки из `?` или `+---+` | нет UTF-8 локали | шаг 2, `export LANG=en_US.UTF-8` |
| «Кракозябры» в кириллице | `LANG=C` / `POSIX` | шаг 2 |
| Рамки двойной ширины, вёрстка едет | в шрифте нет глифов рамок | шаг 3 |
| Иконки квадратами | нет emoji/Nerd шрифта | шаг 3 или набор `ascii` |
| TUI не стартует | `TERM=dumb` | `export TERM=xterm-256color` |
| Нет цветов | 8-цветный терминал | Windows Terminal или Kitty |

## Установка для разработки

```bash
# Клонировать репозиторий
git clone https://github.com/DrXOps/pentool.git
cd pentool

# Установить uv (если ещё не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить проект + все dev-инструменты (.venv создаётся автоматически)
uv sync

# Установить pre-commit хуки
uv run pre-commit install

# Запустить тесты
uv run pytest tests/unit/

# Запустить с покрытием
uv run pytest tests/ --cov=pentool --cov-report=html
```

---

## Зависимости

Pentool устанавливает их автоматически:

### Основные
- `textual>=8.0.0` — TUI-фреймворк
- `aiohttp>=3.9.0` — Async HTTP клиент
- `aiosqlite>=0.19.0` — Async SQLite
- `cryptography>=41.0.0` — SSL/TLS
- `click>=8.1.0` — CLI-фреймворк
- `pyyaml>=6.0` — Конфиг-файлы

---

## Устранение неполадок

### Команда pentool не найдена

```bash
# Linux/macOS — добавить в ~/.bashrc или ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Или пусть uv настроит PATH автоматически:
uv tool update-shell
```

### Ошибка установки пакетов

```bash
# uv
uv tool install pentool --no-cache

# pip
pip install pentool --no-cache-dir
```

### Проблемы с правами доступа

```bash
# uv tool install не трогает системный Python
uv tool install pentool
```

---

## Обновление

```bash
# uv
uv tool upgrade pentool

# pip
pip install --upgrade pentool
```

---

## Удаление

```bash
# uv
uv tool uninstall pentool

# pip
pip uninstall pentool

# Удалить все данные
rm -rf ~/.config/pentool
rm -rf ~/.local/share/pentool
```

---

## Следующие шаги

- [Быстрый старт](QUICKSTART.md) — начните за 5 минут
- [Руководство пользователя](USER_GUIDE.md) — полная документация
- [GitHub](https://github.com/DrXOps/pentool) — исходный код

---

**Нужна помощь?** Создайте issue на GitHub: https://github.com/DrXOps/pentool/issues
