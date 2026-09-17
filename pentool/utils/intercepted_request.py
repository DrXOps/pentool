"""InterceptedRequest — dataclass for proxied HTTP requests with thread-safe state."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from pentool.utils.parser import ParsedRequest, ParsedResponse

InterceptState = Literal["waiting", "forwarded", "dropped"]


@dataclass
class InterceptedRequest:
    """Intercepted request with state and response.

    Thread-safe: state and response are guarded by a Lock because they
    are written from the proxy worker threads and read from the TUI thread.
    """

    id: str
    method: str
    url: str
    headers: dict[str, str]
    body: str
    timestamp: datetime
    state: InterceptState = "waiting"
    response: ParsedResponse | None = None
    is_https: bool = False
    is_websocket: bool = False
    # asyncio.Event — set when the user has made a decision
    _decision_event: asyncio.Event = field(
        default_factory=asyncio.Event, repr=False, compare=False
    )
    # If the user edited the request before forwarding
    _modified_raw: str | None = field(default=None, repr=False, compare=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Ensure the lock is always a fresh instance (dataclass field factory
        only runs once at class definition time — see field(default_factory=...))."""
        if not hasattr(self, "_lock") or self._lock is None:
            object.__setattr__(self, "_lock", threading.Lock())

    def set_response(self, resp: ParsedResponse | None) -> None:
        with self._lock:
            object.__setattr__(self, "response", resp)

    def get_response(self) -> ParsedResponse | None:
        with self._lock:
            return self.response

    def set_state(self, state: InterceptState) -> None:
        with self._lock:
            object.__setattr__(self, "state", state)

    def get_state(self) -> InterceptState:
        with self._lock:
            return self.state

    def to_parsed_request(self) -> ParsedRequest:
        """Convert to ParsedRequest for sending via HTTPClient."""
        return ParsedRequest(
            method=self.method,
            url=self.url,
            headers=self.headers,
            body=self.body,
        )

    def to_dict(self) -> dict:
        """Serialize the intercepted request to a dict (full format with response).

        Symmetric with from_dict() — suitable for project persistence.
        """
        resp = self.response
        return {
            "id": self.id,
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "body": self.body if isinstance(self.body, str) else self.body.decode("utf-8", errors="replace"),
            "timestamp": self.timestamp.isoformat(),
            "state": self.state,
            "is_https": self.is_https,
            "is_websocket": self.is_websocket,
            "response": {
                "status": resp.status,
                "reason": resp.reason,
                "headers": resp.headers,
                "body": resp.body if isinstance(resp.body, str) else resp.body.decode("utf-8", errors="replace"),
            } if resp else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterceptedRequest":
        """Restore InterceptedRequest from a dict (deserialization from project)."""
        from datetime import datetime, timezone
        ts_raw = data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            ts = datetime.now(timezone.utc)

        resp_data = data.get("response")
        response = None
        if resp_data:
            response = ParsedResponse(
                status=resp_data.get("status", 0),
                reason=resp_data.get("reason", ""),
                headers=resp_data.get("headers", {}),
                body=resp_data.get("body", ""),
            )

        return cls(
            id=data.get("id", ""),
            method=data.get("method", "GET"),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            body=data.get("body", ""),
            timestamp=ts,
            state=data.get("state", "forwarded"),
            is_https=data.get("is_https", False),
            is_websocket=data.get("is_websocket", False),
            response=response,
        )