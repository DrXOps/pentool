"""Scope settings dialog (host list + regex include/exclude) on `FormDialog` (step 7).

The dialog used to hand-build three `TextArea`s, its own Save button, its own Escape binding
and its own validation line. All of that now comes from `FormDialog`: the fields are declared as
`lines` fields, the regex check is a `validate` on the field, and the error appears under the
field that caused it instead of a separate message at the bottom.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from textual.binding import Binding

from pentool.tui.dialogs.form_dialog import FormDialog, FormField

_EXTENDED_HINT = (
    "Hosts one per line (wildcards: *.example.com). Leave empty to match all hosts.\n"
    "Regex Include: a URL must match at least one (empty = match all). "
    "Regex Exclude: a URL must not match any (empty = exclude nothing)."
)
_SIMPLE_HINT = "One host per line. Wildcards supported: *.example.com. Leave empty to intercept all hosts."


@dataclass
class ScopeConfig:
    """Extended Scope configuration with regex support."""

    hosts: list[str] = field(default_factory=list)
    regex_include: list[str] = field(default_factory=list)
    regex_exclude: list[str] = field(default_factory=list)

    def matches(self, url: str) -> bool:
        """Check whether the URL falls within scope.

        Logic:
        1. If hosts is non-empty — URL host must match one of the patterns.
        2. If regex_include is non-empty — URL must match at least one.
        3. If regex_exclude is non-empty — URL must not match any.
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
        except Exception:
            host = url

        # Check host list (with wildcard)
        if self.hosts:
            host_ok = any(_host_matches(h, host) for h in self.hosts)
            if not host_ok:
                return False

        # Regex include
        if self.regex_include:
            inc_ok = any(_regex_match(p, url) for p in self.regex_include)
            if not inc_ok:
                return False

        # Regex exclude
        if self.regex_exclude:
            exc_hit = any(_regex_match(p, url) for p in self.regex_exclude)
            if exc_hit:
                return False

        return True

    @property
    def host_list(self) -> list[str]:
        """Alias for backward-compat — returns the host list."""
        return self.hosts


def _host_matches(pattern: str, host: str) -> bool:
    pattern = pattern.strip().lower()
    host = host.strip().lower()
    if pattern.startswith("*"):
        suffix = pattern[1:]
        return host.endswith(suffix)
    return pattern == host


def _regex_match(pattern: str, text: str) -> bool:
    """Safe regex match — returns False on pattern error."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return False


def validate_patterns(patterns: list[str]) -> list[str]:
    """Validate a list of regex patterns. Returns list of invalid ones."""
    invalid = []
    for p in patterns:
        try:
            re.compile(p)
        except re.error:
            invalid.append(p)
    return invalid


def _regex_list_validate(patterns: list[str]) -> str | None:
    """FormDialog field rule: reject invalid regular expressions by name."""
    bad = validate_patterns(list(patterns or []))
    if not bad:
        return None
    return f"invalid regex: {', '.join(bad[:3])}"


class ScopeDialog(FormDialog):
    """Modal dialog for editing Scope.

    In `extended=True` mode returns `ScopeConfig` (hosts + regex include/exclude).
    In `extended=False` mode (default) returns `list[str]` — backward-compat.
    """

    BINDINGS = [*FormDialog.BINDINGS, Binding("ctrl+s", "submit", "Save")]

    def __init__(
        self,
        current_scope: list[str] | ScopeConfig | None = None,
        extended: bool = False,
    ) -> None:
        self._extended = extended

        if isinstance(current_scope, ScopeConfig):
            self._cfg = current_scope
            self._extended = True  # always show extended if ScopeConfig was passed
        elif isinstance(current_scope, list):
            self._cfg = ScopeConfig(hosts=list(current_scope))
        else:
            self._cfg = ScopeConfig()

        fields = [
            FormField(
                "hosts",
                "Hosts",
                kind="lines",
                default="\n".join(self._cfg.hosts),
                lines_height=5,
            )
        ]
        if self._extended:
            fields += [
                FormField(
                    "regex_include",
                    "Regex Include",
                    kind="lines",
                    default="\n".join(self._cfg.regex_include),
                    lines_height=3,
                    help=r"E.g. /api/ or \.(php|asp) (empty = match all)",
                    validate=_regex_list_validate,
                ),
                FormField(
                    "regex_exclude",
                    "Regex Exclude",
                    kind="lines",
                    default="\n".join(self._cfg.regex_exclude),
                    lines_height=3,
                    help=r"E.g. \.js$ or /static/ (empty = exclude nothing)",
                    validate=_regex_list_validate,
                ),
            ]
        super().__init__(
            "Scope Settings",
            fields,
            submit_label="Save",
            description=_EXTENDED_HINT if self._extended else _SIMPLE_HINT,
        )

    def _result(self, values: dict) -> list[str] | ScopeConfig:
        hosts = list(values["hosts"])
        if not self._extended:
            return hosts
        return ScopeConfig(
            hosts=hosts,
            regex_include=list(values["regex_include"]),
            regex_exclude=list(values["regex_exclude"]),
        )
