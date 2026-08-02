# 🔒 Pentool — प्रोफेशनल TUI वेब पेनटेस्टिंग टूलकिट

[![PyPI version](https://img.shields.io/pypi/v/pentool)](https://pypi.org/project/pentool/)
[![Python versions](https://img.shields.io/pypi/pyversions/pentool)](https://pypi.org/project/pentool/)
[![CI](https://github.com/docxqwerty/pentool/actions/workflows/tests.yml/badge.svg)](https://github.com/docxqwerty/pentool/actions)
[![License](https://img.shields.io/github/license/docxqwerty/pentool)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/pentool)](https://pypi.org/project/pentool/)

🌐 **भाषाएँ:** [English](README.md) · [Русский](README_RU.md) · [中文](README_ZH.md) · [हिन्दी](README_HI.md)

---

**Pentool** एक टर्मिनल-आधारित (TUI) सुरक्षा टूलकिट है, जो पेनेट्रेशन टेस्टर्स और सुरक्षा शोधकर्ताओं के लिए बनाया गया है।  
यह HTTP इंटरसेप्शन, वल्नेरेबिलिटी स्कैनिंग, ऑटोमेटेड अटैक और डेटा एनालिसिस — सब कुछ एक ही टर्मिनल में जोड़ता है।  
तेज़, पारदर्शी और वास्तविक परीक्षण के लिए निर्मित।

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

> स्क्रीनशॉट और GIF जल्द आ रहे हैं।

| Dashboard | Proxy | Intruder |
|-----------|-------|----------|
| *(जल्द)* | *(जल्द)* | *(जल्द)* |

---

## 📚 दस्तावेज़ीकरण

- [Quick Start Guide](docs/i18n/en/QUICKSTART.md)
- [User Guide](docs/i18n/en/USER_GUIDE.md)
- [Installation](docs/i18n/en/INSTALLATION.md)
- [Plugin Development](docs/API_CONTRACTS.md)

पूरा डॉक्यूमेंटेशन: **[pentool.pro](https://pentool.pro)**

---

## 🧪 टेस्टिंग मोड (Beta)

> **Pentool अभी पब्लिक बीटा में है।**  
> सभी **फ्री मॉड्यूल पूरी तरह उपलब्ध हैं**। पेड (PRO) प्लगइन्स अभी डेवलपमेंट में हैं — फिलहाल केवल **ट्रायल वर्शन** दिया जाता है।  
>
> लेकिन अगर आपके पास **इन्फॉर्मेशन सिक्योरिटी के क्षेत्र में ब्लॉग या चैनल** है और आप प्रोजेक्ट को प्रमोट करने में मदद कर सकते हैं — हमें DM करें, हम आपको मुफ्त में **प्राइवेट PRO की** देंगे।
>
> 📬 संपर्क: **[@sudores](https://t.me/sudores)** (Telegram)

---

## 💰 प्रोजेक्ट को सपोर्ट करें

Pentool को एक डेवलपर अपने खाली समय में अकेले बनाता और मेंटेन करता है।  
अगर यह आपके काम में मदद करता है, तो सपोर्ट करें — इससे सीधे नए फीचर और बग फिक्स में तेज़ी आती है।

- ⭐ [GitHub पर Star दें](https://github.com/docxqwerty/pentool) — फ्री है और बहुत मदद करता है
- ☕ [TryBit से Donate करें](https://donate.trybit.com/KY1ECKA5) — क्रिप्टो में एक बार सपोर्ट
- 🔑 PRO लाइसेंस — जल्द आ रहा है; अभी ट्रायल उपलब्ध

हर योगदान मायने रखता है। ओपन-सोर्स सिक्योरिटी टूलिंग को सपोर्ट करने के लिए धन्यवाद! 🙌

---

## 🤝 योगदान

योगदान का स्वागत है!  
PR बनाने से पहले कृपया [CONTRIBUTING.md](CONTRIBUTING.md) पढ़ें।

---

## 🙏 धन्यवाद

विशेष धन्यवाद:

- **[codeby.net](https://codeby.net/)** — समुदाय समर्थन और फीडबैक के लिए

---

## 📄 लाइसेंस

**AGPL-3.0** लाइसेंस के तहत वितरित। विवरण के लिए [LICENSE](LICENSE) देखें।  
PRO एक्सटेंशन कमर्शियल लाइसेंस के तहत उपलब्ध हैं।

---

## 📬 संपर्क

- **वेबसाइट:** [pentool.pro](https://pentool.pro)
- **Telegram:** [@sudores](https://t.me/sudores)
- **Email:** support@pentool.pro
- **Author:** Anatoly Kashtanov (DoctorX)

---

⭐ अगर Pentool आपका समय बचाता है, तो GitHub पर एक Star प्रोजेक्ट को बढ़ने में मदद करता है — शुक्रिया!
