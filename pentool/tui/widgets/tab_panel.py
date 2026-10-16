"""TabbedContentPanel — универсальный таб-контейнер с изоляцией.

Каждый таб получает свой TabPane с виджетами, собранными build_tab_ui().
Модуль-владелец:
1. Определяет датакласс TabState
2. Передаёт build_tab_ui (синхронно строит TabPane), save_tab, load_tabs
3. Подписывается на сообщения TabActivated / TabDeactivated

NB: Внутренние ID виджетов НЕ ИМЕЮТ ЗНАЧЕНИЯ для @on-декораторов экрана —
все коммуникации идут через сообщения TabbedContentPanel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, TypeVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Tab, TabbedContent, TabPane

# ── Hooks (опциональные) ──────────────────────────────────────────────
# Модуль может передать callable, который будет вызван при определённых
# событиях. Например, при создании таба — сохранить в БД.
# Они не обязательны: модуль может подписаться на сообщения.


@dataclass
class _TabMeta:
    """Внутреннее состояние таба в контейнере."""
    tab_id: str
    pane: TabPane
    name: str


TState = TypeVar("TState")


class TabbedContentPanel(Widget, Generic[TState]):
    """Универсальный контейнер с изолированными табами.

    Generic[TState] — модуль передаёт свой датакласс (например _IntruderTabState).

    Параметры:
        id: ID контейнера в DOM (нужен для @on-фильтрации).
        tab_id_prefix: префикс для генерации tab_id (напр. "intruder-tab-").
        build_tab_ui: (state, tab_id) -> TabPane. Синхронно собирает виджеты.
        save_tab: (state) -> Awaitable. Сохранить состояние таба.
        load_tabs: () -> Awaitable[list[state]]. Загрузить все табы.
    """

    # ── Сообщения ──────────────────────────────────────────────────────
    # Все сообщения принимают владельца (сам TabbedContentPanel) и отдают
    # его через `control`. Это требуется @on(TabActivated, "#intruder-tabs"):
    # декоратор матчит CSS-селектор против message.control, поэтому control
    # обязан вернуть сам виджет-панель (по паттерну Textual TabbedContent).

    class TabCreated(Message):
        """Постится ПОСЛЕ создания таба."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner
        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabActivated(Message):
        """Постится ПОСЛЕ переключения на новый таб."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner
        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabDeactivated(Message):
        """Постится ДО переключения на другой таб (старый ещё активен)."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner
        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    class TabClosed(Message):
        """Постится ПОСЛЕ закрытия таба."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, owner: "TabbedContentPanel", tab_id: str, tab_state: object) -> None:
            self.tab_id = tab_id
            self.tab_state = tab_state
            super().__init__()
            self._owner = owner
        @property
        def control(self) -> "TabbedContentPanel":
            return self._owner

    # ── Конфигурация ────────────────────────────────────────────────────

    def __init__(
        self,
        *,
        id: str = "tcp",
        tab_id_prefix: str = "tcp-tab-",
        build_tab_ui: Callable[[TState, str], TabPane] | None = None,
        mount_tab_ui: Callable[[TState, str], None] | None = None,
        save_tab: Callable[[TState], Awaitable[None]] | None = None,
        load_tabs: Callable[[], Awaitable[list[TState]]] | None = None,
        rename_input_id: str = "tcp-rename-input",
        # Минимальное число табов (1 = нельзя закрыть последний)
        min_tabs: int = 1,
    ) -> None:
        super().__init__(id=id)
        self._tab_id_prefix = tab_id_prefix
        self._build_tab_ui = build_tab_ui
        self._mount_tab_ui = mount_tab_ui
        self._save_tab = save_tab
        self._load_tabs_fn = load_tabs
        self._rename_input_id = rename_input_id
        self._min_tabs = min_tabs

        # ── Состояние ──────────────────────────────────────────────────
        self._states: dict[str, TState] = {}   # tab_id → state
        self._meta: dict[str, _TabMeta] = {}   # tab_id → meta
        self._counter: int = 0
        self._active_tab_id: str | None = None
        self._generation: int = 0

        # ── Generation guard ────────────────────────────────────────────
        # Для защиты от stale callbacks при смене проекта.
        # Экран вызывает set_generation_guard() перед load_tabs_from_storage().
        self._tabs_generation: int = 0

    # ── compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield TabbedContent(id=f"{self.id}-content")
        inp_rename = Input(id=self._rename_input_id, placeholder="Tab name...", compact=True)
        inp_rename.display = False
        yield inp_rename

    # ── Свойства ────────────────────────────────────────────────────────

    @property
    def tabs_content(self) -> TabbedContent:
        return self.query_one(f"#{self.id}-content", TabbedContent)

    @property
    def active_tab_id(self) -> str | None:
        return self._active_tab_id

    @property
    def active_state(self) -> TState | None:
        if self._active_tab_id is None:
            return None
        return self._states.get(self._active_tab_id)

    @property
    def tab_count(self) -> int:
        return len(self._states)

    @property
    def all_states(self) -> list[TState]:
        return list(self._states.values())

    # ── Generation guard ──────────────────────────────────────────────────

    def set_generation(self, gen: int) -> None:
        """Установить поколение для stale-защиты при смене проекта."""
        self._tabs_generation = gen

    def _is_stale(self) -> bool:
        """Проверить, не сменилось ли поколение (stale callback)."""
        return self._tabs_generation == 0  # simplified; screen sets it

    # ── Lifecycle: создание / закрытие / переключение ────────────────────

    def action_new_tab(self, *, state: TState | None = None, name: str | None = None) -> str:
        """Создать новый таб.

        Args:
            state: готовый TabState (из load_tabs или default).
            name: имя таба (если state не передан).

        Returns:
            tab_id.
        """
        self._counter += 1
        tab_id = f"{self._tab_id_prefix}{self._counter}"
        if state is None:
            name = name or f"Tab {self._counter}"
            import uuid
            state = self._make_default_state(tab_id, name)
            state.tab_id = tab_id
            if hasattr(state, "tab_uid"):
                state.tab_uid = uuid.uuid4().hex
            if hasattr(state, "name"):
                state.name = name

        # ШАГ 1: Создаём empty TabPane и добавляем в TabbedContent (чтобы был в DOM)
        pane = TabPane(getattr(state, "name", f"Tab {self._counter}"), id=tab_id)
        self._states[tab_id] = state
        meta = _TabMeta(tab_id=tab_id, pane=pane, name=getattr(state, "name", f"Tab {self._counter}"))
        self._meta[tab_id] = meta

        try:
            tc = self.tabs_content
            tc.add_pane(pane)
            tc.active = tab_id
        except Exception:
            pass

        self._active_tab_id = tab_id

        # Запланировать построение UI и сообщения (после того как виджет в DOM)
        self.call_after_refresh(self._post_tab_messages, tab_id, state)
        return tab_id

    def _post_tab_messages(self, tab_id: str, state: TState) -> None:
        """Post messages after widget is ready."""
        # 1. Mount per-tab виджеты в TabPane (TabPane уже в DOM после add_pane)
        self._do_build_ui(tab_id, state)
        # 2. Постим сообщения для экрана
        self.post_message(self.TabCreated(self, tab_id, state))
        self.post_message(self.TabActivated(self, tab_id, state))

    def _do_build_ui(self, tab_id: str, state: TState) -> None:
        """Mount per-tab виджеты в TabPane (TabPane уже в DOM)."""
        if tab_id not in self._states:
            return
        if self._mount_tab_ui:
            self._mount_tab_ui(state, tab_id)

    def _make_default_state(self, tab_id: str, name: str) -> TState:
        """Создать пустой TabState (если модуль не передал)."""
        if hasattr(self, "_default_state_factory") and self._default_state_factory is not None:
            return self._default_state_factory(tab_id, name)
        @dataclass
        class _DummyState:
            tab_id: str = ""
            name: str = ""
            template_text: str = ""
        return _DummyState(tab_id=tab_id, name=name)  # type: ignore[return-value]

    def set_default_state_factory(self, factory):
        """Установить фабрику для создания TabState по умолчанию."""
        self._default_state_factory = factory

    def action_close_tab(self) -> None:
        """Закрыть активный таб (если > min_tabs)."""
        if len(self._states) <= self._min_tabs:
            return
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        state = self._states.get(tab_id)
        try:
            tc = self.tabs_content
            tc.remove_pane(tab_id)
        except Exception:
            pass
        self._states.pop(tab_id, None)
        self._meta.pop(tab_id, None)
        # Switch to last remaining tab
        if self._states:
            new_id = list(self._states.keys())[-1]
            self._active_tab_id = new_id
            try:
                tc = self.tabs_content
                tc.active = new_id
            except Exception:
                pass
        else:
            self._active_tab_id = None
        if state is not None:
            self.post_message(self.TabClosed(self, tab_id, state))

    def switch_to(self, tab_id: str) -> None:
        """Программное переключение на таб по id."""
        if tab_id not in self._states:
            return
        # Deactivate old
        old_id = self._active_tab_id
        if old_id and old_id in self._states and old_id != tab_id:
            old_state = self._states[old_id]
            self.post_message(self.TabDeactivated(self, old_id, old_state))
        # Activate new
        self._active_tab_id = tab_id
        try:
            tc = self.tabs_content
            tc.active = tab_id
        except Exception:
            pass
        state = self._states.get(tab_id)
        if state is not None:
            self.post_message(self.TabActivated(self, tab_id, state))

    def get_any_tab_id(self) -> str | None:
        """Вернуть любой tab_id (для тестов)."""
        if self._states:
            return next(iter(self._states))
        return None

    async def close_all(self) -> None:
        """Закрыть все табы (при смене проекта)."""
        for tab_id, state in list(self._states.items()):
            try:
                tc = self.tabs_content
                tc.remove_pane(tab_id)
            except Exception:
                pass
            self.post_message(self.TabClosed(self, tab_id, state))
        self._states.clear()
        self._meta.clear()
        self._counter = 0
        self._active_tab_id = None

    async def load_from_storage(self) -> None:
        """Загрузить табы из хранилища (через load_tabs)."""
        if self._load_tabs_fn is None:
            return
        try:
            states = await self._load_tabs_fn()
        except Exception:
            return
        if not states:
            return
        for st in states:
            tab_id = getattr(st, "tab_id", "")
            if not tab_id:
                continue
            # Avoid duplicates
            existing_tab_id = self._find_by_tab_uid(st)
            if existing_tab_id:
                continue
            self.action_new_tab(state=st)

    def _find_by_tab_uid(self, state: TState) -> str | None:
        """Поиск таба по tab_uid (чтобы не создать дубликат)."""
        uid = getattr(state, "tab_uid", None)
        if not uid:
            return None
        for tid, st in self._states.items():
            if getattr(st, "tab_uid", None) == uid:
                return tid
        return None

    # ── Rename (double-click) ───────────────────────────────────────────

    def on_click(self, event: Click) -> None:
        """Double-click на Tab → rename."""
        if event.chain < 2:
            return
        widget = event.widget
        if not isinstance(widget, Tab):
            return
        # Определяем tab_id из Tab
        tab_widget_id = widget.id or ""
        if not tab_widget_id.startswith("--content-tab-"):
            return
        pane_id = tab_widget_id.removeprefix("--content-tab-")
        if pane_id not in self._states:
            return
        event.stop()
        self._start_rename(pane_id)

    def _start_rename(self, tab_id: str) -> None:
        state = self._states.get(tab_id)
        if state is None:
            return
        try:
            inp = self.query_one(f"#{self._rename_input_id}", Input)
            inp.value = getattr(state, "name", "Tab")
            inp.display = True
            inp.focus()
            inp.action_select_all()
            inp._rename_tab_id = tab_id  # type: ignore[attr-defined]
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != self._rename_input_id:
            return
        tab_id = getattr(event.input, "_rename_tab_id", None)
        new_name = event.value.strip()
        event.input.display = False
        if tab_id and new_name and tab_id in self._states:
            state = self._states[tab_id]
            if hasattr(state, "name"):
                state.name = new_name
            self._update_tab_label(tab_id, new_name)

    def on_input_blur(self, event: Input.Blurred) -> None:
        try:
            inp = self.query_one(f"#{self._rename_input_id}", Input)
            if inp.display:
                inp.display = False
        except Exception:
            pass

    def _update_tab_label(self, tab_id: str, name: str) -> None:
        try:
            tc = self.tabs_content
            tab_widget = tc.get_tab(tab_id)
            if tab_widget is not None:
                tab_widget.label = name
        except Exception:
            pass

    def update_tab_label(self, tab_id: str, label: str) -> None:
        """Публичный метод для обновления лейбла (напр. с * маркером dirty)."""
        self._update_tab_label(tab_id, label)

    # ── TabActivated (от Textual) ───────────────────────────────────────

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id != f"{self.id}-content":
            return
        pane = event.pane
        if pane is None or pane.id is None:
            return
        new_tab_id = pane.id

        # Deactivate old
        old_id = self._active_tab_id
        if old_id and old_id in self._states and old_id != new_tab_id:
            old_state = self._states.get(old_id)
            if old_state is not None:
                self.post_message(self.TabDeactivated(self, old_id, old_state))

        # Activate new
        self._active_tab_id = new_tab_id
        new_state = self._states.get(new_tab_id)
        if new_state is not None:
            self.post_message(self.TabActivated(self, new_tab_id, new_state))

    # ── Get state ───────────────────────────────────────────────────────

    def get_state(self, tab_id: str) -> TState | None:
        return self._states.get(tab_id)

    def get_tab_id_by_uid(self, tab_uid: str) -> str | None:
        """Найти tab_id по tab_uid (для DB-загрузки)."""
        for tid, st in self._states.items():
            if getattr(st, "tab_uid", None) == tab_uid:
                return tid
        return None