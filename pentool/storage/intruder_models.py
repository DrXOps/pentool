"""Доменные типы результатов Intruder, видимые слою хранения.

Почему отдельный модуль, а не `pentool.modules.intruder`: правило слоёв
запрещает `storage -> modules`, но `IntruderStorage` обязан возвращать
типизированные результаты. Это чистый value object — ни атак, ни сети, ни
асyncio, поэтому он может жить на уровне storage.

`pentool.modules.intruder` реэкспортирует имя, так что существующие
`from pentool.modules.intruder import IntruderResult` продолжают работать
(включая PRO-пакет `pro/`, который импортирует именно из modules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IntruderResult:
    """Один результат прогона Intruder.

    Поля — ровно то, что хранится в таблице `intruder_results` плюс
    вычисляемый `timestamp`. Никакого поведения: объект только переносит
    данные из модуля атаки в storage и обратно.
    """

    id: str
    attack_id: str
    request_number: int
    payload_values: list[str]  # values per position
    request_raw: str
    response_raw: str | None = None  # full HTTP response
    response_status: int | None = None
    response_length: int | None = None
    response_time_ms: int | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
