"""Built-in terminal based on pty / libtmux."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import threading
import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import RichLog, Static
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

class TerminalScreen(Widget):
    """Built-in terminal with pty / libtmux support."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("ctrl+shift+t", "new_terminal", "New Terminal", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pty_master: int | None = None
        self._shell_pid: int | None = None
        self._reader_thread: threading.Thread | None = None
        self._running: bool = False
        self._tmux_session: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("Terminal", id="term-statusbar")
        yield RichLog(id="term-log", highlight=False, markup=False, wrap=True)
        yield Static("Shift+X to open terminal tab  |  Ctrl+Shift+T to restart", id="term-hint")

    def on_mount(self) -> None:
        self._start_terminal()

    def _start_terminal(self) -> None:
        if self._try_tmux():
            return
        self._start_pty()

    def _try_tmux(self) -> bool:
        """Try to open a tmux session via libtmux."""
        try:
            import libtmux  # type: ignore[import]
            server = libtmux.Server()
            session_name = "pentool-terminal"
            try:
                session = server.sessions.get(session_name=session_name)
                if session is None:
                    session = server.new_session(session_name=session_name)
            except Exception:
                session = server.new_session(session_name=session_name)
            self._tmux_session = session_name
            self._update_statusbar(f"tmux: {session_name}")
            try:
                log = self.query_one("#term-log", RichLog)
                log.write(f"[bold green]tmux session '{session_name}' active.[/bold green]")
                log.write("Attach: [italic]tmux attach -t pentool-terminal[/italic]")
                log.write("Or run commands in the session directly.")
            except Exception:
                pass
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _start_pty(self) -> None:
        try:
            import pty
            master_fd, slave_fd = pty.openpty()
            shell = os.environ.get("SHELL", "/bin/bash")
            proc = subprocess.Popen(
                [shell, "--login"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                preexec_fn=os.setsid,
            )
            os.close(slave_fd)
            self._pty_master = master_fd
            self._shell_pid = proc.pid
            self._running = True
            self._update_statusbar(f"Shell: {shell} (pid {proc.pid})")
            # Write welcome message
            try:
                log = self.query_one("#term-log", RichLog)
                log.write(f"Shell started: {shell}")
                log.write("Type commands and press Enter to send (not interactive yet)")
            except Exception:
                pass
            self._reader_thread = threading.Thread(
                target=self._read_pty, daemon=True, name="pty-reader"
            )
            self._reader_thread.start()
        except Exception as exc:
            try:
                log = self.query_one("#term-log", RichLog)
                log.write(f"Terminal unavailable: {exc}")
                log.write("")
                log.write("To use a terminal, open a new terminal window")
                log.write("and run: [bold]pentool[/bold]")
            except Exception:
                pass
            self._update_statusbar("Terminal: not available in this environment")

    def _read_pty(self) -> None:
        """Read output from pty and append to RichLog (in a thread)."""
        while self._running:
            fd = self._pty_master
            if fd is None:
                break
            try:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    data = os.read(fd, 4096)
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    self.app.call_from_thread(self._append_output, text)
            except OSError:
                break

    def _append_output(self, text: str) -> None:
        try:
            log = self.query_one("#term-log", RichLog)
            log.write(text)
        except Exception:
            pass

    def _update_statusbar(self, text: str) -> None:
        try:
            self.query_one("#term-statusbar", Static).update(f"Terminal — {text}")
        except Exception:
            pass

    def action_new_terminal(self) -> None:
        self._stop()
        try:
            log = self.query_one("#term-log", RichLog)
            log.clear()
        except Exception:
            pass
        self._start_terminal()

    def _stop(self) -> None:
        self._running = False
        if self._shell_pid:
            try:
                os.kill(self._shell_pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                time.sleep(0.3)
                os.kill(self._shell_pid, signal.SIGKILL)
            except Exception:
                pass
            self._shell_pid = None
        if self._pty_master is not None:
            try:
                os.close(self._pty_master)
            except Exception:
                pass
            self._pty_master = None
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def on_unmount(self) -> None:
        self._stop()
