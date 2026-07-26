"""MatchReplaceEngine — automatic replacement in HTTP traffic."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from pentool.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MatchReplaceRule:
    """Automatic replacement rule for requests/responses.

    Attributes:
        match: String or regex pattern to search for.
        replace: Replacement string.
        target: "request" | "response" | "both".
        scope: "headers" | "body" | "all".
        is_regex: If True — match is interpreted as a regex.
        enabled: Whether the rule is active.
        id: Unique identifier (auto-generated).
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
    """Engine for automatic replacement in HTTP requests/responses.

    Manages a list of MatchReplaceRule objects and applies them to raw
    HTTP traffic strings. Splits headers and body, filters rules by
    target (request/response/both) and scope (headers/body/all).
    """

    def __init__(self) -> None:
        self.rules: list[MatchReplaceRule] = []

    def set_rules(self, rules: list[MatchReplaceRule]) -> None:
        self.rules = rules

    def apply_to_request(self, raw: str) -> str:
        """Apply rules to a raw HTTP request string (headers + body).

        Args:
            raw: Raw HTTP request (headers + body separated by \\r\\n\\r\\n).

        Returns:
            Transformed string.
        """
        req_rules = [r for r in self.rules if r.enabled and r.target in ("request", "both")]
        if not req_rules:
            return raw

        # Split into headers and body
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
        """Apply rules to a raw HTTP response string (headers + body).

        Args:
            raw: Raw HTTP response (headers + body separated by \\r\\n\\r\\n).

        Returns:
            Transformed string.
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
        """Apply a list of rules to text sequentially."""
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
