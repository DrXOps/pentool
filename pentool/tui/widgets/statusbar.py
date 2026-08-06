"""Status bar: proxy, project, time."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from pentool.tui.widgets.activity_indicator import ActivityIndicator

_CSS = (Path(__file__).parent / "statusbar.tcss").read_text(encoding="utf-8")


class StatusBar(Widget):
    """Bottom bar with proxy state, project name, activity indicator and time."""

    DEFAULT_CSS = _CSS

    proxy_running: reactive[bool] = reactive(False)
    proxy_port: reactive[int] = reactive(8080)
    project_name: reactive[str] = reactive("no project")
    project_path: reactive[str] = reactive("")
    project_saved: reactive[bool] = reactive(True)
    current_time: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", id="proxy-status", classes="status-proxy stopped")
        yield Static("", id="project-name", classes="status-project")
        yield Static("", id="saved-status", classes="status-saved")
        # Global "what's running" strip — separate plate to the right of
        # project/saved status, left of the clock (see ActivityIndicator
        # docstring for why this polls instead of subscribing to events).
        yield ActivityIndicator(self.app, id="activity-indicator")
        yield Static("", id="current-time", classes="status-time")

    def on_mount(self) -> None:
        self._update_proxy()
        self._update_project()
        self._update_saved()
        self._update_time()
        self.set_interval(1.0, self._update_time)

    def _update_proxy(self) -> None:
        widget = self.query_one("#proxy-status", Static)
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
        self.query_one("#project-name", Static).update(markup)

    def _update_saved(self) -> None:
        widget = self.query_one("#saved-status", Static)
        if self.project_name == "no project":
            widget.update("")
        elif self.project_saved:
            widget.update("[dim green]● Saved[/dim green]")
        else:
            widget.update("[yellow]● Unsaved[/yellow]")

    def _update_time(self) -> None:
        self.query_one("#current-time", Static).update(
            datetime.now().strftime("%H:%M:%S")
        )

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
