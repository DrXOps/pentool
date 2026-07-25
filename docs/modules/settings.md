# Settings — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную (77 тестов)

**Файлы:**
- `pentool/tui/screens/settings/screen.py` — TUI-экран (`SettingsScreen`, `OptionCycler`)
- `pentool/tui/screens/settings/hotkeys.py` — под-экран горячих клавиш (`HotkeySettingsScreen`)
- `pentool/tui/screens/settings/screen.tcss` — стили
- `pentool/core/config.py` — `Config`, `get_config()`, `Config.update()`, `Config.save()`
- `pentool/core/license.py` — `activate_license()`, `get_session_license()`, `get_machine_id()`

**Горячая клавиша:** `Shift+X`

---

## Назначение

Экран настроек приложения: интерфейс, параметры прокси, горячие клавиши, настройки проекта, управление лицензией. Монтируется как Widget в ContentSwitcher — не ModalScreen.

---

## Вкладки (`#settings-tabs`)

### Interface (`#tab-interface`)
| Элемент | ID | Описание |
|---------|-----|---------|
| OptionCycler | `#set-theme` | Тема: `Dark` / `Light` — переключается кликом |
| OptionCycler | `#set-ui-mode` | Режим: `Advanced` / `Basic` — скрывает вкладки в Basic |
| Кнопка Save | `settings-save` | Применить и сохранить |

**`OptionCycler`** — кастомный виджет: кликом циклически меняет значение, публикует `OptionCycler.Changed(value)`. Немедленно применяет тему при смене (`app.dark`).

**UI Mode Basic** скрывает продвинутые вкладки (Intruder, Decoder, и др.) через `ModuleTabs.set_mode()`.

---

### Proxy (`#tab-proxy`)
| Элемент | ID | Описание |
|---------|-----|---------|
| Input | `#set-proxy-host` | Хост прослушивания (по умолчанию `127.0.0.1`) |
| Input | `#set-proxy-port` | Порт (по умолчанию `8080`) |
| Input | `#set-upstream` | Upstream-прокси (`http://proxy:8080`) |
| Button | `settings-open-ca` | Открыть диалог установки CA-сертификата |
| Кнопка Save | `settings-save-proxy` | Сохранить в Config |

После сохранения: уведомление `"Proxy settings saved (restart proxy to apply)"`. Изменения применяются при следующем запуске прокси-сервера.

---

### Hotkeys (`#tab-hotkeys`)
Встроенный под-экран `HotkeySettingsScreen` — таблица горячих клавиш с возможностью изменения. Подробнее: `pentool/tui/screens/settings/hotkeys.py`.

---

### Project (`#tab-project`)
| Элемент | ID | Описание |
|---------|-----|---------|
| Input | `#set-autosave-path` | Путь для авто-сохранения (`project.json`) |
| Input | `#set-autosave-interval` | Интервал в секундах (`0` = выключено) |
| Checkbox | `#set-autosave-enabled` | Включить авто-сохранение |
| Кнопка Save | `settings-save-project` | Сохранить настройки проекта |

---

### License (`#tab-license`)
| Элемент | ID | Описание |
|---------|-----|---------|
| Static | `#license-status` | `● FREE` или `● PRO` (класс меняет цвет) |
| Static | `#license-plan` | Название плана |
| Static | `#license-expires` | Дата истечения |
| Static | `#license-machine-id` | Machine ID (первые 16 символов) |
| Input | `#license-key-input` | Поле для ввода лицензионного ключа (`XXXX-XXXX-XXXX-XXXX`) |
| Кнопка | `btn-license-activate` | Активировать лицензию |
| Кнопка | `btn-license-deactivate` | Деактивировать |
| Static | `#license-features` | Список доступных фич PRO |
| Static | `#license-error` | Ошибки активации (красный) |

**Активация**: асинхронный воркер `_async_activate(key)` — вызывает `activate_license(key)`, обновляет UI. При успехе — зелёный `● PRO`, фичи, дата истечения.

---

## `OptionCycler` — кастомный виджет

```python
class OptionCycler(Static):
    """Кнопка-переключатель: клик → следующее значение из списка."""

    class Changed(Message):
        value: str

    def __init__(self, options: list[tuple[str, str]], initial: str = "", **kwargs)
    # options: [(label, value), ...]
    # initial: начальное значение

    @property
    def value(self) -> str: ...         # текущее значение
    def set_value(self, value: str) -> None: ...  # программно установить
```

---

## Конфиг (`core/config.py`)

```python
from pentool.core.config import get_config

cfg = get_config()  # синглтон

# Чтение
cfg.proxy_host      # str: "127.0.0.1"
cfg.proxy_port      # int: 8080
cfg.scope           # list[str]
cfg.recent_projects # list[str]
cfg.theme           # str: "dark" | "light"

# Изменение + уведомление observers (не сохраняет в файл)
cfg.update(proxy_port=9090, theme="light")

# Сохранение в YAML
cfg.save()

# Observers
cfg.add_observer(callback)     # callback(changed_fields: set[str])
cfg.remove_observer(callback)
```

---

## Лицензия (`core/license.py`)

```python
from pentool.core.license import (
    get_session_license, activate_license,
    deactivate_license, get_machine_id,
)

# Текущая лицензия из кэша
info = get_session_license()
info.valid          # bool
info.plan           # "free" | "pro" | "enterprise"
info.expires_text   # "2026-12-31" или "—"
info.features       # list[str]: ["reports_pro", ...]
info.has_feature("reports_pro")  # bool
info.license_key    # str или ""
info.error          # str ошибки или ""

# Machine ID
mid = get_machine_id()  # str

# Активация (async)
info = await activate_license("XXXX-XXXX-XXXX-XXXX")

# Деактивация (async)
await deactivate_license()

# После активации/деактивации — обновить кэш
from pentool.core.license import refresh_session_license
refresh_session_license()
```

---

## Публичный API экрана

```python
# Программное обновление UI лицензии
screen._refresh_license_ui() -> None

# Загрузить текущий конфиг в поля
screen._load_current_config() -> None
```

---

## Известные проблемы / Исправленные баги

- Кнопки Save: `height: 3` без явного border/background — стандартный `Button`. `ToolbarButton` используется для Save.
- `.row { height: auto }` — обязательно, иначе `Input`/`Checkbox` обрезаются.
- `_save_project_settings()` сейчас только показывает уведомление — реальное сохранение autosave-интервала не реализовано.

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Settings (Shift+X) — экран с 5 вкладками: Interface / Proxy / Hotkeys / Project / License
- [ ] **Interface**: кликнуть `Dark` → меняется на `Light`, фон приложения меняется → кликнуть обратно на `Dark`
- [ ] **Interface**: кликнуть `Advanced` → меняется на `Basic`, некоторые вкладки в ModuleTabs скрываются
- [ ] **Interface**: нажать `Save` → уведомление "Interface settings applied"
- [ ] **Proxy**: изменить порт на `8888`, нажать Save → уведомление "Proxy settings saved (restart proxy to apply)"
- [ ] Перезапустить прокси → работает на порту `8888`
- [ ] Вернуть порт `8080`, сохранить
- [ ] **Proxy**: ввести upstream `http://127.0.0.1:8081`, сохранить
- [ ] **Proxy**: нажать `Install CA cert` → открывается диалог с инструкциями по установке
- [ ] **Hotkeys**: вкладка открывается, таблица горячих клавиш видна

### License
- [ ] **License**: вкладка показывает `● FREE`, Machine ID (16+ символов)
- [ ] Ввести неверный ключ `XXXX-XXXX-XXXX-XXXX` → нажать Activate → ошибка отображается красным в `#license-error`
- [ ] Ввести корректный PRO ключ → Activate → статус меняется на `● PRO`, показываются фичи и дата
- [ ] Deactivate → статус возвращается к `● FREE`

### Project
- [ ] **Project**: ввести путь `~/project.json`, интервал `60`, включить чекбокс → Save
- [ ] Переключиться между вкладками и вернуться → значения сохранились

### DEMO (дополнительно)
- [ ] Config Observer: изменить proxy_port в Settings → Dashboard обновляет отображение порта
- [ ] UI Mode Basic → нажать вкладку Intruder → вкладка скрыта или заблокирована
- [ ] UI Mode Advanced → все вкладки видны
- [ ] Перезапустить приложение → тема и порт сохранены из предыдущей сессии (YAML)
