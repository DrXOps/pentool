"""Typed application events for the Event Bus."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppEvent:
    """Base class for all events."""
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # source module name, for debugging

    def for_history(self) -> "AppEvent":
        """Return the object retained in EventBus._history (ring buffer).

        Default: return self unchanged. Override in event types that carry
        heavy payloads (e.g. a full request/response object) to strip them
        before they get retained long-term in the ring buffer — live
        subscribers still receive the full original event via
        emit()/emit_threadsafe(), only the *stored* copy is stripped.
        """
        return self


# ── Scanner events ─────────────────────────────────────────────────────────────

@dataclass
class ScanStarted(AppEvent):
    """Scan started."""
    targets: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


@dataclass
class ScanFinished(AppEvent):
    """Scan finished (normally or by stop)."""
    total_findings: int = 0
    stopped_early: bool = False


@dataclass
class ScanProgressEvent(AppEvent):
    """Scan progress."""
    done: int = 0
    total: int = 0
    scanning: bool = True


@dataclass
class FindingDiscovered(AppEvent):
    """Vulnerability discovered (active or passive scan).

    finding: full Finding object (Any to avoid a modules -> core import —
    Finding lives in pentool.modules.scanner.base).

    NOTE on memory: like ProxyRequestCaptured/ProxyRequestCompleted, this
    event's `finding` carries heavy payloads (request_raw/response_raw —
    full HTTP request/response text). Nothing replays FindingDiscovered
    from EventBus history (no get_history(event_type=FindingDiscovered)
    caller in the codebase) — the only consumers are live subscribers
    (Dashboard, ScannerScreen), which already get the full event via
    emit()/emit_threadsafe(). Without for_history(), up to `max_history`
    (10_000) full Finding objects — each with its own request/response
    bodies — could accumulate in the ring buffer on a long/noisy scan
    session, retained purely for a replay feature nothing uses.
    for_history() keeps the lightweight identifying fields and drops the
    heavy raw text.
    """
    finding: Any = None
    scan_source: str = "active"  # "active" | "passive"

    def for_history(self) -> "FindingDiscovered":
        f = self.finding
        if f is None:
            return self
        stripped = copy.copy(f)
        try:
            stripped.request_raw = ""
            stripped.response_raw = ""
        except Exception:
            pass
        return FindingDiscovered(
            timestamp=self.timestamp,
            source=self.source,
            finding=stripped,
            scan_source=self.scan_source,
        )


# ── Spider events ──────────────────────────────────────────────────────────────

@dataclass
class UrlCrawled(AppEvent):
    """Spider found a new URL."""
    url: str = ""
    base_target: str = ""


@dataclass
class SpiderFinished(AppEvent):
    """Crawling finished."""
    base_url: str = ""
    pages_count: int = 0
    forms_count: int = 0
    endpoints_count: int = 0


# ── Intruder events ────────────────────────────────────────────────────────────

@dataclass
class IntruderResultAdded(AppEvent):
    """Result of a single attack request received."""
    result: Any = None   # IntruderResult


@dataclass
class IntruderFinished(AppEvent):
    """Attack finished."""
    total_results: int = 0
    stopped_early: bool = False


# ── Proxy events ───────────────────────────────────────────────────────────────

@dataclass
class ProxyRequestCaptured(AppEvent):
    """Proxy intercepted a new request.

    request: full InterceptedRequest object (Any to avoid
    circular imports modules -> core).

    NOTE on memory: `request` carries the full InterceptedRequest (headers,
    body, response). Live subscribers (app.py, PassiveScanner) need the full
    object and get it via emit()/emit_threadsafe() as before. But EventBus
    also retains a copy of every event in its `_history` ring buffer
    (maxlen=10_000) — retaining the full request there too means up to
    10_000 full HTTP requests/responses held in memory just for history/
    replay purposes, which nothing actually replays (no code calls
    `get_history()`/`replay()` for this event type). `for_history()` strips
    `request` down to None before it enters `_history`, keeping only the
    lightweight metadata fields already present (request_id/method/url/host).
    """
    request_id: str = ""
    method: str = ""
    url: str = ""
    host: str = ""
    request: Any = None  # InterceptedRequest

    def for_history(self) -> "ProxyRequestCaptured":
        if self.request is None:
            return self
        return ProxyRequestCaptured(
            timestamp=self.timestamp,
            source=self.source,
            request_id=self.request_id,
            method=self.method,
            url=self.url,
            host=self.host,
            request=None,
        )


@dataclass
class ProxyRequestCompleted(AppEvent):
    """Request through proxy completed (response received).

    request: full InterceptedRequest object (Any to avoid
    circular imports modules -> core).

    See ProxyRequestCaptured.for_history() docstring — same rationale:
    nothing replays this event type from history, so the full request/
    response body should not be retained in the ring buffer.
    """
    request_id: str = ""
    status_code: int = 0
    request: Any = None  # InterceptedRequest

    def for_history(self) -> "ProxyRequestCompleted":
        if self.request is None:
            return self
        return ProxyRequestCompleted(
            timestamp=self.timestamp,
            source=self.source,
            request_id=self.request_id,
            status_code=self.status_code,
            request=None,
        )


# Alias for backward compatibility: Sequencer subscribes to this event
ProxyRequestDoneEvent = ProxyRequestCompleted


# ── Target / SiteMap events ────────────────────────────────────────────────────

@dataclass
class TargetUrlAdded(AppEvent):
    """URL added to SiteMap/Target."""
    url: str = ""
    host: str = ""


# ── Project events ─────────────────────────────────────────────────────────────

@dataclass
class ProjectSaved(AppEvent):
    """Project saved."""
    path: str = ""


@dataclass
class ProjectLoaded(AppEvent):
    """Project loaded."""
    path: str = ""
    findings_count: int = 0
    history_count: int = 0


# ── Scanner passive events ─────────────────────────────────────────────────────

@dataclass
class PassiveScanToggled(AppEvent):
    """Passive scan toggled on/off."""
    enabled: bool = False


# ── WebSocket events ───────────────────────────────────────────────────────────

@dataclass
class WebSocketFrameEvent(AppEvent):
    """Intercepted WebSocket frame (single message).

    direction: "client->server" or "server->client"
    opcode:    0x1=text, 0x2=binary, 0x8=close, 0x9=ping, 0xA=pong
    payload:   frame body (already unmasked)
    """
    request_id: str = ""   # ID of the parent WS connection (upgrade request)
    direction: str = ""    # "client->server" | "server->client"
    opcode: int = 0x1      # 1=text, 2=binary, 8=close, 9=ping, 10=pong
    payload: bytes = field(default_factory=bytes)
    payload_text: str = "" # UTF-8 decoded payload (for text frames)
