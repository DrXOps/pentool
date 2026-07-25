"""MatchReplaceEngine — автоматическая замена в HTTP-трафике."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from pentool.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MatchReplaceRule:
    """Правило автоматической замены в запросах/ответах.

    Атрибуты:
        match: Строка или regex-паттерн для поиска.
        replace: Строка замены.
        target: "request" | "response" | "both".
        scope: "headers" | "body" | "all".
        is_regex: Если True — match интерпретируется как regex.
        enabled: Активно ли правило.
        id: Уникальный идентификатор (генерируется автоматически).
    """

    match: str
    replace: str
    target: Literal["request", "response", "both"] = "both"
    scope: Literal["headers", "body", "all"] = "all"
    is_regex: bool = False
    enabled: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "match": self.match,
            "replace": self.replace,
            "target": self.target,
            "scope": self.scope,
            "is_regex": self.is_regex,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MatchReplaceRule":
        return cls(
            id=data.get("id", ""),
            match=data.get("match", ""),
            replace=data.get("replace", ""),
            target=data.get("target", "both"),
            scope=data.get("scope", "all"),
            is_regex=data.get("is_regex", False),
            enabled=data.get("enabled", True),
        )


class MatchReplaceEngine:
    """Движок автоматической замены в HTTP-запросах/ответах.

    Управляет списком правил MatchReplaceRule и применяет их к сырым
    строкам HTTP-трафика. Разделяет заголовки и тело, фильтрует правила
    по target (request/response/both) и scope (headers/body/all).
    """

    def __init__(self) -> None:
        self.rules: list[MatchReplaceRule] = []

    def set_rules(self, rules: list[MatchReplaceRule]) -> None:
        self.rules = rules

    def apply_to_request(self, raw: str) -> str:
        """Применить правила к сырой строке HTTP-запроса (headers + body).

        Args:
            raw: Сырой HTTP-запрос (заголовки + тело через \\r\\n\\r\\n).

        Returns:
            Преобразованная строка.
        """
        req_rules = [r for r in self.rules if r.enabled and r.target in ("request", "both")]
        if not req_rules:
            return raw

        # Разбить на заголовки и тело
        if "\r\n\r\n" in raw:
            head, sep, body = raw.partition("\r\n\r\n")
        elif "\n\n" in raw:
            head, sep, body = raw.partition("\n\n")
        else:
            head, sep, body = raw, "", ""

        header_rules = [r for r in req_rules if r.scope in ("headers", "all")]
        body_rules = [r for r in req_rules if r.scope in ("body", "all")]

        head = self._apply_rules(head, header_rules)
        body = self._apply_rules(body, body_rules)
        return head + sep + body

    def apply_to_response(self, raw: str) -> str:
        """Применить правила к сырой строке HTTP-ответа (headers + body).

        Args:
            raw: Сырой HTTP-ответ (заголовки + тело через \\r\\n\\r\\n).

        Returns:
            Преобразованная строка.
        """
        resp_rules = [r for r in self.rules if r.enabled and r.target in ("response", "both")]
        if not resp_rules:
            return raw

        if "\r\n\r\n" in raw:
            head, sep, body = raw.partition("\r\n\r\n")
        elif "\n\n" in raw:
            head, sep, body = raw.partition("\n\n")
        else:
            head, sep, body = raw, "", ""

        header_rules = [r for r in resp_rules if r.scope in ("headers", "all")]
        body_rules = [r for r in resp_rules if r.scope in ("body", "all")]

        head = self._apply_rules(head, header_rules)
        body = self._apply_rules(body, body_rules)
        return head + sep + body

    def _apply_rules(self, text: str, rules: list[MatchReplaceRule]) -> str:
        """Применить список правил к тексту последовательно."""
        for rule in rules:
            if not rule.enabled:
                continue
            try:
                if rule.is_regex:
                    text = re.sub(rule.match, rule.replace, text)
                else:
                    text = text.replace(rule.match, rule.replace)
            except re.error as exc:
                logger.warning("Match/replace rule error (id=%s): %s", rule.id, exc)
        return text
