"""MenuBar — горизонтальная полоса с каскадными выпадающими меню."""

from __future__ import annotations



from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static
from pathlib import Path

_CSS = (Path(__file__).parent / "menu_bar.tcss").read_text(encoding="utf-8")


class MenuItem(Static):
    """Пункт выпадающего меню."""

    DEFAULT_CSS = _CSS

    class Selected(Message):
        """Пользователь выбрал пункт меню."""
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(
        self,
        label: str,
        action: str = "",
        shortcut: str = "",
        disabled: bool = False,
        **kwargs,
    ) -> None:
        self._action = action
        self._shortcut = shortcut
        self._is_separator = label == "---"
        self._is_disabled = disabled or self._is_separator

        if self._is_separator:
            display_text = "─" * 20
        elif shortcut:
            display_text = f"{label:<22}{shortcut}"
        else:
            display_text = label

        super().__init__(display_text, **kwargs)

        if self._is_separator:
            self.add_class("-separator")
        if self._is_disabled:
            self.add_class("-disabled")

    def on_click(self) -> None:
        if self._is_disabled or not self._action:
            return
        self.post_message(self.Selected(self._action))


class MenuDropdown(Widget):
    """Выпадающий список пунктов меню."""

    DEFAULT_CSS = _CSS

    def __init__(self, items: list[tuple], **kwargs) -> None:
        super().__init__(**kwargs)
        self._items = items

    def compose(self) -> ComposeResult:
        for item in self._items:
            if item[0] == "---":
                yield MenuItem("---")
            elif len(item) == 2:
                yield MenuItem(item[0], action=item[1])
            elif len(item) == 3:
                yield MenuItem(item[0], action=item[1], shortcut=item[2])

    def show(self, x: int, y: int) -> None:
        self.styles.offset = (x, y)
        self.display = True

    def hide(self) -> None:
        self.display = False

    @on(MenuItem.Selected)
    def on_menu_item_selected(self, event: MenuItem.Selected) -> None:
        event.stop()
        self.hide()
        # Закрыть остальные дропдауны через MenuBar
        try:
            self.app.query_one("#menu-bar", MenuBar)._close_all()
        except Exception:
            pass
        action = event.action
        if action.startswith("app.action_"):
            # run_action принимает имя без префикса "action_"
            action_name = action[len("app.action_"):]
            self.app.run_worker(self.app.run_action(action_name), exclusive=False)


class MenuHeader(Static):
    """Заголовок одного меню (кликабельный)."""

    DEFAULT_CSS = _CSS

    class Activated(Message):
        """MenuHeader был нажат."""
        def __init__(self, header: MenuHeader) -> None:
            super().__init__()
            self.header = header

    def __init__(self, label: str, menu_id: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self._menu_id = menu_id

    @property
    def menu_id(self) -> str:
        return self._menu_id

    def on_click(self) -> None:
        self.post_message(self.Activated(self))


class MenuBar(Static):
    """Горизонтальная полоса с выпадающими меню — аналог десктопных приложений."""

    DEFAULT_CSS = _CSS

    # Структура: [(label, menu_id, [(item_label, action, shortcut?), ...])]
    MENUS: list[tuple[str, str, list]] = [
        ("PenTool", "burp", [
            ("About PenTool", "app.action_about"),
            ("Check for updates...", "app.action_check_updates"),
        ]),
        ("Project", "project", [
            ("New Project",  "app.action_new_project",  "Ctrl+N"),
            ("Open...",      "app.action_open_project",  "Ctrl+O"),
            ("Save",         "app.action_save_project",  "Ctrl+S"),
            ("Recent",       "app.action_recent_projects"),
            ("---", ""),
            ("Exit",         "app.action_quit",          "Ctrl+Q"),
        ]),
        ("Intruder", "intruder", [
            ("New Attack",   "app.action_intruder_new"),
            ("Start Attack", "app.action_intruder_start"),
            ("Stop Attack",  "app.action_intruder_stop"),
        ]),
        ("Repeater", "repeater", [
            ("Send to Repeater", "app.action_send_to_repeater"),
            ("New Tab",          "app.action_repeater_new_tab"),
        ]),
        ("View", "view", [
            ("Filter settings",        "app.action_filter_settings"),
            ("Toggle Dark/Light theme","app.action_toggle_theme"),
            ("Word wrap",              "app.action_toggle_word_wrap"),
        ]),
        ("Help", "help", [
            ("Documentation",      "app.action_documentation"),
            ("Keyboard shortcuts", "app.action_keyboard_shortcuts"),
            ("---", ""),
            ("CA Certificate",     "app.action_open_ca_cert"),
            ("---", ""),
            ("About",              "app.action_about"),
        ]),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_menu: str | None = None
        self._dropdowns: dict[str, MenuDropdown] = {}

    def compose(self) -> ComposeResult:
        for label, menu_id, items in self.MENUS:
            yield MenuHeader(label, menu_id, id=f"menu-header-{menu_id}")

        # Выпадающие списки монтируются вне MenuBar (через app.mount)
        # чтобы они поверх всего контента

    def on_mount(self) -> None:
        # Создаём дропдауны и монтируем в app
        for label, menu_id, items in self.MENUS:
            dropdown = MenuDropdown(items, id=f"menu-dropdown-{menu_id}")
            self._dropdowns[menu_id] = dropdown
            self.app.mount(dropdown)

    def on_unmount(self) -> None:
        for dropdown in self._dropdowns.values():
            try:
                dropdown.remove()
            except Exception:
                pass

    @on(MenuHeader.Activated)
    def on_menu_header_activated(self, event: MenuHeader.Activated) -> None:
        menu_id = event.header.menu_id
        if self._active_menu == menu_id:
            self._close_all()
            return

        self._close_all()
        self._open_menu(menu_id, event.header)

    def _open_menu(self, menu_id: str, header: MenuHeader) -> None:
        dropdown = self._dropdowns.get(menu_id)
        if dropdown is None:
            return

        # Вычисляем позицию под заголовком
        try:
            region = header.content_region
            x = region.x
            y = region.y + 1
        except Exception:
            x, y = 0, 1

        dropdown.show(x, y)
        header.add_class("-active")
        self._active_menu = menu_id

    def _close_all(self) -> None:
        for dropdown in self._dropdowns.values():
            dropdown.hide()
        for label, menu_id, _ in self.MENUS:
            try:
                header = self.query_one(f"#menu-header-{menu_id}", MenuHeader)
                header.remove_class("-active")
            except Exception:
                pass
        self._active_menu = None

    def on_key(self, event) -> None:
        if event.key == "escape":
            self._close_all()

    def on_click(self, event) -> None:
        # Клик вне MenuBar — закрыть (обрабатывается через app)
        pass
