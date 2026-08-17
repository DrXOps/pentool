# 🚀 Pentool 快速入门指南

5 分钟开始使用 Pentool！

---

## 安装

```bash
# 从 PyPI 安装（推荐）
uv tool install pentool

# 备选：pip
# pip install pentool

# 或从源代码
git clone https://github.com/DrXOps/pentool.git
cd pentool
uv sync
```

---

## 首次启动

```bash
pentool
```

您将看到带有 Dashboard 屏幕的 TUI 界面。

**导航：**
- `Tab` / `Shift+Tab` — 在小部件之间切换
- `Ctrl+X` — 打开菜单
- `Ctrl+Q` — 退出

---

## 1. 配置浏览器代理

**步骤 1：** 启动 Pentool Proxy
- 按 `Ctrl+X` → 选择 "Proxy"
- 点击 "○ Proxy" 启动它
- 默认：`127.0.0.1:8080`（可在 Settings 中配置）

**步骤 2：** 配置浏览器
- Firefox：设置 → 网络 → 手动代理配置
- 设置 HTTP 代理：`127.0.0.1` 端口 `8080`
- 启用 "同时用于 HTTPS"

**步骤 3：** 安装 CA 证书（用于 HTTPS）
- Pentool 在代理首次启动时会在本地生成 CA
  （`~/.config/pentool/certs/ca.crt`）——证书不会离开你的机器
- 在 Proxy 界面点击 "Install CA cert"（或 **Settings → Proxy →
  Install CA cert**）——会打开一个对话框，显示证书路径以及 Firefox、
  Chrome 和系统级安装的分步说明
- Firefox：`about:preferences#privacy` → 证书 → 查看证书 →
  **证书颁发机构** 标签页 → 导入 → 选择 `ca.crt` →
  勾选 "信任由此证书颁发机构颁发的网站证书"

---

## 2. 拦截 HTTP 流量

**在浏览器中：**
- 打开任何网站
- 流量将出现在 Pentool → Proxy → HTTP History

**拦截（Intercept）：**
- 在 Proxy 中点击 "Intercept"
- 修改请求
- 点击 "Forward" 或 "Drop"

---

## 3. 重放请求（Repeater）

1. 在 Proxy History 中：右键点击请求
2. 选择 "Send to Repeater"
3. 在 Repeater 中：修改参数
4. 点击 "Send"（`F5`）
5. 查看响应

---

## 4. 暴力破解参数（Intruder）

1. 从 Proxy 发送到 Intruder
2. 选择参数 → "Mark Param"
3. 选择攻击类型（Sniper、Battering Ram、Pitchfork）
4. 加载字典或输入 payloads
5. 点击 "Start Attack"（`F5`）

---

## 5. 扫描漏洞（Scanner）

**被动扫描：**
- Proxy 工作时自动启用
- 分析所有流量以查找漏洞

**主动扫描：**
1. 进入 Scanner（`Shift+S`）
2. 输入目标 URL
3. 选择检查类型
4. 点击 "Start Scan"（`F5`）

**检查内容：**
- XSS（反射型、DOM、存储型）
- SQL 注入
- SSTI（模板注入）
- LFI/路径遍历
- RCE（命令注入）
- SSRF、XXE、CORS
- JWT、OAuth 漏洞
- 等等...

---

## 6. 实用工具

### Decoder
- `Shift+D` → 打开 Decoder
- 支持：Base64、URL、HTML、Hex、Gzip、JWT
- Smart Decode：自动检测编码

### Comparer
- `Shift+C` → 打开 Comparer
- 粘贴两个文本
- 获取带高亮的差异

### Spider
- `Shift+W` → 打开 Spider
- 输入基础 URL
- 自动爬取网站

---

## 7. 快捷键

### 全局
- `Ctrl+Q` — 退出
- `Ctrl+N` — 新建项目
- `Ctrl+O` — 打开项目
- `Ctrl+S` — 保存项目

### 模块导航（Shift+字母）
- `Shift+H` — Dashboard
- `Shift+P` — Proxy
- `Shift+R` — Repeater
- `Shift+I` — Intruder
- `Shift+S` — Scanner
- `Shift+T` — Target
- `Shift+D` — Decoder
- `Shift+C` — Comparer
- `Shift+Q` — Sequencer
- `Shift+W` — Spider
- `Shift+E` — Extensions
- `Shift+X` — Terminal

### 在模块中
- `F5` — 执行操作（Send、Start Scan 等）
- `F6` — 停止
- `Ctrl+F` — 搜索/过滤
- `m` — 上下文菜单

---

## 8. 典型场景

### Web 应用测试
1. 启动 Proxy
2. 配置浏览器
3. 使用应用程序
4. 在 Proxy History 中分析流量
5. 将感兴趣的请求发送到 Repeater/Intruder

### API 测试
1. 发送到 Repeater
2. 修改 JSON body
3. 测试不同参数
4. 使用 Intruder 进行暴力破解

### 漏洞发现
1. 启用被动扫描
2. 使用应用程序
3. 在 Dashboard 中检查发现
4. 对目标端点运行主动扫描

---

## 9. 项目

**保存：**
- `Ctrl+S` — 保存为 .db（SQLite）
- `Ctrl+Shift+S` — 导出为 JSON

**加载：**
- `Ctrl+O` — 打开 .db 项目
- `Ctrl+Shift+O` — 从 JSON 导入

**项目包括：**
- Proxy 历史
- Scanner 发现
- Intruder 结果
- Target 站点地图
- Match/Replace 规则
- Scope 设置

---

## 10. 设置

`Ctrl+Comma` 或 `Shift+Settings`

**界面：**
- 主题（Dark/Light）
- UI 模式（Basic/Advanced）

**Proxy：**
- 监听 host/port
- 上游代理
- CA 证书

**网络：**
- User-Agent
- 超时
- SSL 验证
- Collaborator URL

**许可证：**
- 激活 PRO 许可证
- 查看可用功能

---

## 下一步

- [完整指南](USER_GUIDE.md) — 所有功能的详细文档
- [安装](INSTALLATION.md) — 扩展安装说明
- [GitHub](https://github.com/DrXOps/pentool) — 源代码、issues、discussions

---

## 需要帮助？

- **文档：** 仓库中的 `docs/`
- **Issues：** https://github.com/DrXOps/pentool/issues
- **Discussions：** https://github.com/DrXOps/pentool/discussions

---

**祝测试愉快！🔒**
