"""Диалог настройки Scope (список хостов + regex include/exclude)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea
from pathlib import Path

from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "scope_dialog.tcss").read_text(encoding="utf-8")


@dataclass
class ScopeConfig:
    """Расширенная конфигурация Scope с поддержкой regex."""

    hosts: list[str] = field(default_factory=list)
    regex_include: list[str] = field(default_factory=list)
    regex_exclude: list[str] = field(default_factory=list)

    def matches(self, url: str) -> bool:
        """Проверить, попадает ли URL в scope.

        Логика:
        1. Если hosts не пустой — хост URL должен совпадать с одним из шаблонов.
        2. Если regex_include не пустой — URL должен совпасть хотя бы с одним.
        3. Если regex_exclude не пустой — URL не должен совпадать ни с одним.
        """
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
        except Exception:
            host = url

        # Проверка host-списка (с wildcard)
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
        """Alias для backward-compat — возвращает список хостов."""
        return self.hosts


def _host_matches(pattern: str, host: str) -> bool:
    pattern = pattern.strip().lower()
    host = host.strip().lower()
    if pattern.startswith("*"):
        suffix = pattern[1:]
        return host.endswith(suffix)
    return pattern == host


def _regex_match(pattern: str, text: str) -> bool:
    """Безопасный regex match — при ошибке паттерна возвращает False."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return False


def validate_patterns(patterns: list[str]) -> list[str]:
    """Валидировать список regex-паттернов. Возвращает список ошибочных."""
    invalid = []
    for p in patterns:
        try:
            re.compile(p)
        except re.error:
            invalid.append(p)
    return invalid


class ScopeDialog(ModalScreen[list[str] | ScopeConfig | None]):
    """Модальный диалог редактирования Scope.

    В режиме `extended=True` возвращает `ScopeConfig` (хосты + regex include/exclude).
    В режиме `extended=False` (по умолчанию) возвращает `list[str]` — backward-compat.
    """

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Save"),
    ]

    def __init__(
        self,
        current_scope: list[str] | ScopeConfig | None = None,
        extended: bool = False,
    ) -> None:
        super().__init__()
        self._extended = extended

        if isinstance(current_scope, ScopeConfig):
            self._cfg = current_scope
            self._extended = True  # всегда показываем extended если передали ScopeConfig
        elif isinstance(current_scope, list):
            self._cfg = ScopeConfig(hosts=list(current_scope))
        else:
            self._cfg = ScopeConfig()

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Scope Settings", id="title")

            if self._extended:
                yield Label(
                    "Hosts (one per line, wildcards: *.example.com):\n"
                    "Leave empty to match all hosts.",
                    id="hint",
                )
            else:
                yield Label(
                    "One host per line. Wildcards supported: *.example.com\n"
                    "Leave empty to intercept all hosts.",
                    id="hint",
                )

            yield TextArea(
                "\n".join(self._cfg.hosts),
                id="scope-area",
            )

            if self._extended:
                yield Static("── Regex Include (URL must match at least one) ──",
                             id="regex-include-label", classes="regex-section-label")
                yield Label(
                    "[dim]E.g.: /api/  or  \\.(php|asp)  (empty = match all)[/dim]",
                    id="regex-include-hint", classes="regex-hint",
                )
                yield TextArea(
                    "\n".join(self._cfg.regex_include),
                    id="regex-include-area",
                    classes="regex-area",
                )

                yield Static("── Regex Exclude (URL must NOT match any) ──",
                             id="regex-exclude-label", classes="regex-section-label")
                yield Label(
                    "[dim]E.g.: \\.js$  or  /static/  (empty = exclude nothing)[/dim]",
                    id="regex-exclude-hint", classes="regex-hint",
                )
                yield TextArea(
                    "\n".join(self._cfg.regex_exclude),
                    id="regex-exclude-area",
                    classes="regex-area",
                )

                yield Static("", id="validation-msg", classes="validation-msg")

            with Horizontal(id="buttons"):
                yield ToolbarButton("Save",   "btn-ok")
                yield ToolbarButton("Cancel", "btn-cancel")

    @on(ToolbarButton.Pressed, "#btn-ok")
    def on_btn_ok(self, _: ToolbarButton.Pressed) -> None:
        self.action_confirm()

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    def action_confirm(self) -> None:
        text = self.query_one("#scope-area", TextArea).text
        hosts = [h.strip() for h in text.splitlines() if h.strip()]

        if not self._extended:
            self.dismiss(hosts)
            return

        # Extended mode — собираем regex include/exclude
        inc_text = self.query_one("#regex-include-area", TextArea).text
        exc_text = self.query_one("#regex-exclude-area", TextArea).text

        regex_include = [p.strip() for p in inc_text.splitlines() if p.strip()]
        regex_exclude = [p.strip() for p in exc_text.splitlines() if p.strip()]

        # Валидация паттернов
        bad_inc = validate_patterns(regex_include)
        bad_exc = validate_patterns(regex_exclude)
        if bad_inc or bad_exc:
            bad_all = bad_inc + bad_exc
            try:
                self.query_one("#validation-msg", Static).update(
                    f"[bold red]Invalid regex: {', '.join(bad_all[:3])}[/bold red]"
                )
            except Exception:
                pass
            return

        self.dismiss(ScopeConfig(
            hosts=hosts,
            regex_include=regex_include,
            regex_exclude=regex_exclude,
        ))

    def action_cancel(self) -> None:
        self.dismiss(None)
