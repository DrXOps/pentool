"""Payload-set serialization helpers for the Intruder screen (Этап 6).

Extracted from IntruderScreen so the lazy payload-source <-> JSON mapping is
pure and testable. FilePayloadSource etc. live in pentool.modules.intruder;
these helpers convert between their objects and a JSON-serializable envelope,
never materializing the (potentially huge) enumerated file/range contents.
"""

from __future__ import annotations

from pentool.modules.intruder import (
    CharPayloadSource,
    ChainedPayloadSource,
    FilePayloadSource,
    NumericPayloadSource,
)


def deserialize_payloads(raw_sets: list) -> list:
    """Inverse of serialize_payloads — reconstitute lazy payload sources."""
    result = []
    for entry in raw_sets:
        if isinstance(entry, dict) and "__file__" in entry:
            result.append(FilePayloadSource(entry["__file__"], count=entry.get("count")))
        elif isinstance(entry, dict) and "__numeric__" in entry:
            result.append(NumericPayloadSource(
                entry.get("start", 0), entry.get("end", 0), entry.get("step", 1)
            ))
        elif isinstance(entry, dict) and "__charset__" in entry:
            result.append(CharPayloadSource(
                entry.get("__charset__", ""), entry.get("min_len", 1), entry.get("max_len", 1)
            ))
        elif isinstance(entry, dict) and "__chained__" in entry:
            result.append(ChainedPayloadSource(
                *deserialize_payloads(entry["__chained__"])
            ))
        elif isinstance(entry, list):
            result.append(entry)
        else:
            result.append([])
    return result


def serialize_payloads(sets: list) -> list:
    """JSON-serializable form of a payload-set list.

    A plain list[str] set serializes as-is. A FilePayloadSource set
    serializes as {"__file__": path, "count": N} — its file path and
    (if already known) line count, NOT its contents (writing out every line
    of a multi-GB payload file would be the same "load a 30GB file into
    memory" problem this avoids). Numeric/Char sources serialize as their
    small constructor params. Chained sources wrap inner sources recursively
    via a {"__chained__": [...]} envelope. Only a plain `list[str]` (the
    base case) is ever actually iterated into a JSON array here.
    """
    result = []
    for entry in sets:
        if isinstance(entry, FilePayloadSource):
            result.append({"__file__": entry.path, "count": entry.cached_count})
        elif isinstance(entry, NumericPayloadSource):
            result.append({
                "__numeric__": True,
                "start": entry.start, "end": entry.end, "step": entry.step,
            })
        elif isinstance(entry, CharPayloadSource):
            result.append({
                "__charset__": entry.charset,
                "min_len": entry.min_len, "max_len": entry.max_len,
            })
        elif isinstance(entry, ChainedPayloadSource):
            result.append({
                "__chained__": serialize_payloads(list(entry._sources)),
            })
        else:
            result.append(list(entry))
    return result
