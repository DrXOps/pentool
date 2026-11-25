# Состояние проекта (факты)

<!-- СГЕНЕРИРОВАНО: python tools/verify_facts.py --render.
     Источник: tools/facts.yml. Руками не править: следующий рендер перезапишет. -->

**Обновлено:** 2026-11-25

Единственное место, где записано «что сейчас правда». Планы (`MYPLANS/`) описывают,
что делать, и ссылаются на эти id — состояние в них не повторяется, поэтому
расхождений между документами быть не может. История — в git (`git log tools/facts.yml`).

| Факт | Утверждение | Как проверено | Статус |
|---|---|---|---|
| `site.languages` | Сайт: 4 языка отдельными страницами (RU/EN/ZH/HI), EN в корне | проверка в `tools/verify_facts.py` | ✅ OK |
| `site.pages` | Сайт генерируется: 24 страницы + 5 редиректов, единый /assets/site.css | проверка в `tools/verify_facts.py` | ✅ OK |
| `site.published` | pentool.pro отдаёт новый сайт (новый CSS, страницы на 4 языках) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `payment.provider` | Оплата: Coinso, только криптовалюта; нигде не упоминается CryptoProc | проверка в `tools/verify_facts.py` | ✅ OK |
| `mail.outbound` | Письма с ключом уходят с licence@pentool.pro (Resend, домен verified) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `license.trial` | 14-дневный триал запускается из UI (Settings → License) и из CLI | проверка в `tools/verify_facts.py` | ✅ OK |
| `license.cli` | `pentool license` — status/activate/deactivate/trial; группа подключена к корню CLI | проверка в `tools/verify_facts.py` | ✅ OK |
| `license.texts` | Ни в TUI, ни в CLI нет ссылок на несуществующие команды вида `pentool license …`, которых нет | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.module_catalog` | Каталог модулей один (module_catalog.py); вкладки, хоткеи, гейтинг и подсказки — производные | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.action_row` | Ряд действий модуля — только header_spec(); Toolbar остался лишь как строка конфигурации Intruder | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.header_refresh` | Обновление шапки — одна реализация AppMixin.refresh_header, копий нет | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.project_reload` | Смена проекта: ProjectReloadable; app/project_manager не трогают приватные поля экранов | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.tab_rename` | Переименование вкладок — одна реализация (TabRenameMixin) | проверка в `tools/verify_facts.py` | ✅ OK |
| `intruder.payloads` | Payload-файлы: один парсер и один загрузчик (PayloadSources) вне экрана Интрудера | проверка в `tools/verify_facts.py` | ✅ OK |
| `tui.dead_code` | Мёртвый код удалён: custom_notify, hintbar_base, ProxyClearHistory, safe_notify | проверка в `tools/verify_facts.py` | ✅ OK |
| `recon.prompts` | Промпты Recon в общем реестре задач (pro/…/ai_discovery/prompts.py удалён) | проверка в `tools/verify_facts.py` | ✅ OK |
| `intruder.results_view` | Рендер результатов Интрудера вынесен: одна сборка Arrow-таблицы и один маппер строк | проверка в `tools/verify_facts.py` | ✅ OK |
| `intruder.tab_fields` | Поля активной вкладки Интрудера — один дескриптор вместо восьми пар property/setter | проверка в `tools/verify_facts.py` | ✅ OK |
| `repo.branches` | origin/develop и origin/main совпадают | проверка в `tools/verify_facts.py` | ✅ OK |
| `ci.green` | CI на develop зелёный: Tests, CI, Dev Build (test-windows — advisory) | проверено 2026-11-25: OK (ручная) | ⚠️ OK (ручная) |
| `license.core` | Лицензии: ядро AGPL-3.0, PRO — proprietary | проверка в `tools/verify_facts.py` | ✅ OK |

`kind: external` — проверяется сетью или руками (`--online`), дата проверки хранится
в факте: устаревший внешний факт — это предупреждение, а не «сделано».
