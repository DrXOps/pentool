"""TargetAPI — public Target/SiteMap interface for TUI and CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pentool.core.logging import get_logger
from pentool.modules.target import SiteMap, SiteNode

if TYPE_CHECKING:
    from pentool.utils.parser import ParsedRequest

from pentool.api.base_api import ExportableAPI

logger = get_logger(__name__)

__all__ = ["TargetAPI", "SiteNode", "SiteMap"]


class TargetAPI(ExportableAPI):

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._sitemap = SiteMap(db_path=db_path)

    @property
    def sitemap(self) -> SiteMap:
        """Direct access to the SiteMap object."""
        return self._sitemap

    async def load(self) -> None:
        await self._sitemap.load()

    async def save(self) -> None:
        await self._sitemap.save()

    async def close(self) -> None:
        """Close the persistent SiteMap SQLite connection (on quit / project switch)."""
        await self._sitemap.close()

    def add_request(self, req: "ParsedRequest", count: bool = True) -> None:
        self._sitemap.add_request(req, count=count)

    def get_tree(self) -> dict[str, list[SiteNode]]:
        return self._sitemap.get_tree()

    def get_hosts(self) -> list[str]:
        return self._sitemap.get_hosts()

    def get_paths(self, host: str) -> list[SiteNode]:
        return self._sitemap.get_paths(host)

    def set_in_scope(self, host: str, in_scope: bool) -> None:
        """Set the scope flag for a host.

        Args:
            host: Host name.
            in_scope: True — host is in scope, False — out of scope.
        """
        self._sitemap.set_in_scope(host, in_scope)

    def get_scope(self) -> list[str]:
        return self._sitemap.get_scope()

    def clear(self) -> None:
        self._sitemap.clear()

    def export_json(self, path: str) -> None:
        data = self._sitemap.export_json()
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("SiteMap exported to %s", path)

    # ── Project persistence ────────────────────────────────────────────────────

    def export_project_data(self) -> dict:
        return {"sitemap": self._sitemap.export_json()}

    def import_project_data(self, data: dict) -> int:
        from pentool.modules.target import SiteNode
        sitemap_data = data.get("sitemap", {})
        self._sitemap.clear()
        loaded = 0
        for host, nodes in sitemap_data.items():
            for node_dict in nodes:
                try:
                    node = SiteNode.from_dict(node_dict)
                    self._sitemap._nodes.setdefault(host, {})[node.path] = node
                    if node.in_scope:
                        self._sitemap._scope_hosts.add(self._sitemap._norm_host(host))
                    loaded += 1
                except Exception as exc:
                    logger.warning("TargetAPI.import_project_data: skip node: %s", exc)
        return loaded
