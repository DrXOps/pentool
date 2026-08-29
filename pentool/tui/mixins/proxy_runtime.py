"""ProxyRuntimeMixin — Proxy start/stop runtime for the App.

Extracted from PentoolApp (Этап 5.1, proxy-runtime domain) so the app class
stays thin and the start/stop/toggle path is tested in one place.

The mixin expects its host (the App) to expose:
    _proxy            — ProxyServer instance (or None)
    _proxy_thread     — threading.Thread | None
    _proxy_loop       — asyncio.AbstractEventLoop | None
    _project_loaded   — bool (project DB switch finished)
    _cfg              — Config (for cert_dir etc.)
    notify()          — from NotificationsMixin
    run_worker(), call_after_refresh(), call_from_thread()
    _update_status(), _update_proxy_screen_labels(), _update_dashboard_proxy_status()
"""

from __future__ import annotations

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)


class ProxyRuntimeMixin:
    """Mix-in for starting/stopping the proxy in a background thread."""

    def action_toggle_proxy(self) -> None:
        if self._proxy is None:  # type: ignore[attr-defined]
            return
        if self._proxy.is_running:  # type: ignore[attr-defined]
            # Stop asynchronously so the TUI thread isn't frozen for up to
            # ~10s while proxy.stop() + thread join complete (the Stop button
            # currently felt slow/unresponsive on a busy proxy).
            self.run_worker(self._stop_proxy_async())  # type: ignore[attr-defined]
        else:
            if not self._project_loaded:  # type: ignore[attr-defined]
                # Project DB switch/open (auto-open at startup, New/Open
                # Project) is still finishing in the background — starting
                # the proxy now would race HttpStorage.switch_db() (its
                # connection may be mid-close/reopen) and silently lose or
                # fail to persist the first captured requests. _project_loaded
                # is set as soon as the DB switch itself completes (see
                # ProjectManager._do_switch) — the other screens may still be
                # reloading, but that's independent of Proxy.
                self.notify(  # type: ignore[attr-defined]
                    "Project is still opening — wait a couple of seconds before starting Proxy",
                    severity="warning",
                    timeout=4,
                )
                return
            self._start_proxy()

    def _start_proxy(self) -> None:
        if self._proxy is None or self._proxy.is_running:  # type: ignore[attr-defined]
            return
        logger.info("APP: _start_proxy: starting proxy on %s:%d", self._proxy.host, self._proxy.port)
        # Sprint 3: callbacks removed — proxy emits via EventBus,
        # app subscribes to ProxyRequestCaptured / ProxyRequestCompleted in on_mount

        def _run_proxy_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._proxy_loop = loop  # type: ignore[attr-defined]
            try:
                loop.run_until_complete(self._proxy_main())  # type: ignore[attr-defined]
            finally:
                loop.close()
                self._proxy_loop = None  # type: ignore[attr-defined]

        self._proxy_thread = threading.Thread(  # type: ignore[attr-defined]
            target=_run_proxy_loop, daemon=True, name="proxy"
        )
        self._proxy_thread.start()  # type: ignore[attr-defined]

    async def _proxy_main(self) -> None:
        """Proxy entry point — runs in a separate event loop."""
        try:
            await self._proxy.start()  # type: ignore[attr-defined]
            self.call_from_thread(self._update_status)  # type: ignore[attr-defined]
            self.call_from_thread(self._update_proxy_screen_labels)  # type: ignore[attr-defined]
            self.call_from_thread(self._update_dashboard_proxy_status, True)  # type: ignore[attr-defined]
            self.call_from_thread(  # type: ignore[attr-defined]
                self.notify, f"● Proxy :{self._proxy.port}", severity="success"  # type: ignore[attr-defined]
            )
            logger.info("Proxy started on port %s", self._proxy.port)
            async with self._proxy._server:  # type: ignore[attr-defined]
                await self._proxy._server.serve_forever()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error("Proxy error: %s", exc)
            # Surface this to the user — previously only logged, so a
            # "port already in use" / "another process holds this file"
            # failure looked like the proxy silently did nothing when the
            # toolbar button was pressed, with no clue why.
            msg = str(exc) or type(exc).__name__
            self.call_from_thread(  # type: ignore[attr-defined]
                self.notify,  # type: ignore[attr-defined]
                f"Proxy failed to start: {msg}",
                severity="error",
                timeout=6,
            )
        finally:
            self.call_from_thread(self._update_status)  # type: ignore[attr-defined]
            self.call_from_thread(self._update_proxy_screen_labels)  # type: ignore[attr-defined]
            self.call_from_thread(self._update_dashboard_proxy_status, False)  # type: ignore[attr-defined]

    def _stop_proxy(self) -> None:
        logger.info("APP: _stop_proxy called")
        if self._proxy and self._proxy.is_running and self._proxy_loop:  # type: ignore[attr-defined]
            future = asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop  # type: ignore[attr-defined]
            )
            try:
                # stop() itself now cancels tasks within a short grace
                # (see _STOP_TASK_GRACE), so a short timeout here is enough —
                # and on a normal quit the leftover connections are released
                # by the process exit, so we never need the old 6s headroom.
                future.result(timeout=1.5)
            except Exception as e:
                logger.warning("APP: proxy.stop() error or timeout: %s", e)
                # Force-cancel anything still running in the proxy loop so
                # the thread can exit even if stop() itself timed out
                if self._proxy_loop and not self._proxy_loop.is_closed():  # type: ignore[attr-defined]
                    try:
                        def _cancel_all():
                            for t in asyncio.all_tasks(self._proxy_loop):  # type: ignore[attr-defined]
                                t.cancel()
                        self._proxy_loop.call_soon_threadsafe(_cancel_all)  # type: ignore[attr-defined]
                    except Exception:
                        pass
        if self._proxy_thread and self._proxy_thread.is_alive():  # type: ignore[attr-defined]
            self._proxy_thread.join(timeout=1.5)  # type: ignore[attr-defined]
            if self._proxy_thread.is_alive():  # type: ignore[attr-defined]
                logger.warning("APP: proxy thread did not stop in 1.5s — port 8080 may still be in use")
        self.call_after_refresh(self._update_status)  # type: ignore[attr-defined]
        self.call_after_refresh(self._update_proxy_screen_labels)  # type: ignore[attr-defined]
        self.call_after_refresh(  # type: ignore[attr-defined]
            self.notify, "○ Proxy stopped", severity="warning"  # type: ignore[attr-defined]
        )

    async def _stop_proxy_async(self) -> None:
        """Async stop of the proxy that does NOT block the TUI thread.

        Same robust path as `_stop_proxy()` (await proxy.stop() up to 6s,
        force-cancel tasks on timeout, join the proxy thread) but expressed
        as a coroutine. Intended to be awaited from an async worker context
        (e.g. ProjectManager._do_switch) so that switching to a new project
        does NOT freeze the UI for up to ~10s while the old proxy is being
        wound down. _stop_proxy() remains the synchronous variant used by
        the Stop button / Ctrl+Q.
        """
        logger.info("APP: _stop_proxy_async called")
        if self._proxy and self._proxy.is_running and self._proxy_loop:  # type: ignore[attr-defined]
            future = asyncio.run_coroutine_threadsafe(
                self._proxy.stop(), self._proxy_loop  # type: ignore[attr-defined]
            )
            try:
                await asyncio.wait_for(asyncio.wrap_future(future), timeout=1.5)
            except asyncio.TimeoutError:
                logger.warning("APP: proxy.stop() (async) timed out")
        # Wait (in this async context) for the proxy thread to die so the
        # 8080 port is released before the caller switches the project DB.
        # Short bounded window — beyond it the port is released by the
        # (soon-exiting) process, so we never block the caller for ~7s.
        loop = asyncio.get_running_loop()
        proxy_thread = self._proxy_thread  # type: ignore[attr-defined]
        if proxy_thread is not None:
            for _ in range(20):  # up to ~2s in 100ms steps
                alive = await loop.run_in_executor(None, proxy_thread.is_alive)
                if not alive:
                    break
                await asyncio.sleep(0.1)
            self.call_after_refresh(self._update_status)  # type: ignore[attr-defined]
            self.call_after_refresh(self._update_proxy_screen_labels)  # type: ignore[attr-defined]
            self.call_after_refresh(  # type: ignore[attr-defined]
                self.notify, "○ Proxy stopped", severity="warning"  # type: ignore[attr-defined]
            )
        else:
            self.call_after_refresh(self._update_status)  # type: ignore[attr-defined]
