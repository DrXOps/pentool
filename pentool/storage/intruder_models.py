"""Доменные типы результатов Intruder, видимые слою хранения.

Why a separate module and not `pentool.modules.intruder`: the layering rule
forbids `storage -> modules`, yet `IntruderStorage` has to return
typed results. This is a pure value object — no attacks, no network, no
asyncio, so it can live at the storage level.

`pentool.modules.intruder` re-exports the name, so the existing
`from pentool.modules.intruder import IntruderResult` imports keep working
(including the PRO package `pro/`, which imports from modules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IntruderResult:
    """Один результат прогона Intruder.

    The fields are exactly what the `intruder_results` table stores plus
    a computed `timestamp`. No behaviour: the object only carries
    data between the attack module and storage.
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
