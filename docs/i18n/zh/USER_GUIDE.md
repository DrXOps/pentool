# 📖 Pentool 用户指南

Web 安全测试的完整 Pentool 使用指南。

---

## 目录

1. [入门](#入门)
2. [Proxy 模块](#proxy-模块)
3. [Repeater 模块](#repeater-模块)
4. [Intruder 模块](#intruder-模块)
5. [Scanner 模块](#scanner-模块)
6. [Decoder 模块](#decoder-模块)
7. [Comparer 模块](#comparer-模块)
8. [Spider 模块](#spider-模块)
9. [WebSocket 模块](#websocket-模块)
10. [HTTPQL 过滤](#httpql-过滤)
11. [快捷键](#快捷键)
12. [技巧与窍门](#技巧与窍门)

---

## 入门

### 首次启动

```bash
pentool
```

主界面包括：
- **顶部栏** — 导航菜单和状态
- **主区域** — 当前模块屏幕
- **状态栏** — 连接状态、快捷键

### 导航

- `Ctrl+X` — 打开菜单
- `Tab` / `Shift+Tab` — 在小部件之间切换
- `Ctrl+Q` — 退出
- 方向键 — 在列表中导航

---

## Proxy 模块

Proxy 拦截浏览器和目标之间的 HTTP/HTTPS 流量。

### 启动 Proxy

1. 进入 Proxy（`Shift+P`）
2. 点击 **Start Proxy** 按钮
3. 默认监听 `127.0.0.1:8888`

### 配置浏览器

**Firefox:**
- Settings → Network → Manual proxy configuration
- HTTP Proxy: `127.0.0.1` Port: `8888`
- 启用 "Also use this proxy for HTTPS"

**Chrome/Chromium:**
- 使用扩展（FoxyProxy）或系统设置

### HTTP History

**HTTP History** 标签显示所有拦截的请求：

- **ID** — 唯一请求编号
- **Host** — 目标主机
- **Method** — HTTP 方法（GET、POST 等）
- **URL** — 请求路径
- **Status** — 响应代码
- **Size** — 响应大小
- **Time** — 执行时间

**操作：**
- 点击请求 → 查看详情
- `Ctrl+Click` 或 `m` → 上下文菜单
- `Ctrl+F` → 过滤/搜索

### Intercept（拦截）

**Intercept** 标签允许即时修改请求：

1. 点击 **Intercept** 按钮（激活拦截）
2. 在浏览器中执行请求
3. 请求将出现在 Intercept 编辑器中
4. 修改请求
5. 点击 **Forward**（发送）或 **Drop**（丢弃）

**快捷键：**
- `Ctrl+F` — Forward 当前请求
- `Ctrl+D` — Drop 当前请求
- `Ctrl+I` — 切换 Intercept 开/关

### Match & Replace

根据规则自动修改请求：

1. 在 Proxy 中点击 **M/R** 按钮
2. 添加规则：
   - **Match:** 正则表达式
   - **Replace:** 替换字符串
   - **Target:** Request/Response/Both
   - **Scope:** All/In-scope only
3. 启用规则

**示例：**
- 更改 User-Agent: `User-Agent: .*` → `User-Agent: CustomBot/1.0`
- 添加 header: `$` → `X-Custom: value\r\n`（在 headers 末尾）

### Scope

定义测试范围：

1. 点击 **Scope** 按钮
2. 将主机添加到 scope
3. 启用 "In-scope only" 过滤器

**优势：**
- 仅过滤目标主机的历史记录
- 被动扫描仅在 scope 上工作
- Match/Replace 仅应用于 scope

---

## Repeater 模块

Repeater 允许重复发送和修改 HTTP 请求。

### 将请求发送到 Repeater

**从 Proxy：**
1. 在 HTTP History 中选择请求
2. `Ctrl+Click` 或 `m` → **Send to Repeater**

**手动创建：**
1. 进入 Repeater（`Shift+R`）
2. 手动输入 HTTP 请求

### 发送请求

1. 在左侧面板中修改请求
2. 点击 **Send**（`F5`）
3. 在右侧面板中查看响应

### 标签

Repeater 支持多个标签：

- `Ctrl+T` — 新标签
- `Ctrl+W` — 关闭标签
- 双击标题 — 重命名

### 历史

Repeater 在每个标签中保存请求历史：

- **History** 按钮 → 所有已发送请求的列表
- 点击请求 → 加载它

---

## Intruder 模块

Intruder 自动化 Web 应用程序攻击。

### 攻击类型

1. **Sniper** — 一个 payload set，逐个位置遍历
2. **Battering Ram** — 一个 payload 同时到所有位置
3. **Pitchfork** — 多个 payload sets，同步迭代
4. **Cluster Bomb** — 多个 payload sets，所有组合

### 配置攻击

1. **加载请求：**
   - 从 Proxy/Repeater 发送到 Intruder
   - 或手动输入

2. **标记位置：**
   - 选择参数
   - 点击 **Mark Param** 或 `Ctrl+M`
   - 位置将标记为 `§value§`

3. **加载 payloads：**
   - **Simple List** — 手动输入的列表
   - **File** — 加载字典
   - **Numbers** — 数字范围
   - **Brute Force** — 字符的所有组合

4. **配置选项：**
   - **Threads** — 线程数（1-50）
   - **Delay** — 请求之间的延迟（ms）
   - **Timeout** — 请求超时（s）

5. **启动攻击：**
   - 点击 **Start Attack**（`F5`）

### 分析结果

结果表显示：
- **#** — 请求编号
- **Payload** — 使用的 payload
- **Status** — 响应代码
- **Length** — 响应大小
- **Time** — 执行时间

**排序：**
- 点击列标题
- 查找异常（不同的 Length/Status/Time）

**Grep/Extract：**
- 配置正则表达式从响应中提取数据

---

## Scanner 模块

Scanner 自动发现漏洞。

### 扫描类型

**被动扫描：**
- 通过 Proxy 分析流量
- 自动启用
- 查找：信息泄露、不安全的 headers、没有 Secure/HttpOnly 的 cookies

**主动扫描：**
- 发送特殊请求以检查漏洞
- 手动启动特定目标

### 启动主动扫描

1. 进入 Scanner（`Shift+S`）
2. 输入目标 **Base URL**
3. 选择**检查类型：**
   - XSS（反射型、DOM、存储型）
   - SQL Injection
   - SSTI（模板注入）
   - LFI/路径遍历
   - RCE（命令注入）
   - SSRF、XXE、CORS
   - JWT、OAuth 漏洞
4. 配置**参数：**
   - **Depth** — 爬取深度（1-10）
   - **Max Pages** — 最大页面数
   - **Threads** — 线程数
5. 点击 **Start Scan**（`F5`）

### 查看发现

发现表显示：
- **Severity** — 严重程度（Critical、High、Medium、Low、Info）
- **Type** — 漏洞类型
- **URL** — 易受攻击的端点
- **Parameter** — 易受攻击的参数

**详情：**
- 点击发现 → 详细信息
- Proof-of-Concept payload
- 修复建议

### PRO 功能（许可证）

- **WAF Detection** — 自动检测 WAF
- **Smart Payloads** — 适应 WAF 绕过的 payloads
- **Advanced Checks:** HTTP Smuggling、Deserialization、IDOR
- **AI Analysis** — GPT-4 结果分析

---

## Decoder 模块

Decoder 以各种格式编码/解码数据。

### 支持的操作

**编码：**
- URL encode
- HTML encode
- Base64 encode
- Hex encode

**解码：**
- URL decode
- HTML decode
- Base64 decode
- Hex decode

**哈希：**
- MD5、SHA-1、SHA-256、SHA-512

**压缩：**
- Gzip compress/decompress

**特殊：**
- JWT decode
- Unicode escape/unescape

### Smart Decode

点击 **Smart Decode** — 自动检测和解码：

- 尝试多种解码方法
- 显示最可能格式的结果

### Chain Mode

按顺序应用多个操作：

1. 输入数据
2. 选择操作 1 → Apply
3. 选择操作 2 → Apply
4. 每个操作的结果成为下一个的输入

---

## Comparer 模块

Comparer 比较两个文本并显示差异。

### 使用

1. 进入 Comparer（`Shift+C`）
2. 将 **Text 1** 粘贴到左侧面板
3. 将 **Text 2** 粘贴到右侧面板
4. 点击 **Compare**（`F5`）

### 比较模式

- **Words** — 逐词比较
- **Lines** — 逐行比较（默认）
- **Bytes** — 逐字节比较

### 结果

- 绿色 — 仅在 Text 1 中的行
- 红色 — 仅在 Text 2 中的行
- 白色 — 相同的行

**统计：**
- Identical lines — 相同的行
- Modified lines — 修改的行
- Added lines — 添加的行

---

## Spider 模块

Spider 自动爬取 Web 应用程序并构建地图。

### 启动 Spider

1. 进入 Spider（`Shift+W`）
2. 输入 **Base URL**
3. 配置参数：
   - **Max Depth** — 最大爬取深度
   - **Max Pages** — 爬取的最大页面数
   - **Threads** — 线程数
4. 点击 **Start**（`F5`）

### 结果

Spider 收集：
- **Pages** — 发现的页面
- **Forms** — 找到的表单
- **Endpoints** — API 端点
- **Parameters** — 请求参数

**操作：**
- 找到的 URL 发送到 Target sitemap
- 可以将结果发送到 Scanner 进行检查

---

## WebSocket 模块

拦截和修改 WebSocket 连接。

### WS History

Proxy 中的 **WS History** 标签显示：
- WebSocket handshake 请求
- 发送/接收的帧

### 拦截 WS

（开发中 — 已有基本支持）

---

## HTTPQL 过滤

HTTPQL — 用于过滤 HTTP 历史的强大查询语言。

### 基本语法

```
field operator value
```

### 支持的字段

- `method` — HTTP 方法
- `host` — 主机
- `path` — URL 路径
- `status` — 状态代码
- `length` — 响应大小
- `time` — 执行时间（ms）

### 运算符

- `=` — 等于
- `!=` — 不等于
- `>`, `<`, `>=`, `<=` — 比较（用于数字）
- `~` — 正则表达式
- `contains` — 包含子字符串

### 示例

```
# 所有 POST 请求
method = POST

# 4xx/5xx 错误
status >= 400

# 慢请求（>1s）
time > 1000

# 特定主机
host = example.com

# 路径的正则表达式
path ~ ^/api/

# 组合条件
method = POST AND status = 200

# OR 条件
status = 404 OR status = 500
```

---

## 快捷键

### 全局

| 键 | 操作 |
|---------|----------|
| `Ctrl+Q` | 退出 |
| `Ctrl+N` | 新建项目 |
| `Ctrl+O` | 打开项目 |
| `Ctrl+S` | 保存项目（.db） |
| `Ctrl+Shift+S` | 导出为 JSON |
| `Ctrl+Comma` | 设置 |

### 模块导航（Shift+字母）

| 键 | 模块 |
|---------|--------|
| `Shift+H` | Dashboard |
| `Shift+P` | Proxy |
| `Shift+R` | Repeater |
| `Shift+I` | Intruder |
| `Shift+S` | Scanner |
| `Shift+T` | Target |
| `Shift+D` | Decoder |
| `Shift+C` | Comparer |
| `Shift+Q` | Sequencer |
| `Shift+W` | Spider |
| `Shift+E` | Extensions |
| `Shift+X` | Terminal |

### 在模块中

| 键 | 操作 |
|---------|----------|
| `F5` | 执行（Send、Start 等） |
| `F6` | 停止 |
| `Ctrl+F` | 过滤/搜索 |
| `Ctrl+T` | 新标签 |
| `Ctrl+W` | 关闭标签 |
| `Ctrl+Click` | 上下文菜单 |
| `m` | 上下文菜单 |
| `Ctrl+C` | 复制 |
| `Ctrl+V` | 粘贴 |
| `Ctrl+A` | 全选 |

---

## 技巧与窍门

### 1. 快速导航

- 使用 `Shift+字母` 在模块之间切换
- `Tab`/`Shift+Tab` 在模块内导航
- 上下文菜单（`m` 或 `Ctrl+Click`）快速访问

### 2. 有效使用 Proxy

- 配置 Scope 以过滤非目标流量
- 使用 Match & Replace 进行自动修改
- 启用被动扫描进行后台分析

### 3. Repeater 技巧

- 为不同端点创建单独的标签
- 使用历史跟踪更改
- 复制 curl 命令以在脚本中使用

### 4. Intruder 优化

- 从少量线程开始（5-10）
- 对于大型字典使用 Turbo Mode（PRO）
- 按 Length 排序结果以识别异常

### 5. Scanner 配置

- 对所有流量启动被动扫描
- 对特定端点运行主动扫描
- 手动检查发现（避免误报）

### 6. 项目

- 定期保存项目（`Ctrl+S`）
- 使用 .db 进行快速工作，使用 JSON 进行交换
- 项目包括所有历史和结果

### 7. 性能

- 关闭 Repeater/Intruder 中不需要的标签
- 定期清理 Proxy history
- 使用过滤器处理大型数据集

---

## 故障排除

### Proxy 不拦截 HTTPS

- 检查 CA 证书是否已安装
- 在 Firefox 中：确保证书可信
- 检查浏览器中的代理设置

### 界面卡顿

- 关闭不需要的模块
- 清除历史记录
- 减少 Intruder/Scanner 中的线程数

### Scanner 未找到漏洞

- 检查目标是否在 Scope 中
- 确保选择了所需的检查类型
- 某些漏洞需要 PRO 许可证

---

## 其他资源

- [GitHub Repository](https://github.com/docxqwerty/pentool)
- [Issue Tracker](https://github.com/docxqwerty/pentool/issues)
- [Discussions](https://github.com/docxqwerty/pentool/discussions)

---

**需要帮助？** 在 GitHub 上创建 issue 或查看现有 discussions。
