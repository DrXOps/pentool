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

### विधि 1: PyPI (अनुशंसित)

```bash
# वर्चुअल एनवायरनमेंट बनाएं (अनुशंसित)
python3 -m venv pentool-env
source pentool-env/bin/activate  # Linux/macOS
# या
pentool-env\Scripts\activate  # Windows

# इंस्टॉल करें
pip install pentool

# सत्यापित करें
pentool --version
```

### विधि 2: स्रोत से

```bash
# रिपॉजिटरी क्लोन करें
git clone https://github.com/docxqwerty/pentool.git
cd pentool

# वर्चुअल एनवायरनमेंट बनाएं
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# या
venv\Scripts\activate  # Windows

# एडिटेबल मोड में इंस्टॉल करें
pip install -e ".[dev]"

# सत्यापित करें
pentool --version
```

### विधि 3: pipx (पृथक इंस्टॉल)

```bash
# pipx इंस्टॉल करें
pip install pipx

# pentool इंस्टॉल करें
pipx install pentool

# चलाएं
pentool
```

---

## प्लेटफॉर्म-विशिष्ट निर्देश

### Linux (Ubuntu/Debian)

```bash
# सिस्टम निर्भरताएं इंस्टॉल करें
sudo apt update
sudo apt install python3 python3-pip python3-venv

# pentool इंस्टॉल करें
pip3 install pentool

# चलाएं
pentool
```

### macOS

```bash
# Homebrew इंस्टॉल करें (यदि इंस्टॉल नहीं है)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python इंस्टॉल करें
brew install python@3.11

# pentool इंस्टॉल करें
pip3 install pentool

# चलाएं
pentool
```

### Windows

```powershell
# python.org से Python इंस्टॉल करें
# https://www.python.org/downloads/

# pentool इंस्टॉल करें
pip install pentool

# चलाएं
pentool
```

---

## CA प्रमाणपत्र इंस्टॉल करना

HTTPS ट्रैफ़िक को इंटरसेप्ट करने के लिए Pentool CA प्रमाणपत्र इंस्टॉल करना आवश्यक है।

### Linux (Ubuntu/Debian)

```bash
# प्रमाणपत्र कॉपी करें
sudo mkdir -p /usr/local/share/ca-certificates/pentool
sudo cp ~/.config/pentool/ca.crt /usr/local/share/ca-certificates/pentool/

# प्रमाणपत्र स्टोर अपडेट करें
sudo update-ca-certificates
```

### macOS

```bash
# Keychain में जोड़ें
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.config/pentool/ca.crt
```

### Windows

```powershell
# प्रमाणपत्र आयात करें
certutil -addstore -f "ROOT" %USERPROFILE%\.config\pentool\ca.crt
```

### ब्राउज़र

**Firefox:**
1. Settings → Privacy & Security → Certificates → View Certificates
2. Import → `~/.config/pentool/ca.crt` चुनें
3. "Trust this CA to identify websites" को चेक करें

**Chrome/Chromium:**
1. Settings → Privacy and security → Security → Manage certificates
2. Authorities → Import
3. `~/.config/pentool/ca.crt` चुनें

---

## इंस्टॉलेशन सत्यापित करें

```bash
# संस्करण जांचें
pentool --version

# TUI प्रारंभ करें
pentool

# विकल्प देखें
pentool --help
```

---

## समस्या निवारण

### Python नहीं मिला

```bash
# Linux/macOS
which python3
python3 --version

# Windows
where python
python --version
```

### पैकेज इंस्टॉलेशन त्रुटि

```bash
# pip अपग्रेड करें
pip install --upgrade pip

# कैश के बिना इंस्टॉल करें
pip install pentool --no-cache-dir
```

### अनुमति समस्याएं

```bash
# Linux/macOS - वर्चुअल एनवायरनमेंट का उपयोग करें
python3 -m venv venv
source venv/bin/activate
pip install pentool
```

---

## अगले चरण

- [त्वरित प्रारंभ](QUICKSTART.md) — 5 मिनट में शुरू करें
- [उपयोगकर्ता गाइड](USER_GUIDE.md) — पूर्ण दस्तावेज़
- [GitHub](https://github.com/docxqwerty/pentool) — स्रोत कोड

---

**सहायता चाहिए?** GitHub पर issue बनाएं: https://github.com/docxqwerty/pentool/issues
