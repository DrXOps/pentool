"""Intruder — модуль автоматизированных атак с подстановкой payload'ов."""

from __future__ import annotations

import asyncio
import csv
import itertools
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class AttackType(str, Enum):
    SNIPER        = "sniper"
    BATTERING_RAM = "battering_ram"
    PITCHFORK     = "pitchfork"
    CLUSTER_BOMB  = "cluster_bomb"


@dataclass
class IntruderResult:
    id: str
    attack_id: str
    request_number: int
    payload_values: list[str]          # значения по каждой позиции
    request_raw: str
    response_status: int | None
    response_length: int | None
    response_time_ms: int | None
    error: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IntruderConfig:
    template: str                      # raw HTTP с маркерами §payload§
    attack_type: AttackType
    payload_sets: list[list[str]]      # один список на каждую позицию
    threads: int = 10
    delay_ms: int = 0
    follow_redirects: bool = False
    timeout: int = 30


def parse_markers(template: str) -> tuple[str, list[tuple[int, int]]]:
    """Найти §маркеры§ в шаблоне.

    Returns:
        (clean_template, positions) где positions — список (start, end)
        в clean_template для каждой позиции.
    """
    positions: list[tuple[int, int]] = []
    result = []
    i = 0
    offset = 0  # смещение из-за удалённых §

    while i < len(template):
        if template[i] == "§":
            # Ищем закрывающий §
            j = template.find("§", i + 1)
            if j == -1:
                # Нет закрывающего — оставляем как есть
                result.append(template[i])
                i += 1
                continue
            # Вырезаем содержимое маркера
            inner = template[i + 1 : j]
            start = len(result)
            result.append(inner)
            end = len(result)
            positions.append((start, end))
            i = j + 1
        else:
            result.append(template[i])
            i += 1

    return "".join(result), positions


def _find_marker_positions(template: str) -> list[tuple[int, int]]:
    """Найти позиции §...§ пар в строке. Возвращает (start_§, end_§)."""
    positions = []
    i = 0
    while i < len(template):
        start = template.find("§", i)
        if start == -1:
            break
        end = template.find("§", start + 1)
        if end == -1:
            break
        positions.append((start, end + 1))  # включая оба §
        i = end + 1
    return positions


def substitute_payload(template: str, payload_values: list[str]) -> str:
    """Подставить payload'ы в §маркеры§ шаблона.

    Заменяет маркеры слева направо. Если payload_values меньше чем маркеров —
    оставшиеся маркеры заменяются пустой строкой.
    """
    result = template
    idx = 0
    while True:
        start = result.find("§")
        if start == -1:
            break
        end = result.find("§", start + 1)
        if end == -1:
            break
        value = payload_values[idx] if idx < len(payload_values) else ""
        result = result[:start] + value + result[end + 1:]
        idx += 1
    return result


def count_markers(template: str) -> int:
    """Подсчитать количество §маркеров§ в шаблоне."""
    count = 0
    i = 0
    while True:
        start = template.find("§", i)
        if start == -1:
            break
        end = template.find("§", start + 1)
        if end == -1:
            break
        count += 1
        i = end + 1
    return count


def extract_marker_defaults(template: str) -> list[str]:
    """Извлечь оригинальные значения из §маркеров§ шаблона.

    Например: 'user=§admin§&pass=§secret§' → ['admin', 'secret']
    """
    defaults = []
    i = 0
    while i < len(template):
        start = template.find("§", i)
        if start == -1:
            break
        end = template.find("§", start + 1)
        if end == -1:
            break
        defaults.append(template[start + 1:end])
        i = end + 1
    return defaults


def load_payloads_from_file(path: str) -> list[str]:
    result = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                result.append(stripped)
    except Exception:
        pass
    return result


def generate_numeric_payloads(start: int, end: int, step: int = 1) -> list[str]:
    """Числовой диапазон [start, end) с шагом step."""
    return [str(n) for n in range(start, end, step)]


def generate_char_payloads(charset: str, min_len: int, max_len: int) -> list[str]:
    """Перебор строк по набору символов заданной длины.

    Осторожно: может быть очень большим. Для min_len > max_len возвращает [].
    """
    result = []
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(charset, repeat=length):
            result.append("".join(combo))
    return result


def process_payload(payload: str, operations: list[str]) -> str:
    """Применить операции из utils/coder.py к payload.

    Операции применяются последовательно (pipeline).
    Неизвестные операции — игнорируются.
    """
    from pentool.utils.coder import OPERATIONS
    result = payload
    for op in operations:
        func = OPERATIONS.get(op)
        if func is not None:
            try:
                result = func(result)
            except Exception:
                pass
    return result


class IntruderAttack:
    """Выполняет intruder-атаку заданного типа."""

    def __init__(
        self,
        config: IntruderConfig,
        db_path: str | None = None,
        http_client=None,
    ) -> None:
        self._config = config
        self._db_path = db_path
        self._http_client = http_client
        self._attack_id = str(uuid.uuid4())
        self._is_running = False
        self._paused = False
        self._stopped = False
        self._done = 0
        self._total = 0
        self._results: list[IntruderResult] = []
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # не на паузе изначально

    @property
    def attack_id(self) -> str:
        return self._attack_id

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def total_requests(self) -> int:
        return self._total

    @property
    def progress(self) -> tuple[int, int]:
        return self._done, self._total

    @property
    def results(self) -> list[IntruderResult]:
        return list(self._results)

    def _iter_sniper(self) -> Iterator[list[str]]:
        """Один набор payload'ов, по одной позиции за раз.
        N_positions × M запросов.
        Незатрагиваемые позиции сохраняют оригинальное значение из шаблона.
        """
        n_positions = count_markers(self._config.template)
        defaults = extract_marker_defaults(self._config.template)
        # Дополняем defaults до n_positions пустыми строками на случай рассинхрона
        while len(defaults) < n_positions:
            defaults.append("")
        # Берём только первый payload set для всех позиций
        payloads = self._config.payload_sets[0] if self._config.payload_sets else []
        for pos_idx in range(n_positions):
            for payload in payloads:
                # В позиции pos_idx подставляем payload, в остальных — оригинал
                values = list(defaults)
                values[pos_idx] = payload
                yield values

    def _iter_battering_ram(self) -> Iterator[list[str]]:
        """Один payload во все позиции одновременно. M запросов."""
        n_positions = count_markers(self._config.template)
        payloads = self._config.payload_sets[0] if self._config.payload_sets else []
        for payload in payloads:
            yield [payload] * n_positions

    def _iter_pitchfork(self) -> Iterator[list[str]]:
        """Параллельно берёт по одному из каждого набора (zip). min(M) запросов."""
        sets = self._config.payload_sets
        if not sets:
            return
        for combo in zip(*sets):
            yield list(combo)

    def _iter_cluster_bomb(self) -> Iterator[list[str]]:
        """Декартово произведение всех наборов. M1×M2×... запросов."""
        sets = self._config.payload_sets
        if not sets:
            return
        for combo in itertools.product(*sets):
            yield list(combo)

    def _get_iterator(self) -> Iterator[list[str]]:
        t = self._config.attack_type
        if t == AttackType.SNIPER:
            return self._iter_sniper()
        elif t == AttackType.BATTERING_RAM:
            return self._iter_battering_ram()
        elif t == AttackType.PITCHFORK:
            return self._iter_pitchfork()
        elif t == AttackType.CLUSTER_BOMB:
            return self._iter_cluster_bomb()
        return iter([])

    def _count_total(self) -> int:
        """Подсчитать общее количество запросов (без реального выполнения)."""
        return sum(1 for _ in self._get_iterator())

    async def run(
        self,
        on_result: Callable[[IntruderResult], None],
        on_progress: Callable[[int, int], None],
    ) -> None:
        self._is_running = True
        self._stopped = False
        self._done = 0
        self._results = []

        combinations = list(self._get_iterator())
        self._total = len(combinations)
        logger.info("INTRUDER: run() started, total=%d, type=%s, threads=%d", self._total, self._config.attack_type, self._config.threads)
        on_progress(0, self._total)

        sem = asyncio.Semaphore(self._config.threads)

        async def _run_one(req_num: int, payload_values: list[str]) -> None:
            if self._stopped:
                return
            # Ожидаем снятия паузы
            await self._pause_event.wait()
            if self._stopped:
                return

            async with sem:
                if self._stopped:
                    return

                # Подставляем payload'ы
                request_raw = substitute_payload(self._config.template, payload_values)

                # Задержка
                if self._config.delay_ms > 0:
                    await asyncio.sleep(self._config.delay_ms / 1000.0)

                result = await self._send_request(req_num, payload_values, request_raw)
                self._results.append(result)
                on_result(result)
                self._done += 1
                on_progress(self._done, self._total)

        tasks = [
            asyncio.create_task(_run_one(i + 1, vals))
            for i, vals in enumerate(combinations)
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._is_running = False

    async def _send_request(
        self,
        req_num: int,
        payload_values: list[str],
        request_raw: str,
    ) -> IntruderResult:
        import time
        t0 = time.monotonic()
        status = None
        length = None
        error_msg = None

        try:
            from pentool.utils.parser import parse_http_request
            from pentool.utils.http_client import HTTPClient

            req = parse_http_request(request_raw)
            async with HTTPClient(timeout=self._config.timeout) as client:
                resp = await client.send(req)
            status = resp.status
            body = resp.body if isinstance(resp.body, (bytes, str)) else b""
            length = len(body) if isinstance(body, bytes) else len(body.encode("utf-8", errors="replace"))
        except Exception as exc:
            error_msg = str(exc)
            logger.warning("INTRUDER: _send_request #%d error: %s", req_num, exc)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("INTRUDER: #%d payload=%s status=%s length=%s time=%dms", req_num, payload_values, status, length, elapsed_ms)

        return IntruderResult(
            id=str(uuid.uuid4()),
            attack_id=self._attack_id,
            request_number=req_num,
            payload_values=payload_values,
            request_raw=request_raw,
            response_status=status,
            response_length=length,
            response_time_ms=elapsed_ms,
            error=error_msg,
        )

    async def pause(self) -> None:
        self._paused = True
        self._pause_event.clear()

    async def resume(self) -> None:
        self._paused = False
        self._pause_event.set()

    async def stop(self) -> None:
        self._stopped = True
        self._pause_event.set()  # разблокировать ожидающие
        self._is_running = False

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "#", "Payloads", "Status", "Length", "Time(ms)", "Error", "Timestamp"
            ])
            for r in self._results:
                writer.writerow([
                    r.request_number,
                    " | ".join(r.payload_values),
                    r.response_status or "",
                    r.response_length or "",
                    r.response_time_ms or "",
                    r.error or "",
                    r.timestamp.isoformat(),
                ])
