"""Sequencer screen — token entropy analysis."""

from __future__ import annotations

import os
import re
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, Label, RichLog, Static, TextArea

from pentool.core.logging import get_logger
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

_SOURCE_OPTIONS = [
    ("Manual input",  "manual"),
    ("Proxy param",   "proxy"),
    ("Cookie header", "cookie"),
    ("Body regex",    "body_regex"),
]


class SequencerScreen(Widget):
    """Capture and entropy analysis of tokens (session IDs, CSRF, JWT…)."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("ctrl+enter", "analyze",       "Analyze",  show=True),
        Binding("ctrl+l",     "clear_tokens",  "Clear",    show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        from pentool.api.sequencer_api import Sequencer
        self._seq = Sequencer()
        self._capturing = False       # live-capture mode from proxy
        self._capture_param: str = "" # parameter/cookie name to capture
        self._proxy_hook = None       # reference for unsubscribe
        self._source: str = "manual"  # currently selected source

    def compose(self) -> ComposeResult:
        # ── Toolbar ────────────────────────────────────────────────────────────
        with Horizontal(id="seq-toolbar"):
            yield ToolbarButton("▶ Capture",   "btn-seq-capture")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("■ Stop",      "btn-seq-stop",    classes="disabled")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("⚡ Analyze",   "btn-seq-analyze")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("📂 Load File", "btn-seq-load")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("🗑 Clear",     "btn-seq-clear")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("📋 Copy",      "btn-seq-copy")
            yield Static(" │ ", classes="seq-sep")
            yield ToolbarButton("💾 Export",    "btn-seq-export")

        # ── Config row ─────────────────────────────────────────────────────────
        with Horizontal(id="seq-config-row"):
            yield Label("Source:", classes="seq-cfg-label")
            yield ToolbarButton("Manual input ▼", "btn-seq-source")
            yield Label("  Param:", classes="seq-cfg-label")
            yield Input(
                placeholder="cookie/header param name",
                id="seq-param-input",
                compact=True,
            )
            yield Static("Captured: 0", id="seq-counter")

        # ── Summary bar ────────────────────────────────────────────────────────
        with Horizontal(id="seq-summary-bar"):
            yield Static(
                "[dim]— Add tokens manually or capture from Proxy, then press Analyze —[/dim]",
                id="seq-summary", markup=True,
            )

        # ── Main area ──────────────────────────────────────────────────────────
        with Horizontal(id="seq-main-area"):
            # Left column: token input (one per line)
            with Vertical(id="seq-input-col"):
                yield Static("Tokens (one per line)", id="seq-tokens-label",
                             classes="seq-col-label")
                yield TextArea(id="seq-token-area", language=None)

            yield ResizeHandle("seq-input-col", "seq-analysis-col", id="seq-resize-h")

            # Right column: analysis results
            with Vertical(id="seq-analysis-col"):
                yield Static("Analysis", id="seq-analysis-label",
                             classes="seq-col-label")
                yield RichLog(id="seq-analysis-log", highlight=True, markup=True,
                              wrap=True, max_lines=500)

        yield ResizeHandle("seq-main-area", "seq-gauge-area", vertical=True, id="seq-resize-v")

        # ── Entropy gauge ──────────────────────────────────────────────────────
        with Vertical(id="seq-gauge-area"):
            yield Static("ENTROPY", id="seq-gauge-label")
            yield Static(" ", id="seq-gauge")
            yield Static(" ", id="seq-assessment")
            yield Static(" ", id="seq-bits-label")

        yield Static(
            "▶ Capture: start live capture  │  ⚡ Analyze: run entropy analysis"
            "  │  📂 Load File: load tokens from file  │  💾 Export: save results",
            id="status-bar",
        )

    # ── Toolbar ───────────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-seq-capture")
    def on_btn_seq_capture(self, _: ToolbarButton.Pressed) -> None:
        self._start_capture()

    @on(ToolbarButton.Pressed, "#btn-seq-stop")
    def on_btn_seq_stop(self, _: ToolbarButton.Pressed) -> None:
        self._stop_capture()

    @on(ToolbarButton.Pressed, "#btn-seq-analyze")
    def on_btn_seq_analyze(self, _: ToolbarButton.Pressed) -> None:
        self.action_analyze()

    @on(ToolbarButton.Pressed, "#btn-seq-load")
    def on_btn_seq_load(self, _: ToolbarButton.Pressed) -> None:
        self._load_file()

    @on(ToolbarButton.Pressed, "#btn-seq-clear")
    def on_btn_seq_clear(self, _: ToolbarButton.Pressed) -> None:
        self.action_clear_tokens()

    @on(ToolbarButton.Pressed, "#btn-seq-copy")
    def on_btn_seq_copy(self, _: ToolbarButton.Pressed) -> None:
        self._copy_report()

    @on(ToolbarButton.Pressed, "#btn-seq-export")
    def on_btn_seq_export(self, _: ToolbarButton.Pressed) -> None:
        self._export_report()

    @on(ToolbarButton.Pressed, "#btn-seq-source")
    def on_btn_seq_source(self, event: ToolbarButton.Pressed) -> None:
        self._open_source_menu(event.button)

    def _open_source_menu(self, btn: ToolbarButton) -> None:
        items = [
            (val, ("✓ " if val == self._source else "  ") + label)
            for label, val in _SOURCE_OPTIONS
        ]
        r = btn.region
        self.app.show_context_menu(items, r.x, r.y + 1, callback=self._on_source_selected)

    def _on_source_selected(self, val: str) -> None:
        self._source = val
        label = next((l for l, v in _SOURCE_OPTIONS if v == val), val)
        try:
            btn = self.query_one("#btn-seq-source", ToolbarButton)
            btn.label = f"{label} ▼"
        except Exception:
            pass

    def _start_capture(self) -> None:
        """Start capturing tokens from the proxy."""
        try:
            src = self._source
            param = self.query_one("#seq-param-input", Input).value.strip()

            if src in ("proxy", "cookie", "body_regex"):
                proxy_api = getattr(self.app, "_proxy_api", None)
                if not proxy_api:
                    self.app.notify("Proxy not available", severity="warning")
                    return
                if src in ("proxy", "cookie") and not param:
                    self.app.notify("Enter param/cookie name to capture", severity="warning")
                    return
                if src == "body_regex" and not param:
                    self.app.notify("Enter regex pattern for body extraction", severity="warning")
                    return
                self._capturing = True
                self._capture_param = param
                self._attach_proxy_hook(proxy_api, param, src)
                src_labels = {"proxy": "param", "cookie": "cookie", "body_regex": "regex"}
                self.app.notify(
                    f"Capturing '{param}' ({src_labels[src]}) from Proxy…", timeout=3
                )
            else:
                self.app.notify("Switch to Proxy/Cookie/Body source for live capture", severity="info")
                return

            self.query_one("#btn-seq-capture", ToolbarButton).disabled = True
            self.query_one("#btn-seq-stop",    ToolbarButton).disabled = False
        except Exception as exc:
            logger.debug("_start_capture: %s", exc)

    def _attach_proxy_hook(self, proxy_api, param: str, source: str = "proxy") -> None:
        """Subscribe to proxy requests for token extraction.

        Args:
            proxy_api: ProxyAPI object used to look up requests.
            param: Parameter/cookie name or regex pattern.
            source: "proxy" — any header/query; "cookie" — Cookie header only;
                    "body_regex" — regex against the response body.
        """
        from pentool.core.event_bus import get_event_bus
        from pentool.core.events import ProxyRequestDoneEvent

        def _on_proxy_request(event: ProxyRequestDoneEvent) -> None:
            if not self._capturing:
                return
            try:
                req = proxy_api.find_request(event.request_id)
                if req is None:
                    return

                token = None

                if source == "cookie":
                    # Cookie header only
                    for hdr_name, hdr_val in (req.headers or {}).items():
                        if hdr_name.lower() == "cookie":
                            token = self._seq.extract_from_header(hdr_val, param)
                            break

                elif source == "body_regex":
                    # Regex against the response body
                    resp = getattr(req, "response", None)
                    body = ""
                    if resp is not None:
                        body = getattr(resp, "body", "") or ""
                    if body:
                        try:
                            m = re.search(param, body)
                            if m:
                                token = m.group(1) if m.lastindex else m.group(0)
                        except re.error:
                            pass

                else:
                    # "proxy" — Cookie + query string + response headers
                    for hdr_name, hdr_val in (req.headers or {}).items():
                        if hdr_name.lower() == "cookie":
                            token = self._seq.extract_from_header(hdr_val, param)
                            if token:
                                break
                    if not token:
                        # Try response Set-Cookie
                        resp = getattr(req, "response", None)
                        if resp is not None:
                            for hdr_name, hdr_val in (getattr(resp, "headers", None) or {}).items():
                                if hdr_name.lower() in ("set-cookie", "authorization"):
                                    token = self._seq.extract_from_header(hdr_val, param)
                                    if token:
                                        break

                if token:
                    self.call_from_thread(self._update_counter)
            except Exception as exc:
                logger.debug("_on_proxy_request hook: %s", exc)

        self._proxy_hook = _on_proxy_request
        get_event_bus().subscribe(ProxyRequestDoneEvent, _on_proxy_request)

    def _stop_capture(self) -> None:
        self._capturing = False
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestDoneEvent
            if hasattr(self, "_proxy_hook"):
                get_event_bus().unsubscribe(ProxyRequestDoneEvent, self._proxy_hook)
        except Exception:
            pass
        try:
            self.query_one("#btn-seq-capture", ToolbarButton).disabled = False
            self.query_one("#btn-seq-stop",    ToolbarButton).disabled = True
        except Exception:
            pass
        self.app.notify("Capture stopped", timeout=2)

    def _update_counter(self) -> None:
        try:
            self.query_one("#seq-counter", Static).update(
                f"Captured: [bold]{self._seq.count}[/bold]"
            )
        except Exception:
            pass

    def _load_file(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path or not os.path.exists(path):
                return
            try:
                text = Path(path).read_text(encoding="utf-8", errors="replace")
                added = self._seq.add_from_text(text)
                # Update TextArea
                self.query_one("#seq-token-area", TextArea).load_text(
                    "\n".join(self._seq.tokens)
                )
                self._update_counter()
                self.app.notify(f"Loaded {added} tokens from {os.path.basename(path)}", timeout=3)
            except Exception as exc:
                self.app.notify(f"Load failed: {exc}", severity="error")

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.OPEN, title="Load Tokens"),
            _on_path,
        )

    def _copy_report(self) -> None:
        try:
            from pentool.utils.copy_as import copy_to_clipboard
            report = self._seq.analyze()
            text = re.sub(r"\[/?[^\]]+\]", "", report.summary())
            if copy_to_clipboard(text):
                self.app.notify("Report copied", timeout=2)
        except Exception as exc:
            self.app.notify(f"Copy failed: {exc}", severity="error")

    def _export_report(self) -> None:
        if self._seq.count == 0:
            self.app.notify("No tokens to export", severity="warning")
            return

        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            try:
                report = self._seq.analyze()
                lines: list[str] = []
                lines.append("=" * 60)
                lines.append("PENTOOL — Sequencer Analysis Report")
                lines.append("=" * 60)
                lines.append("")
                lines.append(f"Token Count:  {report.token_count}")
                lines.append(f"Length:       {report.min_length}–{report.max_length} (avg {report.avg_length:.1f})")
                lines.append(f"Charset:      ~{report.charset_estimate} chars")
                lines.append(f"Entropy:      {report.mean_entropy:.3f} bits/char")
                lines.append(f"Total bits:   {report.mean_total_bits:.1f}")
                lines.append(f"Effective:    {report.effective_bits:.1f} bits")
                lines.append(f"Duplicates:   {report.duplicates}")
                lines.append(f"Assessment:   {report.assessment}")
                lines.append("")
                lines.append("── FIPS 140-2 Statistical Tests ──")
                if report.fips_results:
                    for r in report.fips_results:
                        lo = str(r.threshold_low) if r.threshold_low is not None else "—"
                        hi = str(r.threshold_high) if r.threshold_high is not None else "—"
                        lines.append(
                            f"  {r.status:<10} {r.name:<22} value={r.value}  range={lo}–{hi}"
                        )
                    all_pass = all(r.passed for r in report.fips_results)
                    lines.append(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME TESTS FAILED'}")
                else:
                    lines.append("  (insufficient data)")
                lines.append("")
                lines.append("── Tokens ──")
                for tok in report.tokens:
                    lines.append(f"  {tok}")
                import os
                if not path.endswith(".txt"):
                    path = path + ".txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.app.notify(
                    f"Report exported → {os.path.basename(path)}", timeout=3
                )
            except Exception as exc:
                self.app.notify(f"Export failed: {exc}", severity="error")

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Export Report"),
            _on_path,
        )

    # ── Analyze ───────────────────────────────────────────────────────────────

    def action_analyze(self) -> None:
        """Sync tokens from TextArea and run analysis."""
        try:
            # Sync manual input into Sequencer
            ta_text = self.query_one("#seq-token-area", TextArea).text.strip()
            if ta_text:
                self._seq.clear()
                self._seq.add_from_text(ta_text)

            if self._seq.count == 0:
                self.app.notify("No tokens to analyze", severity="warning")
                return

            self._update_counter()
            report = self._seq.analyze()
            self._render_report(report)
        except Exception as exc:
            self.app.notify(f"Analyze error: {exc}", severity="error")
            logger.debug("action_analyze: %s", exc)

    def _render_report(self, report) -> None:
        """Render the report in the UI."""
        try:
            log = self.query_one("#seq-analysis-log", RichLog)
            log.clear()

            # Summary statistics
            log.write(f"[bold cyan]── Token Analysis ── {report.token_count} tokens ──[/bold cyan]")
            log.write("")
            log.write(f"[bold]Count:[/bold]       {report.token_count}")
            log.write(f"[bold]Length:[/bold]      {report.min_length}–{report.max_length} chars (avg {report.avg_length:.1f})")
            log.write(f"[bold]Charset:[/bold]     ~{report.charset_estimate} chars")
            log.write(f"[bold]Entropy:[/bold]     {report.mean_entropy:.3f} bits/char")
            log.write(f"[bold]Total bits:[/bold]  {report.mean_total_bits:.1f}")
            log.write(f"[bold]Effective:[/bold]   {report.effective_bits:.1f} bits")
            if report.duplicates:
                log.write(f"[bold red]Duplicates:[/bold red] [red]{report.duplicates}[/red]")
            log.write("")

            # Length histogram
            log.write(report.rich_histogram(width=25))
            log.write("")

            # Character frequency (top 15)
            log.write(report.rich_charfreq(top_n=15))

            # FIPS 140-2 tests
            log.write("")
            log.write(report.rich_fips())

            # Position anomalies (for fixed-length tokens)
            log.write("")
            log.write(report.rich_position_anomalies())

            # Summary
            log.write("")
            log.write(f"[bold]Summary:[/bold] {report.summary()}")

            # Gauge
            self._render_gauge(report)
            # Summary bar
            self.query_one("#seq-summary", Static).update(report.summary())

        except Exception as exc:
            logger.debug("_render_report: %s", exc)

    def _render_gauge(self, report) -> None:
        """Render the entropy gauge in the bottom panel."""
        try:
            bits = report.effective_bits
            max_bits = 256.0
            width = 48
            filled = int((bits / max_bits) * width)
            filled = max(0, min(width, filled))

            if bits < 32:
                color = "bold red"
            elif bits < 64:
                color = "yellow"
            elif bits < 128:
                color = "green"
            else:
                color = "bold green"

            bar = "█" * filled + "░" * (width - filled)
            self.query_one("#seq-gauge", Static).update(
                f"[{color}]{bar}[/{color}] [{color}]{bits:.0f} bits[/{color}]"
            )
            assessment = report.assessment
            a_color = "bold red" if "WEAK" in assessment else (
                "yellow" if "MODERATE" in assessment else (
                    "bold green" if "STRONG" in assessment else "green"
                )
            )
            self.query_one("#seq-assessment", Static).update(
                f"[{a_color}]{assessment}[/{a_color}]"
            )
            self.query_one("#seq-bits-label", Static).update(
                f"[dim]Entropy: {report.mean_entropy:.3f} bits/char × "
                f"{report.avg_length:.1f} chars avg = {report.mean_total_bits:.1f} bits[/dim]"
            )
        except Exception as exc:
            logger.debug("_render_gauge: %s", exc)

    # ── Clear ─────────────────────────────────────────────────────────────────

    def action_clear_tokens(self) -> None:
        self._seq.clear()
        try:
            self.query_one("#seq-token-area", TextArea).load_text("")
            self.query_one("#seq-analysis-log", RichLog).clear()
            self.query_one("#seq-counter", Static).update("Captured: 0")
            self.query_one("#seq-summary", Static).update(
                "[dim]— Add tokens manually or capture from Proxy, then press Analyze —[/dim]"
            )
            self.query_one("#seq-gauge",      Static).update(" ")
            self.query_one("#seq-assessment", Static).update(" ")
            self.query_one("#seq-bits-label", Static).update(" ")
        except Exception as exc:
            logger.debug("action_clear_tokens: %s", exc)

    def on_unmount(self) -> None:
        self._stop_capture()

    # ── Public API ────────────────────────────────────────────────────────────

    def add_token(self, token: str) -> None:
        self._seq.add_token(token)
        self.call_from_thread(self._update_counter)
