# 📦 Pentool 安装指南

所有平台的完整安装说明。

---

## 系统要求

### 最低要求
- Python 3.10 或更高版本
- 512 MB RAM
- 100 MB 磁盘空间
- Linux、macOS 或 Windows

### 推荐配置
- Python 3.11+
- 2 GB RAM
- 500 MB 磁盘空间（包含历史记录）
- 支持 Unicode 的现代终端

---

## 安装方法

### 方法 1：uv tool（推荐）

[uv](https://docs.astral.sh/uv/) 将 pentool 安装到隔离环境中 ——
无需手动创建虚拟环境，不会与系统 Python 冲突。

```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# Windows: winget install --id=astral-sh.uv -e

# 安装 pentool
uv tool install pentool

# 验证
pentool --version
```

### 方法 2：pip（备选）

```bash
# 创建虚拟环境（推荐）
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# 或
pentool-env\Scripts\activate     # Windows

# 安装
pip install pentool

# 验证
pentool --version
```

### 方法 3：从源代码安装（开发者）

```bash
# 克隆仓库
git clone https://github.com/DrXOps/pentool.git
cd pentool

# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装所有依赖（uv 自动创建 .venv）
uv sync

# 验证
uv run pentool --version
```

---

## 平台特定说明

### Linux (Ubuntu/Debian)

```bash
# 安装系统 Python（如有需要）
sudo apt update
sudo apt install python3

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 pentool
uv tool install pentool

# 运行
pentool
```

### macOS

```bash
# 安装 Homebrew（如果未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 通过 Homebrew 安装 uv
brew install uv
# 或直接安装：
# curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 pentool
uv tool install pentool

# 运行
pentool
```

### Windows

```powershell
# 安装 uv
winget install --id=astral-sh.uv -e
# 或通过 PowerShell：
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装 pentool
uv tool install pentool

# 运行
pentool
```

> **Windows 用户：TUI 需要 WSL2。** 上面的 PowerShell 命令足以运行 CLI 和无界面扫描
> （`--headless`）。交互界面（代理、ANSI 边框、钩子）请使用 WSL2：见下方
> [在 Windows 上通过 WSL2 运行](#wsl2-windows)。

---

<a id="wsl2-windows"></a>
## 在 Windows 上通过 WSL2 运行

TUI 需要 POSIX 终端：代理、钩子和 ANSI 制表符界面都依赖 UTF-8 locale。在 WSL2（Ubuntu）
中，一切与 Linux 相同。命令请在 **WSL 终端**中执行，而不是 PowerShell。

### 1. 安装 WSL2（以管理员身份运行 PowerShell）

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
wsl --update
wsl --status
```

### 2. Locale 与 UTF-8 —— 边框字符能否正常显示取决于此

```bash
sudo apt update
sudo apt install -y locales
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8
exec bash
echo $LANG    # 应输出 en_US.UTF-8，而不是 C 或 POSIX
```

`LANG=C`、`POSIX` 或空值，是边框变成 `?` 以及西里尔字母出现乱码的常见原因。

### 3. 包含所需字形的字体

**Windows 端**（用于 Windows Terminal）：安装 **JetBrains Mono Nerd Font** 或
**Cascadia Code NF**，然后在终端配置中选择它。表情符号（`▶ ✖ 💥 🧭`）由
**Segoe UI Emoji** 作为后备字体提供。

**WSL 端**（用于 Kitty）：

```bash
sudo apt install -y unzip curl fonts-noto-color-emoji
mkdir -p ~/.local/share/fonts && cd ~/.local/share/fonts
curl -LO https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
unzip -o JetBrainsMono.zip && fc-cache -fv
```

### 4. Kitty（可选 —— Windows Terminal 也可以）

```bash
sudo apt install -y kitty
```

`~/.config/kitty/kitty.conf`：

```conf
font_family JetBrainsMono Nerd Font
font_size 12.0
# 制表符
symbol_map U+2500-U+257F JetBrainsMono Nerd Font
# 表情符号
symbol_map U+1F300-U+1FAFF Noto Color Emoji
# WSLg 下更平滑的默认值
sync_to_monitor no
repaint_delay 8
```

启动：`kitty pentool`，或从 Windows：`wsl.exe -e kitty pentool`。

如果部分面板图标无法显示，请在 **Settings → Interface → Panel icons** 中切换图标集
（`unicode` / `ascii` / `emoji`）。

### 5. 验证字符是否正常

```bash
python3 -c "print('┌────┬────┐\n│ OK │ 42 │\n└────┴────┘')"
printf '█ ▓ ▒ ░  →  ✔ ✖ ⚠\n'
infocmp -1 | head -3    # TERM 应为 *-256color，而不是 dumb
```

### 6. 如果仍然显示异常

| 现象 | 原因 | 处理 |
|---|---|---|
| 边框显示为 `?` 或 `+---+` | 没有 UTF-8 locale | 第 2 步，`export LANG=en_US.UTF-8` |
| 西里尔字母乱码 | `LANG=C` / `POSIX` | 第 2 步 |
| 边框过宽、布局错位 | 字体缺少制表符字形 | 第 3 步 |
| 图标显示为方块 | 缺少 emoji/Nerd 字体 | 第 3 步，或改用 `ascii` 图标集 |
| TUI 无法启动 | `TERM=dumb` | `export TERM=xterm-256color` |
| 没有颜色 | 8 色终端 | Windows Terminal 或 Kitty |

---

## 开发者安装

```bash
git clone https://github.com/DrXOps/pentool.git
cd pentool

# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目 + 所有开发工具（自动创建 .venv）
uv sync

# 安装 pre-commit 钩子
uv run pre-commit install

# 运行测试
uv run pytest tests/unit/

# 带覆盖率运行
uv run pytest tests/ --cov=pentool --cov-report=html
```

---

## 故障排除

### 找不到 pentool 命令

```bash
# Linux/macOS — 添加到 ~/.bashrc 或 ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# 或让 uv 自动配置 PATH：
uv tool update-shell
```

### 包安装错误

```bash
uv tool install pentool --no-cache
# 或使用 pip：
pip install pentool --no-cache-dir
```

---

## 更新

```bash
# uv
uv tool upgrade pentool

# pip
pip install --upgrade pentool
```

---

## 卸载

```bash
# uv
uv tool uninstall pentool

# pip
pip uninstall pentool

# 删除所有数据
rm -rf ~/.config/pentool
rm -rf ~/.local/share/pentool
```

---

## 安装 CA 证书

要拦截 HTTPS 流量，需要安装 Pentool CA 证书。

### Linux (Ubuntu/Debian)

```bash
sudo mkdir -p /usr/local/share/ca-certificates/pentool
sudo cp ~/.config/pentool/ca.crt /usr/local/share/ca-certificates/pentool/
sudo update-ca-certificates
```

### macOS

```bash
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.config/pentool/ca.crt
```

### Windows

```powershell
certutil -addstore -f "ROOT" %USERPROFILE%\.config\pentool\ca.crt
```

---

## 下一步

- [快速开始](QUICKSTART.md) — 5 分钟入门
- [用户手册](USER_GUIDE.md) — 完整文档
- [GitHub](https://github.com/DrXOps/pentool) — 源代码

---

**需要帮助？** 在 GitHub 上提交 issue：https://github.com/DrXOps/pentool/issues
