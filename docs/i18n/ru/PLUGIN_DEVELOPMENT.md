# 🧩 Разработка плагинов Pentool

Система плагинов Pentool позволяет расширять инструмент без изменения ядра —
добавить новый экран TUI, команду CLI, собственный активный сканер или
пассивную проверку, которая запускается на каждом запросе через прокси.

---

## Где живут плагины

| Расположение | Назначение |
|---|---|
| `~/.pentool/plugins/` | Ваши собственные плагины — загружаются автоматически при каждом старте (`PluginManager.load_user_plugins()`) |
| `pentool/plugins/builtin/` | Плагины, поставляемые с FREE-версией |
| PRO-пакет (`~/.pentool/pro/pentool/plugins/builtin/`) | Плагины, скачанные через `pentool license trial`/`activate` |

Поместите `.py`-файл в `~/.pentool/plugins/` — Pentool подхватит его
автоматически при следующем запуске. Файлы, начинающиеся с `_`, пропускаются.

> ⚠️ Плагины из нестандартных/недоверенных путей логируются с
> предупреждением — загружайте только код, которому доверяете: плагин
> выполняется с полными правами процесса.

---

## Минимальный плагин

Каждый плагин — это один Python-файл с двумя вещами:

1. Класс, наследующий `BasePlugin` — только метаданные.
2. Функция модуля `register(hook: PluginHook)` — точка входа, которую
   Pentool вызывает после загрузки файла.

```python
"""Мой первый плагин."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.plugin_manager import BasePlugin, PluginHook


class HelloScreen(Widget):
    """Простой экран, добавленный плагином."""

    def compose(self) -> ComposeResult:
        yield Static("Привет от моего плагина!")


class MyPlugin(BasePlugin):
    name = "my_plugin"          # уникальный ID, snake_case
    version = "1.0"
    author = "you"
    description = "Мой первый плагин Pentool"
    api_version = 1              # текущая версия Plugin API
    required_feature = ""        # "" = бесплатный плагин, PRO-лицензия не нужна


def register(hook: PluginHook) -> None:
    """Вызывается один раз при загрузке плагина."""
    hook.register_screen("My Screen", HelloScreen)
```

Сохраните это как `~/.pentool/plugins/my_plugin.py` и перезапустите Pentool
— в переключателе модулей появится новый пункт.

Полный рабочий пример, поставляемый вместе с Pentool:
`pentool/plugins/example_plugin.py` (+ `example_plugin.tcss` для стилей на
Textual CSS).

---

## Атрибуты `BasePlugin`

| Атрибут | Тип | Значение |
|---|---|---|
| `name` | `str` | Уникальный ID плагина (snake_case) |
| `version` | `str` | Строка версии, например `"1.0"` |
| `author` | `str` | Имя автора |
| `description` | `str` | Краткое описание |
| `api_version` | `int` | Версия Plugin API, на которую ориентирован плагин. Плагины с версией новее, чем `CURRENT_API_VERSION` у Pentool, отклоняются как несовместимые |
| `required_feature` | `str` | Пустая строка = бесплатный плагин. Укажите имя фичи лицензии (например `"scanner_pro"`), чтобы заблокировать плагин за PRO-лицензией — проверяется через `get_session_license()` |

---

## Что можно зарегистрировать через `PluginHook`

```python
def register(hook: PluginHook) -> None:
    hook.register_screen(name, widget_class, hotkey=None)
    hook.register_cli_command(group_name, click_command)
    hook.register_scanner(scanner_class)       # подкласс BaseScanner
    hook.register_passive_check(check_class)   # подкласс BaseCheck
```

### `register_screen(name, widget_class, hotkey=None)`
Добавляет новый модуль/экран в переключатель модулей TUI. `widget_class`
должен быть подклассом `textual.widget.Widget` (см. `HelloScreen` выше).

### `register_cli_command(group_name, command)`
Добавляет `click.Command` в существующую группу CLI-команд (например
`scan`, `proxy`) — расширяет `pentool <group> <ваша-команда>`.

### `register_scanner(scanner_class)`
Регистрирует плагин-сканер — подкласс `BaseScanner`, группирующий одну или
несколько `BaseCheck` под одним именем:

```python
from pentool.core.plugin_manager import BaseScanner, BaseCheck

class MyCheck(BaseCheck):
    name = "my_check"
    description = "Обнаруживает что-то своё"
    severity = "medium"      # critical | high | medium | low | info
    passive = False          # True = запускается автоматически на каждом запросе через прокси

    async def scan(self, target, http_client, **kwargs) -> list:
        findings = []
        # ... ваша логика обнаружения ...
        return findings

class MyScanner(BaseScanner):
    name = "my_scanner"
    checks = [MyCheck]
```

### `register_passive_check(check_class)`
Регистрирует отдельную пассивную `BaseCheck`, которая запускается на каждом
запросе, проходящем через прокси (без активного скана) — полезно для лёгких
всегда включённых проверок (утечки информации, секреты, проблемы заголовков).

---

## Плагины за PRO-лицензией

Установите `required_feature` на строку фичи лицензии, чтобы требовать
PRO-лицензию:

```python
class MyProPlugin(BasePlugin):
    name = "my_pro_plugin"
    required_feature = "scanner_pro"
```

Если активная лицензия не покрывает `"scanner_pro"`, плагин пропускается с
записью WARNING в лог — остальная часть Pentool продолжает работать
нормально.

---

## Тестирование плагина

Специального тестового окружения нет — плагины это обычный Python. Пишите
обычные unit-тесты для ваших классов `BaseCheck.scan()`/`BasePlugin`, и
проведите ручную проверку, поместив файл в `~/.pentool/plugins/` и
перезапустив Pentool. Проверьте лог (`~/.config/pentool/pentool.log`) на
строки `Plugin '<name>': registered ...`, подтверждающие загрузку.

---

## Смотрите также

- [Справочник по API / все API модулей](../../API_CONTRACTS.md) —
  ProxyAPI, ScannerAPI, IntruderAPI, SpiderAPI, RepeaterAPI, TargetAPI,
  DecoderAPI, ComparerAPI, SequencerAPI
- `pentool/core/plugin_manager.py` — полный исходный код `BasePlugin`,
  `BaseCheck`, `BaseScanner`, `PluginHook`, `PluginManager`
- `pentool/plugins/example_plugin.py` — полный рабочий пример
