"""GlobalHintBar / ModuleHintBar — две строки подсказок внизу экрана.

Первая строка (снизу) — ``[InModule] Ctrl+R: Send …`` — клавиши активного модуля.
Вторая строка (снизу) — ``[Global] P: Proxy  R: Rpt …`` — клавиши переключения модулей.
Обе наследуют HintBarBase (compose + set_text).
"""

from __future__ import annotations

from pentool.tui.hotkeys import build_status_bar_markup, registry
from pentool.tui.widgets.hintbar_base import HintBarBase

# ── Цвета клавиш для [Global] секции ──────────────────────────────────
_GLOBAL_KEY_COLORS: dict[str, str] = {
    "H": "#88ccff",  # Dash   — голубой
    "P": "#66dd88",  # Proxy  — зелёный
    "R": "#ff9944",  # Rpt    — оранжевый
    "I": "#ff6666",  # Intrud — красный
    "S": "#aa66ff",  # Scan   — фиолетовый
    "T": "#66ccff",  # Target — синий
    "D": "#ddbb44",  # Decode — жёлтый
    "C": "#ff88cc",  # Comp   — розовый
    "Q": "#77dddd",  # Seq    — бирюзовый
    "E": "#aaaaaa",  # Ext    — серый
}


def _render_global_entry(keys: str, description: str) -> str:
    """Render one [Global] entry: coloured key + dim description."""
    color = _GLOBAL_KEY_COLORS.get(keys, "$text")
    desc = f"[dim]{description}[/]" if description else ""
    return f"[bold {color}]{keys}[/] {desc}"


#: Row labels, drawn as accent chips instead of the old `[Global]` / `[InModule]`
#: brackets: the brackets were the last piece of text-only chrome in an interface
#: that is made of cards and chips (`$accent` is a Textual theme token; the
#: markup parser resolves it, same as `$text` below).
_GLOBAL_LABEL = "[bold $accent]Global[/]"


def _module_label(module_id: str) -> str:
    """Label for the module row: the module's own name, e.g. ``Proxy``.

    ``[InModule]`` said *that* these are hotkeys but not of which module — the
    name is both shorter and more useful next to the key list.
    """
    from pentool.tui.widgets.module_tabs import MODULES

    for mod_id, label, _hotkey in MODULES:
        if mod_id == module_id:
            return f"[bold $accent]{label}[/]"
    return f"[bold $accent]{module_id.replace('_', ' ').title()}[/]"


class GlobalHintBar(HintBarBase):
    """Bottom row: keys that switch modules (previously `[Global] …`)."""

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        entries = registry.get_entries("global")
        shown = [e for e in entries if e.show and e.description]
        shown.sort(key=lambda e: (-len(e.keys), e.keys))
        if shown:
            parts = [_render_global_entry(e.keys, e.description) for e in shown]
            self.set_text(f"{_GLOBAL_LABEL}  {' │ '.join(parts)}")
        else:
            self.set_text(f"{_GLOBAL_LABEL} —")


class ModuleHintBar(HintBarBase):
    """Bottom row: hotkeys of the active module (previously `[InModule] …`)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_group: str | None = None

    def set_module(self, module_id: str) -> None:
        """Switch to *module_id* and re-render hints."""
        if module_id == self._current_group:
            return
        self._current_group = module_id
        self._refresh()

    def _refresh(self) -> None:
        if not self._current_group:
            self.set_text(f"{_module_label('module')} —")
            return
        label = _module_label(self._current_group)
        entries = registry.get_entries(self._current_group)
        hints = build_status_bar_markup(entries)
        if hints:
            self.set_text(f"{label}  {hints}")
        else:
            self.set_text(f"{label} —")
