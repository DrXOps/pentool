"""RepeaterService — orchestrates HTTP request sending + history → EventBus."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from pentool.api.repeater_api import RepeaterAPI
from pentool.core.event_bus import EventBus
from pentool.core.logging import get_logger
from pentool.services.base_service import BaseService
from pentool.utils.parser import ParsedRequest, ParsedResponse, parse_http_request

logger = get_logger(__name__)


class RepeaterService(BaseService):

    def __init__(
        self,
        repeater_api: RepeaterAPI | None = None,
        event_bus: EventBus | None = None,
        tui_loop: asyncio.AbstractEventLoop | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(event_bus=event_bus, tui_loop=tui_loop, on_log=on_log)
        self._repeater_api = repeater_api

    async def send_request(
        self,
        raw_request: str,
        tab_name: str = "Tab",
        follow_redirects: bool = True,
    ) -> tuple[ParsedResponse | None, int, str | None]:
        # Parse request
        try:
            req: ParsedRequest = parse_http_request(raw_request)
        except ValueError as exc:
            logger.error("RepeaterService: parse error: %s", exc)
            return None, 0, f"Parse error: {exc}"

        logger.info(
            "RepeaterService: sending %s %s (follow_redirects=%s)",
            req.method,
            req.url,
            follow_redirects
        )

        t0 = time.monotonic()
        try:
            # Single route through the API layer (Этап 4.3): if no RepeaterAPI
            # was injected, spin up our own (no history saved — same behaviour
            # as the old direct HTTPClient fallback). This removes the second,
            # duplicated HTTP path in the service.
            if self._repeater_api is None:
                from pentool.core.config import get_config
                cfg = get_config()
                self._repeater_api = RepeaterAPI(
                    db_path=cfg.db_path,
                    timeout=cfg.request_timeout,
                    verify_ssl=cfg.verify_ssl,
                )
                resp = await self._repeater_api.send(req, tab_name=tab_name, save=False)
            else:
                resp = await self._repeater_api.send(req, tab_name=tab_name)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "RepeaterService: response %d (%d bytes, %dms)",
                resp.status,
                len(resp.body) if resp.body else 0,
                elapsed_ms
            )
            return resp, elapsed_ms, None

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error("RepeaterService: request failed: %s", exc)
            return None, elapsed_ms, str(exc)

    async def close(self) -> None:
        # No standalone HTTP client anymore (Этап 4.3) — the API layer owns it.
        pass

    # _emit and _log inherited from BaseService
