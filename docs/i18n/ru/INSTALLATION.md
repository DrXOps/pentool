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

### Метод 1: PyPI (рекомендуется)

```bash
# Создать виртуальное окружение (рекомендуется)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# или
pentool-env\Scripts\activate  # Windows

# Установить
pip install pentool

# Проверить
pentool --version
```

### Метод 2: Из исходников

```bash
# Клонировать репозиторий
git clone https://github.com/docxqwerty/pentool.git
cd pentool

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Установить в режиме разработки
pip install -e ".[dev]"

# Проверить
pentool --version
```

### Метод 3: pipx (изолированная установка)

```bash
# Установить pipx
pip install pipx

# Установить pentool
pipx install pentool

# Запустить
pentool
```

---

## Инструкции для конкретных платформ

### Linux (Ubuntu/Debian)

```bash
# Установить системные зависимости
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Установить pentool
pip3 install pentool

# Запустить
pentool
```

### macOS

```bash
# Установить Homebrew (если не установлен)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Установить Python
brew install python@3.11

# Установить pentool
pip3 install pentool

# Запустить
pentool
```

### Windows

```powershell
# Установить Python с python.org
# https://www.python.org/downloads/

# Установить pentool
pip install pentool

# Запустить
pentool
```

---

## Установка CA сертификата

Для перехвата HTTPS трафика необходимо установить CA сертификат Pentool.

### Linux (Ubuntu/Debian)

```bash
# Скопировать сертификат
sudo mkdir -p /usr/local/share/ca-certificates/pentool
sudo cp ~/.config/pentool/ca.crt /usr/local/share/ca-certificates/pentool/

# Обновить хранилище сертификатов
sudo update-ca-certificates
```

### macOS

```bash
# Добавить в Keychain
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.config/pentool/ca.crt
```

### Windows

```powershell
# Импортировать сертификат
certutil -addstore -f "ROOT" %USERPROFILE%\.config\pentool\ca.crt
```

### Браузеры

**Firefox:**
1. Settings → Privacy & Security → Certificates → View Certificates
2. Import → выбрать `~/.config/pentool/ca.crt`
3. Отметить "Trust this CA to identify websites"

**Chrome/Chromium:**
1. Settings → Privacy and security → Security → Manage certificates
2. Authorities → Import
3. Выбрать `~/.config/pentool/ca.crt`

---

## Проверка установки

```bash
# Проверить версию
pentool --version

# Запустить TUI
pentool

# Запустить с опциями
pentool --help
```

---

## Устранение неполадок

### Python не найден

```bash
# Linux/macOS
which python3
python3 --version

# Windows
where python
python --version
```

### Ошибка установки пакетов

```bash
# Обновить pip
pip install --upgrade pip

# Установить с зависимостями сборки
pip install pentool --no-cache-dir
```

### Проблемы с правами доступа

```bash
# Linux/macOS - использовать виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install pentool
```

---

## Следующие шаги

- [Быстрый старт](QUICKSTART.md) — начните за 5 минут
- [Руководство пользователя](USER_GUIDE.md) — полная документация
- [GitHub](https://github.com/docxqwerty/pentool) — исходный код

---

**Нужна помощь?** Создайте issue на GitHub: https://github.com/docxqwerty/pentool/issues
