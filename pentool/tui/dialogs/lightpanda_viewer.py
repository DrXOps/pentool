"""LightpandaViewer — модальное окно с рендером URL через Lightpanda."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, RichLog

_CSS = """
LightpandaViewer {
    align: center middle;
    background: $surface 50%;
}

#lightpanda-dialog {
    width: 90%;
    height: 90%;
    border: round $primary;
    background: $surface;
}

#lightpanda-header {
    height: 3;
    padding: 0 1;
    text-style: bold;
    background: $primary;
    color: $text;
    content-align: center middle;
}

#lightpanda-body {
    height: 1fr;
    margin: 1;
}

#lightpanda-footer {
    height: 1;
    padding: 0 1;
    color: $text-disabled;
}
"""


class LightpandaViewer(ModalScreen[None]):
    """Modal screen showing a URL rendered via Lightpanda."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close", show=True),
        Binding("ctrl+c", "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        import sys as _sys
        print(f"[LIGHTPANDA] Opening viewer for: {url}", file=_sys.stderr, flush=True)

    def compose(self) -> ComposeResult:
        with Vertical(id="lightpanda-dialog"):
            yield Static(f"Lightpanda: {self._url}", id="lightpanda-header")
            yield RichLog(id="lightpanda-body", highlight=True, markup=True, wrap=True)
            yield Static("Esc / Ctrl+C to close", id="lightpanda-footer")

    def on_mount(self) -> None:
        self.run_worker(self._fetch_and_display())

    async def _fetch_and_display(self) -> None:
        body = self.query_one("#lightpanda-body", RichLog)
        body.write("[dim]Fetching via Lightpanda...[/dim]")
        try:
            proc = await asyncio.create_subprocess_exec(
                "lightpanda", "fetch", "--dump", "markdown", self._url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:500]
                body.clear()
                body.write(f"[red]Lightpanda error (exit={proc.returncode}):[/red]")
                body.write(err)
                return
            body.clear()
            text = stdout.decode("utf-8", errors="replace")
            body.write(text)
        except asyncio.TimeoutError:
            body.clear()
            body.write("[red]Lightpanda timed out after 30s[/red]")
        except FileNotFoundError:
            body.clear()
            body.write("[red]Lightpanda not found. Install: pip install lightpanda[/red]")
        except Exception as exc:
            body.clear()
            body.write(f"[red]Error: {exc}[/red]")