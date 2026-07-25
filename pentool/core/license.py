"""Система лицензирования Pentool."""

from __future__ import annotations

import hashlib
import json
import platform
import time
import uuid
from dataclasses import dataclass, field

from pathlib import Path


_LICENSE_FILE = Path.home() / ".pentool" / "license.dat"
_GRACE_PERIOD_DAYS = 7


@dataclass
class LicenseInfo:
    """Информация о текущей лицензии."""

    valid: bool = False
    plan: str = "free"                      # "free" | "pro" | "enterprise"
    features: list[str] = field(default_factory=list)
    expires: str | None = None           # ISO date или None (permanent)
    machine_id: str = ""
    license_key: str = ""
    last_check: float | None = None      # timestamp последней онлайн-проверки
    error: str = ""                         # сообщение об ошибке если not valid

    def has_feature(self, feature: str) -> bool:
        return self.valid and feature in self.features

    def is_pro(self) -> bool:
        return self.valid and self.plan in ("pro", "enterprise")

    @property
    def status_text(self) -> str:
        if not self.valid:
            return "FREE"
        return self.plan.upper()

    @property
    def expires_text(self) -> str:
        if not self.expires:
            return "Lifetime"
        return self.expires


def get_machine_id() -> str:
    try:
        import socket
        hostname = socket.gethostname()
        # Получить MAC первого интерфейса через uuid
        mac = hex(uuid.getnode())[2:]
        raw = f"{hostname}:{mac}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


def _load_cached() -> dict | None:
    try:
        if _LICENSE_FILE.exists():
            data = json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return None


def _save_cached(data: dict) -> None:
    try:
        _LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LICENSE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_license() -> LicenseInfo:
    cached = _load_cached()
    if cached is None:
        return LicenseInfo(valid=False, plan="free", machine_id=get_machine_id())

    last_check = cached.get("last_check", 0)
    grace_seconds = _GRACE_PERIOD_DAYS * 24 * 3600
    if (time.time() - last_check) > grace_seconds:
        # Grace period истёк — деактивируем
        return LicenseInfo(
            valid=False,
            plan="free",
            machine_id=get_machine_id(),
            license_key=cached.get("license_key", ""),
            error=f"Grace period expired. Please reconnect to validate license.",
        )

    return LicenseInfo(
        valid=cached.get("valid", False),
        plan=cached.get("plan", "free"),
        features=cached.get("features", []),
        expires=cached.get("expires"),
        machine_id=cached.get("machine_id", get_machine_id()),
        license_key=cached.get("license_key", ""),
        last_check=last_check,
    )


# Session-level license cache (avoids repeated file reads per check)
_session_license: "LicenseInfo | None" = None


def get_session_license() -> "LicenseInfo":
    """Return cached session license (refreshed once per process)."""
    global _session_license
    if _session_license is None:
        _session_license = get_license()
    return _session_license


def invalidate_session_license() -> None:
    """Force re-read on next get_session_license() call."""
    global _session_license
    _session_license = None


class FeatureNotAvailable(Exception):
    """Feature not available in the current plan."""
    def __init__(self, feature: str, plan_required: str = "pro"):
        self.feature = feature
        self.plan_required = plan_required
        super().__init__(
            f"Feature '{feature}' requires {plan_required.upper()} plan. "
            f"Upgrade at https://pentool.pro/upgrade"
        )


def require_feature(feature: str, plan_required: str = "pro"):
    """Decorator: raise FeatureNotAvailable if feature is not licensed."""
    def decorator(func):
        import functools
        import asyncio as _asyncio

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not get_session_license().has_feature(feature):
                raise FeatureNotAvailable(feature, plan_required)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not get_session_license().has_feature(feature):
                raise FeatureNotAvailable(feature, plan_required)
            return func(*args, **kwargs)

        if _asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


async def activate_license(key: str) -> LicenseInfo:
    """Активировать лицензию онлайн (license.pentool.pro/api/validate).

    Returns:
        LicenseInfo с результатом активации.
    """
    key = key.strip().upper()
    machine_id = get_machine_id()

    if not key:
        return LicenseInfo(
            valid=False, plan="free",
            machine_id=machine_id,
            error="License key is empty",
        )

    # Попытка реальной онлайн-проверки
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.post(
                "https://license.pentool.pro/api/validate",
                json={"key": key, "machine_id": machine_id},
                ssl=False,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    info = LicenseInfo(
                        valid=data.get("valid", False),
                        plan=data.get("plan", "free"),
                        features=data.get("features", []),
                        expires=data.get("expires"),
                        machine_id=machine_id,
                        license_key=key,
                        last_check=time.time(),
                    )
                    if info.valid:
                        _save_cached({
                            "valid": True,
                            "plan": info.plan,
                            "features": info.features,
                            "expires": info.expires,
                            "machine_id": machine_id,
                            "license_key": key,
                            "last_check": time.time(),
                        })
                    return info
    except Exception:
        pass  # Сервер недоступен — fallback к локальной проверке

    # Оффлайн-fallback: проверяем формат ключа
    # Формат: XXXX-XXXX-XXXX-XXXX (16 hex символов через дефисы)
    import re
    if re.match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', key):
        if key.startswith("DEMO"):
            info = LicenseInfo(
                valid=True,
                plan="pro",
                features=["scanner_pro", "reports_pro", "payloads_pro"],
                expires=None,
                machine_id=machine_id,
                license_key=key,
                last_check=time.time(),
            )
            _save_cached({
                "valid": True,
                "plan": "pro",
                "features": ["scanner_pro", "reports_pro", "payloads_pro"],
                "expires": None,
                "machine_id": machine_id,
                "license_key": key,
                "last_check": time.time(),
            })
            return info

    return LicenseInfo(
        valid=False,
        plan="free",
        machine_id=machine_id,
        license_key=key,
        error="License server unavailable. Key format invalid or not activated.",
    )


def deactivate_license() -> None:
    """Деактивировать лицензию (удалить кэш)."""
    try:
        if _LICENSE_FILE.exists():
            _LICENSE_FILE.unlink()
    except Exception:
        pass


# Глобальный кэш лицензии для текущей сессии
_session_license: LicenseInfo | None = None


def get_session_license() -> LicenseInfo:
    global _session_license
    if _session_license is None:
        _session_license = get_license()
    return _session_license


def refresh_session_license(info: LicenseInfo | None = None) -> LicenseInfo:
    global _session_license
    _session_license = info or get_license()
    return _session_license
