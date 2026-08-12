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
