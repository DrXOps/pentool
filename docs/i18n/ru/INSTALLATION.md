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

---

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
