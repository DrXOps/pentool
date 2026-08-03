"""LiveDashboard — «Live» tab in Dashboard with real-time widgets."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import RichLog, Static

from pentool.tui.widgets.toolbar_button import ToolbarButton

# ── Helper functions ───────────────────────────────────────────────────────

_SPARK_CHARS = " ▁▂▃▄▅▆▇█"

def _sparkline(values: list[float], width: int = 30) -> str:
    """Build a fixed-width ASCII sparkline."""
    if not values:
        return " " * width
    # Take the last `width` values
    data = list(values)[-width:]
    if len(data) < width:
        data = [0.0] * (width - len(data)) + data
    max_val = max(data) or 1.0
    chars = []
    for v in data:
        idx = int((v / max_val) * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(idx, len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])
    return "".join(chars)

def _hbar(value: float, max_val: float = 100.0, width: int = 20) -> str:
    """Horizontal progress bar."""
    ratio = min(1.0, max(0.0, value / (max_val or 1.0)))
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)

def _color_by_percent(pct: float) -> str:
    """Color by percentage: green → yellow → red."""
    if pct < 50:
        return "green"
    elif pct < 80:
        return "yellow"
    return "red"

# ── Widget 1: Traffic Sparkline ────────────────────────────────────────────

class TrafficSparkline(Widget):
    """ASCII sparkline of requests per second over the last 60 seconds."""

    DEFAULT_CSS = """
    TrafficSparkline {
        height: 5;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: deque[float] = deque([0.0] * 60, maxlen=60)
        self._last_count: int = 0
        self._count: int = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="sparkline-title")
        yield Static("", id="sparkline-graph")
        yield Static("", id="sparkline-stats")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def increment(self) -> None:
        """Call on each new request."""
        self._count += 1

    def _tick(self) -> None:
        rps = self._count - self._last_count
        self._last_count = self._count
        self._history.append(float(rps))
        self._update_display()

    def _update_display(self) -> None:
        data = list(self._history)
        max_rps = max(data) or 1
        avg_rps = sum(data) / len(data)
        current = data[-1]

        spark = _sparkline(data, width=40)
        color = "green" if current < avg_rps * 1.5 else "yellow"
        if current > avg_rps * 2:
            color = "red"

        try:
            self.query_one("#sparkline-title", Static).update(
                "[bold]┌─ TRAFFIC (RPS) ─[/bold]"
            )
            self.query_one("#sparkline-graph", Static).update(
                f"[{color}]{spark}[/{color}]"
            )
            self.query_one("#sparkline-stats", Static).update(
                f"cur:[bold]{current:.0f}[/bold]  avg:[dim]{avg_rps:.1f}[/dim]  max:[dim]{max_rps:.0f}[/dim]"
            )
        except Exception:
            pass


# ── Widget 2: Bubble Chart ─────────────────────────────────────────────────

class BubbleChart(Widget):
    """ASCII vulnerability map by severity with animation on new findings."""

    DEFAULT_CSS = """
    BubbleChart {
        height: 8;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    # Bubble symbols of varying sizes
    _BUBBLES = {
        0: "●",   # critical — large
        1: "◉",   # high
        2: "○",   # medium
        3: "·",   # low
        4: "·",   # info
    }
    _COLORS = {
        "critical": "bold red",
        "high":     "red",
        "medium":   "yellow",
        "low":      "green",
        "info":     "blue",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._counts: dict[str, int] = {
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
        }
        self._blink_severity: str | None = None
        self._blink_until: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ VULNERABILITY MAP ─[/bold]")
        yield Static("", id="bubble-body")

    def on_mount(self) -> None:
        self.set_interval(0.5, self._update_display)

    def add_finding(self, severity: str) -> None:
        """Add a new finding — the bubble blinks."""
        sev = severity.lower()
        if sev in self._counts:
            self._counts[sev] += 1
        self._blink_severity = sev
        self._blink_until = time.monotonic() + 2.0

    def _update_display(self) -> None:
        now = time.monotonic()
        blink_active = self._blink_severity and now < self._blink_until
        blink_on = blink_active and (int(now * 4) % 2 == 0)

        lines = []
        for i, (sev, label) in enumerate([
            ("critical", "Critical"),
            ("high",     "High    "),
            ("medium",   "Medium  "),
            ("low",      "Low     "),
            ("info",     "Info    "),
        ]):
            count = self._counts[sev]
            bubble = self._BUBBLES.get(i, "●")
            color = self._COLORS[sev]
            is_blink = blink_active and self._blink_severity == sev
            if is_blink and blink_on:
                color = "bold white on red" if sev == "critical" else "bold white"
            lines.append(f"[{color}]{bubble} {label}[/{color}]  [bold]{count:>3}[/bold]")

        try:
            self.query_one("#bubble-body", Static).update("\n".join(lines))
        except Exception:
            pass


# ── Widget 3: Scan Speedometer ─────────────────────────────────────────────

class ScanSpeedometer(Widget):
    """ASCII speedometer for active scan progress."""

    DEFAULT_CSS = """
    ScanSpeedometer {
        height: 7;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._progress: float = 0.0
        self._findings: int = 0
        self._scanning: bool = False
        self._start_time: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ SCAN PROGRESS ─[/bold]")
        yield Static("", id="speedo-arc")
        yield Static("", id="speedo-stats")

    def update_progress(self, done: int, total: int, scanning: bool) -> None:
        self._progress = (done / total * 100) if total > 0 else 0
        self._scanning = scanning
        if scanning and self._start_time == 0.0:
            self._start_time = time.monotonic()
        elif not scanning:
            self._start_time = 0.0
        self._update_display()

    def add_finding(self) -> None:
        self._findings += 1
        self._update_display()

    def _update_display(self) -> None:
        pct = self._progress
        # ASCII speedometer arc (0–100% → left half → right half)
        arc_len = 20
        filled = int(pct / 100 * arc_len)
        arc = "[green]" + "▓" * filled + "░" * (arc_len - filled) + "[/green]"

        color = _color_by_percent(pct)
        status = "SCANNING" if self._scanning else "IDLE"

        # ETA
        eta_str = ""
        if self._scanning and pct > 0 and self._start_time > 0:
            elapsed = time.monotonic() - self._start_time
            total_est = elapsed * 100 / pct
            remaining = max(0, total_est - elapsed)
            m, s = int(remaining // 60), int(remaining % 60)
            eta_str = f"  ETA: {m}m {s}s"

        try:
            self.query_one("#speedo-arc", Static).update(
                f"[{color}]({arc} {pct:.0f}%)[/{color}]"
            )
            self.query_one("#speedo-stats", Static).update(
                f"[dim]{status}[/dim]  findings:[bold]{self._findings}[/bold]{eta_str}"
            )
        except Exception:
            pass


# ── Widget 4: Heatmap ──────────────────────────────────────────────────────

class HeatmapWidget(Widget):
    """Heatmap of scope hosts by request frequency."""

    DEFAULT_CSS = """
    HeatmapWidget {
        height: 8;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._host_counts: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ HOST HEATMAP ─[/bold]")
        yield Static("", id="heatmap-body")

    def increment_host(self, host: str) -> None:
        self._host_counts[host] = self._host_counts.get(host, 0) + 1
        self._update_display()

    def _update_display(self) -> None:
        if not self._host_counts:
            try:
                self.query_one("#heatmap-body", Static).update("[dim]no traffic yet[/dim]")
            except Exception:
                pass
            return

        total = max(self._host_counts.values())
        # Top 6 hosts
        sorted_hosts = sorted(self._host_counts.items(), key=lambda x: -x[1])[:6]

        lines = []
        for host, count in sorted_hosts:
            ratio = count / total
            bar_len = int(ratio * 18)
            # Color from green to red
            if ratio < 0.3:
                color = "green"
            elif ratio < 0.6:
                color = "yellow"
            else:
                color = "red"
            bar = "█" * bar_len + "░" * (18 - bar_len)
            pct = int(ratio * 100)
            short_host = host[:20] if len(host) > 20 else host
            lines.append(f"[{color}]{bar}[/{color}] [dim]{short_host}[/dim] [bold]{pct}%[/bold]")

        try:
            self.query_one("#heatmap-body", Static).update("\n".join(lines))
        except Exception:
            pass


# ── Widget 5: Event Feed ───────────────────────────────────────────────────

class EventFeed(Widget):
    """Real-time event feed."""

    DEFAULT_CSS = """
    EventFeed {
        height: 12;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ LIVE EVENT FEED ─[/bold]")
        yield RichLog(
            id="event-feed-log",
            highlight=True,
            markup=True,
            wrap=False,
            max_lines=200,
        )

    def add_event(self, event_type: str, message: str) -> None:
        """Add an event to the feed."""
        colors = {
            "request":   "dim cyan",
            "intercept": "bold yellow",
            "finding":   "bold red",
            "scan":      "green",
            "error":     "red",
            "info":      "dim",
        }
        color = colors.get(event_type, "white")
        ts = time.strftime("%H:%M:%S")
        try:
            log = self.query_one("#event-feed-log", RichLog)
            log.write(f"[dim]{ts}[/dim] [{color}]{message}[/{color}]")
        except Exception:
            pass


# ── Widget 6: Resource Monitor ─────────────────────────────────────────────

class ResourceMonitor(Widget):
    """CPU + RAM thermometers."""

    DEFAULT_CSS = """
    ResourceMonitor {
        height: 6;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ RESOURCES ─[/bold]")
        yield Static("", id="res-cpu")
        yield Static("", id="res-ram")
        yield Static("", id="res-extra")

    def on_mount(self) -> None:
        self.set_interval(2.0, self._update)

    def _update(self) -> None:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            ram = mem.percent

            cpu_color = _color_by_percent(cpu)
            ram_color = _color_by_percent(ram)
            cpu_bar = _hbar(cpu, 100, 18)
            ram_bar = _hbar(ram, 100, 18)

            blink = "" if cpu < 90 else " [bold red]![/bold red]"
            cpu_line = f"CPU [{cpu_color}]{cpu_bar}[/{cpu_color}] [bold]{cpu:.0f}%[/bold]{blink}"
            ram_line = f"RAM [{ram_color}]{ram_bar}[/{ram_color}] [bold]{ram:.0f}%[/bold]"

            self.query_one("#res-cpu", Static).update(cpu_line)
            self.query_one("#res-ram", Static).update(ram_line)
            # Extra info: number of process threads
            try:
                import os
                proc = psutil.Process(os.getpid())
                threads = proc.num_threads()
                self.query_one("#res-extra", Static).update(
                    f"[dim]threads: {threads}[/dim]"
                )
            except Exception:
                pass
        except ImportError:
            try:
                self.query_one("#res-cpu", Static).update("[dim]psutil not installed[/dim]")
            except Exception:
                pass
        except Exception:
            pass


# ── Widget 7: Emergency Stop ───────────────────────────────────────────────

class EmergencyStop(Widget):
    """Emergency Stop button with a 3-second countdown."""

    DEFAULT_CSS = """
    EmergencyStop {
        height: 5;
        border: solid $error;
        padding: 0 1;
        align: center middle;
    }
    EmergencyStop #stop-countdown {
        color: $error;
        text-align: center;
    }
    """

    def __init__(self, on_stop: Callable | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._on_stop = on_stop
        self._countdown: int = 0
        self._timer = None
        self._armed: bool = False

    def compose(self) -> ComposeResult:
        yield ToolbarButton("🛑 EMERGENCY STOP", "btn-estop", classes="inactive")
        yield Static("", id="stop-countdown")

    @staticmethod
    def _format_countdown(n: int) -> str:
        blocks = "█" * n + "░" * (3 - n)
        return f"[bold red]STOPPING IN {n}... [{blocks}][/bold red]"

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        if event.button.id == "btn-estop":
            if not self._armed:
                self._arm()
            else:
                self._disarm()

    def _arm(self) -> None:
        self._armed = True
        self._countdown = 3
        self._render_countdown()
        self._timer = self.set_interval(1.0, self._tick_countdown)

    def _disarm(self) -> None:
        self._armed = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._countdown = 0
        try:
            self.query_one("#stop-countdown", Static).update("[dim]canceled[/dim]")
        except Exception:
            pass
        self.set_timer(1.0, lambda: self.query_one("#stop-countdown", Static).update(""))

    def _tick_countdown(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            if self._timer:
                self._timer.stop()
                self._timer = None
            self._armed = False
            self._execute_stop()
        else:
            self._render_countdown()

    def _render_countdown(self) -> None:
        try:
            self.query_one("#stop-countdown", Static).update(
                self._format_countdown(self._countdown)
            )
        except Exception:
            pass

    def _execute_stop(self) -> None:
        try:
            self.query_one("#stop-countdown", Static).update("[bold red]STOPPED[/bold red]")
        except Exception:
            pass
        if self._on_stop:
            try:
                self._on_stop()
            except Exception:
                pass
        # Emit EmergencyStop via EventBus
        try:
            import dataclasses

            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import AppEvent

            @dataclasses.dataclass
            class EmergencyStopEvent(AppEvent):
                pass

            get_event_bus().emit(EmergencyStopEvent(source="dashboard"))
        except Exception:
            pass


# ── Mini Site Map ─────────────────────────────────────────────────────────

class MiniSiteMap(Widget):
    """Compact site map with progress bars."""

    DEFAULT_CSS = """
    MiniSiteMap {
        height: 10;
        border: solid $primary-darken-3;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._paths: dict[str, int] = {}  # path → count

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ SITE MAP ─[/bold]")
        yield Static("", id="sitemap-body")

    def add_url(self, url: str) -> None:
        """Add a URL to the mini-map."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            # First 2 path segments
            parts = [p for p in parsed.path.split("/") if p]
            key = "/" + "/".join(parts[:2]) if parts else "/"
            self._paths[key] = self._paths.get(key, 0) + 1
            self._update_display()
        except Exception:
            pass

    def _update_display(self) -> None:
        if not self._paths:
            try:
                self.query_one("#sitemap-body", Static).update("[dim]no URLs yet[/dim]")
            except Exception:
                pass
            return

        total = max(self._paths.values())
        sorted_paths = sorted(self._paths.items(), key=lambda x: -x[1])[:8]
        lines = []
        for i, (path, count) in enumerate(sorted_paths):
            prefix = "├─" if i < len(sorted_paths) - 1 else "└─"
            bar = _hbar(count, total, 10)
            lines.append(
                f"[dim]{prefix}[/dim] [cyan]{path[:18]}[/cyan] [green]{bar}[/green] [dim]{count}[/dim]"
            )

        try:
            self.query_one("#sitemap-body", Static).update("\n".join(lines))
        except Exception:
            pass


# ── Container: LiveDashboardTab ────────────────────────────────────────────

class LiveDashboardTab(Widget):
    """«Live» tab — the entire live dashboard in one widget."""

    DEFAULT_CSS = """
    LiveDashboardTab {
        layout: vertical;
        height: 1fr;
        overflow-y: auto;
    }
    LiveDashboardTab #live-row1 {
        height: auto;
        layout: horizontal;
    }
    LiveDashboardTab #live-row2 {
        height: auto;
        layout: horizontal;
    }
    LiveDashboardTab #live-row3 {
        height: auto;
        layout: horizontal;
    }
    LiveDashboardTab TrafficSparkline {
        width: 1fr;
    }
    LiveDashboardTab EventFeed {
        width: 2fr;
    }
    LiveDashboardTab BubbleChart {
        width: 1fr;
    }
    LiveDashboardTab ScanSpeedometer {
        width: 1fr;
    }
    LiveDashboardTab HeatmapWidget {
        width: 2fr;
    }
    LiveDashboardTab MiniSiteMap {
        width: 1fr;
    }
    LiveDashboardTab ResourceMonitor {
        width: 1fr;
    }
    LiveDashboardTab EmergencyStop {
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="live-row1"):
            yield TrafficSparkline(id="live-sparkline")
            yield EventFeed(id="live-feed")
            yield BubbleChart(id="live-bubbles")
        with Horizontal(id="live-row2"):
            yield ScanSpeedometer(id="live-speedo")
            yield HeatmapWidget(id="live-heatmap")
            yield MiniSiteMap(id="live-sitemap")
        with Horizontal(id="live-row3"):
            yield ResourceMonitor(id="live-resources")
            yield EmergencyStop(id="live-estop")

    def on_mount(self) -> None:
        """Subscribe to EventBus."""
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import (
                FindingDiscovered,
                ProxyRequestDoneEvent,
                ScanProgressEvent,
                UrlCrawled,
            )
            bus = get_event_bus()
            bus.subscribe(ProxyRequestDoneEvent, self._on_request)
            bus.subscribe(FindingDiscovered,     self._on_finding)
            bus.subscribe(ScanProgressEvent,     self._on_scan_progress)
            bus.subscribe(UrlCrawled,            self._on_url_crawled)
        except Exception:
            pass

    def _on_request(self, event) -> None:
        try:
            self.app.call_from_thread(self._handle_request, event)
        except Exception:
            pass

    def _handle_request(self, event) -> None:
        try:
            self.query_one("#live-sparkline", TrafficSparkline).increment()
            url = getattr(event, "url", "") or ""
            if url:
                from urllib.parse import urlparse
                host = urlparse(url).netloc or url
                self.query_one("#live-heatmap", HeatmapWidget).increment_host(host)
                self.query_one("#live-sitemap", MiniSiteMap).add_url(url)
            self.query_one("#live-feed", EventFeed).add_event(
                "request", f"→ {getattr(event, 'method', 'GET')} {url[:60]}"
            )
        except Exception:
            pass

    def _on_finding(self, event) -> None:
        try:
            self.app.call_from_thread(self._handle_finding, event)
        except Exception:
            pass

    def _handle_finding(self, event) -> None:
        try:
            finding = event.finding
            sev = getattr(finding, "severity", "info")
            url = getattr(finding, "url", "?")
            ftype = getattr(finding, "type", "?")
            self.query_one("#live-bubbles", BubbleChart).add_finding(sev)
            self.query_one("#live-speedo",  ScanSpeedometer).add_finding()
            self.query_one("#live-feed", EventFeed).add_event(
                "finding", f"[{sev.upper()}] {ftype} → {url[:50]}"
            )
        except Exception:
            pass

    def _on_scan_progress(self, event) -> None:
        try:
            self.app.call_from_thread(self._handle_scan_progress, event)
        except Exception:
            pass

    def _handle_scan_progress(self, event) -> None:
        try:
            done = getattr(event, "done", 0)
            total = getattr(event, "total", 0)
            scanning = getattr(event, "scanning", True)
            self.query_one("#live-speedo", ScanSpeedometer).update_progress(done, total, scanning)
        except Exception:
            pass

    def _on_url_crawled(self, event) -> None:
        try:
            self.app.call_from_thread(self._handle_url_crawled, event)
        except Exception:
            pass

    def _handle_url_crawled(self, event) -> None:
        try:
            url = getattr(event, "url", "")
            self.query_one("#live-sitemap", MiniSiteMap).add_url(url)
            self.query_one("#live-feed", EventFeed).add_event("scan", f"crawled: {url[:60]}")
        except Exception:
            pass
