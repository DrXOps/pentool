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

### 方法 1：PyPI（推荐）

```bash
# 创建虚拟环境（推荐）
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# 或
pentool-env\Scripts\activate  # Windows

# 安装
pip install pentool

# 验证
pentool --version
```

### 方法 2：从源代码安装

```bash
# 克隆仓库
git clone https://github.com/DrXOps/pentool.git
cd pentool

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 以可编辑模式安装
pip install -e ".[dev]"

# 验证
pentool --version
```

### 方法 3：pipx（隔离安装）

```bash
# 安装 pipx
pip install pipx

# 安装 pentool
pipx install pentool

# 运行
pentool
```

---

## 平台特定说明

### Linux (Ubuntu/Debian)

```bash
# 安装系统依赖
sudo apt update
sudo apt install python3 python3-pip python3-venv

# 安装 pentool
pip3 install pentool

# 运行
pentool
```

### macOS

```bash
# 安装 Homebrew（如果未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python
brew install python@3.11

# 安装 pentool
pip3 install pentool

# 运行
pentool
```

### Windows

```powershell
# 从 python.org 安装 Python
# https://www.python.org/downloads/

# 安装 pentool
pip install pentool

# 运行
pentool
```

---

## 安装 CA 证书

要拦截 HTTPS 流量，需要安装 Pentool CA 证书。

### Linux (Ubuntu/Debian)

```bash
# 复制证书
sudo mkdir -p /usr/local/share/ca-certificates/pentool
sudo cp ~/.config/pentool/ca.crt /usr/local/share/ca-certificates/pentool/

# 更新证书存储
sudo update-ca-certificates
```

### macOS

```bash
# 添加到 Keychain
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.config/pentool/ca.crt
```

### Windows

```powershell
# 导入证书
certutil -addstore -f "ROOT" %USERPROFILE%\.config\pentool\ca.crt
```

### 浏览器

**Firefox:**
1. Settings → Privacy & Security → Certificates → View Certificates
2. Import → 选择 `~/.config/pentool/ca.crt`
3. 勾选 "Trust this CA to identify websites"

**Chrome/Chromium:**
1. Settings → Privacy and security → Security → Manage certificates
2. Authorities → Import
3. 选择 `~/.config/pentool/ca.crt`

---

## 验证安装

```bash
# 检查版本
pentool --version

# 启动 TUI
pentool

# 查看选项
pentool --help
```

---

## 故障排除

### 找不到 Python

```bash
# Linux/macOS
which python3
python3 --version

# Windows
where python
python --version
```

### 包安装错误

```bash
# 升级 pip
pip install --upgrade pip

# 无缓存安装
pip install pentool --no-cache-dir
```

### 权限问题

```bash
# Linux/macOS - 使用虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install pentool
```

---

## 下一步

- [快速入门](QUICKSTART.md) — 5 分钟开始使用
- [用户指南](USER_GUIDE.md) — 完整文档
- [GitHub](https://github.com/DrXOps/pentool) — 源代码

---

**需要帮助？** 在 GitHub 上创建 issue：https://github.com/DrXOps/pentool/issues
