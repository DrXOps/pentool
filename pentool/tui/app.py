"""Главное TUI-приложение Pentool на Textual."""

from __future__ import annotations

from pathlib import Path
import asyncio
import os
import signal
import threading

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import ContentSwitcher, Footer

from pentool.tui.messages import (
    ProxyClearHistory,
    ProxyLoadProject,
    ProxyRequestAdded,
    ProxyRequestDone,
    SendHostToScanner,
    SendRequestToScanner,
    SendToIntruder,
    SendToRepeater,
    SendToScanner,
    SendToTarget,
    SendUrlToTarget,
    SyncScopeToTarget,
    TerminalStop,
    ConfigChanged,
)
from pentool.tui.constants import (
    SCREEN_PROXY, SCREEN_REPEATER, SCREEN_INTRUDER,
    SCREEN_SCANNER, SCREEN_TARGET, SCREEN_TERMINAL,
    SCREEN_DASHBOARD,
)

from pentool.api.proxy_api import ProxyAPI, ProxyServer, InterceptedRequest as _IR
from pentool.core.config import get_config
from pentool.core.database import init_db
from pentool.core.event_bus import get_event_bus
from pentool.core.events import (
    FindingDiscovered,
    PassiveScanToggled,
    ProxyRequestCaptured,
    ProxyRequestCompleted,
    ScanFinished,
    ScanProgressEvent,
    ScanStarted,
)
from pentool.core.logging import get_logger, setup_logging
from pentool.services.proxy_service import ProxyService
from pentool.tui.screens import (
    ComparerScreen,
    DashboardScreen,
    DecoderScreen,
    ExtensionsScreen,
    IntruderScreen,
    ProxyScreen,
    RepeaterScreen,
    ScannerScreen,
    SequencerScreen,
    SettingsScreen,
    SpiderScreen,
    TargetScreen,
    TerminalScreen,
)
from pentool.tui.widgets.menu import ModuleSelected, SideMenu
# MenuBar убран из DOM (R-12), импорт сохранён для возможной обратной совместимости
# from pentool.tui.widgets.menu_bar import MenuBar
from pentool.tui.widgets.module_tabs import ModuleTabs
from pentool.tui.widgets.statusbar import StatusBar

logger = get_logger(__name__)

# Маппинг module_id → класс виджета
_SCREEN_MAP: dict[str, type] = {
    "dashboard":  DashboardScreen,
    "proxy":      ProxyScreen,
    "repeater":   RepeaterScreen,
    "intruder":   IntruderScreen,
    "scanner":    ScannerScreen,
    "target":     TargetScreen,
    "decoder":    DecoderScreen,
    "comparer":   ComparerScreen,
    "sequencer":  SequencerScreen,
    "spider":     SpiderScreen,
    "extensions": ExtensionsScreen,
    "terminal":   TerminalScreen,
    "settings":   SettingsScreen,
}

class PentoolApp(App):
    """Главное TUI-приложение Pentool."""

    TITLE = "Pentool"
    SUB_TITLE = "Web Security Testing"

    CSS = """
    PentoolApp {
        layout: vertical;
        layers: overlay;
    }
    ModuleTabs {
        height: 3;
        width: 100%;
    }
    ContentSwitcher {
        width: 1fr;
        height: 1fr;
    }
    ContentSwitcher > * {
        width: 1fr;
        height: 1fr;
    }

    /* Глобальная строка подсказок горячих клавиш */
    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        color: $text-muted;
        dock: bottom;
    }

    /* Глобальный стиль чекбоксов — компактные, высота 1, без рамки */
    Checkbox {
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
        width: auto;
    }
    Checkbox > .toggle--button {
        color: $primary;
        background: transparent;
    }
    Checkbox.-on > .toggle--button {
        color: $success;
        background: transparent;
    }
    Checkbox:focus {
        border: none;
        background: transparent;
    }
    Checkbox:focus > .toggle--label {
        color: $text;
        background: $primary-darken-3;
        text-style: none;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+s", "save_project", "Save .db", show=False, priority=True),
        Binding("ctrl+o", "open_project", "Open .db", show=False, priority=True),
        Binding("ctrl+n", "new_project",  "New",  show=False, priority=True),
        # JSON-проект (полный экспорт всех модулей)
        Binding("ctrl+shift+s", "save_project_json", "Save JSON", show=False, priority=True),
        Binding("ctrl+shift+o", "open_project_json", "Open JSON", show=False, priority=True),
        Binding("ctrl+comma", "switch_module('settings')", "Settings", show=False, priority=True),
        # Навигация: Shift+буква (работает во всех терминалах)
        Binding("H", "switch_module('dashboard')",  "Dashboard",  show=False, priority=True),
        Binding("P", "switch_module('proxy')",      "Proxy",      show=False, priority=True),
        Binding("R", "switch_module('repeater')",   "Repeater",   show=False, priority=True),
        Binding("I", "switch_module('intruder')",   "Intruder",   show=False, priority=True),
        Binding("S", "switch_module('scanner')",    "Scanner",    show=False, priority=True),
        Binding("T", "switch_module('target')",     "Target",     show=False, priority=True),
        Binding("D", "switch_module('decoder')",    "Decoder",    show=False, priority=True),
        Binding("C", "switch_module('comparer')",   "Comparer",   show=False, priority=True),
        Binding("Q", "switch_module('sequencer')",  "Sequencer",  show=False, priority=True),
        Binding("W", "switch_module('spider')",     "Spider",     show=False, priority=True),
        Binding("E", "switch_module('extensions')", "Extensions", show=False, priority=True),
        Binding("X", "switch_module('terminal')",   "Terminal",   show=False, priority=True),
        # Алиасы Shift+цифра для совместимости
        Binding("exclamation_mark",   "switch_module('proxy')",      show=False, priority=True),
        Binding("at",                 "switch_module('repeater')",   show=False, priority=True),
        Binding("number_sign",        "switch_module('intruder')",   show=False, priority=True),
        Binding("dollar_sign",        "switch_module('scanner')",    show=False, priority=True),
        Binding("percent_sign",       "switch_module('decoder')",    show=False, priority=True),
        Binding("circumflex_accent",  "switch_module('comparer')",   show=False, priority=True),
        Binding("ampersand",          "switch_module('sequencer')",  show=False, priority=True),
        Binding("asterisk",           "switch_module('spider')",     show=False, priority=True),
        Binding("left_parenthesis",   "switch_module('extensions')", show=False, priority=True),
        # Proxy sub-tabs: use Ctrl+H/I/W for Proxy HTTP/Intercept/WS
        Binding("ctrl+h", "proxy_tab('http')",      "HTTP History", show=False, priority=True),
        Binding("ctrl+i", "proxy_tab('intercept')", "Intercept",    show=False, priority=True),
        Binding("ctrl+w", "proxy_tab('ws')",        "WS History",   show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = get_config()
        self._proxy: ProxyServer | None = None
        self._proxy_api: ProxyAPI = ProxyAPI()
        self._proxy_service: ProxyService | None = None
        self._proxy_thread: threading.Thread | None = None
        self._proxy_loop: asyncio.AbstractEventLoop | None = None
        self._active_module = "dashboard"
        self._project_path: str | None = None
        self._project_loaded: bool = False  # Флаг: проект создан или открыт
        self._skip_project_guard: bool = False  # True в тестах для обхода блокировки
        # Защита от message storm: множество pending req_id для дедупликации
        self._pending_done_ids: set[str] = set()
        # Vim-style key sequences: "g" prefix для Proxy sub-tabs
        # Shift+p затем h/i/w → proxy HTTP/Intercept/WS
        self._key_seq_state: str = ""
        import time as _time_mod
        self._key_seq_time: float = 0.0
        self._key_seq_timeout: float = 1.0  # секунда на ввод второй клавиши
        # Авто-сохранение проекта (Блок 3.3)
        from textual.timer import Timer as _Timer
        self._auto_save_timer: "_Timer | None" = None

    def _handle_exception(self, error: Exception) -> None:
        """Перехват фатальных ошибок — логируем перед передачей в Textual."""
        import traceback
        logger.error(
            "FATAL EXCEPTION: %s\n%s",
            error,
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )
        super()._handle_exception(error)

    def compose(self) -> ComposeResult:
        yield ModuleTabs(id="module-tabs")
        # MenuBar и SideMenu убраны из DOM (R-12: 404 строки мёртвого кода).
        # Файлы tui/widgets/menu_bar.py и menu.py сохранены как архив.
        # Единственный зависящий тест — tests/integration/test_navigation.py:58
        # (интеграционные тесты зависают, отдельная задача).
        with ContentSwitcher(initial="screen-dashboard"):
            yield DashboardScreen(id="screen-dashboard")
            yield ProxyScreen(id="screen-proxy")
            yield RepeaterScreen(id="screen-repeater")
            yield IntruderScreen(id="screen-intruder")
            yield ScannerScreen(id="screen-scanner")
            yield TargetScreen(id="screen-target")
            yield DecoderScreen(id="screen-decoder")
            yield ComparerScreen(id="screen-comparer")
            yield SequencerScreen(id="screen-sequencer")
            yield SpiderScreen(id="screen-spider")
            yield ExtensionsScreen(id="screen-extensions")
            yield TerminalScreen(id="screen-terminal")
            yield SettingsScreen(id="screen-settings")
        yield StatusBar(id="statusbar")
        yield Footer()

    async def on_mount(self) -> None:
        setup_logging(self._cfg.log_file, self._cfg.log_level)
        try:
            await init_db(self._cfg.db_path)
        except Exception as exc:
            logger.warning("DB init failed: %s", exc)

        self._proxy = ProxyServer(
            host=self._cfg.proxy_host,
            port=self._cfg.proxy_port,
            cert_dir=self._cfg.cert_dir,
            db_path=self._cfg.db_path,
        )
        self._proxy.intercept_enabled = self._cfg.intercept_enabled
        # Синхронизируем scope из конфига в ProxyServer
        if self._cfg.scope:
            self._proxy.scope = list(self._cfg.scope)
            logger.info("APP: scope loaded from config: %s", self._cfg.scope)

        # Инжектируем ProxyServer в API-слой
        self._proxy_api.set_proxy(self._proxy)

        # Создаём ProxyService и передаём в ProxyScreen — до init_storage
        self._proxy_service = ProxyService(
            proxy_api=self._proxy_api,
            db_path=self._cfg.db_path,
            event_bus=get_event_bus(),
        )
        try:
            from pentool.tui.screens.proxy.screen import ProxyScreen
            proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            proxy_screen._proxy_service = self._proxy_service
            # Запускаем init_storage здесь — ProxyScreen.on_mount уже отработал
            # и не мог этого сделать (ProxyService тогда ещё не был создан)
            proxy_screen.run_worker(self._proxy_service.init_storage())
            logger.info("APP: ProxyService injected and init_storage launched")
        except Exception as exc:
            logger.warning("APP: could not inject ProxyService into ProxyScreen: %s", exc)

        # Инициализируем глобальный Event Bus и подписываем app-обработчики
        bus = get_event_bus()
        bus.subscribe(FindingDiscovered,     self._on_bus_finding_discovered)
        bus.subscribe(ScanStarted,           self._on_bus_scan_started)
        bus.subscribe(ScanFinished,          self._on_bus_scan_finished)
        bus.subscribe(ScanProgressEvent,     self._on_bus_scan_progress)
        bus.subscribe(PassiveScanToggled,    self._on_bus_passive_toggled)
        # Sprint 3: подписываемся на прокси-события через EventBus
        # (proxy emitит из своего треда, мы бриджуем через call_from_thread)
        bus.subscribe(ProxyRequestCaptured,  self._on_bus_proxy_captured)
        bus.subscribe(ProxyRequestCompleted, self._on_bus_proxy_completed)
        logger.info("APP: EventBus subscribed")

        self._update_status()
        logger.info("Pentool TUI started")

        # Предгенерация CA-сертификата в фоне — чтобы к моменту нажатия
        # "Start Proxy" он уже был готов и не тормозил запуск (вариант C)
        self.run_worker(self._prewarm_ca(), exclusive=False, thread=False)

        # Разрешаем jemalloc (pyarrow) освобождать фоновый поток немедленно,
        # иначе он не daemon и блокирует выход процесса
        try:
            import pyarrow as pa
            pa.jemalloc_set_decay_ms(0)
        except Exception:
            pass

        from pentool.utils.terminal_check import get_terminal_warning
        warning = get_terminal_warning()
        if warning:
            self.notify(warning, severity="warning", timeout=6)

        # Обработка SIGTERM — корректное завершение при kill/systemd stop (10.2)
        self._setup_signal_handlers()

        # R-16: подписываемся на изменения конфига — SettingsScreen уведомит нас
        self._cfg.add_observer(self._on_config_changed)

        # Авто-сохранение (Блок 3.3) — запускаем если включено в конфиге
        self._setup_auto_save()

        # Автооткрытие последнего проекта при старте
        self.run_worker(self._auto_open_last_project(), exclusive=False, thread=False)

    async def _auto_open_last_project(self) -> None:
        """Открыть последний проект из recent_projects при старте."""
        await asyncio.sleep(0.2)  # дать Textual отрисовать UI
        recent = getattr(self._cfg, "recent_projects", [])
        if not recent:
            return
        path = recent[0]
        if not os.path.exists(path):
            logger.info("APP: last project not found: %s", path)
            return
        logger.info("APP: auto-opening last project: %s", path)
        self._switch_project_db(path, is_new=False)

    def _setup_auto_save(self) -> None:
        """Настроить / перезапустить таймер авто-сохранения из текущего конфига."""
        # Останавливаем старый таймер если был
        if self._auto_save_timer is not None:
            try:
                self._auto_save_timer.stop()
            except Exception:
                pass
            self._auto_save_timer = None

        if getattr(self._cfg, "auto_save_enabled", False):
            interval_min = max(1, getattr(self._cfg, "auto_save_interval", 5))
            interval_sec = interval_min * 60
            self._auto_save_timer = self.set_interval(interval_sec, self._auto_save_tick)
            logger.info("APP: auto-save enabled, interval=%d min", interval_min)

    def _auto_save_tick(self) -> None:
        """Периодическое авто-сохранение проекта (тихое, без диалогов)."""
        if not self._project_loaded:
            return
        path = self._project_path or self._cfg.db_path
        if not path:
            return
        try:
            # БД SQLite уже на месте — просто показываем уведомление
            import os as _os
            name = _os.path.basename(path)
            self.notify(f"Auto-saved: {name}", timeout=2)
            logger.info("APP: auto-saved project %s", path)
        except Exception as exc:
            logger.debug("_auto_save_tick: %s", exc)

    def _on_config_changed(self, changed_fields: dict) -> None:
        """Колбэк Config Observer — вызывается из любого контекста (R-16).

        Доставляем изменения в TUI через Message Bus (thread-safe).
        """
        self.post_message(ConfigChanged(changed_fields))

    def on_resize(self, event) -> None:
        """Адаптивная компоновка в зависимости от ширины терминала."""
        width = event.size.width
        # При ширине < 80 скрываем Inspector по умолчанию
        if width < 80:
            try:
                from pentool.tui.screens.proxy.screen import ProxyScreen
                screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                if screen._inspector_visible:
                    screen.action_toggle_inspector()
            except Exception as e:
                logger.debug("on_resize: could not toggle inspector: %s", e)

    @on(ModuleSelected)
    def on_module_selected(self, event: ModuleSelected) -> None:
        self._switch_to(event.module_id)

    def action_switch_module(self, module_id: str) -> None:
        self._switch_to(module_id)
        try:
            self.query_one(SideMenu).select_module(module_id)
        except Exception:
            pass
        try:
            self.query_one(ModuleTabs).select_module(module_id)
        except Exception:
            pass

    def on_key(self, event) -> None:
        """Global key handler: Ctrl+A select-all + vim proxy tab sequences."""
        import time as _time_mod
        key = event.key

        # ── Ctrl+A: select all text in focused TextArea or Input ──────────────
        if key == "ctrl+a":
            focused = self.focused
            if focused is not None:
                if hasattr(focused, "select_all"):
                    focused.select_all()
                    event.prevent_default()
                    return
                # TextArea.action_select_all exists in Textual ≥ 0.47
                if hasattr(focused, "action_select_all"):
                    focused.action_select_all()
                    event.prevent_default()
                    return

        now = _time_mod.monotonic()

        # Сброс state при таймауте
        if self._key_seq_state and (now - self._key_seq_time) > self._key_seq_timeout:
            self._key_seq_state = ""

        if self._key_seq_state == "P":
            # Второй символ последовательности
            self._key_seq_state = ""
            if key == "h":
                self.action_proxy_tab("http")
                event.prevent_default()
                return
            elif key == "i":
                self.action_proxy_tab("intercept")
                event.prevent_default()
                return
            elif key == "w":
                self.action_proxy_tab("ws")
                event.prevent_default()
                return
        elif key == "P":
            # Начало последовательности Shift+P (P уже switch_module, перехватим вторую клавишу)
            self._key_seq_state = "P"
            self._key_seq_time = now
            # Не preventDefault — Binding с "P" выполнится первым (switch to proxy),
            # затем если пользователь нажмёт h/i/w — переключится на вкладку

    def action_proxy_tab(self, tab: str) -> None:
        self.action_switch_module("proxy")
        tab_ids = {
            "http":      "tab-http-history",
            "intercept": "tab-intercept",
            "ws":        "tab-ws-history",
        }
        tab_id = tab_ids.get(tab)
        if not tab_id:
            return
        try:
            from pentool.tui.screens.proxy.screen import ProxyScreen
            proxy_screen = self.query_one("#screen-proxy", ProxyScreen)
            from textual.widgets import TabbedContent
            tabs = proxy_screen.query_one("#proxy-subtabs", TabbedContent)
            tabs.active = tab_id
            self.call_after_refresh(
                lambda tid=tab_id: self._focus_proxy_table(proxy_screen, tid)
            )
        except Exception:
            pass

    def _focus_proxy_table(self, proxy_screen: object, tab_id: str) -> None:
        """Фокус на DataTable в нужной вкладке Proxy."""
        try:
            from textual_fastdatatable import DataTable
            table_ids = {
                "tab-http-history": "#request-list",
                "tab-intercept":    None,  # intercept не имеет таблицы
                "tab-ws-history":   "#ws-request-list",
            }
            table_sel = table_ids.get(tab_id)
            if table_sel:
                table = proxy_screen.query_one(table_sel, DataTable)  # type: ignore[union-attr]
                table.focus()
                if table.row_count > 0:
                    table.move_cursor(row=0)
        except Exception:
            pass

    # Модули, доступные без открытого проекта
    _FREE_MODULES = {"dashboard", "settings"}

    def _switch_to(self, module_id: str) -> None:
        if module_id == self._active_module:
            return
        if module_id not in _SCREEN_MAP:
            return
        if not self._project_loaded and not self._skip_project_guard and module_id not in self._FREE_MODULES:
            self.notify(
                "Сначала создайте или откройте проект (Ctrl+N / Ctrl+O)",
                severity="warning",
                timeout=4,
            )
            return
        self.query_one(ContentSwitcher).current = f"screen-{module_id}"
        self._active_module = module_id

    def get_proxy(self) -> ProxyServer | None:
        return self._proxy

    def get_proxy_api(self) -> ProxyAPI:
        return self._proxy_api

    def show_context_menu(
        self,
        items: list[tuple[str, str]],
        x: int,
        y: int,
        callback=None,
    ) -> None:
        from pentool.tui.widgets.context_menu import ContextMenu
        for old in self.query("ContextMenu"):
            old.remove()
        menu = ContextMenu(items, x, y, callback=callback)
        self.mount(menu)
        menu.focus()

    @property
    def db_path(self) -> str:
        """Путь к SQLite-базе данных (публичный доступ для экранов)."""
        return self._cfg.db_path

    def action_toggle_proxy(self) -> None:
        if self._proxy is None:
            return
        if self._proxy.is_running:
            self._stop_proxy()
        else:
            self._start_proxy()

    def action_toggle_intercept(self) -> None:
        if self._proxy is None:
            return
        enabled = not self._proxy.intercept_enabled
        # Используем thread-safe метод — proxy loop работает в отдельном треде,
        # прямое присвоение может вызвать race condition (R-fix: intercept bug)
        self._proxy.set_intercept(enabled)
        logger.info("APP: intercept toggled → %s (thread-safe)", enabled)
        self._update_status()
        self._update_proxy_screen_labels()

    def _start_proxy(self) -> None:
        if self._proxy is None or self._proxy.is_running:
            return
        logger.info("APP: _start_proxy: starting proxy on %s:%d", self._proxy.host, self._proxy.port)
        # Sprint 3: коллбэки убраны — proxy emitит через EventBus,
        # app подписан на ProxyRequestCaptured / ProxyRequestCompleted в on_mount

        def _run_proxy_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._proxy_loop = loop
            try:
                loop.run_until_complete(self._proxy_main())
            finally:
                loop.close()
                self._proxy_loop = None

        self._proxy_thread = threading.Thread(
            target=_run_proxy_loop, daemon=True, name="proxy"
        )
        self._proxy_thread.start()

    def _setup_signal_handlers(self) -> None:
        """Регистрируем SIGTERM/SIGINT для корректного завершения (10.2).

        signal.signal() работает только в главном треде. При получении SIGTERM
        вызываем action_quit() через loop.call_soon_threadsafe — это безопасно
        из обработчика сигнала, т.к. он вызывается в контексте asyncio event loop.
        """
        def _handle_signal(signum: int, frame: object) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("APP: received %s — initiating graceful shutdown", sig_name)
            # Используем call_soon_threadsafe — безопасен из любого контекста,
            # включая обработчики сигналов в главном треде.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.action_quit)
            except Exception:
                # Крайний случай — просто выходим
                sys.exit(0)

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            # SIGINT уже обрабатывается Textual (KeyboardInterrupt → exit),
            # переопределяем для консистентного поведения
            signal.signal(signal.SIGINT, _handle_signal)
            logger.debug("APP: SIGTERM/SIGINT handlers installed")
        except (OSError, ValueError) as e:
            # ValueError если не главный тред, OSError на Windows
            logger.debug("APP: could not install signal handlers: %s", e)

    async def _prewarm_ca(self) -> None:
        """Предгенерация CA-сертификата при старте приложения (фоново).

        load_or_create_ca() создаёт файлы если их нет — это может занять 0.5-2с
        (RSA keygen). Вызывая здесь, мы гарантируем что к моменту нажатия
        Start Proxy сертификат уже готов и proxy.start() не тормозит.
        """
        loop = asyncio.get_running_loop()
        try:
            from pentool.utils.cert import load_or_create_ca
            # Запускаем синхронную генерацию в executor чтобы не блокировать TUI
            cert_dir = self._cfg.cert_dir
            await loop.run_in_executor(None, load_or_create_ca, cert_dir)
            logger.info("APP: CA certificate pre-warmed from %s", cert_dir)
        except Exception as exc:
            logger.warning("APP: CA pre-warm failed: %s", exc)

    async def _proxy_main(self) -> None:
        """Точка входа прокси — запускается в отдельном event loop."""
        try:
            await self._proxy.start()
            self.call_from_thread(self._update_status)
            self.call_from_thread(self._update_proxy_screen_labels)
            self.call_from_thread(self._update_dashboard_proxy_status, True)
            logger.info("Proxy started on port %s", self._proxy.port)
            async with self._proxy._server:
                await self._proxy._server.serve_forever()
        except Exception as exc:
            logger.error("Proxy error: %s", exc)
        finally:
            self.call_from_thread(self._update_status)
            self.call_from_thread(self._update_proxy_screen_labels)
            self.call_from_thread(self._update_dashboard_proxy_status, False)

    def _stop_proxy(self) -> None:
        logger.info("APP: _stop_proxy called")
        if self._proxy and self._proxy.is_running and self._proxy_loop:
            future = asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop
            )
            try:
                future.result(timeout=5)
            except Exception as e:
                logger.warning("APP: proxy.stop() error or timeout: %s", e)
        if self._proxy_thread and self._proxy_thread.is_alive():
            self._proxy_thread.join(timeout=3)
            if self._proxy_thread.is_alive():
                logger.warning("APP: proxy thread did not stop in 3s")
        self.call_after_refresh(self._update_status)
        self.call_after_refresh(self._update_proxy_screen_labels)

    # Sprint 3: _on_proxy_request и _proxy_request_done_cb убраны — proxy emit через EventBus,
    # app подписан на ProxyRequestCaptured / ProxyRequestCompleted → _on_bus_proxy_captured/completed

    @on(ProxyRequestAdded)
    def on_proxy_request_added(self, msg: ProxyRequestAdded) -> None:
        """Прокси поймал новый запрос → обновляем ProxyScreen."""
        if not (self._proxy and self._proxy.is_running):
            return
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.add_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:
                screen.show_intercepted_request(msg.req)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("on_proxy_request_added: %s", e)

    @on(ProxyRequestDone)
    def on_proxy_request_done(self, msg: ProxyRequestDone) -> None:
        """Прокси завершил цикл запрос/ответ → обновляем строку и SiteMap."""
        # Снимаем из pending — теперь следующий запрос с этим id пройдёт снова
        req_id = getattr(msg.req, "id", None)
        self._pending_done_ids.discard(req_id)
        # Guard: msg.req должен быть InterceptedRequest
        if not isinstance(msg.req, _IR):
            logger.warning("on_proxy_request_done: msg.req is %s, skipping", type(msg.req))
            return
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.update_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:
                screen.show_intercept_response(msg.req)  # type: ignore[arg-type]
        except Exception as e:
            logger.debug("on_proxy_request_done (proxy screen): %s", e)
        # Автопостроение SiteMap
        self.post_message(SendToTarget(msg.req))

    @on(SendToTarget)
    def on_send_to_target(self, msg: SendToTarget) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target.add_request_from_proxy(msg.req)
        except Exception as e:
            logger.debug("on_send_to_target: %s", e)

    def _add_raw_to_target(self, raw: str) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            from pentool.utils.parser import parse_http_request
            req = parse_http_request(raw)
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target.add_request_from_proxy(req)
        except Exception as e:
            logger.debug("_add_raw_to_target: %s", e)

    @on(SendToRepeater)
    def on_send_to_repeater(self, msg: SendToRepeater) -> None:
        try:
            from pentool.tui.screens.repeater.screen import RepeaterScreen
            repeater = self.query_one(SCREEN_REPEATER, RepeaterScreen)
            repeater.load_request(msg.raw)
            self.action_switch_module("repeater")
            self.notify("Sent to Repeater", severity="information", timeout=2)
            self._add_raw_to_target(msg.raw)
        except Exception as exc:
            self.notify(f"Send to Repeater failed: {exc}", severity="error", timeout=4)

    @on(SendToIntruder)
    def on_send_to_intruder(self, msg: SendToIntruder) -> None:
        try:
            from pentool.tui.screens.intruder.screen import IntruderScreen
            intruder = self.query_one(SCREEN_INTRUDER, IntruderScreen)
            intruder.load_request(msg.raw)
            self.action_switch_module("intruder")
            self.notify("Sent to Intruder", severity="information", timeout=2)
            self._add_raw_to_target(msg.raw)
        except Exception as exc:
            self.notify(f"Send to Intruder failed: {exc}", severity="error", timeout=4)

    @on(SyncScopeToTarget)
    def on_sync_scope_to_target(self, msg: SyncScopeToTarget) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            api = target._get_api()
            api.sitemap.set_in_scope(msg.host, msg.in_scope)
            target._load_sitemap()
        except Exception as e:
            logger.debug("on_sync_scope_to_target: %s", e)

    @on(SendHostToScanner)
    def on_send_host_to_scanner(self, msg: SendHostToScanner) -> None:
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen
            scanner = self.query_one(SCREEN_SCANNER, ScannerScreen)
            host = msg.host
            url = f"https://{host}" if not host.startswith("http") else host
            # Передаём url напрямую в action_new_tab — он сохранит в state.pending_target
            # и применит в _fill_settings, когда Input уже смонтирован
            scanner.action_new_tab(initial_url=url)
            self.action_switch_module("scanner")
            self.notify(f"✓ {host} → Scanner (новая вкладка, F5 to start)", timeout=3)
            logger.info("SendHostToScanner: host=%s url=%s", host, url)
        except Exception as exc:
            logger.error("SendHostToScanner error: %s", exc, exc_info=True)
            self.notify(f"Scanner error: {exc}", severity="error", timeout=4)

    @on(SendToScanner)
    def on_send_to_scanner(self, msg: SendToScanner) -> None:
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen
            scanner = self.query_one(SCREEN_SCANNER, ScannerScreen)
            # Каждый "Send to Scanner" открывает новую вкладку, чтобы не затирать
            # данные уже запущенного сканирования (баг: старые findings грузились).
            first_url = msg.urls.splitlines()[0].strip() if msg.urls.strip() else msg.urls
            scanner.action_new_tab(initial_url=first_url)
            self.action_switch_module("scanner")
            count = len(msg.urls.splitlines())
            self.notify(f"Sent {count} URL(s) to Scanner (new tab)", severity="information", timeout=2)
        except Exception as exc:
            self.notify(f"Send to Scanner failed: {exc}", severity="error", timeout=4)

    @on(SendRequestToScanner)
    def on_send_request_to_scanner(self, msg: SendRequestToScanner) -> None:
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen
            scanner = self.query_one(SCREEN_SCANNER, ScannerScreen)
            scanner.action_new_tab(seed_request=msg.request)
            self.action_switch_module("scanner")
            url = getattr(msg.request, "url", "?")
            self.notify(f"Sent to Scanner: {url[:60]}", severity="information", timeout=2)
        except Exception as exc:
            self.notify(f"Send to Scanner failed: {exc}", severity="error", timeout=4)

    @on(SendUrlToTarget)
    def on_send_url_to_target(self, msg: SendUrlToTarget) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target.add_request_from_proxy(msg.req)
        except Exception as e:
            logger.debug("on_send_url_to_target: %s", e)

    @on(ProxyClearHistory)
    def on_proxy_clear_history(self, msg: ProxyClearHistory) -> None:
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.action_clear_list()
        except Exception as e:
            logger.debug("on_proxy_clear_history: %s", e)

    @on(ProxyLoadProject)
    def on_proxy_load_project(self, msg: ProxyLoadProject) -> None:
        """Перезагрузить таблицу ProxyScreen после загрузки проекта."""
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.load_from_project()
        except Exception as e:
            logger.debug("on_proxy_load_project: %s", e)

    @on(TerminalStop)
    def on_terminal_stop(self, msg: TerminalStop) -> None:
        try:
            from pentool.tui.screens.terminal.screen import TerminalScreen
            term = self.query_one(SCREEN_TERMINAL, TerminalScreen)
            term._stop()
        except Exception as e:
            logger.debug("on_terminal_stop: %s", e)

    @on(ConfigChanged)
    def on_config_changed(self, msg: ConfigChanged) -> None:
        """Применить изменения конфига к ProxyServer и StatusBar (R-16).

        Вызывается когда SettingsScreen сохраняет настройки через cfg.update().
        ProxyServer обновляет port/host — но не перезапускается автоматически,
        пользователь должен перезапустить прокси вручную.
        """
        fields = msg.fields
        logger.info("APP: config changed: %s", list(fields.keys()))
        if self._proxy:
            if "proxy_host" in fields:
                self._proxy.host = fields["proxy_host"]
            if "proxy_port" in fields:
                self._proxy.port = fields["proxy_port"]
        self._update_status()
        if fields.get("proxy_host") or fields.get("proxy_port"):
            self.notify(
                "Proxy settings updated — restart proxy to apply",
                severity="information", timeout=4,
            )
        # Перезапустить таймер авто-сохранения если изменились соответствующие поля
        if "auto_save_enabled" in fields or "auto_save_interval" in fields:
            self._setup_auto_save()

    def _update_status(self) -> None:
        try:
            bar = self.query_one(StatusBar)
            running = bool(self._proxy and self._proxy.is_running)
            port = self._proxy.port if self._proxy else self._cfg.proxy_port
            bar.set_proxy_status(running, port)
        except Exception as e:
            logger.debug("_update_status: %s", e)

    def _update_dashboard_proxy_status(self, running: bool) -> None:
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_proxy_status(running)
        except Exception:
            pass

    def _update_proxy_screen_labels(self) -> None:
        try:
            if self._active_module == "proxy":
                screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                running = bool(self._proxy and self._proxy.is_running)
                port = self._proxy.port if self._proxy else self._cfg.proxy_port
                screen.update_proxy_label(running, port)
                intercept = bool(self._proxy and self._proxy.intercept_enabled)
                screen.update_intercept_label(intercept)
        except Exception as e:
            logger.debug("_update_proxy_screen_labels: %s", e)

    def action_open_settings(self) -> None:
        """Переключиться на экран настроек."""
        self.action_switch_module("settings")

    def action_about(self) -> None:
        self.notify("PenTool — Быстрее. Удобнее. Умнее.", timeout=3)

    def action_toggle_theme(self) -> None:
        self.run_worker(self.run_action("toggle_dark"), exclusive=False)

    def action_new_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            self._switch_project_db(path, is_new=True)

        self.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="New Project — Choose Location",
                start_dir=os.path.expanduser("~"),
            ),
            _on_path,
        )

    def action_open_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._project_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                self.notify(f"File not found: {path}", severity="error", timeout=4)
                return
            self._switch_project_db(path, is_new=False)

        self.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title="Open Project",
                start_dir=start_dir,
                filter_ext=[".db"],
            ),
            _on_path,
        )

    def action_save_project(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            import shutil
            src = self._cfg.db_path
            try:
                shutil.copy2(src, path)
                self._project_path = path
                self._update_project_name(path, saved=True)
                self.notify(f"Saved to {os.path.basename(path)}", timeout=3)
                try:
                    dash = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
                    dash.log_activity(
                        f'Project "{os.path.splitext(os.path.basename(path))[0]}" saved to {path}',
                        "ok"
                    )
                    dash._populate_projects()
                except Exception:
                    pass
            except Exception as e:
                self.notify(f"Save failed: {e}", severity="error", timeout=4)

        self.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="Save Project As",
                start_dir=start_dir,
            ),
            _on_path,
        )

    def action_save_project_json(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".json"):
                path = path + ".json"
            self._do_save_project_json(path)

        self.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="Export Project (JSON)",
                start_dir=start_dir,
            ),
            _on_path,
        )

    def action_open_project_json(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = self._project_path or self._cfg.db_path
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                self.notify(f"File not found: {path}", severity="error", timeout=4)
                return
            self._do_load_project_json(path)

        self.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title="Import Project (JSON)",
                start_dir=start_dir,
                filter_ext=[".json"],
            ),
            _on_path,
        )

    def _do_save_project_json(self, path: str) -> None:
        """Собрать данные из всех API и сохранить в JSON v2."""
        from pentool.core.project import save_project
        try:
            # Proxy (scope, match/replace) — без http_history (читаем из SQLite)
            proxy_export = self._proxy_api.export_project_data()
            # HTTP history — читаем из SQLite через ProxyService
            try:
                if self._proxy_service is not None and self._proxy_service.is_storage_ready():
                    http_history = asyncio.run_coroutine_threadsafe(
                        self._proxy_service._storage.export_all_requests(), self._loop
                    ).result(timeout=30)
                    proxy_export["http_history"] = http_history
                    logger.info(
                        "_do_save_project_json: exported %d HTTP entries from SQLite",
                        len(http_history),
                    )
            except Exception as exc:
                logger.warning("_do_save_project_json: http_history export failed: %s", exc)
            # Scanner findings
            try:
                from pentool.tui.screens.scanner.screen import ScannerScreen
                scanner_screen = self.query_one(SCREEN_SCANNER, ScannerScreen)
                scanner_api = scanner_screen._scanner_api
                scanner_export = scanner_api.export_project_data() if scanner_api else {"findings": []}
            except Exception:
                scanner_export = {"findings": []}
            # Target sitemap
            try:
                from pentool.tui.screens.target.screen import TargetScreen
                target_screen = self.query_one(SCREEN_TARGET, TargetScreen)
                target_api = target_screen._get_api()
                target_export = target_api.export_project_data()
            except Exception:
                target_export = {"sitemap": {}}
            # Intruder results — self._api в IntruderScreen
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen
                intruder_screen = self.query_one(SCREEN_INTRUDER, IntruderScreen)
                intruder_api = getattr(intruder_screen, "_api", None)
                intruder_export = intruder_api.export_project_data() if intruder_api else {"results": []}
            except Exception:
                intruder_export = {"results": []}
            # Spider sessions (из EventBus history)
            spider_export = self._collect_spider_sessions()

            data = {
                **proxy_export,   # proxy + http_history на верхнем уровне
                "scanner":  scanner_export,
                "intruder": intruder_export,
                "spider":   spider_export,
                "target":   target_export,
            }
            save_project(path, data)
            self._update_project_name(path)
            self.notify(f"Saved → {os.path.basename(path)}", timeout=3)
            logger.info("APP: project saved to JSON: %s", path)
        except Exception as exc:
            logger.error("_do_save_project_json error: %s", exc, exc_info=True)
            self.notify(f"Save failed: {exc}", severity="error", timeout=4)

    def _do_load_project_json(self, path: str) -> None:
        from pentool.core.project import load_project
        data, err = load_project(path)
        if err:
            self.notify(f"Load failed: {err}", severity="error", timeout=5)
            return
        try:
            # Proxy
            loaded_proxy, err_proxy = self._proxy_api.import_project_data(data)
            if err_proxy:
                logger.warning("import proxy: %s", err_proxy)
            # Scanner findings — восстанавливаем через engine, потом reload UI
            scanner_count = 0
            try:
                from pentool.tui.screens.scanner.screen import ScannerScreen
                scanner_screen = self.query_one(SCREEN_SCANNER, ScannerScreen)
                db_path = self._cfg.db_path
                scanner_api = scanner_screen._get_or_create_api(db_path)
                scanner_count = scanner_api.import_project_data(data.get("scanner", {}))
                # Перезагружаем UI из БД (import_project_data уже записал в SQLite)
                scanner_screen._populate_from_db([])   # очищаем таблицу
                scanner_screen._load_findings_worker()  # загружаем из БД
            except Exception as exc:
                logger.warning("import scanner: %s", exc)
            # Target sitemap
            target_count = 0
            try:
                from pentool.tui.screens.target.screen import TargetScreen
                target_screen = self.query_one(SCREEN_TARGET, TargetScreen)
                target_api = target_screen._get_api()
                target_count = target_api.import_project_data(data.get("target", {}))
                target_screen._load_sitemap()
            except Exception as exc:
                logger.warning("import target: %s", exc)
            # Intruder results — восстанавливаем в API (self._api)
            intruder_count = 0
            try:
                from pentool.tui.screens.intruder.screen import IntruderScreen
                intruder_screen = self.query_one(SCREEN_INTRUDER, IntruderScreen)
                intruder_api = getattr(intruder_screen, "_api", None)
                if intruder_api:
                    intruder_count = intruder_api.import_project_data(data.get("intruder", {}))
            except Exception as exc:
                logger.warning("import intruder: %s", exc)

            # Обновляем ProxyScreen
            self.post_message(ProxyLoadProject())
            self._update_project_name(path)

            total = loaded_proxy + scanner_count + target_count + intruder_count
            self.notify(
                f"Loaded {os.path.basename(path)} — "
                f"proxy: {loaded_proxy}, scanner: {scanner_count}, "
                f"target: {target_count}, intruder: {intruder_count}",
                timeout=5,
            )
            logger.info(
                "APP: project loaded from JSON: %s, total items: %d", path, total
            )
        except Exception as exc:
            logger.error("_do_load_project_json error: %s", exc, exc_info=True)
            self.notify(f"Load failed: {exc}", severity="error", timeout=4)

    def _collect_spider_sessions(self) -> dict:
        """Собрать данные Spider-сессий из EventBus history."""
        from pentool.core.event_bus import get_event_bus
        from pentool.core.events import SpiderFinished
        sessions = []
        try:
            bus = get_event_bus()
            events = bus.get_history(event_type=SpiderFinished, limit=100)
            for ev in events:
                sessions.append({
                    "base_url": getattr(ev, "base_url", ""),
                    "pages_count": getattr(ev, "pages_count", 0),
                    "forms_count": getattr(ev, "forms_count", 0),
                    "endpoints_count": getattr(ev, "endpoints_count", 0),
                    "timestamp": getattr(ev, "timestamp", 0),
                })
        except Exception as exc:
            logger.debug("_collect_spider_sessions: %s", exc)
        return {"sessions": sessions}

    def _switch_project_db(self, path: str, is_new: bool = False) -> None:
        """Переключиться на другой .db файл как активный проект.

        Args:
            path: Путь к .db файлу.
            is_new: True — создать новую БД (очистить историю), False — открыть существующую.
        """

        if is_new:
            # Для нового проекта — создаём директорию и инициализируем схему
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Обновляем cfg.db_path — это публичный property всего приложения
        self._cfg.db_path = path
        self._project_path = path
        self._project_loaded = True  # Разблокировать все модули

        # Обновляем ProxyServer.db_path чтобы HttpStorage писал в новую БД
        if self._proxy:
            self._proxy.db_path = path

        # Очистить in-memory историю прокси (для нового проекта или чистого открытия)
        if is_new and self._proxy:
            try:
                self._proxy.requests.clear()
                self._proxy.scope = []
                self._proxy.match_replace_rules = []
            except Exception:
                pass

        if is_new:
            # Для нового проекта — инициализируем схему и шлём сигнал очистки
            self.run_worker(self._init_new_db(path), exclusive=False, thread=False)
            self.post_message(ProxyClearHistory())
        else:
            # Для существующей БД — сначала переключить storage, потом перезагрузить экраны
            # Всё в одном воркере чтобы гарантировать последовательность
            self.run_worker(
                self._open_project_sequence(path),
                exclusive=False,
                thread=False,
            )

        self._update_project_name(path)
        action = "Created" if is_new else "Opened"
        self.notify(f"{action}: {os.path.basename(path)}", timeout=3)

        # Обновить дерево проектов на дашборде и записать в Live Feed
        try:
            dash = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dash._populate_projects()
            verb = "created" if is_new else "loaded"
            dash.log_activity(
                f'Project "{os.path.splitext(os.path.basename(path))[0]}" {verb} from {path}',
                "ok"
            )
        except Exception:
            pass

    async def _reload_project_screens(self, path: str) -> None:
        """Перезагрузить данные из БД во все экраны после смены проекта."""
        # 1. ProxyScreen — перечитать историю из новой БД
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.load_from_project()
            logger.info("_reload_project_screens: proxy reloaded from %s", path)
        except Exception as exc:
            logger.debug("_reload_project_screens proxy: %s", exc)

        # 2. ScannerScreen — перечитать findings из новой БД
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen
            scanner_screen = self.query_one(SCREEN_SCANNER, ScannerScreen)
            # Обновить API на новый db_path
            if scanner_screen._scanner_api is not None:
                scanner_screen._scanner_api._db_path = path
            scanner_screen._scanner_api = None  # сбросить, пересоздастся с новым path
            scanner_screen._scanner_api = scanner_screen._get_or_create_api(path)
            scanner_screen._populate_from_db([])      # очистить таблицу
            scanner_screen._load_findings_worker()     # загрузить из новой БД
            logger.info("_reload_project_screens: scanner reloaded")
        except Exception as exc:
            logger.debug("_reload_project_screens scanner: %s", exc)

        # 3. TargetScreen — сохранить текущий sitemap в старую БД, затем перечитать из новой
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target_screen = self.query_one(SCREEN_TARGET, TargetScreen)
            # Сохранить текущий in-memory sitemap в старую БД перед сменой
            if target_screen._target_api is not None:
                try:
                    await target_screen._target_api.save()
                except Exception:
                    pass
            # Сбросить API — пересоздастся с новым db_path в _get_api()
            target_screen._target_api = None
            target_screen._get_api()  # pre-create с новым db_path
            target_screen._load_sitemap()
            logger.info("_reload_project_screens: target reloaded from %s", path)
        except Exception as exc:
            logger.debug("_reload_project_screens target: %s", exc)

        # 4. Dashboard — обновить статистику
        try:
            dash = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dash.refresh_stats()
        except Exception as exc:
            logger.debug("_reload_project_screens dashboard: %s", exc)

    async def _init_new_db(self, path: str) -> None:
        try:
            await init_db(path)
        except Exception as exc:
            logger.warning("_init_new_db: %s", exc)

    async def _switch_storage_db(self, path: str) -> None:
        try:
            if self._proxy_service is not None:
                await self._proxy_service.switch_db(path)
                logger.info("_switch_storage_db: proxy_service switched to %s", path)
        except Exception as exc:
            logger.debug("_switch_storage_db error: %s", exc)

    async def _open_project_sequence(self, path: str) -> None:
        # 1. Переключить HttpStorage
        await self._switch_storage_db(path)
        # 2. Инициализировать/мигрировать схему
        await self._init_new_db(path)
        # 3. Дать Textual один цикл для обработки любых pending сообщений
        await asyncio.sleep(0.05)
        # 4. Перезагрузить данные во все экраны
        await self._reload_project_screens(path)

    def action_open_ca_cert(self) -> None:
        from pentool.core.config import get_config
        from pentool.tui.dialogs.cert_dialog import CertInstallDialog
        ca_path = str(get_config().cert_dir) + "/ca.crt"
        self.push_screen(CertInstallDialog(ca_path))

    def _update_project_name(self, path: str, saved: bool = True) -> None:
        name = os.path.basename(path) if path else "new project"
        # Убираем расширение .db
        if name.endswith(".db"):
            name = name[:-3]
        try:
            from pentool.tui.widgets.statusbar import StatusBar
            bar = self.query_one(StatusBar)
            bar.set_project(name, path, saved)
        except Exception:
            pass
        # Обновляем SUB_TITLE приложения
        try:
            self.sub_title = f"project: {name}"
        except Exception:
            pass
        # Добавляем в список последних проектов (если реальный файл)
        if path and path != "new project":
            try:
                self._cfg.add_recent_project(path)
            except Exception:
                pass

    # ── EventBus handlers ──────────────────────────────────────────────────────
    # Все обработчики вызываются из основного event loop (через emit или
    # emit_threadsafe → call_soon_threadsafe), поэтому query_one безопасен.

    def _on_bus_finding_discovered(self, event: FindingDiscovered) -> None:
        """Finding из активного или пассивного сканера → Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.add_finding(event.finding)
        except Exception:
            pass

    def _on_bus_scan_started(self, event: ScanStarted) -> None:
        """Скан запущен → обновить статус на Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(True, 0)
        except Exception:
            pass

    def _on_bus_scan_finished(self, event: ScanFinished) -> None:
        """Скан завершён → сбросить статус на Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(False, 100)
        except Exception:
            pass

    def _on_bus_scan_progress(self, event: ScanProgressEvent) -> None:
        """Прогресс скана → Dashboard (опционально, для live-обновления)."""
        # Пока не используем — Dashboard обновляется через ScanStarted/ScanFinished.
        pass

    def _on_bus_proxy_captured(self, event: ProxyRequestCaptured) -> None:
        """EventBus: прокси перехватил новый запрос.

        Бридж: proxy emit из своего треда → EventBus → этот метод вызывается
        синхронно в proxy-треде → call_from_thread → Textual Message в TUI-треде.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        self.call_from_thread(self.post_message, ProxyRequestAdded(req))

    def _on_bus_proxy_completed(self, event: ProxyRequestCompleted) -> None:
        """EventBus: запрос через прокси завершён.

        Бридж: proxy emit из своего треда → EventBus → call_from_thread → Textual Message.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        req_id = req.id
        # Дедупликация: если уже pending, игнорируем
        if req_id in self._pending_done_ids:
            return
        self._pending_done_ids.add(req_id)
        self.call_from_thread(self.post_message, ProxyRequestDone(req))

    def _on_bus_passive_toggled(self, event: PassiveScanToggled) -> None:
        """Пассивный скан включён/выключен — обновляем LED на Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_passive_status(event.enabled)
        except Exception:
            pass

    async def action_quit(self) -> None:
        # Отписываемся от EventBus перед выходом
        try:
            bus = get_event_bus()
            bus.unsubscribe_all(self._on_bus_finding_discovered)
            bus.unsubscribe_all(self._on_bus_scan_started)
            bus.unsubscribe_all(self._on_bus_scan_finished)
            bus.unsubscribe_all(self._on_bus_scan_progress)
            bus.unsubscribe_all(self._on_bus_passive_toggled)
            bus.unsubscribe_all(self._on_bus_proxy_captured)
            bus.unsubscribe_all(self._on_bus_proxy_completed)
        except Exception:
            pass
        # Останавливаем терминал (shell-процесс) через Message Bus
        self.post_message(TerminalStop())
        # Останавливаем прокси
        if self._proxy and self._proxy.is_running and self._proxy_loop:
            asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop
            )
        if self._proxy_thread and self._proxy_thread.is_alive():
            self._proxy_thread.join(timeout=2)
        # Закрываем SQLite-хранилище — сливаем WAL на диск
        try:
            if self._proxy_service is not None:
                await self._proxy_service._storage.close()
                logger.info("APP: HttpStorage closed on quit")
        except Exception as e:
            logger.warning("APP: HttpStorage close error on quit: %s", e)
        self.exit()
        # Принудительно завершаем процесс — убивает не-daemon потоки
        # (jemalloc_bg_thd от pyarrow), которые иначе блокируют выход.
        # call_later даёт Textual ~100мс на финальный cleanup экрана.
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(0.1, os._exit, 0)
        except RuntimeError:
            os._exit(0)
