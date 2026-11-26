"""WSL clipboard: the Windows interop path is used first and survives a round trip.

Owner: copy and paste did not work from inside WSL. Inside WSL there is no DISPLAY and no
xclip, so every X11 backend fails; `clip.exe` and `powershell.exe Get-Clipboard` are the only
working path. The tests mock the interop so they run everywhere and still pin the order.
"""

from __future__ import annotations

import sys
from types import ModuleType

from pentool.utils import copy_as


class _Completed:
    def __init__(self, returncode: int = 0, stdout: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = b""


def test_copy_uses_clip_exe_when_running_under_wsl(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _Completed(0)

    monkeypatch.setattr(copy_as, "_is_wsl", lambda: True)
    monkeypatch.setattr(copy_as, "_find_executable", lambda name: "clip.exe" if name.startswith("clip") else None)
    monkeypatch.setattr(copy_as.subprocess, "run", fake_run)

    assert copy_as.copy_to_clipboard("hello") is True
    assert calls and calls[0][0] == "clip.exe"


def test_paste_uses_powershell_when_running_under_wsl(monkeypatch) -> None:
    monkeypatch.setattr(copy_as, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        copy_as,
        "_find_executable",
        lambda name: "powershell.exe" if name.startswith("powershell") else None,
    )
    monkeypatch.setattr(
        copy_as.subprocess,
        "run",
        lambda args, **kwargs: _Completed(0, b"text from windows clipboard\r\n"),
    )

    assert copy_as.paste_from_clipboard() == "text from windows clipboard"


def test_paste_falls_through_when_the_windows_clipboard_is_empty(monkeypatch) -> None:
    """An empty Windows clipboard must not be mistaken for no clipboard: the chain continues."""
    monkeypatch.setattr(copy_as, "_is_wsl", lambda: True)

    def only_powershell(args, **kwargs):
        if "powershell" in str(args[0]):
            return _Completed(0, b"\r\n")
        raise FileNotFoundError("not installed")  # other backends are absent

    monkeypatch.setattr(
        copy_as,
        "_find_executable",
        lambda name: "powershell.exe" if name.startswith("powershell") else None,
    )
    monkeypatch.setattr(copy_as.subprocess, "run", only_powershell)

    fake = ModuleType("pyperclip")
    fake.paste = lambda: "from pyperclip"  # type: ignore[attr-defined]
    fake.copy = lambda text: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyperclip", fake)

    assert copy_as.paste_from_clipboard() == "from pyperclip"


def test_broken_interop_does_not_raise(monkeypatch) -> None:
    """A disabled interop must degrade to the old chain, not break the copy."""

    def boom(args, **kwargs):
        # Only the interop binaries fail: a disabled WSL interop looks exactly like this.
        if "clip.exe" in str(args[0]) or "powershell" in str(args[0]):
            raise OSError("interop disabled")
        raise FileNotFoundError("not installed")

    monkeypatch.setattr(copy_as, "_is_wsl", lambda: True)
    monkeypatch.setattr(copy_as, "_find_executable", lambda name: None)
    monkeypatch.setattr(copy_as.subprocess, "run", boom)

    fake = ModuleType("pyperclip")
    fake.copy = lambda text: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyperclip", fake)

    assert copy_as.copy_to_clipboard("x") is True
