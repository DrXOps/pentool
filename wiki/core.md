# core

**Ядро приложения: конфигурация, события, лицензия, плагины, БД-схема, обновления.**

- **Связи:** [[utils]], [[api]], [[services]], [[deps/textual]]
- **Код:** pentool/core/
- **Источник:** pentool/core/*.py, tests/unit/core/
- **Обновлено:** 2026-11-05

## Назначение

Слой ниже модулей: не знает о доменной логике, но знает о процессе в целом.
Содержит синглтоны и глобальное состояние, поэтому правила слоёв запрещают
`core → modules/tui/api`.

## Публичный интерфейс

- `Config` (`config.py`) — единый конфиг; подменяется в тестах через
  контекст-менеджер `override_config(...)`.
- `EventBus` (`event_bus.py`) + события `events.py` (`ScanStarted`,
  `FindingDiscovered`, `ProxyRequestCaptured`, `ProjectSaved`, …).
- `LicenseInfo` (`license.py`) — план, фичи, `has_feature()`;
  глобальный кэш `_session_license`, `refresh_session_license()`.
- `Feature`, `Subscription`, `FeatureStatus` (`features.py`).
- `PluginManager` (`plugin_manager.py`) — загрузка плагинов из `plugins_dir`.
- `init_db()` (`db_schema.py`) — создание схемы SQLite.
- `StorageInterface` (`storage_interface.py`) — ABC хранилищ.
- `crash_reporter.py`, `error_guard.py`, `logging.py`, `updater.py`,
  `license_update.py`, `notification_sound.py`, `project.py`.
  `logging.py` — только `setup_logging()` и загрузка правил; сама
  фабрика `get_logger` и класс `_NamedLogger` живут в [[utils]]
  (`pentool.utils.logging`) и реэкспортируются отсюда.

## Инварианты и подводные камни

- **`_session_license` — процесс-глобальный кэш.** Тесты обязаны сбрасывать его
  между файлами (autouse-фикстура `_pin_clean_session_license` в
  `tests/conftest.py`); иначе лицензия «протекает» между тестами.
- **Лицензия влияет на доступность проверок сканера**: `BaseCheck.is_available()`
  сверяет `required_feature` с `get_session_license().has_feature(...)`.
  На free-плане PRO-проверки недоступны, и движок их молча пропускает.
- `Config` — изменяемый синглтон; тесты используют `override_config`, а не
  прямое присваивание (иначе состояние утекает в последующие тесты).

## Связи

Базируется на [[utils]]. На него опираются [[api]], [[services]] и [[tui]].
Лицензионная логика определяет, какие модули [[modules]] доступны на free-плане.

## Источник

Код `pentool/core/*.py`; история тестов — `tests/conftest.py`
(коммиты `2d959fd`, `47d4f8f`); коммит `cb11bfd`.
