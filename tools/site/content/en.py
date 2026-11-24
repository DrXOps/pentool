"""English content — mirrors ``ru.py`` key for key (parity is enforced by the build)."""

from __future__ import annotations

LANG = "en"

NAV = {
    "features": "Features",
    "install": "Install",
    "pricing": "Pricing",
    "docs": "Documentation",
}

UI = {
    "skip": "Skip to content",
    "menu": "Sections",
    "slots_label": "How many machines will you activate?",
    "slots_hint": "One slot is one machine. You can move the licence to another machine at any time.",
    "buy_title": "Buy Pentool PRO",
    "buy_text": (
        "Leave your e-mail — the key goes there. Next comes the Coinso payment page; payment is made in cryptocurrency."
    ),
    "buy_email": "E-mail for the key",
    "buy_hint": "If the letter does not arrive, write to support with your order number.",
    "buy_confirm": "Continue to payment",
    "buy_slots": "Slots: {n}",
    "buy_waiting": "Creating the invoice…",
    "err_email": "That address looks off — please check the e-mail.",
    "err_checkout": "Could not create the invoice. Write to support: support@pentool.pro",
    "close": "Close",
}

FOOTER = {
    "blurb": "Pentesting in the terminal: interception, attacks, scanner and reports in one project. Open-source core.",
    "groups": [
        {
            "title": "Product",
            "links": [
                {"label": "Features", "href": "@index#features"},
                {"label": "Modules", "href": "@index#modules"},
                {"label": "Install", "href": "@index#install"},
                {"label": "Pricing and PRO", "href": "@pricing"},
            ],
        },
        {
            "title": "Documentation",
            "links": [
                {"label": "Quick start", "href": "@docs:quickstart"},
                {"label": "User guide", "href": "@docs:user_guide"},
                {"label": "Scanning in CI", "href": "@link:ci_guide"},
                {"label": "Plugin API", "href": "@link:plugin_api"},
                {"label": "Source code", "href": "@link:github"},
            ],
        },
        {
            "title": "Contact",
            "links": [
                {"label": "Support", "href": "@link:email"},
                {"label": "Telegram channel", "href": "@link:telegram_channel"},
                {"label": "Author", "href": "@link:telegram_author"},
                {"label": "Report a bug", "href": "@link:issues"},
            ],
        },
        {
            "title": "Legal",
            "links": [
                {"label": "Terms of Service", "href": "@terms"},
                {"label": "Privacy Policy", "href": "@privacy"},
                {"label": "AGPL-3.0 licence", "href": "@link:license"},
                {"label": "Licence portal", "href": "@link:license_portal"},
            ],
        },
    ],
    "legal": "© 2024–2026 Anatoly Kashtanov (DoctorX). Pentool is an independent project.",
    "built": "This site is static HTML — no analytics, no trackers.",
}

PAGES = {
    "index": {
        "title": "Pentool — web pentesting in your terminal",
        "description": (
            "Pentool is a terminal tool for web pentesting: proxy, repeater, intruder, vulnerability "
            "scanner, reconnaissance and reports. Open-source core."
        ),
        "hero": {
            "kicker": "A pentest toolkit for the terminal",
            "h1": "Web pentesting <em>in one terminal</em> window",
            "lead": (
                "Intercept and replay requests, run payload attacks, scan for vulnerabilities, map the "
                "target and export reports. One project instead of a dozen windows, a browser and a heavy IDE."
            ),
            "buttons": [
                {"label": "Buy PRO", "href": "@pricing", "style": "primary"},
                {"label": "Download free", "href": "#install", "style": "ghost"},
            ],
            "meta": ["Linux · macOS · Windows (WSL)", "Python 3.10+", "Core under AGPL-3.0"],
        },
        "sections": [
            {
                "id": "features",
                "eyebrow": "Why it exists",
                "title": "Fewer switches, more work",
                "lead": (
                    "Pentool does not try to replace your whole toolkit. It removes the shuffling between "
                    "tools: the target, the requests, the findings and the report live in one project."
                ),
                "blocks": [
                    {
                        "t": "cards",
                        "items": [
                            {
                                "title": "The target is one command",
                                "text": (
                                    "<code>pentool --url https://target</code> creates a project, adds the "
                                    "target and starts the proxy. Requests appear in the history right away."
                                ),
                            },
                            {
                                "title": "Runs over SSH",
                                "text": (
                                    "A terminal, tmux, a server with no desktop. Keyboard and mouse, dark "
                                    "and light themes — nothing to configure on the client side."
                                ),
                            },
                            {
                                "title": "A project is a folder",
                                "text": (
                                    "Traffic history, findings and reports sit in SQLite next to the project: "
                                    "come back in a month or hand it to a colleague."
                                ),
                            },
                            {
                                "title": "Reports, not screenshots",
                                "text": (
                                    "Findings export to HTML, JSON or CSV, plus a bulk Bug Bounty report and "
                                    "exports for HackerOne, Bugcrowd and DefectDojo."
                                ),
                            },
                        ],
                    }
                ],
            },
            {
                "id": "modules",
                "eyebrow": "Modules",
                "title": "Ten tabs, ten jobs",
                "lead": (
                    "Switch with a hotkey, tab state survives restarts. The scanner and reconnaissance open "
                    "with a PRO key; everything else is available immediately."
                ),
                "blocks": [
                    {
                        "t": "modules",
                        "items": [
                            {
                                "name": "Dashboard",
                                "text": "Project overview: what was found, what is running, quick actions.",
                            },
                            {
                                "name": "Proxy",
                                "text": "HTTP/HTTPS and WebSocket interception, request history, Match &amp; Replace rules, scope.",
                            },
                            {
                                "name": "Repeater",
                                "text": "Edit and replay requests in tabs, compare against the previous response.",
                            },
                            {
                                "name": "Intruder",
                                "text": "Sniper, Battering Ram, Pitchfork, Cluster Bomb. Your own thread and delay limits, results in a table.",
                            },
                            {
                                "name": "Scanner",
                                "tag": "PRO",
                                "text": "Active and passive checks: SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE and more.",
                            },
                            {
                                "name": "Target",
                                "text": "Site map built from proxy traffic, scope rules, per-host filters.",
                            },
                            {
                                "name": "Utils",
                                "text": "Decoder (19 chained operations), Comparer (line diff), Sequencer (entropy and FIPS tests).",
                            },
                            {
                                "name": "Extensions",
                                "text": "Plugins: your own screens, scanner checks, passive checks and commands.",
                            },
                            {
                                "name": "Recon",
                                "tag": "PRO",
                                "text": "Subdomains, endpoints, real IP behind a CDN, parameter fuzzing.",
                            },
                            {
                                "name": "Settings",
                                "text": "Themes, network, proxy, licence, local AI.",
                            },
                        ],
                        "copy": "Decoder, Comparer and Sequencer have their own sub-tabs inside Utils.",
                    }
                ],
            },
            {
                "id": "scanner",
                "eyebrow": "Scanner · PRO",
                "title": "What it actually checks",
                "lead": (
                    "Active checks send requests to the target and confirm a finding; passive checks read "
                    "the responses that already flow through the proxy."
                ),
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "<strong>Injection:</strong> SQLi (error-, time- and boolean-based, UNION), NoSQL, "
                            "SSTI, LFI, path traversal, RCE, header and host header injection",
                            "<strong>Client side:</strong> XSS, DOM XSS, prototype pollution, open redirect",
                            "<strong>Access and data:</strong> broken auth, JWT none, OAuth, CORS, "
                            "sensitive data in responses",
                            "<strong>Services:</strong> SSRF, XXE, GraphQL",
                            "<strong>Passive:</strong> missing security headers, information leaks, "
                            "sensitive data, DOM XSS",
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "Findings land in a table with severity, evidence and the request that produced "
                            "them — ready to replay in Repeater. Reports export to HTML, JSON or CSV; the bulk "
                            "one follows the Bug Bounty template."
                        ),
                    },
                    {
                        "t": "note",
                        "text": "The check list grows between releases. If yours is missing, a plugin can add one.",
                    },
                ],
            },
            {
                "id": "ai",
                "eyebrow": "Artificial intelligence",
                "title": "The model runs on your machine, not in a cloud",
                "lead": (
                    "AI in Pentool is a small local model. It runs on your CPU, is off by default and "
                    "sends nothing outside your machine."
                ),
                "blocks": [
                    {
                        "t": "cards",
                        "items": [
                            {
                                "title": "What it does",
                                "text": (
                                    "Picks checks for the target's technology, generates payloads, tries WAF "
                                    "bypass for XSS, re-checks findings and suggests endpoints while crawling."
                                ),
                            },
                            {
                                "title": "Where it runs",
                                "text": (
                                    "On your machine: a model of about 350 MB is downloaded once and runs on "
                                    "the CPU — no graphics card needed."
                                ),
                            },
                            {
                                "title": "What leaves",
                                "text": (
                                    "Requests, responses and findings stay in the project. Pentool has no "
                                    "cloud provider — there is nowhere for the traffic to go."
                                ),
                            },
                            {
                                "title": "When to enable it",
                                "text": (
                                    "Optional, in Settings → AI. Without the model the regular checks still "
                                    "run and finding analysis falls back to simple heuristics."
                                ),
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": "AI is an assistant, not a replacement for checks: the final call on a finding is yours.",
                    },
                ],
            },
            {
                "id": "ci",
                "eyebrow": "Automation",
                "title": "Scanning inside a pipeline",
                "lead": (
                    "The same scanner runs without the interface — <code>--headless</code>. Works in GitHub "
                    "Actions, GitLab CI and any shell."
                ),
                "blocks": [
                    {
                        "t": "term",
                        "title": "bash",
                        "lines": [
                            {"k": "cmd", "text": "$ pentool --url https://example.com --headless \\"},
                            {"k": "cmd", "text": "    --check xss,sqli --threads 20 --delay 0.2 \\"},
                            {"k": "cmd", "text": "    --format html --output report.html"},
                            {"k": "dim", "text": "# exit code: 0 — success, 1 — scan failed, 2 — bad arguments"},
                        ],
                        "copy": (
                            "More flags: <code>--crawl --depth</code>, <code>--ai</code>, <code>--format json</code>."
                        ),
                    },
                    {
                        "t": "p",
                        "text": (
                            "Your own checks ship as a plugin: <code>BasePlugin</code> can register a screen, "
                            "a CLI command, a scanner check and a passive check. Plugins live in "
                            "<code>~/.config/pentool/plugins</code>, the API is documented."
                        ),
                    },
                ],
            },
            {
                "id": "install",
                "eyebrow": "Installation",
                "title": "Two commands to the first request",
                "lead": "The package comes from PyPI. No Docker, no JDK, no external proxy.",
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
                            "No <code>uv</code>? <code>pip install pentool</code> works too. "
                            "Pentool creates its own certificate for HTTPS."
                        ),
                    },
                    {
                        "t": "note",
                        "text": (
                            "Use a modern terminal: Windows Terminal, iTerm2, GNOME Terminal, Kitty, "
                            "Alacritty or WezTerm. On Windows, WSL2 is the smoother path."
                        ),
                    },
                ],
            },
            {
                "id": "start",
                "blocks": [
                    {
                        "t": "cta",
                        "title": "Try it on your own project",
                        "text": (
                            "The free core has no time limit. PRO is needed for the scanner, reconnaissance "
                            "and reports."
                        ),
                        "buttons": [
                            {"label": "Download free", "href": "#install", "style": "primary"},
                            {"label": "Buy PRO", "href": "@pricing", "style": "ghost"},
                        ],
                    }
                ],
            },
        ],
    },
    "pricing": {
        "title": "Pentool — pricing and PRO licence",
        "description": (
            "Free Pentool core and the PRO licence: vulnerability scanner, reconnaissance, local AI and "
            "reports. One key with the number of machines you choose."
        ),
        "intro": {
            "eyebrow": "Pricing",
            "title": "Free core. PRO adds the scanner, reconnaissance and reports",
            "lead": (
                "The core is released under AGPL-3.0: no sign-up, no time limit. PRO is a separate annual "
                "key; you choose the number of machines when you buy."
            ),
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
                                "period": "forever, no sign-up",
                                "features": [
                                    {
                                        "ok": True,
                                        "text": "Proxy: interception, history, WebSocket, Match &amp; Replace, scope",
                                    },
                                    {"ok": True, "text": "Repeater with tabs and response comparison"},
                                    {"ok": True, "text": "Intruder: four attack modes, up to 5 threads"},
                                    {"ok": True, "text": "Utils: Decoder (19 operations), Comparer, Sequencer"},
                                    {"ok": True, "text": "Spider, Target and the site map"},
                                    {"ok": True, "text": "Plugins: screens, checks, CLI commands"},
                                    {"ok": True, "text": "Headless scanning in CI"},
                                    {"ok": False, "text": "Vulnerability scanner"},
                                    {"ok": False, "text": "Reconnaissance (Recon)"},
                                ],
                                "cta": {"label": "Install free", "href": "@index#install", "style": "ghost"},
                            },
                            {
                                "name": "PRO",
                                "badge": "PRO",
                                "featured": True,
                                "price_from_config": True,
                                "suffix": "/year",
                                "period_template": "{n} slot · each extra +$19/year",
                                "slots_picker": True,
                                "features": [
                                    {"ok": True, "text": "Everything in the free version"},
                                    {"ok": True, "text": "<strong>Scanner: 21 checks</strong> — active and passive"},
                                    {
                                        "ok": True,
                                        "text": "<strong>Reconnaissance:</strong> subdomains, endpoints, real IP behind a CDN",
                                    },
                                    {"ok": True, "text": "Local AI: payloads, WAF bypass, finding analysis"},
                                    {"ok": True, "text": "Reports in HTML, JSON, CSV plus a bulk Bug Bounty report"},
                                    {"ok": True, "text": "Exports for HackerOne, Bugcrowd, DefectDojo"},
                                    {"ok": True, "text": "Intruder Turbo: connection pool and up to 200 threads"},
                                    {"ok": True, "text": "Priority e-mail support"},
                                ],
                                "cta": {"label": "Buy PRO", "action": "buy", "style": "primary"},
                                "note": (
                                    "Payment in cryptocurrency via Coinso. The key goes to the e-mail you "
                                    "provide; if it does not arrive, write to support with the order number."
                                ),
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": (
                            "Prices are shown in US dollars; the provider issues the invoice in rubles at its own rate."
                        ),
                    },
                ],
            },
            {
                "id": "compare",
                "eyebrow": "Comparison",
                "title": "What the key unlocks",
                "blocks": [
                    {
                        "t": "table",
                        "head": ["Capability", "Free", "PRO"],
                        "rows": [
                            ["Proxy: interception, history, WebSocket", "✓", "✓"],
                            ["Repeater: tabs, replay, comparison", "✓", "✓"],
                            ["Intruder: Sniper, Battering Ram, Pitchfork, Cluster Bomb", "✓", "✓"],
                            ["Intruder Turbo: connection pool, up to 200 threads", "—", "✓"],
                            ["Utils: Decoder, Comparer, Sequencer", "✓", "✓"],
                            ["Spider, Target, scope, Match &amp; Replace", "✓", "✓"],
                            ["Vulnerability scanner: 21 checks, active and passive", "—", "✓"],
                            ["Reconnaissance: subdomains, endpoints, real IP, fuzzing", "—", "✓"],
                            ["Local AI: payload generation, WAF bypass, analysis", "—", "✓"],
                            ["Reports and exports: HTML, JSON, CSV, HackerOne, Bugcrowd, DefectDojo", "—", "✓"],
                            ["Headless scanning in CI/CD", "✓", "✓"],
                        ],
                    },
                ],
            },
            {
                "id": "payment",
                "eyebrow": "Payment",
                "title": "How buying works",
                "lead": (
                    "You choose the number of machines and leave an e-mail. Then the Coinso payment page "
                    "opens — cryptocurrency only, no cards or bank transfers."
                ),
                "blocks": [
                    {
                        "t": "steps",
                        "items": [
                            {
                                "title": "Pick the slots",
                                "text": "One slot is one machine. The price updates right away: $29 a year for the first slot, +$19 for each extra one.",
                            },
                            {
                                "title": "Leave an e-mail",
                                "text": "The key goes to that address. It also names the licence for support, which makes orders easy to find.",
                            },
                            {
                                "title": "Pay in cryptocurrency",
                                "text": "Coinso issues an invoice with the exact amount and network. The key is generated automatically after payment.",
                            },
                            {
                                "title": "Activate the key",
                                "text": "Settings → License → Activate. The first activation takes a slot and binds it to that machine.",
                            },
                        ],
                    },
                    {
                        "t": "note",
                        "text": (
                            "No key within half an hour? Write to "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a> with the order number '
                            "and e-mail — we will issue it by hand."
                        ),
                    },
                ],
            },
            {
                "id": "activation",
                "eyebrow": "Licence",
                "title": "Slots, moving machines and offline work",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "<strong>Slots.</strong> The number of machines is fixed at purchase. Activating on a new machine takes a free slot; deactivating frees it.",
                            "<strong>Moving.</strong> Deactivate the key on the old machine, or ask support to move the binding.",
                            "<strong>Offline.</strong> The key is validated at startup and cached. Without a network, PRO keeps working for up to 7 days.",
                            "<strong>Expiry.</strong> PRO modules stop opening, the free part keeps working. The key and its slots stay for renewal.",
                            "<strong>From a terminal.</strong> The same actions exist in the CLI: <code>pentool license activate KEY</code>, <code>pentool license status</code>, <code>pentool license trial</code> — handy on a server and in CI.",
                        ],
                    },
                ],
            },
            {
                "id": "faq",
                "eyebrow": "Questions",
                "title": "The short answers",
                "blocks": [
                    {
                        "t": "faq",
                        "items": [
                            {
                                "q": "Do I need an account for the free version?",
                                "a": "No. <code>uv tool install pentool</code> and you are working. No e-mail, no account, no expiry.",
                            },
                            {
                                "q": "What does a PRO key unlock?",
                                "a": "The vulnerability scanner, reconnaissance, the local AI, reports with exports and Intruder Turbo. The table above is the complete list.",
                            },
                            {
                                "q": "Can I try PRO before buying?",
                                "a": (
                                    "Yes: Settings → License → «Start 14-day trial», or the command "
                                    "<code>pentool license trial</code>. One trial per machine, no key "
                                    "and no card needed."
                                ),
                            },
                            {
                                "q": "How many machines can I activate?",
                                "a": "As many as you bought slots. One slot is one machine; when you move, the slot is released on the old one.",
                            },
                            {
                                "q": "What happens after a year?",
                                "a": "PRO modules close, everything else keeps working. The key and slots stay — renewal brings the access back.",
                            },
                            {
                                "q": "Does Pentool send data to a server?",
                                "a": (
                                    "Only service data: the licence check at startup (the key and a hashed "
                                    "machine id), a one-time install ping and crash reports. Traffic, findings "
                                    "and projects stay on your machine; the AI runs locally. Crash reports can "
                                    "be switched off in the settings."
                                ),
                            },
                            {
                                "q": "What is the refund policy?",
                                "a": (
                                    "Full refund within 14 days of purchase — write to "
                                    '<a href="mailto:support@pentool.pro">support@pentool.pro</a> from the '
                                    "purchase e-mail with the key. The key is disabled and its slots released."
                                ),
                            },
                            {
                                "q": "Is there a team plan?",
                                "a": "There is no separate plan. If you need several machines, buy a key with the number of slots you need.",
                            },
                        ],
                    },
                ],
            },
        ],
    },
    "privacy": {
        "title": "Pentool — Privacy Policy",
        "description": (
            "What Pentool sends to a server and what stays on your machine: licence validation, install "
            "telemetry, crash reports, the local AI and buying a key."
        ),
        "intro": {
            "title": "Privacy Policy",
            "note": "Last updated 24 November 2026",
            "lead": (
                "Pentool is a local tool: traffic, projects and findings stay on your machine. This page "
                "lists everything that leaves it, why, and how to turn it off."
            ),
        },
        "sections": [
            {
                "id": "short",
                "blocks": [
                    {
                        "t": "note",
                        "text": (
                            "<strong>Short version.</strong> We never receive your traffic, requests, "
                            "responses, findings or project databases. Buying a licence gives us your e-mail "
                            "and key data. Crash reports can be switched off."
                        ),
                    }
                ],
            },
            {
                "id": "controller",
                "title": "1. Who is responsible",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Data controller: Anatoly Kashtanov (DoctorX), author of Pentool. Any privacy "
                            'request: <a href="mailto:support@pentool.pro">support@pentool.pro</a>.'
                        ),
                    }
                ],
            },
            {
                "id": "sent",
                "title": "2. What the app sends, and when",
                "blocks": [
                    {
                        "t": "table",
                        "head": ["What", "When", "Exactly what", "Can it be off?"],
                        "rows": [
                            [
                                "Licence validation",
                                "At startup with a PRO key, then cached",
                                "Key string, hashed machine id, app version",
                                "Not while using PRO",
                            ],
                            [
                                "Install ping",
                                "Once per installation",
                                "Random install id, OS and version — no traffic, no personal data",
                                "Yes, in the settings",
                            ],
                            [
                                "Crash report",
                                "Only on a fatal crash",
                                "Traceback, error type, version, OS and architecture, source (tui or cli)",
                                "Yes — <code>send_crash_reports: false</code>",
                            ],
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "Token-like strings are stripped from tracebacks before sending. Reports are "
                            "stored on the licence service, which runs on Cloudflare Workers."
                        ),
                    },
                ],
            },
            {
                "id": "local-ai",
                "title": "3. The AI runs locally",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool's AI features are served by a local model that runs as a separate "
                            "process on your machine. Requests, responses and findings are not sent to us or "
                            "to any cloud service. The only network access is the one-time download of the "
                            "model file, if you enable it."
                        ),
                    }
                ],
            },
            {
                "id": "not-collected",
                "title": "4. What we do not collect",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "proxied requests and responses, cookies, credentials, session tokens;",
                            "findings, site maps, project databases or files from your disk;",
                            "keystrokes, clipboard, screen contents or terminal history;",
                            "analytics or advertising identifiers on this site.",
                        ],
                    }
                ],
            },
            {
                "id": "purchases",
                "title": "5. Buying a licence",
                "blocks": [
                    {
                        "t": "p",
                        "text": "When you buy PRO we process:",
                    },
                    {
                        "t": "list",
                        "items": [
                            "<strong>e-mail</strong> — the key goes there, and it names the licence for support and renewals;",
                            "<strong>number of slots, amount and payment date</strong> — for accounting and renewals;",
                            "<strong>payment data</strong> — handled by the provider Coinso and the payment networks; we never see wallet private keys or card numbers.",
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "The legal basis is performance of the contract (delivering the licence) and "
                            "accounting obligations. Purchase records are kept as long as tax law requires."
                        ),
                    },
                ],
            },
            {
                "id": "activation",
                "title": "6. Activation data",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Each activation stores the key and a hashed machine identifier on the licence "
                            "service, so that used slots can be counted and the licence moved between "
                            "machines. The identifier is a hash of the system machine id; it is not used to "
                            "identify a person."
                        ),
                    }
                ],
            },
            {
                "id": "files",
                "title": "7. Data on your machine",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool writes to <code>~/.config/pentool/</code>: settings, licence cache, "
                            "logs, certificates for HTTPS interception, the project database and plugins. The "
                            "AI model lives in <code>~/.pentool/ai/models</code>. This data does not leave "
                            "the machine unless you send it. Deleting the directory deletes all of it."
                        ),
                    }
                ],
            },
            {
                "id": "site",
                "title": "8. Cookies and this site",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "This site is static: it sets no cookies and loads no analytics or third-party "
                            "scripts. Payment pages belong to the provider and follow its own rules."
                        ),
                    }
                ],
            },
            {
                "id": "rights",
                "title": "9. Your rights",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Depending on your jurisdiction (GDPR, 152-FZ and others) you may request access "
                            "to your data, its correction, deletion or export, object to processing and "
                            "complain to a supervisory authority. Write to "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a> — we answer within '
                            "30 days."
                        ),
                    }
                ],
            },
            {
                "id": "retention",
                "title": "10. Retention",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "crash reports — up to 12 months;",
                            "purchase and licence records — for the licence term plus the period required by tax law;",
                            "install counter — aggregate only, no per-user records.",
                        ],
                    }
                ],
            },
            {
                "id": "children",
                "title": "11. Children",
                "blocks": [
                    {
                        "t": "p",
                        "text": "Pentool is a professional security tool and is not intended for people under 18.",
                    }
                ],
            },
            {
                "id": "changes",
                "title": "12. Changes to this policy",
                "blocks": [
                    {
                        "t": "p",
                        "text": "A new version is published here with a new date and applies from publication.",
                    }
                ],
            },
            {
                "id": "contacts",
                "title": "13. Contact",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Privacy questions and requests: "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>.'
                        ),
                    }
                ],
            },
        ],
    },
    "terms": {
        "title": "Pentool — Terms of Service",
        "description": (
            "Terms for using Pentool and buying a PRO licence: what is allowed, how the key works, payment "
            "in cryptocurrency, refunds and liability."
        ),
        "intro": {
            "title": "Terms of Service",
            "note": "Last updated 24 November 2026",
            "lead": (
                "These terms cover the use of the Pentool software and the purchase of a PRO licence. "
                "Installing the software or activating a key means accepting them."
            ),
        },
        "sections": [
            {
                "id": "core-license",
                "blocks": [
                    {
                        "t": "note",
                        "text": (
                            "The free Pentool core is distributed under the GNU Affero General Public License "
                            'v3.0 — its terms are in the <a href="@link:license">LICENSE</a> file and govern '
                            "the open part of the code. These Terms cover the paid features, keys and the "
                            "purchase."
                        ),
                    }
                ],
            },
            {
                "id": "who",
                "title": "1. Who provides the software",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "The software and PRO licences are provided by the developer publishing under the "
                            "name Pentool: Anatoly Kashtanov (DoctorX). Contact: "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>.'
                        ),
                    }
                ],
            },
            {
                "id": "grant",
                "title": "2. What the key grants",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "A PRO key grants a non-exclusive right to use the paid features on the number of "
                            'machines ("slots") bought with that key, for the paid term — one year by default.'
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "one slot is one machine; deactivating frees the slot;",
                            "the key must not be resold, published or used to run a competing service;",
                            "the licence moves by deactivating the old machine or through support.",
                        ],
                    },
                ],
            },
            {
                "id": "trial",
                "title": "3. Trial access",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "The 14-day trial is started inside the app: Settings → License → "
                            "«Start 14-day trial». It is issued once per machine; a second attempt on "
                            "the same machine is rejected by the licence server."
                        ),
                    }
                ],
            },
            {
                "id": "payment",
                "title": "4. Payment and prices",
                "blocks": [
                    {
                        "t": "list",
                        "items": [
                            "payments are accepted by the third-party provider Coinso; payment is made in cryptocurrency;",
                            "prices are shown on the pricing page in US dollars per year and depend on the number of slots; the amount to pay appears on the payment page, and the invoice itself is issued in rubles at the provider's rate;",
                            "the key is delivered to the e-mail given at checkout; that address is stored as the licence name for support and renewals;",
                            "if you need a company invoice, write to support before paying.",
                        ],
                    }
                ],
            },
            {
                "id": "refunds",
                "title": "5. Refunds",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Full refund within 14 days of purchase. Write to "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a> from the purchase '
                            "e-mail and include the key. On refund the key is disabled and its slots released."
                        ),
                    }
                ],
            },
            {
                "id": "acceptable",
                "title": "6. Acceptable use",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Pentool is a security testing tool. You agree to use it only against systems you "
                            "own or are explicitly authorised in writing to test. You are responsible for:"
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "obtaining the system owner's permission before testing;",
                            "following the laws and regulations that apply to you;",
                            "the consequences of the tests you run, including the load they place on other systems.",
                        ],
                    },
                    {
                        "t": "p",
                        "text": (
                            "We do not authorise or assist unauthorised access to computer systems and accept "
                            "no liability for such use."
                        ),
                    },
                ],
            },
            {
                "id": "validation",
                "title": "7. Licence validation and telemetry",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "PRO features validate the key at startup through the licence service. Only the "
                            "key and a hashed machine identifier are sent; results are cached, so limited "
                            "offline work is possible. Crash reports are optional and can be switched off — "
                            'see the <a href="@privacy">Privacy Policy</a>.'
                        ),
                    }
                ],
            },
            {
                "id": "updates",
                "title": "8. Updates to the software",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "We release updates that may add, change or remove features. Paid features listed "
                            "on the pricing page at the time of purchase are provided for the paid term; if a "
                            "feature is removed permanently, we will refund its pro-rata value for the "
                            "remaining term on request."
                        ),
                    }
                ],
            },
            {
                "id": "warranty",
                "title": "9. Warranty and liability",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            'The software is provided "as is", without warranties of any kind, express or '
                            "implied, including fitness for a particular purpose. To the fullest extent "
                            "permitted by law:"
                        ),
                    },
                    {
                        "t": "list",
                        "items": [
                            "we are not liable for indirect or incidental damages, lost profits, lost data or business interruption;",
                            "total liability is limited to the amount paid for the licence in the 12 months before the claim.",
                        ],
                    },
                    {
                        "t": "p",
                        "text": "Nothing here limits liability that cannot be limited by law.",
                    },
                ],
            },
            {
                "id": "termination",
                "title": "10. Termination",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "We may disable a key without a refund if it is used in breach of section 2 "
                            "(resale or publication) or section 6 (unauthorised testing). You may stop using "
                            "the software at any time; uninstalling does not entitle you to a refund outside "
                            "section 5."
                        ),
                    }
                ],
            },
            {
                "id": "terms-changes",
                "title": "11. Changes to these Terms",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "The version published on this page with its date applies. Material changes apply "
                            "to purchases made after publication; existing licences continue under the terms "
                            "in force at purchase."
                        ),
                    }
                ],
            },
            {
                "id": "law",
                "title": "12. Governing law",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "The law of the owner's country of residence applies unless mandatory rules of "
                            "your jurisdiction require otherwise. Disputes are settled by negotiation and, "
                            "failing that, in a competent court."
                        ),
                    }
                ],
            },
            {
                "id": "contacts",
                "title": "13. Contact",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "Questions about these Terms and licences: "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a>.'
                        ),
                    }
                ],
            },
        ],
    },
    "success": {
        "title": "Pentool — payment received",
        "description": "Payment accepted: your PRO key is on its way to the e-mail you provided.",
        "intro": {
            "title": "Payment received",
            "lead": (
                "Thank you. The key is sent to the e-mail given at checkout — usually within a few "
                "minutes. If it is not there, check the spam folder."
            ),
        },
        "sections": [
            {
                "id": "next",
                "blocks": [
                    {
                        "t": "steps",
                        "items": [
                            {
                                "title": "Find the key in the letter",
                                "text": "The letter contains a key like <code>PTOOL-XXXX-XXXX-XXXX</code> and the number of slots you bought.",
                            },
                            {
                                "title": "Activate it in the app",
                                "text": "Pentool → Settings → License → Activate. The first activation takes a slot and binds it to this machine.",
                            },
                            {
                                "title": "If the letter is missing",
                                "text": "Write to support@pentool.pro with the order number and the e-mail used for payment — we will issue the key by hand.",
                            },
                        ],
                    },
                    {
                        "t": "buttons",
                        "items": [
                            {"label": "Back to pricing", "href": "@pricing", "style": "primary"},
                            {"label": "Write to support", "href": "@link:email", "style": "ghost"},
                        ],
                    },
                ],
            }
        ],
    },
    "fail": {
        "title": "Pentool — payment not completed",
        "description": "The payment did not go through: nothing was charged and no key was issued.",
        "intro": {
            "title": "Payment not completed",
            "lead": (
                "Nothing was charged and no key was issued: the invoice expired or the payment was "
                "cancelled before it went through. You can start again — slots and payment method are "
                "chosen on the pricing page."
            ),
        },
        "sections": [
            {
                "id": "what-now",
                "blocks": [
                    {
                        "t": "p",
                        "text": (
                            "If your bank still shows a charge, it is usually a temporary hold that is "
                            "released automatically. If it stays, write to "
                            '<a href="mailto:support@pentool.pro">support@pentool.pro</a> with the payment id '
                            "and date."
                        ),
                    },
                    {
                        "t": "buttons",
                        "items": [
                            {"label": "Try again", "href": "@pricing", "style": "primary"},
                            {"label": "Write to support", "href": "@link:email", "style": "ghost"},
                        ],
                    },
                ],
            }
        ],
    },
}
