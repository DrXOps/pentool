# Dashboard — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/tui/screens/dashboard/screen.py`
- `pentool/tui/screens/dashboard/screen.tcss`

**Горячая клавиша:** `Shift+H`

---

## Компоненты

| Виджет | ID | Описание |
|--------|----|---------|
| `Static` | `#logo` | ASCII-логотип Pentool |
| `LiveChart` | `#chart-requests` | Sparkline HTTP req/s |
| `LiveChart` | `#chart-findings` | Sparkline findings/s |
| `ThreatMeter` | `#threat-meter` | Gauge угрозы (0–100%) |
| `Static` | `#led-proxy-bar` | LED-статус прокси |
| `Static` | `#led-passive-bar` | LED-статус пассивного сканера |
| `Static` | `#led-scan-bar` | LED-статус активного скана |
| `Static` | `#led-spider-bar` | LED-статус Spider |
| `RichLog` | `#feed-log` | Live Feed событий |
| `Tree` | `#project-tree` | Дерево последних проектов |
| `SeverityMatrix` | `#vuln-matrix` | Heatmap по типу × severity |
| `RichLog` | `#terminal-log` | Вывод PTY-терминала |
| `Input` | `#terminal-input` | Ввод команд терминала |

---

## Публичный API

```python
dashboard.refresh_stats()                          # обновить статистику с диска
dashboard.add_finding(finding)                     # добавить finding (из EventBus)
dashboard.log_activity(msg, level)                 # системное сообщение в feed
dashboard.update_proxy_status(running, port)       # обновить LED прокси
dashboard.update_passive_status(enabled)           # обновить LED пассивного сканера
dashboard.update_scan_status(scanning, progress)   # обновить LED активного скана
dashboard.update_spider_status(running, pages)     # обновить LED Spider
dashboard.push_request(method, url, status)        # зарегистрировать HTTP-запрос
dashboard._populate_projects()                     # перезагрузить дерево проектов
```

---

## Исправленные баги (этап DCX, 2026-04-14)

| # | Проблема | Исправление |
|---|----------|-------------|
| БАГ-1 | `ThreatMeter` не смонтирован в DOM | Добавлен `yield ThreatMeter(id="threat-meter")` в `#top-row` |
| БАГ-2 | `SeverityMatrix` маппил `missing_security_header` и `info_leak` в `"XSS"` | Исправлен `type_map`: `Hdrs`, `Info`; добавлены `XXE`, `Hdrs`, `Info` в `_VULN_TYPES` |
| БАГ-3 | `BINDINGS` содержал broken `"n"` и `"ctrl+s"` без реализованных методов | Удалены из `BINDINGS` — перехватываются app.py |
| БАГ-4 | `_fetch_stats` запрашивал несуществующую таблицу `http_history` | Исправлено на `requests` (правильное имя таблицы в HttpStorage) |
| БАГ-5 | Кнопки `^ Open` и `v Save` — нелогичные иконки | Заменены на `📂 Open` и `💾 Save` |
| БАГ-6 | Hotkeys panel показывал `Shift+D Dashboard` (неверно) | Исправлено на `Shift+H Dashboard` |
| БАГ-7 | `_apply_stats` не обновлял `SeverityMatrix` | Добавлен вызов `matrix._refresh_display()` |

---

## Известные оставшиеся проблемы

| # | Проблема | Приоритет |
|---|----------|-----------|
| УX-1 | Boot animation показывает фиктивные OK-статусы независимо от реального состояния | Низкий (косметика) |
| УX-2 | `update_passive_status()` не вызывается из app.py при toggle passive | Средний |
| УX-3 | PTY double-echo: команда отображается дважды (ввод пользователя + echo PTY) | Низкий |
| УX-4 | `export_project_data()` в ProxyAPI читает RAM (`self._proxy.requests`), а не SQLite | Средний — при перезапуске теряется история |
| КОД-1 | `DEFAULT_CSS = open(...)` повторяется 4 раза в разных классах | Низкий (архитектура) |
| КОД-2 | `_fetch_stats` создаёт новый `ScannerAPI()` вместо переиспользования | Низкий |

---

## Загрузка проектов (исправлено в DCX)

**До исправления:** `_switch_project_db(path, is_new=False)` → только меняла указатель + показывала toast.

**После исправления:** При открытии существующей `.db` через Recent Projects или `Ctrl+O`:
1. Обновляется `cfg.db_path` и `HttpStorage.db_path`
2. `_reload_project_screens(path)` в фоне (async worker):
   - `ProxyScreen.load_from_project()` → перечитывает историю из новой БД
   - `ScannerScreen._load_findings_worker()` → перечитывает findings из новой БД
   - `TargetScreen._load_sitemap()` → перечитывает SiteMap
   - `DashboardScreen.refresh_stats()` → обновляет статистику

---

## Чеклист ручного тестирования

### MVP
- [ ] При запуске Dashboard показывается ASCII-логотип
- [ ] `Shift+H` переключает на Dashboard из других экранов
- [ ] LiveChart req/s обновляется при прохождении запросов через прокси
- [ ] ThreatMeter обновляется при добавлении findings
- [ ] LED-индикаторы меняются при старте/стопе прокси
- [ ] Live Feed показывает события (proxy requests, findings)
- [ ] Дерево Recent Projects показывает список; клик открывает проект
- [ ] После открытия проекта ProxyScreen содержит реальную историю из БД
- [ ] После открытия проекта ScannerScreen содержит реальные findings
- [ ] SeverityMatrix обновляется при add_finding (правильные типы)
- [ ] Терминал: ввод команды → вывод отображается в terminal-log
- [ ] Кнопки `+ New`, `📂 Open`, `💾 Save` открывают диалоги
- [ ] Кнопка `r` (Refresh) обновляет статистику

### DEMO (дополнительно)
- [ ] Sparkline-графики плавно анимируются при нагрузке
- [ ] ThreatMeter показывает правильный уровень (WEAK/MODERATE/HIGH/CRITICAL)
- [ ] SeverityMatrix не смешивает типы (Hdrs ≠ XSS, Info ≠ XSS)
- [ ] Boot animation воспроизводится один раз при запуске
- [ ] При создании нового проекта дерево обновляется сразу
- [ ] `led-passive-bar` меняется при toggle Passive в Scanner
