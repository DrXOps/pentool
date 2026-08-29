"""Proxy request-table domain: Arrow-building helpers for the HTTP history table.

Extracted from ProxyScreen (Этап 6, proxy_table domain) so the row→Arrow
mapping is pure and testable in isolation. Both the full-rebuild path
("_rows_to_arrow") and the incremental append path share these so column
order and row formatting stay in sync.
"""

from __future__ import annotations

import datetime
import pyarrow as pa

# Column order for the HTTP history table. Shared by _row_to_record and
# _rows_to_arrow so both stay in sync.
COL_NAMES = ["ID", "Host", "Method", "URL", "Status", "Size", "Time"]

_COLOR_DOTS: dict[str, str] = {
    "red":    "🔴",
    "orange": "🟠",
    "yellow": "🟡",
    "green":  "🟢",
    "blue":   "🔵",
    "purple": "🟣",
}


def make_empty_table() -> pa.Table:
    """Empty Arrow table with the required columns."""
    return pa.table({
        "ID":     pa.array([], type=pa.int64()),
        "Host":   pa.array([], type=pa.string()),
        "Method": pa.array([], type=pa.string()),
        "URL":    pa.array([], type=pa.string()),
        "Status": pa.array([], type=pa.string()),
        "Size":   pa.array([], type=pa.string()),
        "Time":   pa.array([], type=pa.string()),
    })


def row_to_record(r: dict) -> tuple:
    """Convert one HttpStorage metadata dict into a DataTable row tuple.

    Column order matches COL_NAMES / rows_to_arrow: ID, Host, Method, URL,
    Status, Size, Time. Shared by the full rebuild path (rows_to_arrow) and
    the incremental append_rows() path so both stay in sync.
    """
    url = str(r.get("url", "") or "")
    status = r.get("status_code")
    length = r.get("length")
    ts = r.get("timestamp")
    if ts:
        try:
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        except Exception:
            time_str = "-"
    else:
        time_str = "-"

    # Prepend color dot and/or 💬 comment marker to Host column — both are
    # left-aligned prefixes so marked/commented requests are visible in the
    # list without opening them.
    host = str(r.get("host", "") or "")
    color = str(r.get("color", "") or "")
    dot = _COLOR_DOTS.get(color, "")
    comment = str(r.get("comment", "") or "")
    comment_marker = "💬 " if comment.strip() else ""
    prefix = f"{dot} " if dot else ""
    host_display = f"{prefix}{comment_marker}{host}"

    return (
        r.get("id", 0),
        host_display,
        str(r.get("method", "") or ""),
        url[:80] + "…" if len(url) > 80 else url,
        str(status) if status is not None else "-",
        str(length) if length is not None else "-",
        time_str,
    )


def rows_to_arrow(rows: list[dict]) -> pa.Table:
    """Convert a list of dicts from HttpStorage into an Arrow table."""
    if not rows:
        return make_empty_table()
    ids, hosts, methods, urls, statuses, sizes, times = [], [], [], [], [], [], []
    for r in rows:
        rid, host, method, url, status, size, tstr = row_to_record(r)
        ids.append(rid)
        hosts.append(host)
        methods.append(method)
        urls.append(url)
        statuses.append(status)
        sizes.append(size)
        times.append(tstr)
    return pa.table({
        "ID":     pa.array(ids,      type=pa.int64()),
        "Host":   pa.array(hosts,    type=pa.string()),
        "Method": pa.array(methods,  type=pa.string()),
        "URL":    pa.array(urls,     type=pa.string()),
        "Status": pa.array(statuses, type=pa.string()),
        "Size":   pa.array(sizes,    type=pa.string()),
        "Time":   pa.array(times,    type=pa.string()),
    })
