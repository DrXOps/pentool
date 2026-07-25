"""Боковое меню навигации по модулям."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static
from pathlib import Path

_CSS = (Path(__file__).parent / "menu.tcss").read_text(encoding="utf-8")


# Список модулей: (id, отображаемое название, горячая клавиша)
MODULES: list[tuple[str, str, str]] = [
    ("dashboard",  "Dashboard",  "^H"),
    ("proxy",      "Proxy",      "^P"),
    ("repeater",   "Repeater",   "^R"),
    ("intruder",   "Intruder",   "^I"),
    ("scanner",    "Scanner",    "^S"),
    ("target",     "Target",     "^T"),
    ("decoder",    "Decoder",    "^D"),
    ("comparer",   "Comparer",   "^C"),
    ("sequencer",  "Sequencer",  "^Q"),
    ("extensions", "Extensions", "^E"),
    ("settings",   "Settings",   "^,"),
]

# Модули доступные в базовом режиме
BASIC_MODULES = {"dashboard", "proxy", "repeater", "intruder", "settings"}


class ModuleSelected(Message):
    """Событие: пользователь выбрал модуль."""

    def __init__(self, module_id: str) -> None:
        super().__init__()
        self.module_id = module_id


class _MenuItem(Static):
    """Один пункт меню — кликабельный Static."""

    DEFAULT_CSS = _CSS

    def __init__(self, mod_id: str, label: str, hotkey: str, **kwargs) -> None:
        super().__init__(f" {label:<12}[dim]{hotkey}[/dim]", **kwargs)
        self.mod_id = mod_id

    def on_click(self) -> None:
        self.post_message(ModuleSelected(self.mod_id))


class SideMenu(Widget):
    """Боковая панель навигации."""

    DEFAULT_CSS = _CSS

    active_module: reactive[str] = reactive("proxy")

    def compose(self) -> ComposeResult:
        yield Static(" PENTOOL ", classes="menu-header")
        for mod_id, label, hotkey in MODULES:
            yield _MenuItem(mod_id, label, hotkey, id=f"menu-{mod_id}")

    def on_mount(self) -> None:
        self._highlight(self.active_module)

    def on_module_selected(self, event: ModuleSelected) -> None:
        """Перехватываем событие от _MenuItem, обновляем подсветку и пробрасываем выше."""
        self.active_module = event.module_id
        self._highlight(event.module_id)

    def select_module(self, module_id: str) -> None:
        """Программно выбрать модуль (из горячей клавиши)."""
        self.active_module = module_id
        self._highlight(module_id)

    def _highlight(self, module_id: str) -> None:
        for mod_id, _, _ in MODULES:
            item = self.query_one(f"#menu-{mod_id}", _MenuItem)
            if mod_id == module_id:
                item.add_class("active")
            else:
                item.remove_class("active")
