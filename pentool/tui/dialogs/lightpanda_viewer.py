"""LightpandaViewer — модальное окно с рендером URL через Lightpanda."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from pentool.core.logging import get_logger
from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.markup import esc

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "lightpanda_viewer.tcss").read_text(encoding="utf-8")


class LightpandaViewer(BaseDialog[None]):
    """Modal screen showing a URL rendered via Lightpanda."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close", show=True),
        Binding("ctrl+c", "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        logger.info("Opening LightpandaViewer for: %s", url)

    def compose(self) -> ComposeResult:
        with Vertical(id="lightpanda-dialog"):
            yield Static(f"Lightpanda: {esc(self._url)}", id="lightpanda-header")
            yield RichLog(id="lightpanda-body", highlight=True, markup=True, wrap=True)
            yield Static("Esc / Ctrl+C to close", id="lightpanda-footer")

    def on_mount(self) -> None:
        self.run_worker(self._fetch_and_display())

    async def _fetch_and_display(self) -> None:
        body = self.query_one("#lightpanda-body", RichLog)
        body.write("[dim]Fetching via Lightpanda...[/dim]")
        try:
            proc = await asyncio.create_subprocess_exec(
                "lightpanda",
                "fetch",
                "--dump",
                "markdown",
                self._url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:500]
                body.clear()
                body.write(f"[red]Lightpanda error (exit={proc.returncode}):[/red]")
                body.write(esc(err))
                return
            body.clear()
            text = stdout.decode("utf-8", errors="replace")
            body.write(esc(text))
        except asyncio.TimeoutError:
            body.clear()
            body.write("[red]Lightpanda timed out after 30s[/red]")
        except FileNotFoundError:
            body.clear()
            body.write("[red]Lightpanda not found. Install: pip install lightpanda[/red]")
        except Exception as exc:
            body.clear()
            body.write(f"[red]Error: {esc(exc)}[/red]")
