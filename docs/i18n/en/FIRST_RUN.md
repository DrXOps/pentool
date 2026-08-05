# 🚀 First Run — Certificate & First Intercept

A minimal walkthrough to get from `pip install pentool` to seeing your first
intercepted HTTPS request. For the full picture see the
[Quick Start Guide](QUICKSTART.md) and [User Guide](USER_GUIDE.md).

> ⚠️ **Use a modern terminal emulator.** Pentool's TUI relies on mouse
> support, true color, and modern rendering (Textual framework). Windows
> `cmd.exe` and old/legacy terminals will look broken or behave oddly.
> Recommended: **Windows Terminal**, **iTerm2** (macOS), **GNOME
> Terminal/Kitty/Alacritty/WezTerm** (Linux). On Windows, run Pentool inside
> **WSL** for the best experience.

---

## 1. Install and launch

```bash
pip install pentool
pentool
```

You'll land on the Dashboard screen.

## 2. Start the proxy

1. Switch to the **Proxy** module (`Ctrl+X` → Proxy, or `Shift+P`)
2. Click **"○ Proxy"** to start it — it turns into **"● Proxy :8080"**
   (default host/port `127.0.0.1:8080`, configurable in Settings)

## 3. Download and install the CA certificate

Pentool generates a local Certificate Authority the first time the proxy
starts, so it can decrypt HTTPS traffic for you (same approach as Burp/
mitmproxy). Nothing leaves your machine — the CA is generated locally in
`~/.config/pentool/certs/ca.crt`.

1. In the Proxy screen, click **"Install CA cert"** (or open it from
   **Settings → Proxy → Install CA cert**) — a dialog shows the certificate
   path and step-by-step instructions for Firefox, Chrome, and system-wide
   installation (Ubuntu/Debian, Fedora/RHEL).
2. Follow the instructions for your browser:
   - **Firefox:** `about:preferences#privacy` → Certificates → View
     Certificates → **Authorities** tab (not "Your Certificates") → Import →
     select `ca.crt` → check "Trust this CA to identify websites" → restart
     Firefox.
   - **Chrome/Chromium:** `chrome://settings/certificates` → Authorities →
     Import → select `ca.crt` → check "Trust for identifying websites" →
     restart Chrome.
   - **System-wide (Linux):** commands are shown directly in the dialog for
     your distro.
3. **Configure your browser's proxy settings** to point at Pentool:
   - HTTP/HTTPS proxy: `127.0.0.1`, port `8080` (or whatever you set)
   - Firefox: Settings → Network Settings → Manual proxy configuration
   - Chrome: launch with `--proxy-server="127.0.0.1:8080"`, or use a system-wide
     proxy setting / an extension like FoxyProxy

## 4. Intercept your first request

1. In the Proxy screen, toggle **"○ Intercept"** ON
2. Browse to any HTTPS site in your configured browser
3. The request pauses in Pentool's **Intercept** tab — review/edit it, then
   **Forward** or **Drop**
4. Turn Intercept back OFF to let traffic flow normally and just watch it
   accumulate in **HTTP History**

That's it — you're capturing and can now send requests to **Repeater**,
**Intruder**, or run the **Scanner** against them.

---

**Next:** [Quick Start Guide](QUICKSTART.md) · [User Guide](USER_GUIDE.md)
