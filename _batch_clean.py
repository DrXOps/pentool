import os

reps = []

reps.append(("core/plugin_manager.py:BasePlugin",
    '/home/docx/pentool/pentool/core/plugin_manager.py',
    'class BasePlugin:\n    """Base for all pentool plugins (both FREE builtins and PRO).\n\n    Each plugin module defines a subclass of BasePlugin with a `register()`\n    function that returns an instance — PluginManager.load_plugins() calls\n    register() and assembles the metadata from the returned object\'s fields.\n    Anything set on the instance (screens, scanners, checks) is picked up by\n    the app\'s screen registry / scanner engine / passive-check runner.\n\n    register() is called exactly once per module (cached), so `register()`\n    can safely do non-trivial work (import, instantiate) without the risk of\n    repeated imports from multiple callers.\n    """',
    'class BasePlugin:\n    """Base for pentool plugins. register() called once per module."""'))

reps.append(("app.py:_auto_save",
    '/home/docx/pentool/pentool/tui/app.py',
    'def _auto_save(self) -> None:\n        """Auto-save current project every N seconds (default 1 min).\n\n        The first auto-save also runs as soon as the user has typed something\n        (keyboard activity), cutting the initial wait down from 60s to ~0s.\n        After that, it falls back to the timer.\n        """',
    'def _auto_save(self) -> None:\n        """Auto-save every N min (fires on first input, then timer)."""'))

reps.append(("app.py:_on_bus_proxy_captured",
    '/home/docx/pentool/pentool/tui/app.py',
    'def _on_bus_proxy_captured(self, msg: ProxyRequestCaptured) -> None:\n        """EventBus: proxy captured a request -> add to ProxyScreen and optionally Intercept tab.\n\n        Exists outside ProxyScreen (not an @on handler there) because\n        EventBus subscribers are mixin/(widget)-level, and screen-level\n        @on(...) handlers on a mixin are silently skipped: Textual only\n        introspects the direct App class for `@on(...)` handlers and would\n        silently skip a mixin MRO handler, breaking live history rows.\n        """',
    'def _on_bus_proxy_captured(self, msg: ProxyRequestCaptured) -> None:\n        """Route captured request to ProxyScreen (App-level @on avoids mixin MRO skip)."""'))

reps.append(("proxy_runtime.py:_start_proxy_daemon",
    '/home/docx/pentool/pentool/tui/mixins/proxy_runtime.py',
    'def _start_proxy_daemon(self) -> None:\n        """Start the isolated daemon-backed proxy (ProxyClient facade).\n\n        start() is synchronous here (spawns+connects, then pushes the startup\n        intercept/scope prefs). Event emission back into the TUI is handled by\n        the client\'s background reader re-emitting into the EventBus, so the\n        UI update calls below are identical to the in-memory path.\n        """',
    'def _start_proxy_daemon(self) -> None:\n        """Start daemon proxy (synchronous, events re-emitted to EventBus)."""'))

reps.append(("proxy_runtime.py:_stop_proxy_async",
    '/home/docx/pentool/pentool/tui/mixins/proxy_runtime.py',
    'async def _stop_proxy_async(self) -> None:\n        """Async proxy stop (the TUI\'s own event loop can await it directly).\n\n        The daemon engine sends a stop command over the control socket and\n        waits for the subprocess to exit. The memory engine sends a stop\n        command to the proxy loop\'s CommandQueue. Both are async and can be\n        awaited by run_worker/call_from_thread/call_after_refresh.\n        """',
    'async def _stop_proxy_async(self) -> None:\n        """Async proxy stop (socket cmd for daemon, CommandQueue for memory engine)."""'))

reps.append(("app.py:_do_real_fetch_sync",
    '/home/docx/pentool/pentool/tui/app.py',
    'def _do_real_fetch_sync(self) -> None:\n        """Run REAL fetch asynchronously for auto-save synchronization.\n\n        Auto-save runs on a loop and needs to synchronously wait for the fetch\n        to complete before proceeding. This ran in the event loop thread before\n        and blocked the entire TUI for the duration of the request (which\n        includes the request time, processing time, and any retries). Moved to\n        a fire-and-forget worker so the auto-save timer doesn\'t block the UI.\n        """',
    'def _do_real_fetch_sync(self) -> None:\n        """Fire-and-forget REAL fetch worker (unblocks auto-save timer)."""'))

bad = 0
ok = 0
for label, fpath, old, new in reps:
    try:
        with open(fpath, 'r') as f:
            text = f.read()
        if old in text:
            text = text.replace(old, new)
            with open(fpath, 'w') as f:
                f.write(text)
            ok += 1
            print(f"OK: {label}")
        else:
            bad += 1
            print(f"FAIL: {label}")
    except Exception as e:
        bad += 1
        print(f"ERROR {label}: {e}")
print(f"\nDone: {ok} ok, {bad} failed")