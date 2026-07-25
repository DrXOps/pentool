# PENTOOL API CONTRACTS

**Version:** 1.0  
**Purpose:** Documentation of all API methods for module developers and SaaS integration

---

## TABLE OF CONTENTS

1. [ProxyAPI](#proxyapi)
2. [ScannerAPI](#scannerapi)
3. [IntruderAPI](#intruderapi)
4. [SpiderAPI](#spiderapi)
5. [RepeaterAPI](#repeaterapi)
6. [TargetAPI](#targetapi)
7. [DecoderAPI](#decoderapi)
8. [ComparerAPI](#comparerapi)
9. [SequencerAPI](#sequencerapi)

---

## ProxyAPI

**File:** `pentool/api/proxy_api.py`  
**Purpose:** HTTP proxy server management

### Methods

#### `start(host: str, port: int) -> None`
Start the proxy server.

**Parameters:**
- `host` — listen address (usually "127.0.0.1")
- `port` — port number (usually 8080)

**Exceptions:**
- `RuntimeError` — if proxy is already running
- `OSError` — if port is already in use

**Example:**
```python
from pentool.api.proxy_api import ProxyAPI

proxy = ProxyAPI()
proxy.start("127.0.0.1", 8080)
```

---

#### `stop() -> None`
Stop the proxy server.

**Exceptions:**
- `RuntimeError` — if proxy is not running

**Example:**
```python
proxy.stop()
```

---

#### `is_running` property
Check if proxy is running.

**Returns:** `True` if proxy is running, otherwise `False`

**Example:**
```python
if proxy.is_running:
    print("Proxy is running")
```

⚠️ **Important:** This is a property, call WITHOUT parentheses!

---

#### `get_requests(limit: int = 100) -> list[dict]`
Get history of intercepted requests.

**Parameters:**
- `limit` — maximum number of records

**Returns:** List of dictionaries with fields:
- `id` (int)
- `method` (str)
- `url` (str)
- `status_code` (int)
- `timestamp` (float)
- `host` (str)
- `length` (int)

**Example:**
```python
requests = await proxy.get_requests(limit=50)
for req in requests:
    print(f"{req['method']} {req['url']}")
```

---

#### `export_project_data() -> dict`
Export proxy data for project saving.

**Returns:** Dictionary with keys:
- `proxy` — scope and match/replace rules
- `http_history` — intercepted requests

**Example:**
```python
data = proxy.export_project_data()
with open("project.json", "w") as f:
    json.dump(data, f)
```

---

#### `import_project_data(data: dict) -> tuple[int, str]`
Import data from loaded project.

**Parameters:**
- `data` — dictionary returned by `core.project.load_project()`

**Returns:** Tuple `(count, error)`:
- `count` — number of loaded requests
- `error` — empty string if OK, error description otherwise

**Example:**
```python
with open("project.json") as f:
    data = json.load(f)
count, error = proxy.import_project_data(data)
if error:
    print(f"Error: {error}")
else:
    print(f"Loaded {count} requests")
```

---

## ScannerAPI

**File:** `pentool/api/scanner_api.py`  
**Purpose:** Vulnerability scanning

### Methods

#### `async scan(url: str, checks: list[str] = None) -> list[Finding]`
Start active scan on target URL.

**Parameters:**
- `url` — target URL
- `checks` — list of check names (None = all available)

**Returns:** List of `Finding` objects

**Example:**
```python
from pentool.api.scanner_api import ScannerAPI

scanner = ScannerAPI()
findings = await scanner.scan(
    "https://example.com",
    checks=["xss", "sqli", "ssrf"]
)

for finding in findings:
    print(f"{finding.severity}: {finding.title}")
```

---

#### `async get_findings(limit: int = 1000) -> list[Finding]`
Get all findings from database.

**Parameters:**
- `limit` — maximum number of findings

**Returns:** List of `Finding` objects sorted by severity

**Example:**
```python
findings = await scanner.get_findings(limit=100)
```

---

#### `get_available_checks() -> list[str]`
Get list of available vulnerability checks.

**Returns:** List of check names

**Example:**
```python
checks = scanner.get_available_checks()
print(f"Available: {', '.join(checks)}")
```

---

## IntruderAPI

**File:** `pentool/api/intruder_api.py`  
**Purpose:** Automated attacks and brute-force

### Methods

#### `async attack(request: str, positions: list[int], payloads: list[str], attack_type: str = "sniper") -> int`
Start attack.

**Parameters:**
- `request` — HTTP request template
- `positions` — list of byte positions for payload insertion
- `payloads` — list of payloads
- `attack_type` — attack type: "sniper", "battering_ram", "pitchfork", "cluster_bomb"

**Returns:** Attack ID

**Example:**
```python
from pentool.api.intruder_api import IntruderAPI

intruder = IntruderAPI()

request = """GET /api/user?id=1 HTTP/1.1
Host: example.com

"""

# Mark position: id=§1§
positions = [request.find("id=") + 3]
payloads = ["1", "2", "3", "admin", "' OR 1=1--"]

attack_id = await intruder.attack(
    request=request,
    positions=positions,
    payloads=payloads,
    attack_type="sniper"
)
```

---

#### `get_results(attack_id: int = None) -> list[IntruderResult]`
Get attack results.

**Parameters:**
- `attack_id` — specific attack ID (None = latest)

**Returns:** List of results

**Example:**
```python
results = intruder.get_results()
for r in results:
    print(f"Payload: {r.payload_values}, Status: {r.response_status}")
```

---

## SpiderAPI

**File:** `pentool/api/spider_api.py`  
**Purpose:** Web crawling

### Methods

#### `async crawl(base_url: str, max_depth: int = 3) -> dict`
Start crawling from base URL.

**Parameters:**
- `base_url` — starting URL
- `max_depth` — maximum crawl depth

**Returns:** Dictionary with:
- `urls` — list of discovered URLs
- `forms` — list of discovered forms
- `endpoints` — list of API endpoints

**Example:**
```python
from pentool.api.spider_api import SpiderAPI

spider = SpiderAPI()
results = await spider.crawl("https://example.com", max_depth=2)
print(f"Found {len(results['urls'])} URLs")
```

---

## RepeaterAPI

**File:** `pentool/api/repeater_api.py`  
**Purpose:** Manual request sending

### Methods

#### `async send(request: str) -> dict`
Send HTTP request and get response.

**Parameters:**
- `request` — raw HTTP request

**Returns:** Dictionary with:
- `status` — HTTP status code
- `headers` — response headers dict
- `body` — response body
- `time` — request time in ms

**Example:**
```python
from pentool.api.repeater_api import RepeaterAPI

repeater = RepeaterAPI()

request = """GET / HTTP/1.1
Host: example.com

"""

response = await repeater.send(request)
print(f"Status: {response['status']}")
print(f"Time: {response['time']}ms")
```

---

## TargetAPI

**File:** `pentool/api/target_api.py`  
**Purpose:** Target scope management

### Methods

#### `add_to_scope(host: str) -> None`
Add host to scope.

**Parameters:**
- `host` — hostname or pattern (supports wildcards)

**Example:**
```python
from pentool.api.target_api import TargetAPI

target = TargetAPI()
target.add_to_scope("example.com")
target.add_to_scope("*.example.com")
```

---

#### `is_in_scope(url: str) -> bool`
Check if URL is in scope.

**Parameters:**
- `url` — URL to check

**Returns:** `True` if in scope

**Example:**
```python
if target.is_in_scope("https://api.example.com/users"):
    print("In scope")
```

---

#### `get_sitemap() -> dict`
Get site map.

**Returns:** Dictionary with site structure

**Example:**
```python
sitemap = target.get_sitemap()
```

---

## DecoderAPI

**File:** `pentool/api/decoder_api.py`  
**Purpose:** Encoding/decoding operations

### Functions

#### `decode_op(data: str, operation: str) -> str`
Apply decoding operation.

**Parameters:**
- `data` — input data
- `operation` — operation name (see `OPERATIONS`)

**Returns:** Decoded string

**Available operations:**
- `url_decode`, `url_encode`
- `base64_decode`, `base64_encode`
- `html_decode`, `html_encode`
- `hex_decode`, `hex_encode`
- `md5`, `sha1`, `sha256`, `sha512`
- `gzip_decompress`, `gzip_compress`
- `jwt_decode`

**Example:**
```python
from pentool.api.decoder_api import decode_op

result = decode_op("SGVsbG8gV29ybGQ=", "base64_decode")
print(result)  # "Hello World"
```

---

#### `decode_smart(data: str) -> str`
Auto-detect and decode.

**Parameters:**
- `data` — encoded data

**Returns:** Decoded string (tries multiple methods)

**Example:**
```python
from pentool.api.decoder_api import decode_smart

result = decode_smart("%48%65%6C%6C%6F")  # Auto-detects URL encoding
print(result)  # "Hello"
```

---

## ComparerAPI

**File:** `pentool/api/comparer_api.py`  
**Purpose:** Text comparison

### Functions

#### `compare(text1: str, text2: str) -> DiffResult`
Compare two texts.

**Parameters:**
- `text1` — first text
- `text2` — second text

**Returns:** `DiffResult` object with:
- `lines` — list of `DiffLine` objects
- `stats` — `CompareStats` with counts

**Example:**
```python
from pentool.api.comparer_api import compare

result = compare("Hello World", "Hello Python")
for line in result.lines:
    if line.type == "modified":
        print(f"Changed: {line.text}")
```

---

## SequencerAPI

**File:** `pentool/api/sequencer_api.py`  
**Purpose:** Randomness analysis

### Class Methods

#### `analyze(tokens: list[str]) -> SequencerReport`
Analyze token randomness.

**Parameters:**
- `tokens` — list of tokens to analyze

**Returns:** `SequencerReport` with:
- `entropy` — Shannon entropy
- `charset_size` — detected character set size
- `min_length`, `max_length` — length statistics
- `patterns` — detected patterns

**Example:**
```python
from pentool.api.sequencer_api import Sequencer

tokens = ["abc123", "def456", "ghi789"]
report = Sequencer.analyze(tokens)
print(f"Entropy: {report.entropy:.2f} bits")
```

---

## Common Patterns

### Async/Await
Most API methods are async and require `await`:

```python
import asyncio
from pentool.api.scanner_api import ScannerAPI

async def main():
    scanner = ScannerAPI()
    findings = await scanner.scan("https://example.com")
    
asyncio.run(main())
```

### Error Handling
All APIs raise standard Python exceptions:

```python
try:
    proxy.start("127.0.0.1", 8080)
except OSError as e:
    print(f"Port already in use: {e}")
except RuntimeError as e:
    print(f"Proxy error: {e}")
```

### Type Hints
All APIs use type hints for better IDE support:

```python
from pentool.api.proxy_api import ProxyAPI

def my_function(proxy: ProxyAPI) -> None:
    # IDE will autocomplete proxy methods
    proxy.start("127.0.0.1", 8080)
```

---

## Complete Example

```python
import asyncio
from pentool.api import ProxyAPI, ScannerAPI, TargetAPI

async def main():
    # Initialize APIs
    proxy = ProxyAPI()
    scanner = ScannerAPI()
    target = TargetAPI()
    
    # Configure scope
    target.add_to_scope("example.com")
    
    # Start proxy
    proxy.start("127.0.0.1", 8080)
    print("Proxy started on port 8080")
    
    # Wait for some traffic...
    await asyncio.sleep(10)
    
    # Get intercepted requests
    requests = await proxy.get_requests(limit=10)
    print(f"Captured {len(requests)} requests")
    
    # Scan first URL
    if requests:
        url = requests[0]['url']
        findings = await scanner.scan(url)
        print(f"Found {len(findings)} vulnerabilities")
        
        for finding in findings:
            print(f"  [{finding.severity}] {finding.title}")
    
    # Stop proxy
    proxy.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

**For more examples, see `examples/` directory in the repository.**
