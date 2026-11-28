"""Declarative settings fields: one spec per setting instead of one handler per setting.

Every settings pane collected its fields by hand: a `query_one`, a try/except that logged a
warning and carried on, an `isdigit()` check, a clamp (`max(1, …)`) and a comparison with the
current config value — four times over, with slightly different rules each time (the network
pane clamps `max_redirects` at 0 but the project pane clamps the interval at 1; a missing field
is a warning in one pane and a silent skip in another).

A `FieldSpec` says once what the field is: which config key it writes, which widget id holds it,
how to read it, and the one clamp that applies. `collect_changes()` then does the loop for the
whole section and returns only the keys whose value actually changed — the shape
`SettingsScreen._save_settings()` expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from textual.css.query import NoMatches
from textual.widgets import Checkbox

from pentool.core.logging import get_logger

logger = get_logger(__name__)

FieldKind = Literal["bool", "int", "text", "option"]


@dataclass(frozen=True)
class FieldSpec:
    """One setting: config key, widget id, how to read it, how to validate it."""

    key: str
    widget_id: str
    #: "bool" for a Checkbox, "int"/"text" for an Input, "option" for an OptionCycler.
    kind: FieldKind
    minimum: int | None = None
    maximum: int | None = None
    #: For text fields: an empty input means "leave as is" (host, user agent, header name).
    require_text: bool = False

    def coerce(self, raw: Any) -> tuple[Any, str | None]:
        """Return `(value, error)` for the raw widget value; error means "skip this field"."""
        if self.kind == "bool":
            return bool(raw), None
        text = str(raw).strip()
        if self.kind == "int":
            if not text.isdigit():
                return None, f"{self.key}: not a number"
            value = int(text)
            if self.minimum is not None:
                value = max(self.minimum, value)
            if self.maximum is not None:
                value = min(self.maximum, value)
            return value, None
        if self.require_text and not text:
            return None, f"{self.key}: empty"
        return text, None


@dataclass(frozen=True)
class SectionSpec:
    """A pane's worth of fields."""

    name: str
    fields: tuple[FieldSpec, ...]


def _read_widget(screen: Any, spec: FieldSpec) -> Any:
    widget = screen.query_one(f"#{spec.widget_id}")
    if isinstance(widget, Checkbox):
        return widget.value
    return widget.value  # Input and OptionCycler both expose `.value`


def read_section(screen: Any, section: SectionSpec, cfg: Any) -> tuple[dict[str, Any], list[str]]:
    """Read a section's widgets: `(changes, problems)`, only keys whose value changed.

    A missing widget is a problem for the log, not an exception: the pane may not be composed
    yet, and the other fields must still be saved.
    """
    changes: dict[str, Any] = {}
    problems: list[str] = []
    for spec in section.fields:
        try:
            raw = _read_widget(screen, spec)
        except NoMatches:
            problems.append(f"{section.name}: #{spec.widget_id} is not mounted")
            continue
        value, error = spec.coerce(raw)
        if error:
            problems.append(error)
            continue
        current = getattr(cfg, spec.key, None)
        if value != current:
            changes[spec.key] = value
    return changes, problems


def collect_changes(screen: Any, section: SectionSpec, cfg: Any | None = None) -> dict[str, Any]:
    """`read_section` for the save handlers: logs the problems, returns the changes."""
    if cfg is None:
        from pentool.core.config import get_config

        cfg = get_config()
    changes, problems = read_section(screen, section, cfg)
    for problem in problems:
        logger.warning("settings: %s", problem)
    return changes


# ── The panes ────────────────────────────────────────────────────────────────
# Widget ids come from `SettingsScreen.compose()`; `test_settings_fields.py` fails when a spec
# names an id that the screen no longer composes, so a renamed widget cannot silently stop
# being saved.

PROXY = SectionSpec(
    "proxy",
    (
        FieldSpec("proxy_host", "set-proxy-host", "text", require_text=True),
        FieldSpec("proxy_port", "set-proxy-port", "int", minimum=1, maximum=65535),
    ),
)

PROJECT = SectionSpec(
    "project",
    (
        FieldSpec("auto_save_enabled", "set-autosave-enabled", "bool"),
        FieldSpec("auto_save_interval", "set-autosave-interval", "int", minimum=1),
    ),
)

NETWORK = SectionSpec(
    "network",
    (
        FieldSpec("default_user_agent", "set-user-agent", "text", require_text=True),
        FieldSpec("request_timeout", "set-req-timeout", "int", minimum=1),
        FieldSpec("connect_timeout", "set-conn-timeout", "int", minimum=1),
        FieldSpec("max_redirects", "set-max-redirects", "int", minimum=0),
        FieldSpec("verify_ssl", "set-verify-ssl", "bool"),
        FieldSpec("tooltips_enabled", "set-tooltips", "bool"),
        FieldSpec("panel_icons", "set-panel-icons", "option"),
        FieldSpec("collaborator_url", "set-collaborator-url", "text"),
        FieldSpec("scan_marker_enabled", "set-scan-marker-enabled", "bool"),
        FieldSpec("scan_marker_name", "set-scan-marker-name", "text", require_text=True),
        FieldSpec("scan_marker_value", "set-scan-marker-value", "text"),
    ),
)

PRIVACY = SectionSpec(
    "privacy",
    (
        FieldSpec("send_crash_reports", "set-send-crash-reports", "bool"),
        FieldSpec("check_updates", "set-check-updates", "bool"),
        FieldSpec("auto_scope", "set-auto-scope", "bool"),
    ),
)
