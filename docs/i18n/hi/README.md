# 🔒 Pentool — प्रोफेशनल TUI वेब पेनटेस्टिंग टूलकिट

> **🚧 सक्रिय विकास — पब्लिक डेमो/बीटा।** कोर मॉड्यूल स्टेबल और पूरी तरह उपयोग करने योग्य हैं। PRO फीचर्स सक्रिय रूप से विकसित किए जा रहे हैं। फीडबैक और बग रिपोर्ट का स्वागत है।

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/docxqwerty/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/docxqwerty/pentool/actions)
[![License](https://img.shields.io/github/license/docxqwerty/pentool)](../../../LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **भाषाएँ:** [English](../../../README.md) · [Русский](../ru/README.md) · [中文](../zh/README.md) · [हिन्दी](README.md)

---

**Pentool** एक टर्मिनल-आधारित (TUI) सुरक्षा टूलकिट है, जो पेनेट्रेशन टेस्टर्स और सुरक्षा शोधकर्ताओं के लिए बनाया गया है।  
यह HTTP इंटरसेप्शन, वल्नेरेबिलिटी स्कैनिंग, ऑटोमेटेड अटैक और डेटा एनालिसिस — सब कुछ एक ही टर्मिनल में जोड़ता है।  
तेज़, पारदर्शी और वास्तविक परीक्षण के लिए निर्मित।

> ⚠️ **एक आधुनिक टर्मिनल एमुलेटर का उपयोग करें।** Pentool का TUI [Textual](https://github.com/Textualize/textual) फ्रेमवर्क पर बना है और माउस सपोर्ट, ट्रू कलर और आधुनिक रेंडरिंग पर निर्भर करता है। लीगेसी टर्मिनल (जैसे Windows का `cmd.exe`) गलत दिखेंगे। सुझाव: **Windows Terminal**, **iTerm2** (macOS), **GNOME Terminal / Kitty / Alacritty / WezTerm** (Linux)। Windows पर, **WSL** के अंदर चलाने पर सबसे अच्छा अनुभव मिलता है।

---

## ✨ विशेषताएँ

- **🌐 Proxy (प्रॉक्सी)**  
  रियल टाइम में HTTP/HTTPS ट्रैफिक को इंटरसेप्ट और मॉडिफाई करें। Scope मैनेज करें, Match & Replace नियम लागू करें, WebSocket मैसेज कैप्चर करें।

- **🔄 Repeater**  
  किसी भी बदलाव के साथ रिक्वेस्ट को दोबारा भेजें। सेशन के बीच टैब सेव करें और तुरंत स्विच करें।

- **💥 Intruder**  
  चार स्ट्रेटेजी के साथ ऑटोमेटेड payload अटैक: Sniper, Battering Ram, Pitchfork, Cluster Bomb।  
  Turbo Mode में Keep-Alive और कनेक्शन पूलिंग से 10× स्पीड।

- **🔍 Scanner (स्कैनर)**  
  एक्टिव और पैसिव वल्नेरेबिलिटी एनालिसिस: SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE, CORS, JWT फ्लॉ और बहुत कुछ।  
  स्मार्ट कॉन्टेक्स्ट-अवेयर payload, WAF बाइपास, टाइम-बेस्ड और बूलियन-ब्लाइंड तकनीकें।

- **🕷 Spider**  
  टार्गेट को ऑटोमेटिकली क्रॉल करें — पेज, फॉर्म, API एंडपॉइंट और JS फाइलें कलेक्ट करें।  
  Playwright के ज़रिए JavaScript रेंडरिंग सपोर्टेड।

- **🎯 Target / Site Map**  
  प्रॉक्सी ट्रैफिक से साइट मैप बनाएँ, टेस्टिंग स्कोप मैनेज करें और UI से ही होस्ट फिल्टर करें।

- **🔐 Decoder · Comparer · Sequencer**  
  - **Decoder** — चेनिंग सपोर्ट के साथ 19 एनकोड/डिकोड/हैश ऑपरेशन  
  - **Comparer** — बदलावों की हाइलाइटिंग के साथ साइड-बाय-साइड diff  
  - **Sequencer** — टोकन (सेशन, CSRF, JWT) की एंट्रॉपी एनालिसिस, FIPS टेस्ट के साथ

- **🧩 Plugin System**  
  कोर को बदले बिना फंक्शनैलिटी बढ़ाएँ। PRO प्लगइन्स में एडवांस्ड स्कैनर, स्मार्ट payload और रिपोर्ट जनरेटर शामिल हैं।

- **⚡ Async Core**  
  पूरी तरह async इंजन — हज़ारों कंकरंट कनेक्शन और प्रति सेकंड सैकड़ों रिक्वेस्ट।

- **📦 एक लाइन इंस्टॉलेशन**  
  `pip install pentool` — कोई जटिल सेटअप नहीं। Linux, macOS और Windows (WSL) पर काम करता है।

- **🆓 Open Source + PRO Extensions**  
  बेस वर्शन पूरी तरह फ्री और ओपन। PRO लाइसेंस एक्सक्लूसिव फीचर्स अनलॉक करता है और प्रोजेक्ट को सपोर्ट करता है।

---

## 🚀 Quick Start (त्वरित शुरुआत)

```bash
# इंस्टॉल करें
pip install pentool

# TUI लॉन्च करें
pentool

# कस्टम पोर्ट पर प्रॉक्सी शुरू करें
pentool proxy start --port 8080

# एक्टिव स्कैन
pentool scan active --url https://example.com

# अपडेट चेक करें
pentool update --check
```

---

## 📸 स्क्रीनशॉट

| Dashboard | Scanner |
|:---------:|:-------:|
| ![Dashboard](../../../screens/dashboard.png) | ![Scanner](../../../screens/scaner.png) |

| Proxy | Repeater |
|:-----:|:--------:|
| ![Proxy](../../../screens/proxy.png) | ![Repeater](../../../screens/repeater.png) |

| Intruder | Settings |
|:--------:|:--------:|
| ![Intruder](../../../screens/intruder.png) | ![Settings](../../../screens/settings.png) |

---

## 📚 दस्तावेज़ीकरण

- [🚀 पहला रन: सर्टिफिकेट और पहला इंटरसेप्ट](FIRST_RUN.md) — यहाँ से शुरू करें
- [Quick Start Guide](QUICKSTART.md)
- [User Guide](USER_GUIDE.md)
- [Installation](INSTALLATION.md)
- [Plugin Development](PLUGIN_DEVELOPMENT.md)
- [Plugin API संदर्भ](../../API_CONTRACTS.md)

पूरा डॉक्यूमेंटेशन: **[pentool.pro](https://pentool.pro)**

---

## 🧪 डेमो / टेस्टिंग मोड

> **Pentool अभी पब्लिक डेमो/बीटा में है।**  
> सभी **फ्री मॉड्यूल पूरी तरह फंक्शनल हैं**। PRO फीचर्स सक्रिय रूप से बनाए जा रहे हैं — **14-दिन का ट्रायल** उपलब्ध है ताकि आप सब कुछ पहले से जांच सकें।

### 🎙 ब्लॉगर्स और कंटेंट क्रिएटर्स के लिए

**सिक्योरिटी ब्लॉग, YouTube चैनल, या Telegram चैनल** चलाते हैं?  
एक ईमानदार रिव्यू लिखें और अपनी ऑडियंस को Pentool रेकमेंड करें — हम आपको **परमानेंट PRO लाइसेंस, बिल्कुल फ्री** देंगे।

कोई मिनिमम फॉलोअर काउंट नहीं। हम रीच से ज़्यादा क्वालिटी को महत्व देते हैं।  
→ संपर्क करें: **[@sudores](https://t.me/sudores)** Telegram पर

---

## 💰 प्रोजेक्ट को सपोर्ट करें

Pentool को एक डेवलपर अपने खाली समय में अकेले बनाता और मेंटेन करता है।  
अगर यह आपका पेनटेस्ट में घंटों बचाता है — कुछ वापस देने पर विचार करें। हर योगदान सीधे नए फीचर्स, फिक्स और तेज़ रिलीज़ को फंड करता है।

- ⭐ **[GitHub पर Star करें](https://github.com/docxqwerty/pentool)** — फ्री, 2 सेकंड लगते हैं, विज़िबिलिटी में बहुत मदद करता है
- 🔑 **PRO लाइसेंस** — जल्दी एक्सेस पाएँ और डेवलपमेंट सपोर्ट करें → **[@sudores](https://t.me/sudores)**
- 💬 **शेयर करें** — किसी सहकर्मी को बताएँ, रिव्यू पोस्ट करें, या अपने राइटअप्स में Pentool का ज़िक्र करें

> टूल्स बनाना एक अकेला काम है। एक Star या एक अच्छा शब्द वाकई मायने रखता है। धन्यवाद। 🙏

---

## 🤝 योगदान

योगदान का स्वागत है!  
PR बनाने से पहले कृपया [CONTRIBUTING.md](../../../CONTRIBUTING.md) पढ़ें।

---

## 🙏 धन्यवाद

विशेष धन्यवाद:

- **[codeby.net](https://codeby.net/)** — समुदाय समर्थन और फीडबैक के लिए

---

## 📄 लाइसेंस

**AGPL-3.0** लाइसेंस के तहत वितरित। विवरण के लिए [LICENSE](../../../LICENSE) देखें।  
PRO एक्सटेंशन कमर्शियल लाइसेंस के तहत उपलब्ध हैं।

---

## 📬 संपर्क

- **वेबसाइट:** [pentool.pro](https://pentool.pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** support@pentool.pro
- **Author:** Anatoly Kashtanov (DoctorX)

---

⭐ अगर Pentool आपका समय बचाता है, तो GitHub पर एक Star प्रोजेक्ट को बढ़ने में मदद करता है — शुक्रिया!
