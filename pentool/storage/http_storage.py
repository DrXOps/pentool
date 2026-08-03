"""HttpStorage — SQLite storage for HTTP requests/responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from pentool.core.logging import get_logger

logger = get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         REAL    NOT NULL,
    host              TEXT    NOT NULL DEFAULT '',
    method            TEXT    NOT NULL DEFAULT '',
    url               TEXT    NOT NULL DEFAULT '',
    has_params        INTEGER NOT NULL DEFAULT 0,
    edited            INTEGER NOT NULL DEFAULT 0,
    status_code       INTEGER,
    length            INTEGER,
    mime_type         TEXT,
    extension         TEXT,
    is_websocket      INTEGER NOT NULL DEFAULT 0,
    request_headers   TEXT,
    response_headers  TEXT,
    request_body      TEXT,
    response_body     TEXT,
    request_body_ref  TEXT,
    response_body_ref TEXT,
    comment           TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_host   ON requests(host);
CREATE INDEX IF NOT EXISTS idx_status ON requests(status_code);
CREATE INDEX IF NOT EXISTS idx_ts     ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_method ON requests(method);
CREATE INDEX IF NOT EXISTS idx_ws     ON requests(is_websocket);
CREATE VIRTUAL TABLE IF NOT EXISTS requests_fts
    USING fts5(url, host, request_body, response_body,
               content='requests', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS requests_ai AFTER INSERT ON requests BEGIN
    INSERT INTO requests_fts(rowid, url, host, request_body, response_body)
    VALUES (new.id, new.url, new.host,
            COALESCE(new.request_body, ''),
            COALESCE(new.response_body, ''));
END;
CREATE TRIGGER IF NOT EXISTS requests_ad AFTER DELETE ON requests BEGIN
    INSERT INTO requests_fts(requests_fts, rowid, url, host, request_body, response_body)
    VALUES ('delete', old.id, old.url, old.host,
            COALESCE(old.request_body, ''),
            COALESCE(old.response_body, ''));
END;
CREATE TRIGGER IF NOT EXISTS requests_au AFTER UPDATE ON requests BEGIN
    INSERT INTO requests_fts(requests_fts, rowid, url, host, request_body, response_body)
    VALUES ('delete', old.id, old.url, old.host,
            COALESCE(old.request_body, ''),
            COALESCE(old.response_body, ''));
    INSERT INTO requests_fts(rowid, url, host, request_body, response_body)
    VALUES (new.id, new.url, new.host,
            COALESCE(new.request_body, ''),
            COALESCE(new.response_body, ''));
END;
"""

_LARGE_BODY_THRESHOLD = 1 * 1024 * 1024  # 1 MB


class HttpStorage:
    """Async SQLite storage for HTTP records.

    Lifecycle:
        storage = HttpStorage()
        await storage.init_db("~/.config/pentool/history.db")
        row_id = await storage.add_request(req, resp)
        ...
        await storage.close()
    """

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None
        self._path: str = ""

    async def init_db(self, path: str) -> None:
        """Open/create the database and apply the schema."""
        self._path = str(Path(path).expanduser())
        logger.debug("HttpStorage: init_db at %s", self._path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        # Migration: add is_websocket column if missing (for existing databases)
        try:
            await self._db.execute(
                "ALTER TABLE requests ADD COLUMN is_websocket INTEGER NOT NULL DEFAULT 0"
            )
            await self._db.commit()
        except Exception:
            pass  # column already exists — this is normal, no need to log
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA cache_size=-32000")  # 32 MB cache
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def switch_db(self, path: str) -> None:
        logger.info("HttpStorage: switch_db called for %s", path)
        await self.close()
        await self.init_db(path)
        # Log the count of existing records after switching
        try:
            count = await self._db.execute("SELECT COUNT(*) FROM requests")
            row = await count.fetchone()
            total = row[0] if row else 0
            logger.info("HttpStorage: switched to %s, found %d existing records", path, total)
        except Exception as exc:
            logger.warning("HttpStorage: could not count records after switch: %s", exc)

    async def add_request(self, req: Any, resp: Any = None, is_websocket: bool = False) -> int:
        assert self._db, "init_db() not called"

        url = getattr(req, "url", "") or ""
        parsed = urlparse(url)
        host = parsed.netloc or getattr(req, "headers", {}).get("Host", "")
        method = getattr(req, "method", "") or ""
        has_params = 1 if parsed.query else 0
        ext = Path(parsed.path).suffix.lstrip(".").lower() if parsed.path else ""
        mime_type = ""

        req_headers = getattr(req, "headers", {}) or {}
        req_body = getattr(req, "body", None)
        if isinstance(req_body, bytes):
            req_body = req_body.decode("utf-8", errors="replace")

        resp_headers: dict = {}
        resp_body: str | None = None
        status_code: int | None = None
        length: int | None = None

        if resp is not None:
            resp_headers = dict(getattr(resp, "headers", {}) or {})
            status_code = getattr(resp, "status", None)
            rb = getattr(resp, "body", None)
            if isinstance(rb, bytes):
                rb = rb.decode("utf-8", errors="replace")
            resp_body = rb
            length = len(resp_body) if resp_body else 0
            ct = resp_headers.get("Content-Type", resp_headers.get("content-type", ""))
            mime_type = ct.split(";")[0].strip()

        # Large bodies → write to disk
        req_body_ref: str | None = None
        resp_body_ref: str | None = None

        if req_body and len(req_body) > _LARGE_BODY_THRESHOLD:
            req_body_ref = "__large__"  # will be replaced after INSERT
            req_body_store = None
        else:
            req_body_store = req_body

        if resp_body and len(resp_body) > _LARGE_BODY_THRESHOLD:
            resp_body_ref = "__large__"
            resp_body_store = None
        else:
            resp_body_store = resp_body

        async with self._db.execute(
            """INSERT INTO requests
               (timestamp, host, method, url, has_params, status_code, length,
                mime_type, extension, is_websocket, request_headers, response_headers,
                request_body, response_body, request_body_ref, response_body_ref)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), host, method, url, has_params,
                status_code, length, mime_type, ext,
                1 if is_websocket else 0,
                json.dumps(dict(req_headers)),
                json.dumps(resp_headers),
                req_body_store, resp_body_store,
                None, None,
            ),
        ) as cur:
            row_id = cur.lastrowid

        # Step 1: commit immediately after INSERT — row_id is locked.
        # If the process crashes after this during file writes — the row exists in DB
        # with ref=NULL. No situation of "file exists, row does not".
        await self._db.commit()

        # Save large bodies with the real row_id
        from pentool.storage.large_body_handler import LargeBodyHandler
        if req_body_ref == "__large__" and req_body:
            ref = LargeBodyHandler.store(row_id, "req", req_body.encode())
            await self._db.execute(
                "UPDATE requests SET request_body_ref=? WHERE id=?", (ref, row_id)
            )
        if resp_body_ref == "__large__" and resp_body:
            ref = LargeBodyHandler.store(row_id, "resp", resp_body.encode())
            await self._db.execute(
                "UPDATE requests SET response_body_ref=? WHERE id=?", (ref, row_id)
            )

        # Step 2: commit UPDATE if there were large bodies
        if (req_body_ref == "__large__" and req_body) or (resp_body_ref == "__large__" and resp_body):
            await self._db.commit()
        logger.debug("HttpStorage: add_request saved row_id=%d (%s %s, ws=%s, status=%s)", row_id, method, url, is_websocket, status_code)
        return row_id

    async def update_response(self, row_id: int, resp: Any) -> None:
        assert self._db
        resp_headers = dict(getattr(resp, "headers", {}) or {})
        status_code = getattr(resp, "status", None)
        rb = getattr(resp, "body", None)
        if isinstance(rb, bytes):
            rb = rb.decode("utf-8", errors="replace")
        length = len(rb) if rb else 0
        ct = resp_headers.get("Content-Type", resp_headers.get("content-type", ""))
        mime_type = ct.split(";")[0].strip()

        await self._db.execute(
            """UPDATE requests SET
               status_code=?, length=?, mime_type=?,
               response_headers=?, response_body=?
               WHERE id=?""",
            (status_code, length, mime_type, json.dumps(resp_headers), rb, row_id),
        )
        await self._db.commit()
        logger.debug("HttpStorage: update_response row_id=%d status=%s", row_id, status_code)

    async def delete(self, row_id: int) -> None:
        assert self._db
        # Delete bodies from disk
        async with self._db.execute(
            "SELECT request_body_ref, response_body_ref FROM requests WHERE id=?",
            (row_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            from pentool.storage.large_body_handler import LargeBodyHandler
            if row["request_body_ref"]:
                LargeBodyHandler.delete(row["request_body_ref"])
            if row["response_body_ref"]:
                LargeBodyHandler.delete(row["response_body_ref"])

        await self._db.execute("DELETE FROM requests WHERE id=?", (row_id,))
        await self._db.commit()

    async def get_metadata_batch(
        self,
        offset: int = 0,
        limit: int = 200,
        filters: dict | None = None,
        order_by: str = "id",
        desc: bool = True,
    ) -> list[dict]:
        assert self._db
        where, params = self._build_where(filters)
        direction = "DESC" if desc else "ASC"
        # Validate order_by against injection
        valid_cols = {"id", "timestamp", "host", "method", "url",
                      "status_code", "length", "mime_type"}
        if order_by not in valid_cols:
            order_by = "id"

        sql = f"""
            SELECT id, timestamp, host, method, url, has_params, edited,
                   status_code, length, mime_type, extension
            FROM requests
            {where}
            ORDER BY {order_by} {direction}
            LIMIT ? OFFSET ?
        """
        async with self._db.execute(sql, params + [limit, offset]) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_full_entry(self, row_id: int) -> dict | None:
        """Load a full record including bodies."""
        assert self._db
        async with self._db.execute(
            "SELECT * FROM requests WHERE id=?", (row_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None

        entry = dict(row)

        # Load bodies from disk if needed
        from pentool.storage.large_body_handler import LargeBodyHandler
        if entry.get("request_body_ref"):
            try:
                entry["request_body"] = LargeBodyHandler.load(
                    entry["request_body_ref"]
                ).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning("get_full_entry: failed to load req body ref=%s: %s", entry["request_body_ref"], e)
                entry["request_body"] = "(could not load body)"

        if entry.get("response_body_ref"):
            try:
                entry["response_body"] = LargeBodyHandler.load(
                    entry["response_body_ref"]
                ).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning("get_full_entry: failed to load resp body ref=%s: %s", entry["response_body_ref"], e)
                entry["response_body"] = "(could not load body)"

        # Deserialize JSON headers
        for key in ("request_headers", "response_headers"):
            raw = entry.get(key)
            if raw:
                try:
                    entry[key] = json.loads(raw)
                except Exception as e:
                    logger.warning("get_full_entry: bad JSON in %s (row_id=%s): %s", key, entry.get("id"), e)
                    entry[key] = {}
            else:
                entry[key] = {}

        return entry

    async def export_all_requests(self, limit: int = 10000) -> list[dict]:
        if not self._db:
            return []
        try:
            async with self._db.execute(
                """SELECT id, timestamp, method, url, request_headers,
                          request_body, request_body_ref,
                          response_headers, response_body, response_body_ref,
                          status_code
                   FROM requests
                   ORDER BY id DESC
                   LIMIT ?""",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        except Exception as exc:
            logger.warning("export_all_requests: query failed: %s", exc)
            return []

        result = []
        from pentool.storage.large_body_handler import LargeBodyHandler
        for row in rows:
            entry = dict(row)
            # Load large bodies
            if entry.get("request_body_ref"):
                try:
                    entry["request_body"] = LargeBodyHandler.load(
                        entry["request_body_ref"]
                    ).decode("utf-8", errors="replace")
                except Exception:
                    entry["request_body"] = ""
            if entry.get("response_body_ref"):
                try:
                    entry["response_body"] = LargeBodyHandler.load(
                        entry["response_body_ref"]
                    ).decode("utf-8", errors="replace")
                except Exception:
                    entry["response_body"] = ""
            # Deserialize headers
            import json as _json
            for key in ("request_headers", "response_headers"):
                raw = entry.get(key)
                if raw and isinstance(raw, str):
                    try:
                        entry[key] = _json.loads(raw)
                    except Exception:
                        entry[key] = {}
                elif not raw:
                    entry[key] = {}
            result.append(entry)

        return result

    async def count(self, filters: dict | None = None) -> int:
        assert self._db
        where, params = self._build_where(filters)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM requests {where}", params
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def count_distinct_hosts(self) -> int:
        assert self._db
        async with self._db.execute(
            "SELECT COUNT(DISTINCT host) FROM requests"
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def search(self, query: str, limit: int = 100) -> list[dict]:
        """Full-text search via FTS5."""
        assert self._db
        sql = """
            SELECT r.id, r.timestamp, r.host, r.method, r.url,
                   r.status_code, r.length, r.mime_type
            FROM requests r
            JOIN requests_fts f ON r.id = f.rowid
            WHERE requests_fts MATCH ?
            ORDER BY r.id DESC
            LIMIT ?
        """
        try:
            async with self._db.execute(sql, (query, limit)) as cur:
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("search: FTS query failed for %r: %s", query, e)
            return []

    async def clear_all(self) -> None:
        """Delete all records and associated large body files from disk."""
        assert self._db
        from pentool.storage.large_body_handler import LargeBodyHandler
        # First collect all file refs
        async with self._db.execute(
            "SELECT request_body_ref, response_body_ref FROM requests"
            " WHERE request_body_ref IS NOT NULL OR response_body_ref IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()
        # Delete files
        for row in rows:
            if row["request_body_ref"]:
                try:
                    LargeBodyHandler.delete(row["request_body_ref"])
                except Exception as e:
                    logger.warning("clear_all: failed to delete req body file %s: %s", row["request_body_ref"], e)
            if row["response_body_ref"]:
                try:
                    LargeBodyHandler.delete(row["response_body_ref"])
                except Exception as e:
                    logger.warning("clear_all: failed to delete resp body file %s: %s", row["response_body_ref"], e)
        # Now delete records from DB
        await self._db.execute("DELETE FROM requests")
        await self._db.execute("DELETE FROM requests_fts")
        await self._db.commit()
        logger.info("HttpStorage: clear_all done, removed %d large body files", len(rows))

    async def get_request_by_id(self, request_id: int) -> dict | None:
        return await self.get_full_entry(request_id)

    async def update_comment(self, request_id: int, comment: str) -> None:
        """Update comment for a request."""
        assert self._db
        await self._db.execute(
            "UPDATE requests SET comment = ? WHERE id = ?",
            (comment, request_id)
        )
        await self._db.commit()

    async def get_comment(self, request_id: int) -> str:
        """Get comment for a request."""
        assert self._db
        async with self._db.execute(
            "SELECT comment FROM requests WHERE id = ?", (request_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else ""

    def _build_where(self, filters: dict | None) -> tuple[str, list]:
        """Build a WHERE clause from a filter dictionary."""
        if not filters:
            return "", []

        clauses: list[str] = []
        params: list = []

        host = filters.get("host")
        if host:
            clauses.append("host LIKE ?")
            params.append(f"%{host}%")

        # List of hosts for "in-scope only" filter
        # Use LIKE to account for variants with port (example.com vs example.com:443)
        hosts = filters.get("hosts")
        if hosts and isinstance(hosts, (list, tuple)) and len(hosts) > 0:
            sub = " OR ".join("(host = ? OR host LIKE ?)" for _ in hosts)
            clauses.append(f"({sub})")
            for h in hosts:
                base = h.split(":")[0]  # strip port if present
                params.append(base)
                params.append(f"{base}:%")

        methods = filters.get("method")
        if methods:
            if isinstance(methods, str):
                methods = [methods]
            placeholders = ",".join("?" * len(methods))
            clauses.append(f"method IN ({placeholders})")
            params.extend(methods)

        status = filters.get("status_code")
        if status:
            if isinstance(status, (list, tuple)) and len(status) == 2:
                clauses.append("status_code BETWEEN ? AND ?")
                params.extend(status)
            elif isinstance(status, int):
                clauses.append("status_code = ?")
                params.append(status)

        mime = filters.get("mime_type")
        if mime:
            clauses.append("mime_type LIKE ?")
            params.append(f"%{mime}%")

        ext = filters.get("extension")
        if ext:
            clauses.append("extension = ?")
            params.append(ext)

        has_params = filters.get("has_params")
        if has_params is not None:
            clauses.append("has_params = ?")
            params.append(1 if has_params else 0)

        is_websocket = filters.get("is_websocket")
        if is_websocket is not None:
            clauses.append("is_websocket = ?")
            params.append(1 if is_websocket else 0)

        if not clauses:
            return "", []
        return "WHERE " + " AND ".join(clauses), params
