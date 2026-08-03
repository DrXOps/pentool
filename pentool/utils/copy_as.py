"""Utilities for generating external tool commands from an HTTP request."""

from __future__ import annotations

import re
import shlex
import subprocess
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


def copy_to_clipboard(text: str) -> bool:
    """Copy to clipboard via xclip/xsel/wl-copy/GTK/pyperclip. Returns success."""
    for cmd in [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["wl-copy"],
    ]:
        try:
            result = subprocess.run(cmd, input=text.encode(), timeout=2, capture_output=True)
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # GTK clipboard (works on X11 without xclip/xsel)
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
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # pyperclip as fallback
    try:
        import pyperclip  # type: ignore[import]
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    return False
