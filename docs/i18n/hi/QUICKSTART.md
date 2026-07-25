# 🚀 Pentool त्वरित प्रारंभ गाइड

5 मिनट में Pentool के साथ शुरू करें!

---

## इंस्टॉलेशन

```bash
# PyPI से इंस्टॉल करें
pip install pentool

# या स्रोत से
git clone https://github.com/docxqwerty/pentool.git
cd pentool
pip install -e .
```

---

## पहला लॉन्च

```bash
pentool
```

आप Dashboard स्क्रीन के साथ TUI इंटरफ़ेस देखेंगे।

**नेविगेशन:**
- `Tab` / `Shift+Tab` — विजेट्स के बीच स्विच करें
- `Ctrl+X` — मेनू खोलें
- `Ctrl+Q` — बाहर निकलें

---

## 1. ब्राउज़र प्रॉक्सी कॉन्फ़िगर करें

**चरण 1:** Pentool Proxy प्रारंभ करें
- `Ctrl+X` दबाएं → "Proxy" चुनें
- "Start Proxy" बटन क्लिक करें
- डिफ़ॉल्ट: `127.0.0.1:8888`

**चरण 2:** ब्राउज़र कॉन्फ़िगर करें
- Firefox: Settings → Network → Manual proxy configuration
- HTTP Proxy सेट करें: `127.0.0.1` पोर्ट `8888`
- "Also use this proxy for HTTPS" सक्षम करें

**चरण 3:** CA प्रमाणपत्र इंस्टॉल करें (HTTPS के लिए)
- यहां जाएं: http://burp (या http://127.0.0.1:8888)
- `cacert.pem` डाउनलोड करें
- ब्राउज़र या सिस्टम में आयात करें

---

## 2. HTTP ट्रैफ़िक इंटरसेप्ट करें

**ब्राउज़र में:**
- कोई भी वेबसाइट खोलें
- ट्रैफ़िक Pentool → Proxy → HTTP History में दिखाई देगा

**Intercept (इंटरसेप्ट):**
- Proxy में "Intercept" क्लिक करें
- अनुरोध संशोधित करें
- "Forward" या "Drop" क्लिक करें

---

## 3. अनुरोध दोहराएं (Repeater)

1. Proxy History में: अनुरोध पर राइट क्लिक करें
2. "Send to Repeater" चुनें
3. Repeater में: पैरामीटर संशोधित करें
4. "Send" (`F5`) क्लिक करें
5. प्रतिक्रिया देखें

---

## 4. ब्रूट-फोर्स पैरामीटर (Intruder)

1. Proxy से Intruder में भेजें
2. पैरामीटर चुनें → "Mark Param"
3. हमले का प्रकार चुनें (Sniper, Battering Ram, Pitchfork)
4. Wordlist लोड करें या payloads दर्ज करें
5. "Start Attack" (`F5`) क्लिक करें

---

## 5. भेद्यता स्कैनिंग (Scanner)

**पैसिव स्कैनिंग:**
- Proxy काम करते समय स्वचालित रूप से सक्षम
- भेद्यताओं के लिए सभी ट्रैफ़िक का विश्लेषण करता है

**एक्टिव स्कैनिंग:**
1. Scanner (`Shift+S`) पर जाएं
2. लक्ष्य URL दर्ज करें
3. चेक प्रकार चुनें
4. "Start Scan" (`F5`) क्लिक करें

**जांच की जाती है:**
- XSS (Reflected, DOM, Stored)
- SQL Injection
- SSTI (Template Injection)
- LFI/Path Traversal
- RCE (Command Injection)
- SSRF, XXE, CORS
- JWT, OAuth भेद्यताएं
- और बहुत कुछ...

---

## 6. उपयोगी उपकरण

### Decoder
- `Shift+D` → Decoder खोलें
- समर्थित: Base64, URL, HTML, Hex, Gzip, JWT
- Smart Decode: स्वचालित एन्कोडिंग पहचान

### Comparer
- `Shift+C` → Comparer खोलें
- दो टेक्स्ट पेस्ट करें
- हाइलाइटिंग के साथ diff प्राप्त करें

### Spider
- `Shift+W` → Spider खोलें
- बेस URL दर्ज करें
- स्वचालित साइट क्रॉल

---

## 7. शॉर्टकट कुंजियां

### ग्लोबल
- `Ctrl+Q` — बाहर निकलें
- `Ctrl+N` — नया प्रोजेक्ट
- `Ctrl+O` — प्रोजेक्ट खोलें
- `Ctrl+S` — प्रोजेक्ट सहेजें

### मॉड्यूल नेविगेशन (Shift+अक्षर)
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

### मॉड्यूल में
- `F5` — क्रिया निष्पादित करें (Send, Start Scan आदि)
- `F6` — रोकें
- `Ctrl+F` — खोज/फ़िल्टर
- `m` — संदर्भ मेनू

---

## 8. विशिष्ट परिदृश्य

### Web ऐप परीक्षण
1. Proxy प्रारंभ करें
2. ब्राउज़र कॉन्फ़िगर करें
3. एप्लिकेशन का उपयोग करें
4. Proxy History में ट्रैफ़िक का विश्लेषण करें
5. रुचिकर अनुरोधों को Repeater/Intruder में भेजें

### API परीक्षण
1. Repeater में भेजें
2. JSON body संशोधित करें
3. विभिन्न पैरामीटर परीक्षण करें
4. ब्रूट-फोर्स के लिए Intruder का उपयोग करें

### भेद्यता खोज
1. पैसिव स्कैनर सक्षम करें
2. एप्लिकेशन का उपयोग करें
3. Dashboard में खोजों की जांच करें
4. लक्ष्य एंडपॉइंट पर एक्टिव स्कैनर चलाएं

---

## 9. प्रोजेक्ट

**सहेजें:**
- `Ctrl+S` — .db के रूप में सहेजें (SQLite)
- `Ctrl+Shift+S` — JSON में निर्यात करें

**लोड करें:**
- `Ctrl+O` — .db प्रोजेक्ट खोलें
- `Ctrl+Shift+O` — JSON से आयात करें

**प्रोजेक्ट में शामिल:**
- Proxy इतिहास
- Scanner खोजें
- Intruder परिणाम
- Target साइटमैप
- Match/Replace नियम
- Scope सेटिंग्स

---

## 10. सेटिंग्स

`Ctrl+Comma` या `Shift+Settings`

**इंटरफ़ेस:**
- थीम (Dark/Light)
- UI मोड (Basic/Advanced)

**Proxy:**
- सुनें host/port
- अपस्ट्रीम प्रॉक्सी
- CA प्रमाणपत्र

**नेटवर्क:**
- User-Agent
- टाइमआउट
- SSL सत्यापन
- Collaborator URL

**लाइसेंस:**
- PRO लाइसेंस सक्रिय करें
- उपलब्ध सुविधाएं देखें

---

## अगले चरण

- [पूर्ण गाइड](USER_GUIDE.md) — सभी सुविधाओं का विस्तृत दस्तावेज़ीकरण
- [इंस्टॉलेशन](INSTALLATION.md) — विस्तारित इंस्टॉलेशन निर्देश
- [GitHub](https://github.com/docxqwerty/pentool) — स्रोत कोड, issues, discussions

---

## सहायता चाहिए?

- **दस्तावेज़:** रिपॉजिटरी में `docs/`
- **Issues:** https://github.com/docxqwerty/pentool/issues
- **Discussions:** https://github.com/docxqwerty/pentool/discussions

---

**परीक्षण का आनंद लें! 🔒**
