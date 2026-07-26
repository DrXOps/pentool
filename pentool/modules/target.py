"""Target / SiteMap — target tree from proxy traffic."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pentool.core.database import get_db, init_db
from pentool.core.logging import get_logger

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


class SiteMap:
    """Target tree, automatically populated from proxy traffic."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
    # host -> path -> SiteNode
        self._nodes: dict[str, dict[str, SiteNode]] = {}

    def add_request(self, req: "ParsedRequest") -> None:
        try:
            parsed = urlparse(req.url)
            host = parsed.netloc or parsed.hostname or req.url
            path = parsed.path or "/"
            if not path:
                path = "/"
        except Exception:
            return

        now = datetime.now(timezone.utc)
        host_map = self._nodes.setdefault(host, {})

        if path in host_map:
            node = host_map[path]
            node.methods.add(req.method)
            node.request_count += 1
            node.last_seen = now
        else:
            host_map[path] = SiteNode(
                host=host,
                path=path,
                methods={req.method},
                request_count=1,
                last_seen=now,
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
        return [h for h, paths in self._nodes.items() if any(n.in_scope for n in paths.values())]

    def get_request_count(self, host: str) -> int:
        return sum(n.request_count for n in self._nodes.get(host, {}).values())

    def set_in_scope(self, host: str, in_scope: bool) -> None:
        """Include/exclude a host from Scope."""
        if host in self._nodes:
            for node in self._nodes[host].values():
                node.in_scope = in_scope

    def is_in_scope(self, host: str) -> bool:
        paths = self._nodes.get(host, {})
        return any(n.in_scope for n in paths.values())

    async def save(self) -> None:
        try:
            if self._db_path:
                await init_db(self._db_path)
            async with get_db(self._db_path) as db:
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
            if self._db_path:
                await init_db(self._db_path)
            async with get_db(self._db_path) as db:
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
        except Exception as exc:
            logger.error("SiteMap.load error: %s", exc)

    def clear(self) -> None:
        self._nodes.clear()

    def export_json(self) -> dict:
        return {
            host: [n.to_dict() for n in nodes]
            for host, nodes in self.get_tree().items()
        }
