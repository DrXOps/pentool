"""Типизированные события приложения для Event Bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppEvent:
    """Базовый класс для всех событий."""
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # имя модуля-источника, для отладки


# ── Scanner events ─────────────────────────────────────────────────────────────

@dataclass
class ScanStarted(AppEvent):
    """Сканирование запущено."""
    targets: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


@dataclass
class ScanFinished(AppEvent):
    """Сканирование завершено (нормально или по стопу)."""
    total_findings: int = 0
    stopped_early: bool = False


@dataclass
class ScanProgressEvent(AppEvent):
    """Прогресс сканирования."""
    done: int = 0
    total: int = 0
    scanning: bool = True


@dataclass
class FindingDiscovered(AppEvent):
    """Обнаружена уязвимость (активный или пассивный скан)."""
    finding: Any = None
    scan_source: str = "active"  # "active" | "passive"


# ── Spider events ──────────────────────────────────────────────────────────────

@dataclass
class UrlCrawled(AppEvent):
    """Spider нашёл новый URL."""
    url: str = ""
    base_target: str = ""


@dataclass
class SpiderFinished(AppEvent):
    """Краулинг завершён."""
    base_url: str = ""
    pages_count: int = 0
    forms_count: int = 0
    endpoints_count: int = 0


# ── Intruder events ────────────────────────────────────────────────────────────

@dataclass
class IntruderResultAdded(AppEvent):
    """Получен результат одного запроса атаки."""
    result: Any = None   # IntruderResult


@dataclass
class IntruderFinished(AppEvent):
    """Атака завершена."""
    total_results: int = 0
    stopped_early: bool = False


# ── Proxy events ───────────────────────────────────────────────────────────────

@dataclass
class ProxyRequestCaptured(AppEvent):
    """Прокси перехватил новый запрос.

    request: полный объект InterceptedRequest (Any чтобы не создавать
    циклических импортов modules → core).
    """
    request_id: str = ""
    method: str = ""
    url: str = ""
    host: str = ""
    request: Any = None  # InterceptedRequest


@dataclass
class ProxyRequestCompleted(AppEvent):
    """Запрос через прокси завершён (получен ответ).

    request: полный объект InterceptedRequest (Any чтобы не создавать
    циклических импортов modules → core).
    """
    request_id: str = ""
    status_code: int = 0
    request: Any = None  # InterceptedRequest


# Алиас для обратной совместимости: Sequencer подписывается на это событие
ProxyRequestDoneEvent = ProxyRequestCompleted


# ── Target / SiteMap events ────────────────────────────────────────────────────

@dataclass
class TargetUrlAdded(AppEvent):
    """URL добавлен в SiteMap/Target."""
    url: str = ""
    host: str = ""


# ── Project events ─────────────────────────────────────────────────────────────

@dataclass
class ProjectSaved(AppEvent):
    """Проект сохранён."""
    path: str = ""


@dataclass
class ProjectLoaded(AppEvent):
    """Проект загружен."""
    path: str = ""
    findings_count: int = 0
    history_count: int = 0


# ── Scanner passive events ──────────────────���───────────────────────────────────

@dataclass
class PassiveScanToggled(AppEvent):
    """Пассивный скан включён/выключен."""
    enabled: bool = False


# ── WebSocket events ───────────────────────────────────────────────────────────

@dataclass
class WebSocketFrameEvent(AppEvent):
    """Перехвачен WebSocket-фрейм (отдельное сообщение).

    direction: "client→server" или "server→client"
    opcode:    0x1=text, 0x2=binary, 0x8=close, 0x9=ping, 0xA=pong
    payload:   тело фрейма (уже без маски)
    """
    request_id: str = ""   # ID родительского WS-соединения (upgrade-запрос)
    direction: str = ""    # "client→server" | "server→client"
    opcode: int = 0x1      # 1=text, 2=binary, 8=close, 9=ping, 10=pong
    payload: bytes = field(default_factory=bytes)
    payload_text: str = "" # UTF-8 декодированный payload (для text-фреймов)
