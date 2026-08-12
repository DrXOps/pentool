"""Dashboard — application start screen."""

from __future__ import annotations

import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widget import Widget

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

from textual.widgets import (
    RichLog,
    Static,
    Tree,
)

from pentool.core.logging import get_logger
from pentool.tui.screens.dashboard.live_dashboard import ResourceMonitor
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)


def _build_logo() -> str:
    """Build the ASCII logo with the real installed pentool version.

    Version line is centered within the same width as the other dashed
    lines in the logo (kept fixed regardless of version string length,
    so e.g. "0.2.8" vs "0.2.10" vs "0.2.8.dev4" don't visibly misalign
    the block).
    """
    from pentool import __version__

    inner_width = 77
    label = f" Web Security Testing Platform v{__version__} "
    dashes_total = max(inner_width - len(label), 0)
    left = dashes_total // 2
    right = dashes_total - left
    version_line = "─" * left + label + "─" * right

    return (
        "[bold green] ██████╗ [/][bold cyan]███████╗[/][bold green]███╗   ██╗[/][bold cyan]████████╗[/][bold green] ██████╗  ██████╗ ██╗[/]\n"
        "[bold green] ██╔══██╗[/][bold cyan]██╔════╝[/][bold green]████╗  ██║[/][bold cyan]╚══██╔══╝[/][bold green]██╔═══██╗██╔═══██╗██║[/]\n"
        "[bold green] ██████╔╝[/][bold cyan]█████╗  [/][bold green]██╔██╗ ██║[/][bold cyan]   ██║   [/][bold green]██║   ██║██║   ██║██║[/]\n"
        "[bold green] ██╔═══╝ [/][bold cyan]██╔══╝  [/][bold green]██║╚██╗██║[/][bold cyan]   ██║   [/][bold green]██║   ██║██║   ██║██║[/]\n"
        "[bold green] ██║     [/][bold cyan]███████╗[/][bold green]██║ ╚████║[/][bold cyan]   ██║   [/][bold green]╚██████╔╝╚██████╔╝███████╗[/]\n"
        "[bold green] ╚═╝     [/][bold cyan]╚══════╝[/][bold green]╚═╝  ╚═══╝[/][bold cyan]   ╚═╝   [/][bold green] ╚═════╝  ╚═════╝ ╚══════╝[/]\n"
        f"[dim green]{version_line}[/]\n"
        "[dim]                           by @sudores (aka DoctorX)                           [/]"
    )


# Module constants
_LOGO = _build_logo()

_BOOT_LINES = [
    ("[dim green]", "> Mounting kernel modules..."),
    ("[dim green]", "> Loading OWASP Top 10 payload database..."),
    ("[bold green]", "> [OK] SQLi / XSS / SSTI / LFI / RCE / SSRF engine READY"),
    ("[dim green]", "> Initializing passive scanner hooks..."),
    ("[bold green]", "> [OK] Passive scanner ARMED"),
    ("[dim green]", "> Starting spider engine (depth=3, pages=100)..."),
    ("[bold green]", "> [OK] Spider engine READY"),
    ("[dim green]", "> Loading certificate authority..."),
    ("[bold green]", "> [OK] MITM proxy engine READY"),
    ("[bold green]", "> All systems GO. Happy hacking! 🔒"),
]

_SPARK_CHARS = " ▁▂▃▄▅▆▇█"

_SEV_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "green",
    "info": "blue",
}
_SEV_ICONS = {
    "critical": "💀",
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
    "info": "🔵",
}

_THREAT_CHARS = "█"
_THREAT_COLORS = ["green", "green", "yellow", "yellow", "red", "red", "bold red", "bold red", "bold red", "bold red"]

def _sparkline(values: list[int], width: int = 30, max_val: int | None = None) -> str:
    """Build a sparkline from the given values."""
    if not values:
        return " " * width
    mv = max_val or max(values) or 1
    vals = list(values)[-width:]
    if len(vals) < width:
        vals = [0] * (width - len(vals)) + vals
    result = ""
    for v in vals:
        idx = int((v / mv) * (len(_SPARK_CHARS) - 1))
        result += _SPARK_CHARS[min(idx, len(_SPARK_CHARS) - 1)]
    return result

def _bar(value: int, max_val: int, width: int = 20, color: str = "green") -> str:
    """Horizontal bar with color."""
    if max_val == 0:
        filled = 0
    else:
        filled = int((value / max_val) * width)
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar}[/{color}]"

def _threat_gauge(level: int, width: int = 40) -> str:
    """Threat level gauge (0–100)."""
    level = max(0, min(100, level))
    filled = int((level / 100) * width)
    color = _THREAT_COLORS[min(9, level // 10)]
    bar = "█" * filled + "░" * (width - filled)
    label = f" {level:3d}%"
    if level == 0:
        label_color = "dim"
        threat_word = "NONE"
    elif level < 20:
        label_color = "green"
        threat_word = "LOW"
    elif level < 40:
        label_color = "yellow"
        threat_word = "MEDIUM"
    elif level < 70:
        label_color = "red"
        threat_word = "HIGH"
    else:
        label_color = "bold red"
        threat_word = "CRITICAL"
    return f"[{color}]{bar}[/{color}][{label_color}]{label} [{threat_word}][/{label_color}]"

def _matrix_cell(count: int) -> str:
    """Severity matrix cell for heatmap."""
    if count == 0:
        return "[dim]·[/dim]"
    elif count < 3:
        return "[green]▪[/green]"
    elif count < 10:
        return "[yellow]▪[/yellow]"
    elif count < 30:
        return "[red]▪[/red]"
    else:
        return "[bold red]▪[/bold red]"

class LiveChart(Vertical):
    """ASCII sparkline chart with live updates."""

    DEFAULT_CSS = _CSS

    def __init__(self, title: str, color: str = "green", unit: str = "req/s", chart_id: str = "", **kwargs):
        super().__init__(id=chart_id or None, **kwargs)
        self._title = title
        self._color = color
        self._unit = unit
        self._history: deque[int] = deque([0] * 60, maxlen=60)
        self._total = 0
        self._peak = 0
        self._last_rate = 0
        self._summary: str = ""  # additional info line

    def compose(self) -> ComposeResult:
        yield Static(f"┌─ {self._title} ─", id="chart-title")
        yield Static(" ", id="chart-spark")
        yield Static(" ", id="chart-axis")
        yield Static(" ", id="chart-stats")
        yield Static(" ", id="chart-meta")
        yield Static(" ", id="chart-summary")

    def set_summary(self, text: str) -> None:
        self._summary = text
        try:
            self.query_one("#chart-summary", Static).update(text)
        except Exception:
            pass

    def on_mount(self) -> None:
        self.call_after_refresh(self._render_chart)

    def push(self, value: int) -> None:
        self._history.append(value)
        self._total += value
        if value > self._peak:
            self._peak = value
        self._last_rate = value
        self._render_chart()

    def _render_chart(self) -> None:
        vals = list(self._history)
        mv = max(vals) if vals else 1
        spark = _sparkline(vals, width=50, max_val=max(mv, 1))
        axis = "[dim]└" + "─" * 48 + "60s[/dim]"
        avg = sum(vals) / max(len([v for v in vals if v > 0]), 1)
        stats = (
            f"[{self._color}]now:[/{self._color}][bold] {self._last_rate:4d}[/bold] "
            f"[dim]avg:[/dim][bold] {avg:5.1f}[/bold] "
            f"[dim]peak:[/dim][bold] {self._peak:4d}[/bold] "
            f"[dim]total:[/dim][bold] {self._total:,}[/bold] {self._unit}"
        )
        try:
            self.query_one("#chart-spark", Static).update(f"[{self._color}]{spark}[/{self._color}]")
            self.query_one("#chart-axis", Static).update(axis)
            self.query_one("#chart-stats", Static).update(stats)
            self.query_one("#chart-meta", Static).update(
                f"[dim]scale: 0–{mv} {self._unit}  │  window: 60s[/dim]"
            )
        except Exception:
            pass

class ThreatMeter(Vertical):
    """Threat Level visual gauge."""

    DEFAULT_CSS = _CSS

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._level = 0
        self._counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        self._top_finding = "—"

    def compose(self) -> ComposeResult:
        yield Static("┌─ THREAT LEVEL ─", id="tm-title")
        yield Static(" ", id="tm-gauge")
        yield Static(" ", id="tm-breakdown")
        yield Static(" ", id="tm-top")
        yield Static("[dim]Based on active findings in current session[/dim]", id="tm-hint")

    def on_mount(self) -> None:
        self.call_after_refresh(self._refresh_display)

    def update_findings(self, counts: dict[str, int], top_finding: str = "") -> None:
        self._counts = counts
        self._top_finding = top_finding or "—"
        level = (
            counts.get("critical", 0) * 25 +
            counts.get("high", 0) * 10 +
            counts.get("medium", 0) * 3 +
            counts.get("low", 0) * 1
        )
        self._level = min(100, level)
        self._refresh_display()

    def _refresh_display(self) -> None:
        try:
            gauge = _threat_gauge(self._level, width=42)
            c = self._counts
            breakdown = (
                f"[bold red]CRIT:{c.get('critical',0):3d}[/bold red]  "
                f"[red]HIGH:{c.get('high',0):3d}[/red]  "
                f"[yellow]MED:{c.get('medium',0):4d}[/yellow]  "
                f"[green]LOW:{c.get('low',0):4d}[/green]  "
                f"[blue]INFO:{c.get('info',0):3d}[/blue]"
            )
            top = f"[dim]Top finding: [/dim][yellow]{self._top_finding[:55]}[/yellow]"
            self.query_one("#tm-gauge", Static).update(gauge)
            self.query_one("#tm-breakdown", Static).update(breakdown)
            self.query_one("#tm-top", Static).update(top)
        except Exception:
            pass

class SeverityMatrix(Vertical):
    """Heatmap matrix of findings by type × severity."""

    DEFAULT_CSS = _CSS

    _VULN_TYPES = ["SQLi", "XSS", "SSTI", "LFI", "RCE", "Redir", "SSRF", "XXE", "Hdrs", "Info"]
    _SEV_KEYS   = ["critical", "high", "medium", "low", "info"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._matrix: dict[str, dict[str, int]] = {
            vt: {s: 0 for s in self._SEV_KEYS}
            for vt in self._VULN_TYPES
        }

    def compose(self) -> ComposeResult:
        yield Static(" ", id="mx-body", markup=True)

    def on_mount(self) -> None:
        self.call_after_refresh(self._refresh_display)

    def add_finding(self, vuln_type: str, severity: str) -> None:
        type_map = {
            "sqli": "SQLi", "xss": "XSS", "ssti": "SSTI",
            "lfi": "LFI", "rce": "RCE", "open_redirect": "Redir", "ssrf": "SSRF",
            "xxe": "XXE",
            "missing_security_header": "Hdrs", "missing_security_headers": "Hdrs",
            "info_leak": "Info",
        }
        vt_key = type_map.get(vuln_type.lower(), "Info")
        if vt_key in self._matrix and severity in self._matrix[vt_key]:
            self._matrix[vt_key][severity] += 1
        self._refresh_display()

    def set_matrix(self, matrix: dict) -> None:
        for vt, counts in matrix.items():
            if vt in self._matrix:
                self._matrix[vt].update(counts)
        self._refresh_display()

    def _build_text(self) -> str:
        lines = []
        lines.append("[bold yellow]┌─ VULNERABILITY MATRIX ─[/bold yellow]")
        lines.append("[dim]TYPE    CRIT     HIGH     MED      LOW      INFO    TOTAL[/dim]")
        lines.append("[dim]" + "─" * 56 + "[/dim]")
        for vt in self._VULN_TYPES:
            counts = self._matrix.get(vt, {})
            total = sum(counts.values())
            cells = ""
            for sev in self._SEV_KEYS:
                cnt = counts.get(sev, 0)
                cells += f"  {_matrix_cell(cnt)}[dim]{cnt:3d}[/dim]  "
            tc = "bold red" if counts.get("critical", 0) > 0 else (
                "red" if counts.get("high", 0) > 0 else (
                    "yellow" if counts.get("medium", 0) > 0 else "dim"))
            lines.append(f"[cyan]{vt:<6}[/cyan]{cells}[{tc}]{total:3d}[/{tc}]")
        lines.append("[dim]· none  [/dim][green]▪ 1–2  [/green][yellow]▪ 3–9  [/yellow][red]▪ 10–29  [/red][bold red]▪ 30+[/bold red]")
        return "\n".join(lines)

    def _refresh_display(self) -> None:
        try:
            self.query_one("#mx-body", Static).update(self._build_text())
        except Exception:
            pass

class DashboardScreen(Widget):
    """Dashboard — application start screen."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("r", "refresh_dash", "Refresh", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats = {"requests": 0, "findings": 0, "hosts": 0, "req_rate": 0}
        self._finding_counts: dict[str, int] = {
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0
        }
        self._top_finding = "—"
        self._req_history: list[int] = []
        self._find_history: list[int] = []
        self._ticker: Timer | None = None
        self._req_bucket = 0   # requests in the current second
        self._find_bucket = 0  # findings in the current second

    def compose(self) -> ComposeResult:
        yield from self._compose_overview()

    def _compose_overview(self) -> ComposeResult:
        with Horizontal(id="logo-bar"):
            yield Static(_LOGO, id="logo", markup=True)

        with Horizontal(id="top-row"):
            yield LiveChart(
                "HTTP REQUESTS / sec",
                color="green",
                unit="req/s",
                chart_id="chart-requests",
            )
            yield ThreatMeter(id="threat-meter")
            yield ResourceMonitor(id="dash-resources")

        with Horizontal(id="main-area"):
            with Vertical(id="left-pane"):
                yield Static("┌─ PROJECTS ─", id="pp-title")
                yield Tree("Recent projects:", id="project-tree")
                with Horizontal(id="pp-actions"):
                    yield ToolbarButton("+ New",    "btn-new-project")
                    yield ToolbarButton("📂 Open",  "btn-open-project")
                    yield ToolbarButton("💾 Save",  "btn-save-project")
                yield Static(
                    "[dim]"
                    "Shift+P Proxy  Shift+R Repeater  Shift+I Intruder\n"
                    "Shift+S Scanner  Shift+T Target  Shift+L Spider\n"
                    "Shift+D Decoder  Shift+C Comparer  Shift+E Settings\n"
                    "Ctrl+N New  Ctrl+O Open  Ctrl+S Save  Ctrl+Q Quit"
                    "[/dim]",
                    id="hk-panel",
                )

            with Vertical(id="right-col"):
                with Horizontal(id="mid-row"):
                    with Vertical(id="feed-panel"):
                        yield Static("┌─ LIVE FEED ─", id="feed-panel-title")
                        yield RichLog(id="feed-log", highlight=True, markup=True, wrap=False, max_lines=300)
                    with Vertical(id="status-panel"):
                        yield Static("┌─ STATUS ─", id="status-panel-title")
                        yield Static("[dim]●[/dim] Proxy: [dim]STOPPED[/dim]",  id="led-proxy-bar",   classes="led-item")
                        yield Static("[dim]●[/dim] Passive: [dim]OFF[/dim]",    id="led-passive-bar", classes="led-item")
                        yield Static("[dim]●[/dim] Active: [dim]IDLE[/dim]",    id="led-scan-bar",    classes="led-item")
                        yield Static("[dim]●[/dim] Spider: [dim]IDLE[/dim]",    id="led-spider-bar",  classes="led-item")
                        yield Static("[dim]●[/dim] Threads: [dim]—[/dim]",      id="led-threads-bar", classes="led-item")
                with Vertical(id="matrix-col"):
                    yield SeverityMatrix(id="vuln-matrix")

    def on_mount(self) -> None:
        self._ticker = self.set_interval(1.0, self._tick)
        try:
            feed = self.query_one("#feed-log", RichLog)
            feed.write("[dim cyan]ℹ Live feed ready. Waiting for events...[/dim cyan]")
        except Exception:
            pass
        self._load_stats_bg()
        self._populate_projects()
        self._boot_animate()

    @on(ToolbarButton.Pressed, "#btn-new-project")
    def on_btn_new_project(self, _: ToolbarButton.Pressed) -> None:
        self._new_project_dialog()

    @on(ToolbarButton.Pressed, "#btn-open-project")
    def on_btn_open_project(self, _: ToolbarButton.Pressed) -> None:
        self._open_project_dialog()

    @on(ToolbarButton.Pressed, "#btn-save-project")
    def on_btn_save_project(self, _: ToolbarButton.Pressed) -> None:
        self._save_project_dialog()

    def _populate_projects(self) -> None:
        try:
            tree = self.query_one("#project-tree", Tree)
            tree.clear()
            root = tree.root
            root.label = "[dim]Recent projects:[/dim]"
            cfg = getattr(self.app, "_cfg", None)
            recent = (getattr(cfg, "recent_projects", None) or []) if cfg else []
            current = getattr(self.app, "_project_path", None)
            for path in recent[:8]:
                basename = os.path.basename(path)
                proj_name = os.path.splitext(basename)[0]
                ts = ""
                try:
                    mtime = os.path.getmtime(path)
                    ts = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
                except Exception:
                    pass
                exists = os.path.exists(path)
                is_active = (path == current)

                if is_active:
                    node_label = f"[bold cyan]{proj_name}[/bold cyan] [bold green]●[/bold green]" + (f" [dim]{ts}[/dim]" if ts else "")
                elif exists:
                    node_label = f"[cyan]{proj_name}[/cyan]" + (f" [dim]{ts}[/dim]" if ts else "")
                else:
                    node_label = f"[dim]{proj_name} (missing)[/dim]"

                # Add as a node with a child leaf showing the path
                node = root.add(node_label, data=path)
                node.add_leaf(f"[dim]{path}[/dim]", data=path)
                if is_active:
                    node.expand()

            if not root.children:
                root.add_leaf("[dim]No recent projects — use Open to load[/dim]")
            root.expand()
        except Exception:
            pass

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        path = getattr(node, "data", None)
        if not path or not isinstance(path, str):
            return
        if not os.path.exists(path):
            self.app.notify(f"File not found: {path}", severity="warning", timeout=3)
            return
        switch_fn = getattr(self.app, "_switch_project_db", None)
        if switch_fn:
            switch_fn(path, is_new=False)
        else:
            self.app.notify(f"Opened: {os.path.basename(path)}", timeout=3)

    @work(thread=True)
    def _boot_animate(self) -> None:
        time.sleep(0.2)
        for color, line in _BOOT_LINES:
            time.sleep(0.12)
            try:
                self.app.call_from_thread(self._boot_write, color, line)
            except Exception:
                break
        time.sleep(0.3)
        try:
            self.app.call_from_thread(self._boot_write, "[dim]", "─" * 48)
        except Exception:
            pass

    def _boot_write(self, color: str, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            log = self.query_one("#feed-log", RichLog)
            log.write(f"[dim green]{ts}[/dim green] {color}{line}[/]")
        except Exception:
            pass

    def _tick(self) -> None:
        try:
            rps = self._req_bucket
            self._req_bucket = 0
            self._find_bucket = 0
            self.query_one("#chart-requests", LiveChart).push(rps)
        except Exception:
            pass

    @work
    async def _load_stats_bg(self) -> None:
        try:
            db_path = getattr(self.app, "_db_path", "") or ""
            if not db_path:
                return
            data = await self._fetch_stats(db_path)
            self._apply_stats(data)
        except Exception as exc:
            logger.debug("_load_stats_bg: %s", exc)

    async def _fetch_stats(self, db_path: str) -> dict:
        from pentool.api.scanner_api import ScannerAPI
        result: dict = {
            "requests": 0, "hosts": 0,
            "findings": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "top_finding": "—",
        }
        try:
            api = ScannerAPI(db_path=db_path)
            result["requests"] = await api.get_request_count()
            result["hosts"] = await api.get_host_count()
            scanner_stats = await api.get_stats()
            result["findings"]    = scanner_stats["findings"]
            result["top_finding"] = scanner_stats["top_finding"]
        except Exception as exc:
            logger.debug("_fetch_stats scanner_stats: %s", exc)
        return result

    def _apply_stats(self, data: dict) -> None:
        self._finding_counts = data.get("findings", self._finding_counts)
        self._top_finding = data.get("top_finding", "—")

        try:
            self.query_one("#threat-meter", ThreatMeter).update_findings(
                self._finding_counts, self._top_finding
            )
        except Exception as exc:
            logger.debug("_apply_stats ThreatMeter: %s", exc)

        try:
            matrix = self.query_one("#vuln-matrix", SeverityMatrix)
            matrix._matrix = {
                vt: {s: 0 for s in SeverityMatrix._SEV_KEYS}
                for vt in SeverityMatrix._VULN_TYPES
            }
            matrix._refresh_display()
        except Exception as exc:
            logger.debug("_apply_stats SeverityMatrix: %s", exc)

        total = data.get("requests", 0)
        hosts = data.get("hosts", 0)
        total_findings = sum(self._finding_counts.values())
        self.log_activity(
            f"Session: {total:,} requests · {hosts} hosts · {total_findings} findings",
            "ok"
        )

        try:
            self.query_one("#chart-requests", LiveChart).set_summary(
                f"[dim]Total: [/dim][bold]{total:,}[/bold][dim] reqs · [/dim][bold]{hosts}[/bold][dim] hosts[/dim]"
            )
        except Exception as exc:
            logger.debug("_apply_stats chart_summary: %s", exc)

    def action_refresh_dash(self) -> None:
        self._load_stats_bg()
        self.log_activity("Dashboard refreshed", "info")

    def _feed_write(self, text: str) -> None:
        """Write to the live-feed RichLog."""
        try:
            self.query_one("#feed-log", RichLog).write(text)
        except Exception:
            pass

    def _set_led_bar(self, widget_id: str, color: str, label: str) -> None:
        try:
            self.query_one(f"#{widget_id}", Static).update(
                f"[{color}]●[/{color}] {label}"
            )
        except Exception:
            pass

    def push_request(self, method: str, url: str, status: int = 0) -> None:
        self._req_bucket += 1
        self._stats["requests"] += 1
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        method_color = {"GET": "green", "POST": "yellow", "PUT": "cyan", "DELETE": "red", "PATCH": "magenta"}.get(method.upper(), "white")
        status_color = "green" if 200 <= status < 300 else ("yellow" if 300 <= status < 400 else ("red" if status >= 400 else "dim"))
        status_str = f"[{status_color}]{status}[/{status_color}]" if status else "[dim]···[/dim]"
        short_url = url[:60] + "…" if len(url) > 60 else url
        self._feed_write(
            f"[dim]{ts}[/dim] [{method_color}]{method:<7}[/{method_color}] "
            f"{status_str} [dim]{short_url}[/dim]"
        )

    def add_finding(self, finding) -> None:
        self._find_bucket += 1
        sev = getattr(finding, "severity", "info")
        vuln_type = getattr(finding, "type", "unknown")
        url = getattr(finding, "url", "")
        name = getattr(finding, "name", vuln_type)

        self._finding_counts[sev] = self._finding_counts.get(sev, 0) + 1
        self._top_finding = name

        try:
            self.query_one("#threat-meter", ThreatMeter).update_findings(
                self._finding_counts, self._top_finding
            )
        except Exception:
            pass
        try:
            self.query_one("#vuln-matrix", SeverityMatrix).add_finding(vuln_type, sev)
        except Exception:
            pass

        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        icon = _SEV_ICONS.get(sev, "●")
        color = _SEV_COLORS.get(sev, "white")
        short_url = url[:45] + "…" if len(url) > 45 else url
        self._feed_write(
            f"[dim]{ts}[/dim] {icon} [{color}]{sev.upper():<8}[/{color}] "
            f"[bold]{vuln_type}[/bold] [dim]{short_url}[/dim]"
        )

    def log_activity(self, message: str, level: str = "info") -> None:
        """Write a system message to the live feed."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        colors = {"info": "cyan", "warning": "yellow", "error": "red", "ok": "bold green"}
        color = colors.get(level, "white")
        prefix = {"info": "ℹ", "warning": "⚠", "error": "✗", "ok": "✓"}.get(level, "·")
        self._feed_write(f"[dim]{ts}[/dim] [{color}]{prefix} {message}[/{color}]")

    def update_proxy_status(self, running: bool, port: int = 8080) -> None:
        if running:
            self._set_led_bar("led-proxy-bar", "bold green", f"Proxy: [bold green]:{port}[/bold green]")
        else:
            self._set_led_bar("led-proxy-bar", "dim", "Proxy: [dim]STOPPED[/dim]")
        msg = f"Proxy {'started' if running else 'stopped'} on :{port}"
        self.log_activity(msg, "ok" if running else "warning")

    def update_passive_status(self, enabled: bool) -> None:
        if enabled:
            self._set_led_bar("led-passive-bar", "bold cyan", "Passive: [bold cyan]ARMED[/bold cyan]")
        else:
            self._set_led_bar("led-passive-bar", "dim", "Passive: [dim]OFF[/dim]")
        self.log_activity(f"Passive scanner {'armed' if enabled else 'disabled'}", "ok" if enabled else "warning")

    def update_scan_status(self, scanning: bool, progress: int = 0, threads: int = 0) -> None:
        if scanning:
            self._set_led_bar("led-scan-bar", "bold yellow", f"Active: [bold yellow]SCANNING {progress}%[/bold yellow]")
            if threads > 0:
                self._set_led_bar("led-threads-bar", "cyan", f"Threads: [cyan]{threads} active[/cyan]")
        else:
            self._set_led_bar("led-scan-bar", "dim", "Active: [dim]IDLE[/dim]")
            self._set_led_bar("led-threads-bar", "dim", "Threads: [dim]—[/dim]")

    def update_spider_status(self, running: bool, pages: int = 0) -> None:
        if running:
            self._set_led_bar("led-spider-bar", "bold magenta", f"Spider: [bold magenta]CRAWLING {pages}p[/bold magenta]")
        else:
            self._set_led_bar("led-spider-bar", "dim", "Spider: [dim]IDLE[/dim]")

    def refresh_stats(self) -> None:
        self._load_stats_bg()

    def _new_project_dialog(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            switch_fn = getattr(self.app, "_switch_project_db", None)
            if switch_fn:
                switch_fn(path, is_new=True)
            self._populate_projects()

        self.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="New Project — Choose Location",
                start_dir=os.path.expanduser("~"),
            ),
            _on_path,
        )

    def _open_project_dialog(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = getattr(self.app, "_project_path", None)
        start_dir = os.path.dirname(current) if current else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not os.path.exists(path):
                self.app.notify(f"File not found: {path}", severity="error", timeout=4)
                return
            switch_fn = getattr(self.app, "_switch_project_db", None)
            if switch_fn:
                switch_fn(path, is_new=False)
            self._populate_projects()

        self.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                title="Open Project",
                start_dir=start_dir,
                filter_ext=[".db"],
            ),
            _on_path,
        )

    def _save_project_dialog(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        current = getattr(self.app, "_project_path", None)
        cfg = getattr(self.app, "_cfg", None)
        src_db = (current or (cfg.db_path if cfg else None) or os.path.expanduser("~"))
        start_dir = os.path.dirname(src_db) if src_db else os.path.expanduser("~")

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".db"):
                path = path + ".db"
            import shutil
            src = (cfg.db_path if cfg else None) or src_db
            try:
                shutil.copy2(src, path)
                self.app._project_path = path  # type: ignore
                update_fn = getattr(self.app, "_update_project_name", None)
                if update_fn:
                    update_fn(path)
                self.app.notify(f"Saved to {os.path.basename(path)}", timeout=3)
                self._populate_projects()
                self.log_activity(f"Project saved: {path}", "ok")
            except Exception as e:
                self.app.notify(f"Save failed: {e}", severity="error", timeout=4)

        self.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.SAVE,
                title="Save Project As",
                start_dir=start_dir,
            ),
            _on_path,
        )

    def action_new_project(self) -> None:
        try:
            self.app.action_new_project()  # type: ignore
        except Exception:
            pass

    def action_save_project(self) -> None:
        try:
            self.app.action_save_project()  # type: ignore
        except Exception:
            pass
