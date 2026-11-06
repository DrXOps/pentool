# tui

**Textual-интерфейс: приложение, экраны, виджеты, диалоги, миксины и система вкладок.**

- **Связи:** [[api]], [[core]], [[deps/textual]], [[deps/textual-fastdatatable]]
- **Код:** pentool/tui/
- **Источник:** pentool/tui/, коммиты `a753512`, `4e8b189`, `916ca9a`, `cb11bfd`; аудит TUI — `docs/tui-audit/REPORT.md`
- **Обновлено:** 2026-11-06

## Назначение

Самый крупный слой (96 `.py` + `.tcss`). Реализует TUI на Textual: набор
экранов модулей, общие виджеты и систему вкладок. Правило слоёв:
`tui → modules` запрещён — только через [[api]].

## Публичный интерфейс

- `PentoolApp` (`app.py`) — корневое приложение; монтирует экраны, содержит
  `ContentSwitcher` и условную загрузку PRO-экранов (Scanner, Recon).
- `screen_registry.py` — `SCREEN_MAP`, реестр экранов, ленивые импорты.
- `BaseModuleScreen` (`screens/base.py`) — база для экранов с вкладками.
- **Система вкладок**: `widgets/tab_panel.py::TabbedContentPanel` (Generic по
  типу состояния), `_TabState` / `_IntruderTabState`, стабильный `tab_uid`.
- Экраны: `proxy`, `repeater`, `intruder`, `decoder`, `comparer`, `sequencer`,
  `target`, `dashboard`, `extensions`, `settings`.
- Виджеты: `ContentPanel` (унификация HTTP-представлений), `Toolbar` (без
  дефолтного `id` — экраны монтируются одновременно, общий `#toolbar`
  разрешался в чужой виджет), `StartStopWidget` (единственный
  Start/Pause/Resume/Stop), `ProxyDataTable`, `ModuleTabs`, `FilterBar`,
  `StatusBar`.
- Диалоги, миксины (`autosave`, `ai_sync`, `auto_scope`, `content_clipboard`,
  `proxy_runtime`, `notifications`), `hotkeys/` (централизованный
  `HotkeyRegistry`).
- **Миксины**: `ContentClipboardMixin` (copy/paste `ContentPanel`),
  `AiModeSyncMixin` (подписка на `AiModeChanged` с отпиской в `on_unmount`),
  `AutoSaveMixin` (воркеры автосейва в группе `autosave`, отмена через
  `WorkerManager.cancel_group`).

## Инварианты и подводные камни

- **Каждый экран имеет собственный `.tcss`** рядом с `.py`; файлы обязаны быть
  перечислены в `[tool.setuptools.package-data]`, иначе wheel собирается, но
  падает в рантайме с `FileNotFoundError`.
- **PRO-экраны условны**: `ReconScreen` и `ScannerScreen` импортируются только
  при наличии сабмодуля `pro`; иначе — fallback `scanner_unavailable.py`.
- Вкладки адресуются `tab_uid`, а не именем/индексом: переименование вкладки
  не должно терять сохранённое состояние.
- `StartStopWidget` — единственный источник логики Start/Stop; `StartStopMixin`
  удалён (был мёртв в проде).
- **`@on(...)` в обычном миксине не регистрируется** — Textual собирает
  декораторы только из `__dict__` конкретного класса. В миксинах хендлеры
  объявляются по соглашению об именах (`on_<message_name>`), которое
  разрешается по MRO. Проверяется `tests/unit/tui/test_handler_name_dispatch.py`.
- **Имя хендлера выводится из `Message.handler_name`** = `on_` + snake_case от
  `__qualname__` класса сообщения. `ProxyDataTable.ScrolledToTop` →
  `on_proxy_data_table_scrolled_to_top` (одно подчёркивание); двойное
  встречается только у классов с ведущим `_`. Ошибка в имени = молча мёртвый
  хендлер, исключения не будет.
- `WorkerManager` умеет ровно шесть операций: `add_worker`, `cancel_all`,
  `cancel_group`, `cancel_node`, `start_all`, `wait_for_complete`. Отмена —
  по группе/узлу, не по имени воркера.
- Каждый `EventBus.subscribe`/`Config.add_observer` имеет парный
  `unsubscribe`/`remove_observer`: на уровне виджета — в `on_unmount`, для
  приложения — в `_on_exit_app`.

## Связи

Зависит от [[api]] и [[core]]. Опирается на [[deps/textual]] и
[[deps/textual-fastdatatable]]. PRO-экраны приходят из сабмодуля `pro`.

## Источник

Код `pentool/tui/`; коммиты `a753512` (Toolbar во все экраны), `b43782a`,
`ae5f5bb` (ContentPanel), `916ca9a`/`4e8b189` (вкладки Intruder), `cb11bfd`.
Аудит и решения: `docs/tui-audit/REPORT.md` (46 находок), `DECISIONS.md`
(ADR-1…ADR-12), `SUMMARY.md`.
