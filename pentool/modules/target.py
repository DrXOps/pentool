"""Target / SiteMap — target tree from proxy traffic."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pentool.core.logging import get_logger
from pentool.storage.base_sqlite_storage import BaseSqliteStorage

if TYPE_CHECKING:
    from pentool.utils.parser import ParsedRequest

logger = get_logger(__name__)


@dataclass
class SiteNode:
    """Tree node: host + path."""

    host: str
    path: str                       # "/" for root, "/api/users" for endpoint
    methods: set[str] = field(default_factory=set)
    request_count: int = 0
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    in_scope: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "host": self.host,
            "path": self.path,
            "methods": list(self.methods),
            "request_count": self.request_count,
            "last_seen": self.last_seen.isoformat(),
            "in_scope": self.in_scope,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SiteNode":
        ts = d.get("last_seen", "")
        try:
            ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            host=d["host"],
            path=d["path"],
            methods=set(d.get("methods", [])),
            request_count=d.get("request_count", 0),
            last_seen=ts,
            in_scope=bool(d.get("in_scope", False)),
        )


class SiteMap(BaseSqliteStorage):
    """Target tree, automatically populated from proxy traffic.

    Connection lifecycle: inherits `BaseSqliteStorage` (see
    pentool/storage/base_sqlite_storage.py). `save()`/`load()` open ONE
    persistent aiosqlite connection lazily on first use (`ensure_open()`)
    and reuse it for the object's lifetime instead of opening/closing a
    fresh connection via `core.db_schema.get_db()` on every call — the same
    consolidation already applied to HttpStorage and IntruderStorage.
    Like those, `ensure_open()` returns False (safe no-op) when `db_path`
    is falsy.
    """

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path=db_path)
    # host -> path -> SiteNode
        self._nodes: dict[str, dict[str, SiteNode]] = {}
        # Scope is tracked independently of _nodes (normalized, port-stripped
        # host names) so that adding a host to scope from Proxy works even
        # if Target hasn't seen any traffic for it yet (or saw it under a
        # host:port key that doesn't match the port-less host the user/Proxy
        # refers to). Previously set_in_scope() was a no-op unless the exact
        # host string already existed as a node — a host added to scope
        # before any matching traffic arrived (or under a different
        # host:port key) silently never got flagged, with no error raised.
        self._scope_hosts: set[str] = set()

    async def init_db(self, path: str) -> None:
        """Open/create the connection and ensure the `site_map` table exists."""
        # BaseSqliteStorage._connect() opens self._db and applies the shared
        # PRAGMAs (WAL/busy_timeout) common to every storage class. Schema is
        # applied on the SAME persistent connection (not a second get_db()),
        # reusing the shared DDL from core.db_schema so `site_map` and its
        # unique index stay defined in one place. All statements are
        # idempotent (CREATE TABLE/INDEX IF NOT EXISTS), so this is safe to
        # run against an already-initialized project DB.
        await self._connect(path)
        from pentool.core.db_schema import _SCHEMA
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    @staticmethod
    def _norm_host(host: str) -> str:
        """Normalize a host for scope comparisons: lowercase, no port."""
        return host.split(":")[0].strip().lower()

    @staticmethod
    def _strip_default_port(host: str) -> str:
        """Return ``host`` with a DEFAULT http/https port stripped (host:443 → host).

        Non-standard ports (e.g. :8443) are kept — they are distinct endpoints.
        """
        try:
            if ":" in host:
                bare, _, port = host.rpartition(":")
                if port in ("80", "443"):
                    return bare
        except Exception:
            pass
        return host

    def add_request(self, req: "ParsedRequest", count: bool = True) -> None:
        """Add a discovered URL to the tree.

        Args:
            req: parsed request to register (host + path).
            count: when True (default), a re-addition of an existing path bumps
                its request_count by one. Pass count=False for "discovery" sources
                (spider crawl, AI-suggested endpoints) so re-crawling the same
                target does NOT inflate the node counter — that counter should
                track real HTTP requests, not how many times the crawler re-found
                an already-known page. Real proxy traffic always uses count=True.
        """
        try:
            parsed = urlparse(req.url)
            host = parsed.netloc or parsed.hostname or req.url
            path = parsed.path or "/"
            if not path:
                path = "/"
        except Exception:
            return

        now = datetime.now(timezone.utc)
        # Merge the browser-CONNECT host ("host:443") and a seed host ("host")
        # into ONE tree node, but only strip the DEFAULT ports (80/443) — a
        # non-standard port (e.g. :8443) is a genuinely separate endpoint and
        # must stay its own host.
        host_key = self._strip_default_port(host)
        host_map = self._nodes.setdefault(host_key, {})
        in_scope = self._norm_host(host_key) in self._scope_hosts

        if path in host_map:
            node = host_map[path]
            node.methods.add(req.method)
            if count:
                node.request_count += 1
            node.last_seen = now
        else:
            host_map[path] = SiteNode(
                host=host_key,
                path=path,
                methods={req.method},
                request_count=1,
                last_seen=now,
                in_scope=in_scope,
            )

    def get_tree(self) -> dict[str, list[SiteNode]]:
        return {
            host: sorted(paths.values(), key=lambda n: n.path)
            for host, paths in self._nodes.items()
        }

    def get_hosts(self) -> list[str]:
        return sorted(self._nodes.keys())

    def get_paths(self, host: str) -> list[SiteNode]:
        return sorted(self._nodes.get(host, {}).values(), key=lambda n: n.path)

    def get_scope(self) -> list[str]:
        # Union of hosts flagged via nodes (legacy/DB-loaded state) and hosts
        # registered in _scope_hosts before any matching node existed.
        node_hosts = {h for h, paths in self._nodes.items() if any(n.in_scope for n in paths.values())}
        explicit_hosts = {h for h in self._nodes if self._norm_host(h) in self._scope_hosts}
        return sorted(node_hosts | explicit_hosts)

    def get_request_count(self, host: str) -> int:
        return sum(n.request_count for n in self._nodes.get(host, {}).values())

    def set_in_scope(self, host: str, in_scope: bool) -> None:
        """Include/exclude a host from Scope.

        Tracks the (normalized, port-stripped) host in `_scope_hosts`
        independently of whether a matching node already exists in
        `_nodes` — a host added to scope before any traffic for it has
        been seen (or seen under a different host:port key) is still
        remembered and will be applied to any node for that host,
        present now or added later via add_request().
        """
        norm = self._norm_host(host)
        if in_scope:
            self._scope_hosts.add(norm)
        else:
            self._scope_hosts.discard(norm)
        for h, paths in self._nodes.items():
            if self._norm_host(h) == norm:
                for node in paths.values():
                    node.in_scope = in_scope

    def is_in_scope(self, host: str) -> bool:
        if self._norm_host(host) in self._scope_hosts:
            return True
        paths = self._nodes.get(host, {})
        return any(n.in_scope for n in paths.values())

    async def save(self) -> None:
        try:
            if not await self.ensure_open():
                return
            db = self._db
            for host, paths in self._nodes.items():
                for path, node in paths.items():
                    await db.execute(
                        """
                        INSERT INTO site_map (id, host, path, methods, request_count, last_seen, in_scope)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(host, path) DO UPDATE SET
                            methods = excluded.methods,
                            request_count = excluded.request_count,
                            last_seen = excluded.last_seen,
                            in_scope = excluded.in_scope
                        """,
                        (
                            node.id,
                            node.host,
                            node.path,
                            json.dumps(list(node.methods)),
                            node.request_count,
                            node.last_seen.isoformat(),
                            1 if node.in_scope else 0,
                        ),
                    )
            await db.commit()
        except Exception as exc:
            logger.error("SiteMap.save error: %s", exc)

    async def load(self) -> None:
        try:
            if not await self.ensure_open():
                return
            db = self._db
            async with db.execute("SELECT * FROM site_map") as cur:
                rows = await cur.fetchall()
            self._nodes.clear()
            for row in rows:
                node = SiteNode(
                    id=row["id"],
                    host=row["host"],
                    path=row["path"],
                    methods=set(json.loads(row["methods"] or "[]")),
                    request_count=row["request_count"],
                    last_seen=datetime.fromisoformat(row["last_seen"]),
                    in_scope=bool(row["in_scope"]),
                )
                self._nodes.setdefault(node.host, {})[node.path] = node
                if node.in_scope:
                    self._scope_hosts.add(self._norm_host(node.host))
        except Exception as exc:
            logger.error("SiteMap.load error: %s", exc)

    def clear(self) -> None:
        self._nodes.clear()
        self._scope_hosts.clear()

    def export_json(self) -> dict:
        return {
            host: [n.to_dict() for n in nodes]
            for host, nodes in self.get_tree().items()
        }
