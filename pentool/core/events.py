"""Typed application events for the Event Bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppEvent:
    """Base class for all events."""
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # source module name, for debugging


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
    """Vulnerability discovered (active or passive scan)."""
    finding: Any = None
    scan_source: str = "active"  # "active" | "passive"


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
    """
    request_id: str = ""
    method: str = ""
    url: str = ""
    host: str = ""
    request: Any = None  # InterceptedRequest


@dataclass
class ProxyRequestCompleted(AppEvent):
    """Request through proxy completed (response received).

    request: full InterceptedRequest object (Any to avoid
    circular imports modules -> core).
    """
    request_id: str = ""
    status_code: int = 0
    request: Any = None  # InterceptedRequest


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
