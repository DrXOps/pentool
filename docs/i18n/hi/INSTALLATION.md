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

> **Windows उपयोगकर्ताओं के लिए: TUI के लिए WSL2 चाहिए।** ऊपर दिए PowerShell कमांड CLI और
> headless स्कैन (`--headless`) के लिए काफ़ी हैं। इंटरैक्टिव इंटरफ़ेस — प्रॉक्सी, ANSI
> फ़्रेम, हुक — के लिए WSL2 इस्तेमाल करें: नीचे देखें
> [WSL2 के ज़रिए Windows पर चलाना](#wsl2-windows)।

---

<a id="wsl2-windows"></a>
## WSL2 के ज़रिए Windows पर चलाना

TUI को POSIX टर्मिनल चाहिए: प्रॉक्सी, हुक और ANSI बॉक्स-ड्रॉइंग UI — सब UTF-8 लोकेल पर
निर्भर करते हैं। WSL2 (Ubuntu) के अंदर सब कुछ Linux की तरह काम करता है। कमांड
**WSL शेल** में चलाएँ, PowerShell में नहीं।

### 1. WSL2 इंस्टॉल करें (PowerShell, Administrator के रूप में)

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
wsl --update
wsl --status
```

### 2. लोकेल और UTF-8 — बॉक्स-ड्रॉइंग अक्षर इसी से काम करते हैं

```bash
sudo apt update
sudo apt install -y locales
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8
exec bash
echo $LANG    # en_US.UTF-8 होना चाहिए, C या POSIX नहीं
```

`LANG=C`, `POSIX` या खाली मान — फ़्रेम की जगह `?` दिखने और सिरिलिक में “मोजीबेक” की
आम वजह है।

### 3. ऐसा फ़ॉन्ट जिसमें ग्लिफ़ मौजूद हैं

**Windows तरफ़** (Windows Terminal के लिए): **JetBrains Mono Nerd Font** या
**Cascadia Code NF** इंस्टॉल करें और टर्मिनल प्रोफ़ाइल में उसे चुनें। इमोजी
(`▶ ✖ 💥 🧭`) **Segoe UI Emoji** से fallback के तौर पर आते हैं।

**WSL तरफ़** (Kitty के लिए):

```bash
sudo apt install -y unzip curl fonts-noto-color-emoji
mkdir -p ~/.local/share/fonts && cd ~/.local/share/fonts
curl -LO https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
unzip -o JetBrainsMono.zip && fc-cache -fv
```

### 4. Kitty (वैकल्पिक — Windows Terminal भी चलता है)

```bash
sudo apt install -y kitty
```

`~/.config/kitty/kitty.conf`:

```conf
font_family JetBrainsMono Nerd Font
font_size 12.0
# बॉक्स ड्रॉइंग
symbol_map U+2500-U+257F JetBrainsMono Nerd Font
# इमोजी
symbol_map U+1F300-U+1FAFF Noto Color Emoji
# WSLg में आसान डिफ़ॉल्ट
sync_to_monitor no
repaint_delay 8
```

शुरू करें: `kitty pentool`, या Windows से: `wsl.exe -e kitty pentool`।

अगर कुछ पैनल आइकन नहीं दिखते — **Settings → Interface → Panel icons** में आइकन सेट
बदलें (`unicode` / `ascii` / `emoji`)।

### 5. जाँचें कि अक्षर ठीक हैं

```bash
python3 -c "print('┌────┬────┐\n│ OK │ 42 │\n└────┴────┘')"
printf '█ ▓ ▒ ░  →  ✔ ✖ ⚠\n'
infocmp -1 | head -3    # TERM *-256color होना चाहिए, dumb नहीं
```

### 6. अगर कुछ फिर भी गलत दिखे

| लक्षण | कारण | उपाय |
|---|---|---|
| `?` या `+---+` जैसे फ़्रेम | UTF-8 लोकेल नहीं | चरण 2, `export LANG=en_US.UTF-8` |
| सिरिलिक में “मोजीबेक” | `LANG=C` / `POSIX` | चरण 2 |
| फ़्रेम दुगनी चौड़ाई, लेआउट खिसकता है | फ़ॉन्ट में बॉक्स ग्लिफ़ नहीं | चरण 3 |
| आइकन चौकोर | इमोजी/Nerd फ़ॉन्ट नहीं | चरण 3, या `ascii` आइकन सेट |
| TUI शुरू नहीं होता | `TERM=dumb` | `export TERM=xterm-256color` |
| रंग नहीं | 8-रंग वाला टर्मिनल | Windows Terminal या Kitty |

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
