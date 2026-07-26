"""String encoding, decoding, and hashing."""

from __future__ import annotations

import base64
import hashlib
import html
import urllib.parse
from typing import Callable


def url_encode(text: str) -> str:
    """URL-encode a string (all characters except letters/digits/'-._~')."""
    return urllib.parse.quote(text, safe="")


def url_decode(text: str) -> str:
    """URL-decode a string."""
    return urllib.parse.unquote(text)


def url_encode_all(text: str) -> str:
    """URL-encode a string, encoding spaces as %20."""
    return urllib.parse.quote(text, safe="")


def url_decode_plus(text: str) -> str:
    """URL-decode a string, treating '+' as a space."""
    return urllib.parse.unquote_plus(text)


def base64_encode(text: str) -> str:
    """Encode a string to standard Base64."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def base64_decode(text: str) -> str:
    """Decode a string from standard Base64.

    Raises:
        ValueError: If the string is not valid Base64.
    """
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.b64decode(padded).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid base64: {exc}") from exc


def base64url_encode(text: str) -> str:
    """Encode a string to URL-safe Base64 (without padding)."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def base64url_decode(text: str) -> str:
    """Decode a string from URL-safe Base64.

    Raises:
        ValueError: If the string is not valid Base64url.
    """
    try:
        padded = text + "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid base64url: {exc}") from exc


def html_encode(text: str) -> str:
    """HTML-encode a string (replace special characters with HTML entities)."""
    return html.escape(text, quote=True)


def html_decode(text: str) -> str:
    """HTML-decode a string (replace HTML entities with characters)."""
    return html.unescape(text)


def hex_encode(text: str) -> str:
    """Encode a string to the hex representation of its UTF-8 bytes."""
    return text.encode("utf-8").hex()


def hex_decode(text: str) -> str:
    """Decode a hex string back to text.

    Raises:
        ValueError: If the string is not valid hex.
    """
    try:
        clean = text.replace(" ", "").replace("\\x", "").replace("0x", "")
        return bytes.fromhex(clean).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Invalid hex: {exc}") from exc


def unicode_escape(text: str) -> str:
    """Encode a string to Unicode escape (\\uXXXX for non-ASCII characters)."""
    result = []
    for ch in text:
        code = ord(ch)
        if code > 127:
            result.append(f"\\u{code:04x}")
        else:
            result.append(ch)
    return "".join(result)


def unicode_unescape(text: str) -> str:
    """Decode a string from Unicode escape."""
    try:
        return text.encode("utf-8").decode("unicode_escape")
    except Exception:
        import codecs
        try:
            return codecs.decode(text, "unicode_escape")
        except Exception as exc:
            raise ValueError(f"Invalid unicode escape: {exc}") from exc


def md5(text: str) -> str:
    """Compute the MD5 hash of a string (hex digest)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha1(text: str) -> str:
    """Compute the SHA1 hash of a string (hex digest)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def sha256(text: str) -> str:
    """Compute the SHA256 hash of a string (hex digest)."""
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
    """Apply a named operation to text.

    Args:
        operation: Operation name from OPERATIONS.
        text: Input string.

    Returns:
        Result of the operation.

    Raises:
        ValueError: If the operation is unknown.
    """
    func = OPERATIONS.get(operation)
    if func is None:
        raise ValueError(f"Unknown operation: {operation!r}. Available: {list(OPERATIONS)}")
    return func(text)
