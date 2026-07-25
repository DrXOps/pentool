"""TargetAPI — публичный интерфейс Target/SiteMap для TUI и CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pentool.core.logging import get_logger
from pentool.modules.target import SiteMap, SiteNode

if TYPE_CHECKING:
    from pentool.utils.parser import ParsedRequest

logger = get_logger(__name__)

__all__ = ["TargetAPI", "SiteNode", "SiteMap"]


class TargetAPI:

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._sitemap = SiteMap(db_path=db_path)

    @property
    def sitemap(self) -> SiteMap:
        """Прямой доступ к объекту SiteMap."""
        return self._sitemap

    async def load(self) -> None:
        await self._sitemap.load()

    async def save(self) -> None:
        await self._sitemap.save()

    def add_request(self, req: "ParsedRequest") -> None:
        self._sitemap.add_request(req)

    async def get_tree(self) -> dict[str, list[SiteNode]]:
        return self._sitemap.get_tree()

    def get_hosts(self) -> list[str]:
        return self._sitemap.get_hosts()

    def get_paths(self, host: str) -> list[SiteNode]:
        return self._sitemap.get_paths(host)

    async def set_in_scope(self, host: str, in_scope: bool) -> None:
        """Задать scope-флаг для хоста.

        Args:
            host: Имя хоста.
            in_scope: True — хост в scope, False — вне scope.
        """
        self._sitemap.set_in_scope(host, in_scope)

    async def get_scope(self) -> list[str]:
        return self._sitemap.get_scope()

    async def clear(self) -> None:
        self._sitemap.clear()

    async def export_json(self, path: str) -> None:
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
                    loaded += 1
                except Exception as exc:
                    logger.warning("TargetAPI.import_project_data: skip node: %s", exc)
        return loaded
