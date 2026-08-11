"""Intruder — automated attack module with payload substitution."""

from __future__ import annotations

import asyncio
import csv
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator

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
    payload_values: list[str]          # values per position
    request_raw: str
    response_raw: str | None = None    # full HTTP response
    response_status: int | None = None
    response_length: int | None = None
    response_time_ms: int | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IntruderConfig:
    template: str                      # raw HTTP with §payload§ markers
    attack_type: AttackType
    payload_sets: list[list[str]]      # one list per position
    threads: int = 10
    delay_ms: int = 0
    follow_redirects: bool = False
    timeout: int = 30
    # Turbo mode settings (PRO)
    turbo_pipeline: bool = False       # HTTP pipelining
    turbo_keep_alive: bool = True      # connection reuse
    turbo_rate_limit: int | None = None  # requests per second limit


def parse_markers(template: str) -> tuple[str, list[tuple[int, int]]]:
    """Find §markers§ in the template.

    Returns:
        (clean_template, positions) where positions is a list of (start, end)
        in clean_template for each position.
    """
    positions: list[tuple[int, int]] = []
    result = []
    i = 0

    while i < len(template):
        if template[i] == "§":
            # Look for closing §
            j = template.find("§", i + 1)
            if j == -1:
                # No closing marker — leave as is
                result.append(template[i])
                i += 1
                continue
            # Extract marker content
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
    """Find positions of §...§ pairs in a string. Returns (start_§, end_§)."""
    positions = []
    i = 0
    while i < len(template):
        start = template.find("§", i)
        if start == -1:
            break
        end = template.find("§", start + 1)
        if end == -1:
            break
        positions.append((start, end + 1))  # including both §
        i = end + 1
    return positions


def substitute_payload(template: str, payload_values: list[str]) -> str:
    """Substitute payloads into §markers§ of the template.

    Replaces markers left to right. If payload_values has fewer items than markers —
    remaining markers are replaced with empty string.
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
    """Count the number of §markers§ in the template."""
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
    """Extract original values from §markers§ in the template.

    Example: 'user=§admin§&pass=§secret§' -> ['admin', 'secret']
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


class FilePayloadSource:
    """Lazily-iterated payload set backed by a file on disk.

    Reads and yields one payload line at a time using Python's normal
    buffered text-file iteration (`for line in f:`) — this already streams
    the file rather than loading it whole, unlike `load_payloads_from_file()`
    above (which calls `Path(path).read_text()` + `.splitlines()`, materializing
    the entire file — and a second full copy as a list of lines — in memory).
    That eager path is fine for small payload files (kept for backward
    compatibility) but is the wrong tool for a "load a 30GB payload file"
    requirement: this class exists so the Intruder TUI/attack engine never
    has to hold more than one line at a time in memory for such a file.

    Blank lines and lines starting with '#' are skipped — same convention
    as `load_payloads_from_file()`.

    Supports repeated iteration (`for x in source` more than once, needed by
    Pitchfork's `zip()` over multiple sets and Cluster Bomb's cartesian
    product re-iterating inner sets) by reopening the file fresh on every
    `__iter__()` call — each pass costs one more disk read of the file, but
    memory stays O(1) regardless of file size or how many passes are made.
    """

    __slots__ = ("path", "encoding", "_count")

    def __init__(self, path: str, encoding: str = "utf-8", count: int | None = None) -> None:
        self.path = path
        self.encoding = encoding
        self._count = count  # cached qualifying-line count, or None if unknown

    def __iter__(self):
        with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    yield stripped

    def __len__(self) -> int:
        """Number of qualifying (non-blank, non-comment) lines.

        Computed by a full streaming pass over the file the first time this
        is called, then cached — callers that already know the count (e.g.
        the TUI, which counts while showing a live progress readout during
        load) should call `set_count()` first to avoid a second full read.
        """
        if self._count is None:
            self._count = sum(1 for _ in self)
        return self._count

    def __bool__(self) -> bool:
        # Without this, `bool(x)` would fall back to `__len__() != 0` anyway
        # (Python's default when only __len__ is defined) — spelled out
        # explicitly here since that implicit fallback is easy to miss and
        # its cost (a full recount on first use if not yet cached) matters
        # for a multi-GB file.
        return len(self) > 0

    def set_count(self, count: int) -> None:
        """Attach a precomputed qualifying-line count (e.g. from the TUI's
        streaming preload with progress), avoiding a redundant full re-read
        the first time `len()`/`bool()` is used."""
        self._count = count

    @property
    def cached_count(self) -> int | None:
        """The cached qualifying-line count, or None if never computed/set.

        Unlike `len()`, never triggers a file read — used by callers (e.g.
        the TUI's state serializer) that need to know the count *if it's
        already cheap to know* without accidentally forcing a full
        multi-GB file scan as a side effect of checking.
        """
        return self._count

    @property
    def is_count_known(self) -> bool:
        """True if `len()` can answer instantly (no file read)."""
        return self._count is not None

    def head(self, n: int) -> list[str]:
        """Return up to the first `n` qualifying lines.

        Used for TUI previews of a huge file-backed set — reads at most `n`
        lines regardless of total file size, and explicitly closes the file
        afterward rather than relying on a `for` loop's `break` to trigger
        generator-close-on-GC (correct in CPython but not a guarantee worth
        depending on for something as scarce as an open file handle).
        """
        result: list[str] = []
        with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
            for line in f:
                if len(result) >= n:
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    result.append(stripped)
        return result

    def __repr__(self) -> str:
        return f"FilePayloadSource({self.path!r}, count={self._count!r})"


def count_lines_with_progress(
    path: str,
    encoding: str = "utf-8",
    on_progress: Callable[[int, int, int], None] | None = None,
) -> int:
    """Stream-count qualifying (non-blank, non-comment) lines in `path`.

    Meant to run in a worker thread (via loop.run_in_executor) while the TUI
    shows a live "N lines counted so far" readout — `on_progress(count,
    bytes_read, total_bytes)` fires at most a few times per second (NOT once
    per line — for a file with hundreds of millions of lines, calling back
    into the TUI thread that often would itself become the bottleneck).

    Reads in binary chunks and splits on b"\\n" instead of iterating the file
    in text mode line-by-line. Text-mode iteration decodes + strips one line
    at a time entirely in the Python interpreter loop, which holds the GIL
    almost continuously for a large file — measured on a 47MB/6M-line file:
    the text-mode version stalled the asyncio event loop thread for the
    *entire* duration of the read (this function always runs in a worker
    thread via run_in_executor, but the GIL is process-wide — a Python-level
    tight loop in one thread can still starve another). This is the root
    cause behind "the whole TUI freezes when loading a 100+MB payload file".
    Chunked binary reads + bytes.split do the bulk of the work in C, which
    releases the GIL far more often and keeps the UI thread responsive.
    Splitting only on b"\\n" is UTF-8-safe even for multi-byte chars split
    across a chunk boundary, since 0x0A never appears as a continuation byte.
    """
    import time

    try:
        total_bytes = Path(path).stat().st_size
    except Exception:
        total_bytes = 0

    _CHUNK_SIZE = 4 * 1024 * 1024  # 4MB

    def _is_qualifying(raw: bytes) -> bool:
        stripped = raw.strip()
        return bool(stripped) and not stripped.startswith(b"#")

    count = 0
    bytes_read = 0
    leftover = b""
    last_report = time.monotonic()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            bytes_read += len(chunk)
            data = leftover + chunk
            lines = data.split(b"\n")
            leftover = lines.pop()  # last piece may be an incomplete line
            count += sum(1 for line in lines if _is_qualifying(line))
            now = time.monotonic()
            if on_progress is not None and (now - last_report) >= 0.2:
                last_report = now
                on_progress(count, bytes_read, total_bytes)
    if _is_qualifying(leftover):
        count += 1
    if on_progress is not None:
        on_progress(count, total_bytes, total_bytes)
    return count


class ProcessedPayloads:
    """Lazily applies payload-processing ops (URL-encode/Base64/…) to each
    item of `source` as it is iterated.

    Wraps any iterable payload set — a plain `list[str]` or a
    `FilePayloadSource` — without ever materializing the whole set into a
    new list. Without this, `IntruderScreen.action_start_attack()`'s old
    `[apply(p, ops) for p in ps]` list-comprehension would itself read an
    entire multi-GB file-backed set into memory just to apply processing,
    even after the file load itself had been made lazy.
    """

    __slots__ = ("_source", "_ops", "_apply")

    def __init__(self, source, ops: list[str], apply: Callable[[str, list[str]], str]) -> None:
        self._source = source
        self._ops = ops
        self._apply = apply

    def __iter__(self):
        for p in self._source:
            yield self._apply(p, self._ops)

    def __len__(self) -> int:
        return len(self._source)

    def __bool__(self) -> bool:
        return len(self._source) > 0


def generate_numeric_payloads(start: int, end: int, step: int = 1) -> list[str]:
    """Numeric range [start, end) with step."""
    return [str(n) for n in range(start, end, step)]


def generate_char_payloads(charset: str, min_len: int, max_len: int) -> list[str]:
    """Brute-force strings over a charset of given lengths.

    Warning: can be very large. Returns [] if min_len > max_len.
    """
    result = []
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(charset, repeat=length):
            result.append("".join(combo))
    return result


def process_payload(payload: str, operations: list[str]) -> str:
    """Apply operations from utils/coder.py to a payload.

    Operations are applied sequentially (pipeline).
    Unknown operations are ignored.
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


def _lazy_cartesian_product(*sets):
    """Cartesian product of `sets`, re-iterating each set fresh on every
    step instead of caching its items in memory (unlike itertools.product,
    see _iter_cluster_bomb's docstring for why that matters here).

    Equivalent output/order to itertools.product(*sets) — right-most set
    advances fastest. Iterative (not recursive) so the payload-set count
    isn't bounded by Python's recursion limit.

    Cost trade-off vs itertools.product: each of the first N-1 sets is
    re-iterated once per combination of the sets to its right — for
    file-backed sets (FilePayloadSource) that means re-reading those files
    from disk repeatedly. Only the LAST set streams through in a single
    pass. This is the right trade for this module's purpose (never holding
    a multi-GB payload file's contents in memory) — put the largest/only
    huge file-backed set last (right-most) in payload_sets to minimize
    repeated disk reads, matching the standard itertools.product usage
    guidance for expensive-to-reiterate inputs.
    """
    if not sets:
        return
    if len(sets) == 1:
        for item in sets[0]:
            yield (item,)
        return
    for head in sets[0]:
        for rest in _lazy_cartesian_product(*sets[1:]):
            yield (head,) + rest


class IntruderAttack:
    """Executes an intruder attack of the specified type."""

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
        self._pause_event.set()  # not paused initially

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
        """One payload set, one position at a time.
        N_positions x M requests.
        Untouched positions keep the original value from the template.
        """
        n_positions = count_markers(self._config.template)
        defaults = extract_marker_defaults(self._config.template)
        # Pad defaults to n_positions with empty strings in case of mismatch
        while len(defaults) < n_positions:
            defaults.append("")
        # Use only the first payload set for all positions
        payloads = self._config.payload_sets[0] if self._config.payload_sets else []
        for pos_idx in range(n_positions):
            for payload in payloads:
                # At pos_idx substitute payload, at others use original
                values = list(defaults)
                values[pos_idx] = payload
                yield values

    def _iter_battering_ram(self) -> Iterator[list[str]]:
        """One payload into all positions simultaneously. M requests."""
        n_positions = count_markers(self._config.template)
        payloads = self._config.payload_sets[0] if self._config.payload_sets else []
        for payload in payloads:
            yield [payload] * n_positions

    def _iter_pitchfork(self) -> Iterator[list[str]]:
        """Takes one from each set in parallel (zip). min(M) requests.

        zip() pulls one item at a time from each set via a single iterator
        per set — it never materializes a set's contents, so this is
        already safe for FilePayloadSource-backed (multi-GB file) sets
        without any change.
        """
        sets = self._config.payload_sets
        if not sets:
            return
        for combo in zip(*sets):
            yield list(combo)

    def _iter_cluster_bomb(self) -> Iterator[list[str]]:
        """Cartesian product of all sets. M1×M2×... requests.

        NOT itertools.product(*sets) — CPython's implementation explicitly
        "completely consumes the input iterables, keeping pools of values
        in memory" (per its own docs) before producing anything. For a
        FilePayloadSource backed by a multi-GB payload file, that means
        reading the entire file into a tuple in memory just to start the
        attack — exactly the OOM this module is meant to avoid.
        _lazy_cartesian_product below re-iterates each inner set once per
        outer-loop step instead (costs extra disk reads for file-backed
        sets on repeated passes, never extra memory) — see its docstring.
        """
        sets = self._config.payload_sets
        if not sets:
            return
        for combo in _lazy_cartesian_product(*sets):
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
        """Number of requests the current config would produce.

        Uses len() on the configured payload sets (O(1) for a plain list,
        one cached streaming pass for a FilePayloadSource — see its
        __len__) and simple arithmetic, instead of the old
        `sum(1 for _ in self._get_iterator())`, which for Cluster Bomb
        walked the full (potentially huge) cartesian product just to count
        it — wasted, since the same numbers are derivable from the input
        set sizes directly.
        """
        sets = self._config.payload_sets
        if not sets:
            return 0
        t = self._config.attack_type
        if t == AttackType.SNIPER:
            n_positions = count_markers(self._config.template)
            return n_positions * len(sets[0])
        elif t == AttackType.BATTERING_RAM:
            return len(sets[0])
        elif t == AttackType.PITCHFORK:
            return min(len(s) for s in sets)
        elif t == AttackType.CLUSTER_BOMB:
            total = 1
            for s in sets:
                total *= len(s)
            return total
        return 0

    async def run(
        self,
        on_result: Callable[[IntruderResult], None],
        on_progress: Callable[[int, int], None],
    ) -> None:
        self._is_running = True
        self._stopped = False
        self._done = 0
        self._results = []

        # NOT `combinations = list(self._get_iterator())` — that materialized
        # every (payload_values) combination into one Python list before the
        # attack's first request was even sent. For Cluster Bomb (cartesian
        # product) or a single Sniper/Battering Ram set backed by a
        # multi-GB payload file, that list itself can be gigabytes, defeating
        # the whole point of streaming the file lazily (see FilePayloadSource
        # / _lazy_cartesian_product above). `_count_total()` gets the total
        # from the input sets' sizes directly (O(1) or one cached streaming
        # pass) instead of counting by materializing the iterator.
        self._total = self._count_total()
        logger.info("INTRUDER: run() started, total=%d, type=%s, threads=%d", self._total, self._config.attack_type, self._config.threads)
        on_progress(0, self._total)

        # БАГ-D: reuse a single HTTPClient (and its aiohttp connection pool)
        # for the whole attack instead of opening/closing a new TCP+TLS
        # connection per request. aiohttp.ClientSession is safe to share
        # across concurrent coroutines. Only close it here if we created
        # it ourselves — an injected client (self._http_client) is owned
        # by the caller.
        from pentool.utils import http_client as _http_client_mod
        owns_client = self._http_client is None
        client = self._http_client or _http_client_mod.HTTPClient(timeout=self._config.timeout)

        async def _run_one(req_num: int, payload_values: list[str]) -> None:
            if self._stopped:
                return
            # Wait for unpause
            await self._pause_event.wait()
            if self._stopped:
                return

            # Substitute payloads
            request_raw = substitute_payload(self._config.template, payload_values)

            # Delay
            if self._config.delay_ms > 0:
                await asyncio.sleep(self._config.delay_ms / 1000.0)

            result = await self._send_request(req_num, payload_values, request_raw, client)
            self._results.append(result)
            on_result(result)
            self._done += 1
            on_progress(self._done, self._total)

        # ── Bounded worker pool instead of eager fan-out ──────────────────────
        # BEFORE: tasks = [asyncio.create_task(_run_one(...)) for i, vals in
        # enumerate(combinations)] created ALL len(combinations) asyncio.Task
        # objects up front (for Cluster Bomb this is the cartesian product of
        # every payload set — can be hundreds of thousands of live tasks),
        # each holding a live coroutine frame. `sem = asyncio.Semaphore(threads)`
        # only throttled how many of those already-created tasks could reach
        # the actual HTTP-send section concurrently — it did nothing to stop
        # every task from existing in memory at once. Identical pattern to the
        # one found and fixed in ScanEngine.run_active_on_requests (see
        # MYPLANS/MEMORY_LEAK_INVESTIGATION_PLAN_2026-08-08.md, H1/H2).
        #
        # AFTER: a fixed pool of `threads` worker coroutines pulls the next
        # (req_num, payload_values) tuple off a single shared iterator and
        # runs it to completion before pulling the next one. `next(task_iter)`
        # is synchronous (no `await` inside it), so sharing one iterator
        # across concurrently-running worker coroutines is safe under
        # asyncio's cooperative scheduling — no lock needed. At most
        # `threads` _run_one() calls (and their live coroutine frames) exist
        # at any given moment, regardless of how large the payload sets are.
        # The semaphore is no longer needed — the worker count itself bounds
        # concurrency to exactly `threads`. `self._get_iterator()` itself is
        # also lazy end-to-end now (FilePayloadSource/_lazy_cartesian_product),
        # so nothing upstream of this line materializes the full combination
        # set either.
        task_iter = iter(enumerate(self._get_iterator(), start=1))

        async def _worker() -> None:
            for req_num, vals in task_iter:
                if self._stopped:
                    return
                await _run_one(req_num, vals)

        try:
            n_workers = min(self._config.threads, self._total) if self._total else 0
            if n_workers:
                await asyncio.gather(*[_worker() for _ in range(n_workers)])
        finally:
            if owns_client:
                try:
                    await client.close()
                except Exception:
                    pass
            self._is_running = False

    async def _send_request(
        self,
        req_num: int,
        payload_values: list[str],
        request_raw: str,
        client=None,
    ) -> IntruderResult:
        import time
        t0 = time.monotonic()
        status = None
        length = None
        error_msg = None
        response_raw = None

        try:
            from pentool.utils.http_client import HTTPClient
            from pentool.utils.parser import parse_http_request

            req = parse_http_request(request_raw)
            if client is not None:
                # Reused client (БАГ-D) — do not close, owned by run()/caller.
                resp = await client.send(req)
            else:
                # Fallback for direct/standalone calls (e.g. tests) that
                # don't go through run(): open a short-lived client.
                async with HTTPClient(timeout=self._config.timeout) as tmp_client:
                    resp = await tmp_client.send(req)
            status = resp.status
            body = resp.body if isinstance(resp.body, (bytes, str)) else b""
            length = len(body) if isinstance(body, bytes) else len(body.encode("utf-8", errors="replace"))

            # Build response_raw
            from pentool.modules.scanner.checks.helpers import format_response_raw
            response_raw = format_response_raw(resp)
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
            response_raw=response_raw,
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
        self._pause_event.set()  # unblock waiting tasks
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
