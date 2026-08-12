# 🚀 पहला रन — सर्टिफिकेट और पहला इंटरसेप्ट

`uv tool install pentool` से लेकर पहला इंटरसेप्ट किया गया HTTPS रिक्वेस्ट देखने तक
की एक न्यूनतम गाइड। पूरी जानकारी के लिए [Quick Start Guide](QUICKSTART.md) और
[User Guide](USER_GUIDE.md) देखें।

> ⚠️ **एक आधुनिक टर्मिनल एमुलेटर का उपयोग करें।** Pentool का TUI माउस
> सपोर्ट, ट्रू कलर और आधुनिक रेंडरिंग (Textual फ्रेमवर्क) पर निर्भर करता है।
> Windows का `cmd.exe` और पुराने/लीगेसी टर्मिनल गलत दिखेंगे। सुझाव:
> **Windows Terminal**, **iTerm2** (macOS), **GNOME
> Terminal/Kitty/Alacritty/WezTerm** (Linux)। Windows पर सबसे अच्छे अनुभव के
> लिए Pentool को **WSL** के अंदर चलाएँ।

---

## 1. इंस्टॉल करें और लॉन्च करें

```bash
uv tool install pentool   # अनुशंसित
# या: pip install pentool
pentool
```

आपको Dashboard स्क्रीन दिखेगी।

## 2. प्रॉक्सी शुरू करें

1. **Proxy** मॉड्यूल पर जाएँ (`Ctrl+X` → Proxy, या `Shift+P`)
2. **"○ Proxy"** पर क्लिक करें इसे शुरू करने के लिए — बटन **"● Proxy :8080"**
   में बदल जाएगा (डिफ़ॉल्ट होस्ट/पोर्ट `127.0.0.1:8080`, Settings में बदला
   जा सकता है)

## 3. CA सर्टिफिकेट डाउनलोड और इंस्टॉल करें

प्रॉक्सी पहली बार शुरू होने पर, Pentool एक लोकल सर्टिफिकेट अथॉरिटी (CA)
जनरेट करता है, ताकि वह आपके लिए HTTPS ट्रैफिक को डिक्रिप्ट कर सके (Burp/
mitmproxy जैसा ही तरीका)। कुछ भी आपकी मशीन से बाहर नहीं जाता — CA लोकली
`~/.config/pentool/certs/ca.crt` में जनरेट होता है।

1. Proxy स्क्रीन पर **"Install CA cert"** पर क्लिक करें (या
   **Settings → Proxy → Install CA cert** से खोलें) — एक डायलॉग सर्टिफिकेट
   का पाथ और Firefox, Chrome, और सिस्टम-वाइड इंस्टॉलेशन (Ubuntu/Debian,
   Fedora/RHEL) के लिए स्टेप-बाय-स्टेप निर्देश दिखाएगा।
2. अपने ब्राउज़र के लिए निर्देशों का पालन करें:
   - **Firefox:** `about:preferences#privacy` → Certificates → View
     Certificates → **Authorities** टैब (न कि "Your Certificates") →
     Import → `ca.crt` चुनें → "Trust this CA to identify websites" चेक
     करें → Firefox रीस्टार्ट करें।
   - **Chrome/Chromium:** `chrome://settings/certificates` → Authorities →
     Import → `ca.crt` चुनें → "Trust for identifying websites" चेक करें →
     Chrome रीस्टार्ट करें।
   - **सिस्टम-वाइड (Linux):** आपके डिस्ट्रो के लिए कमांड सीधे डायलॉग में
     दिखाए जाते हैं।
3. **अपने ब्राउज़र की प्रॉक्सी सेटिंग्स को Pentool पर पॉइंट करें:**
   - HTTP/HTTPS प्रॉक्सी: `127.0.0.1`, पोर्ट `8080` (या जो भी आपने सेट किया
     हो)
   - Firefox: Settings → Network Settings → Manual proxy configuration
   - Chrome: `--proxy-server="127.0.0.1:8080"` के साथ लॉन्च करें, या
     सिस्टम-वाइड प्रॉक्सी सेटिंग / FoxyProxy जैसा एक्सटेंशन इस्तेमाल करें

## 4. अपना पहला रिक्वेस्ट इंटरसेप्ट करें

1. Proxy स्क्रीन पर **"○ Intercept"** को ON करें
2. अपने कॉन्फ़िगर किए गए ब्राउज़र में किसी भी HTTPS साइट पर जाएँ
3. रिक्वेस्ट Pentool के **Intercept** टैब में रुक जाएगा — इसे
   देखें/एडिट करें, फिर **Forward** या **Drop** करें
4. ट्रैफिक को सामान्य रूप से चलने देने के लिए Intercept को वापस OFF करें और
   बस इसे **HTTP History** में जमा होते देखें

बस — अब आप ट्रैफिक कैप्चर कर रहे हैं और उसे **Repeater**, **Intruder** को
भेज सकते हैं, या उन पर **Scanner** चला सकते हैं।

---

**आगे:** [Quick Start Guide](QUICKSTART.md) · [User Guide](USER_GUIDE.md)
