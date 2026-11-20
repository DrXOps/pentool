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

from pathlib import Path

import psutil
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.logging import get_logger

logger = get_logger(__name__)

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

    DEFAULT_CSS = (Path(__file__).parent / "live_dashboard.tcss").read_text(encoding="utf-8")

    @staticmethod
    def _get_git_branch(root: Path) -> str:
        """Get current git branch name from .git/HEAD."""
        try:
            head = root / ".git" / "HEAD"
            if head.exists():
                ref = head.read_text(encoding="utf-8").strip()
                if ref.startswith("ref: refs/heads/"):
                    return ref[16:]
                # detached HEAD — show short hash
                return ref[:8]
        except Exception as exc:
            # Панель покажет "?" вместо ветки — а ещё это единственный случай,
            # когда git-репозиторий у проекта есть, но HEAD прочитать нельзя.
            logger.debug("resource monitor: git branch not read: %s", exc)
        return "?"

    def compose(self) -> ComposeResult:
        yield Static("[bold]┌─ RESOURCES ─[/bold]")
        yield Static("", id="res-cpu")
        yield Static("", id="res-ram")
        yield Static("", id="res-extra")
        yield Static("", id="res-version")

    def on_mount(self) -> None:
        self.set_interval(2.0, self._update)

    def _update(self) -> None:
        # Hidden screens stay mounted (`ContentSwitcher`), so without this guard
        # the resource panel kept polling psutil and repainting itself while the
        # user worked in another module (measured: ~240 ms of work per idle
        # second with the dashboard hidden behind Proxy).
        if not self.display:
            return
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
                self.query_one("#res-extra", Static).update(f"[dim]system threads: {threads}[/dim]")
            except Exception as exc:
                # Строка «system threads» останется пустой — сама по себе
                # косметика, но повтор раз в 2 с означает сломанный psutil.
                logger.debug("resource monitor: threads not read: %s", exc)
            # Version info: show dev mode when running from source
            try:
                from pentool import __version__

                pentool_root = Path(__file__).resolve().parent.parent.parent.parent.parent
                is_dev = (pentool_root / ".git").exists()
                if is_dev:
                    branch = self._get_git_branch(pentool_root)
                    self.query_one("#res-version", Static).update(
                        f"[bold green]DEV[/bold green] [bold]{__version__}[/bold] [dim]({branch})[/dim]"
                    )
                else:
                    self.query_one("#res-version", Static).update(f"[dim]v{__version__}[/dim]")
            except Exception as exc:
                # Поле версии пустое — не видно ни версии, ни DEV-режима, и
                # именно это первое, что просят в отчёте об ошибке.
                logger.debug("resource monitor: version line not drawn: %s", exc)
        except ImportError:
            try:
                self.query_one("#res-cpu", Static).update("[dim]psutil not installed[/dim]")
            except NoMatches as exc:
                # Причина пустой панели ресурсов пользователю не сообщается.
                logger.debug("resource monitor: psutil notice not shown: %s", exc)
        except Exception as exc:
            # Тик монитора целиком пропущен: панель показывает цифры
            # предыдущего тика, будто система не меняется.
            logger.debug("resource monitor: update skipped: %s", exc)
