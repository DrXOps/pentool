"""Ensure every persistent aiosqlite connection runs on a daemon thread.

aiosqlite creates its worker thread as non-daemon (`Thread(...)` in
`Connection.__init__`). A non-daemon thread keeps the interpreter alive after
the TUI's run() returns — so a normal exit can hang waiting on SQLite workers
that never finish (one of the " завис на выходе " failure modes). Marking them
daemon lets the process exit promptly; data is still flushed because we close
the storage explicitly before exit.

Call `make_aiosqlite_daemon(db)` right after `aiosqlite.connect(...)` and
before awaiting it (the worker thread starts only on connect).
"""

from __future__ import annotations

import aiosqlite


def make_aiosqlite_daemon(db: aiosqlite.Connection) -> aiosqlite.Connection:
    """Mark *db*'s worker thread as daemon so it cannot block interpreter exit.

    Must be called before the connection is awaited/entered (the thread starts
    during connect). Safe: no-op-ish if the attribute is missing.
    """
    try:
        thread = getattr(db, "_thread", None)
        if thread is not None:
            thread.daemon = True
    except Exception:
        pass
    return db
