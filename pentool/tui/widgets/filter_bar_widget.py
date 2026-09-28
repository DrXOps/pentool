"""FilterBarWidget — универсальный виджет строки фильтра для любой таблицы.

Конфигурируется через наследование:
    - configure() → список FilterField (описания полей)
    - compose() рендерит поля по configure()
    - collect() читает поля и строит FilterSpec

Наследник обязан объявить свой FilterChanged Message (см. Textual naming).
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

from pentool.collections.filter_predicate import (
    FilterField,
    FilterFieldType,
    FilterOp,
    FilterPredicate,
    FilterSpec,
)

# FilterBarWidget doesn't ship a DEFAULT_CSS — each concrete subclass
# (ProxyFilterBar, IntruderFilterBar) defines its own layout, widths,
# and styling. The base class only provides the widget tree via compose()
# and the filter-logic via configure()/collect().


class Cycler(Static):
    """Циклический переключатель: клик → следующее значение."""

    class Changed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    # DEFAULT_CSS отсутствует — стили задаются родителем (ProxyFilterBar и т.д.)

    def __init__(self, options: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._options = options or []
        self._idx: int = 0
        self._update_label()

    def value(self) -> str:
        if self._idx == 0:
            return ""
        return self._options[self._idx][1]

    def reset(self) -> None:
        self._idx = 0
        self._update_label()

    def _update_label(self) -> None:
        self.update(f"{self._options[self._idx][0]} ▼")

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % len(self._options)
        self._update_label()
        self.post_message(self.Changed(self.value()))


class ToggleButton(Static):
    """Кнопка-тумблер.

    Минимальный DEFAULT_CSS для базового отображения.
    Детали (цвета, hover, active) задаются родительским CSS.
    """

    DEFAULT_CSS = """
    ToggleButton {
        height: 1;
        width: auto;
        padding: 0 1;
        background: $panel;
        color: $text;
    }
    """

    class Toggled(Message):
        def __init__(self, active: bool) -> None:
            super().__init__()
            self.active = active

    def __init__(self, label: str = "", active_label: str | None = None, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self._label = label
        self._active_label = active_label or label
        self._active: bool = False

    def is_active(self) -> bool:
        return self._active

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the button and grey it out when disabled."""
        self.set_class(not enabled, "disabled")

    def reset(self) -> None:
        self._active = False
        self.remove_class("-active")
        self.update(self._label)

    def toggle(self) -> None:
        self._active = not self._active
        self.set_class(self._active, "-active")
        self.update(self._active_label if self._active else self._label)
        self.post_message(self.Toggled(self._active))

    def on_click(self) -> None:
        self.toggle()


class FilterBarWidget(Widget):
    """Базовый виджет строки фильтрации.

    Наследник:
        1. Объявляет свой FilterChanged Message.
        2. Переопределяет configure() → список FilterField.
        3. В compose() вызывает super() для рендера + свои виджеты после.
        4. В collect() вызывает super() и дополняет кастомные предикаты.
    """

    class FilterChanged(Message):
        def __init__(self, spec: FilterSpec) -> None:
            super().__init__()
            self.spec = spec

    DEFAULT_CSS = "FilterBarWidget { height: auto; }"

    # ── Конфигурация ───────────────────────────────────────────────────────

    def configure(self) -> list[FilterField]:
        """Описание полей фильтрации. Override в наследнике."""
        return []

    # ── Compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        for f in self.configure():
            yield Label(f.label, classes="fb-label")
            yield from self._render_field(f)
            yield Label(" ", classes="fb-sep")
        yield Button("Filter", id="fb-apply", variant="primary")
        yield Button("Clear", id="fb-reset")

    def _render_field(self, field: FilterField) -> ComposeResult:
        match field.field_type:
            case FilterFieldType.TEXT:
                yield Input(id=field.id, placeholder=field.placeholder, compact=True)
            case FilterFieldType.NUMBER:
                yield Input(id=field.id, placeholder=field.placeholder, type="integer", compact=True)
            case FilterFieldType.CYCLER:
                yield Cycler(id=field.id, options=field.options or [])
            case FilterFieldType.TOGGLE:
                yield ToggleButton(field.label, id=field.id)
            case FilterFieldType.RANGE:
                lo_id = f"{field.id}-lo"
                hi_id = f"{field.id}-hi"
                yield Input(id=lo_id, placeholder=field.placeholder)
                yield Label("→", classes="fb-label")
                yield Input(id=hi_id, placeholder="∞")

    # ── Сбор предикатов ────────────────────────────────────────────────────

    def collect(self) -> list[FilterPredicate]:
        """Read current UI values → FilterPredicates.

        Наследник может переопределить и расширить результат super().
        """
        predicates: list[FilterPredicate] = []
        for f in self.configure():
            raw = self._read_field(f)
            if raw is not None and raw != "":
                predicates.append(FilterPredicate(
                    field=f.field,
                    operator=f.operator,
                    value=self._normalize_value(f, raw),
                ))
        return predicates

    def _read_field(self, field: FilterField) -> Any | None:
        try:
            match field.field_type:
                case FilterFieldType.TEXT | FilterFieldType.NUMBER:
                    return self.query_one(f"#{field.id}", Input).value.strip() or None

                case FilterFieldType.CYCLER:
                    return self.query_one(f"#{field.id}", Cycler).value()

                case FilterFieldType.TOGGLE:
                    tb = self.query_one(f"#{field.id}", ToggleButton)
                    return tb.is_active()

                case FilterFieldType.RANGE:
                    lo = self.query_one(f"#{field.id}-lo", Input).value.strip()
                    hi = self.query_one(f"#{field.id}-hi", Input).value.strip()
                    if lo and hi:
                        return (lo, hi)
                    if lo:
                        return lo
                    return None
        except Exception:
            return None

    @staticmethod
    def _normalize_value(field: FilterField, raw: Any) -> Any:
        if field.field_type == FilterFieldType.NUMBER:
            try: return int(raw)
            except ValueError: return raw
        if field.field_type == FilterFieldType.RANGE and isinstance(raw, tuple):
            try: return (int(raw[0]), int(raw[1]))
            except ValueError: return raw
        return raw

    # ── Apply / Reset ──────────────────────────────────────────────────────

    def _apply(self) -> None:
        spec = FilterSpec(predicates=self.collect())
        self._emit(spec)

    def _reset(self) -> None:
        self._clear_fields()
        self._emit(FilterSpec())

    def _emit(self, spec: FilterSpec) -> None:
        self.post_message(self.FilterChanged(spec))

    def _clear_fields(self) -> None:
        for f in self.configure():
            self._clear_field(f)

    def _clear_field(self, field: FilterField) -> None:
        try:
            match field.field_type:
                case FilterFieldType.TEXT | FilterFieldType.NUMBER:
                    self.query_one(f"#{field.id}", Input).value = ""
                case FilterFieldType.CYCLER:
                    self.query_one(f"#{field.id}", Cycler).reset()
                case FilterFieldType.TOGGLE:
                    self.query_one(f"#{field.id}", ToggleButton).reset()
                case FilterFieldType.RANGE:
                    self.query_one(f"#{field.id}-lo", Input).value = ""
                    self.query_one(f"#{field.id}-hi", Input).value = ""
        except Exception:
            pass

    # ── Handlers ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fb-apply":
            self._apply()
        elif event.button.id == "fb-reset":
            self._reset()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in any Input applies the filter."""
        self._apply()