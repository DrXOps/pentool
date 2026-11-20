"""Auto-Scope: автоматически добавлять хост в Scope + TechDetect.

Используется из контекстных меню (RequestContextMenuMixin) и при --real старте.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from pentool.core.config import get_config

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)  # диагностика — убедись что логи видны

# Textual worker group for fire-and-forget tech detection. Every task lives in
# this group, so `WorkerManager.cancel_group` can stop them on app shutdown
# (F-014: previously `asyncio.create_task` left them with no handle and no
# cancellation path).
TECH_DETECT_WORKER_GROUP = "tech-detect"


def _spawn_tech_detect(host: str, app) -> None:
    """Start tech detection as a Textual worker instead of a bare asyncio task.

    `App` is a `MessagePump`, so ``run_worker`` is available and is thread-safe
    (it bounces to the app thread via ``call_from_thread`` when needed).
    ``exit_on_error=False`` keeps a failing fingerprint from killing the app;
    the exception is logged by the worker itself.
    """
    try:
        app.run_worker(
            _tech_detect_and_cache(host, app),
            group=TECH_DETECT_WORKER_GROUP,
            exclusive=False,
            exit_on_error=False,
        )
    except Exception:
        # Воркер не завёлся — техдетект хоста не запустится вовсе, и в дереве
        # у него не будет строки Tech. `run_worker` может упасть по разным
        # причинам (приложение уже закрывается, группа занята), поэтому
        # трейсбек.
        log.exception("tech_detect: worker spawn failed for %s", host)


def _get_sitemap(app):
    """Get the SiteMap via TargetScreen._get_api().sitemap.

    app.sitemap does NOT exist — SiteMap lives inside TargetScreen's
    TargetAPI. This helper queries the screen and returns the sitemap,
    or None if the screen isn't mounted yet.
    """
    try:
        from pentool.tui.screens.target.screen import TargetScreen

        target = app.require_module_screen("target", TargetScreen)
        api = target._get_api()
        if api is not None:
            return api.sitemap
        log.warning("_get_sitemap: TargetAPI is None")
    except Exception as exc:
        log.warning("_get_sitemap: query_one failed: %s", exc)
    return None


def _get_proxy(app):
    """Get the ProxyClient from app._proxy."""
    try:
        return getattr(app, "_proxy", None)
    except Exception:
        return None


def _extract_host(raw: str) -> str | None:
    """Extract hostname from a raw HTTP request or URL string."""
    raw = raw.strip()
    if raw.startswith(("GET ", "POST ", "PUT ", "DELETE ", "PATCH ", "HEAD ")):
        # Raw HTTP request — extract Host header or URL from first line
        lines = raw.splitlines()
        if lines:
            parts = lines[0].split()
            if len(parts) >= 2:
                path = parts[1]
                if path.startswith("http"):
                    parsed = urlparse(path)
                    return parsed.netloc or parsed.hostname
                # Relative path — look for Host header
                for line in lines[1:]:
                    if line.lower().startswith("host:"):
                        return line.split(":", 1)[1].strip()
    # Plain URL
    if raw.startswith("http"):
        parsed = urlparse(raw)
        return parsed.netloc or parsed.hostname
    return None


def _strip_default_port(host: str) -> str:
    """Strip default ports (80/443) from a host string."""
    if ":" in host:
        hostname, port = host.rsplit(":", 1)
        if port in ("80", "443"):
            return hostname
    return host


def _force_scope_host(host: str, app) -> None:
    """Add host to Scope unconditionally (bypasses auto_scope config), syncs into ProxyServer.scope."""
    if not host:
        return
    norm_host = _strip_default_port(host)

    # 1. SiteMap — через TargetScreen._get_api().sitemap (app.sitemap НЕ СУЩЕСТВУЕТ)
    sitemap_ok = False
    try:
        sitemap = _get_sitemap(app)
        if sitemap is not None:
            sitemap.set_in_scope(norm_host, True)
            sitemap_ok = True
            log.info("FORCE_SCOPE: added %s to sitemap scope", norm_host)
        else:
            log.warning("FORCE_SCOPE: sitemap is None (TargetScreen not ready?)")
    except Exception as exc:
        log.warning("FORCE_SCOPE: sitemap set_in_scope error: %s", exc)

    # 2. Sync into ProxyServer.scope
    try:
        proxy = _get_proxy(app)
        if proxy is not None:
            scope = list(proxy.scope)
            if norm_host not in scope:
                scope.append(norm_host)
                proxy.set_scope(scope)
                log.info("FORCE_SCOPE: synced %s to proxy.scope", norm_host)
        else:
            log.warning("FORCE_SCOPE: proxy is None")
    except Exception as exc:
        log.warning("FORCE_SCOPE: proxy sync error: %s", exc)

    # 3. Trigger async TechDetect (только если SiteMap жива)
    if sitemap_ok:
        _spawn_tech_detect(norm_host, app)
    else:
        log.warning("FORCE_SCOPE: skipped TechDetect — sitemap not available")


def _maybe_auto_scope_host(host: str, app) -> None:
    """Add *host* to Scope if auto_scope is enabled in config.

    Also triggers async TechDetect if the host isn't already cached.
    """
    if not host:
        return
    cfg = get_config()
    if not getattr(cfg, "auto_scope", False):
        return

    norm_host = _strip_default_port(host)
    sitemap_ok = False
    try:
        sitemap = _get_sitemap(app)
        if sitemap is not None:
            sitemap.set_in_scope(norm_host, True)
            sitemap_ok = True
            log.info("AUTO_SCOPE: added %s to sitemap scope", norm_host)
    except Exception as exc:
        log.debug("AUTO_SCOPE: set_in_scope error: %s", exc)
        return

    # Sync into ProxyServer.scope
    try:
        proxy = _get_proxy(app)
        if proxy is not None:
            scope = list(proxy.scope)
            if norm_host not in scope:
                scope.append(norm_host)
                proxy.set_scope(scope)
                log.info("AUTO_SCOPE: synced %s to proxy.scope", norm_host)
    except Exception as exc:
        log.debug("AUTO_SCOPE: proxy sync error: %s", exc)

    # Trigger async TechDetect
    if sitemap_ok:
        _spawn_tech_detect(norm_host, app)


def _maybe_auto_scope_request(raw: str, app) -> None:
    """Extract host from raw request and add to scope if enabled."""
    host = _extract_host(raw)
    if host:
        _maybe_auto_scope_host(host, app)


async def _tech_detect_and_cache(host: str, app) -> None:
    """Run TechFingerprinter on a host, cache result, update Target tree.

    Uses Lightpanda to fetch the page, then TechFingerprinter to detect
    technologies. Results are cached in TechCache so repeat scans skip it.
    """
    # 1. Check cache через services слой (не прямой импорт PRO)
    from pentool.services.tech_detector import get_tech_cache

    cached = get_tech_cache(host)
    if cached is not None:
        log.info("TECH_DETECT: %s — from cache", host)
        await _update_target_tree_tech(host, cached, app)
        return

    # 2. Run fingerprint — через services слой (не прямой импорт PRO)
    from pentool.services.tech_detector import cache_tech_profile, fingerprint_from_html, run_fingerprint
    from pentool.utils.http_client import get_shared_http_client
    from pentool.utils.lightpanda import is_lightpanda_available, lightpanda_fetch_html

    url = f"https://{host}/" if "://" not in host else host

    profile = await run_fingerprint(url, get_shared_http_client(follow_redirects=True))

    # 3. Fallback: fetch the page with Lightpanda and run the local heuristics.
    if profile is None and is_lightpanda_available():
        try:
            html = await lightpanda_fetch_html(url, timeout=15.0)
            profile = await fingerprint_from_html(url, html or "")
        except Exception as exc:
            log.debug("TECH_DETECT: lightpanda fallback error for %s: %s", host, exc)

    if profile is None:
        log.info("TECH_DETECT: %s — no profile (skipped)", host)
        return

    # 4. Кэширование: TechProfile теперь содержит все поля напрямую
    profile_dict = profile.to_context_dict() if hasattr(profile, "to_context_dict") else profile
    cache_tech_profile(host, profile_dict)
    log.info("TECH_DETECT: %s — cached: %s", host, profile_dict)
    await _update_target_tree_tech(host, profile_dict, app)


async def _update_target_tree_tech(host: str, profile: dict, app) -> None:
    """Update Target tree with technology info under the host node."""
    try:
        # Lazy screens: Target is usually not mounted while tech detection runs in
        # the background, and `query_one` would then raise for every host. The
        # tree is rebuilt from the DB when the screen is mounted, so a missing
        # screen is a quiet no-op rather than an error.
        screen = app.module_screen("target")  # type: ignore[attr-defined]
        if screen is not None and hasattr(screen, "_update_tech_node"):
            screen._update_tech_node(host, profile)  # type: ignore[attr-defined]
    except Exception as exc:
        log.debug("TECH_DETECT: _update_target_tree_tech error: %s", exc)
