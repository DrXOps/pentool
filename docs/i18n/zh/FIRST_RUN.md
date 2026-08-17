# 🚀 首次运行 — 证书与首次拦截

从 `uv tool install pentool` 到看到第一个被拦截的 HTTPS 请求的最简指南。完整内容请参阅
[快速开始指南](QUICKSTART.md) 和 [用户手册](USER_GUIDE.md)。

> ⚠️ **请使用现代终端模拟器。** Pentool 的 TUI 依赖鼠标支持、真彩色和现代渲染
> （基于 Textual 框架）。Windows 的 `cmd.exe` 和旧版/传统终端会显示异常。
> 推荐使用：**Windows Terminal**、**iTerm2**（macOS）、**GNOME
> Terminal/Kitty/Alacritty/WezTerm**（Linux）。在 Windows 上，建议在
> **WSL** 中运行 Pentool 以获得最佳体验。

---

## 1. 安装并启动

```bash
uv tool install pentool   # 推荐
# 或: pip install pentool
pentool
```

你将看到 Dashboard 界面。

## 2. 启动代理

1. 切换到 **Proxy** 模块（`Ctrl+X` → Proxy，或 `Shift+P`）
2. 点击 **"○ Proxy"** 启动代理——按钮会变为 **"● Proxy :8080"**
   （默认地址/端口为 `127.0.0.1:8080`，可在设置中修改）

## 3. 下载并安装 CA 证书

代理首次启动时，Pentool 会在本地生成一个证书颁发机构（CA），以便解密 HTTPS
流量（与 Burp/mitmproxy 相同的方式）。所有内容都在本地生成，不会离开你的机器
——CA 位于 `~/.config/pentool/certs/ca.crt`。

1. 在 Proxy 界面点击 **"Install CA cert"**（或从
   **Settings → Proxy → Install CA cert** 打开）——会弹出一个对话框，显示证书
   路径以及 Firefox、Chrome 和系统级安装（Ubuntu/Debian、Fedora/RHEL）的
   分步说明。
2. 按照你浏览器对应的说明操作：
   - **Firefox：** 打开 `about:preferences#privacy` → 证书 → 查看证书 →
     **证书颁发机构** 标签页（不是"您的证书"）→ 导入 → 选择 `ca.crt` →
     勾选"信任此 CA 标识网站" → 重启 Firefox。
   - **Chrome/Chromium：** 打开 `chrome://settings/certificates` → 证书颁发
     机构 → 导入 → 选择 `ca.crt` → 勾选"信任此证书标识网站" → 重启 Chrome。
   - **系统级（Linux）：** 对话框中会直接显示适用于你所用发行版的命令。
3. **在浏览器中配置代理**，指向 Pentool：
   - HTTP/HTTPS 代理：`127.0.0.1`，端口 `8080`（或你设置的其他端口）
   - Firefox：设置 → 网络设置 → 手动配置代理
   - Chrome：使用 `--proxy-server="127.0.0.1:8080"` 启动，或使用系统级代理
     设置，或 FoxyProxy 等扩展

## 4. 拦截你的第一个请求

1. 在 Proxy 界面开启 **"○ Intercept"**
2. 在已配置代理的浏览器中访问任意 HTTPS 网站
3. 请求会在 Pentool 的 **Intercept** 标签页中暂停——查看/编辑后点击
   **Forward**（转发）或 **Drop**（丢弃）
4. 再次关闭 Intercept，让流量正常通过——它会持续记录在 **HTTP History** 中

至此，你已经可以捕获流量，并将请求发送到 **Repeater**、**Intruder**，
或对其运行 **Scanner**。

---

**下一步：** [快速开始指南](QUICKSTART.md) · [用户手册](USER_GUIDE.md)
