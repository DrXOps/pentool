"""Main Pentool TUI application built on Textual."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Checkbox, ContentSwitcher, Footer

# Nicer checkbox glyph applied project-wide — Checkbox is a subclass of
# ToggleButton, whose BUTTON_LEFT/INNER/RIGHT class attributes control the
# rendered glyph. Overriding them here (once, at import time) changes every
# Checkbox instance across all screens without touching each screen's CSS —
# previously every screen used Textual's default "▐X▌" look, which several
# screens then had to fight with ad-hoc height/margin overrides.
Checkbox.BUTTON_LEFT = "["
Checkbox.BUTTON_INNER = "✓"
Checkbox.BUTTON_RIGHT = "]"

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
from pentool.services.proxy_service import ProxyService
from pentool.tui.constants import (
    SCREEN_DASHBOARD,
    SCREEN_INTRUDER,
    SCREEN_PROXY,
    SCREEN_REPEATER,
    SCREEN_SCANNER,
    SCREEN_TARGET,
    SCREEN_TERMINAL,
)
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
    TerminalStop,
)
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
    TerminalScreen,
)
from pentool.tui.widgets.module_tabs import ModuleTabs
from pentool.tui.widgets.notification_center import NotificationCenter
from pentool.tui.widgets.statusbar import StatusBar

logger = get_logger(__name__)

# Mapping module_id → widget class
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
    "extensions": ExtensionsScreen,
    "terminal":   TerminalScreen,
    "settings":   SettingsScreen,
}

class PentoolApp(App):
    """Main Pentool TUI application."""

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

    /* Global hotkey hint bar */
    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        color: $text-muted;
        dock: bottom;
    }

    /* Wrapper around Footer + StatusBar — see compose()'s comment for why
       this exists: two independently-docked bottom widgets overlap rather
       than stack, so both are laid out normally inside one docked container
       instead. Height 2 = Footer's 1 + StatusBar's 1.

       Both Footer (in its own DEFAULT_CSS) and StatusBar (in statusbar.tcss)
       hard-code `dock: bottom` themselves — just nesting them inside this
       wrapper is not enough, they'd still each dock to the bottom of the
       wrapper and overlap each other exactly as before. Both docks must be
       explicitly cancelled here so they lay out normally (stacked, one
       above the other) inside #bottom-dock instead. */
    #bottom-dock {
        dock: bottom;
        height: 2;
        layout: vertical;
    }
    #bottom-dock Footer {
        dock: none;
        height: 1;
    }
    #bottom-dock StatusBar {
        dock: none;
        height: 1;
    }

    /* Global checkbox style — compact, height 1, no border.
       Glyph itself ("[ ]" / "[✓]") is set once in Checkbox.BUTTON_LEFT/
       INNER/RIGHT above; this just controls color/spacing/hover so every
       screen gets the same look without per-screen overrides. */
    Checkbox {
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
        width: auto;
    }
    Checkbox > .toggle--button {
        color: $text-muted;
        background: transparent;
        text-style: bold;
    }
    Checkbox.-on > .toggle--button {
        color: $success;
        background: transparent;
        text-style: bold;
    }
    Checkbox:hover > .toggle--button {
        color: $primary;
    }
    Checkbox.-on:hover > .toggle--button {
        color: $success;
        text-style: bold;
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
        # JSON project (full export of all modules)
        Binding("ctrl+shift+s", "save_project_json", "Save JSON", show=False, priority=True),
        Binding("ctrl+shift+o", "open_project_json", "Open JSON", show=False, priority=True),
        Binding("ctrl+comma", "switch_module('settings')", "Settings", show=False, priority=True),
        # Navigation: Shift+letter (works in all terminals)
        Binding("H", "switch_module('dashboard')",  "Dashboard",  show=False, priority=True),
        Binding("P", "switch_module('proxy')",      "Proxy",      show=False, priority=True),
        Binding("R", "switch_module('repeater')",   "Repeater",   show=False, priority=True),
        Binding("I", "switch_module('intruder')",   "Intruder",   show=False, priority=True),
        Binding("S", "switch_module('scanner')",    "Scanner",    show=False, priority=True),
        Binding("T", "switch_module('target')",     "Target",     show=False, priority=True),
        Binding("D", "switch_module('decoder')",    "Decoder",    show=False, priority=True),
        Binding("C", "switch_module('comparer')",   "Comparer",   show=False, priority=True),
        Binding("Q", "switch_module('sequencer')",  "Sequencer",  show=False, priority=True),
        Binding("E", "switch_module('extensions')", "Extensions", show=False, priority=True),
        Binding("X", "switch_module('terminal')",   "Terminal",   show=False, priority=True),
        # Shift+digit aliases for compatibility
        Binding("exclamation_mark",   "switch_module('proxy')",      show=False, priority=True),
        Binding("at",                 "switch_module('repeater')",   show=False, priority=True),
        Binding("number_sign",        "switch_module('intruder')",   show=False, priority=True),
        Binding("dollar_sign",        "switch_module('scanner')",    show=False, priority=True),
        Binding("percent_sign",       "switch_module('decoder')",    show=False, priority=True),
        Binding("circumflex_accent",  "switch_module('comparer')",   show=False, priority=True),
        Binding("ampersand",          "switch_module('sequencer')",  show=False, priority=True),
        Binding("left_parenthesis",   "switch_module('extensions')", show=False, priority=True),
        # Proxy sub-tabs: use Ctrl+H/I/W for Proxy HTTP/Intercept/WS
        Binding("ctrl+h", "proxy_tab('http')",      "HTTP History", show=False, priority=True),
        Binding("ctrl+i", "proxy_tab('intercept')", "Intercept",    show=False, priority=True),
        Binding("ctrl+w", "proxy_tab('ws')",        "WS History",   show=False, priority=True),
        # Repeater send — ctrl+space arrives as ctrl-at (NUL/^@) in most terminals
        # Handled at App level with priority so it fires regardless of focus depth
        Binding("ctrl-at",    "repeater_send", "Send", show=False, priority=True),
        Binding("ctrl+space", "repeater_send", "Send", show=False, priority=True),
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
        self._project_loaded: bool = False  # Flag: project created or opened
        self._skip_project_guard: bool = False  # True in tests to bypass the guard
        # Protection against message storm: set of pending req_ids for deduplication
        self._pending_done_ids: set[str] = set()
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

    def _handle_exception(self, error: Exception) -> None:
        """Catch fatal exceptions — log before passing to Textual."""
        import traceback
        logger.error(
            "FATAL EXCEPTION: %s\n%s",
            error,
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        )
        super()._handle_exception(error)

    def compose(self) -> ComposeResult:
        yield ModuleTabs(id="module-tabs")
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
            yield ExtensionsScreen(id="screen-extensions")
            yield TerminalScreen(id="screen-terminal")
            yield SettingsScreen(id="screen-settings")
        # Footer and StatusBar both used to `dock: bottom` independently —
        # in Textual, multiple independently-docked widgets at the same
        # edge don't stack, they all pin to the same row and overlap each
        # other (whichever was composed last wins the pixels). That's why
        # StatusBar (and, inside it, the new ActivityIndicator) never
        # rendered — Footer, composed after it, was drawn on top and
        # covered it completely. Wrapping both in one docked container
        # lets them lay out normally (one above the other) inside it.
        with Vertical(id="bottom-dock"):
            yield Footer()
            yield StatusBar(id="statusbar")
        yield NotificationCenter(id="notification-center")

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
        # Sync scope from config into ProxyServer
        if self._cfg.scope:
            self._proxy.scope = list(self._cfg.scope)
            logger.info("APP: scope loaded from config: %s", self._cfg.scope)

        # Inject ProxyServer into the API layer
        self._proxy_api.set_proxy(self._proxy)

        # Create ProxyService and pass it to ProxyScreen — before init_storage
        self._proxy_service = ProxyService(
            proxy_api=self._proxy_api,
            db_path=self._cfg.db_path,
            event_bus=get_event_bus(),
            on_storage_error=self._on_storage_error,
        )
        try:
            from pentool.tui.screens.proxy.screen import ProxyScreen
            proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
            proxy_screen._proxy_service = self._proxy_service
            # Run init_storage synchronously and WAIT for it to complete
            # before auto-opening last project (which calls switch_db)
            await self._proxy_service.init_storage()
            logger.info("APP: ProxyService injected and init_storage completed")
        except Exception as exc:
            logger.warning("APP: could not inject ProxyService into ProxyScreen: %s", exc)

        # Initialize global Event Bus and subscribe app-level handlers
        bus = get_event_bus()
        bus.subscribe(FindingDiscovered,     self._on_bus_finding_discovered)
        bus.subscribe(ScanStarted,           self._on_bus_scan_started)
        bus.subscribe(ScanFinished,          self._on_bus_scan_finished)
        bus.subscribe(ScanProgressEvent,     self._on_bus_scan_progress)
        bus.subscribe(PassiveScanToggled,    self._on_bus_passive_toggled)
        # Sprint 3: subscribe to proxy events via EventBus
        # (proxy emits from its own thread, we bridge via call_from_thread)
        bus.subscribe(ProxyRequestCaptured,  self._on_bus_proxy_captured)
        bus.subscribe(ProxyRequestCompleted, self._on_bus_proxy_completed)
        logger.info("APP: EventBus subscribed")

        self._update_status()
        logger.info("Pentool TUI started")

        # Pre-generate CA certificate in background — so that by the time
        # "Start Proxy" is pressed it is already ready and doesn't slow startup (option C)
        self.run_worker(self._prewarm_ca(), exclusive=False, thread=False)

        # Allow jemalloc (pyarrow) to release the background thread immediately,
        # otherwise it is non-daemon and blocks process exit
        try:
            import pyarrow as pa
            pa.jemalloc_set_decay_ms(0)
        except Exception:
            pass

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
        except Exception:
            pass

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
        else:
            # Auto-open last project at startup (no arguments)
            self.run_worker(self._auto_open_last_project(), exclusive=False, thread=False)

        # Check for updates in background (if enabled in settings)
        if getattr(self._cfg, "check_updates", True):
            self.run_worker(self._check_for_updates(), exclusive=False, thread=False)

        # Check for a newer PRO build in background (if a PRO license is
        # active) — closes the gap where pentool-pro ships a fix but an
        # already-activated machine keeps running the stale code forever,
        # since the PRO package otherwise only downloads once, at activation.
        self.run_worker(self._check_for_pro_update(), exclusive=False, thread=False)

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
        """Seed targets passed via `pentool --url ...` (launch-TUI branch).

        Starts the proxy (CA cert is pre-warmed on mount) and populates the
        Target / Site Map with each URL, so the user lands on a NEW project for
        the target (rather than the last-used project). Headless-browser import
        + issuing the first request is part of the interactive auto-setup
        feature (roadmap) — see docs/i18n/en/CI_CD.md.
        """
        await asyncio.sleep(0.6)  # let the TUI render first

        # Create a NEW project for this target (do not reuse the last project).
        try:
            new_path = self._project_path_for_target(urls[0])
            self._pm.switch_project_db(new_path, is_new=True)
        except Exception as exc:
            logger.warning("seed: new project create failed: %s", exc)

        for url in urls:
            try:
                from pentool.utils.parser import ParsedRequest
                self.post_message(SendUrlToTarget(ParsedRequest(method="GET", url=url)))
            except Exception as exc:
                logger.debug("seed url %s: %s", url, exc)

        real = bool(getattr(self, "_pending_start_real", False))

        # Start the proxy so --real traffic (and subsequent manual use) can be
        # intercepted and land in the project.
        proxy_started = False
        try:
            if not (self._proxy and self._proxy.is_running):
                self._start_proxy()
                proxy_started = True
        except Exception as exc:
            logger.warning("seed: proxy start failed: %s", exc)

        logger.info("seed: --real=%s proxy_started=%s proxy_running=%s", real, proxy_started,
                    bool(self._proxy and self._proxy.is_running))
        if real:
            # Actually fetch the target(s) through the proxy so real requests
            # show up in the project (not just a dry seed entry).
            try:
                logger.info("--real: calling _do_real_fetch for %s", urls)
                await self._do_real_fetch(urls)
            except Exception as exc:
                logger.warning("seed: real fetch failed: %s", exc)
                self.notify(f"--real fetch failed: {exc}", severity="warning", timeout=6)

        self.notify(f"New project for {len(urls)} URL(s) — {'proxy on, ready to audit' if (proxy_started or (self._proxy and self._proxy.is_running)) else 'ready to audit'}.", timeout=6)

    async def _do_real_fetch(self, urls: list[str]) -> None:
        """Fetch each URL with a real headless browser THROUGH the running proxy.

        Runs Playwright/Firefox in a SEPARATE subprocess — not inside the Textual
        event loop, which can conflict with Playwright's own driver/loop and hang
        (which is why the earlier in-loop version captured nothing). The child
        process points Firefox at our proxy; ProxyServer's MITM captures the real
        request into HTTP History + Target automatically.

        Requires Playwright + a browser install in the child's Python env.
        """
        # The proxy starts async via _start_proxy — wait up to ~5s for it.
        for _ in range(50):
            if self._proxy and self._proxy.is_running:
                break
            await asyncio.sleep(0.1)
        if not (self._proxy and self._proxy.is_running):
            logger.info("--real: proxy not ready, cannot do a real browser fetch")
            return

        proxy_host = self._proxy.host or "127.0.0.1"
        proxy_port = self._proxy.port or 8080
        proxy_url = f"http://{proxy_host}:{proxy_port}"

        # Commit-ready script executed in a child process (sys.executable — the
        # same venv), so the browser runs independently of the TUI's loop.
        # Chromium + --proxy-server (reliable for proxy interception) with
        # --ignore-certificate-errors so it accepts our dynamic CA on HTTPS.
        _proxy_arg = f"--proxy-server={proxy_url}"
        _script = (
            "import asyncio,sys\n"
            "async def _run():\n"
            "    from playwright.async_api import async_playwright\n"
            "    async with async_playwright() as pw:\n"
            "        b=await pw.chromium.launch(headless=True,args=[%r,%r])\n"
            "        p=await b.new_page()\n"
            "        for u in sys.argv[1:]:\n"
            "            try:\n"
            "                await p.goto(u,timeout=30000,wait_until='domcontentloaded')\n"
            "                print('--real child visited',u,flush=True)\n"
            "            except Exception as e:\n"
            "                print('--real child visit failed',u,repr(e),flush=True)\n"
            "        await b.close()\n"
            "asyncio.run(_run())\n"
        ) % (_proxy_arg, "--ignore-certificate-errors")

        import subprocess
        try:
            # Run the browser child SYNCHRONOUSLY in an executor thread — avoids
            # the Textual event loop entirely (Playwright/Chromium + Textual's
            # loop were fighting, leaving --real frozen with no child output).
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [sys.executable, "-c", _script, *urls],
                        capture_output=True, text=True, timeout=120,
                    ),
                ),
                timeout=130,
            )
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            for line in out.splitlines():
                logger.info("--real: %s", line)
            if result.returncode != 0:
                logger.warning("--real: child exited %s: %s",
                               result.returncode, (err.splitlines()[-1] if err else ""))
                self.notify(f"--real: couldn't open real browser (exit {result.returncode})",
                            severity="warning", timeout=8)
            else:
                self.call_after_refresh(self._refresh_target_tree)
        except asyncio.TimeoutError:
            logger.warning("--real: child timed out")
            self.notify("--real: browser fetch timed out", severity="warning", timeout=6)
        except Exception as exc:
            logger.warning("--real: browser capture error: %s", exc)
            self.notify(f"--real browser error: {exc}", severity="warning", timeout=6)

    def _refresh_target_tree(self) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target._refresh_tree()
        except Exception:
            pass

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
        """Re-download the PRO package in the background if a newer build
        has been published, then notify so the user knows to restart.

        No-op (silently) if there's no active PRO license or the package was
        never downloaded in the first place. If the check/refresh couldn't
        reach the server AND the PRO package on disk is stale/version-
        mismatched, warns the user via notify() instead of staying silent —
        see pentool.core.license.check_and_update_pro_package /
        is_pro_package_compatible. (The TUI itself already refused to start
        at all in this situation — see __main__.main() — this notify only
        fires for the "was fine at startup, went stale mid-session" case,
        e.g. FREE got upgraded via a separate `pentool update` invocation
        while this TUI instance kept running.)
        """
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

    def _setup_auto_save(self) -> None:
        """Configure / restart the auto-save timer from the current config.

        Safe to call at any time — including from call_after_refresh and on_mount.
        Stops the old timer cleanly before creating a new one.
        """
        # Pause the old timer before replacing it.
        # Timer.pause() is safe to call from any point in the event loop;
        # .stop() schedules a cancellation but may race if called during a tick.
        if self._auto_save_timer is not None:
            try:
                self._auto_save_timer.pause()
                self._auto_save_timer.stop()
            except Exception:
                pass
            self._auto_save_timer = None

        if getattr(self._cfg, "auto_save_enabled", False):
            interval_min = max(1, getattr(self._cfg, "auto_save_interval", 5))
            interval_sec = interval_min * 60
            self._auto_save_timer = self.set_interval(interval_sec, self._auto_save_tick)
            logger.info("APP: auto-save enabled, interval=%d min", interval_min)
        else:
            logger.info("APP: auto-save disabled")

    def _auto_save_tick(self) -> None:
        """Periodic auto-save of the project (silent, no dialogs)."""
        if not self._project_loaded:
            return
        path = self._project_path or self._cfg.db_path
        if not path:
            return
        try:
            # SQLite DB is already in place — just show a notification
            import os as _os
            name = _os.path.basename(path)
            self.notify(f"Auto-saved: {name}", timeout=2)
            logger.info("APP: auto-saved project %s", path)
        except Exception as exc:
            logger.debug("_auto_save_tick: %s", exc)

    def _cfg_observer_cb(self, changed_fields: dict) -> None:
        """Config Observer callback — called from any context (R-16).

        Renamed away from _on_config_changed intentionally: Textual's dispatch
        looks for cls.__dict__.get('_on_<message_name>') as a fallback handler,
        so a method named _on_config_changed would be called with the ConfigChanged
        *object* (not a dict), triggering post_message(ConfigChanged(msg)) →
        infinite message loop → UI freeze with 20M log entries.
        """
        self.post_message(ConfigChanged(changed_fields))

    def on_resize(self, event) -> None:
        """Adaptive layout depending on terminal width."""
        width = event.size.width
        # Hide Inspector by default when width < 80
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
        """Focus the DataTable in the specified Proxy tab."""
        try:
            from textual_fastdatatable import DataTable
            table_ids = {
                "tab-http-history": "#request-list",
                "tab-intercept":    None,  # intercept has no table
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

    def _focus_repeater_editor(self, repeater) -> None:
        """Set focus to the RequestEditor in the active Repeater tab."""
        try:
            from textual.widgets import TextArea

            from pentool.tui.widgets.request_editor import RequestEditor
            tab_id = repeater._active_tab_id
            if tab_id:
                editor = repeater.query_one(f"#req-editor-{tab_id}", RequestEditor)
                area = editor.query_one("#editor-area", TextArea)
                area.focus()
        except Exception:
            pass

    def action_repeater_send(self) -> None:
        """Ctrl+Space / ctrl-at — send the request to Repeater regardless of focus depth."""
        if self._active_module != "repeater":
            return
        try:
            repeater = self.query_one(SCREEN_REPEATER, RepeaterScreen)
            repeater.action_send()
        except Exception:
            pass

    # Modules available without an open project
    _FREE_MODULES = {"dashboard", "settings"}

    def _refresh_scanner_tab_lock(self) -> None:
        """Lock or unlock the Scanner tab based on the current license."""
        try:
            from pentool.core.license import get_session_license
            lic = get_session_license()
            scanner_available = lic.valid and lic.has_feature("scanner_pro")
        except Exception:
            scanner_available = False
        try:
            self.query_one("#module-tabs", ModuleTabs).set_scanner_locked(not scanner_available)
        except Exception:
            pass

    def _switch_to(self, module_id: str) -> None:
        if module_id == self._active_module:
            return
        if module_id not in _SCREEN_MAP:
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
                        "🔒 Scanner — paid feature.\n"
                        "Activate: pentool license trial",
                        severity="warning",
                        timeout=5,
                    )
                    return
            except Exception:
                pass
        self.query_one(ContentSwitcher).current = f"screen-{module_id}"
        self._active_module = module_id
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

    def flash(self, message: str, severity: str = "information", timeout: float = 2.5) -> None:
        """Short message on the right side of the module bar (tooltip2)."""
        try:
            self.query_one("#module-tabs", ModuleTabs).flash(message, severity, timeout)
        except Exception:
            pass

    def notify2(
        self,
        message: str,
        severity: str = "information",
        title: str | None = None,
        timeout: float | None = None,
        sound: bool = True,
    ) -> None:
        """ICQ-style stacked toast notification (top-right corner).

        Separate from `flash()` (single-line tooltip2 in the module bar,
        kept as-is for existing lightweight status messages) and from the
        standard Textual `app.notify()` toast. Use this for events that
        deserve a more visible, dismissible, optionally-audible alert —
        e.g. a finished attack, a high-severity Scanner finding, a dropped
        connection.

        severity: "information" | "success" | "warning" | "error" | "critical"
        sound: play a short notification sound (see
            pentool.core.notification_sound) — respects the user's
            `notifications_sound_enabled` config toggle regardless of this
            argument's default.
        """
        try:
            self.query_one("#notification-center", NotificationCenter).push(
                message, severity=severity, title=title, timeout=timeout
            )
        except Exception as exc:
            logger.debug("notify2: could not show toast: %s", exc)

        if sound:
            try:
                if self._cfg.notifications_sound_enabled:
                    from pentool.core.notification_sound import play_notification_sound
                    play_notification_sound(severity)
            except Exception as exc:
                logger.debug("notify2: sound failed: %s", exc)

    def _on_storage_error(self, message: str) -> None:
        """ProxyService.init_storage()/switch_db() failed to open the DB.

        Most common cause: the project's .db file is locked by another
        process (e.g. a second Pentool instance already has it open) or the
        path is unwritable. Previously this was logged only — requests
        silently stopped being saved to history with no visible indication
        why. init_storage()/switch_db() both run on the app's own event
        loop (awaited directly, never from a worker thread), so a plain
        notify() here is safe without call_from_thread.
        """
        self.notify(
            f"{message}\n\nRequests will not be saved until this is fixed — "
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

    def action_toggle_proxy(self) -> None:
        if self._proxy is None:
            return
        if self._proxy.is_running:
            # Stop asynchronously so the TUI thread isn't frozen for up to
            # ~10s while proxy.stop() + thread join complete (the Stop button
            # currently felt slow/unresponsive on a busy proxy).
            self.run_worker(self._stop_proxy_async())
        else:
            if not self._project_loaded:
                # Project DB switch/open (auto-open at startup, New/Open
                # Project) is still finishing in the background — starting
                # the proxy now would race HttpStorage.switch_db() (its
                # connection may be mid-close/reopen) and silently lose or
                # fail to persist the first captured requests. _project_loaded
                # is set as soon as the DB switch itself completes (see
                # ProjectManager._do_switch) — the other screens may still be
                # reloading, but that's independent of Proxy.
                self.notify(
                    "Project is still opening — wait a couple of seconds before starting Proxy",
                    severity="warning",
                    timeout=4,
                )
                return
            self._start_proxy()

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

    def _start_proxy(self) -> None:
        if self._proxy is None or self._proxy.is_running:
            return
        logger.info("APP: _start_proxy: starting proxy on %s:%d", self._proxy.host, self._proxy.port)
        # Sprint 3: callbacks removed — proxy emits via EventBus,
        # app subscribes to ProxyRequestCaptured / ProxyRequestCompleted in on_mount

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

    async def _proxy_main(self) -> None:
        """Proxy entry point — runs in a separate event loop."""
        try:
            await self._proxy.start()
            self.call_from_thread(self._update_status)
            self.call_from_thread(self._update_proxy_screen_labels)
            self.call_from_thread(self._update_dashboard_proxy_status, True)
            self.call_from_thread(self.flash, f"● Proxy :{self._proxy.port}", "success")
            logger.info("Proxy started on port %s", self._proxy.port)
            async with self._proxy._server:
                await self._proxy._server.serve_forever()
        except Exception as exc:
            logger.error("Proxy error: %s", exc)
            # Surface this to the user — previously only logged, so a
            # "port already in use" / "another process holds this file"
            # failure looked like the proxy silently did nothing when the
            # toolbar button was pressed, with no clue why.
            msg = str(exc) or type(exc).__name__
            self.call_from_thread(
                self.notify,
                f"Proxy failed to start: {msg}",
                severity="error",
                timeout=6,
            )
        finally:
            self.call_from_thread(self._update_status)
            self.call_from_thread(self._update_proxy_screen_labels)
            self.call_from_thread(self._update_dashboard_proxy_status, False)
            self.call_from_thread(self.flash, "○ Proxy stopped", "warning")

    def _stop_proxy(self) -> None:
        logger.info("APP: _stop_proxy called")
        if self._proxy and self._proxy.is_running and self._proxy_loop:
            future = asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop
            )
            try:
                # stop() now cancels all active tasks and waits up to ~4s
                # internally, so 6s here is generous headroom
                future.result(timeout=6)
            except Exception as e:
                logger.warning("APP: proxy.stop() error or timeout: %s", e)
                # Force-cancel anything still running in the proxy loop so
                # the thread can exit even if stop() itself timed out
                if self._proxy_loop and not self._proxy_loop.is_closed():
                    try:
                        def _cancel_all():
                            for t in asyncio.all_tasks(self._proxy_loop):
                                t.cancel()
                        self._proxy_loop.call_soon_threadsafe(_cancel_all)
                    except Exception:
                        pass
        if self._proxy_thread and self._proxy_thread.is_alive():
            self._proxy_thread.join(timeout=5)
            if self._proxy_thread.is_alive():
                logger.warning("APP: proxy thread did not stop in 5s — port 8080 may still be in use")
        self.call_after_refresh(self._update_status)
        self.call_after_refresh(self._update_proxy_screen_labels)

    async def _stop_proxy_async(self) -> None:
        """Async stop of the proxy that does NOT block the TUI thread.

        Same robust path as `_stop_proxy()` (await proxy.stop() up to 6s,
        force-cancel tasks on timeout, join the proxy thread) but expressed
        as a coroutine. Intended to be awaited from an async worker context
        (e.g. ProjectManager._do_switch) so that switching to a new project
        does NOT freeze the UI for up to ~10s while the old proxy is being
        wound down. _stop_proxy() remains the synchronous variant used by
        the Stop button / Ctrl+Q.
        """
        logger.info("APP: _stop_proxy_async called")
        if self._proxy and self._proxy.is_running and self._proxy_loop:
            future = asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop
            )
            try:
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=6)
            except asyncio.TimeoutError:
                logger.warning("APP: proxy.stop() (async) timed out")
        # Wait (in this async context) for the proxy thread to die so the
        # 8080 port is released before the caller switches the project DB.
        loop = asyncio.get_running_loop()
        proxy_thread = self._proxy_thread
        if proxy_thread is not None:
            for _ in range(70):  # up to ~7s in 100ms steps
                alive = await loop.run_in_executor(None, proxy_thread.is_alive)
                if not alive:
                    break
                await asyncio.sleep(0.1)
            self.call_after_refresh(self._update_status)
            self.call_after_refresh(self._update_proxy_screen_labels)

    # Sprint 3: _on_proxy_request and _proxy_request_done_cb removed — proxy emits via EventBus,
    # app subscribes to ProxyRequestCaptured / ProxyRequestCompleted → _on_bus_proxy_captured/completed

    @on(ProxyRequestAdded)
    def on_proxy_request_added(self, msg: ProxyRequestAdded) -> None:
        """Proxy captured a new request → update ProxyScreen."""
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
        """Proxy completed a request/response cycle → update the row and SiteMap."""
        # Remove from pending — the next request with this id will pass through again
        req_id = getattr(msg.req, "id", None)
        self._pending_done_ids.discard(req_id)
        # Guard: msg.req must be InterceptedRequest
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
        # Auto-build SiteMap
        self.post_message(SendToTarget(msg.req))

    @on(SendToTarget)
    def on_send_to_target(self, msg: SendToTarget) -> None:
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target = self.query_one(SCREEN_TARGET, TargetScreen)
            target.add_request_from_proxy(msg.req)
        except Exception as e:
            logger.warning("on_send_to_target: failed to forward request to Target: %s", e)

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
            repeater.load_request_in_new_tab(msg.raw)
            self.action_switch_module("repeater")
            self.call_after_refresh(self._focus_repeater_editor, repeater)
            self.flash("→ Repeater", "information", 2.0)
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
        except Exception as e:
            logger.debug("on_sync_scope_to_target: %s", e)

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
            except Exception as e:
                logger.warning("on_sync_scope_to_proxy: failed to save config: %s", e)
            # Persist per-project (DB) too — otherwise a scope change made
            # from Target only lived in Config (global) and proxy.scope
            # (in-memory), and got silently overwritten by whatever the
            # project's own project_settings row said on the next project
            # switch (see ProxyScreen._load_scope_setting).
            try:
                from pentool.tui.screens.proxy.screen import ProxyScreen
                proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                self.run_worker(proxy_screen._save_scope_setting(list(proxy.scope)))
            except Exception as e:
                logger.debug("on_sync_scope_to_proxy: failed to persist scope per-project: %s", e)
            # Refresh Proxy screen's ScopeToggle state if mounted
            try:
                from pentool.tui.screens.proxy.screen import ProxyScreen
                from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
                proxy_screen = self.query_one(SCREEN_PROXY, ProxyScreen)
                st = proxy_screen.query_one("#filter-bar", FilterBar).query_one("#fb-scope", ScopeToggle)
                st.set_scope_empty(not bool(proxy.scope))
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_sync_scope_to_proxy: %s", e)

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
            logger.error("SendHostToScanner error: %s", exc, exc_info=True)
            self.notify(f"Scanner error: {exc}", severity="error", timeout=4)

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
        """Reload the ProxyScreen table after loading a project."""
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
                severity="information", timeout=4,
            )
        # Apply theme if changed (skip if already the correct theme — avoids
        # double-render when SettingsScreen sets self.app.theme directly and then
        # also saves to config which fires this observer).
        if "theme" in fields:
            try:
                new_theme = fields["theme"]
                if getattr(self, "theme", None) != new_theme:
                    self.theme = new_theme
            except Exception:
                pass
        # Restart the auto-save timer if the relevant fields have changed.
        # Use call_after_refresh so the current message-dispatch cycle finishes
        # before we touch the timer (avoids a race where stop() is called on a
        # timer that is still mid-fire).
        if "auto_save_enabled" in fields or "auto_save_interval" in fields:
            self.call_after_refresh(self._setup_auto_save)

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
        """Switch to the settings screen."""
        self.action_switch_module("settings")

    def action_about(self) -> None:
        self.notify("PenTool — Faster. Smarter. Better.", timeout=3)

    def action_toggle_theme(self) -> None:
        self.run_worker(self.run_action("toggle_dark"), exclusive=False)

    def action_new_project(self)       -> None: self._pm.new_project()
    def action_open_project(self)      -> None: self._pm.open_project()
    def action_save_project(self)      -> None: self._pm.save_project()
    def action_save_project_json(self) -> None: self._pm.save_project_json()
    def action_open_project_json(self) -> None: self._pm.open_project_json()

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
        except Exception:
            pass

    def _on_bus_scan_started(self, event: ScanStarted) -> None:
        """Scan started → update status on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(True, 0)
        except Exception:
            pass

    def _on_bus_scan_finished(self, event: ScanFinished) -> None:
        """Scan finished → reset status on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_scan_status(False, 100)
        except Exception:
            pass

    def _on_bus_scan_progress(self, event: ScanProgressEvent) -> None:
        """Scan progress → Dashboard (optional, for live updates)."""
        # Not used yet — Dashboard updates via ScanStarted/ScanFinished.

    def _on_bus_proxy_captured(self, event: ProxyRequestCaptured) -> None:
        """EventBus: proxy captured a new request.

        Bridge: proxy emit from its thread → EventBus → this method is called
        synchronously in the proxy thread → call_from_thread → Textual Message in TUI thread.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        self.call_from_thread(self.post_message, ProxyRequestAdded(req))

    def _on_bus_proxy_completed(self, event: ProxyRequestCompleted) -> None:
        """EventBus: request through proxy completed.

        Bridge: proxy emit from its thread → EventBus → call_from_thread → Textual Message.
        """
        req = event.request
        if req is None or not isinstance(req, _IR):
            return
        req_id = req.id
        # Deduplication: if already pending, ignore
        if req_id in self._pending_done_ids:
            return
        self._pending_done_ids.add(req_id)
        self.call_from_thread(self.post_message, ProxyRequestDone(req))

    def _on_bus_passive_toggled(self, event: PassiveScanToggled) -> None:
        """Passive scan enabled/disabled — update LED on Dashboard."""
        try:
            dashboard = self.query_one(SCREEN_DASHBOARD, DashboardScreen)
            dashboard.update_passive_status(event.enabled)
        except Exception:
            pass

    async def action_quit(self) -> None:
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
            pass
        # Stop terminal (shell process) via Message Bus
        self.post_message(TerminalStop())
        # Stop proxy — reuse the same robust path as manual stop (_stop_proxy):
        # it awaits proxy.stop() up to 6s, force-cancels stuck tasks on timeout,
        # and joins the proxy thread (cf. the old weak inline stop that used only
        # join(timeout=2) here, which could leave the proxy thread wound around
        # the 8080 listener after Ctrl+Q — see oszatel procesy workaround).
        if self._proxy and self._proxy.is_running:
            self._stop_proxy()
        # Close SQLite storage — flush WAL to disk
        try:
            if self._proxy_service is not None:
                await self._proxy_service.close()
                logger.info("APP: HttpStorage closed on quit")
        except Exception as e:
            logger.warning("APP: HttpStorage close error on quit: %s", e)
        # Close Intruder's persistent SQLite connection (see IntruderScreen
        # _get_api()/reload_from_project() — mirrors HttpStorage above).
        try:
            from pentool.tui.screens.intruder.screen import IntruderScreen
            intruder_screen = self.query_one(SCREEN_INTRUDER, IntruderScreen)
            if intruder_screen._api is not None:
                await intruder_screen._api.close()
                logger.info("APP: Intruder storage closed on quit")
        except Exception as e:
            logger.warning("APP: Intruder storage close error on quit: %s", e)
        # Close Target/SiteMap's persistent SQLite connection (BaseSqliteStorage).
        try:
            from pentool.tui.screens.target.screen import TargetScreen
            target_screen = self.query_one(SCREEN_TARGET, TargetScreen)
            if target_screen._target_api is not None:
                await target_screen._target_api.close()
                logger.info("APP: Target storage closed on quit")
        except Exception as e:
            logger.warning("APP: Target storage close error on quit: %s", e)
        # Close Repeater's persistent SQLite connection (BaseSqliteStorage).
        try:
            from pentool.tui.screens.repeater.screen import RepeaterScreen
            repeater_screen = self.query_one(SCREEN_REPEATER, RepeaterScreen)
            if repeater_screen._repeater_api is not None:
                await repeater_screen._repeater_api.close()
                logger.info("APP: Repeater storage closed on quit")
        except Exception as e:
            logger.warning("APP: Repeater storage close error on quit: %s", e)
        # Stop the spider CPU pool BEFORE the hard os._exit() below. exit() is
        # followed synchronously by os._exit(), which by-passes atexit/finally —
        # so a process-pool created via fork leaves orphaned workers (PPID=1)
        # holding the inherited 8080 listener fd, and the next launch fails
        # with "address already in use". shutdown_proc_pool() terminates them
        # cleanly so the port is released on a normal quit.
        try:
            from pentool.modules.spider import shutdown_proc_pool
            shutdown_proc_pool()
        except Exception:
            pass
        self.exit()
        # Force-terminate the process — kills non-daemon threads
        # (jemalloc_bg_thd from pyarrow) that would otherwise block exit.
        # call_later gives Textual ~100ms for final screen cleanup.
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(0.1, os._exit, 0)
        except RuntimeError:
            os._exit(0)
