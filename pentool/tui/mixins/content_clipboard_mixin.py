"""ContentClipboardMixin — универсальные обработчики Copy/Paste для ContentPanel."""

from __future__ import annotations

from textual import on

from pentool.tui.widgets.content_panel import ContentPanel


class ContentClipboardMixin:
    """Mixin с обработчиками CopyRequested/PasteRequested для ContentPanel.

    Copy — копирует весь или выделенный текст в буфер.
    Paste — вставляет текст в ContentPanel (в TextArea или RichLog).
    Можно переопределить _on_cp_paste в экране для кастомной вставки.
    """

    @on(ContentPanel.CopyRequested)
    def _on_cp_copy(self, event: ContentPanel.CopyRequested) -> None:
        """Скопировать текст из ContentPanel в буфер обмена."""
        text = event.selection or event.text
        if text:
            from pentool.utils.copy_as import copy_to_clipboard
            if copy_to_clipboard(text):
                try:
                    self.app.notify("Copied", timeout=2)
                except Exception:
                    pass

    @on(ContentPanel.PasteRequested)
    def _on_cp_paste(self, event: ContentPanel.PasteRequested) -> None:
        """Вставить текст из буфера обмена в ContentPanel."""
        from pentool.utils.copy_as import paste_from_clipboard
        text = paste_from_clipboard()
        if text:
            self._paste_text_to_panel(event.panel, text)

    def _paste_text_to_panel(self, panel: ContentPanel, text: str) -> None:
        """Базовая вставка текста в виджет ContentPanel."""
        w = panel.content_widget
        try:
            if hasattr(w, "load_text"):
                w.load_text(text)
            elif hasattr(w, "write"):
                w.write(text)
            try:
                self.app.notify("Pasted", timeout=2)
            except Exception:
                pass
        except Exception:
            pass