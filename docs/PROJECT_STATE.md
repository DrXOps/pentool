# Состояние проекта (факты)

<!-- СГЕНЕРИРОВАНО: python tools/verify_facts.py --render.
     Источник: tools/facts.yml. Руками не править: следующий рендер перезапишет. -->

**Обновлено:** 2026-11-25

Единственное место, где записано «что сейчас правда». Планы (`MYPLANS/`) описывают,
что делать, и ссылаются на эти id — состояние в них не повторяется, поэтому
расхождений между документами быть не может. История — в git (`git log tools/facts.yml`).

| Факт | Утверждение | Как проверено | Статус |
|---|---|---|---|
| `site.languages` | Сайт: 4 языка отдельными страницами (RU/EN/ZH/HI), EN в корне | языков в config: 4; страниц-каталогов: 3 | ✅ OK |
| `site.pages` | Сайт генерируется: 24 страницы + 5 редиректов, единый /assets/site.css | страниц 9 (index+pricing), общий CSS: True, редиректов 3 | ✅ OK |
| `site.published` | pentool.pro отдаёт новый сайт (новый CSS, страницы на 4 языках) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `payment.provider` | Оплата: Coinso, только криптовалюта; нигде не упоминается CryptoProc | Coinso упоминается: True; CryptoProc остался: False | ✅ OK |
| `mail.outbound` | Письма с ключом уходят с licence@pentool.pro (Resend, домен verified) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `license.trial` | 14-дневный триал запускается из UI (Settings → License) и из CLI | кнопка+воркер в UI: True; команда `license trial`: True | ✅ OK |
| `license.cli` | `pentool license` — status/activate/deactivate/trial; группа подключена к корню CLI | подключено к корню: ['license'] | ✅ OK |
| `license.texts` | Ни в TUI, ни в CLI нет ссылок на несуществующие команды вида `pentool license …`, которых нет | ссылок на несуществующие подкоманды нет | ✅ OK |
| `tui.module_catalog` | Каталог модулей один (module_catalog.py); вкладки, хоткеи, гейтинг и подсказки — производные | CATALOG есть: True; производные: {'module_tabs': True, 'hotkeys': True, 'project_manager': True, 'keyhintbar': True} | ✅ OK |
| `tui.action_row` | Ряд действий модуля — только header_spec(); Toolbar остался лишь как строка конфигурации Intruder | только header_spec() | ✅ OK |
| `tui.header_refresh` | Обновление шапки — одна реализация AppMixin.refresh_header, копий нет | копий _refresh_header_now: 0; AppMixin.refresh_header: True | ✅ OK |
| `tui.project_reload` | Смена проекта: ProjectReloadable; app/project_manager не трогают приватные поля экранов | обращений: 0; гвард: True | ✅ OK |
| `tui.tab_rename` | Переименование вкладок — одна реализация (TabRenameMixin) | миксин: True; потребители: ['panel', 'base']; копии: [] | ✅ OK |
| `intruder.payloads` | Payload-файлы: один парсер и один загрузчик (PayloadSources) вне экрана Интрудера | модуль: True; экран делегирует: True; общий парсер: True | ✅ OK |
| `tui.dead_code` | Мёртвый код удалён: custom_notify, hintbar_base, ProxyClearHistory, safe_notify | файлов осталось: нет; ProxyClearHistory: нет; safe_notify: нет | ✅ OK |
| `recon.prompts` | Промпты Recon в общем реестре задач (pro/…/ai_discovery/prompts.py удалён) | локальный prompts.py: False; задач в реестре: ['discovery_subdomains', 'discovery_endpoints', 'discovery_params'] | ✅ OK |
| `intruder.results_view` | Рендер результатов Интрудера вынесен: одна сборка Arrow-таблицы и один маппер строк | модуль: True; экран делегирует: True; маппер один: True; Arrow собирается в одном месте: True | ✅ OK |
| `repo.branches` | origin/develop и origin/main совпадают | origin/develop=66f4579 origin/main=66f4579 | ✅ OK |
| `ci.green` | CI на develop зелёный: Tests, CI, Dev Build (test-windows — advisory) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `license.core` | Лицензии: ядро AGPL-3.0, PRO — proprietary | ядро AGPL-3.0: True; PRO proprietary: True | ✅ OK |

`kind: external` — проверяется сетью или руками (`--online`), дата проверки хранится
в факте: устаревший внешний факт — это предупреждение, а не «сделано».
