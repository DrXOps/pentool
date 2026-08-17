# 🚀 Pentool Quick Start Guide

Get started with Pentool in 5 minutes!

---

## Installation

```bash
# Install from PyPI (recommended)
uv tool install pentool

# Alternative: pip
# pip install pentool

# Or from source
git clone https://github.com/DrXOps/pentool.git
cd pentool
uv sync
```

---

## First Launch

```bash
pentool
```

You'll see the TUI interface with the Dashboard screen.

**Navigation:**
- `Tab` / `Shift+Tab` — switch between widgets
- `Ctrl+X` — open menu
- `Ctrl+Q` — quit

---

## 1. Configure Browser Proxy

**Step 1:** Start Pentool Proxy
- Press `Ctrl+X` → Select "Proxy"
- Click "○ Proxy" to start it
- Default: `127.0.0.1:8080` (configurable in Settings)

**Step 2:** Configure your browser
- Firefox: Settings → Network → Manual proxy
- Set HTTP Proxy: `127.0.0.1` port `8080`
- Enable "Use this proxy for HTTPS"

**Step 3:** Install CA Certificate (for HTTPS)
- Pentool generates a local CA the first time the proxy starts
  (`~/.config/pentool/certs/ca.crt`) — nothing leaves your machine
- In the Proxy screen, click "Install CA cert" (or **Settings → Proxy →
  Install CA cert**) — this opens a dialog with the certificate path and
  step-by-step instructions for Firefox, Chrome, and system-wide install
- Firefox: `about:preferences#privacy` → Certificates → View Certificates →
  **Authorities** tab → Import → select `ca.crt` → check "Trust this CA to
  identify websites"

---

## 2. Intercept Your First Request

**Enable Intercept:**
- In Proxy screen, toggle "Intercept" ON
- Browse to any website in your browser
- Request will be captured in Pentool

**Actions:**
- **Forward** — send request as-is
- **Drop** — discard request
- **Send to Repeater** — modify and replay
- **Edit** — modify before forwarding

---

## 3. Use Repeater

**From intercepted request:**
- Right-click → "Send to Repeater"
- Or press `Ctrl+R`

**In Repeater:**
- Modify request (headers, body, URL)
- Click "Send" or press `Ctrl+Enter`
- View response
- Click "Send" again to replay

**Pro tip:** Create multiple tabs for different requests

---

## 4. Run Intruder Attack

**Step 1:** Prepare template
- From Repeater: "Send to Intruder"
- Or create new attack in Intruder screen

**Step 2:** Mark positions
- Place `§markers§` around payload positions
- Example: `GET /?id=§1§ HTTP/1.1`

**Step 3:** Load payloads
- Simple list: one payload per line
- Or generate: numbers, chars, etc.

**Step 4:** Start attack
- Select attack type (Sniper recommended for start)
- Set threads (5-10 for testing)
- Click "Start Attack"

**Step 5:** Analyze results
- Sort by status code, length, time
- Look for anomalies
- Export results to CSV

---

## 5. Decode/Encode Data

**Decoder screen:**
- Paste data in input
- Select format: Base64, URL, HTML, Hex, etc.
- Click Encode or Decode
- Chain multiple operations

---

## 6. Compare Responses

**Comparer screen:**
- Paste two requests/responses
- Click "Compare"
- View side-by-side diff
- Highlights differences

---

## Common Use Cases

### Testing Authentication
1. Intercept login request
2. Send to Repeater
3. Modify credentials
4. Check response for errors

### Finding SQLi
1. Intercept request with parameter
2. Send to Intruder
3. Load SQL injection payloads
4. Look for errors or time delays

### Brute Force
1. Intercept login form
2. Send to Intruder
3. Mark password position with §
4. Load password wordlist
5. Start attack

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+X` | Open menu |
| `Ctrl+Q` | Quit |
| `Ctrl+R` | Send to Repeater |
| `Ctrl+I` | Send to Intruder |
| `Ctrl+S` | Save project |
| `Ctrl+F` | Find/Filter |
| `Tab` | Next widget |
| `Shift+Tab` | Previous widget |

---

## Troubleshooting

### Proxy not starting
- Check if port 8080 is already in use
- Try different port in settings

### HTTPS errors
- Install CA certificate
- Trust it in browser settings

### Slow performance
- Reduce Intruder threads
- Clear history (500+ entries)
- Restart Pentool

---

## Next Steps

- Read full [User Guide](USER_GUIDE.md)
- Check [API Reference](API_CONTRACTS.md)
- Join our [Telegram channel](https://t.me/pentool_pro) for news and releases

---

**Happy hacking! 🔐**
