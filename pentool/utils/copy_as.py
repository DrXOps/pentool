"""Utilities for generating external tool commands from an HTTP request."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

from pentool.core.logging import get_logger

logger = get_logger(__name__)
from pathlib import Path

from pentool.utils.parser import ParsedRequest


def copy_as_curl(req: ParsedRequest) -> str:
    """Generate a curl command with -X, -H, -d, --proxy flags."""
    parts = ["curl", "-i", "-s", "-k"]

    if req.method != "GET":
        parts += ["-X", req.method]

    for name, value in req.headers.items():
        if name.lower() in ("content-length", "connection", "transfer-encoding"):
            continue
        parts += ["-H", f"{name}: {value}"]

    if req.body:
        body_str = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")
        parts += ["--data-raw", body_str]

    parts.append(req.url)
    return " ".join(shlex.quote(p) for p in parts)


def copy_as_ffuf(req: ParsedRequest) -> str:
    """Generate an ffuf command for URL fuzzing."""
    url = req.url
    # If FUZZ is not yet in the URL — append it to the last segment
    if "FUZZ" not in url:
        url = url.rstrip("/") + "/FUZZ"

    parts = ["ffuf", "-u", url, "-w", "wordlist.txt:FUZZ"]

    for name, value in req.headers.items():
        if name.lower() in ("content-length", "connection"):
            continue
        parts += ["-H", f"{name}: {value}"]

    if req.method != "GET":
        parts += ["-X", req.method]

    if req.body:
        body_str = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")
        parts += ["-d", body_str]

    return " ".join(shlex.quote(p) for p in parts)


def copy_as_sqlmap(req: ParsedRequest, request_file: str = "request.txt") -> str:
    """Generate a sqlmap -r request.txt command."""
    parts = ["sqlmap", "-r", request_file, "--batch"]

    # If parameters are present — add -p for explicit specification
    body_str = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")
    if body_str and any(c in body_str for c in ("=", "&")):
        parts += ["--data", body_str]

    # Detect dbms from response headers if possible
    parts += ["--dbs"]

    return " ".join(shlex.quote(p) for p in parts)


def copy_as_nmap(req: ParsedRequest) -> str:
    """Generate an nmap -sV -p PORT HOST command."""
    from urllib.parse import urlparse
    parsed = urlparse(req.url)
    host = parsed.hostname or "TARGET"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    parts = ["nmap", "-sV", "-sC", "-p", str(port), host]
    return " ".join(shlex.quote(p) for p in parts)


def copy_as_jwt_tool(req: ParsedRequest) -> str:
    """If a JWT is found in the headers — generate a jwt_tool command."""
    jwt_token: str | None = None

    # Look for JWT in Authorization: Bearer ...
    auth = req.headers.get("Authorization", req.headers.get("authorization", ""))
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        # Check JWT format (three base64 parts separated by dots)
        if re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$', token):
            jwt_token = token

    # Look for JWT in Cookie
    if jwt_token is None:
        cookie_hdr = req.headers.get("Cookie", req.headers.get("cookie", ""))
        for part in cookie_hdr.split(";"):
            part = part.strip()
            if "=" in part:
                _, val = part.split("=", 1)
                val = val.strip()
                if re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$', val):
                    jwt_token = val
                    break

    if jwt_token is None:
        return f"# No JWT found in request headers\n# jwt_tool <token> -t {req.url}"

    parts = ["jwt_tool", jwt_token, "-t", req.url]
    return " ".join(shlex.quote(p) for p in parts)


def save_request_txt(req: ParsedRequest, path: str) -> None:
    """Save a raw HTTP request to a file for external tools (sqlmap, etc.)."""
    from urllib.parse import urlparse
    parsed = urlparse(req.url)
    path_qs = parsed.path
    if parsed.query:
        path_qs += "?" + parsed.query

    http_ver = getattr(req, "http_version", "HTTP/1.1") or "HTTP/1.1"
    lines = [f"{req.method} {path_qs} {http_ver}"]
    for name, value in req.headers.items():
        lines.append(f"{name}: {value}")
    lines.append("")

    if req.body:
        body_str = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")
        lines.append(body_str)

    Path(path).write_text("\r\n".join(lines), encoding="utf-8")


def copy_as_fetch(req: ParsedRequest) -> str:
    """Generate a JavaScript fetch() call for the DevTools Console."""
    import json as _json

    headers_dict = {
        k: v for k, v in req.headers.items()
        if k.lower() not in ("content-length", "connection", "transfer-encoding", "host")
    }

    body_str: str | None = None
    if req.body:
        body_str = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")

    opts: dict = {"method": req.method}
    if headers_dict:
        opts["headers"] = headers_dict
    if body_str:
        opts["body"] = body_str

    opts_json = _json.dumps(opts, indent=2, ensure_ascii=False)
    return f"fetch({_json.dumps(req.url)}, {opts_json});"


def open_in_browser(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def extract_url_from_raw(raw: str) -> str:
    """Extract a URL from a raw HTTP request (first line + Host header)."""
    if not raw:
        return ""
    lines = raw.replace("\r\n", "\n").split("\n")
    first = lines[0].strip()
    parts = first.split(" ", 2)
    if len(parts) < 2:
        return ""
    method_or_url = parts[0]
    path = parts[1] if len(parts) >= 2 else "/"

    # If the first line is already a URL (not an HTTP method)
    if method_or_url.lower().startswith("http"):
        return method_or_url

    # Look for Host header
    host = ""
    scheme = "https"
    for line in lines[1:]:
        if not line.strip():
            break
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip()
        if "x-forwarded-proto: http" in line.lower():
            scheme = "http"

    if not host:
        return path

    # Determine scheme from port
    if host.endswith(":80"):
        scheme = "http"
    elif host.endswith(":443"):
        scheme = "https"
        host = host[:-4]

    return f"{scheme}://{host}{path}"


def _find_executable(name: str) -> str | None:
    """Find executable by name, checking PATH and common paths."""
    path = shutil.which(name)
    if path:
        return path
    # fallback: common non-PATH locations
    common = ["/usr/bin", "/usr/local/bin", "/tmp/xclip/usr/bin"]
    for d in common:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _x11_display_ok() -> bool:
    """Проверить, что X11 DISPLAY доступен (xclip/xsel/GTK без него не работают)."""
    return bool(os.environ.get("DISPLAY"))


def copy_to_clipboard(text: str) -> bool:
    """Copy to clipboard via (tkinter → xclip/xsel → GTK → wl-copy → pyperclip)."""

    if not text:
        logger.debug("copy_to_clipboard: empty text, skipping")
        return False

    # tkinter — работает везде где есть Tk (без внешних бинарников)
    try:
        import tkinter as _tk
        r = _tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.destroy()
        logger.debug("copy_to_clipboard: tkinter OK")
        return True
    except Exception as exc:
        logger.debug("copy_to_clipboard: tkinter error: %s", exc)

    have_display = _x11_display_ok()
    logger.debug("copy_to_clipboard: DISPLAY=%s", have_display)

    if have_display:
        # xclip (оптимально — самый быстрый)
        path = _find_executable("xclip")
        if path:
            try:
                result = subprocess.run(
                    [path, "-selection", "clipboard"],
                    input=text.encode(), timeout=2, capture_output=True,
                )
                if result.returncode == 0:
                    logger.debug("copy_to_clipboard: xclip OK")
                    return True
                logger.debug("copy_to_clipboard: xclip rc=%s stderr=%s",
                             result.returncode, result.stderr.decode(errors="replace").strip())
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                logger.debug("copy_to_clipboard: xclip error: %s", exc)

        # xsel (fallback на X11)
        path = _find_executable("xsel")
        if path:
            try:
                result = subprocess.run(
                    [path, "--clipboard", "--input"],
                    input=text.encode(), timeout=2, capture_output=True,
                )
                if result.returncode == 0:
                    logger.debug("copy_to_clipboard: xsel OK")
                    return True
                logger.debug("copy_to_clipboard: xsel rc=%s stderr=%s",
                             result.returncode, result.stderr.decode(errors="replace").strip())
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                logger.debug("copy_to_clipboard: xsel error: %s", exc)

        # GTK clipboard (работает на X11 без xclip/xsel)
        try:
            gtk_script = (
                "import gi; gi.require_version('Gtk','3.0'); "
                "from gi.repository import Gtk,Gdk; "
                "cb=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD); "
                f"cb.set_text({text!r},-1); cb.store()"
            )
            result = subprocess.run(
                ["python3", "-c", gtk_script],
                timeout=3, capture_output=True,
            )
            if result.returncode == 0:
                logger.debug("copy_to_clipboard: GTK OK")
                return True
            logger.debug("copy_to_clipboard: GTK rc=%s stderr=%s",
                         result.returncode, result.stderr.decode(errors="replace").strip())
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("copy_to_clipboard: GTK error: %s", exc)

    # wl-copy (Wayland — не требует DISPLAY)
    path = _find_executable("wl-copy")
    if path:
        try:
            result = subprocess.run(
                [path], input=text.encode(), timeout=2, capture_output=True,
            )
            if result.returncode == 0:
                logger.debug("copy_to_clipboard: wl-copy OK")
                return True
            logger.debug("copy_to_clipboard: wl-copy rc=%s stderr=%s",
                         result.returncode, result.stderr.decode(errors="replace").strip())
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("copy_to_clipboard: wl-copy error: %s", exc)

    # pyperclip — универсальный fallback

    # pyperclip — универсальный fallback, покрывает macOS, Windows, и headless
    # через собственные механизмы (xclip/xsel/wl-copy сам выбирает).
    # Пробуем его в самом конце, потому что он может тянуть тяжелые импорты.
    try:
        import pyperclip  # type: ignore[import]
        pyperclip.copy(text)
        logger.debug("copy_to_clipboard: pyperclip OK")
        return True
    except Exception as exc:
        logger.debug("copy_to_clipboard: pyperclip error: %s", exc)

    logger.debug("copy_to_clipboard: ALL backends failed")
    return False


def paste_from_clipboard() -> str | None:
    """Read from clipboard via (tkinter → xclip/xsel → GTK → wl-paste → pyperclip)."""

    # tkinter — работает без внешних бинарников
    try:
        import tkinter as _tk
        r = _tk.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        if text and text.strip():
            logger.debug("paste_from_clipboard: tkinter OK")
            return text
    except Exception as exc:
        logger.debug("paste_from_clipboard: tkinter error: %s", exc)

    have_display = _x11_display_ok()
    logger.debug("paste_from_clipboard: DISPLAY=%s", have_display)

    if have_display:
        # xclip
        path = _find_executable("xclip")
        if path:
            try:
                result = subprocess.run(
                    [path, "-selection", "clipboard", "-o"],
                    timeout=2, capture_output=True,
                )
                if result.returncode == 0:
                    logger.debug("paste_from_clipboard: xclip OK")
                    return result.stdout.decode("utf-8", errors="replace")
                logger.debug("paste_from_clipboard: xclip rc=%s stderr=%s",
                             result.returncode, result.stderr.decode(errors="replace").strip())
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                logger.debug("paste_from_clipboard: xclip error: %s", exc)

        # xsel
        path = _find_executable("xsel")
        if path:
            try:
                result = subprocess.run(
                    [path, "--clipboard", "--output"],
                    timeout=2, capture_output=True,
                )
                if result.returncode == 0:
                    logger.debug("paste_from_clipboard: xsel OK")
                    return result.stdout.decode("utf-8", errors="replace")
                logger.debug("paste_from_clipboard: xsel rc=%s stderr=%s",
                             result.returncode, result.stderr.decode(errors="replace").strip())
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                logger.debug("paste_from_clipboard: xsel error: %s", exc)

        # GTK clipboard read
        try:
            gtk_script = (
                "import gi; gi.require_version('Gtk','3.0'); "
                "from gi.repository import Gtk,Gdk; "
                "cb=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD); "
                "txt=cb.wait_for_text(); "
                "print(txt or '')"
            )
            result = subprocess.run(
                ["python3", "-c", gtk_script],
                timeout=3, capture_output=True,
            )
            if result.returncode == 0:
                text = result.stdout.decode("utf-8", errors="replace").strip()
                if text:
                    logger.debug("paste_from_clipboard: GTK OK")
                    return text
                logger.debug("paste_from_clipboard: GTK returned empty")
            else:
                logger.debug("paste_from_clipboard: GTK rc=%s", result.returncode)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("paste_from_clipboard: GTK error: %s", exc)

    # wl-paste (Wayland)
    path = _find_executable("wl-paste")
    if path:
        try:
            result = subprocess.run([path], timeout=2, capture_output=True)
            if result.returncode == 0:
                logger.debug("paste_from_clipboard: wl-paste OK")
                return result.stdout.decode("utf-8", errors="replace")
            logger.debug("paste_from_clipboard: wl-paste rc=%s stderr=%s",
                         result.returncode, result.stderr.decode(errors="replace").strip())
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("paste_from_clipboard: wl-paste error: %s", exc)

    # pyperclip fallback
    try:
        import pyperclip  # type: ignore[import]
        text = pyperclip.paste()
        if text and text.strip():
            logger.debug("paste_from_clipboard: pyperclip OK")
            return text
        logger.debug("paste_from_clipboard: pyperclip returned empty")
    except Exception as exc:
        logger.debug("paste_from_clipboard: pyperclip error: %s", exc)

    logger.debug("paste_from_clipboard: ALL backends failed")
    return None
