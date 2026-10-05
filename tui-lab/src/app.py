"""TUI Lab — стенд для ContentPanel vs ContentBlockWrapper.

Запуск:
    cd tui-lab
    uv run python src/app.py
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header, RichLog, Static, TextArea

from content_block_wrapper import ContentBlockWrapper
from log_panel import ContentPanel, ToolbarButton

_CSS = (Path(__file__).parent / "app.tcss").read_text(encoding="utf-8")


class TuiLab(App):
    """Тестовый стенд ContentPanel vs ContentBlockWrapper."""

    CSS = _CSS

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # ═══════════════════════════════════════════════════════════════
        # СЕКЦИЯ 1: ContentPanel (существующая — ToolbarButton)
        # ═══════════════════════════════════════════════════════════════
        yield Static("═══  ContentPanel (ToolbarButton) — существующая  ═══",
                     classes="section-title")
        with Horizontal(classes="row-multilog"):
            yield ContentPanel(
                "RichLog (toolbar кнопки)",
                widget_type="richlog", wrap=True, max_lines=100,
            )
            yield ContentPanel(
                "TextArea (toolbar кнопки)",
                widget_type="textarea", textarea_language="http",
                initial_text="GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
                buttons=["copy", "paste", "clear"],
            )

        # ═══════════════════════════════════════════════════════════════
        # СЕКЦИЯ 2: ContentBlockWrapper (новая — обычные Button)
        # ═══════════════════════════════════════════════════════════════
        yield Static("═══  ContentBlockWrapper (Button из textual.widgets) — НОВАЯ  ═══",
                     classes="section-title")
        yield Static(
            "[dim]Панель с обычными Button, а не ToolbarButton. "
            "Посмотри как выглядят, сравни клики.[/dim]",
            classes="item-label",
        )
        with Horizontal(classes="row-multilog"):
            yield ContentBlockWrapper(
                "RichLog (обычные Button)",
                widget_type="richlog", wrap=True, max_lines=100,
                buttons=["📋 Копия", "✕ Очистить", "✚ Тест"],
            )
            yield ContentBlockWrapper(
                "TextArea (обычные Button)",
                widget_type="textarea",
                textarea_language="http",
                initial_text="POST /api HTTP/1.1\r\nHost: test.com\r\n\r\n{\"key\": \"val\"}",
                buttons=["📋", "✕", "📥"],
            )

        # ═══════════════════════════════════════════════════════════════
        # СЕКЦИЯ 3: Сравнение в лоб — два идентичных блока рядом
        # ═══════════════════════════════════════════════════════════════
        yield Static("═══  Сравнение: ContentPanel vs ContentBlockWrapper (рядом)  ═══",
                     classes="section-title")
        yield Static(
            "[dim]Слева — ContentPanel (ToolbarButton), "
            "справа — ContentBlockWrapper (Button)[/dim]",
            classes="item-label",
        )
        with Horizontal(classes="row-multilog"):
            yield ContentPanel(
                "ContentPanel",
                widget_type="richlog", wrap=True, max_lines=50,
                buttons=["copy", "clear", "wrap"],
            )
            yield ContentBlockWrapper(
                "ContentBlockWrapper",
                widget_type="richlog", wrap=True, max_lines=50,
                buttons=["📋", "✕", "↩"],
            )

        yield Footer()

    def on_mount(self) -> None:
        # Наполним RichLog тестовыми данными
        for panel in self.query(ContentPanel):
            if panel._widget_type == "richlog":
                panel.write_to_log("[bold green]INFO[/bold green]  ContentPanel запущен")
                panel.write_to_log("[bold yellow]WARN[/bold yellow]  Пример предупреждения")
                panel.write_to_log(
                    "[bold red]ERROR[/bold red]    "
                    "Длинный текст для проверки обёртывания "
                    "строк в RichLog с wrap=True"
                )
                panel.write_to_log("-" * 80)

        for wrapper in self.query(ContentBlockWrapper):
            if wrapper._widget_type == "richlog":
                wrapper.write_to_log("[bold green]INFO[/bold green]  ContentBlockWrapper работает")
                wrapper.write_to_log("[bold yellow]WARN[/bold yellow]  Ещё одно предупреждение")
                wrapper.write_to_log(
                    "[bold red]ERROR[/bold red]    "
                    "Очень длинный текст чтобы проверить "
                    "как ведёт себя обёртка RichLog"
                )
                wrapper.write_to_log("─" * 80)

    # ── Handlers для ContentPanel ──

    @on(ContentPanel.CopyRequested)
    def on_cp_copy(self, event: ContentPanel.CopyRequested) -> None:
        text = event.text
        if text:
            self.copy_to_clipboard(text)
            btn = event.panel.query_one("#cp-btn-copy", ToolbarButton)
            old = btn.label
            btn.label = "✅"
            self.set_timer(1.5, lambda: setattr(btn, "label", old))

    @on(ContentPanel.PasteRequested)
    def on_cp_paste(self, event: ContentPanel.PasteRequested) -> None:
        text = self.get_clipboard_text()
        if text:
            w = event.panel.content_widget
            if isinstance(w, TextArea):
                w.load_text(text)

    # ── Handlers для ContentBlockWrapper ──

    @on(ContentBlockWrapper.Action)
    def on_cbw_action(self, event: ContentBlockWrapper.Action) -> None:
        action = event.action
        w = event.wrapper
        if "Копия" in action or "📋" in action:
            text = w.get_text()
            if text:
                self.copy_to_clipboard(text)
        elif "Очистить" in action or "✕" in action:
            w.clear_content()
        elif "✚" in action or "Тест" in action:
            import time
            w.write_to_log(
                f"[dim]{time.strftime('%H:%M:%S')}[/dim]  "
                f"[bold]Тестовый лог[/bold]  Lorem ipsum"
            )


if __name__ == "__main__":
    TuiLab().run()