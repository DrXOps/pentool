"""Chinese content — mirrors ru.py key for key."""

from __future__ import annotations

LANG = "zh"

NAV = {
    "features": "功能",
    "install": "安装",
    "pricing": "价格",
    "docs": "文档",
}

UI = {
    "skip": "跳到正文",
    "menu": "栏目",
    "slots_label": "你要激活几台机器？",
    "slots_hint": "一个槽位对应一台机器。许可证随时可以转移到另一台机器。",
    "buy_title": "购买 Pentool PRO",
    "buy_text": ("留下 e-mail：密钥会发到这个地址。之后进入 Coinso 支付页面，用加密货币付款。"),
    "buy_email": "接收密钥的 e-mail",
    "buy_hint": "如果没收到邮件，请联系支持并注明订单号。",
    "buy_confirm": "前往支付",
    "buy_slots": "槽位：{n}",
    "buy_waiting": "正在创建账单…",
    "err_email": "这个地址看起来有笔误，请检查 e-mail。",
    "err_checkout": "无法创建账单。请联系支持：support@pentool.pro",
    "close": "关闭",
}

FOOTER = {
    "blurb": "终端里的渗透测试：拦截、攻击、扫描和报告都在同一个项目里。核心开源。",
    "groups": [
        {
            "title": "产品",
            "links": [
                {"label": "功能", "href": "@index#features"},
                {"label": "模块", "href": "@index#modules"},
                {"label": "安装", "href": "@index#install"},
                {"label": "价格与 PRO", "href": "@pricing"},
            ],
        },
        {
            "title": "文档",
            "links": [
                {"label": "快速开始", "href": "@docs:quickstart"},
                {"label": "用户手册", "href": "@docs:user_guide"},
                {"label": "在 CI 中扫描", "href": "@link:ci_guide"},
                {"label": "Plugin API", "href": "@link:plugin_api"},
                {"label": "源代码", "href": "@link:github"},
            ],
        },
        {
            "title": "联系",
            "links": [
                {"label": "支持", "href": "@link:email"},
                {"label": "Telegram 频道", "href": "@link:telegram_channel"},
                {"label": "作者", "href": "@link:telegram_author"},
                {"label": "报告问题", "href": "@link:issues"},
            ],
        },
        {
            "title": "法律",
            "links": [
                {"label": "用户协议", "href": "@terms"},
                {"label": "隐私政策", "href": "@privacy"},
                {"label": "AGPL-3.0 许可证", "href": "@link:license"},
                {"label": "许可证门户", "href": "@link:license_portal"},
            ],
        },
    ],
    "legal": "© 2024–2026 Anatoly Kashtanov (DoctorX)。Pentool 是一个独立项目。",
    "built": "本站是静态 HTML，没有分析代码，也没有跟踪器。",
}

PAGES = {
    "index": {
        "title": "Pentool — 终端里的 Web 渗透测试",
        "description": (
            "Pentool 是终端里的 Web 渗透测试工具：代理、请求重放、Intruder、漏洞扫描、侦察和报告。核心开源。"
        ),
        "hero": {
            "kicker": "面向终端的渗透测试工具",
            "h1": "在<em>一个终端窗口</em>里完成 Web 渗透测试",
            "lead": (
                "拦截并重放请求、按字典发起攻击、扫描漏洞、做侦察并出报告。"
                "一个项目，替代十几个窗口、一个浏览器和笨重的 IDE。"
            ),
            "buttons": [
                {"label": "购买 PRO", "href": "@pricing", "style": "primary"},
                {"label": "免费下载", "href": "#install", "style": "ghost"},
            ],
            "meta": ["Linux · macOS · Windows (WSL)", "Python 3.10+", "核心采用 AGPL-3.0"],
        },
        "sections": [
            {
                "id": "features",
                "eyebrow": "为什么需要它",
                "title": "少切换几次，多做一些工作",
                "lead": (
                    "Pentool 并不想取代你整套工具链。它去掉的是工具之间的来回折腾："
                    "目标、请求、发现和报告都放在同一个项目里。"
                ),
                "blocks": [
                    {
                        "t": "cards",
                        "items": [
                            {
                                "title": "目标只需一条命令",
                                "text": (
                                    "<code>pentool --url https://target</code> 会创建项目、添加目标并"
                                    "启动代理。接下来请求直接出现在历史里。"
                                ),
                            },
                            {
                                "title": "通过 SSH 使用",
                                "text": (
                                    "终端、tmux、没有图形界面的服务器。键盘和鼠标、深色和浅色"
                                    "主题——客户端不需要额外配置。"
                                ),
                            },
                            {
                                "title": "项目就是一个文件夹",
                                "text": (
                                    "流量历史、发现和报告存放在项目旁边的 SQLite 里：可以过一个月"
                                    "再回来，也可以交给同事。"
                                ),
                            },
                            {
                                "title": "要的是报告，不是截图",
                                "text": (
                                    "发现可以导出为 HTML、JSON 或 CSV，另外还有 Bug Bounty 模板的"
                                    "汇总报告，以及导出到 HackerOne、Bugcrowd 和 DefectDojo。"
                                ),
                            },
                        ],
                    }
                ],
            },
            {
                "id": "modules",
                "eyebrow": "模块",
                "title": "十个标签页，十项任务",
                "lead": ("用快捷键切换，标签页状态在重启后保留。扫描器和侦察需要 PRO 密钥，其余功能立即可以使用。"),
                "blocks": [
                    {
                        "t": "modules",
                        "items": [
                            {
                                "name": "Dashboard",
                                "text": "项目概览：发现了什么、正在运行什么、快捷操作。",
                            },
                            {
                                "name": "Proxy",
                                "text": ("HTTP/HTTPS 和 WebSocket 拦截、请求历史、Match &amp; Replace 规则、scope。"),
                            },
                            {
                                "name": "Repeater",
                                "text": "在标签页里修改并重放请求，与上一次响应做对比。",
                            },
                            {
                                "name": "Intruder",
                                "text": (
                                    "Sniper、Battering Ram、Pitchfork、Cluster Bomb。线程数和延迟"
                                    "可以自定，结果以表格呈现。"
                                ),
                            },
                            {
                                "name": "Scanner",
                                "tag": "PRO",
                                "text": "主动和被动检查：SQLi、XSS、SSTI、LFI、RCE、SSRF、XXE 等。",
                            },
                            {
                                "name": "Target",
                                "text": "从代理流量生成站点地图、scope 规则、按主机过滤。",
                            },
                            {
                                "name": "Utils",
                                "text": "Decoder（19 种链式操作）、Comparer（逐行 diff）、Sequencer（熵和 FIPS 测试）。",
                            },
                            {
                                "name": "Extensions",
                                "text": "插件：自定义界面、扫描器检查、被动检查和命令。",
                            },
                            {
                                "name": "Recon",
                                "tag": "PRO",
                                "text": "子域名、端点、CDN 背后的真实 IP、参数模糊测试。",
                            },
                            {
                                "name": "Settings",
                                "text": "主题、网络、代理、许可证、本地 AI。",
                            },
                        ],
                        "copy": "Decoder、Comparer 和 Sequencer 在 Utils 里有各自的子标签页。",
                    }
                ],
            },
            {
                "id": "scanner",
                "eyebrow": "扫描器 · PRO",
                "title": "具体检查什么",
                "lead": ("主动检查会向目标发送请求并确认发现，被动检查则分析本来就会经过代理的响应。"),
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "<strong>注入：</strong> SQLi（error、time 和 boolean 型，UNION）、NoSQL、"
                            "SSTI、LFI、路径穿越、RCE、header 和 host header 注入",
                            "<strong>客户端：</strong> XSS、DOM XSS、原型链污染、开放重定向",
                            "<strong>访问与数据：</strong> 认证缺陷、JWT none、OAuth、CORS、响应中的敏感数据",
                            "<strong>服务：</strong> SSRF、XXE、GraphQL",
                            "<strong>被动：</strong> 缺失的安全响应头、信息泄露、敏感数据、DOM XSS",
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "发现会进入一张带风险等级、证据和原始请求的表格，请求可以直接在 "
                            "Repeater 里重放。报告可导出为 HTML、JSON 或 CSV，汇总报告使用"
                            " Bug Bounty 模板。"
                        ),
                    },
                    {
                        "t": "note",
                        "text": ("检查列表会随版本增加。如果缺了你需要的那一项，插件可以自己加一个。"),
                    },
                ],
            },
            {
                "id": "ai",
                "eyebrow": "人工智能",
                "title": "模型跑在你的机器上，不在云端",
                "lead": ("Pentool 里的 AI 是一个小型本地模型。它运行在你的 CPU 上，默认关闭，不向外部发送任何内容。"),
                "blocks": [
                    {
                        "t": "cards",
                        "items": [
                            {
                                "title": "它做什么",
                                "text": (
                                    "按目标的技术栈挑选检查、生成 payload、尝试为 XSS 绕过 WAF、"
                                    "复核发现，并在爬取过程中建议端点。"
                                ),
                            },
                            {
                                "title": "它跑在哪",
                                "text": ("在你的机器上：约 350 MB 的模型只需下载一次，用 CPU 推理，不需要显卡。"),
                            },
                            {
                                "title": "什么不会外发",
                                "text": (
                                    "请求、响应和发现都留在项目里。Pentool 没有云端服务商——流量根本没有地方可发。"
                                ),
                            },
                            {
                                "title": "什么时候打开",
                                "text": (
                                    "可选：在 Settings → AI 里。不开模型时常规检查照常工作，"
                                    "发现分析会退回简单的启发式规则。"
                                ),
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": ("AI 是助手，不能替代检查：对发现的最终判断仍在你手上。"),
                    },
                ],
            },
            {
                "id": "ci",
                "eyebrow": "自动化",
                "title": "在流水线里扫描",
                "lead": (
                    "同一个扫描器可以不带界面运行——用 <code>--headless</code> 标志。"
                    "适用于 GitHub Actions、GitLab CI 和任何 shell。"
                ),
                "blocks": [
                    {
                        "t": "term",
                        "title": "bash",
                        "lines": [
                            {"k": "cmd", "text": "$ pentool --url https://example.com --headless \\"},
                            {"k": "cmd", "text": "    --check xss,sqli --threads 20 --delay 0.2 \\"},
                            {"k": "cmd", "text": "    --format html --output report.html"},
                            {"k": "dim", "text": "# 退出码：0 — 成功，1 — 扫描失败，2 — 参数错误"},
                        ],
                        "copy": (
                            "还有其他标志：<code>--crawl --depth</code>、<code>--ai</code>、"
                            "<code>--format json</code>。"
                        ),
                    },
                    {
                        "t": "p",
                        "text": (
                            "自定义检查以插件形式提供：<code>BasePlugin</code> 可以添加"
                            "界面、CLI 命令、扫描器检查和被动检查。插件放在 "
                            "<code>~/.config/pentool/plugins</code>，API 有文档。"
                        ),
                    },
                ],
            },
            {
                "id": "install",
                "eyebrow": "安装",
                "title": "两条命令，直到发出第一个请求",
                "lead": "软件包从 PyPI 安装。不需要 Docker、JDK 和外部代理。",
                "blocks": [
                    {
                        "t": "term",
                        "title": "bash",
                        "lines": [
                            {"k": "cmd", "text": "$ uv tool install pentool"},
                            {"k": "cmd", "text": "$ pentool --url https://example.com"},
                            {
                                "k": "accent",
                                "text": (
                                    "▶ Dashboard  ·  Proxy  ·  Repeater  ·  Intruder  ·  Scanner  ·  "
                                    "Target  ·  Utils  ·  Extensions  ·  Recon  ·  Settings"
                                ),
                            },
                        ],
                        "copy": (
                            "没有 <code>uv</code> 也可以用 <code>pip install pentool</code>。"
                            "HTTPS 证书 Pentool 会自己生成。"
                        ),
                    },
                    {
                        "t": "note",
                        "text": (
                            "需要现代终端：Windows Terminal、iTerm2、GNOME Terminal、"
                            "Kitty、Alacritty 或 WezTerm。在 Windows 上 WSL2 更省事。"
                        ),
                    },
                ],
            },
            {
                "id": "start",
                "blocks": [
                    {
                        "t": "cta",
                        "title": "在自己的项目上试试",
                        "text": ("免费核心没有时间限制。扫描器、侦察和报告需要 PRO。"),
                        "buttons": [
                            {"label": "免费下载", "href": "#install", "style": "primary"},
                            {"label": "购买 PRO", "href": "@pricing", "style": "ghost"},
                        ],
                    }
                ],
            },
        ],
    },
    "pricing": {
        "title": "Pentool — 价格与 PRO 许可证",
        "description": (
            "Pentool 免费核心与 PRO 许可证：漏洞扫描器、侦察、本地 AI 和报告。一个密钥，机器数量由你选择。"
        ),
        "intro": {
            "eyebrow": "价格",
            "title": "免费核心。PRO 提供扫描器、侦察和报告",
            "lead": ("核心以 AGPL-3.0 发布：无需注册，没有时间限制。PRO 是单独的一年期密钥，机器数量在购买时选择。"),
        },
        "sections": [
            {
                "id": "plans",
                "blocks": [
                    {
                        "t": "plans",
                        "items": [
                            {
                                "name": "Free",
                                "price": "$0",
                                "period": "永久，无需注册",
                                "features": [
                                    {
                                        "ok": True,
                                        "text": "Proxy：拦截、历史、WebSocket、Match &amp; Replace、scope",
                                    },
                                    {"ok": True, "text": "带标签页和响应对比的 Repeater"},
                                    {"ok": True, "text": "Intruder：四种模式，最多 5 个线程"},
                                    {"ok": True, "text": "Utils：Decoder（19 种操作）、Comparer、Sequencer"},
                                    {"ok": True, "text": "Spider、Target 和站点地图"},
                                    {"ok": True, "text": "插件：界面、检查、CLI 命令"},
                                    {"ok": True, "text": "在 CI 中无界面扫描"},
                                    {"ok": False, "text": "漏洞扫描器"},
                                    {"ok": False, "text": "侦察（Recon）"},
                                ],
                                "cta": {"label": "免费安装", "href": "@index#install", "style": "ghost"},
                            },
                            {
                                "name": "PRO",
                                "badge": "PRO",
                                "featured": True,
                                "price_from_config": True,
                                "suffix": "/年",
                                "period_template": "{n} 个槽位 · 每增加一个 +$19/年",
                                "slots_picker": True,
                                "features": [
                                    {"ok": True, "text": "免费版的全部功能"},
                                    {"ok": True, "text": "<strong>扫描器：21 项检查</strong> —— 主动和被动"},
                                    {
                                        "ok": True,
                                        "text": "<strong>侦察：</strong> 子域名、端点、CDN 背后的真实 IP",
                                    },
                                    {"ok": True, "text": "本地 AI：payload、WAF 绕过、发现分析"},
                                    {"ok": True, "text": "HTML、JSON、CSV 报告 + Bug Bounty 模板汇总报告"},
                                    {"ok": True, "text": "导出到 HackerOne、Bugcrowd、DefectDojo"},
                                    {"ok": True, "text": "Intruder Turbo：连接池，最多 200 个线程"},
                                    {"ok": True, "text": "优先邮件支持"},
                                ],
                                "cta": {"label": "购买 PRO", "action": "buy", "style": "primary"},
                                "note": (
                                    "通过 Coinso 用加密货币付款。密钥会发到你填写的 e-mail；"
                                    "如果没收到邮件，请带订单号联系支持。"
                                ),
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": ("价格以美元标注，账单由支付服务商按其汇率以卢布生成。"),
                    },
                ],
            },
            {
                "id": "compare",
                "eyebrow": "对比",
                "title": "密钥究竟解锁什么",
                "blocks": [
                    {
                        "t": "table",
                        "head": ["功能", "Free", "PRO"],
                        "rows": [
                            ["代理：拦截、历史、WebSocket", "✓", "✓"],
                            ["Repeater：标签页、重放、对比", "✓", "✓"],
                            ["Intruder：Sniper、Battering Ram、Pitchfork、Cluster Bomb", "✓", "✓"],
                            ["Intruder Turbo：连接池，最多 200 个线程", "—", "✓"],
                            ["Utils：Decoder、Comparer、Sequencer", "✓", "✓"],
                            ["Spider、Target、scope、Match &amp; Replace", "✓", "✓"],
                            ["漏洞扫描器：21 项检查，主动和被动", "—", "✓"],
                            ["侦察：子域名、端点、真实 IP、模糊测试", "—", "✓"],
                            ["本地 AI：生成 payload、WAF 绕过、发现分析", "—", "✓"],
                            ["报告与导出：HTML、JSON、CSV、HackerOne、Bugcrowd、DefectDojo", "—", "✓"],
                            ["在 CI/CD 中无界面扫描", "✓", "✓"],
                        ],
                    },
                ],
            },
            {
                "id": "payment",
                "eyebrow": "付款",
                "title": "购买流程",
                "lead": (
                    "你选择机器数量并留下 e-mail。随后会打开 Coinso 的支付页面——加密货币，不用银行卡，也不用银行转账。"
                ),
                "blocks": [
                    {
                        "t": "steps",
                        "items": [
                            {
                                "title": "选择槽位",
                                "text": "一个槽位对应一台机器。价格立即算出：第一个槽位每年 $29，之后每个 +$19。",
                            },
                            {
                                "title": "留下 e-mail",
                                "text": "密钥会发到这个地址。它同时也是支持时用的许可证名称，这样更容易找到订单。",
                            },
                            {
                                "title": "用加密货币付款",
                                "text": "Coinso 会开出含确切金额和网络的账单。付款后密钥自动生成。",
                            },
                            {
                                "title": "激活密钥",
                                "text": "Settings → License → Activate。首次激活会占用一个槽位并把它绑定到这台机器。",
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": (
                            "半小时内还没收到密钥？请写信到 "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>，注明订单号'
                            "和 e-mail——我们会手动发放密钥。"
                        ),
                    },
                ],
            },
            {
                "id": "activation",
                "eyebrow": "许可证",
                "title": "槽位、迁移和离线使用",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "<strong>槽位。</strong> 机器数量在购买时指定。在新机器上激活会占用一个空闲槽位，反激活则释放它。",
                            "<strong>迁移。</strong> 在旧机器上反激活密钥，或请支持迁移绑定。",
                            "<strong>离线。</strong> 密钥在启动时校验并缓存。没有网络时 PRO 最多可用 7 天，之后会要求联网。",
                            "<strong>到期。</strong> PRO 模块不再打开，免费部分照常工作。密钥和槽位都会保留，以便续费。",
                        ],
                    },
                ],
            },
            {
                "id": "faq",
                "eyebrow": "问题",
                "title": "简要回答",
                "blocks": [
                    {
                        "t": "faq",
                        "items": [
                            {
                                "q": "免费版需要注册吗？",
                                "a": "不需要。<code>uv tool install pentool</code>——然后就开始工作。没有邮箱、没有账号、没有有效期。",
                            },
                            {
                                "q": "PRO 密钥解锁什么？",
                                "a": "漏洞扫描器、侦察、本地 AI、带导出的报告，以及 Intruder 的 Turbo 模式。上面的表格是完整清单。",
                            },
                            {
                                "q": "购买前可以先看看 PRO 吗？",
                                "a": "请联系支持——我们会手动开通 14 天的试用访问。",
                            },
                            {
                                "q": "可以激活几台机器？",
                                "a": "买了多少个槽位就能激活多少台。一个槽位一台机器；迁移时旧机器上的槽位会被释放。",
                            },
                            {
                                "q": "一年到期后会发生什么？",
                                "a": "PRO 模块关闭，其余部分继续工作。密钥和槽位都保留——续费即恢复访问。",
                            },
                            {
                                "q": "Pentool 会把数据发送到服务器吗？",
                                "a": (
                                    "只发送必要的部分：启动时校验密钥（密钥和机器标识符的哈希）、"
                                    "一次性的安装 ping 和崩溃报告。流量、发现和项目都留在你的机器上，"
                                    "AI 在本地运行。崩溃报告可以在设置里关闭。"
                                ),
                            },
                            {
                                "q": "怎么退款？",
                                "a": (
                                    "购买后 14 天内——请用购买时的 e-mail 和密钥写信到 "
                                    '<a href="mailto:support@pentool.pro">support@pentool.pro</a>。'
                                    "密钥会被停用，槽位会被释放。"
                                ),
                            },
                            {
                                "q": "有面向团队的方案吗？",
                                "a": "没有单独的方案。如果机器有多台，就买带所需槽位数的密钥。",
                            },
                        ],
                    },
                ],
            },
        ],
    },
    "privacy": {
        "title": "Pentool — 隐私政策",
        "description": (
            "Pentool 会把什么发送到服务器、什么留在你的机器上：许可证校验、安装遥测、崩溃报告、本地 AI 和密钥购买。"
        ),
        "intro": {
            "title": "隐私政策",
            "note": "更新于 2026 年 11 月 24 日",
            "lead": (
                "Pentool 是本地工具：流量、项目和发现都留在你的机器上。"
                "这里说明所有离开本机的内容、为什么离开，以及怎么关闭。"
            ),
        },
        "sections": [
            {
                "id": "short",
                "blocks": [
                    {
                        "t": "note",
                        "text": (
                            "<strong>简要说明。</strong> 我们收不到你的流量、请求、响应、发现"
                            "和项目数据库。购买许可证时我们会收到 e-mail 和密钥数据。"
                            "崩溃报告可以关闭。"
                        ),
                    }
                ],
            },
            {
                "id": "controller",
                "title": "1. 谁负责数据",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "数据控制者：Anatoly Kashtanov (DoctorX)，Pentool 的作者。"
                            "任何涉及个人数据的请求："
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>。'
                        ),
                    }
                ],
            },
            {
                "id": "sent",
                "title": "2. 应用发送什么，什么时候发送",
                "blocks": [
                    {
                        "t": "table",
                        "head": ["内容", "时间", "具体是什么", "可以关闭吗？"],
                        "rows": [
                            [
                                "许可证校验",
                                "带 PRO 密钥启动时，之后从缓存读取",
                                "密钥字符串、机器标识符的哈希、应用版本",
                                "使用 PRO 期间——不能",
                            ],
                            [
                                "安装 ping",
                                "每次安装一次",
                                "随机的安装标识符、操作系统和版本——不含流量和个人数据",
                                "可以，在设置里",
                            ],
                            [
                                "崩溃报告",
                                "仅在异常结束时",
                                "traceback、错误类型、版本、操作系统与架构、来源（tui 或 cli）",
                                "可以——<code>send_crash_reports: false</code>",
                            ],
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "发送前会从 traceback 中剔除类似令牌的行。报告保存在部署于 "
                            "Cloudflare Workers 的许可证服务上。"
                        ),
                    },
                ],
            },
            {
                "id": "local-ai",
                "title": "3. 人工智能在本地运行",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool 的 AI 功能由一个本地模型提供：它作为独立进程在你的机器上"
                            "运行。请求、响应和发现都不会发给我们，也不发往云服务。唯一的联网"
                            "行为是：如果你启用了模型，会一次性下载模型文件。"
                        ),
                    }
                ],
            },
            {
                "id": "not-collected",
                "title": "4. 我们不收集什么",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "经代理的请求和响应、cookie、凭据、会话令牌；",
                            "发现、站点地图、项目数据库和你磁盘上的文件；",
                            "按键、剪贴板、屏幕内容和终端历史；",
                            "本站上的分析代码和广告标识符。",
                        ],
                    }
                ],
            },
            {
                "id": "purchases",
                "title": "5. 购买许可证",
                "blocks": [
                    {
                        "t": "p",
                        "text": "购买 PRO 时我们会处理：",
                    },
                    {
                        "t": "list",
                        "items": [
                            "<strong>e-mail</strong> —— 密钥发到这里，它同时作为许可证名称用于支持和续费；",
                            "<strong>槽位数、金额和付款日期</strong> —— 用于账务和续费；",
                            "<strong>支付数据</strong> —— 由服务商 Coinso 和支付网络处理；我们看不到钱包私钥和银行卡数据。",
                        ],
                    },
                    {
                        "t": "p",
                        "text": ("处理的依据是履行合同（发放许可证）和会计核算的要求。购买记录按税法要求的期限保存。"),
                    },
                ],
            },
            {
                "id": "activation",
                "title": "6. 激活数据",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "每次激活都会在许可证服务上保存密钥和机器标识符的哈希——"
                            "用于统计已占用的槽位并支持许可证迁移。"
                            "机器标识符是系统标识符的哈希，不用于识别个人。"
                        ),
                    }
                ],
            },
            {
                "id": "files",
                "title": "7. 你机器上的数据",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool 会写入 <code>~/.config/pentool/</code>：设置、许可证缓存、"
                            "日志、用于拦截 HTTPS 的证书、项目数据库和插件。AI 模型位于 "
                            "<code>~/.pentool/ai/models</code>。这些数据不会离开本机，"
                            "除非你自己把它们发出去。删除该目录即删除全部内容。"
                        ),
                    }
                ],
            },
            {
                "id": "site",
                "title": "8. Cookie 与本站",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "本站是静态的：不设置 cookie，不加载分析代码和第三方脚本。"
                            "支付页面归服务商所有，按其规则运行。"
                        ),
                    }
                ],
            },
            {
                "id": "rights",
                "title": "9. 你的权利",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "视你所在的司法辖区而定（GDPR、152-FZ 等），你可以要求访问自己的"
                            "数据、更正、删除或导出它们，反对处理，并向监管机构申诉。请写信到 "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>——'
                            "我们会在 30 天内答复。"
                        ),
                    }
                ],
            },
            {
                "id": "retention",
                "title": "10. 保存期限",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "崩溃报告 —— 最多 12 个月；",
                            "购买和许可证记录 —— 许可证有效期加上税法要求的期限；",
                            "安装计数 —— 只有聚合数值，没有按用户的记录。",
                        ],
                    }
                ],
            },
            {
                "id": "children",
                "title": "11. 儿童",
                "blocks": [
                    {
                        "t": "p",
                        "text": "Pentool 是专业安全工具，不面向 18 岁以下人士。",
                    }
                ],
            },
            {
                "id": "changes",
                "title": "12. 政策变更",
                "blocks": [
                    {
                        "t": "p",
                        "text": ("新版本会连同新日期发布在这里，并自发布之时起生效。"),
                    }
                ],
            },
            {
                "id": "contacts",
                "title": "13. 联系方式",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            '关于数据的问题和请求：<a href="mailto:support@pentool.pro">support@pentool.pro</a>。'
                        ),
                    }
                ],
            },
        ],
    },
    "terms": {
        "title": "Pentool — 用户协议",
        "description": ("使用 Pentool 与购买 PRO 许可证的条款：允许做什么、密钥如何工作、加密货币付款、退款与责任。"),
        "intro": {
            "title": "用户协议",
            "note": "更新于 2026 年 11 月 24 日",
            "lead": ("本协议规定 Pentool 程序的使用和 PRO 许可证的购买。安装程序或激活密钥即表示同意这些条款。"),
        },
        "sections": [
            {
                "id": "core-license",
                "blocks": [
                    {
                        "t": "note",
                        "text": (
                            "Pentool 的免费核心按 GNU Affero General "
                            "Public License v3.0 发布——其条款位于 "
                            '<a href="@link:license">LICENSE</a> 文件，适用于代码的开源部分。'
                            "本协议涉及的是付费功能、密钥和购买。"
                        ),
                    }
                ],
            },
            {
                "id": "who",
                "title": "1. 谁提供本程序",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "本程序和 PRO 许可证由以 Pentool 名义发布内容的开发者提供："
                            "Anatoly Kashtanov (DoctorX)。联系方式："
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>。'
                        ),
                    }
                ],
            },
            {
                "id": "grant",
                "title": "2. 密钥赋予什么",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "PRO 密钥授予非独占的使用权：在随密钥一起购买的那些机器"
                            "（“槽位”）上，于已付费的期限内使用付费功能——默认一年。"
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "一个槽位对应一台机器；反激活会释放槽位；",
                            "密钥不得转售、公开，也不得用于提供竞争性服务；",
                            "迁移许可证可通过在旧机器上反激活或联系支持完成。",
                        ],
                    },
                ],
            },
            {
                "id": "trial",
                "title": "3. 试用访问",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "14 天的试用访问需向支持申请开通。每位个人或组织只提供一次；"
                            "为绕过购买而重复申请的，不予发放。"
                        ),
                    }
                ],
            },
            {
                "id": "payment",
                "title": "4. 付款与价格",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "付款由第三方服务商 Coinso 受理；付款通过加密货币完成；",
                            "价格以美元/年标注在价格页，取决于槽位数量；应付金额由支付页面显示，账单按服务商的汇率以卢布生成；",
                            "密钥发送到购买时填写的 e-mail；该地址同时作为许可证名称保存，用于支持和续费；",
                            "如果需要开给单位的发票，请在付款前联系支持。",
                        ],
                    }
                ],
            },
            {
                "id": "refunds",
                "title": "5. 退款",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "购买后 14 天内可全额退款。请用购买时填写的地址写信到 "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>，'
                            "并附上密钥。退款时密钥会被停用，槽位会被释放。"
                        ),
                    }
                ],
            },
            {
                "id": "acceptable",
                "title": "6. 可接受的使用",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool 是安全测试工具。你同意仅针对你拥有或已获得书面许可测试的"
                            "系统使用它。以下事项由你负责："
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "在开始测试前取得系统所有者的许可；",
                            "遵守你所在司法辖区的法律和适用的法规；",
                            "测试造成的后果，包括对他人系统造成的负载。",
                        ],
                    },
                    {
                        "t": "p",
                        "text": ("我们不许可也不协助对计算机系统的未授权访问，并且不对这类使用承担责任。"),
                    },
                ],
            },
            {
                "id": "validation",
                "title": "7. 密钥校验与遥测",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "PRO 功能在启动时通过许可证服务校验密钥。外发的只有密钥和"
                            "机器标识符的哈希；结果会被缓存，因此可以短时间离线工作。"
                            "崩溃报告是可选的，可以关闭——详情见"
                            '<a href="@privacy">隐私政策</a>。'
                        ),
                    }
                ],
            },
            {
                "id": "updates",
                "title": "8. 程序更新",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "我们会发布可能增加、修改和移除功能的更新。"
                            "购买时价格页上列出的付费功能会在已付费的期限内提供；"
                            "如果某项功能永久消失，我们会按请求退还未使用期间的相应费用。"
                        ),
                    }
                ],
            },
            {
                "id": "warranty",
                "title": "9. 保证与责任",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "本程序按“现状”提供，不附带任何明示或默示的保证，"
                            "包括对特定用途的适用性。在法律允许的最大范围内："
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "我们不对间接和偶发损失、利润损失、数据丢失和业务中断负责；",
                            "累计责任以索赔前 12 个月内为许可证支付的金额为限。",
                        ],
                    },
                    {
                        "t": "p",
                        "text": "本条款中的任何内容都不限制法律不允许限制的责任。",
                    },
                ],
            },
            {
                "id": "termination",
                "title": "10. 终止",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "如果密钥被用于违反第 2 条（转售和公开）或第 6 条（未授权测试）的"
                            "行为，我们可以停用密钥且不退款。你可以随时停止使用本程序；"
                            "删除程序并不赋予第 5 条规定之外的退款权利。"
                        ),
                    }
                ],
            },
            {
                "id": "terms-changes",
                "title": "11. 协议变更",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "以本页面发布的、标注了日期的版本为准。"
                            "重大变更适用于发布之后的购买；已购买的许可证继续按购买时的条件工作。"
                        ),
                    }
                ],
            },
            {
                "id": "law",
                "title": "12. 适用法律",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "本协议适用权利人居住国的法律，除非你所在司法辖区的强制性规定"
                            "另有要求。争议通过协商解决，协商不成时提交有管辖权的法院。"
                        ),
                    }
                ],
            },
            {
                "id": "contacts",
                "title": "13. 联系方式",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            '关于条款和许可证的问题：<a href="mailto:support@pentool.pro">support@pentool.pro</a>。'
                        ),
                    }
                ],
            },
        ],
    },
    "success": {
        "title": "Pentool — 已收到付款",
        "description": "付款成功：PRO 密钥会发送到填写的 e-mail。",
        "intro": {
            "title": "已收到付款",
            "lead": ("谢谢。密钥会发送到付款时填写的 e-mail，通常在几分钟内。如果没收到邮件，请检查“垃圾邮件”文件夹。"),
        },
        "sections": [
            {
                "id": "next",
                "blocks": [
                    {
                        "t": "steps",
                        "items": [
                            {
                                "title": "找到含密钥的邮件",
                                "text": "邮件里有形如 <code>PTOOL-XXXX-XXXX-XXXX</code> 的密钥和购买的槽位数。",
                            },
                            {
                                "title": "在程序里激活",
                                "text": "Pentool → Settings → License → Activate。首次激活会占用一个槽位，并把它绑定到这台机器。",
                            },
                            {
                                "title": "如果没收到邮件",
                                "text": "写信到 support@pentool.pro，注明订单号和付款用的 e-mail——我们会手动发放密钥。",
                            },
                        ],
                    },
                    {
                        "t": "buttons",
                        "items": [
                            {"label": "返回价格页", "href": "@pricing", "style": "primary"},
                            {"label": "联系支持", "href": "@link:email", "style": "ghost"},
                        ],
                    },
                ],
            }
        ],
    },
    "fail": {
        "title": "Pentool — 付款未完成",
        "description": "支付未成功：没有扣款，也没有发放密钥。",
        "intro": {
            "title": "付款未完成",
            "lead": (
                "没有扣款，也没有发放密钥：账单已过期，或者付款在完成前被取消。"
                "可以重新开始——槽位数量和付款方式在价格页选择。"
            ),
        },
        "sections": [
            {
                "id": "what-now",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "如果银行仍显示有扣款，通常是金额的临时冻结——它会自动解除。"
                            "如果一直存在，请写信到 "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>，注明'
                            "支付编号和日期。"
                        ),
                    },
                    {
                        "t": "buttons",
                        "items": [
                            {"label": "重试", "href": "@pricing", "style": "primary"},
                            {"label": "联系支持", "href": "@link:email", "style": "ghost"},
                        ],
                    },
                ],
            }
        ],
    },
}
