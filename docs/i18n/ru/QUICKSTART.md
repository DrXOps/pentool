# 🚀 Быстрый старт Pentool

Начните работу с Pentool за 5 минут!

---

## Установка

```bash
# Установка из PyPI (рекомендуется)
uv tool install pentool

# Альтернатива: pip
# pip install pentool

# Или из исходников
git clone https://github.com/DrXOps/pentool.git
cd pentool
uv sync
```

---

## Первый запуск

```bash
pentool
```

Вы увидите TUI интерфейс с экраном Dashboard.

**Навигация:**
- `Tab` / `Shift+Tab` — переключение между виджетами
- `Ctrl+X` — открыть меню
- `Ctrl+Q` — выход

---

## 1. Настройка прокси в браузере

**Шаг 1:** Запустите Pentool Proxy
- Нажмите `Ctrl+X` → выберите "Proxy"
- Нажмите "○ Proxy", чтобы запустить его
- По умолчанию: `127.0.0.1:8080` (настраивается в Settings)

**Шаг 2:** Настройте браузер
- Firefox: Настройки → Сеть → Ручная настройка прокси
- Установите HTTP прокси: `127.0.0.1` порт `8080`
- Включите "Использовать этот прокси для HTTPS"

**Шаг 3:** Установите CA сертификат (для HTTPS)
- Pentool генерирует локальный CA при первом запуске proxy
  (`~/.config/pentool/certs/ca.crt`) — сертификат не покидает вашу машину
- На экране Proxy нажмите "Install CA cert" (или **Settings → Proxy →
  Install CA cert**) — откроется диалог с путём к сертификату и
  пошаговыми инструкциями для Firefox, Chrome и системной установки
- Firefox: `about:preferences#privacy` → Сертификаты → Просмотр
  сертификатов → вкладка **Центры сертификации** → Импорт → выберите
  `ca.crt` → отметьте "Доверять этому ЦС при идентификации веб-сайтов"

---

## 2. Перехват HTTP трафика

**В браузере:**
- Откройте любой сайт
- Трафик появится в Pentool → Proxy → HTTP History

**Intercept (перехват):**
- Нажмите "Intercept" в Proxy
- Модифицируйте запрос
- Нажмите "Forward" или "Drop"

---

## 3. Повтор запроса (Repeater)

1. В Proxy History: правый клик на запросе
2. Выберите "Send to Repeater"
3. В Repeater: измените параметры
4. Нажмите "Send" (`F5`)
5. Просмотрите ответ

---

## 4. Brute-force параметров (Intruder)

1. Send to Intruder из Proxy
2. Выделите параметр → "Mark Param"
3. Выберите тип атаки (Sniper, Battering Ram, Pitchfork)
4. Загрузите wordlist или введите payloads
5. Нажмите "Start Attack" (`F5`)

---

## 5. Сканирование уязвимостей (Scanner)

**Пассивное сканирование:**
- Включается автоматически при работе Proxy
- Анализирует весь трафик на уязвимости

**Активное сканирование:**
1. Перейдите в Scanner (`Shift+S`)
2. Введите URL цели
3. Выберите типы проверок
4. Нажмите "Start Scan" (`F5`)

**Проверяется:**
- XSS (Reflected, DOM, Stored)
- SQL Injection
- SSTI (Template Injection)
- LFI/Path Traversal
- RCE (Command Injection)
- SSRF, XXE, CORS
- JWT, OAuth уязвимости
- И многое другое...

---

## 6. Полезные инструменты

### Decoder
- `Shift+D` → откроет Decoder
- Поддержка: Base64, URL, HTML, Hex, Gzip, JWT
- Smart Decode: автоматическое определение кодировки

### Comparer
- `Shift+C` → откроет Comparer
- Вставьте два текста
- Получите diff с подсветкой

### Spider (краулинг)
- Нет отдельной вкладки — краулинг запускается в модуле **Target**
- Кнопка «🕷 Crawl Scope» — обойти все хосты в scope
- Кнопка «🕷 Crawl Host» — обойти выбранный в дереве хост
- Чекбокс «🤖 Use AI» — после обхода AI добавит неочевидные эндпоинты

---

## 7. Горячие клавиши

### Глобальные
- `Ctrl+Q` — выход
- `Ctrl+N` — новый проект
- `Ctrl+O` — открыть проект
- `Ctrl+S` — сохранить проект

### Навигация по модулям (Shift+буква)
- `Shift+H` — Dashboard
- `Shift+P` — Proxy
- `Shift+R` — Repeater
- `Shift+I` — Intruder
- `Shift+S` — Scanner
- `Shift+T` — Target
- `Shift+D` — Decoder
- `Shift+C` — Comparer
- `Shift+Q` — Sequencer
- `Shift+E` — Extensions
- `Shift+X` — Terminal

### В модулях
- `F5` — выполнить действие (Send, Start Scan, etc.)
- `F6` — остановить
- `Ctrl+F` — поиск/фильтр
- `m` — контекстное меню

---

## 8. Типичные сценарии

### Web App Testing
1. Запустите Proxy
2. Настройте браузер
3. Работайте с приложением
4. Анализируйте трафик в Proxy History
5. Отправляйте интересные запросы в Repeater/Intruder

### API Testing
1. Send to Repeater
2. Модифицируйте JSON body
3. Тестируйте различные параметры
4. Используйте Intruder для brute-force

### Vulnerability Discovery
1. Включите Passive Scanner
2. Работайте с приложением
3. Проверяйте Dashboard на findings
4. Запустите Active Scanner на целевой endpoint

---

## 9. Проекты

**Сохранение:**
- `Ctrl+S` — сохранить как .db (SQLite)
- `Ctrl+Shift+S` — экспортировать в JSON

**Загрузка:**
- `Ctrl+O` — открыть .db проект
- `Ctrl+Shift+O` — импортировать из JSON

**Проект включает:**
- Proxy history
- Scanner findings
- Intruder results
- Target sitemap
- Match/Replace rules
- Scope настройки

---

## 10. Настройки

`Ctrl+Comma` или `Shift+Settings`

**Interface:**
- Тема (Dark/Light)
- UI Mode (Basic/Advanced)

**Proxy:**
- Listen host/port
- Upstream proxy
- CA certificate

**Network:**
- User-Agent
- Timeouts
- SSL verification
- Collaborator URL

**License:**
- Активация PRO лицензии
- Просмотр доступных features

---

## Следующие шаги

- [Полное руководство](USER_GUIDE.md) — детальная документация всех функций
- [Установка](INSTALLATION.md) — расширенные инструкции по установке
- [GitHub](https://github.com/DrXOps/pentool) — исходный код, issues, discussions

---

## Нужна помощь?

- **Документация:** `docs/` в репозитории
- **Issues:** https://github.com/DrXOps/pentool/issues
- **Discussions:** https://github.com/DrXOps/pentool/discussions

---

**Приятного тестирования! 🔒**
