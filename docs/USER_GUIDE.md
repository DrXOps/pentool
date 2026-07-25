# 📖 Pentool User Guide

Complete guide to using Pentool for web security testing.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Proxy Module](#proxy-module)
3. [Repeater Module](#repeater-module)
4. [Intruder Module](#intruder-module)
5. [Scanner Module](#scanner-module)
6. [Decoder Module](#decoder-module)
7. [Comparer Module](#comparer-module)
8. [Spider Module](#spider-module)
9. [WebSocket Module](#websocket-module)
10. [HTTPQL Filtering](#httpql-filtering)
11. [Keyboard Shortcuts](#keyboard-shortcuts)
12. [Tips & Tricks](#tips--tricks)

---

## Getting Started

### First Launch

```bash
pentool
```

The main interface consists of:
- **Top Bar** — navigation menu and status
- **Main Area** — current module screen
- **Status Bar** — connection status, shortcuts

### Navigation

- `Ctrl+X` — Open menu
- `Tab` / `Shift+Tab` — Switch between widgets
- `Ctrl+Q` — Quit
- Arrow keys — Navigate lists

---

## Proxy Module

The Proxy intercepts HTTP/HTTPS traffic between your browser and target.

### Starting the Proxy

1. Open Proxy screen (`Ctrl+X` → Proxy)
2. Configure settings:
   - **Port:** Default 8888
   - **Interface:** 127.0.0.1 (localhost) or 0.0.0.0 (all interfaces)
3. Click "Start Proxy"

### Browser Configuration

**Firefox:**
1. Settings → Network Settings → Manual proxy
2. HTTP Proxy: `127.0.0.1`, Port: `8888`
3. Check "Use this proxy for HTTPS"

**Chrome:**
```bash
# Linux/Mac
google-chrome --proxy-server="127.0.0.1:8888"

# Windows
chrome.exe --proxy-server="127.0.0.1:8888"
```

### Installing CA Certificate

For HTTPS interception:

1. With Proxy running, navigate to: `http://burp` or `http://127.0.0.1:8888`
2. Download `cacert.pem`
3. Install in browser:
   - **Firefox:** Preferences → Privacy & Security → Certificates → Import
   - **Chrome/System:** Settings → Manage certificates → Authorities → Import

### Intercept Mode

**Enable Intercept:**
- Toggle "Intercept" button ON
- All requests will pause for your review

**Actions on intercepted request:**
- **Forward** — Send request as-is
- **Drop** — Discard request
- **Edit** — Modify before forwarding
- **Send to Repeater** — Save for replay (`Ctrl+R`)
- **Send to Intruder** — Use for automated attacks (`Ctrl+I`)

### Request History

All proxied requests appear in History tab:
- Click to view request/response details
- Right-click for context menu
- Use HTTPQL to filter (see [HTTPQL section](#httpql-filtering))

### Match & Replace

Automatically modify requests/responses:

1. Open Match & Replace dialog
2. Add rule:
   - **Type:** Request Header / Request Body / Response
   - **Match:** Regex pattern
   - **Replace:** Replacement text
3. Rules apply to all traffic

---

## Repeater Module

Modify and replay HTTP requests.

### Sending to Repeater

From Proxy or other modules:
- Right-click request → "Send to Repeater"
- Or press `Ctrl+R`

### Using Repeater

**Request Panel (Left):**
- Edit any part of request:
  - Method, URL, path
  - Headers
  - Body
- Syntax highlighting for JSON/XML

**Response Panel (Right):**
- View response after sending
- Tabs: Headers / Body / Hex

**Actions:**
- **Send** (`Ctrl+Enter`) — Send modified request
- **Save** — Save request/response
- **New Tab** — Create another request tab
- **Close Tab** — Close current tab

### Advanced Features

**Parameters Tab:**
- Automatically parsed from URL and body
- Edit in table format
- Auto-updates request

**Headers Tab:**
- Add/remove/edit headers easily
- Common headers suggested

---

## Intruder Module

Automated attacks with payload injection.

### Creating an Attack

**Step 1: Prepare Template**
- Send request from Repeater/Proxy
- Or paste raw HTTP request

**Step 2: Mark Positions**
- Place `§` markers around injection points
- Example: `GET /?id=§1§&user=§admin§ HTTP/1.1`
- Multiple positions supported

**Step 3: Configure Payloads**

**Simple List:**
```
admin
root
test
```

**Generate:**
- Numbers: 1-1000
- Characters: a-z, A-Z, 0-9
- Dates: 2020-01-01 to 2024-12-31

**From File:**
- Load wordlist (one payload per line)
- Common paths: `/usr/share/wordlists/`

**Step 4: Select Attack Type**

**Sniper (Default):**
- One position at a time
- Uses single payload list
- Total requests = positions × payloads

**Battering Ram:**
- All positions get same payload simultaneously
- Uses single payload list
- Total requests = payloads

**Pitchfork:**
- Each position has its own payload list
- Iterates in parallel (zip)
- Total requests = min(list lengths)

**Cluster Bomb:**
- Cartesian product of all payload lists
- Total requests = list1 × list2 × ...
- ⚠️ Can generate MANY requests!

**Step 5: Configure Options**

- **Threads:** 5-50 (more = faster, but may trigger rate limits)
- **Delay:** Milliseconds between requests
- **Follow Redirects:** Enable/disable
- **Turbo Mode:** 10x speed boost (PRO)

**Step 6: Start Attack**

Click "Start Attack" and monitor results in real-time.

### Analyzing Results

**Results Table:**
- **#** — Request number
- **Payloads** — Values used
- **Status** — HTTP status code
- **Length** — Response size
- **Time** — Response time (ms)
- **Error** — Any errors

**Sorting:**
- Click column headers to sort
- Look for anomalies:
  - Different status codes
  - Different response lengths
  - Longer/shorter response times

**Filtering:**
- Show only specific status codes
- Filter by response length
- Search in responses

**Exporting:**
- Export to CSV for analysis
- Export selected results

### Common Attack Patterns

**Password Brute Force:**
```
POST /login HTTP/1.1
Host: example.com
Content-Type: application/x-www-form-urlencoded

username=admin&password=§password§
```
- Load password wordlist
- Use Sniper attack
- Look for different status/length

**SQL Injection:**
```
GET /product?id=§1§ HTTP/1.1
Host: example.com
```
- Payloads: `1' OR '1'='1`, `1; DROP TABLE users--`
- Look for errors, different content lengths

**Username Enumeration:**
```
POST /register HTTP/1.1
...
username=§user§&email=test@test.com
```
- Load username list
- Different error messages reveal valid usernames

---

## Scanner Module

Automated vulnerability scanner with 23 checks.

### Starting a Scan

**Step 1: Define Target**
- Enter target URL(s)
- Or select from Proxy history

**Step 2: Configure Scan**

**Scope:**
- **URLs:** List of starting URLs
- **Max Depth:** How deep to crawl (2-10)
- **Max Pages:** Limit total pages (20-1000)

**Checks to Run:**
- **All** — Run all 23 checks
- **Selected** — Choose specific vulnerability types:
  - XSS (Reflected, Stored, DOM)
  - SQL Injection
  - Command Injection / RCE
  - SSRF
  - Path Traversal / LFI
  - XXE
  - SSTI
  - Open Redirect
  - And more...

**Performance:**
- **Threads:** 5-20 concurrent requests
- **Delay:** Rate limiting

**Step 3: Start Scan**

Click "Start Scan" — can take minutes to hours depending on scope.

### Understanding Results

**Findings Tab:**

Each finding shows:
- **Severity:** Critical / High / Medium / Low / Info
- **Type:** Vulnerability category
- **URL:** Affected endpoint
- **Parameter:** Vulnerable parameter
- **Payload:** Proof-of-concept payload
- **Evidence:** How vulnerability was detected

**Click finding for details:**
- Full description
- Request/response showing vulnerability
- Remediation advice
- CWE / MITRE ATT&CK references (if applicable)

### Severity Levels

- **Critical:** Remote code execution, SQL injection with data exfiltration
- **High:** XSS, authentication bypass, SSRF
- **Medium:** Information disclosure, missing security headers
- **Low:** Verbose errors, directory listing
- **Info:** Technology fingerprinting, interesting files

### Exporting Results

**HTML Report:**
- Professional format
- Includes all findings with details

**JSON:**
- Machine-readable
- For integration with other tools

**CSV:**
- Simple table format
- Import into spreadsheet

---

## Decoder Module

Encode/decode various formats.

### Supported Formats

**Encoding:**
- Base64
- URL encoding
- HTML entities
- Hex
- ASCII Hex
- Gzip
- JWT decode

**Hashing:**
- MD5
- SHA-1
- SHA-256

### Using Decoder

1. Paste or type data in input
2. Select operation from dropdown
3. Click "Encode" or "Decode"
4. Result appears below

**Chaining Operations:**
- Decode Base64 → URL decode → JSON pretty-print
- Build complex transformation chains

---

## Comparer Module

Compare two requests/responses to find differences.

### Using Comparer

1. Paste first request/response in left panel
2. Paste second in right panel
3. Click "Compare"

**Diff View:**
- Additions highlighted in green
- Deletions highlighted in red
- Side-by-side view
- Line numbers for easy reference

**Use Cases:**
- Compare two similar requests to find authentication differences
- Compare responses to detect changes (useful for blind SQLi)
- Analyze session tokens

---

## Spider Module

Automatically crawl website to discover content.

### Starting a Crawl

1. Enter starting URL
2. Configure:
   - **Max Depth:** Levels to follow (3-10)
   - **Max Pages:** Total pages limit (50-1000)
   - **Scope:** Stay in same domain / allow subdomains
3. Click "Start Crawl"

### Discovered URLs

All found URLs listed with:
- HTTP method
- Status code
- Content type
- Depth level

Right-click to send to other modules.

---

## WebSocket Module

Intercept and modify WebSocket traffic.

### Intercepting WebSockets

1. Enable WebSocket intercept
2. Connect to WebSocket from browser
3. Messages appear in real-time

**Actions:**
- View message content (text/binary)
- Modify before sending
- Drop message
- Replay message

---

## HTTPQL Filtering

SQL-like query language for request history.

### Basic Syntax

```sql
url contains "admin"
status == 200
method == "POST"
```

### Operators

- `==` — Equal
- `!=` — Not equal
- `contains` — String contains
- `matches` — Regex match
- `>`, `<`, `>=`, `<=` — Numeric comparison

### Fields

- `url` — Full URL
- `host` — Hostname
- `path` — URL path
- `method` — HTTP method
- `status` — Status code
- `length` — Response length
- `time` — Response time (ms)
- `request` — Request content
- `response` — Response content

### Complex Queries

```sql
-- Find admin panels with errors
url contains "admin" AND status >= 500

-- Large responses
length > 100000

-- Slow requests
time > 5000

-- POST with specific parameter
method == "POST" AND request contains "password="

-- Combine conditions
(status == 200 OR status == 301) AND host == "example.com"
```

---

## Keyboard Shortcuts

### Global

| Shortcut | Action |
|----------|--------|
| `Ctrl+X` | Open menu |
| `Ctrl+Q` | Quit |
| `Ctrl+S` | Save project |
| `Ctrl+F` | Focus search/filter |
| `Tab` | Next widget |
| `Shift+Tab` | Previous widget |

### Module-Specific

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Send to Repeater |
| `Ctrl+I` | Send to Intruder |
| `Ctrl+Enter` | Send request (Repeater) |
| `Ctrl+A` | Select all |
| `Ctrl+C` | Copy |
| `Ctrl+V` | Paste |

---

## Tips & Tricks

### Performance

**Speed up Intruder:**
- Use Turbo Mode (PRO) for 10x speed
- Increase threads (but watch for rate limiting)
- Reduce payload list size

**Reduce Memory Usage:**
- Clear history regularly (Settings → Clear History)
- Limit history size (500-5000 entries)
- Close unused tabs

### Security Testing

**Finding Vulnerabilities:**
1. Start with passive scanning (Spider + Proxy)
2. Review interesting endpoints
3. Manual testing with Repeater
4. Automated fuzzing with Intruder
5. Full scan with Scanner

**Avoiding Detection:**
- Use realistic User-Agent
- Add delays between requests
- Respect robots.txt (or don't, but carefully)
- Use proxy chains for anonymity

### Workflow

**Typical Testing Flow:**
1. Configure browser proxy
2. Browse target application normally
3. Review Proxy history for interesting requests
4. Send promising requests to Repeater
5. Experiment with modifications
6. Use Intruder for automated testing
7. Run Scanner for comprehensive check
8. Export findings

---

## Advanced Topics

### Custom Payloads

Create payload files for common attacks:

**SQL Injection (`sqli.txt`):**
```
' OR '1'='1
' OR '1'='1' --
' OR '1'='1' /*
1' UNION SELECT NULL--
1' UNION SELECT NULL,NULL--
```

**XSS (`xss.txt`):**
```
<script>alert(1)</script>
<img src=x onerror=alert(1)>
<svg onload=alert(1)>
'><script>alert(1)</script>
```

### Integration with Other Tools

**Burp Compatibility:**
- Import/export requests
- Similar UI concepts
- Familiar workflow

**With curl:**
```bash
# Export request from Pentool
# Copy as curl from context menu
curl -X POST http://example.com/api ...
```

---

## Troubleshooting

### Proxy Issues

**HTTPS Errors:**
- Install CA certificate
- Trust it in browser

**Connection Refused:**
- Check port not already in use
- Verify proxy running

**No Traffic Captured:**
- Verify browser proxy settings
- Check Intercept is ON (if enabled)

### Performance Issues

**Slow UI:**
- Clear history
- Reduce history limit
- Close unused modules

**Intruder Slow:**
- Reduce threads
- Enable Turbo Mode
- Check network speed

---

## Getting Help

- **Documentation:** https://pentool.dev/docs
- **GitHub Issues:** https://github.com/pentool/pentool/issues
- **Discord:** https://discord.gg/pentool
- **Email:** support@pentool.dev

---

**Happy hacking! 🔐**
