"""Dialog for installing the CA certificate for HTTPS interception."""

from __future__ import annotations

from pathlib import Path

_CSS = (Path(__file__).parent / "cert_dialog.tcss").read_text(encoding="utf-8")

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class CertInstallDialog(ModalScreen[None]):
    """Instructions for installing the CA certificate in a browser.

    Shows the CA path and commands for Firefox, Chrome and system-wide.
    """

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def __init__(self, ca_cert_path: str) -> None:
        super().__init__()
        self._ca_path = ca_cert_path

    def compose(self) -> ComposeResult:
        p = self._ca_path
        with Static(id="dialog"):
            yield Static("⚠  HTTPS Interception — Install CA Certificate", id="title")

            yield Static("CA certificate path:", classes="section-title")
            yield Static(p, classes="code")

            yield Static("Firefox  ⚠ do NOT double-click the file:", classes="section-title")
            yield Static(
                "1. Address bar → type:  about:preferences#privacy\n"
                "2. Scroll down → Certificates → [View Certificates...]\n"
                "3. Tab: Authorities  (NOT 'Your Certificates'!)\n"
                "4. Click [Import...] → select the ca.crt file above\n"
                "5. Check ✓ Trust this CA to identify websites → [OK]\n"
                "6. Restart Firefox",
                classes="code",
            )

            yield Static("Chrome / Chromium:", classes="section-title")
            yield Static(
                "1. Address bar → type:  chrome://settings/certificates\n"
                "2. Tab: Authorities\n"
                "3. Click [Import] → select the ca.crt file above\n"
                "4. Check ✓ Trust for identifying websites → [OK]\n"
                "5. Restart Chrome",
                classes="code",
            )

            yield Static("System-wide (Ubuntu/Debian):", classes="section-title")
            yield Static(
                f"sudo cp '{p}' /usr/local/share/ca-certificates/pentool-ca.crt\n"
                "sudo update-ca-certificates",
                classes="code",
            )

            yield Static("System-wide (Fedora/RHEL):", classes="section-title")
            yield Static(
                f"sudo cp '{p}' /etc/pki/ca-trust/source/anchors/pentool-ca.crt\n"
                "sudo update-ca-trust",
                classes="code",
            )

            yield Button("Close  [Esc]", id="btn-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)
