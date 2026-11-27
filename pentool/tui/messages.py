"""Messages (Message Bus) for cross-screen communication without direct imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.message import Message

from pentool.utils.parser import ParsedRequest

if TYPE_CHECKING:
    # Type-only: `proxy_api` is the proxy façade, and importing it here would pull the API
    # layer into the module every screen imports. Annotations are strings thanks to
    # `from __future__ import annotations`, so runtime stays clean.
    from pentool.api.proxy_api import InterceptedRequest  # noqa: F401 - used in annotations


class SendToRepeater(Message):
    def __init__(self, raw: str) -> None:
        super().__init__()
        self.raw = raw


class SendToIntruder(Message):
    def __init__(self, raw: str) -> None:
        super().__init__()
        self.raw = raw


class SendToTarget(Message):
    def __init__(self, req: ParsedRequest) -> None:
        super().__init__()
        self.req = req


class SyncScopeToTarget(Message):
    """Synchronize in-scope status of a host with TargetScreen."""

    def __init__(self, host: str, in_scope: bool) -> None:
        super().__init__()
        self.host = host
        self.in_scope = in_scope


class SyncScopeToProxy(Message):
    """Sync host scope from TargetScreen to ProxyServer (fixes one-way sync bug)."""

    def __init__(self, host: str, in_scope: bool) -> None:
        super().__init__()
        self.host = host
        self.in_scope = in_scope


class SendHostToScanner(Message):
    def __init__(self, host: str) -> None:
        super().__init__()
        self.host = host


class ProxyRequestAdded(Message):
    """Proxy received a new request — add a row to the ProxyScreen table."""

    def __init__(self, req: InterceptedRequest) -> None:
        super().__init__()
        self.req = req


class ProxyRequestDone(Message):
    """Proxy completed a request — update the row in the ProxyScreen table."""

    def __init__(self, req: InterceptedRequest) -> None:
        super().__init__()
        self.req = req


class ProxyLoadProject(Message):
    """Reload the ProxyScreen table from storage after loading a project."""


class SendToScanner(Message):
    def __init__(self, urls: str) -> None:
        super().__init__()
        self.urls = urls  # newline-separated


class SendRequestToScanner(Message):
    def __init__(self, request: ParsedRequest | None) -> None:
        super().__init__()
        self.request = request


class SendUrlToTarget(Message):
    def __init__(self, req: ParsedRequest) -> None:
        super().__init__()
        self.req = req


class ConfigChanged(Message):
    """Configuration changed — notify all subscribers (R-16).

    The `fields` attribute contains a dict of changed fields: {'proxy_port': 8081, ...}.
    The app layer listens to this message and applies changes to ProxyServer/StatusBar.
    """

    def __init__(self, fields: dict) -> None:
        super().__init__()
        self.fields = fields


class ModuleSelected(Message):
    """User selected a module from the navigation widget."""

    def __init__(self, module_id: str) -> None:
        super().__init__()
        self.module_id = module_id
