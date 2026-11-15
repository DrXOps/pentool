"""Main Pentool TUI application built on Textual."""

from __future__ import annotations

import asyncio
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult, InvalidThemeError
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Checkbox, ContentSwitcher

from pentool import __version__
from pentool.api.proxy_api import InterceptedRequest as _IR
from pentool.api.proxy_api import ProxyAPI, ProxyServer
from pentool.core.config import get_config
from pentool.core.db_schema import init_db
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
from pentool.proxy.client import ProxyClient
from pentool.services.proxy_service import ProxyService
from pentool.tui.constants import (
    SCREEN_DASHBOARD,
    SCREEN_INTRUDER,
    SCREEN_PROXY,
    SCREEN_REPEATER,
    SCREEN_SCANNER,
    SCREEN_TARGET,
)
from pentool.tui.hotkeys.defaults import build_global_bindings
from pentool.tui.messages import (
    ConfigChanged,
    ModuleSelected,
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
    SyncScopeToProxy,
    SyncScopeToTarget,
)
from pentool.tui.mixins.events_handlers import ProxyEventHandlersMixin
from pentool.tui.mixins.notifications import NotificationsMixin
from pentool.tui.mixins.project_autosave import ProjectAutoSaveMixin
from pentool.tui.mixins.proxy_runtime import ProxyRuntimeMixin
from pentool.tui.screen_registry import SCREEN_MAP
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
    TargetScreen,
)
from pentool.tui.widgets.keyhintbar import GlobalHintBar, ModuleHintBar
from pentool.tui.widgets.module_tabs import ModuleTabs
from pentool.tui.widgets.statusbar import StatusBar

logger = get_logger(__name__)

# Nicer checkbox glyph applied project-wide — Checkbox is a subclass of
# ToggleButton, whose BUTTON_LEFT/INNER/RIGHT class attributes control the
# rendered glyph. Overriding them here (once, at import time) changes every
# Checkbox instance across all screens without touching each screen's CSS —
# previously every screen used Textual's default "▐X▌" look, which several
# screens then had to fight with ad-hoc height/margin overrides.
Checkbox.BUTTON_LEFT = "["
Checkbox.BUTTON_INNER = "✓"
Checkbox.BUTTON_RIGHT = "]"


def _setup_faulthandler(log_file: str) -> None:
    """Install faulthandler to dump thread stacks on crash (best-effort)."""
    try:
        import faulthandler
        import signal as _signal

        path = str(log_file)
        try:
            _fh = open(path, "a", buffering=1)
        except Exception:
            # Fall back to stderr if the configured log path isn't writable.
            _fh = None
        faulthandler.enable(file=_fh, all_threads=True) if _fh is not None else faulthandler.enable(all_threads=True)
        for _sig in (_signal.SIGUSR1, _signal.SIGUSR2):
            try:
                # chain=False deliberately: faulthandler prints the stacks and
                # swallows the signal, so `kill -USR1 <pid>` is a pure on-demand
                # dump that does NOT terminate the process (chain=True would
                # re-raise to the default SIG_DFL and kill it).
                (
                    faulthandler.register(
                        _sig,
                        file=_fh,
                        chain=False,
                        all_threads=True,
                    )
                    if _fh is not None
                    else faulthandler.register(_sig, chain=False, all_threads=True)
                )
            except (ValueError, OSError):
                pass
    except Exception as exc:
        # faulthandler — диагностика «на всякий случай»: её отсутствие не
        # должно мешать запуску, но и молчать о нём нельзя (ADR-6).
        logger.debug("faulthandler setup skipped: %s", exc)


def _release_pyarrow_thread() -> None:
    """Let pyarrow's jemalloc arena release its worker thread immediately.

    pyarrow starts a non-daemon thread that otherwise lives until ``os._exit``,
    which makes a plain quit hang for a moment. The call is best-effort and has
    exactly two expected refusals: pyarrow is not installed (``ImportError`` —
    it is an optional dependency of the payload engine) and the wheel was built
    without jemalloc (``ArrowNotImplementedError``, a ``RuntimeError``). Both
    are named here instead of a blanket ``except Exception``: a signature change
    in pyarrow must fail loudly rather than be filed under "no jemalloc".
    """
    try:
        import pyarrow as pa

        pa.jemalloc_set_decay_ms(0)
    except (ImportError, RuntimeError) as exc:
        # Поток pyarrow проживёт до os._exit — выход задержится на мгновение,
        # а не сломается; запись объясняет, почему задержка есть.
        logger.debug("jemalloc decay not configured: %s", exc)


class PentoolApp(NotificationsMixin, ProxyRuntimeMixin, ProxyEventHandlersMixin, ProjectAutoSaveMixin, App):
    """Main Pentool TUI application."""

    TITLE = "Pentool"
    SUB_TITLE = "Web Security Testing"

    CSS = (Path(__file__).parent / "app.tcss").read_text(encoding="utf-8")

    BINDINGS = []

    def __init__(self) -> None:
        super().__init__()
        self._bindings = build_global_bindings()
        self._cfg = get_config()
        # Proxy backend: 'daemon' (default, isolated subprocess via ProxyClient)
        # or 'memory' (legacy ProxyServer on a daemon thread). Selected from
        # config.proxy_engine so the isolated path can be reverted instantly.
        self._proxy_engine: str = getattr(self._cfg, "proxy_engine", "daemon")
        self._proxy: ProxyServer | ProxyClient | None = None
        self._proxy_api: ProxyAPI = ProxyAPI()
        # Built here, not in on_mount: ProxyService's constructor touches no
        # event loop (only the storage is opened, later, in init_storage), so
        # the screen can receive it through its constructor instead of having
        # its private field assigned from outside (REPORT.md F-012).
        self._proxy_service: ProxyService = ProxyService(
            proxy_api=self._proxy_api,
            db_path=self._cfg.db_path,
            event_bus=get_event_bus(),
            on_storage_error=self._on_storage_error,
        )
        self._proxy_thread: threading.Thread | None = None
        self._proxy_loop: asyncio.AbstractEventLoop | None = None
        self._active_module = "dashboard"
        self._project_path: str | None = None
        self._project_loaded: bool = False  # Flag: project created or opened
        self._skip_project_guard: bool = False  # True in tests to bypass the guard
        # Protection against message storm: set of pending req_ids for deduplication.
        # Guarded by a Lock because it is read/written from both the TUI event
        # loop thread and the proxy's reader thread (via EventBus callbacks).
        self._pending_done_ids: set[str] = set()
        self._pending_done_lock: threading.Lock = threading.Lock()
        # Set when a deliberate quit (action_quit / Ctrl+Q) is underway, so the
        # exit log in _on_exit_app can tell a normal shutdown from a crash.
        # Reset per run() naturally since a fresh app instance is created per launch.
        self._is_quitting = False
        # Diagnostic: patched below to capture the call-site of app.exit() so the
        # "run() returned cleanly" dump in __main__.py can cross-reference who
        # requested the exit. Textual's App.exit() does NOT raise anything that
        # escapes run() — it sets an internal flag and the event loop winds down
        # naturally.  Without a probe, the "clean return" case (no exception =>
        # no traceback) has no way to name the caller.
        # _exit_caller_stack removed — was dead code (always empty, no writer)
        # Cached module screens + last time we re-resolved them. Live proxy
        # traffic calls on_proxy_request_* / on_send_to_target *per request*;
        # each call used to do a fresh `query_one(SCREEN_*)`. When a module
        # screen wasn't mounted (other tab, being torn down), that became a
        # query_one → NoMatches → try/except → log-log-log on EVERY request —
        # under a wall of traffic this alone pegged the CPU (~25%) with the UI
        # already gone. Cache the resolved screen and only re-resolve on a slow
        # interval, so a missing screen degrades to a quiet no-op instead of a
        # per-request hunt.
        self._proxy_screen = None
        self._target_screen = None
        # Vim-style key sequences: "g" prefix for Proxy sub-tabs
        # Shift+p then h/i/w → proxy HTTP/Intercept/WS
        self._key_seq_state: str = ""
        self._key_seq_time: float = 0.0
        self._key_seq_timeout: float = 1.0  # one second to enter the second key
        # Project auto-save (Block 3.3)
        from textual.timer import Timer as _Timer

        self._auto_save_timer: "_Timer | None" = None
        # Project management — extracted to keep app.py focused on Textual wiring
        from pentool.tui.project_manager import ProjectManager

        self._pm = ProjectManager(self)
        # Shared "is a crawl in progress" state. There is no dedicated
        # SpiderScreen/module-tab anymore — crawling runs only from
        # TargetScreen's "Crawl scope"/"Crawl selected host" triggers
        # (which build their own SpiderAPI instance — see
        # TargetScreen._crawl_hosts_worker). A counter (not a bool) because
        # _crawl_hosts_worker can in principle be re-triggered while a
        # previous one is still finishing up; ActivityIndicator's Spider
        # glyph reads this via is_spider_active().
        self._spider_active_count: int = 0

    def spider_crawl_started(self) -> None:
        """Call when any crawl begins — keeps ActivityIndicator's Spider
        glyph in sync regardless of which screen initiated the crawl."""
        self._spider_active_count += 1

    def spider_crawl_finished(self) -> None:
        """Call when a crawl started via spider_crawl_started() ends (success,
        error, or stop) — never let the counter go negative even if start/end
        calls end up mismatched somewhere."""
        self._spider_active_count = max(0, self._spider_active_count - 1)

    def is_spider_active(self) -> bool:
        return self._spider_active_count > 0

    def notify(
        self,
        message: str,
        *,
        severity: str = "information",
        title: str | None = None,
        timeout: int | None = None,
        markup: bool = False,
    ) -> None:
        """Override Textual App.notify — log error notifications to pentool.log.

        ``markup`` defaults to ``False`` here, unlike Textual. Notification text
        is almost always data from outside — an exception message from ``err()``,
        a URL, a filename, a license-server reply — and Rich markup in it either
        raises ``MarkupError`` or turns into a ``[link=javascript:…]`` link. A
        caller that really wants styling passes ``markup=True`` and escapes its
        own values (:func:`pentool.tui.markup.esc`).
        """
        if severity == "error":
            logger.error("UI NOTIFICATION: [%s] %s", severity, message)
        super().notify(message, severity=severity, title=title, timeout=timeout, markup=markup)

    def _handle_exception(self, error: Exception) -> None:
        """Catch fatal exceptions — log before passing to Textual."""
        import traceback

        logger.error(
            "FATAL EXCEPTION: %s\n%s",
            error,
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )
        # Additionally dump EVERY thread's Python stack — a module screen can
        # be torn down by Textual after a fatal error, and the plain traceback
        # above loses what the other threads (proxy loop, aiosqlite) were doing
        # at the moment the app collapsed. All-threads dump is what shows the
        # actual trigger ("TUI just vanished" hunting).
        try:
            import faulthandler
            import io

            _buf = io.StringIO()
            faulthandler.dump_traceback(file=_buf, all_threads=True)
            logger.error(
                "APP: --- fatal all-thread dump begin ---\n%s\n--- fatal all-thread dump end ---",
                _buf.getvalue(),
            )
        except Exception as exc:
            # Молча здесь было бы хуже всего: этот дамп добавляют ровно к тому
            # падению, которое не удаётся поймать, и его отсутствие нужно
            # видеть в журнале, а не искать глазами.
            logger.debug("APP: all-thread dump failed: %s", exc)
        super()._handle_exception(error)

    @staticmethod
    def _guard_forward_event() -> None:
        """Monkey-patch Textual Screen._forward_event to degrade layout-race crash to no-op."""
        try:
            import textual.screen as _tss

            if getattr(_tss.Screen, "_pentool_guard_done", False):
                return
            _tss.Screen._pentool_guard_done = True

            def _is_layout_race(exc: BaseException) -> bool:
                """True if *exc* is the known 'widget layout changed under the
                mouse' race, which must degrade to a no-op rather than kill the
                TUI (the "TUI just vanished" class)."""
                if isinstance(exc, AttributeError):
                    return "has no attribute 'region'" in str(exc)
                # textual.errors.NoWidget — hover under a coordinate that no
                # longer has a widget (history table rebuilt under traffic).
                if type(exc).__name__ == "NoWidget":
                    return True
                return False

            # 1) Guard Screen._forward_event (mouse dispatch) against the
            #    parent.region dereference race.
            _orig_fwd = _tss.Screen._forward_event

            def _guarded_fwd(self, event) -> None:
                try:
                    _orig_fwd(self, event)
                except Exception as _e:  # noqa: BLE001
                    if _is_layout_race(_e):
                        return
                    raise

            _guarded_fwd.__name__ = "_forward_event"
            _guarded_fwd.__qualname__ = "Screen._forward_event"
            _tss.Screen._forward_event = _guarded_fwd

            # 2) Guard Screen._handle_mouse_move against NoWidget (hover under a
            #    coordinate with no widget while the layout is being refreshed).
            if hasattr(_tss.Screen, "_handle_mouse_move"):
                _orig_mm = _tss.Screen._handle_mouse_move

                def _guarded_mm(self, event) -> None:
                    try:
                        _orig_mm(self, event)
                    except Exception as _e:  # noqa: BLE001
                        if _is_layout_race(_e):
                            return
                        raise

                _guarded_mm.__name__ = "_handle_mouse_move"
                _guarded_mm.__qualname__ = "Screen._handle_mouse_move"
                _tss.Screen._handle_mouse_move = _guarded_mm

            logger.debug("APP: Screen mouse-dispatch guarded against layout races")
        except Exception as exc:
            # Патч не обязателен для работы, но если он не встал — мышь будет
            # падать на гонке раскладки так же, как падала до него, и это
            # единственный след, по которому это можно понять.
            logger.debug("APP: layout-race guard not installed: %s", exc)

    def compose(self) -> ComposeResult:
        yield ModuleTabs(id="module-tabs")
        with ContentSwitcher(initial="screen-dashboard"):
            yield DashboardScreen(id="screen-dashboard")
            yield ProxyScreen(id="screen-proxy", proxy_service=self._proxy_service)
            yield RepeaterScreen(id="screen-repeater")
            yield IntruderScreen(id="screen-intruder")
            yield ScannerScreen(id="screen-scanner")
            yield TargetScreen(id="screen-target")
            yield DecoderScreen(id="screen-decoder")
            yield ComparerScreen(id="screen-comparer")
            yield SequencerScreen(id="screen-sequencer")
            yield ExtensionsScreen(id="screen-extensions")
            yield SettingsScreen(id="screen-settings")
            # ReconScreen — PRO-only, conditional
            recon_cls = SCREEN_MAP.get("recon")
            if recon_cls is not None:
                yield recon_cls(id="screen-recon")
        # Footer and StatusBar both used to `dock: bottom` independently —
        # in Textual, multiple independently-docked widgets at the same
        # edge don't stack, they all pin to the same row and overlap each
        # other (whichever was composed last wins the pixels). That's why
        # StatusBar (and, inside it, the new ActivityIndicator) never
        # rendered — Footer, composed after it, was drawn on top and
        # covered it completely. Wrapping both in one docked container
        # lets them lay out normally (one above the other) inside it.
        with Vertical(id="bottom-dock"):
            yield ModuleHintBar(id="module-hints")
            yield GlobalHintBar(id="global-hints")
            yield StatusBar(id="statusbar")

    async def on_mount(self) -> None:
        setup_logging(self._cfg.log_file, self._cfg.log_level)
        _setup_faulthandler(self._cfg.log_file)
        self._guard_forward_event()
        # Init ModuleHintBar with the starting module (dashboard)
        try:
            self.query_one(ModuleHintBar).set_module("dashboard")
        except NoMatches as exc:
            # Подсказки клавиш при старте — единственное, что скажет
            # пользователю, как тут что-то делать; их пропажа должна быть
            # видна в журнале.
            logger.debug("starting hint bar not initialised: %s", exc)

        # _exit_caller_stack removed — dead code (was always empty, see __init__).

        try:
            await init_db(self._cfg.db_path)
        except Exception:
            # Без схемы ни один модуль не откроет проект: приложение стартует,
            # но всё, что пишет в базу, будет падать уже своими ошибками.
            logger.exception("DB init failed")

        if self._proxy_engine == "daemon":
            # Isolated: ProxyClient facade over the daemon subprocess. Events
            # come back over the event socket and are re-emitted into the TUI
            # EventBus by the client's reader thread, so downstream subscribers
            # (ProxyService → HttpStorage, ProxyScreen) behave as before.
            self._proxy = ProxyClient(
                host=self._cfg.proxy_host,
                port=self._cfg.proxy_port,
                cert_dir=self._cfg.cert_dir,
                db_path=self._cfg.db_path,
            )
        else:
            # Legacy fallback: in-process ProxyServer on a daemon thread.
            self._proxy = ProxyServer(
                host=self._cfg.proxy_host,
                port=self._cfg.proxy_port,
                cert_dir=self._cfg.cert_dir,
                db_path=self._cfg.db_path,
            )
        # Startup prefs. For ProxyClient these property setters only cache the
        # value while no socket exists; start() pushes them into the daemon.
        self._proxy.intercept_enabled = self._cfg.intercept_enabled
        # Sync scope from config into Proxy
        if self._cfg.scope:
            self._proxy.scope = list(self._cfg.scope)
            logger.info("APP: scope loaded from config: %s", self._cfg.scope)

        # Inject Proxy into the API layer
        self._proxy_api.set_proxy(self._proxy)

        # The service already reached ProxyScreen through its constructor;
        # only storage still has to be opened. Run init_storage synchronously
        # and WAIT for it to complete before auto-opening the last project
        # (which calls switch_db).
        try:
            await self._proxy_service.init_storage()
            logger.info("APP: ProxyService init_storage completed")
        except Exception:
            # Хранилище прокси не открылось: история запросов не пишется, а
            # экран Proxy показывает пустоту при живом трафике.
            logger.exception("ProxyService.init_storage failed")

        # Initialize global Event Bus and subscribe app-level handlers
        bus = get_event_bus()
        bus.subscribe(FindingDiscovered, self._on_bus_finding_discovered)
        bus.subscribe(ScanStarted, self._on_bus_scan_started)
        bus.subscribe(ScanFinished, self._on_bus_scan_finished)
        bus.subscribe(ScanProgressEvent, self._on_bus_scan_progress)
        bus.subscribe(PassiveScanToggled, self._on_bus_passive_toggled)
        # Sprint 3: subscribe to proxy events via EventBus
        # (proxy emits from its own thread, we bridge via call_from_thread)
        bus.subscribe(ProxyRequestCaptured, self._on_bus_proxy_captured)
        bus.subscribe(ProxyRequestCompleted, self._on_bus_proxy_completed)
        logger.info("APP: EventBus subscribed")

        self._update_status()
        logger.info("Pentool TUI started")

        # Pre-generate CA certificate in background — so that by the time
        # "Start Proxy" is pressed it is already ready and doesn't slow startup (option C)
        self.run_worker(self._prewarm_ca(), exclusive=False, thread=False)

        _release_pyarrow_thread()

        from pentool.utils.terminal_check import get_terminal_warning

        warning = get_terminal_warning()
        if warning:
            self.notify(warning, severity="warning", timeout=6)

        # Handle SIGTERM — graceful shutdown on kill/systemd stop (10.2)
        self._setup_signal_handlers()

        # R-16: subscribe to config changes — SettingsScreen will notify us
        # NOTE: do NOT name this _on_config_changed — Textual treats any method
        # matching _(on_)<MessageClass> as a message handler and calls it with the
        # Message object instead of dict, causing an infinite post_message loop.
        self._cfg.add_observer(self._cfg_observer_cb)

        # Apply saved theme
        saved_theme = getattr(self._cfg, "theme", "textual-dark")
        try:
            self.theme = saved_theme
        except InvalidThemeError as exc:
            # Тема из конфига — пользовательский выбор, и если она перестала
            # существовать (переименована в новой Textual), приложение
            # остаётся на тёмной по умолчанию. Без записи это неотличимо от
            # «настройка не сохранилась». Ловится ровно `InvalidThemeError`,
            # которым Textual отвечает на незарегистрированное имя.
            logger.debug("saved theme %r not applied: %s", saved_theme, exc)

        # Auto-save (Block 3.3) — start if enabled in config
        self._setup_auto_save()

        # Lock Scanner tab if no valid license with scanner_pro feature
        self._refresh_scanner_tab_lock()

        # Seed target URL(s) passed via `pentool --url ...` — a NEW project for
        # the target is created, proxy on, target populated, ready to audit.
        # When --url is given we do NOT auto-open the last project.
        pending = getattr(self, "_pending_start_urls", None)
        if pending:
            self.run_worker(self._seed_pending_urls(list(pending)), exclusive=False, thread=False)
        elif getattr(self, "_pending_open_last", False):
            # --last flag: auto-open the most recent project
            self.run_worker(self._auto_open_last_project(), exclusive=False, thread=False)
        # else: no --last, no --url — start with empty project

        # Check for updates in background (if enabled in settings)
        if getattr(self._cfg, "check_updates", True):
            self.run_worker(self._check_for_updates(), exclusive=False, thread=False)

        # Check for a newer PRO build in background (if a PRO license is
        # active) — closes the gap where pentool-pro ships a fix but an
        # already-activated machine keeps running the stale code forever,
        # since the PRO package otherwise only downloads once, at activation.
        self.run_worker(self._check_for_pro_update(), exclusive=False, thread=False)

        # Global AI: if the master switch was left ON (persisted), bring up the
        # MCP server and make AI controls visible right away. If OFF, hide them.
        self._start_ai_if_enabled()

        # -- DEV-ONLY (промо-скринкасты) ------------------------------
        # Минисервер координат виджетов для точных xdotool-кликов при записи
        # видео. Подключается СТРОГО опционально и никогда не ломает release:
        # нужен только если задан PENTOOL_COORDS_FILE=<абс.путь> (gitignored
        # tools/dev/coords_server.py) И PENTOOL_COORDS_PORT. В обычной
        # разработке/релизе env-переменных нет — тут просто тихий return.
        try:
            import importlib.util
            import os as _os

            _cspath = _os.environ.get("PENTOOL_COORDS_FILE")
            if _cspath and _os.path.exists(_cspath):
                _spec = importlib.util.spec_from_file_location("_dev_coords_server", _cspath)
                if _spec and _spec.loader:
                    _mod = importlib.util.module_from_spec(_spec)
                    _spec.loader.exec_module(_mod)
                    _mod.activate_coords_worker(self)
        except Exception as exc:  # логируем в /tmp (диагностика съёмки)
            # Здесь широкий `except` оправдан и назван осознанно: выполняется
            # произвольный внешний файл (`exec_module`), и падать он может
            # чем угодно. Ошибка попадает и в журнал приложения, и в /tmp —
            # второй нужен сценарию записи, который читает файл мимо лога.
            logger.exception("coords activation failed: %s", exc)
            try:
                import traceback as _tb

                with open("/tmp/pentool_coords_err.log", "a") as _f:
                    _f.write(f"PENTOOL coords activation error: {exc!r}\n")
                    _tb.print_exc(file=_f)
            except OSError as log_exc:
                # Уже в ветке «записать ошибку не удалось»: единственное, что
                # остаётся, — не уронить приложение из-за диагностики.
                logger.debug("coords activation error not recorded: %s", log_exc)

    async def _auto_open_last_project(self) -> None:
        """Open the last project from recent_projects at startup."""
        await asyncio.sleep(0.2)  # give Textual time to render the UI
        recent = getattr(self._cfg, "recent_projects", [])
        if not recent:
            return
        path = recent[0]
        if not os.path.exists(path):
            logger.info("APP: last project not found: %s", path)
            return
        logger.info("APP: auto-opening last project: %s", path)
        # Use the same exclusive worker path as manual open — no races
        self._pm.switch_project_db(path, is_new=False)

    async def _seed_pending_urls(self, urls: list[str]) -> None:
        """Seed targets from --url flag into Target/SiteMap."""
        await asyncio.sleep(0.6)  # let the TUI render first

        # Create a NEW project for this target (do not reuse the last project).
        try:
            new_path = self._project_path_for_target(urls[0])
            self._pm.switch_project_db(new_path, is_new=True)
        except Exception:
            # Проект не создан — и весь остальной seed пойдёт в предыдущий
            # проект, то есть данные для нового хоста окажутся в чужой базе.
            logger.exception("seed: new project create failed")

        for url in urls:
            try:
                from pentool.utils.parser import ParsedRequest

                self.post_message(SendUrlToTarget(ParsedRequest(method="GET", url=url)))
            except Exception:
                # Хост из --url не попал в Target вовсе: флаг сработал, а цели
                # в дереве нет — поэтому здесь нужен traceback, а не строка.
                logger.exception("seed: url %s not seeded", url)

        real = bool(getattr(self, "_pending_start_smart", False))
        use_ai = bool(getattr(self, "_pending_start_ai", False))

        # If --ai flag was passed, start the MCP server and enable AI
        if use_ai:
            try:
                from pentool.services.ai.factory import start_ai

                self.run_worker(start_ai(self._cfg, _force=True))
                logger.info("seed: --ai: starting MCP server")
            except Exception:
                # --ai не запустился: AI-панель останется неактивной, хотя
                # флаг был передан, — причину показывает только traceback.
                logger.exception("seed: --ai start failed")
            try:
                from pentool.core.config import get_config

                cfg = get_config()
                cfg.ai_enabled = True
            except Exception:
                # Флаг --ai остаётся включённым только в конфиге: если записать
                # его не удалось, следующий запуск будет уже без AI, и без
                # записи об этом догадаться неоткуда.
                logger.exception("seed: --ai flag not persisted")

        # Start the proxy so --real traffic (and subsequent manual use) can be
        # intercepted and land in the project.
        proxy_started = False
        try:
            if not (self._proxy and self._proxy.is_running):
                self._start_proxy()
                proxy_started = True
        except Exception:
            # Прокси не поднялся — при --real трафик не пойдёт через него
            # вовсе, то есть проект останется пустым без видимой причины.
            logger.exception("seed: proxy start failed")

        logger.info(
            "seed: --real=%s proxy_started=%s proxy_running=%s",
            real,
            proxy_started,
            bool(self._proxy and self._proxy.is_running),
        )
        # Auto-scope: добавляем хост в скоуп ВСЕГДА при --real, даже если
        # fetch не удался. Без этого хост не попадает ни в SiteMap.scope,
        # ни в ProxyServer.scope, и техдетект не запускается.
        for target_url in urls:
            try:
                from urllib.parse import urlparse

                from pentool.tui.mixins.auto_scope import _force_scope_host

                parsed = urlparse(target_url)
                host = parsed.netloc or parsed.hostname or target_url
                logger.info("seed: force-scope %s (real=%s)", host, real)
                _force_scope_host(host, self)
            except Exception:
                # Хост не попал в scope: запросы к нему уйдут в Proxy-историю
                # как out-of-scope, а техдетект не запустится вовсе.
                logger.exception("seed: force-scope failed for %s", target_url)

        if real:
            # Actually fetch the target(s) through the proxy so real requests
            # show up in the project (not just a dry seed entry).
            try:
                logger.info("--real: calling _do_real_fetch for %s", urls)
                # Run the WHOLE browser fetch in an executor thread (time.sleep,
                # subprocess.run) — Textual's loop doesn't pump `await
                # asyncio.sleep()` inside this worker, which hung the old async
                # wait-loop and produced zero logs/children.
                loop = asyncio.get_running_loop()
                ok = await asyncio.wait_for(loop.run_in_executor(None, self._do_real_fetch_sync, urls), timeout=140)
                logger.info("--real: fetch done ok=%s", ok)
                if ok:
                    self.call_after_refresh(self._refresh_target_tree)
                else:
                    self.notify(
                        "--real: browser fetch didn't capture traffic",
                        severity="warning",
                        timeout=6,
                    )
            except Exception as exc:
                from pentool.core.error_guard import err

                err(exc, "--real fetch failed", self, severity="warning")

        proxy_ready = proxy_started or bool(self._proxy and self._proxy.is_running)
        ready = "proxy on, ready to audit" if proxy_ready else "ready to audit"
        self.notify(f"New project for {len(urls)} URL(s) — {ready}.", timeout=6)

    def _do_real_fetch_sync(self, urls: list[str]) -> bool:
        """Fetch URLs through proxy via headless Chrome in executor thread (avoids asyncio hang)."""
        import subprocess
        import time

        # The proxy starts async via _start_proxy — wait up to ~10s (time.sleep).
        waited = 0
        while not (self._proxy and self._proxy.is_running):
            time.sleep(0.2)
            waited += 0.2
            if waited >= 10:
                break
        if not (self._proxy and self._proxy.is_running):
            logger.info("--real: proxy not ready after %.1fs, cannot fetch", waited)
            return False

        proxy_host = self._proxy.host or "127.0.0.1"
        proxy_port = self._proxy.port or 8080
        proxy_url = f"http://{proxy_host}:{proxy_port}"

        # Lightpanda binary (third-party, not a pip dep) drives --real now. It
        # executes JS and, with --http-proxy + --ca-cert, sends the real request
        # through OUR MITM proxy so it lands in HTTP History + Target (same as
        # the old Chromium/Playwright path, without the Node/browser stack).
        import pentool.utils.lightpanda as _lp

        binary = _lp.find_lightpanda_binary()
        if binary is None:
            logger.warning("--real: lightpanda binary not installed — cannot fetch")
            return False

        cmd = [binary, "fetch"]
        cmd.extend(urls)
        cmd += [
            "--dump",
            "html",
            "--http-proxy",
            proxy_url,
            "--wait-ms",
            "3000",
        ]
        # Trust our MITM CA so HTTPS captures work (not just HTTP).
        ca_path = os.path.join(self._cfg.cert_dir, "ca.crt")
        if os.path.isfile(ca_path):
            cmd += ["--ca-cert", ca_path]

        logger.info("--real: running lightpanda fetch via subprocess in executor (bin=%s)", binary)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            logger.info("--real: lightpanda returned rc=%s", result.returncode)
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            for line in err.splitlines():
                logger.debug("--real: %s", line)
            if result.returncode != 0:
                logger.warning(
                    "--real: lightpanda exited %s: %s",
                    result.returncode,
                    (err.splitlines()[-1] if err else ""),
                )
                return False
            return bool(out)
        except subprocess.TimeoutExpired:
            logger.warning("--real: lightpanda timed out")
            return False
        except Exception as exc:
            logger.warning("--real: lightpanda capture error: %s", exc)
            return False

    def _refresh_target_tree(self) -> None:
        try:
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target._refresh_tree()
        except Exception as exc:
            # Экран Target строится лениво: при --url прогоне его может ещё не
            # быть, и это нормально. Отличить норму от «дерево не обновилось»
            # можно только по записи.
            logger.debug("--real: Target tree not refreshed: %s", exc)

    def _project_path_for_target(self, url: str) -> str:
        """Build a clean .db path for a target URL with a date+time stamp so each
        `pentool --url ...` run creates a fresh, uniquely-named project.

        e.g. ~/.config/pentool/projects/xss-game.appspot.com_20260818_185030.db
        """
        from datetime import datetime
        from urllib.parse import urlparse

        host = urlparse(url if "://" in url else f"//{url}").netloc or url
        host_clean = "".join(c if (c.isalnum() or c in "._-") else "_" for c in host).strip(".")
        if not host_clean:
            host_clean = "target"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Fixed projects dir (~/.config/pentool/projects/) — NOT derived from
        # the current db_path, which would nest projects/projects/... deeper
        # on every --real run.
        from pentool.core.config import DEFAULT_CONFIG_DIR

        projects_dir = DEFAULT_CONFIG_DIR / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        return str(projects_dir / f"{host_clean}_{stamp}.db")

    async def _check_for_updates(self) -> None:
        """Check for a new version in the background. Show notify if an update is available."""
        import asyncio as _asyncio

        await _asyncio.sleep(3.0)  # give the UI time to fully load
        try:
            from pentool.core.updater import check_update_async

            info = await check_update_async()
            if info.has_update:
                self.notify(
                    f"New version available: {info.latest_version} — run `pentool update`",
                    severity="information",
                    timeout=10,
                )
                logger.info("APP: update available: %s", info.latest_version)
        except Exception as exc:
            logger.debug("APP: update check failed: %s", exc)

    async def _check_for_pro_update(self) -> None:
        """Re-download PRO package if newer build published (no-op if no PRO)."""
        import asyncio as _asyncio

        await _asyncio.sleep(4.0)  # after the pip-update check, UI settled
        try:
            from pentool.core.license import check_and_update_pro_package

            result = await check_and_update_pro_package()
            if result.updated:
                self.notify(
                    "PRO package updated to the latest build — restart Pentool to use it.",
                    severity="information",
                    timeout=10,
                )
                logger.info("APP: PRO package updated to a newer build")
            elif result.warning:
                self.notify(result.warning, severity="warning", timeout=15)
                logger.warning("APP: PRO package incompatible: %s", result.warning)
        except Exception as exc:
            logger.debug("APP: PRO update check failed: %s", exc)

    def _cfg_observer_cb(self, changed_fields: dict) -> None:
        """Config Observer callback (named to avoid Textual _on_* dispatch collision)."""
        self.post_message(ConfigChanged(changed_fields))

    #: Below this terminal width the layout switches to its compact form.
    NARROW_BREAKPOINT: int = 80

    def on_resize(self, event) -> None:
        """Adapt the layout to the terminal width — never the user's state.

        This used to call ``ProxyScreen.action_toggle_inspector()`` when the
        terminal dropped below 80 columns. That flipped ``_inspector_visible``,
        so widening the terminal again did *not* bring the inspector back: a
        layout reaction had permanently changed a user preference (F-027,
        ADR-7).

        Now the width only sets a class on the base screen. CSS decides what a
        narrow terminal shows, and the user's own choice survives the trip
        down to 60 columns and back.

        The class goes on ``screen_stack[0]`` rather than ``self.screen``: the
        latter is the top of the stack, so an open dialog would take the class
        with it and the module underneath would stay unmarked until the next
        resize.
        """
        try:
            stack = self.screen_stack
            stack[0].set_class(event.size.width < self.NARROW_BREAKPOINT, "narrow")
        except IndexError:  # pragma: no cover - screen missing during teardown
            # Стек экранов пуст только когда приложение уже разбирают; класс
            # `narrow` тогда все равно никому не нужен. Ловится `IndexError`,
            # а не `Exception`, чтобы опечатка в `set_class` была видна.
            logger.debug("on_resize: no screen to mark narrow")

    @on(ModuleSelected)
    def on_module_selected(self, event: ModuleSelected) -> None:
        self._switch_to(event.module_id)

    def action_switch_module(self, module_id: str) -> None:
        self._switch_to(module_id)
        try:
            self.query_one(ModuleTabs).select_module(module_id)
        except NoMatches as exc:
            # Экран уже переключён строкой выше; отказ здесь означает, что
            # подсветка вкладки разошлась с содержимым — это видно глазом, но
            # причину показывает только запись.
            logger.debug("switch_module: tab highlight not updated: %s", exc)

    def on_key(self, event) -> None:
        """Ctrl+A select-all, Ctrl+E export, F2-F4 module tabs."""
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

        # Reset state on timeout
        if self._key_seq_state and (now - self._key_seq_time) > self._key_seq_timeout:
            self._key_seq_state = ""

        if self._key_seq_state == "P":
            # Second character of the sequence
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
            # Start of Shift+P sequence (P already does switch_module, we'll catch the second key)
            self._key_seq_state = "P"
            self._key_seq_time = now
            # No preventDefault — Binding with "P" will fire first (switch to proxy),
            # then if the user presses h/i/w — it will switch to the sub-tab

    def action_proxy_tab(self, tab: str) -> None:
        self.action_switch_module("proxy")
        tab_ids = {
            "http": "tab-http-history",
            "intercept": "tab-intercept",
            "ws": "tab-ws-history",
        }
        tab_id = tab_ids.get(tab)
        if not tab_id:
            return
        try:
            proxy_screen = self.query_one("#screen-proxy", ProxyScreen)
            from textual.widgets import TabbedContent

            tabs = proxy_screen.query_one("#proxy-subtabs", TabbedContent)
            tabs.active = tab_id
            self.call_after_refresh(lambda tid=tab_id: self._focus_proxy_table(proxy_screen, tid))
        except NoMatches as exc:
            # Пользователь нажал горячую клавишу вкладки — и остался на старой.
            # Экран Proxy или панель вкладок ещё не смонтированы; именно это
            # и значит `NoMatches`, других причин тут нет.
            logger.debug("proxy_tab %s: switch failed: %s", tab_id, exc)

    def _focus_proxy_table(self, proxy_screen: object, tab_id: str) -> None:
        """Focus the DataTable in the specified Proxy tab."""
        try:
            from textual_fastdatatable import DataTable

            table_ids = {
                "tab-http-history": "#request-list",
                "tab-intercept": None,  # intercept has no table
                "tab-ws-history": "#ws-request-list",
            }
            table_sel = table_ids.get(tab_id)
            if table_sel:
                table = proxy_screen.query_one(table_sel, DataTable)  # type: ignore[union-attr]
                table.focus()
                if table.row_count > 0:
                    table.move_cursor(row=0)
        except (NoMatches, ImportError) as exc:
            # Фокус — не то, ради чего стоит падать, но «переключился на tab,
            # а клавиатура осталась в старом» иначе не диагностируется.
            # Две ожидаемые причины названы: таблицы нет в дереве
            # (`NoMatches`) и нет самого `textual_fastdatatable` (`ImportError`).
            logger.debug("_focus_proxy_table %s: %s", tab_id, exc)

    def _focus_repeater_editor(self, repeater) -> None:
        """Set focus to the RequestEditor in the active Repeater tab."""
        try:
            from pentool.tui.widgets.request_editor import RequestEditor

            tab_id = repeater._active_tab_id
            if tab_id:
                editor = repeater.query_one(f"#req-editor-{tab_id}", RequestEditor)
                # The TextArea is ContentPanel's #cp-body-widget; focusing a
                # made-up "#editor-area" raised NoMatches into the except below.
                editor.content_widget.focus()
        except NoMatches as exc:
            # Комментарий выше — ровно про этот except: он уже однажды прятал
            # опечатку в селекторе. Поэтому ловится ровно `NoMatches` —
            # «редактора нет в дереве», — а `AttributeError` от неверного
            # объекта пусть всплывает: это опечатка, её надо видеть.
            logger.debug("_focus_repeater_editor: %s", exc)

    def action_repeater_send(self) -> None:
        """Ctrl+Space / ctrl-at — send the request to Repeater regardless of focus depth."""
        if self._active_module != "repeater":
            return
        try:
            repeater = self.query_one(SCREEN_REPEATER, RepeaterScreen)
            repeater.action_send()
        except NoMatches as exc:
            # Экрана Repeater нет в дереве — активный модуль и DOM разошлись
            # (переключение ещё не доехало). Горячая клавиша не сработает.
            logger.debug("repeater_send: screen not mounted: %s", exc)
        except Exception:
            # Ctrl+Space молча ничего не делает — худший из возможных исходов
            # горячей клавиши: пользователь нажимает её ещё и ещё. Всё, что не
            # `NoMatches`, здесь — сбой внутри отправки, и нужен трейсбек.
            logger.exception("repeater_send: send failed")

    # Modules available without an open project
    _FREE_MODULES = {"dashboard", "settings"}

    def _refresh_scanner_tab_lock(self) -> None:
        """Lock or unlock the Scanner tab based on the current license."""
        try:
            from pentool.core.license import get_session_license

            lic = get_session_license()
            scanner_available = lic.valid and lic.has_feature("scanner_pro")
        except Exception:
            # Ошибка чтения лицензии — это «не знаем», а не «можно»: вкладка
            # Scanner остаётся запертой, и причина остаётся в журнале
            # трейсбеком — иначе «лицензия не работает» не отличить от
            # испорченного файла лицензии.
            logger.exception("license check failed, Scanner stays locked")
            scanner_available = False
        try:
            self.query_one("#module-tabs", ModuleTabs).set_scanner_locked(not scanner_available)
        except NoMatches as exc:
            # Замок не встал — вкладка выглядит доступной. Без записи это
            # выглядит как «лицензия не работает», а не как «виджета нет».
            logger.debug("scanner tab lock not applied: %s", exc)

    def _switch_to(self, module_id: str) -> None:
        if module_id == self._active_module:
            return
        if module_id not in SCREEN_MAP:
            return
        if not self._project_loaded and not self._skip_project_guard and module_id not in self._FREE_MODULES:
            self.notify(
                "Please create or open a project first (Ctrl+N / Ctrl+O)",
                severity="warning",
                timeout=4,
            )
            return
        # Block Scanner if no valid license
        if module_id == "scanner":
            try:
                from pentool.core.license import get_session_license

                lic = get_session_license()
                if not (lic.valid and lic.has_feature("scanner_pro")):
                    self.notify(
                        "🔒 Scanner — paid feature. Activate: pentool license trial",
                        severity="warning",
                        timeout=5,
                    )
                    return
            except Exception as exc:
                # Раньше здесь стоял `pass`, и любой сбой чтения лицензии
                # открывал платный экран — то есть ошибка работала на
                # пользователя, а не против него. Теперь наоборот: не смогли
                # проверить — не пускаем, и пишем почему.
                logger.warning("scanner license check failed, access denied: %s", exc)
                self.notify(
                    "🔒 Scanner — could not verify the license. Try `pentool license status`.",
                    severity="warning",
                    timeout=5,
                )
                return

        # Block Recon if no valid license (ai_discovery feature)
        if module_id == "recon":
            try:
                from pentool.core.license import get_session_license

                lic = get_session_license()
                if not (lic.valid and lic.has_feature("ai_discovery")):
                    self.notify(
                        "🔒 Recon — paid feature. Activate: pentool license trial",
                        severity="warning",
                        timeout=5,
                    )
                    return
            except Exception as exc:
                # Тот же fail-open, что и у Scanner: не смогли проверить
                # лицензию — значит, не пускаем (и пишем почему).
                logger.warning("recon license check failed, access denied: %s", exc)
                self.notify(
                    "🔒 Recon — could not verify the license. Try `pentool license status`.",
                    severity="warning",
                    timeout=5,
                )
                return
        screen_id = f"screen-{module_id}"
        self.query_one(ContentSwitcher).current = screen_id
        self._active_module = module_id
        # Update ModuleHintBar to show the new module's keybindings
        try:
            self.query_one(ModuleHintBar).set_module(module_id)
        except NoMatches as exc:
            # Подсказки клавиш останутся от прошлого модуля — то есть будут
            # врать. Не критично, но и не то, о чём стоит молчать.
            logger.debug("hint bar not updated for %s: %s", module_id, exc)
        # Refresh AI-dependent UI whenever we switch to Target: the "🤖 Use AI"
        # checkbox visibility tracks the global ai_enabled, and this must be
        # re-applied when the Target screen is (re)shown — otherwise a checkbox
        # that was hidden while the screen wasn't mounted stays hidden even
        # after the user enables AI globally.
        if module_id == "target":
            self._sync_ai_global()
        # Re-paint any visible toasts on top after the content swap, so they
        # don't end up hidden underneath the freshly-shown tab (Textual's
        # toast rack can sit below a tab's own layers after a switch).
        self.call_after_refresh(self._refresh_notifications)
        # _update_proxy_screen_labels() only refreshes the ProxyScreen label
        # when it IS the active module — so if the proxy was stopped/started
        # while the user was on a different tab (e.g. right after creating a
        # new project, which force-stops the proxy while Dashboard is shown),
        # the label update was skipped and stayed stale until the next actual
        # start/stop toggle. Refresh it explicitly on every switch into Proxy.
        if module_id == "proxy":
            self._update_proxy_screen_labels()

    def get_proxy(self) -> ProxyServer | None:
        return self._proxy

    def get_proxy_api(self) -> ProxyAPI:
        return self._proxy_api

    async def health(self) -> dict[str, Any]:
        """Return a health-check dict for monitoring / diagnostics.

        Checks:
          - DB connection (via proxy_service)
          - Proxy status (running / stopped)
          - EventBus subscriber count
          - Spider activity
          - AI server status

        Returns a dict suitable for ``pentool status --verbose``.
        """
        status: dict[str, Any] = {
            "app": "Pentool",
            "version": __version__,
            "proxy_running": bool(self._proxy and self._proxy.is_running),
            "proxy_port": self._proxy.port if self._proxy else self._cfg.proxy_port,
            "spider_active": self.is_spider_active(),
            "project_loaded": self._project_loaded,
            "active_module": self._active_module,
        }
        # DB health
        try:
            if self._proxy_service is not None:
                await self._proxy_service._storage.count()
                status["db"] = "ok"
            else:
                status["db"] = "not_initialized"
        except Exception as e:
            status["db"] = f"error: {e}"

        # EventBus stats
        try:
            bus = get_event_bus()
            s = bus.stats()
            status["eventbus_handlers"] = s.get("total_handlers", 0)
            status["eventbus_history"] = s.get("history_size", 0)
        except Exception as exc:
            # Поля просто не появятся в выводе — но читатель статуса должен
            # понимать, что их отсутствие значит «не смогли», а не «нет шины».
            status["eventbus"] = f"error: {exc}"

        # AI status
        try:
            from pentool.services.ai.factory import is_ai_running

            status["ai_running"] = is_ai_running()
        except Exception:
            status["ai_running"] = False

        return status

    def _on_storage_error(self, message: str) -> None:
        """Show error notify when ProxyService fails to open DB (locked/unwritable)."""
        self.notify(
            f"{message}. Requests will not be saved until this is fixed — "
            f"check that no other Pentool instance has this project open.",
            severity="error",
            timeout=8,
        )

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
        """Path to the SQLite database (public access for screens)."""
        return self._cfg.db_path

    def action_toggle_intercept(self) -> None:
        if self._proxy is None:
            return
        enabled = not self._proxy.intercept_enabled
        # Use thread-safe method — proxy loop runs in a separate thread,
        # direct assignment can cause a race condition (R-fix: intercept bug)
        self._proxy.set_intercept(enabled)
        logger.info("APP: intercept toggled → %s (thread-safe)", enabled)
        self._update_status()
        self._update_proxy_screen_labels()

    # -- Proxy start/stop/toggle lives in ProxyRuntimeMixin (tui/mixins/proxy_runtime.py)

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM/SIGINT for graceful shutdown (10.2).

        signal.signal() only works in the main thread. On SIGTERM
        we call action_quit() via loop.call_soon_threadsafe — this is safe
        from a signal handler since it is called in the asyncio event loop context.
        """

        def _handle_signal(signum: int, frame: object) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("APP: received %s — initiating graceful shutdown", sig_name)
            # Use call_soon_threadsafe — safe from any context,
            # including signal handlers in the main thread.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.action_quit)
            except Exception:
                # Last resort — just exit
                import sys as _sys

                _sys.exit(0)

        try:
            signal.signal(signal.SIGTERM, _handle_signal)
            # SIGINT is already handled by Textual (KeyboardInterrupt → exit),
            # override for consistent behavior
            signal.signal(signal.SIGINT, _handle_signal)
            logger.debug("APP: SIGTERM/SIGINT handlers installed")
        except (OSError, ValueError) as e:
            # ValueError if not main thread, OSError on Windows
            logger.debug("APP: could not install signal handlers: %s", e)

    async def _prewarm_ca(self) -> None:
        """Pre-generate CA certificate at application startup (background).

        load_or_create_ca() creates files if they don't exist — this can take 0.5-2s
        (RSA keygen). Calling here ensures the certificate is ready by the time
        Start Proxy is pressed and proxy.start() doesn't slow down.
        """
        loop = asyncio.get_running_loop()
        try:
            from pentool.utils.cert import load_or_create_ca

            # Run synchronous generation in executor to avoid blocking TUI
            cert_dir = self._cfg.cert_dir
            await loop.run_in_executor(None, load_or_create_ca, cert_dir)
            logger.info("APP: CA certificate pre-warmed from %s", cert_dir)
        except Exception as exc:
            logger.warning("APP: CA pre-warm failed: %s", exc)

    # Note: _proxy_main, _stop_proxy, _stop_proxy_async now live in
    # ProxyRuntimeMixin (tui/mixins/proxy_runtime.py).

    # Sprint 3: _on_proxy_request and _proxy_request_done_cb removed — proxy emits via EventBus,
    # app subscribes to ProxyRequestCaptured / ProxyRequestCompleted → _on_bus_proxy_captured/completed

    _SCREEN_RESOLVE_INTERVAL = 2.0

    def _get_proxy_screen(self):
        """Cached #screen-proxy; re-resolves every interval. Returns None when
        the screen isn't mounted — callers treat None as a quiet no-op."""
        return self._get_cached_screen(SCREEN_PROXY, ProxyScreen, "_proxy_screen")

    def _get_target_screen(self):
        """Cached #screen-target; re-resolves every interval. None = not mounted."""
        return self._get_cached_screen(SCREEN_TARGET, TargetScreen, "_target_screen")

    def _get_cached_screen(self, selector: str, cls, cache_attr: str):
        _ts_attr = f"_screen_resolve_{cache_attr}"
        _last = getattr(self, _ts_attr, 0.0)
        now = time.monotonic()
        # Cache hit within the interval → reuse without re-querying.
        if now - _last < self._SCREEN_RESOLVE_INTERVAL:
            return getattr(self, cache_attr)
        setattr(self, _ts_attr, now)
        try:
            screen = self.query_one(selector, cls)
        except NoMatches:
            # Screen not mounted (other tab / being torn down). Cache None so we
            # DON'T re-hunt on every request — this is the anti-spam that stops
            # the per-request query_one→NoMatches→log loop under load.
            setattr(self, cache_attr, None)
            return None
        setattr(self, cache_attr, screen)
        return screen

    @on(ProxyRequestAdded)
    def on_proxy_request_added(self, msg: ProxyRequestAdded) -> None:
        """Proxy captured a new request → update ProxyScreen.

        NOTE: must stay in the App class (not a mixin) — Textual only
        introspects the direct App class for `@on(...)` handlers and would
        silently skip a mixin MRO handler, breaking live history rows.
        """
        if not (self._proxy and self._proxy.is_running):
            return
        try:
            screen = self._get_proxy_screen()
            if screen is None:
                return  # quiet no-op — screen not mounted; do NOT log each call
            screen.add_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:
                screen.show_intercepted_request(msg.req)  # type: ignore[arg-type]
        except NoMatches as e:
            # Вкладки Intercept нет в дереве — экран ещё собирается. Это
            # ожидаемое состояние, и оно обязано остаться тихим: запись на
            # каждый запрос прокси утопила бы журнал.
            logger.debug("on_proxy_request_added: panel not mounted: %s", e)
        except Exception:
            # Всё остальное здесь — дефект: запрос не появился в истории,
            # хотя прокси его поймал. Трейсбек нужен, и нужен именно на
            # каждый запрос — сломанный путь строки и есть весь трафик.
            logger.exception("on_proxy_request_added: row not added")

    @on(ProxyRequestDone)
    def on_proxy_request_done(self, msg: ProxyRequestDone) -> None:
        """Proxy completed a request/response cycle → update the row and SiteMap."""
        # Remove from pending — the next request with this id will pass through again
        req_id = getattr(msg.req, "id", None)
        with self._pending_done_lock:
            self._pending_done_ids.discard(req_id)
        # Guard: msg.req must be InterceptedRequest
        if not isinstance(msg.req, _IR):
            logger.warning("on_proxy_request_done: msg.req is %s, skipping", type(msg.req))
            return
        try:
            screen = self._get_proxy_screen()
            if screen is None:
                return  # quiet no-op — screen not mounted; do NOT log each call
            screen.update_request_row(msg.req)
            if self._proxy and self._proxy.intercept_enabled:
                screen.show_intercept_response(msg.req)  # type: ignore[arg-type]
        except NoMatches as e:
            # Панели ответа нет в дереве — экран ещё собирается; тихо, как и
            # для нового запроса выше.
            logger.debug("on_proxy_request_done: panel not mounted: %s", e)
        except Exception:
            # Строка осталась без статуса и ответа: в истории видно «—»
            # вместо кода, и других следов сбоя нет.
            logger.exception("on_proxy_request_done: row not updated")
        # Auto-build SiteMap
        self.post_message(SendToTarget(msg.req))

    @on(SendToTarget)
    def on_send_to_target(self, msg: SendToTarget) -> None:
        try:
            target = self._get_target_screen()
            if target is None:
                return  # quiet no-op — Target screen not mounted; do NOT log each call
            target.add_request_from_proxy(msg.req)
        except NoMatches as e:
            # Дерево Target ещё не смонтировано — тихо, как и выше.
            logger.debug("on_send_to_target: tree not mounted: %s", e)
        except Exception:
            # Запрос не попал в дерево сайта: пользователь видит пустой
            # Target при живом трафике в Proxy, и другого следа нет.
            logger.exception("on_send_to_target: request not added to sitemap")

    def _add_raw_to_target(self, raw: str) -> None:
        try:
            from pentool.utils.parser import parse_http_request

            req = parse_http_request(raw)
            target = self._get_target_screen()
            if target is None:
                return
            target.add_request_from_proxy(req)
        except NoMatches as e:
            logger.debug("_add_raw_to_target: tree not mounted: %s", e)
        except Exception:
            # Сырой запрос не разобран или не лёг в SiteMap: экран Target
            # отстаёт от того, что реально отправлено.
            logger.exception("_add_raw_to_target: raw request not added")

    @on(SendToRepeater)
    def on_send_to_repeater(self, msg: SendToRepeater) -> None:
        try:
            repeater = self.query_one(SCREEN_REPEATER, RepeaterScreen)
            repeater.load_request_in_new_tab(msg.raw)
            self.action_switch_module("repeater")
            self.call_after_refresh(self._focus_repeater_editor, repeater)
            self.notify("→ Repeater", severity="information")
            self._add_raw_to_target(msg.raw)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Send to Repeater", self, severity="error")

    @on(SendToIntruder)
    def on_send_to_intruder(self, msg: SendToIntruder) -> None:
        try:
            intruder = self.query_one(SCREEN_INTRUDER, IntruderScreen)
            intruder.load_request(msg.raw)
            self.action_switch_module("intruder")
            self.notify("Sent to Intruder", severity="information", timeout=2)
            self._add_raw_to_target(msg.raw)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Send to Intruder", self, severity="error")

    @on(SyncScopeToTarget)
    def on_sync_scope_to_target(self, msg: SyncScopeToTarget) -> None:
        try:
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            api = target._get_api()
            api.sitemap.set_in_scope(msg.host, msg.in_scope)
            # Rebuild the tree from the in-memory sitemap only — NOT
            # target._load_sitemap(), which does a full api.load() from
            # the DB. The sitemap is persisted in batches of 20 rows
            # (see target/screen.py _do_save_sitemap), so any host/path
            # added in-memory since the last batch save would be wiped
            # out by that reload, making a simple "Add to Scope" click
            # from Proxy appear to clear the whole Target tree.
            target._refresh_tree()
            # Persist the scope change right away — without this, the
            # in-memory-only mutation above can be silently discarded by a
            # later full api.load() from the DB (e.g. on project import),
            # making the scope change from Proxy appear to have never
            # happened once the project is reloaded.
            self.run_worker(api.save(), exclusive=False)
        except NoMatches as e:
            # Экрана Target нет в дереве (проект только открывается) — scope
            # из Proxy всё равно лёг в ProxyServer, терять нечего.
            logger.debug("on_sync_scope_to_target: screen not mounted: %s", e)
        except Exception:
            # Переключение Scope из Proxy не доехало до дерева Target:
            # пользователь видит, что галка не сработала, и второй попытки
            # у этого клика нет.
            logger.exception("on_sync_scope_to_target: scope not applied to sitemap")

    @on(SyncScopeToProxy)
    def on_sync_scope_to_proxy(self, msg: SyncScopeToProxy) -> None:
        """Mirror a scope change made in TargetScreen into ProxyServer.scope.

        Symmetric counterpart of on_sync_scope_to_target — without this,
        adding/removing a host to scope from the Target module never
        reached ProxyServer.scope (one-way sync bug).
        """
        try:
            proxy = self._proxy
            if proxy is None:
                return
            scope = list(proxy.scope)
            if msg.in_scope:
                if msg.host not in scope:
                    scope.append(msg.host)
                    proxy.set_scope(scope)
            else:
                if msg.host in scope:
                    scope.remove(msg.host)
                    proxy.set_scope(scope)
            # Keep Config.scope (persisted on disk) in sync too
            try:
                self._cfg.scope = list(proxy.scope)
                self._cfg.save()
            except OSError as e:
                # Диск недоступен или config.yaml не записался: в памяти scope
                # новый, а на диске — старый, и следующий старт его вернёт.
                logger.warning("on_sync_scope_to_proxy: failed to save config: %s", e)
            # Persist per-project (DB) too — otherwise a scope change made
            # from Target only lived in Config (global) and proxy.scope
            # (in-memory), and got silently overwritten by whatever the
            # project's own project_settings row said on the next project
            # switch (see ProxyScreen._load_scope_setting).
            try:
                proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                self.run_worker(proxy_screen._save_scope_setting(list(proxy.scope)))
            except NoMatches as e:
                # Экрана Proxy нет в дереве — сохранение в проект пропущено;
                # при следующем переключении проекта вернётся старая настройка.
                logger.debug("on_sync_scope_to_proxy: failed to persist scope per-project: %s", e)
            # Refresh Proxy screen's ScopeToggle state if mounted
            try:
                from pentool.tui.widgets.proxy_filter_bar import ProxyFilterBar
                from pentool.tui.widgets.toolbar_button import ToolbarButton

                proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                st = proxy_screen.query_one("#filter-bar", ProxyFilterBar).query_one("#fb-scope", ToolbarButton)
                if not bool(proxy.scope):
                    st.add_class("disabled")
                else:
                    st.remove_class("disabled")
            except NoMatches as exc:
                # Кнопка Scope на экране Proxy останется в прежнем состоянии —
                # то есть покажет ровно противоположное тому, что сохранено.
                # `NoMatches` здесь — либо экран, либо фильтр-бар, либо сама
                # кнопка ещё не в дереве; других причин у этой цепочки нет.
                logger.debug("on_sync_scope_to_proxy: scope toggle not refreshed: %s", exc)
        except NoMatches as e:
            # Сюда попадает только `self.query_one(SCREEN_PROXY, ...)` выше —
            # экрана Proxy нет, синхронизировать нечего.
            logger.debug("on_sync_scope_to_proxy: proxy screen not mounted: %s", e)
        except Exception:
            # Scope обновлён в одном месте и не обновлён в другом: Target и
            # Proxy начнут расходиться, а это ровно тот односторонний баг,
            # ради которого этот хендлер и написан.
            logger.exception("on_sync_scope_to_proxy: scope not mirrored")

    @on(SendHostToScanner)
    def on_send_host_to_scanner(self, msg: SendHostToScanner) -> None:
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen

            scanner = self.query_one(SCREEN_SCANNER, ScannerScreen)
            host = msg.host
            url = f"https://{host}" if not host.startswith("http") else host
            # Pass url directly to action_new_tab — it will store in state.pending_target
            # and apply in _fill_settings when Input is already mounted
            scanner.action_new_tab(initial_url=url)
            self.action_switch_module("scanner")
            self.notify(f"✓ {host} → Scanner (new tab, F5 to start)", timeout=3)
            logger.info("SendHostToScanner: host=%s url=%s", host, url)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "SendHostToScanner", self, severity="error")

    @on(SendToScanner)
    def on_send_to_scanner(self, msg: SendToScanner) -> None:
        try:
            from pentool.tui.screens.scanner.screen import ScannerScreen

            scanner = self.query_one(SCREEN_SCANNER, ScannerScreen)
            # Each "Send to Scanner" opens a new tab so as not to overwrite
            # data from an already running scan (bug: old findings were loaded).
            first_url = msg.urls.splitlines()[0].strip() if msg.urls.strip() else msg.urls
            scanner.action_new_tab(initial_url=first_url)
            self.action_switch_module("scanner")
            count = len(msg.urls.splitlines())
            self.notify(f"Sent {count} URL(s) to Scanner (new tab)", severity="information", timeout=2)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Send to Scanner", self, severity="error")

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
            from pentool.core.error_guard import err

            err(exc, "SendRequestToScanner", self, severity="error")

    @on(SendUrlToTarget)
    def on_send_url_to_target(self, msg: SendUrlToTarget) -> None:
        try:
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target.add_request_from_proxy(msg.req)
        except NoMatches as e:
            # Экрана Target нет в дереве: URL из --url не виден, но проект и
            # прокси уже созданы — при монтировании дерево соберётся из БД.
            logger.debug("on_send_url_to_target: screen not mounted: %s", e)
        except Exception:
            # URL из --url не попал в дерево сайта вовсе.
            logger.exception("on_send_url_to_target: url not added")

    @on(ProxyClearHistory)
    def on_proxy_clear_history(self, msg: ProxyClearHistory) -> None:
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.action_clear_list()
        except NoMatches as e:
            # Экрана Proxy нет в дереве — чистить нечего.
            logger.debug("on_proxy_clear_history: screen not mounted: %s", e)
        except Exception:
            # Пользователь нажал «очистить» и ждёт пустую таблицу, а строки
            # остаются: выглядит как «кнопка не работает».
            logger.exception("on_proxy_clear_history: list not cleared")

    @on(ProxyLoadProject)
    def on_proxy_load_project(self, msg: ProxyLoadProject) -> None:
        """Reload the ProxyScreen table after loading a project."""
        try:
            screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            screen.load_from_project()
        except NoMatches as e:
            # Экрана Proxy нет в дереве — загружать нечего, таблица соберётся
            # при его монтировании.
            logger.debug("on_proxy_load_project: screen not mounted: %s", e)
        except Exception:
            # Таблица осталась от прошлого проекта: открытый проект и то, что
            # показывает Proxy, — разные базы.
            logger.exception("on_proxy_load_project: table not reloaded")

    @on(ConfigChanged)
    def on_config_changed(self, msg: ConfigChanged) -> None:
        """Apply config changes to ProxyServer and StatusBar (R-16).

        Called when SettingsScreen saves settings via cfg.update().
        ProxyServer updates port/host — but does not restart automatically,
        the user must restart the proxy manually.
        """
        fields = msg.fields
        if not isinstance(fields, dict):
            logger.warning("APP: on_config_changed: unexpected fields type %s", type(fields))
            return
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
                severity="information",
                timeout=4,
            )
        # Apply theme if changed (skip if already the correct theme — avoids
        # double-render when SettingsScreen sets self.app.theme directly and then
        # also saves to config which fires this observer).
        if "theme" in fields:
            try:
                new_theme = fields["theme"]
                if getattr(self, "theme", None) != new_theme:
                    self.theme = new_theme
            except InvalidThemeError as exc:
                # Пользователь только что сохранил тему и ждёт, что она
                # применится; отказ Textual принять имя темы иначе не заметен.
                logger.debug("config: theme %r not applied: %s", fields.get("theme"), exc)
        # Restart the auto-save timer if the relevant fields have changed.
        # Use call_after_refresh so the current message-dispatch cycle finishes
        # before we touch the timer (avoids a race where stop() is called on a
        # timer that is still mid-fire).
        if "auto_save_enabled" in fields or "auto_save_interval" in fields:
            self.call_after_refresh(self._setup_auto_save)
        # Global AI master-switch (Settings → AI): when toggled, start the MCP
        # server (or stop it) and show/hide AI-dependent UI across modules.
        # start_ai/stop_ai are async and run as workers so the TUI stays live.
        if "ai_enabled" in fields:
            self._sync_ai_global()

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
        except Exception as exc:
            # Прокси уже запущен/остановлен; на дашборде об этом останется
            # прошлое состояние — самый заметный из «залипших» индикаторов.
            logger.debug("dashboard proxy status not updated: %s", exc)

    def _sync_ai_global(self) -> None:
        """Управляет MCP сервером + публикует AiModeChanged EventBus.

        Каждый модуль сам подписывается на событие и скрывает/показывает
        свои AI-элементы (Intruder, Scanner, Target, Dashboard).
        """
        ai_on = bool(getattr(self._cfg, "ai_enabled", False))

        # 1. MCP сервер — старт/стоп
        from pentool.services.ai.factory import is_ai_running as _is_ai_running

        if ai_on and not _is_ai_running():
            from pentool.services.ai.factory import start_ai as _start_ai

            self.run_worker(_start_ai(self._cfg))
        elif not ai_on and _is_ai_running():
            from pentool.services.ai.factory import stop_ai as _stop_ai

            self.run_worker(_stop_ai())

        # 2. Оповестить все модули через EventBus
        from pentool.core.event_bus import get_event_bus
        from pentool.core.events import AiModeChanged

        get_event_bus().emit(AiModeChanged(enabled=ai_on))

    def _start_ai_if_enabled(self) -> None:
        """On app startup: start the MCP server if the global AI switch is on."""
        self._sync_ai_global()

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
        """Switch to the settings screen."""
        self.action_switch_module("settings")

    def action_about(self) -> None:
        self.notify("PenTool — Faster. Smarter. Better.", timeout=3)

    def action_toggle_theme(self) -> None:
        self.run_worker(self.run_action("toggle_dark"), exclusive=False)

    def action_new_project(self) -> None:
        self._pm.new_project()

    def action_open_project(self) -> None:
        self._pm.open_project()

    def action_save_project(self) -> None:
        self._pm.save_project()

    def action_save_project_json(self) -> None:
        self._pm.save_project_json()

    def action_open_project_json(self) -> None:
        self._pm.open_project_json()

    def _switch_project_db(self, path: str, is_new: bool = False) -> None:
        self._pm.switch_project_db(path, is_new)

    def _update_project_name(self, path: str, saved: bool = True) -> None:
        self._pm.update_project_name(path, saved)

    # ── Helpers kept in app.py (used by other app-level methods) ──────────────

    def _do_save_project_json(self, path: str) -> None:
        self._pm._do_save_json(path)

    def _do_load_project_json(self, path: str) -> None:
        self._pm._do_load_json(path)

    def _collect_spider_sessions(self) -> dict:
        return self._pm._collect_spider_sessions()

    async def _reload_project_screens(self, path: str) -> None:
        await self._pm._reload_project_screens(path)

    async def _init_new_db(self, path: str) -> None:
        await self._pm._init_new_db(path)

    async def _switch_storage_db(self, path: str) -> None:
        await self._pm._switch_storage_db(path)

    async def _open_project_sequence(self, path: str) -> None:
        await self._pm._open_project_sequence(path)

    # ── EventBus handlers ──────────────────────────────────────────────────────
    # All handlers are called from the main event loop (via emit or
    # emit_threadsafe → call_soon_threadsafe), so query_one is safe.

    def _on_bus_finding_discovered(self, event: FindingDiscovered) -> None:
        """Finding from active or passive scanner → Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.add_finding(event.finding)
        except Exception as exc:
            # Dashboard есть всегда, поэтому отказ здесь — не «ещё не собран»,
            # а настоящая потеря: находка не попала в ленту.
            logger.debug("bus: finding not shown on Dashboard: %s", exc)

    def _on_bus_scan_started(self, event: ScanStarted) -> None:
        """Scan started → update status on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(True, 0)
        except Exception as exc:
            logger.debug("bus: scan-started status not shown: %s", exc)

    def _on_bus_scan_finished(self, event: ScanFinished) -> None:
        """Scan finished → reset status on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(False, 100)
        except Exception as exc:
            # Скан кончился, а индикатор продолжает идти — самый заметный из
            # симптомов этого класса ошибок.
            logger.debug("bus: scan-finished status not shown: %s", exc)

    def _on_bus_scan_progress(self, event: ScanProgressEvent) -> None:
        """Scan progress → Dashboard (optional, for live updates)."""
        # Not used yet — Dashboard updates via ScanStarted/ScanFinished.

    def _on_bus_passive_toggled(self, event: PassiveScanToggled) -> None:
        """Passive scan enabled/disabled — update LED on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_passive_status(event.enabled)
        except Exception as exc:
            logger.debug("bus: passive LED not updated: %s", exc)

    async def _on_exit_app(self) -> None:
        """Log exit reason (Textual run() returns silently on non-action_quit exits)."""
        import asyncio
        import traceback

        try:
            quitting = bool(getattr(self, "_is_quitting", False))
            screen = getattr(self, "screen", None)
            screen_id = getattr(screen, "id", None) if screen is not None else None
            task = asyncio.current_task()
            logger.info(
                "APP: run() exiting — quitting=%s active_screen=%r current_task=%r app_running=%s",
                quitting,
                screen_id,
                task.name if task else None,
                getattr(self, "is_running", False),
            )
            logger.info("APP: exit stack:\n%s", "".join(traceback.format_stack()))
        except Exception as exc:
            # Диагностика выхода сама по себе может упасть (экран уже снят) —
            # это не повод падать на выходе, но повод оставить след.
            logger.debug("APP: exit diagnostics failed: %s", exc)
        # Config is a process-wide singleton: an observer left behind keeps this
        # App (and its whole widget tree) alive for the life of the process and
        # fires on a torn-down app on the next launch (REPORT F-046).
        try:
            self._cfg.remove_observer(self._cfg_observer_cb)
        except Exception as exc:
            # Именно этот отказ и оставляет утечку F-046: следующий запуск
            # получит наблюдателя от мёртвого App.
            logger.debug("APP: config observer not removed on exit: %s", exc)
        await super()._on_exit_app()

    async def _close_all_storages(self) -> None:
        """Close all persistent SQLite connections and stop background workers.

        Called from action_quit() — consolidates the per-storage cleanup that
        used to be inline (4 repeated try/except/log blocks).
        """
        # ProxyService (HttpStorage)
        try:
            if self._proxy_service is not None:
                await self._proxy_service.close()
                logger.info("APP: HttpStorage closed on quit")
        except Exception as e:
            logger.warning("APP: HttpStorage close error on quit: %s", e)

        # Per-screen storages: Intruder, Target, Repeater
        _storage_screens: list[tuple[str, type, str, str]] = [
            (SCREEN_INTRUDER, IntruderScreen, "_api", "Intruder"),
            (SCREEN_TARGET, TargetScreen, "_target_api", "Target"),
            (SCREEN_REPEATER, RepeaterScreen, "_repeater_api", "Repeater"),
        ]
        for selector, cls, api_attr, name in _storage_screens:
            try:
                screen = self.query_one(selector, cls)
                if hasattr(screen, "_cancel_save_workers"):
                    screen._cancel_save_workers()
                api = getattr(screen, api_attr, None)
                if api is not None:
                    await api.close()
                    logger.info("APP: %s storage closed on quit", name)
            except Exception as e:
                logger.warning("APP: %s storage close error on quit: %s", name, e)

        # Spider CPU pool
        # Spider CPU pool
        try:
            from pentool.api.spider_api import shutdown_spider_pool

            shutdown_spider_pool()
        except Exception as exc:
            # Пул не погашен — процесс завершится ниже через os._exit, так что
            # это безопасно; но если однажды уберут жёсткий выход, след
            # понадобится.
            logger.debug("APP: spider pool not shut down: %s", exc)

        # AI MCP server
        try:
            from pentool.services.ai.factory import stop_ai

            await stop_ai()
        except Exception as exc:
            # MCP-процесс, переживший TUI, остаётся сиротой на порту.
            logger.debug("APP: AI MCP server not stopped: %s", exc)

    async def action_quit(self) -> None:
        # Deliberate quit underway — _on_exit_app logs it as such instead of as
        # an unexplained teardown.
        self._is_quitting = True
        # Unsubscribe from EventBus before exiting
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
            # Не отписались — мёртвый App продолжит получать события шины.
            # Процесс всё равно завершается жёстко, но след нужен, и целиком:
            # по строке не понять, какая из семи подписок не снялась.
            logger.exception("APP: EventBus unsubscribe on quit failed")
        # Stop proxy — reuse the same robust path as manual stop, but the
        # async variant so Ctrl+Q does NOT freeze the TUI renderer, and with
        # short grace windows (proxy.stop cancels tasks fast; the 8080 port is
        # released by the process exit anyway). Shutdown now takes ~1-2s even
        # with a busy proxy instead of the old ~11s (6s stop + 5s join).
        if self._proxy and self._proxy.is_running:
            await self._stop_proxy_async()
        # Close all storages in one consolidated call
        await self._close_all_storages()
        self.exit()
        # Force-terminate the process — kills non-daemon threads
        # (jemalloc_bg_thd from pyarrow) that would otherwise block exit.
        # call_later gives Textual ~100ms for final screen cleanup.
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(0.1, os._exit, 0)
        except RuntimeError:
            os._exit(0)
