# tui

**Textual-интерфейс: приложение, экраны, виджеты, диалоги, миксины и система вкладок.**

- **Связи:** [[api]], [[core]], [[deps/textual]], [[deps/textual-fastdatatable]]
- **Код:** pentool/tui/
- **Источник:** pentool/tui/, коммиты `a753512`, `4e8b189`, `916ca9a`, `cb11bfd`
- **Обновлено:** 2026-11-05

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
- Виджеты (32): `ContentPanel` (унификация HTTP-представлений), `Toolbar`,
  `StartStopWidget`/`StartStopMixin` (единые Start/Pause/Resume/Stop),
  `ProxyDataTable`, `ModuleTabs`, `MenuBar`, `FilterBar`, `StatusBar`.
- Диалоги, миксины (`autosave`, `auto_scope`, `proxy_runtime`, `notifications`),
  `hotkeys/` (централизованный `HotkeyRegistry`).

## Инварианты и подводные камни

- **Каждый экран имеет собственный `.tcss`** рядом с `.py`; файлы обязаны быть
  перечислены в `[tool.setuptools.package-data]`, иначе wheel собирается, но
  падает в рантайме с `FileNotFoundError`.
- **PRO-экраны условны**: `ReconScreen` и `ScannerScreen` импортируются только
  при наличии сабмодуля `pro`; иначе — fallback `scanner_unavailable.py`.
- Вкладки адресуются `tab_uid`, а не именем/индексом: переименование вкладки
  не должно терять сохранённое состояние.
- Миксины `StartStopMixin`/`StartStopWidget` — единственный источник логики
  Start/Stop; дублирование кнопок в экранах приводило к рассинхронизации.

## Связи

Зависит от [[api]] и [[core]]. Опирается на [[deps/textual]] и
[[deps/textual-fastdatatable]]. PRO-экраны приходят из сабмодуля `pro`.

## Источник

Код `pentool/tui/`; коммиты `a753512` (Toolbar во все экраны), `b43782a`,
`ae5f5bb` (ContentPanel), `8d75480` (StartStopMixin), `916ca9a`/`4e8b189`
(вкладки Intruder), `cb11bfd` (HEAD).
