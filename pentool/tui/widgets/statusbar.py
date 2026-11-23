"""Status bar: proxy, project, time."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from pentool.tui.mixins.safe_query import safe_query_one
from pentool.tui.widgets.activity_indicator import ActivityIndicator

_CSS = (Path(__file__).parent / "statusbar.tcss").read_text(encoding="utf-8")


class _Left(Horizontal):
    """Left half: proxy, project, activity."""


class _Right(Horizontal):
    """Right half: saved, time — right-aligned."""


class StatusBar(Widget):
    """Bottom bar with proxy state, project name, activity indicator and time."""

    DEFAULT_CSS = _CSS

    proxy_running: reactive[bool] = reactive(False)
    proxy_port: reactive[int] = reactive(8080)
    project_name: reactive[str] = reactive("no project")
    project_path: reactive[str] = reactive("")
    project_saved: reactive[bool] = reactive(True)
    current_time: reactive[str] = reactive("")

    def __init__(
        self,
        *children: Widget,
        now: Callable[[], datetime] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        markup: bool = True,
    ) -> None:
        """``now`` is the clock seam.

        The bar prints the wall clock every second, so a screenshot of it can
        never be byte-stable across runs. Snapshot tests hand in a frozen
        clock instead of normalising the time out of the SVG afterwards — the
        normalised baseline would also hide a real change to the time format.
        """
        super().__init__(
            *children,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
            markup=markup,
        )
        self._now: Callable[[], datetime] = now or datetime.now

    def compose(self) -> ComposeResult:
        with _Left():
            yield Static("", id="proxy-status", classes="status-proxy stopped")
            yield Static("", id="project-name", classes="status-project")
        with _Right():
            yield Static("", id="right-spacer", classes="right-spacer")
            yield ActivityIndicator(self.app, id="activity-indicator")
            yield Static("", id="saved-status", classes="status-saved")
            yield Static("", id="current-time", classes="status-time")

    def on_mount(self) -> None:
        self._update_proxy()
        self._update_project()
        self._update_saved()
        self._update_time()
        self.set_interval(1.0, self._update_time)

    def _update_proxy(self) -> None:
        # The bar ticks once per second from on_mount; a child can be missing
        # during the first layout pass, and an exception in a clock tick would
        # take the whole TUI down.
        widget = safe_query_one(self, "#proxy-status", Static, context="statusbar: proxy status")
        if widget is None:
            return
        if self.proxy_running:
            widget.update(f"[green]● Proxy :{self.proxy_port}[/green]")
            widget.remove_class("stopped")
            widget.add_class("running")
        else:
            widget.update("[red]○ Proxy stopped[/red]")
            widget.remove_class("running")
            widget.add_class("stopped")

    def _update_project(self) -> None:
        name = self.project_name
        path = self.project_path
        if name == "no project":
            markup = "[dim]no project[/dim]"
        elif path:
            markup = f"[dim]project:[/dim] [bold cyan]{name}[/bold cyan] [dim]{path}[/dim]"
        else:
            markup = f"[dim]project:[/dim] [bold cyan]{name}[/bold cyan]"
        widget = safe_query_one(self, "#project-name", Static, context="statusbar: project name")
        if widget is not None:
            widget.update(markup)

    def _update_saved(self) -> None:
        widget = safe_query_one(self, "#saved-status", Static, context="statusbar: saved status")
        if widget is None:
            return
        if self.project_name == "no project":
            widget.update("")
        elif self.project_saved:
            widget.update("[dim green]● Saved[/dim green]")
        else:
            widget.update("[yellow]● Unsaved[/yellow]")

    def _update_time(self) -> None:
        widget = safe_query_one(self, "#current-time", Static, context="statusbar: clock")
        if widget is not None:
            widget.update(self._now().strftime("%H:%M:%S"))

    def set_proxy_status(self, running: bool, port: int = 8080) -> None:
        self.proxy_running = running
        self.proxy_port = port
        self._update_proxy()

    def set_project_name(self, name: str) -> None:
        self.project_name = name
        self._update_project()
        self._update_saved()

    def set_project(self, name: str, path: str, saved: bool = True) -> None:
        self.project_name = name
        self.project_path = path
        self.project_saved = saved
        self._update_project()
        self._update_saved()

    def set_saved(self, saved: bool) -> None:
        self.project_saved = saved
        self._update_saved()
