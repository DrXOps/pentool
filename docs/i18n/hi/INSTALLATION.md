# 📦 Pentool इंस्टॉलेशन गाइड

सभी प्लेटफॉर्म के लिए पूर्ण इंस्टॉलेशन निर्देश।

---

## सिस्टम आवश्यकताएं

### न्यूनतम
- Python 3.10 या उच्चतर
- 512 MB RAM
- 100 MB डिस्क स्पेस
- Linux, macOS या Windows

### अनुशंसित
- Python 3.11+
- 2 GB RAM
- 500 MB डिस्क स्पेस (इतिहास के साथ)
- Unicode समर्थन के साथ आधुनिक टर्मिनल

---

## इंस्टॉलेशन विधियां

### विधि 1: uv tool (अनुशंसित)

[uv](https://docs.astral.sh/uv/) pentool को एक अलग (isolated) वातावरण में
इंस्टॉल करता है — कोई venv बनाने की ज़रूरत नहीं, सिस्टम Python से कोई टकराव नहीं।

```bash
# uv इंस्टॉल करें (अगर पहले से नहीं है)
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# Windows: winget install --id=astral-sh.uv -e

# pentool इंस्टॉल करें
uv tool install pentool

# सत्यापित करें
pentool --version
```

### विधि 2: pip (वैकल्पिक)

```bash
# वर्चुअल एनवायरनमेंट बनाएं (अनुशंसित)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# या
pentool-env\Scripts\activate     # Windows

# इंस्टॉल करें
pip install pentool

# सत्यापित करें
pentool --version
```

### विधि 3: स्रोत से (विकास के लिए)

```bash
# रिपॉजिटरी क्लोन करें
git clone https://github.com/DrXOps/pentool.git
cd pentool

# uv इंस्टॉल करें (अगर पहले से नहीं है)
curl -LsSf https://astral.sh/uv/install.sh | sh

# सभी निर्भरताएं इंस्टॉल करें (uv स्वचालित रूप से .venv बनाता है)
uv sync

# सत्यापित करें
uv run pentool --version
```

---

## प्लेटफॉर्म-विशिष्ट निर्देश

### Linux (Ubuntu/Debian)

```bash
# Python इंस्टॉल करें (यदि आवश्यक हो)
sudo apt update
sudo apt install python3

# uv इंस्टॉल करें
curl -LsSf https://astral.sh/uv/install.sh | sh

# pentool इंस्टॉल करें
uv tool install pentool

# चलाएं
pentool
```

### macOS

```bash
# Homebrew इंस्टॉल करें (यदि नहीं है)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Homebrew के ज़रिए uv इंस्टॉल करें
brew install uv
# या सीधे:
# curl -LsSf https://astral.sh/uv/install.sh | sh

# pentool इंस्टॉल करें
uv tool install pentool

# चलाएं
pentool
```

### Windows

```powershell
# uv इंस्टॉल करें
winget install --id=astral-sh.uv -e
# या PowerShell से:
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# pentool इंस्टॉल करें
uv tool install pentool

# चलाएं
pentool
```

---

## डेवलपमेंट इंस्टॉलेशन

```bash
git clone https://github.com/DrXOps/pentool.git
cd pentool

# uv इंस्टॉल करें (अगर पहले से नहीं है)
curl -LsSf https://astral.sh/uv/install.sh | sh

# प्रोजेक्ट + सभी dev टूल्स इंस्टॉल करें (.venv स्वचालित बनता है)
uv sync

# pre-commit हुक्स इंस्टॉल करें
uv run pre-commit install

# टेस्ट चलाएं
uv run pytest tests/unit/

# कवरेज के साथ चलाएं
uv run pytest tests/ --cov=pentool --cov-report=html
```

---

## समस्या निवारण

### pentool कमांड नहीं मिली

```bash
# Linux/macOS — ~/.bashrc या ~/.zshrc में जोड़ें
export PATH="$HOME/.local/bin:$PATH"

# या uv को PATH कॉन्फ़िगर करने दें:
uv tool update-shell
```

### पैकेज इंस्टॉलेशन त्रुटि

```bash
uv tool install pentool --no-cache
# या pip से:
pip install pentool --no-cache-dir
```

---

## अपडेट करें

```bash
# uv
uv tool upgrade pentool

# pip
pip install --upgrade pentool
```

---

## अनइंस्टॉल करें

```bash
# uv
uv tool uninstall pentool

# pip
pip uninstall pentool

# सभी डेटा हटाएं
rm -rf ~/.config/pentool
rm -rf ~/.local/share/pentool
```

---

## CA प्रमाणपत्र इंस्टॉल करना

HTTPS ट्रैफ़िक को इंटरसेप्ट करने के लिए Pentool CA प्रमाणपत्र इंस्टॉल करना आवश्यक है।

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

## अगले चरण

- [त्वरित प्रारंभ](QUICKSTART.md) — 5 मिनट में शुरू करें
- [उपयोगकर्ता गाइड](USER_GUIDE.md) — पूर्ण दस्तावेज़
- [GitHub](https://github.com/DrXOps/pentool) — स्रोत कोड

---

**सहायता चाहिए?** GitHub पर issue बनाएं: https://github.com/DrXOps/pentool/issues
