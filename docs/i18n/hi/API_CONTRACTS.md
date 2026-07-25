# PENTOOL API अनुबंध

**संस्करण:** 1.0  
**उद्देश्य:** मॉड्यूल डेवलपर्स और SaaS एकीकरण के लिए सभी API विधियों का दस्तावेज़ीकरण

---

## विषय सूची

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

**फ़ाइल:** `pentool/api/proxy_api.py`  
**उद्देश्य:** HTTP प्रॉक्सी सर्वर प्रबंधन

### विधियां

#### `start(host: str, port: int) -> None`
प्रॉक्सी सर्वर प्रारंभ करें।

**पैरामीटर:**
- `host` — सुनने का पता (आमतौर पर "127.0.0.1")
- `port` — पोर्ट नंबर (आमतौर पर 8080)

**अपवाद:**
- `RuntimeError` — यदि प्रॉक्सी पहले से चल रहा है
- `OSError` — यदि पोर्ट पहले से उपयोग में है

**उदाहरण:**
```python
from pentool.api.proxy_api import ProxyAPI

proxy = ProxyAPI()
proxy.start("127.0.0.1", 8080)
```

---

#### `stop() -> None`
प्रॉक्सी सर्वर बंद करें।

**अपवाद:**
- `RuntimeError` — यदि प्रॉक्सी नहीं चल रहा है

**उदाहरण:**
```python
proxy.stop()
```

---

#### `is_running` गुण
जांचें कि प्रॉक्सी चल रहा है या नहीं।

**रिटर्न:** यदि प्रॉक्सी चल रहा है तो `True`, अन्यथा `False`

**उदाहरण:**
```python
if proxy.is_running:
    print("Proxy is running")
```

⚠️ **महत्वपूर्ण:** यह एक गुण है, कोष्ठक के बिना कॉल करें!

---

#### `get_requests(limit: int = 100) -> list[dict]`
इंटरसेप्ट किए गए अनुरोधों का इतिहास प्राप्त करें।

**पैरामीटर:**
- `limit` — अधिकतम रिकॉर्ड संख्या

**रिटर्न:** निम्नलिखित फ़ील्ड के साथ शब्दकोश की सूची:
- `id` (int)
- `method` (str)
- `url` (str)
- `status_code` (int)
- `timestamp` (float)
- `host` (str)
- `length` (int)

**उदाहरण:**
```python
requests = await proxy.get_requests(limit=50)
for req in requests:
    print(f"{req['method']} {req['url']}")
```

---

## ScannerAPI

**फ़ाइल:** `pentool/api/scanner_api.py`  
**उद्देश्य:** भेद्यता स्कैनिंग

### विधियां

#### `async scan(url: str, checks: list[str] = None) -> list[Finding]`
लक्ष्य URL पर सक्रिय स्कैन प्रारंभ करें।

**पैरामीटर:**
- `url` — लक्ष्य URL
- `checks` — चेक नामों की सूची (None = सभी उपलब्ध)

**रिटर्न:** `Finding` ऑब्जेक्ट की सूची

**उदाहरण:**
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
डेटाबेस से सभी खोजें प्राप्त करें।

**पैरामीटर:**
- `limit` — अधिकतम खोजों की संख्या

**रिटर्न:** गंभीरता के अनुसार क्रमबद्ध `Finding` ऑब्जेक्ट की सूची

**उदाहरण:**
```python
findings = await scanner.get_findings(limit=100)
```

---

#### `get_available_checks() -> list[str]`
उपलब्ध भेद्यता जांचों की सूची प्राप्त करें।

**रिटर्न:** चेक नामों की सूची

**उदाहरण:**
```python
checks = scanner.get_available_checks()
print(f"उपलब्ध: {', '.join(checks)}")
```

---

## IntruderAPI

**फ़ाइल:** `pentool/api/intruder_api.py`  
**उद्देश्य:** स्वचालित हमले और ब्रूट-फोर्स

### विधियां

#### `async attack(request: str, positions: list[int], payloads: list[str], attack_type: str = "sniper") -> int`
हमला प्रारंभ करें।

**पैरामीटर:**
- `request` — HTTP अनुरोध टेम्पलेट
- `positions` — payload सम्मिलन के लिए बाइट स्थितियों की सूची
- `payloads` — payloads की सूची
- `attack_type` — हमले का प्रकार: "sniper", "battering_ram", "pitchfork", "cluster_bomb"

**रिटर्न:** हमला ID

**उदाहरण:**
```python
from pentool.api.intruder_api import IntruderAPI

intruder = IntruderAPI()

request = """GET /api/user?id=1 HTTP/1.1
Host: example.com

"""

# स्थिति चिह्नित करें: id=§1§
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
हमले के परिणाम प्राप्त करें।

**पैरामीटर:**
- `attack_id` — विशिष्ट हमला ID (None = नवीनतम)

**रिटर्न:** परिणामों की सूची

**उदाहरण:**
```python
results = intruder.get_results()
for r in results:
    print(f"Payload: {r.payload_values}, Status: {r.response_status}")
```

---

## SpiderAPI

**फ़ाइल:** `pentool/api/spider_api.py`  
**उद्देश्य:** Web क्रॉलिंग

### विधियां

#### `async crawl(base_url: str, max_depth: int = 3) -> dict`
आधार URL से क्रॉलिंग प्रारंभ करें।

**पैरामीटर:**
- `base_url` — प्रारंभिक URL
- `max_depth` — अधिकतम क्रॉल गहराई

**रिटर्न:** शब्दकोश, जिसमें:
- `urls` — खोजे गए URL की सूची
- `forms` — खोजे गए फ़ॉर्म की सूची
- `endpoints` — API endpoints की सूची

**उदाहरण:**
```python
from pentool.api.spider_api import SpiderAPI

spider = SpiderAPI()
results = await spider.crawl("https://example.com", max_depth=2)
print(f"{len(results['urls'])} URL खोजे गए")
```

---

## RepeaterAPI

**फ़ाइल:** `pentool/api/repeater_api.py`  
**उद्देश्य:** मैनुअल अनुरोध भेजना

### विधियां

#### `async send(request: str) -> dict`
HTTP अनुरोध भेजें और प्रतिक्रिया प्राप्त करें।

**पैरामीटर:**
- `request` — कच्चा HTTP अनुरोध

**रिटर्न:** शब्दकोश, जिसमें:
- `status` — HTTP स्थिति कोड
- `headers` — प्रतिक्रिया headers शब्दकोश
- `body` — प्रतिक्रिया body
- `time` — अनुरोध समय (ms)

**उदाहरण:**
```python
from pentool.api.repeater_api import RepeaterAPI

repeater = RepeaterAPI()

request = """GET / HTTP/1.1
Host: example.com

"""

response = await repeater.send(request)
print(f"स्थिति: {response['status']}")
print(f"समय: {response['time']}ms")
```

---

## TargetAPI

**फ़ाइल:** `pentool/api/target_api.py`  
**उद्देश्य:** लक्ष्य दायरा प्रबंधन

### विधियां

#### `add_to_scope(host: str) -> None`
होस्ट को दायरे में जोड़ें।

**पैरामीटर:**
- `host` — होस्टनाम या पैटर्न (वाइल्डकार्ड समर्थित)

**उदाहरण:**
```python
from pentool.api.target_api import TargetAPI

target = TargetAPI()
target.add_to_scope("example.com")
target.add_to_scope("*.example.com")
```

---

#### `is_in_scope(url: str) -> bool`
जांचें कि URL दायरे में है या नहीं।

**पैरामीटर:**
- `url` — जांचने के लिए URL

**रिटर्न:** यदि दायरे में है तो `True`

**उदाहरण:**
```python
if target.is_in_scope("https://api.example.com/users"):
    print("दायरे में है")
```

---

## DecoderAPI

**फ़ाइल:** `pentool/api/decoder_api.py`  
**उद्देश्य:** एन्कोडिंग/डिकोडिंग संचालन

### फ़ंक्शन

#### `decode_op(data: str, operation: str) -> str`
डिकोडिंग संचालन लागू करें।

**पैरामीटर:**
- `data` — इनपुट डेटा
- `operation` — संचालन नाम (`OPERATIONS` देखें)

**रिटर्न:** डीकोड की गई स्ट्रिंग

**उपलब्ध संचालन:**
- `url_decode`, `url_encode`
- `base64_decode`, `base64_encode`
- `html_decode`, `html_encode`
- `hex_decode`, `hex_encode`
- `md5`, `sha1`, `sha256`, `sha512`
- `gzip_decompress`, `gzip_compress`
- `jwt_decode`

**उदाहरण:**
```python
from pentool.api.decoder_api import decode_op

result = decode_op("SGVsbG8gV29ybGQ=", "base64_decode")
print(result)  # "Hello World"
```

---

#### `decode_smart(data: str) -> str`
स्वचालित रूप से पता लगाएं और डीकोड करें।

**पैरामीटर:**
- `data` — एन्कोड किया गया डेटा

**रिटर्न:** डीकोड की गई स्ट्रिंग (कई विधियों का प्रयास करता है)

**उदाहरण:**
```python
from pentool.api.decoder_api import decode_smart

result = decode_smart("%48%65%6C%6C%6F")  # URL एन्कोडिंग स्वचालित रूप से पता लगाता है
print(result)  # "Hello"
```

---

## ComparerAPI

**फ़ाइल:** `pentool/api/comparer_api.py`  
**उद्देश्य:** टेक्स्ट तुलना

### फ़ंक्शन

#### `compare(text1: str, text2: str) -> DiffResult`
दो टेक्स्ट की तुलना करें।

**पैरामीटर:**
- `text1` — पहला टेक्स्ट
- `text2` — दूसरा टेक्स्ट

**रिटर्न:** `DiffResult` ऑब्जेक्ट, जिसमें:
- `lines` — `DiffLine` ऑब्जेक्ट की सूची
- `stats` — गणना के साथ `CompareStats`

**उदाहरण:**
```python
from pentool.api.comparer_api import compare

result = compare("Hello World", "Hello Python")
for line in result.lines:
    if line.type == "modified":
        print(f"परिवर्तित: {line.text}")
```

---

## SequencerAPI

**फ़ाइल:** `pentool/api/sequencer_api.py`  
**उद्देश्य:** यादृच्छिकता विश्लेषण

### क्लास विधियां

#### `analyze(tokens: list[str]) -> SequencerReport`
टोकन यादृच्छिकता का विश्लेषण करें।

**पैरामीटर:**
- `tokens` — विश्लेषण के लिए टोकन की सूची

**रिटर्न:** `SequencerReport`, जिसमें:
- `entropy` — Shannon एंट्रॉपी
- `charset_size` — पता लगाया गया वर्ण सेट आकार
- `min_length`, `max_length` — लंबाई सांख्यिकी
- `patterns` — पता लगाए गए पैटर्न

**उदाहरण:**
```python
from pentool.api.sequencer_api import Sequencer

tokens = ["abc123", "def456", "ghi789"]
report = Sequencer.analyze(tokens)
print(f"एंट्रॉपी: {report.entropy:.2f} bits")
```

---

## सामान्य पैटर्न

### Async/Await
अधिकांश API विधियां async हैं और `await` की आवश्यकता होती है:

```python
import asyncio
from pentool.api.scanner_api import ScannerAPI

async def main():
    scanner = ScannerAPI()
    findings = await scanner.scan("https://example.com")
    
asyncio.run(main())
```

### त्रुटि प्रबंधन
सभी API मानक Python अपवाद उत्पन्न करते हैं:

```python
try:
    proxy.start("127.0.0.1", 8080)
except OSError as e:
    print(f"पोर्ट पहले से उपयोग में है: {e}")
except RuntimeError as e:
    print(f"प्रॉक्सी त्रुटि: {e}")
```

### टाइप हिंट
सभी API बेहतर IDE समर्थन के लिए टाइप हिंट का उपयोग करते हैं:

```python
from pentool.api.proxy_api import ProxyAPI

def my_function(proxy: ProxyAPI) -> None:
    # IDE स्वचालित रूप से proxy विधियों को पूरा करेगा
    proxy.start("127.0.0.1", 8080)
```

---

## पूर्ण उदाहरण

```python
import asyncio
from pentool.api import ProxyAPI, ScannerAPI, TargetAPI

async def main():
    # API प्रारंभ करें
    proxy = ProxyAPI()
    scanner = ScannerAPI()
    target = TargetAPI()
    
    # दायरा कॉन्फ़िगर करें
    target.add_to_scope("example.com")
    
    # प्रॉक्सी प्रारंभ करें
    proxy.start("127.0.0.1", 8080)
    print("प्रॉक्सी पोर्ट 8080 पर शुरू किया गया")
    
    # कुछ ट्रैफ़िक की प्रतीक्षा करें...
    await asyncio.sleep(10)
    
    # इंटरसेप्ट किए गए अनुरोध प्राप्त करें
    requests = await proxy.get_requests(limit=10)
    print(f"{len(requests)} अनुरोध कैप्चर किए गए")
    
    # पहले URL को स्कैन करें
    if requests:
        url = requests[0]['url']
        findings = await scanner.scan(url)
        print(f"{len(findings)} भेद्यताएं पाई गईं")
        
        for finding in findings:
            print(f"  [{finding.severity}] {finding.title}")
    
    # प्रॉक्सी बंद करें
    proxy.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

**अधिक उदाहरणों के लिए, रिपॉजिटरी में `examples/` निर्देशिका देखें।**
