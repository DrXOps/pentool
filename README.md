# 🔐 PENTOOL — Modern Web Pentesting TUI

**Версия:** 1.0 (Pre-release)  
**Статус:** 87% готовности к релизу  
**Автор:** @sudores (DoctorX)

Современный инструмент для тестирования безопасности веб-приложений с интуитивным TUI интерфейсом.

---

## 🚀 Быстрый старт

```bash
# Установка
pip install pentool

# Запуск
pentool

# Или из исходников
git clone https://github.com/pentool/pentool.git
cd pentool
pip install -e .
pentool
```

---

## ✨ Ключевые возможности

### Основные инструменты (Free)
- **Proxy** — HTTP/HTTPS перехват с SSL
- **Repeater** — модификация и повтор запросов
- **Intruder** — автоматизированные атаки с payloads
- **Decoder** — кодирование/декодирование
- **Comparer** — сравнение запросов/ответов
- **HTTPQL** — мощная фильтрация истории

### PRO возможности
- **Turbo Mode Intruder** 🚀 — 10x ускорение (100-200 req/sec)
- **Scanner** — автоматическое обнаружение уязвимостей (23 проверки)
- **Spider** — автоматическое сканирование сайтов
- **WebSocket** — перехват и модификация WS трафика
- **AI Analysis** — анализ уязвимостей с помощью GPT-4
- **Plugins** — система расширений

---

## 📦 Установка

### Требования
- Python 3.10+
- Linux / macOS / Windows

### Из PyPI
```bash
pip install pentool
```

### Из исходников
```bash
git clone https://github.com/pentool/pentool.git
cd pentool
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate на Windows
pip install -e ".[dev]"
```

---

## 📖 Документация

- **Quick Start:** `docs/QUICKSTART.md`
- **User Guide:** `docs/user/`
- **API Reference:** `docs/API_CONTRACTS.md`
- **Architecture:** `docs/ARCHITECTURE_AUDIT.md`

---

## 🧪 Тестирование

```bash
# Запустить все тесты
pytest tests/

# С coverage
pytest tests/ --cov=pentool --cov-report=html

# Только unit-тесты
pytest tests/unit/ -v
```

**Текущий статус:**
- Unit-тесты: 1348/1360 PASSED (99.1%)
- Coverage: 29%
- Integration: требуют отладки

---

## 🏗️ Архитектура

```
pentool/
├── core/              # Ядро: EventBus, license, features
├── modules/           # Логика: proxy, scanner, intruder
├── api/               # API фасады для модулей
├── services/          # Оркестрация бизнес-логики
├── storage/           # База данных (SQLite)
├── tui/               # TUI интерфейс (Textual)
├── cli/               # CLI команды
├── plugins/           # Система плагинов
└── utils/             # Вспомогательные утилиты
```

---

## 💰 Тарифные планы

| Plan | Цена | Инструменты | Лимиты |
|------|------|-------------|--------|
| **Free** | $0 | Proxy, Repeater, Intruder Basic, Decoder | 500 записей истории, 10 потоков |
| **Lite** | $29/мес | + Scanner, Spider, Match&Replace | 5K истории, 20 потоков |
| **Medium** | $99/мес | + WebSocket, Plugins, Turbo Mode | 50K истории, 50 потоков |
| **Full** | $299/мес | + AI Analysis, PRO Reports, API | Unlimited |

---

## 🚀 Killer Features

### Turbo Mode Intruder
10x ускорение через HTTP Keep-Alive и connection pooling:
- Обычный режим: ~10-20 req/sec
- Turbo режим: ~100-200 req/sec

```python
from pentool.api.intruder_api import IntruderAPI

api = IntruderAPI()
await api.start_attack(config, turbo_mode=True)  # 🚀
```

### Коммерческие планы
4 тарифа с автоматической проверкой лимитов:
```python
from pentool.core.features import has_feature, get_limit

if has_feature("turbo_mode", plan):
    max_threads = get_limit("intruder_max_threads", plan)
```

---

## 🤝 Contributing

Contributions приветствуются! Перед началом:
1. Прочитай `docs/ARCHITECTURE_AUDIT.md`
2. Проверь `MYPLANS/MASTER_PLAN.md` для актуальных задач
3. Запусти тесты перед PR

---

## 📄 License

- **Community Edition:** AGPL-3.0
- **PRO Edition:** Commercial license

---

## 🔗 Ссылки

- **GitHub:** https://github.com/pentool/pentool
- **Docs:** https://pentool.dev/docs
- **Discord:** https://discord.gg/pentool

---

## 📊 Статус проекта

- **Готовность:** 87%
- **Последнее обновление:** 2026-07-22
- **Тесты:** 99.1% проходят
- **Прогноз релиза:** 1-8 августа 2026

**Проект в активной разработке. Релиз 1.0 скоро!** 🚀

---

*Создано с помощью Claude Opus 4.8*
