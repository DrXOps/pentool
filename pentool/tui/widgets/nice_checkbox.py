"""NiceCheckbox — Checkbox subclass with distinct on/off glyphs (☐ / ☑).

The project-wide `Checkbox.BUTTON_LEFT/INNER/RIGHT = "[", "✓", "]"` override
in app.py renders the SAME glyph "[✓]" in both states — only the color
changes (muted grey when off, green when on). That's a lot less legible at a
glance than a genuinely different symbol per state, which is what the
"Skip out-of-scope" toggle button in ProxyScreen uses (☐/☑) and what
prompted this widget: swap every plain `Checkbox` in the app for this one so
the whole project gets the same clearly-different-symbol look.
"""

from __future__ import annotations

from textual.content import Content
from textual.widgets import Checkbox


class NiceCheckbox(Checkbox):
    """Checkbox with a visibly different glyph per state: ☐ (off) / ☑ (on).

    Drop-in replacement for `textual.widgets.Checkbox` — same constructor
    signature, same `.value` reactive, same `Changed` message.
    """

    # BUTTON_LEFT/RIGHT are unused for the on/off distinction here — the
    # whole box+check glyph is drawn as a single BUTTON_INNER character so
    # we can swap the entire glyph based on `.value`, not just its color.
    BUTTON_LEFT = ""
    BUTTON_RIGHT = ""

    @property
    def _button(self) -> Content:
        button_style = self.get_visual_style("toggle--button")
        glyph = "☑" if self.value else "☐"
        return Content.assemble((glyph, button_style))
