# 🧩 Pentool प्लगइन लिखना

Pentool का प्लगइन सिस्टम आपको कोर कोड को छुए बिना टूलकिट को एक्सटेंड करने देता
है — एक नई TUI स्क्रीन, CLI कमांड, कस्टम एक्टिव स्कैनर, या हर प्रॉक्सी
रिक्वेस्ट पर चलने वाला पैसिव चेक जोड़ें।

---

## प्लगइन कहाँ रहते हैं

| लोकेशन | उद्देश्य |
|---|---|
| `~/.pentool/plugins/` | आपके खुद के प्लगइन — हर स्टार्टअप पर ऑटो-लोड होते हैं (`PluginManager.load_user_plugins()`) |
| `pentool/plugins/builtin/` | FREE पैकेज के साथ आने वाले प्लगइन |
| PRO पैकेज (`~/.pentool/pro/pentool/plugins/builtin/`) | `pentool license trial`/`activate` से डाउनलोड किए गए प्लगइन |

`~/.pentool/plugins/` में एक `.py` फाइल डालें और अगली बार Pentool स्टार्ट
होने पर वह ऑटोमैटिकली लोड हो जाएगी। `_` से शुरू होने वाली फाइलनेम्स स्किप हो
जाती हैं।

> ⚠️ नॉन-स्टैंडर्ड/अविश्वसनीय पाथ से प्लगइन एक वार्निंग लॉग ट्रिगर करते हैं
> — केवल वही कोड लोड करें जिस पर आप भरोसा करते हैं; एक प्लगइन पूरे प्रोसेस
> प्रिविलेज के साथ चलता है।

---

## न्यूनतम प्लगइन

हर प्लगइन एक सिंगल Python फाइल है जिसमें दो चीज़ें होती हैं:

1. `BasePlugin` से इनहेरिट करने वाला एक क्लास — केवल मेटाडेटा।
2. एक मॉड्यूल-लेवल `register(hook: PluginHook)` फंक्शन — एंट्री पॉइंट जिसे
   Pentool फाइल लोड होने के बाद कॉल करता है।

```python
"""मेरा पहला प्लगइन।"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.plugin_manager import BasePlugin, PluginHook


class HelloScreen(Widget):
    """प्लगइन द्वारा जोड़ा गया एक सिंपल स्क्रीन।"""

    def compose(self) -> ComposeResult:
        yield Static("मेरे प्लगइन से नमस्ते!")


class MyPlugin(BasePlugin):
    name = "my_plugin"          # यूनिक ID, snake_case
    version = "1.0"
    author = "you"
    description = "मेरा पहला Pentool प्लगइन"
    api_version = 1              # करंट Plugin API वर्शन
    required_feature = ""        # "" = फ्री प्लगइन, PRO लाइसेंस की ज़रूरत नहीं


def register(hook: PluginHook) -> None:
    """प्लगइन लोड होने पर एक बार कॉल होता है।"""
    hook.register_screen("My Screen", HelloScreen)
```

इसे `~/.pentool/plugins/my_plugin.py` के रूप में सेव करें और Pentool
रीस्टार्ट करें — मॉड्यूल स्विचर में एक नई एंट्री दिखेगी।

Pentool के साथ आने वाला पूरा वर्किंग एग्ज़ाम्पल देखें:
`pentool/plugins/example_plugin.py` (+ Textual CSS स्टाइलिंग के लिए
`example_plugin.tcss`)।

---

## `BasePlugin` एट्रिब्यूट्स

| एट्रिब्यूट | टाइप | मतलब |
|---|---|---|
| `name` | `str` | यूनिक प्लगइन ID (snake_case) |
| `version` | `str` | वर्शन स्ट्रिंग, जैसे `"1.0"` |
| `author` | `str` | ऑथर का नाम |
| `description` | `str` | संक्षिप्त विवरण |
| `api_version` | `int` | Plugin API वर्शन जिसे यह प्लगइन टारगेट करता है। Pentool के `CURRENT_API_VERSION` से नया वर्शन डिक्लेयर करने वाले प्लगइन इनकम्पैटिबल मानकर रिजेक्ट कर दिए जाते हैं |
| `required_feature` | `str` | खाली स्ट्रिंग = फ्री प्लगइन। PRO लाइसेंस के पीछे प्लगइन को गेट करने के लिए लाइसेंस फीचर का नाम सेट करें (जैसे `"scanner_pro"`) — `get_session_license()` के ज़रिए चेक होता है |

---

## `PluginHook` के ज़रिए क्या रजिस्टर कर सकते हैं

```python
def register(hook: PluginHook) -> None:
    hook.register_screen(name, widget_class, hotkey=None)
    hook.register_cli_command(group_name, click_command)
    hook.register_scanner(scanner_class)       # BaseScanner का सबक्लास
    hook.register_passive_check(check_class)   # BaseCheck का सबक्लास
```

### `register_screen(name, widget_class, hotkey=None)`
TUI के मॉड्यूल स्विचर में एक नया मॉड्यूल/स्क्रीन जोड़ता है। `widget_class`
`textual.widget.Widget` का सबक्लास होना चाहिए (ऊपर `HelloScreen` देखें)।

### `register_cli_command(group_name, command)`
किसी मौजूदा CLI कमांड ग्रुप (जैसे `scan`, `proxy`) के तहत एक
`click.Command` जोड़ता है — `pentool <group> <your-command>` को एक्सटेंड
करता है।

### `register_scanner(scanner_class)`
एक स्कैनर प्लगइन रजिस्टर करता है — एक `BaseScanner` सबक्लास जो एक या ज़्यादा
`BaseCheck`s को एक नाम के तहत ग्रुप करता है:

```python
from pentool.core.plugin_manager import BaseScanner, BaseCheck

class MyCheck(BaseCheck):
    name = "my_check"
    description = "कुछ कस्टम डिटेक्ट करता है"
    severity = "medium"      # critical | high | medium | low | info
    passive = False          # True = हर प्रॉक्सी रिक्वेस्ट पर ऑटोमैटिकली चलता है

    async def scan(self, target, http_client, **kwargs) -> list:
        findings = []
        # ... आपकी डिटेक्शन लॉजिक ...
        return findings

class MyScanner(BaseScanner):
    name = "my_scanner"
    checks = [MyCheck]
```

### `register_passive_check(check_class)`
एक स्टैंडअलोन पैसिव `BaseCheck` रजिस्टर करता है जो प्रॉक्सी से गुज़रने वाले
हर रिक्वेस्ट पर चलता है (एक्टिव स्कैन की ज़रूरत नहीं) — लाइटवेट, हमेशा-ऑन
डिटेक्शन्स (info leaks, secrets, header issues) के लिए उपयोगी।

---

## PRO-गेटेड प्लगइन

PRO लाइसेंस की ज़रूरत के लिए `required_feature` को एक लाइसेंस फीचर स्ट्रिंग
पर सेट करें:

```python
class MyProPlugin(BasePlugin):
    name = "my_pro_plugin"
    required_feature = "scanner_pro"
```

अगर एक्टिव लाइसेंस `"scanner_pro"` को कवर नहीं करता, तो प्लगइन एक WARNING
लॉग लाइन के साथ स्किप हो जाता है — बाकी Pentool सामान्य रूप से काम करता
रहता है।

---

## अपने प्लगइन का टेस्टिंग

कोई खास टेस्ट हार्नेस नहीं है — प्लगइन प्लेन Python हैं। अपने
`BaseCheck.scan()`/`BasePlugin` क्लासेस के खिलाफ रेगुलर यूनिट टेस्ट लिखें,
और फाइल को `~/.pentool/plugins/` में डालकर और Pentool रीस्टार्ट करके एक
मैनुअल स्मोक टेस्ट करें। लोड होने की पुष्टि के लिए लॉग
(`~/.config/pentool/pentool.log`) में `Plugin '<name>': registered ...`
लाइनें चेक करें।

---

## ये भी देखें

- [Plugin API संदर्भ / सभी मॉड्यूल APIs](../../API_CONTRACTS.md) —
  ProxyAPI, ScannerAPI, IntruderAPI, SpiderAPI, RepeaterAPI, TargetAPI,
  DecoderAPI, ComparerAPI, SequencerAPI
- `pentool/core/plugin_manager.py` — `BasePlugin`, `BaseCheck`,
  `BaseScanner`, `PluginHook`, `PluginManager` का पूरा सोर्स
- `pentool/plugins/example_plugin.py` — पूरा वर्किंग एग्ज़ाम्पल
