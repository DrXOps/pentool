# PENTOOL API CONTRACTS

**Version:** 1.1
**Purpose:** Documentation of the public `pentool/api/*` classes used by the TUI, CLI, and SaaS/plugin integrations. TUI screens must import from `pentool.api.*`, never from `pentool.modules.*` directly.

---

## TABLE OF CONTENTS

1. [ProxyAPI](#proxyapi)
2. [ScannerAPI](#scannerapi) *(PRO)*
3. [IntruderAPI](#intruderapi)
4. [SpiderAPI](#spiderapi)
5. [RepeaterAPI](#repeaterapi)
6. [TargetAPI](#targetapi)
7. [DecoderAPI](#decoderapi)
8. [ComparerAPI](#comparerapi)
9. [SequencerAPI](#sequencerapi)
10. [ExportableAPI (base class)](#exportableapi-base-class)

---

## ProxyAPI

**File:** `pentool/api/proxy_api.py`
**Purpose:** Thin wrapper around the actual `ProxyServer` instance (`pentool.modules.proxy.ProxyServer`). `ProxyAPI` itself does not start/stop network I/O — it holds a reference to a `ProxyServer` created elsewhere (`create_proxy()`) or injected (`set_proxy()`), and forwards calls to it.

### Methods

#### `create_proxy(host="127.0.0.1", port=8080, cert_dir="/tmp/pentool_certs", db_path=None) -> ProxyServer`
Create a new `ProxyServer` and store it internally.

#### `set_proxy(proxy: ProxyServer) -> None`
Inject an existing `ProxyServer` instance (used by the TUI app, which owns the proxy's lifecycle/thread).

#### `get_proxy() -> ProxyServer | None`
Return the underlying `ProxyServer`, or `None` if not yet created/injected.

#### `is_running() -> bool`
`True` if a proxy is set and its `is_running` property is `True`.

⚠️ Note: on `ProxyServer` itself, `is_running` is a **property** (call without parentheses). On `ProxyAPI`, `is_running()` is a regular **method** (call with parentheses).

#### `get_port() -> int` / `get_host() -> str`
Return the configured port/host, or the defaults (`8080` / `"127.0.0.1"`) if no proxy is set.

#### `get_status() -> dict`
Returns `{"running", "host", "port", "intercept_enabled", "scope", "rules_count", "requests_count", "waiting_count"}`.

#### `get_requests(limit=100, method=None, host=None) -> list[InterceptedRequest]`
In-memory request history (bounded ring, see `ProxyServer.requests`) — NOT the full SQLite-backed HTTP History (that's `ProxyService.get_history()` in `pentool/services/proxy_service.py`, used by the TUI's ProxyScreen).

#### `find_request(req_id: str) -> InterceptedRequest | None`
Find a request by ID (full or partial UUID).

#### `clear_requests() -> None`
Clear the in-memory request list.

#### `forward(req_id: str, modified_raw: str | None = None) -> None`
Forward a waiting (intercepted) request to the target server, optionally with modified raw HTTP text.
Raises `RuntimeError` if no proxy is set.

#### `drop(req_id: str) -> None`
Drop a waiting request. Raises `RuntimeError` if no proxy is set.

#### `set_intercept(enabled: bool) -> None` / `get_intercept() -> bool`
Toggle interactive intercept mode. `set_intercept` is thread-safe (uses `call_soon_threadsafe` internally since the proxy loop runs on its own thread).

#### `set_scope(hosts: list[str]) -> None` / `get_scope() -> list[str]`
Configure the host allowlist used by `ProxyServer.is_in_scope()`. An empty list means "match everything" — see `ProxyServer.enforce_scope` for whether out-of-scope traffic is actually filtered from capture (off by default; toggled via the "Skip out-of-scope" button in the Proxy screen).

#### `get_match_replace_rules() -> list[MatchReplaceRule]` / `set_match_replace_rules(rules) -> None`
Get/replace the Match & Replace rule set.

#### `export_project_data() -> dict`
Returns `{"proxy": {"scope": [...], "match_replace": [...]}, "http_history": [...]}` (not async).

#### `import_project_data(data: dict) -> tuple[int, str]`
Returns `(loaded_count, error_message)` — `error_message` is `""` on success.

**Example:**
```python
from pentool.api.proxy_api import ProxyAPI

proxy_api = ProxyAPI()
proxy = proxy_api.create_proxy(host="127.0.0.1", port=8080)
await proxy.start()  # actual start() is async, lives on ProxyServer, not ProxyAPI

if proxy_api.is_running():
    print("Proxy is running")

requests = proxy_api.get_requests(limit=50)
for req in requests:
    print(f"{req.method} {req.url}")
```

---

## ScannerAPI *(PRO)*

**File:** `pro/pentool/api/scanner_api.py` — lives in the `pentool-pro` package (obfuscated, license-gated), not in the FREE `pentool` distribution.
**Purpose:** Active + passive vulnerability scanning across 22+ checks (SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE, CORS, JWT, NoSQLi, GraphQL, Prototype Pollution, DOM XSS, OAuth, Sensitive Data, Header Injection, Path Traversal, Open Redirect, Broken Auth, Missing Security Headers, Info Leak).

### Methods

#### `async start_active_scan(targets: list[str], check_names: list[str] | None = None, on_finding=None, on_progress=None, on_request=None, concurrency: int = 5, request_delay: float = 0.0) -> str`
Start an active scan in the background (returns immediately with a scan ID; the scan itself runs as an `asyncio.Task`).

#### `async stop_scan() -> None`
Cancel the running active scan.

#### `is_scanning() -> bool`
Whether an active scan task is currently running.

#### `async get_findings(limit: int = 200) -> list[Finding]`
Findings persisted so far for this project.

#### `async mark_false_positive(finding_id: str) -> None`

#### `async attach_passive(proxy_api=None) -> None` / `async detach_passive() -> None`
Attach/detach the passive scanner to the EventBus (analyzes traffic captured by Proxy).

#### `set_passive_callback(callback: Callable[[Finding], None]) -> None`

#### `async generate_report(path: str, fmt: str = "html") -> None`
`fmt` is one of `"html"`, `"json"`, `"csv"`.

#### `register_check(check: BaseCheck) -> None` / `get_registered_checks() -> list[BaseCheck]`

#### `export_project_data() -> dict` / `import_project_data(data: dict) -> int`

**Example:**
```python
from pentool.api.scanner_api import ScannerAPI

scanner = ScannerAPI(db_path="/path/to/project.db")
scan_id = await scanner.start_active_scan(
    targets=["https://example.com"],
    check_names=["xss", "sqli", "ssti"],
)
findings = await scanner.get_findings(limit=100)
for f in findings:
    print(f"{f.severity.upper()}: {f.title} at {f.url}")
```

---

## IntruderAPI

**File:** `pentool/api/intruder_api.py`
**Purpose:** Automated attacks (Sniper / Battering Ram / Pitchfork / Cluster Bomb) with an optional Turbo mode (connection pooling + keep-alive, PRO).

### Types

```python
class AttackType(str, Enum):
    SNIPER = "sniper"
    BATTERING_RAM = "battering_ram"
    PITCHFORK = "pitchfork"
    CLUSTER_BOMB = "cluster_bomb"

@dataclass
class IntruderConfig:
    template: str            # request template with §marker§ positions
    attack_type: AttackType
    payloads: list[list[str]]
    threads: int = 10
    delay_ms: int = 0

@dataclass
class IntruderResult:
    payload_values: list[str]
    request_number: int
    response_status: int | None
    response_length: int | None
    response_time_ms: float | None
    request_raw: str
    response_raw: str | None
    error: str | None
    timestamp: datetime
```

### Methods

#### `async start_attack(config: IntruderConfig, on_result=None, on_progress=None, turbo_mode: bool = False) -> str`
Returns the attack ID (or `"turbo"` in Turbo mode).

#### `async pause() -> None` / `async resume() -> None` / `async stop() -> None`

#### `get_results() -> list[IntruderResult]`
Not async.

#### `get_progress() -> tuple[int, int]`
`(done, total)`.

#### `is_running -> bool` (property)

#### `async load_payloads(path: str) -> list[str]`
#### `async generate_numeric(start: int, end: int, step: int = 1) -> list[str]`
#### `async generate_chars(charset: str, min_len: int, max_len: int) -> list[str]`
#### `export_csv(path: str) -> None`

#### Tab / result persistence (SQLite-backed, not project-JSON)
`async save_state(tab_name, template, attack_type, payloads)`, `async load_state(tab_name) -> dict | None`, `async save_result(result, project_id=None)`, `async get_results_from_db(attack_id=None, limit=1000) -> list[IntruderResult]`.

#### `export_project_data() -> dict` / `import_project_data(data: dict) -> int`

**Example:**
```python
from pentool.api.intruder_api import IntruderAPI, IntruderConfig, AttackType

intruder = IntruderAPI(db_path="/path/to/project.db")

config = IntruderConfig(
    template="GET /search?q=§payload§ HTTP/1.1\r\nHost: example.com\r\n\r\n",
    attack_type=AttackType.SNIPER,
    payloads=[["admin", "user", "test", "root"]],
    threads=5,
)

attack_id = await intruder.start_attack(config)
# ... wait / poll get_progress() ...
for r in intruder.get_results():
    print(f"{r.payload_values}: {r.response_status} ({r.response_length} bytes)")
```

---

## SpiderAPI

**File:** `pentool/api/spider_api.py`
**Purpose:** Async web crawler.

### Types

```python
@dataclass
class SpiderConfig:
    max_depth: int = 3
    max_pages: int = 100
    concurrency: int = 5
    timeout: float = 10.0
    user_agent: str = "pentool/1.0"
    respect_scope: bool = False
    js_render: bool = False  # requires Playwright
```

### Methods

#### `SpiderAPI(config: SpiderConfig | None = None)` / `SpiderAPI.from_params(max_depth=3, max_pages=100, concurrency=5, timeout=10.0) -> SpiderAPI`

#### `async crawl(url: str, on_page=None, on_progress=None, extra_headers: dict | None = None) -> SpiderResult`
Returns a `SpiderResult` with `.pages`, `.forms`, `.endpoints`, `.js_files`, `.errors`. Never raises — crawl errors are captured into `.errors`.

#### `stop() -> None`
Request the running crawl to stop.

#### `config -> SpiderConfig` (property)

#### `export_project_data() -> dict` / `import_project_data(data: dict) -> int`
Spider results are transient by design — both are no-ops (`{"spider": {}}` / `0`).

**Example:**
```python
from pentool.api.spider_api import SpiderAPI, SpiderConfig

spider = SpiderAPI(SpiderConfig(max_depth=2, max_pages=50))
result = await spider.crawl("https://example.com")
print(f"Found {len(result.pages)} pages, {len(result.forms)} forms")
```

---

## RepeaterAPI

**File:** `pentool/api/repeater_api.py`
**Purpose:** Send a single modified HTTP request, optionally saving it to the project's history.

### Methods

#### `RepeaterAPI(db_path: str, project_id: int | None = None, timeout: float = 30.0, verify_ssl: bool = False)`

#### `async send(request: ParsedRequest, tab_name: str = "Tab", save: bool = True) -> ParsedResponse`
Takes a **`ParsedRequest`** object (from `pentool.utils.parser`), not a raw string — build one with `pentool.utils.parser.parse_http_request(raw_text)` first.

#### `async save_to_history(request: ParsedRequest, response: ParsedResponse, tab_name: str = "Tab") -> int`
#### `async get_history(limit: int = 50, project_id: int | None = None) -> list[RepeaterEntry]`
#### `async get_entry(entry_id: int) -> RepeaterEntry | None`
#### `async delete_entry(entry_id: int) -> None`

#### `export_project_data() -> dict` / `import_project_data(data: dict) -> int`
Repeater history lives in SQLite (`repeater_entries` table) and is loaded on demand — both are no-ops.

**Example:**
```python
from pentool.api.repeater_api import RepeaterAPI
from pentool.utils.parser import parse_http_request

repeater = RepeaterAPI(db_path="/path/to/project.db")

raw = "GET /api/users HTTP/1.1\r\nHost: example.com\r\nUser-Agent: Pentool\r\n\r\n"
request = parse_http_request(raw)

response = await repeater.send(request, tab_name="Users")
print(f"Status: {response.status}")
print(f"Body: {response.body}")
```

---

## TargetAPI

**File:** `pentool/api/target_api.py`
**Purpose:** Manage the project's site map (`SiteMap`) — discovered hosts/paths and their in-scope flag.

### Methods

#### `TargetAPI(db_path: str = "")`
#### `sitemap -> SiteMap` (property) — direct access to the underlying `SiteMap` object.
#### `async load() -> None` / `async save() -> None`
#### `add_request(req: ParsedRequest) -> None`
Register a request into the site map (called by the Proxy screen for every captured request).
#### `get_tree() -> dict[str, list[SiteNode]]`
#### `get_hosts() -> list[str]` / `get_paths(host: str) -> list[SiteNode]`
#### `set_in_scope(host: str, in_scope: bool) -> None`
Set the scope flag for a single host in the site map — this is the mechanism that drives the ★ marker in the Target tree, and what the `SyncScopeToTarget` message (posted from the Proxy screen's Scope dialog and context menu) ultimately calls.
#### `get_scope() -> list[str]`
Hosts currently flagged `in_scope=True` in the site map.
#### `clear() -> None`
#### `export_json(path: str) -> None`
#### `export_project_data() -> dict` / `import_project_data(data: dict) -> int`

**Example:**
```python
from pentool.api.target_api import TargetAPI

target = TargetAPI(db_path="/path/to/project.db")
await target.load()

target.set_in_scope("example.com", True)
tree = target.get_tree()
print(f"Hosts: {target.get_hosts()}")
await target.save()
```

---

## DecoderAPI

**File:** `pentool/api/decoder_api.py` — a thin re-export of `pentool/modules/decoder.py` functions, not a class.
**Purpose:** Encode/decode/hash text data (19 operations).

### Functions

#### `encode_op(operation: str, text: str) -> str`
Apply an operation by its label (see `OP_LABELS`). Note the argument order: **operation name first, then text.**

#### `decode_op(operation: str, text: str) -> str`
Alias for `encode_op` — operation labels already encode direction (e.g. `"Base64 Decode"` vs `"Base64 Encode"`), there is no separate decode/encode dispatch.

**Available operations (`OP_LABELS`):** `URL Encode`, `URL Decode`, `Base64 Encode`, `Base64 Decode`, `Base64URL Encode`, `Base64URL Decode`, `HTML Encode`, `HTML Decode`, `Hex Encode`, `Hex Decode`, `Unicode Encode`, `Unicode Decode`, `JWT Decode`, `Gzip+B64 Encode`, `Gzip+B64 Decode`, `MD5`, `SHA1`, `SHA256`, `SHA512`.

#### `run_chain(operations: list[str], text: str) -> tuple[str, list[str]]`
Apply a sequence of operations, returning `(final_text, per_step_texts)`.

#### `decode_smart(text: str, max_depth: int = 8) -> str`
Auto-detect the encoding and decode (tries multiple methods, up to `max_depth` layers).

#### `detect_encoding(text: str) -> str | None`
Best-guess encoding detection without decoding.

#### `class DecoderChain`
Stateful multi-step chain helper used by the Decoder screen's "chain" mode.

**Example:**
```python
from pentool.api.decoder_api import decode_op, decode_smart

result = decode_op("Base64 Decode", "SGVsbG8gV29ybGQ=")
print(result)  # "Hello World"

result = decode_smart("%48%65%6C%6C%6F")  # auto-detects URL encoding
print(result)  # "Hello"
```

---

## ComparerAPI

**File:** `pentool/api/comparer_api.py` — re-exports from `pentool/modules/comparer.py`, not a class.
**Purpose:** Line-level diff between two texts.

### Functions

#### `compare(left: str, right: str) -> DiffResult`
#### `compare_lines(left_lines: list[str], right_lines: list[str]) -> DiffResult`

`DiffResult` has `.lines: list[DiffLine]` and `.stats: CompareStats`.

**Example:**
```python
from pentool.api.comparer_api import compare

result = compare("Hello World", "Hello Pentool")
for line in result.lines:
    print(line)
```

---

## SequencerAPI

**File:** `pentool/api/sequencer_api.py` — re-exports from `pentool/modules/sequencer.py`.
**Purpose:** Token randomness/entropy analysis (session tokens, CSRF tokens, etc.).

### Functions

#### `token_entropy(token: str) -> float`
Shannon entropy of a single token, in bits.

#### `charset_size(token: str) -> int`
Detected character-set size for a token (used to normalize entropy).

### `class Sequencer`
Stateful token collector used by the Sequencer screen.

#### `add_token(token: str) -> None` / `add_tokens_bulk(tokens: list[str]) -> int` / `add_from_text(text: str) -> int`
#### `extract_from_header(header_value: str, param: str) -> str | None`
Extract a parameter value from a Cookie-style header string.

`SequencerReport` (built by the Sequencer screen from the collected tokens) includes entropy, FIPS 140-2 statistical test results, and per-position entropy — see `pentool/modules/sequencer.py` for the full dataclass.

**Example:**
```python
from pentool.api.sequencer_api import Sequencer, token_entropy

seq = Sequencer()
seq.add_tokens_bulk(["abc123", "abc124", "abc125", "abc126"])
print(f"Entropy of first token: {token_entropy('abc123'):.2f} bits")
```

---

## ExportableAPI (base class)

**File:** `pentool/api/base_api.py`
**Purpose:** Common interface every `*API` class implements so `core.project.save_project()`/`load_project()` can serialize/restore all modules uniformly.

```python
class ExportableAPI(ABC):
    @abstractmethod
    def export_project_data(self) -> dict:
        """Return a JSON-serializable dict (no datetime — use .isoformat())."""

    @abstractmethod
    def import_project_data(self, data: dict) -> int | tuple[int, str]:
        """Restore state from a project.json block. Returns a count, or
        (count, error_message) if the API needs to report failures."""
```

Modules whose real state lives in SQLite (Repeater, Spider, Intruder tab state) implement these as no-ops or thin wrappers — the DB *is* the source of truth, not the project JSON blob.

---

## Common Patterns

### Async vs. sync
Most I/O-bound methods are `async` and must be awaited. A few pure in-memory accessors (`get_requests`, `get_results`, `get_scope`, `compare`, `token_entropy`, …) are plain synchronous methods/functions — check the signature above rather than assuming.

```python
result = await api.some_async_method()   # ✅
result = api.some_sync_method()          # ✅ — no await needed
```

### Error handling
```python
try:
    proxy.forward(req_id)
except RuntimeError as e:
    print(f"Proxy not initialized: {e}")
```

### Import paths
Always import from `pentool.api.*`, never `pentool.modules.*`:
```python
from pentool.api.target_api import TargetAPI       # ✅
from pentool.modules.target import SiteMap         # ❌ (internal, no stability guarantee)
```

### EventBus
Several API-driven actions also emit events on the process-wide EventBus (`pentool.core.event_bus`), independent of any particular API's return value — e.g. `ProxyRequestCaptured`/`ProxyRequestCompleted` (Proxy), `FindingDiscovered` (Scanner), `ScanStarted`/`ScanFinished`, `SpiderFinished`.

```python
from pentool.core.event_bus import get_event_bus
from pentool.core.events import FindingDiscovered

def on_finding(event: FindingDiscovered) -> None:
    print(f"New finding: {event.finding.title}")

get_event_bus().subscribe(FindingDiscovered, on_finding)
```

### Licensing (PRO features)
```python
from pentool.core.license import get_session_license

lic = get_session_license()
if lic.has_feature("scanner_pro"):
    ...
else:
    print("Scanner requires an active PRO license/trial")
```

---

## Testing

API classes have unit tests under `tests/unit/api/`:
```bash
pytest tests/unit/api/test_proxy_api.py -v
```

---

## CHANGELOG

### v1.1 (2026-08-08)
- Rewritten in English (was previously Russian at the repo root, inconsistent with the other `docs/*.md` files, which are all English-first).
- Corrected method signatures across all sections to match the current code — the v1.0 draft had drifted significantly from `pentool/api/*` (invented methods like `ProxyAPI.start()`/`ScannerAPI.scan()`/`TargetAPI.add_to_scope()` that do not exist; wrong parameter names/order in several places).
- Added `ExportableAPI` base-class section.
- Noted that `ScannerAPI` ships in the separate PRO package (`pentool-pro`), not the FREE `pentool` distribution.

### v1.0 (2026-07-22)
- Initial contract draft, all core APIs documented, `StorageInterface` mentioned for SaaS-readiness.

---

**For developers:** when you add a new public method to any `pentool/api/*` class, update this document in the same change — a signature drift here is easy to miss and directly misleads anyone (including future you) integrating against these APIs.
