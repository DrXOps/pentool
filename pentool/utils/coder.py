"""Кодирование, декодирование и хэширование строк."""

from __future__ import annotations

import base64
import hashlib
import html
import urllib.parse
from typing import Callable


def url_encode(text: str) -> str:
    """URL-кодировать строку (все символы, кроме букв/цифр/'-._~')."""
    return urllib.parse.quote(text, safe="")


def url_decode(text: str) -> str:
    """URL-декодировать строку."""
    return urllib.parse.unquote(text)


def url_encode_all(text: str) -> str:
    """URL-кодировать строку, включая пробелы как %20."""
    return urllib.parse.quote(text, safe="")


def url_decode_plus(text: str) -> str:
    """URL-декодировать строку, обрабатывая '+' как пробел."""
    return urllib.parse.unquote_plus(text)


def base64_encode(text: str) -> str:
    """Закодировать строку в стандартный Base64."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def base64_decode(text: str) -> str:
    """Декодировать строку из стандартного Base64.

    Raises:
        ValueError: Если строка не является корректным Base64.
    """
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.b64decode(padded).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid base64: {exc}") from exc


def base64url_encode(text: str) -> str:
    """Закодировать строку в URL-safe Base64 (без паддинга)."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def base64url_decode(text: str) -> str:
    """Декодировать строку из URL-safe Base64.

    Raises:
        ValueError: Если строка не является корректным Base64url.
    """
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid base64url: {exc}") from exc


def html_encode(text: str) -> str:
    """HTML-кодировать строку (заменить спецсимволы на HTML-сущности)."""
    return html.escape(text, quote=True)


def html_decode(text: str) -> str:
    """HTML-декодировать строку (заменить HTML-сущности на символы)."""
    return html.unescape(text)


def hex_encode(text: str) -> str:
    """Закодировать строку в hex-представление байт (UTF-8)."""
    return text.encode("utf-8").hex()


def hex_decode(text: str) -> str:
    """Декодировать hex-строку обратно в текст.

    Raises:
        ValueError: Если строка не является корректным hex.
    """
    try:
        clean = text.replace(" ", "").replace("\\x", "").replace("0x", "")
        return bytes.fromhex(clean).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid hex: {exc}") from exc


def unicode_escape(text: str) -> str:
    """Закодировать строку в Unicode escape (\\uXXXX для не-ASCII)."""
    result = []
    for ch in text:
        code = ord(ch)
        if code > 127:
            result.append(f"\\u{code:04x}")
        else:
            result.append(ch)
    return "".join(result)


def unicode_unescape(text: str) -> str:
    """Декодировать строку из Unicode escape."""
    try:
        return text.encode("utf-8").decode("unicode_escape")
    except Exception:
        import codecs
        try:
            return codecs.decode(text, "unicode_escape")
        except Exception as exc:
            raise ValueError(f"Invalid unicode escape: {exc}") from exc


def md5(text: str) -> str:
    """Вычислить MD5-хэш строки (hex-дайджест)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha1(text: str) -> str:
    """Вычислить SHA1-хэш строки (hex-дайджест)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def sha256(text: str) -> str:
    """Вычислить SHA256-хэш строки (hex-дайджест)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


OPERATIONS: dict[str, Callable[[str], str]] = {
    "url_encode": url_encode,
    "url_decode": url_decode,
    "base64_encode": base64_encode,
    "base64_decode": base64_decode,
    "base64url_encode": base64url_encode,
    "base64url_decode": base64url_decode,
    "html_encode": html_encode,
    "html_decode": html_decode,
    "hex_encode": hex_encode,
    "hex_decode": hex_decode,
    "unicode_escape": unicode_escape,
    "unicode_unescape": unicode_unescape,
    "md5": md5,
    "sha1": sha1,
    "sha256": sha256,
}


def apply_operation(operation: str, text: str) -> str:
    """Применить именованную операцию к тексту.

    Args:
        operation: Имя операции из OPERATIONS.
        text: Входная строка.

    Returns:
        Результат операции.

    Raises:
        ValueError: Если операция неизвестна.
    """
    func = OPERATIONS.get(operation)
    if func is None:
        raise ValueError(f"Unknown operation: {operation!r}. Available: {list(OPERATIONS)}")
    return func(text)
