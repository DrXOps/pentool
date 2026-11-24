# core

**Ядро приложения: конфигурация, события, лицензия, плагины, БД-схема, обновления.**

- **Связи:** [[utils]], [[api]], [[services]], [[cli]], [[deps/textual]]
- **Код:** pentool/core/
- **Источник:** pentool/core/*.py, tests/unit/core/; тексты про PRO-пакет —
  изменения 2026-11-24
- **Обновлено:** 2026-11-24

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
- `is_pro_package_compatible()` (`license.py`) — сверяет build metadata
  установленного PRO-пакета с версией базового пакета и возвращает
  `(совместим, сообщение для пользователя)`.
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
- **Тексты про несовместимый PRO-пакет адресуют пользователя в интерфейс, а не
  в CLI.** `is_pro_package_compatible()` (`license.py`, два сообщения:
  нет build metadata / расхождение версий) и `load_pro_module()`
  (`plugin_manager.py`, `FileNotFoundError` с путями поиска) раньше советовали
  `pentool license activate <key>` — такой команды нет; теперь оба говорят
  «Settings → License → Activate». Формулировку меняют вместе: это одна и та
  же подсказка в трёх местах (включая `pentool/cli/scan_runner.py`, см. [[cli]]).

## Связи

Базируется на [[utils]]. На него опираются [[api]], [[services]] и [[tui]].
Лицензионная логика определяет, какие модули [[modules]] доступны на free-плане.

## Источник

Код `pentool/core/*.py`; история тестов — `tests/conftest.py`
(коммиты `2d959fd`, `47d4f8f`); коммит `cb11bfd`. Правка сообщений о
PRO-пакете — изменения 2026-11-24 `pentool/core/license.py`
(`is_pro_package_compatible`) и `pentool/core/plugin_manager.py`
(`load_pro_module`) от 2026-11-24.
