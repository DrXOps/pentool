"""ProxyService — orchestrates ProxyServer + HttpStorage → EventBus."""

from __future__ import annotations

import asyncio
from typing import Callable

from pentool.api.proxy_api import InterceptedRequest, ProxyAPI
from pentool.core.event_bus import EventBus
from pentool.core.logging import get_logger
from pentool.services.base_service import BaseService
from pentool.storage.http_storage import HttpStorage

logger = get_logger(__name__)


class ProxyService(BaseService):

    def __init__(
        self,
        proxy_api: ProxyAPI,
        db_path: str,
        event_bus: EventBus | None = None,
        tui_loop: asyncio.AbstractEventLoop | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(event_bus=event_bus, tui_loop=tui_loop, on_log=on_log)
        self._proxy_api = proxy_api
        self._db_path = db_path
        self._storage = HttpStorage()
        self._storage_ready = False
        self._pre_storage_queue: list[InterceptedRequest] = []
        self._pre_storage_queue_max = 2000

    async def init_storage(self) -> None:
        try:
            await self._storage.init_db(self._db_path)
            self._storage_ready = True
            logger.info("ProxyService: storage ready at %s", self._db_path)

            # Process requests that arrived before storage was ready
            if self._pre_storage_queue:
                logger.info(
                    "ProxyService: flushing %d pre-storage requests",
                    len(self._pre_storage_queue)
                )
                for queued_req in self._pre_storage_queue:
                    await self.store_request(queued_req)
                self._pre_storage_queue.clear()
        except Exception as exc:
            logger.error("ProxyService: storage init failed: %s", exc)

    async def store_request(self, req: InterceptedRequest) -> int | None:
        if not self._storage_ready:
            # Bound the pre-storage queue — if DB init hangs/never completes,
            # this list must not grow unbounded (memory leak).
            if len(self._pre_storage_queue) >= self._pre_storage_queue_max:
                dropped = self._pre_storage_queue.pop(0)
                logger.error(
                    "ProxyService: pre_storage_queue full (%d), dropping oldest "
                    "queued request id=%s to bound memory",
                    self._pre_storage_queue_max, getattr(dropped, "id", "?"),
                )
            self._pre_storage_queue.append(req)
            return None

        try:
            parsed = req.to_parsed_request()
            row_id = await self._storage.add_request(
                parsed,
                req.response,
                is_websocket=req.is_websocket,
            )
            logger.debug("ProxyService: store_request saved row_id=%d req.id=%s", row_id, req.id)
            return row_id
        except Exception as exc:
            # This used to be a silent "logger.warning" — from the user's
            # perspective the request simply vanished from HTTP History with
            # no trace. Log at error level (with traceback) and retry once,
            # since most failures here are transient (e.g. DB busy/locked).
            logger.error(
                "ProxyService: store_request failed for req.id=%s, retrying once: %s",
                req.id, exc, exc_info=True,
            )
            try:
                parsed = req.to_parsed_request()
                row_id = await self._storage.add_request(
                    parsed,
                    req.response,
                    is_websocket=req.is_websocket,
                )
                logger.info("ProxyService: store_request retry succeeded, row_id=%d req.id=%s", row_id, req.id)
                return row_id
            except Exception as exc2:
                logger.error(
                    "ProxyService: store_request retry failed for req.id=%s — request LOST from history: %s",
                    req.id, exc2, exc_info=True,
                )
                return None

    def _effective_filters(self, filters: dict | None) -> dict:
        """Resolve scope_only/is_websocket defaults shared by get_history/count."""
        effective_filters = dict(filters) if filters else {}
        if effective_filters.pop("scope_only", False):
            proxy = self._proxy_api.get_proxy()
            scope_hosts = proxy.scope if proxy else []
            if scope_hosts:
                effective_filters["hosts"] = scope_hosts
        # HTTP History shows only non-WebSocket requests by default
        if "is_websocket" not in effective_filters:
            effective_filters["is_websocket"] = False
        return effective_filters

    async def get_history(
        self,
        offset: int = 0,
        limit: int = 1000,
        filters: dict | None = None,
    ) -> list[dict]:
        if not self._storage_ready:
            return []

        try:
            effective_filters = self._effective_filters(filters)
            rows = await self._storage.get_metadata_batch(
                offset=offset,
                limit=limit,
                filters=effective_filters if effective_filters else None,
            )
            return rows
        except Exception as exc:
            logger.warning("ProxyService: get_history failed: %s", exc)
            return []

    async def count_history(self, filters: dict | None = None) -> int:
        """Total rows matching filters (for 'showing N of M' UI + scroll-load)."""
        if not self._storage_ready:
            return 0
        try:
            effective_filters = self._effective_filters(filters)
            return await self._storage.count(effective_filters if effective_filters else None)
        except Exception as exc:
            logger.warning("ProxyService: count_history failed: %s", exc)
            return 0

    async def get_request_by_id(self, request_id: int) -> dict | None:
        if not self._storage_ready:
            return None

        try:
            return await self._storage.get_request_by_id(request_id)
        except Exception as exc:
            logger.warning("ProxyService: get_request_by_id(%d) failed: %s", request_id, exc)
            return None

    async def get_full_entry(self, row_id: int) -> dict | None:
        if not self._storage_ready:
            return None

        try:
            return await self._storage.get_full_entry(row_id)
        except Exception as exc:
            logger.warning("ProxyService: get_full_entry(%d) failed: %s", row_id, exc)
            return None

    async def delete_request(self, row_id: int) -> None:
        if not self._storage_ready:
            return

        try:
            await self._storage.delete(row_id)
            logger.info("ProxyService: deleted request %d", row_id)
        except Exception as exc:
            logger.warning("ProxyService: delete_request(%d) failed: %s", row_id, exc)

    async def update_response(self, row_id: int, response: object) -> None:
        if not self._storage_ready:
            return

        try:
            await self._storage.update_response(row_id, response)
            logger.debug("ProxyService: updated response for %d", row_id)
        except Exception as exc:
            logger.warning("ProxyService: update_response(%d) failed: %s", row_id, exc)

    async def switch_db(self, new_db_path: str) -> None:
        try:
            logger.info("ProxyService: switch_db called for %s", new_db_path)
            await self._storage.switch_db(new_db_path)
            self._db_path = new_db_path
            self._storage_ready = True
            logger.info("ProxyService: switched to %s, storage_ready=%s", new_db_path, self._storage_ready)
        except Exception as exc:
            logger.error("ProxyService: switch_db failed: %s", exc)
            self._storage_ready = False

    async def clear_history(self) -> None:
        if not self._storage_ready:
            return

        try:
            await self._storage.clear_all()
            logger.info("ProxyService: history cleared")
        except Exception as exc:
            logger.warning("ProxyService: clear_history failed: %s", exc)

    def is_storage_ready(self) -> bool:
        return self._storage_ready

    async def reload_from_proxy(self, proxy_api: "ProxyAPI") -> None:
        """Synchronize storage from the in-memory proxy (for history clear/reset scenarios)."""
        if not self._storage_ready:
            return
        proxy = proxy_api.get_proxy() if proxy_api else None
        await self._storage.clear_all()
        if proxy is not None:
            for req in proxy.get_requests(limit=100_000):
                parsed = req.to_parsed_request()
                await self._storage.add_request(
                    parsed, req.response,
                    is_websocket=getattr(req, "is_websocket", False),
                )

    # _emit and _log inherited from BaseService
