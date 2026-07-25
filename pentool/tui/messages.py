"""Сообщения (Message Bus) для межэкранного взаимодействия без прямых импортов."""

from __future__ import annotations

from textual.message import Message


class SendToRepeater(Message):

    def __init__(self, raw: str) -> None:
        super().__init__()
        self.raw = raw


class SendToIntruder(Message):

    def __init__(self, raw: str) -> None:
        super().__init__()
        self.raw = raw


class SendToTarget(Message):

    def __init__(self, req: object) -> None:
        super().__init__()
        self.req = req


class SyncScopeToTarget(Message):
    """Синхронизировать in-scope статус хоста с TargetScreen."""

    def __init__(self, host: str, in_scope: bool) -> None:
        super().__init__()
        self.host = host
        self.in_scope = in_scope


class SendHostToScanner(Message):

    def __init__(self, host: str) -> None:
        super().__init__()
        self.host = host


class ProxyRequestAdded(Message):
    """Прокси получил новый запрос — добавить строку в таблицу ProxyScreen."""

    def __init__(self, req: object) -> None:
        super().__init__()
        self.req = req


class ProxyRequestDone(Message):
    """Прокси завершил запрос — обновить строку в таблице ProxyScreen."""

    def __init__(self, req: object) -> None:
        super().__init__()
        self.req = req


class ProxyClearHistory(Message):
    pass


class ProxyLoadProject(Message):
    """Перезагрузить таблицу ProxyScreen из хранилища после загрузки проекта."""


class SendToScanner(Message):

    def __init__(self, urls: str) -> None:
        super().__init__()
        self.urls = urls  # newline-separated


class SendRequestToScanner(Message):

    def __init__(self, request: object) -> None:
        super().__init__()
        self.request = request


class SendUrlToTarget(Message):

    def __init__(self, req: object) -> None:
        super().__init__()
        self.req = req


class TerminalStop(Message):
    pass


class ConfigChanged(Message):
    """Конфигурация изменена — уведомить всех подписчиков (R-16).

    Атрибут `fields` содержит словарь изменённых полей: {'proxy_port': 8081, ...}.
    App-слой слушает это сообщение и применяет изменения к ProxyServer/StatusBar.
    """

    def __init__(self, fields: dict) -> None:
        super().__init__()
        self.fields = fields
