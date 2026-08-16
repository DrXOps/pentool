"""Live dashboard widgets.

Currently a single live widget on the Dashboard: ``ResourceMonitor`` (CPU/RAM
thermometers). Renderable helpers ``_hbar`` / ``_color_by_percent`` are shared
with it.

Note: the original module also defined an unwired ``LiveDashboardTab`` container
plus TrafficSparkline / BubbleChart / ScanSpeedometer / HeatmapWidget / EventFeed
/ EmergencyStop / MiniSiteMap — none of those were ever mounted anywhere in
production, so they were removed as dead code (2026-08-16).
"""

from __future__ import annotations

import psutil

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


# ── Helper functions ───────────────────────────────────────────────────────

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


# ── Resource Monitor ───────────────────────────────────────────────────────

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
