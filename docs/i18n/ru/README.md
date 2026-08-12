# 🔒 Pentool — Профессиональный TUI-инструмент для веб-пентеста

> **🚧 Активная разработка — публичное демо/бета.** Основные модули стабильны и полностью рабочие. PRO-функции в активной разработке. Обратная связь и баг-репорты приветствуются.

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/DrXOps/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/DrXOps/pentool/actions)
[![License](https://img.shields.io/github/license/DrXOps/pentool)](../../../LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **Языки:** [English](../../../README.md) · [Русский](README.md) · [中文](../zh/README.md) · [हिन्दी](../hi/README.md)

---

**Pentool** — консольное приложение с текстовым интерфейсом (TUI) для пентестеров и специалистов по безопасности.  
Объединяет перехват трафика, сканирование уязвимостей, автоматизированные атаки и анализ данных — всё в одном терминале.  
Быстро, удобно, прозрачно.

> ⚠️ **Используйте современный терминал.** TUI Pentool построен на фреймворке [Textual](https://github.com/Textualize/textual) и опирается на поддержку мыши, true color и современный рендеринг. Легаси-терминалы (например, `cmd.exe` в Windows) будут отображаться некорректно. Рекомендуется: **Windows Terminal**, **iTerm2** (macOS), **GNOME Terminal / Kitty / Alacritty / WezTerm** (Linux). На Windows лучший опыт — запуск внутри **WSL**.

---

## ✨ Возможности

- **🌐 Прокси**  
  Перехватывайте и модифицируйте HTTP/HTTPS-трафик в реальном времени. Управляйте scope, применяйте правила Match & Replace, захватывайте WebSocket-сообщения.

- **🔄 Repeater**  
  Повторяйте запросы с любыми изменениями. Сохраняйте вкладки между сессиями, мгновенно переключайтесь между сценариями.

- **💥 Intruder**  
  Автоматизированные атаки с подстановкой данных. Четыре стратегии: Sniper, Battering Ram, Pitchfork, Cluster Bomb.  
  Turbo Mode даёт 10× прирост скорости за счёт Keep-Alive и пула соединений.

- **🔍 Сканер**  
  Активный и пассивный анализ: SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE, CORS, JWT-уязвимости и многое другое.  
  Контекстный подбор пейлоадов, WAF-байпас, time-based и boolean-blind техники.

- **🕷 Spider**  
  Автоматический краулинг: страницы, формы, API-эндпоинты, JS-файлы.  
  Поддерживается JavaScript-рендеринг через Playwright.

- **🎯 Target / Site Map**  
  Карта сайта на основе прокси-трафика, управление scope и фильтрация хостов прямо из интерфейса.

- **🔐 Decoder · Comparer · Sequencer**  
  - **Decoder** — 19 операций кодирования/декодирования/хэширования с поддержкой цепочек  
  - **Comparer** — side-by-side сравнение с подсветкой изменений  
  - **Sequencer** — анализ энтропии токенов (сессии, CSRF, JWT) с FIPS-тестами

- **🧩 Система плагинов**  
  Расширяйте функциональность без изменения ядра. PRO-плагины добавляют продвинутые сканеры, умные пейлоады и генераторы отчётов.

- **⚡ Асинхронное ядро**  
  Полностью async: тысячи одновременных соединений и сотни запросов в секунду.

- **📦 Установка одной командой**  
  `uv tool install pentool` — никакой сложной настройки. Работает на Linux, macOS, Windows (WSL).

- **🆓 Open Source + PRO-расширения**  
  Базовая версия полностью бесплатна и открыта. PRO-лицензия открывает эксклюзивные функции и поддерживает развитие проекта.

---

## 🚀 Быстрый старт

```bash
# Установка (рекомендуется)
uv tool install pentool

# Или через pip
# pip install pentool

# Активировать 14-дневный PRO-триал (разблокирует Scanner и другие PRO-функции)
# Выполните это ДО первого запуска TUI — если TUI уже открыт, перезапустите
# его после активации, чтобы он подхватил новую лицензию.
pentool license trial

# Запуск TUI
pentool

# Запуск прокси на нужном порту
pentool proxy start --port 8080

# Активное сканирование
pentool scan active --url https://example.com

# Проверка обновлений
pentool update --check
```

---

## 📸 Скриншоты

| Дашборд | Сканер |
|:---------:|:-------:|
| ![Dashboard](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/dashboard.png) | ![Scanner](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/scaner.png) |

| Прокси | Repeater |
|:-----:|:--------:|
| ![Proxy](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/proxy.png) | ![Repeater](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/repeater.png) |

| Intruder | Настройки |
|:--------:|:--------:|
| ![Intruder](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/intruder.png) | ![Settings](https://raw.githubusercontent.com/DrXOps/pentool/main/screens/settings.png) |

---

## 📚 Документация

- [🚀 Первый запуск: сертификат и первый перехват](FIRST_RUN.md) — начните отсюда
- [Быстрый старт](QUICKSTART.md)
- [Руководство пользователя](USER_GUIDE.md)
- [Установка](INSTALLATION.md)
- [Разработка плагинов](PLUGIN_DEVELOPMENT.md)
- [Справочник по Plugin API](../../API_CONTRACTS.md)

Полная документация: **[pentool.pro](https://pentool.pro)**

---

## 🧪 Демо / тестовый режим

> **Pentool сейчас находится в публичном демо/бета-режиме.**  
> Все **бесплатные модули полностью функциональны**. PRO-функции активно разрабатываются — доступен **14-дневный триал**, чтобы оценить всё заранее.

### 🎙 Для блогеров и авторов контента

Ведёте **блог по безопасности, YouTube-канал или Telegram-канал**?  
Напишите честный обзор и порекомендуйте Pentool своей аудитории — мы выдадим вам **постоянную PRO-лицензию совершенно бесплатно.**

Без минимального требования по подписчикам. Мы ценим качество, а не охват.  
→ Написать: **[@sudores](https://t.me/sudores)** в Telegram

---

## 💰 Поддержать проект

Pentool разрабатывается одним разработчиком в свободное время.  
Если он экономит вам часы на пентесте — рассмотрите возможность поддержать проект. Любой вклад напрямую финансирует новые функции, исправления и более быстрые релизы.

- ⭐ **[Звёздочка на GitHub](https://github.com/DrXOps/pentool)** — бесплатно, занимает 2 секунды, сильно помогает видимости
- 🔑 **PRO-лицензия** — получите ранний доступ и поддержите разработку → **[@sudores](https://t.me/sudores)**
- 💬 **Поделитесь** — расскажите коллеге, напишите обзор или упомяните Pentool в своих райтапах

> Разработка инструментов — одинокая работа. Звёздочка или доброе слово реально имеют значение. Спасибо. 🙏

---

## 🤝 Участие в разработке

Вклад в проект приветствуется!  
Пожалуйста, прочитайте [CONTRIBUTING.md](../../../CONTRIBUTING.md) перед созданием PR.

---

## 🙏 Благодарности

Особая благодарность:

- **[codeby.net](https://codeby.net/)** — за поддержку сообщества и обратную связь

---

## 📄 Лицензия

Распространяется под лицензией **AGPL-3.0**. Подробнее — в файле [LICENSE](../../../LICENSE).  
PRO-расширения доступны по коммерческой лицензии.

---

## 📬 Контакты

- **Сайт:** [pentool.pro](https://pentool.pro)
- **Telegram-канал:** [t.me/pentool_pro](https://t.me/pentool_pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** support@pentool.pro
- **Автор:** Анатолий Каштанов (DoctorX)

---

⭐ Если Pentool экономит твоё время — звёздочка на GitHub помогает проекту расти. Спасибо!
