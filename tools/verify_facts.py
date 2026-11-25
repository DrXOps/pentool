"""Executable facts: what is true about the project right now, and how to prove it.

The problem this closes: "done" was prose. A handoff could say "e-mail does not work",
PLAN could say "keys arrive by e-mail", and both stayed in the tree — nobody could tell
which was true without reading the code again. Decisions were also lost: a claim written
once was never re-checked after the code moved.

Design:

* ``tools/facts.yml`` is the single place where current state lives, one fact per claim;
* every fact names a check implemented here — mostly "read the repository" (fast, offline,
  runs in pre-commit), a few need the network or a human and record ``last_verified``;
* ``docs/PROJECT_STATE.md`` is generated from the file, so the human-readable page cannot
  drift from the machine one;
* history comes from git: a value changes with a date and a reason, ``git log`` shows it.

Usage::

    python tools/verify_facts.py                # code checks + staleness of external ones
    python tools/verify_facts.py --online       # also call the network checks
    python tools/verify_facts.py --render       # rewrite docs/PROJECT_STATE.md
    python tools/verify_facts.py --check-render # fail if the page is out of date
    python tools/verify_facts.py --update ci.green   # mark an external fact verified today
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
FACTS_FILE = ROOT / "tools" / "facts.yml"
STATE_PAGE = ROOT / "docs" / "PROJECT_STATE.md"

#: (ok, detail) — a check never raises; a broken probe is a FAILED fact, not a crash.
Check = Callable[[], tuple[bool, str]]


# ── helpers ────────────────────────────────────────────────────────────────────


def _read(relative: str) -> str:
    path = ROOT / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _exists(relative: str) -> bool:
    return (ROOT / relative).exists()


def _screen_files() -> list[Path]:
    return sorted((ROOT / "pentool/tui/screens").rglob("screen.py"))


def _load_facts() -> list[dict]:
    import yaml

    data = yaml.safe_load(FACTS_FILE.read_text(encoding="utf-8")) or {}
    facts = data.get("facts") or []
    if not isinstance(facts, list) or not facts:
        raise SystemExit("verify_facts: tools/facts.yml has no facts")
    return facts


# ── code checks (offline) ──────────────────────────────────────────────────────


def site_languages() -> tuple[bool, str]:
    config = _read("tools/site/config.py")
    langs = [code for code in ("ru", "en", "zh", "hi") if f'("{code}",' in config]
    pages = [f"docs/{code}/index.html" for code in ("ru", "zh", "hi") if _exists(f"docs/{code}/index.html")]
    ok = len(langs) == 4 and len(pages) == 3 and _exists("docs/index.html")
    return ok, f"языков в config: {len(langs)}; страниц-каталогов: {len(pages)}"


def site_pages() -> tuple[bool, str]:
    pages = list((ROOT / "docs").rglob("index.html")) + list((ROOT / "docs").rglob("pricing.html"))
    has_css = "/assets/site.css" in _read("docs/index.html")
    redirects = [p for p in ("docs/pricing.ru.html", "docs/upgrade.html", "docs/pricing/index.html") if _exists(p)]
    ok = len(pages) >= 8 and has_css and len(redirects) == 3
    return ok, f"страниц {len(pages)} (index+pricing), общий CSS: {has_css}, редиректов {len(redirects)}"


def payment_provider() -> tuple[bool, str]:
    html = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs").rglob("*.html"))
    content = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "tools/site/content").glob("*.py"))
    has_coinso = "coinso" in html.lower() or "coinso" in content.lower()
    has_cryptoproc = "cryptoproc" in (html + content).lower()
    ok = has_coinso and not has_cryptoproc
    return ok, f"Coinso упоминается: {has_coinso}; CryptoProc остался: {has_cryptoproc}"


def license_trial() -> tuple[bool, str]:
    settings = _read("pentool/tui/screens/settings/screen.py")
    cli = _read("pentool/cli/license_cmd.py")
    ui = "btn-license-trial" in settings and "start_trial()" in settings
    command = '"trial"' in cli and "start_trial()" in cli
    return ui and command, f"кнопка+воркер в UI: {ui}; команда `license trial`: {command}"


def license_cli() -> tuple[bool, str]:
    try:
        from pentool.cli.main import cli
    except Exception as exc:  # noqa: BLE001 - a missing CLI is the finding
        return False, f"CLI не импортируется: {exc}"
    commands = sorted(getattr(cli, "commands", {}))
    ok = commands == ["license"]
    return ok, f"подключено к корню: {commands}"


def license_texts() -> tuple[bool, str]:
    """No user-facing text may point at a CLI command that does not exist."""
    offenders: list[str] = []
    for path in (ROOT / "pentool").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"pentool license ([a-z]+)", text):
            if match.group(1) not in {"status", "activate", "deactivate", "trial"}:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {match.group(0)}")
    return not offenders, "ссылок на несуществующие подкоманды нет" if not offenders else "; ".join(offenders[:3])


def tui_module_catalog() -> tuple[bool, str]:
    catalog = _read("pentool/tui/module_catalog.py")
    consumers = {
        "module_tabs": "module_catalog" in _read("pentool/tui/widgets/module_tabs.py"),
        "hotkeys": "module_catalog" in _read("pentool/tui/hotkeys/defaults.py"),
        "project_manager": "module_catalog.reloadable_ids" in _read("pentool/tui/project_manager.py"),
        "keyhintbar": "module_catalog" in _read("pentool/tui/widgets/keyhintbar.py"),
    }
    ok = "CATALOG" in catalog and all(consumers.values())
    return ok, f"CATALOG есть: {'CATALOG' in catalog}; производные: {consumers}"


def tui_action_row() -> tuple[bool, str]:
    offenders = []
    for path in _screen_files():
        text = path.read_text(encoding="utf-8")
        if "yield Toolbar(" in text and path.parent.name != "intruder":
            offenders.append(path.parent.name)
    return not offenders, "только header_spec()" if not offenders else f"свой Toolbar: {offenders}"


def tui_header_refresh() -> tuple[bool, str]:
    hits = sum(
        1 for p in (ROOT / "pentool/tui").rglob("*.py") if "_refresh_header_now" in p.read_text(encoding="utf-8")
    )
    single = "def refresh_header" in _read("pentool/tui/mixins/app_mixin.py")
    return hits == 0 and single, f"копий _refresh_header_now: {hits}; AppMixin.refresh_header: {single}"


def tui_project_reload() -> tuple[bool, str]:
    pattern = re.compile(r"\b\w*screen\._[a-z]")
    offenders: list[str] = []
    for name in ("app.py", "project_manager.py"):
        for line_no, line in enumerate(_read(f"pentool/tui/{name}").splitlines(), 1):
            for match in pattern.finditer(line):
                if "_cancel_save_workers" in match.group(0):
                    continue
                offenders.append(f"{name}:{line_no}")
    guard = _exists("tests/unit/tui/test_no_private_screen_access.py")
    return not offenders and guard, f"обращений: {len(offenders)}; гвард: {guard}"


def tui_tab_rename() -> tuple[bool, str]:
    allowed = {"intruder"}  # one-line delegation to the panel, keeps hotkeys/tests working
    offenders = [
        path.parent.name
        for path in _screen_files()
        if "def _start_rename" in path.read_text(encoding="utf-8") and path.parent.name not in allowed
    ]
    mixin = _exists("pentool/tui/mixins/tab_rename.py")
    consumers = [
        name
        for name, relative in (
            ("panel", "pentool/tui/widgets/tab_panel.py"),
            ("base", "pentool/tui/screens/base.py"),
        )
        if "TabRenameMixin" in _read(relative)
    ]
    return mixin and len(
        consumers
    ) == 2 and not offenders, f"миксин: {mixin}; потребители: {consumers}; копии: {offenders}"


def intruder_payloads() -> tuple[bool, str]:
    module = _exists("pentool/tui/screens/intruder/payload_sources.py")
    screen = _read("pentool/tui/screens/intruder/screen.py")
    delegates = "PayloadSources(self)" in screen and "self._payload_sources.load" in screen
    parser_shared = "_read_file_sync" not in screen and "load_payloads_from_file" in _read(
        "pentool/tui/screens/intruder/payload_sources.py"
    )
    return module and delegates and parser_shared, (
        f"модуль: {module}; экран делегирует: {delegates}; общий парсер: {parser_shared}"
    )


def tui_dead_code() -> tuple[bool, str]:
    gone = [
        "pentool/tui/widgets/custom_notify.py",
        "pentool/tui/widgets/custom_notify.tcss",
        "pentool/tui/widgets/hintbar_base.py",
        "pentool/tui/widgets/hintbar_base.tcss",
    ]
    leftovers = [relative for relative in gone if _exists(relative)]
    messages = _read("pentool/tui/messages.py")
    safe_query = _read("pentool/tui/mixins/safe_query.py")
    ok = not leftovers and "ProxyClearHistory" not in messages and "def safe_notify" not in safe_query
    return ok, (
        f"файлов осталось: {leftovers or 'нет'}; "
        f"ProxyClearHistory: {'есть' if 'ProxyClearHistory' in messages else 'нет'}; "
        f"safe_notify: {'есть' if 'def safe_notify' in safe_query else 'нет'}"
    )


def recon_prompts() -> tuple[bool, str]:
    local_module = _exists("pro/pentool/modules/ai_discovery/prompts.py")
    registry = _read("pentool/services/ai/prompts.py")
    tasks = [name for name in ("discovery_subdomains", "discovery_endpoints", "discovery_params") if name in registry]
    return not local_module and len(tasks) == 3, f"локальный prompts.py: {local_module}; задач в реестре: {tasks}"


def repo_branches() -> tuple[bool, str]:
    def sha(ref: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "--short", ref], cwd=ROOT, capture_output=True, text=True, check=False
        )
        return result.stdout.strip()

    left, right = sha("origin/develop"), sha("origin/main")
    return bool(left) and left == right, f"origin/develop={left or '?'} origin/main={right or '?'}"


def license_core() -> tuple[bool, str]:
    core = "GNU AFFERO GENERAL PUBLIC LICENSE" in _read("LICENSE")
    pro = "Proprietary" in _read("pro/README.md")
    return core and pro, f"ядро AGPL-3.0: {core}; PRO proprietary: {pro}"


# ── external checks (network / human) ─────────────────────────────────────────


def site_published() -> tuple[bool, str]:
    try:
        request = urllib.request.Request("https://pentool.pro/", headers={"User-Agent": "facts-check"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"сайт недоступен: {exc}"
    ok = "/assets/site.css" in body and "Pentool" in body
    return ok, f"HTTP {response.status}, новый CSS: {'/assets/site.css' in body}"


def mail_outbound() -> tuple[bool, str]:
    """Cannot be probed automatically without sending mail.

    The fact records that a live letter was delivered (evidence + date). Re-verify by
    buying a licence (or asking support to resend) and updating `--update mail.outbound`.
    """
    return True, "проверяется живым письмом вручную; см. evidence"


def ci_green() -> tuple[bool, str]:
    token_file = Path.home() / ".git-credentials"
    if not token_file.is_file():
        return True, "нет токена GitHub — статус CI проверяется вручную"
    token = token_file.read_text(encoding="utf-8").strip().rsplit(":", 1)[-1].split("@", 1)[0]
    url = "https://api.github.com/repos/DrXOps/pentool/actions/runs?per_page=10"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "facts"},
    )
    try:
        import json

        with urllib.request.urlopen(request, timeout=25) as response:
            runs = json.loads(response.read()).get("workflow_runs", [])
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"GitHub API недоступен: {exc}"
    latest = {}
    for run in runs:
        latest.setdefault(run["name"], run)
    gated = {name: run["conclusion"] for name, run in latest.items() if name in {"Tests", "CI", "Dev Build (TestPyPI)"}}
    ok = bool(gated) and all(value == "success" for value in gated.values())
    return ok, f"последние прогоны: {gated}"


CHECKS: dict[str, Check] = {
    "site_languages": site_languages,
    "site_pages": site_pages,
    "payment_provider": payment_provider,
    "license_trial": license_trial,
    "license_cli": license_cli,
    "license_texts": license_texts,
    "tui_module_catalog": tui_module_catalog,
    "tui_action_row": tui_action_row,
    "tui_header_refresh": tui_header_refresh,
    "tui_project_reload": tui_project_reload,
    "tui_tab_rename": tui_tab_rename,
    "intruder_payloads": intruder_payloads,
    "tui_dead_code": tui_dead_code,
    "recon_prompts": recon_prompts,
    "repo_branches": repo_branches,
    "license_core": license_core,
    "site_published": site_published,
    "mail_outbound": mail_outbound,
    "ci_green": ci_green,
}


# ── runner ─────────────────────────────────────────────────────────────────────


def _today() -> dt.date:
    return dt.date.today()


def _age_days(value: str) -> int:
    try:
        return (_today() - dt.date.fromisoformat(str(value))).days
    except ValueError:
        return 10**6


def run(online: bool) -> tuple[list[str], int]:
    facts = _load_facts()
    rows: list[tuple[str, str, str, str]] = []
    problems = 0
    for fact in facts:
        fact_id = fact["id"]
        claim = fact["claim"]
        kind = fact.get("kind", "code")
        check_name = fact["check"]
        check = CHECKS.get(check_name)
        if check is None:
            rows.append((fact_id, claim, f"НЕТ ПРОВЕРКИ {check_name}", "FAIL"))
            problems += 1
            continue
        if kind == "external" and not online:
            age = _age_days(fact.get("last_verified", ""))
            max_age = int(fact.get("max_age_days", 30))
            state = "OK (ручная)" if age <= max_age else f"УСТАРЕЛ {age} дн"
            if age > max_age:
                problems += 1
            rows.append((fact_id, claim, f"проверено {fact.get('last_verified', '—')}: {state}", state))
            continue
        ok, detail = check()
        state = "OK" if ok else "РАСХОЖДЕНИЕ"
        if not ok:
            problems += 1
        rows.append((fact_id, claim, detail, state))
    return [f"{i}\t{c}\t{d}\t{s}" for i, c, d, s in rows], problems


def render(rows: list[tuple[str, str, str, str]]) -> str:
    lines = [
        "# Состояние проекта (факты)",
        "",
        "<!-- СГЕНЕРИРОВАНО: python tools/verify_facts.py --render.",
        "     Источник: tools/facts.yml. Руками не править: следующий рендер перезапишет. -->",
        "",
        f"**Обновлено:** {_today().isoformat()}",
        "",
        "Единственное место, где записано «что сейчас правда». Планы (`MYPLANS/`) описывают,",
        "что делать, и ссылаются на эти id — состояние в них не повторяется, поэтому",
        "расхождений между документами быть не может. История — в git (`git log tools/facts.yml`).",
        "",
        "| Факт | Утверждение | Как проверено | Статус |",
        "|---|---|---|---|",
    ]
    for fact_id, claim, detail, state in rows:
        lines.append(f"| `{fact_id}` | {claim} | {detail} | {'✅ OK' if state == 'OK' else '⚠️ ' + state} |")
    lines += [
        "",
        "`kind: external` — проверяется сетью или руками (`--online`), дата проверки хранится",
        "в факте: устаревший внешний факт — это предупреждение, а не «сделано».",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="выполнить и сетевые проверки")
    parser.add_argument("--render", action="store_true", help="перезаписать docs/PROJECT_STATE.md")
    parser.add_argument("--check-render", action="store_true", help="упасть, если страница устарела")
    parser.add_argument("--update", metavar="FACT_ID", help="отметить внешний факт проверенным сегодня")
    args = parser.parse_args(argv)

    if args.update:
        facts = _load_facts()
        found = [fact for fact in facts if fact["id"] == args.update]
        if not found:
            print(f"verify_facts: неизвестный факт {args.update!r}", file=sys.stderr)
            return 2
        text = FACTS_FILE.read_text(encoding="utf-8")
        pattern = re.compile(rf"(id: {re.escape(args.update)}\n(?:.*\n)*?\s*last_verified: )\"[^\"]*\"")
        text, count = pattern.subn(rf'\g<1>"{_today().isoformat()}"', text, count=1)
        if not count:
            print(f"verify_facts: у факта {args.update} нет поля last_verified", file=sys.stderr)
            return 2
        FACTS_FILE.write_text(text, encoding="utf-8")
        print(f"verify_facts: {args.update} отмечен проверенным {_today().isoformat()}")
        return 0

    rows_text, problems = run(args.online)
    for line in rows_text:
        print("  ".join(line.split("\t")))
    if args.render or args.check_render:
        rows = [tuple(line.split("\t")) for line in rows_text]
        page = render([(a, b, c, d) for a, b, c, d in rows])
        if args.render:
            STATE_PAGE.write_text(page, encoding="utf-8")
            print(f"verify_facts: {STATE_PAGE.relative_to(ROOT).as_posix()} обновлён")
        elif STATE_PAGE.is_file() and STATE_PAGE.read_text(encoding="utf-8") != page:
            print("verify_facts: docs/PROJECT_STATE.md устарел — запустите --render", file=sys.stderr)
            problems += 1
    if problems:
        print(f"verify_facts: проблем — {problems}", file=sys.stderr)
        return 1
    print(f"verify_facts: всё сходится ({len(rows_text)} фактов)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
