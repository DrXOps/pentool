# PENTOOL API 契约

**版本：** 1.0  
**目的：** 为模块开发者和 SaaS 集成提供所有 API 方法的文档

---

## 目录

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

**文件：** `pentool/api/proxy_api.py`  
**目的：** HTTP 代理服务器管理

### 方法

#### `start(host: str, port: int) -> None`
启动代理服务器。

**参数：**
- `host` — 监听地址（通常是 "127.0.0.1"）
- `port` — 端口号（通常是 8080）

**异常：**
- `RuntimeError` — 如果代理已在运行
- `OSError` — 如果端口已被使用

**示例：**
```python
from pentool.api.proxy_api import ProxyAPI

proxy = ProxyAPI()
proxy.start("127.0.0.1", 8080)
```

---

#### `stop() -> None`
停止代理服务器。

**异常：**
- `RuntimeError` — 如果代理未运行

**示例：**
```python
proxy.stop()
```

---

#### `is_running` 属性
检查代理是否正在运行。

**返回：** 如果代理正在运行则为 `True`，否则为 `False`

**示例：**
```python
if proxy.is_running:
    print("Proxy is running")
```

⚠️ **重要：** 这是一个属性，调用时不带括号！

---

#### `get_requests(limit: int = 100) -> list[dict]`
获取拦截请求的历史记录。

**参数：**
- `limit` — 最大记录数

**返回：** 字典列表，包含以下字段：
- `id` (int)
- `method` (str)
- `url` (str)
- `status_code` (int)
- `timestamp` (float)
- `host` (str)
- `length` (int)

**示例：**
```python
requests = await proxy.get_requests(limit=50)
for req in requests:
    print(f"{req['method']} {req['url']}")
```

---

## ScannerAPI

**文件：** `pentool/api/scanner_api.py`  
**目的：** 漏洞扫描

### 方法

#### `async scan(url: str, checks: list[str] = None) -> list[Finding]`
对目标 URL 启动主动扫描。

**参数：**
- `url` — 目标 URL
- `checks` — 检查名称列表（None = 所有可用）

**返回：** `Finding` 对象列表

**示例：**
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
从数据库获取所有发现。

**参数：**
- `limit` — 最大发现数

**返回：** 按严重程度排序的 `Finding` 对象列表

**示例：**
```python
findings = await scanner.get_findings(limit=100)
```

---

#### `get_available_checks() -> list[str]`
获取可用漏洞检查的列表。

**返回：** 检查名称列表

**示例：**
```python
checks = scanner.get_available_checks()
print(f"可用检查: {', '.join(checks)}")
```

---

## IntruderAPI

**文件：** `pentool/api/intruder_api.py`  
**目的：** 自动化攻击和暴力破解

### 方法

#### `async attack(request: str, positions: list[int], payloads: list[str], attack_type: str = "sniper") -> int`
启动攻击。

**参数：**
- `request` — HTTP 请求模板
- `positions` — payload 插入的字节位置列表
- `payloads` — payloads 列表
- `attack_type` — 攻击类型："sniper"、"battering_ram"、"pitchfork"、"cluster_bomb"

**返回：** 攻击 ID

**示例：**
```python
from pentool.api.intruder_api import IntruderAPI

intruder = IntruderAPI()

request = """GET /api/user?id=1 HTTP/1.1
Host: example.com

"""

# 标记位置：id=§1§
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
获取攻击结果。

**参数：**
- `attack_id` — 特定攻击 ID（None = 最新）

**返回：** 结果列表

**示例：**
```python
results = intruder.get_results()
for r in results:
    print(f"Payload: {r.payload_values}, Status: {r.response_status}")
```

---

## SpiderAPI

**文件：** `pentool/api/spider_api.py`  
**目的：** Web 爬取

### 方法

#### `async crawl(base_url: str, max_depth: int = 3) -> dict`
从基础 URL 开始爬取。

**参数：**
- `base_url` — 起始 URL
- `max_depth` — 最大爬取深度

**返回：** 字典，包含：
- `urls` — 发现的 URL 列表
- `forms` — 发现的表单列表
- `endpoints` — API 端点列表

**示例：**
```python
from pentool.api.spider_api import SpiderAPI

spider = SpiderAPI()
results = await spider.crawl("https://example.com", max_depth=2)
print(f"发现 {len(results['urls'])} 个 URL")
```

---

## RepeaterAPI

**文件：** `pentool/api/repeater_api.py`  
**目的：** 手动请求发送

### 方法

#### `async send(request: str) -> dict`
发送 HTTP 请求并获取响应。

**参数：**
- `request` — 原始 HTTP 请求

**返回：** 字典，包含：
- `status` — HTTP 状态代码
- `headers` — 响应 headers 字典
- `body` — 响应 body
- `time` — 请求时间（ms）

**示例：**
```python
from pentool.api.repeater_api import RepeaterAPI

repeater = RepeaterAPI()

request = """GET / HTTP/1.1
Host: example.com

"""

response = await repeater.send(request)
print(f"状态: {response['status']}")
print(f"时间: {response['time']}ms")
```

---

## TargetAPI

**文件：** `pentool/api/target_api.py`  
**目的：** 目标范围管理

### 方法

#### `add_to_scope(host: str) -> None`
将主机添加到范围。

**参数：**
- `host` — 主机名或模式（支持通配符）

**示例：**
```python
from pentool.api.target_api import TargetAPI

target = TargetAPI()
target.add_to_scope("example.com")
target.add_to_scope("*.example.com")
```

---

#### `is_in_scope(url: str) -> bool`
检查 URL 是否在范围内。

**参数：**
- `url` — 要检查的 URL

**返回：** 如果在范围内则为 `True`

**示例：**
```python
if target.is_in_scope("https://api.example.com/users"):
    print("在范围内")
```

---

## DecoderAPI

**文件：** `pentool/api/decoder_api.py`  
**目的：** 编码/解码操作

### 函数

#### `decode_op(data: str, operation: str) -> str`
应用解码操作。

**参数：**
- `data` — 输入数据
- `operation` — 操作名称（见 `OPERATIONS`）

**返回：** 解码后的字符串

**可用操作：**
- `url_decode`, `url_encode`
- `base64_decode`, `base64_encode`
- `html_decode`, `html_encode`
- `hex_decode`, `hex_encode`
- `md5`, `sha1`, `sha256`, `sha512`
- `gzip_decompress`, `gzip_compress`
- `jwt_decode`

**示例：**
```python
from pentool.api.decoder_api import decode_op

result = decode_op("SGVsbG8gV29ybGQ=", "base64_decode")
print(result)  # "Hello World"
```

---

#### `decode_smart(data: str) -> str`
自动检测并解码。

**参数：**
- `data` — 编码的数据

**返回：** 解码后的字符串（尝试多种方法）

**示例：**
```python
from pentool.api.decoder_api import decode_smart

result = decode_smart("%48%65%6C%6C%6F")  # 自动检测 URL 编码
print(result)  # "Hello"
```

---

## ComparerAPI

**文件：** `pentool/api/comparer_api.py`  
**目的：** 文本比较

### 函数

#### `compare(text1: str, text2: str) -> DiffResult`
比较两个文本。

**参数：**
- `text1` — 第一个文本
- `text2` — 第二个文本

**返回：** `DiffResult` 对象，包含：
- `lines` — `DiffLine` 对象列表
- `stats` — 带计数的 `CompareStats`

**示例：**
```python
from pentool.api.comparer_api import compare

result = compare("Hello World", "Hello Python")
for line in result.lines:
    if line.type == "modified":
        print(f"已更改: {line.text}")
```

---

## SequencerAPI

**文件：** `pentool/api/sequencer_api.py`  
**目的：** 随机性分析

### 类方法

#### `analyze(tokens: list[str]) -> SequencerReport`
分析令牌随机性。

**参数：**
- `tokens` — 要分析的令牌列表

**返回：** `SequencerReport`，包含：
- `entropy` — Shannon 熵
- `charset_size` — 检测到的字符集大小
- `min_length`, `max_length` — 长度统计
- `patterns` — 检测到的模式

**示例：**
```python
from pentool.api.sequencer_api import Sequencer

tokens = ["abc123", "def456", "ghi789"]
report = Sequencer.analyze(tokens)
print(f"熵: {report.entropy:.2f} bits")
```

---

## 常见模式

### Async/Await
大多数 API 方法是异步的，需要 `await`：

```python
import asyncio
from pentool.api.scanner_api import ScannerAPI

async def main():
    scanner = ScannerAPI()
    findings = await scanner.scan("https://example.com")
    
asyncio.run(main())
```

### 错误处理
所有 API 都引发标准 Python 异常：

```python
try:
    proxy.start("127.0.0.1", 8080)
except OSError as e:
    print(f"端口已被使用: {e}")
except RuntimeError as e:
    print(f"代理错误: {e}")
```

### 类型提示
所有 API 都使用类型提示以获得更好的 IDE 支持：

```python
from pentool.api.proxy_api import ProxyAPI

def my_function(proxy: ProxyAPI) -> None:
    # IDE 将自动完成 proxy 方法
    proxy.start("127.0.0.1", 8080)
```

---

## 完整示例

```python
import asyncio
from pentool.api import ProxyAPI, ScannerAPI, TargetAPI

async def main():
    # 初始化 API
    proxy = ProxyAPI()
    scanner = ScannerAPI()
    target = TargetAPI()
    
    # 配置范围
    target.add_to_scope("example.com")
    
    # 启动代理
    proxy.start("127.0.0.1", 8080)
    print("代理已在端口 8080 上启动")
    
    # 等待一些流量...
    await asyncio.sleep(10)
    
    # 获取拦截的请求
    requests = await proxy.get_requests(limit=10)
    print(f"捕获了 {len(requests)} 个请求")
    
    # 扫描第一个 URL
    if requests:
        url = requests[0]['url']
        findings = await scanner.scan(url)
        print(f"发现 {len(findings)} 个漏洞")
        
        for finding in findings:
            print(f"  [{finding.severity}] {finding.title}")
    
    # 停止代理
    proxy.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

**更多示例，请参阅仓库中的 `examples/` 目录。**
