"""ToolbarButton — кастомная компактная кнопка для панелей."""

from textual.message import Message
from textual.widget import Widget


class ToolbarButton(Widget):
    """Кастомная кнопка: variant, disabled, compact."""

    class Pressed(Message):
        def __init__(self, button: "ToolbarButton") -> None:
            self.button = button
            super().__init__()

    def __init__(
        self,
        label: str = "",
        button_id: str = "",
        *,
        variant: str = "default",
        classes: str = "",
        disabled: bool = False,
    ):
        super().__init__()
        self._label = label
        self._variant = variant
        self._disabled = disabled
        if button_id:
            self.id = button_id
        if classes:
            self.classes = classes

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, val: str) -> None:
        self._label = val
        self.refresh()

    @property
    def variant(self) -> str:
        return self._variant

    @variant.setter
    def variant(self, val: str) -> None:
        self._variant = val
        self._update_css_classes()

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, val: bool) -> None:
        self._disabled = val
        self._update_css_classes()

    def _update_css_classes(self) -> None:
        classes = set()
        if self._disabled:
            classes.add("disabled")
        if self._variant and self._variant != "default":
            classes.add(f"variant-{self._variant}")
        self.classes = " ".join(sorted(classes))
        self.refresh()

    def render(self) -> str:
        return self._label

    def on_click(self) -> None:
        if not self._disabled:
            self.post_message(self.Pressed(self))