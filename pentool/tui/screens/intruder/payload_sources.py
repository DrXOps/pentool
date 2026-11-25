"""Payload sources of the Intruder module: picking, reading and counting payload files.

Extracted from `IntruderScreen` (docs/tui-audit/REPORT.md, step 5): file picking, the
20 MB eager/streamed decision and the background line counter were four methods of a
3 100-line class, mixed with table rendering and tab state. They now live here, behind a
small host protocol, so the screen keeps only the parts that draw something.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pentool.api.intruder_api import FilePayloadSource, count_lines_with_progress
from pentool.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

logger = get_logger(__name__)

#: Files below this size are read at once; bigger ones are streamed line by line to keep
#: memory flat (a 500 MB wordlist must not become a list of strings).
EAGER_LOAD_MAX_BYTES = 20 * 1024 * 1024


class PayloadHost(Protocol):
    """What the loader needs from the screen — and nothing more."""

    app: Any

    def _active_tab(self) -> Any: ...

    def _refresh_payload_list(self) -> None: ...

    def _update_payload_count_label(self) -> None: ...

    def _auto_save_state(self) -> None: ...

    def err(self, exception: Exception, context: str = "", severity: str = "error") -> None: ...


class PayloadSources:
    """Loads payload files into the active tab's current set."""

    def __init__(self, host: PayloadHost) -> None:
        self._host = host

    # ── Entry point: file dialog ────────────────────────────────────────────

    def pick_and_load(self) -> None:
        """Ask for a file and start loading it into the *currently active* set."""
        tab = self._host._active_tab()
        if tab is None:
            return
        if tab.payload_load_in_progress:
            self._host.app.notify("A payload file is already loading — please wait", severity="warning", timeout=3)
            return

        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        captured_idx = tab.active_set_idx

        def _on_file(path: str | None) -> None:
            if path:
                self._host.run_worker(  # type: ignore[attr-defined]
                    self.load(path, captured_idx),
                    exclusive=False,
                    name="payload-load",
                    exit_on_error=False,
                )

        self._host.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                filter_ext=["*.txt", "*.yaml", "*.yml"],
                title="Select payload file",
            ),
            _on_file,
        )

    # ── Loading ─────────────────────────────────────────────────────────────

    async def load(self, path: str, target_idx: int) -> None:
        """Read *path* into the set at *target_idx*, eager or streamed by size."""
        tab = self._host._active_tab()
        try:
            size = await asyncio.get_running_loop().run_in_executor(None, lambda: Path(path).stat().st_size)
        except Exception as exc:
            logger.warning("payloads: file size not read for %s", path, exc_info=True)
            self._host.err(exc, "Failed to load payload file", severity="error")
            return
        if tab is None:
            return
        while target_idx >= len(tab.payload_sources):
            tab.payload_sources.append([])
        if size <= EAGER_LOAD_MAX_BYTES:
            await self.load_eager(path, target_idx)
        else:
            await self.load_streamed(path, target_idx, size)

    async def load_eager(self, path: str, target_idx: int) -> None:
        from pentool.api.intruder_api import load_payloads_from_file

        tab = self._host._active_tab()
        if tab is None:
            return
        try:
            loop = asyncio.get_running_loop()
            payloads = await loop.run_in_executor(None, load_payloads_from_file, path)
        except Exception as exc:
            logger.warning("payloads: %s not read", path, exc_info=True)
            self._host.err(exc, "Failed to load payload (eager)", severity="error")
            return
        existing = tab.payload_sources[target_idx]
        if not isinstance(existing, list):
            # A generated/file-backed set cannot be extended line by line — replace it.
            tab.payload_sources[target_idx] = payloads
        else:
            existing.extend(payloads)
        if target_idx == tab.active_set_idx:
            self._host._refresh_payload_list()
        self._host.app.notify(f"Loaded {len(payloads)} payloads from {Path(path).name}", timeout=3)
        self._host._auto_save_state()

    async def load_streamed(self, path: str, target_idx: int, size_bytes: int) -> None:
        tab = self._host._active_tab()
        if tab is None:
            return
        tab.payload_load_in_progress = True
        source = FilePayloadSource(path)
        tab.payload_sources[target_idx] = source
        if target_idx == tab.active_set_idx:
            self._host._refresh_payload_list()
        name = Path(path).name
        self._host.app.notify(
            f"Loading {name} ({size_bytes / (1024 * 1024):.0f} MB) — streaming, counting lines in background…",
            timeout=4,
        )

        def _on_progress(count: int, bytes_read: int, total_bytes: int) -> None:
            self._host.app.call_from_thread(self._show_count_progress, target_idx, count, bytes_read, total_bytes)

        try:
            loop = asyncio.get_running_loop()
            final_count = await loop.run_in_executor(None, count_lines_with_progress, path, "utf-8", _on_progress)
            source.set_count(final_count)
        except Exception as exc:
            # The set is still usable: the source streams lines, only the count is off.
            logger.warning("payloads: line count failed for %s", path, exc_info=True)
            self._host.err(exc, "Payload line count failed (still usable)", severity="warning")
        finally:
            tab.payload_load_in_progress = False
            if target_idx == tab.active_set_idx:
                self._host._update_payload_count_label()
            self._host._auto_save_state()

    # ── Progress in the count label ─────────────────────────────────────────

    def _show_count_progress(self, target_idx: int, count: int, bytes_read: int, total_bytes: int) -> None:
        """Show "N lines counted so far (42%)" while the counter works."""
        tab = self._host._active_tab()
        if tab is None:
            return
        active = tab.payload_sources[target_idx] if target_idx < len(tab.payload_sources) else None
        if not isinstance(active, FilePayloadSource):
            return
        if target_idx != tab.active_set_idx:
            return
        update = getattr(self._host, "update_payload_count_label", None)
        if callable(update):
            percent = f" ({bytes_read / total_bytes * 100:.0f}%)" if total_bytes else ""
            update(f"{count:,} line(s) counted so far{percent}…")
