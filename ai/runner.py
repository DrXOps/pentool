"""ai/runner.py — маршрутизация задач на модели, эскалация, журнал.

Единственный исполняемый модуль автоматизации. Вызывается из `ai/run`
(тонкая bash-обёртка) и из хуков `.claude/hooks/*` через `python3 -I`.

Почему stdlib-only: `ai/` кладётся в проекты на любом стеке (Node, Go, Rust),
и требовать от них Python-пакет было бы навязыванием. Здесь только urllib,
json, subprocess и argparse. PyYAML используется, если установлен; иначе
работает встроенный парсер подмножества (см. `_parse_yaml_subset`).

Контракт вывода: `--json` печатает машинно-читаемый результат в stdout,
всё диагностическое — в stderr. Коды возврата: 0 — успех, 1 — ошибка
конфигурации/ввода, 2 — исчерпана цепочка эскалации.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------
AI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AI_DIR.parent
CONFIG_PATH = AI_DIR / "models.yaml"


def _log_dir() -> Path:
    d = PROJECT_ROOT / ".claude" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Конфигурация: YAML, с фолбэком на встроенный парсер подмножества
# ---------------------------------------------------------------------------
def _strip_comment(s: str) -> str:
    """Убирает ` # комментарий` вне кавычек — как это делает YAML.

    Без этого `context_tokens: 32768   # подтверждено` разбирался бы как
    строка, и тип значения молча менялся в зависимости от того, установлен
    ли PyYAML (adversarial-тест `test_yaml_fallback_matches_pyyaml` это ловит).
    """
    quote = ""
    for idx, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (idx == 0 or s[idx - 1] in " \t"):
            return s[:idx].rstrip()
    return s


def _parse_scalar(raw: str) -> Any:
    s = _strip_comment(raw).strip()
    if not s:
        return ""
    if s in ("null", "~", "None"):
        return None
    if s in ("true", "True", "yes"):
        return True
    if s in ("false", "False", "no"):
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_flow(inner)]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _split_flow(inner: str) -> list[str]:
    """Разделяет `a, b, "c, d"` по запятым вне кавычек."""
    parts, buf, quote = [], [], ""
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_yaml_subset(text: str) -> dict:
    """Парсер подмножества YAML, достаточного для ai/models.yaml.

    Поддерживается: комментарии, отступы пробелами, вложенные словари,
    скаляры, flow-списки `[a, b]`, блочные списки `- item`, блочные строки
    `>` и `|`. Не поддерживается (и не нужно здесь): якоря, теги, множественные
    документы, многострочные flow-структуры.
    """
    root: dict = {}
    # стек: (отступ, контейнер)
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(-1, root)]
        parent = stack[-1][1]

        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"YAML: список без ключа на строке {i}: {line!r}")
            parent.append(_parse_scalar(line[2:]))
            continue
        if line == "-":
            if not isinstance(parent, list):
                raise ValueError(f"YAML: список без ключа на строке {i}")
            parent.append("")
            continue

        if ":" not in line:
            raise ValueError(f"YAML: ожидался 'ключ: значение' на строке {i}: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip().strip("\"'")
        rest = rest.strip()

        # блочная строка: всё, что глубже, склеивается
        if rest in (">", "|", ">-", "|-"):
            chunks: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip(" "))) <= indent:
                    break
                chunks.append(nxt.strip())
                i += 1
            # Как в YAML: `>` склеивает строки пробелом (без хвостового),
            # `|` сохраняет переводы; модификатор `-` убирает финальный \n.
            joiner = " " if rest.startswith(">") else "\n"
            joined = joiner.join(c for c in chunks if c)
            if rest.endswith("-"):
                joined = joined.rstrip()
            else:
                joined += "\n"
            parent[key] = joined
            continue

        if rest == "":
            # Смотрим вперёд: это словарь или список?
            j = i
            while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                j += 1
            is_list = j < len(lines) and lines[j].strip().startswith("-")
            child: Any = [] if is_list else {}
            parent[key] = child
            stack.append((indent, child))
            continue

        parent[key] = _parse_scalar(rest)
    return root


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise SystemExit(f"ai: нет файла конфигурации {path}")
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        data = _parse_yaml_subset(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict) or "models" not in data:
        raise SystemExit(f"ai: конфигурация {path} пуста или не содержит 'models'")
    return data


def resolve_model(cfg: dict, name: str) -> dict:
    models = cfg["models"]
    if name not in models:
        raise SystemExit(f"ai: неизвестная модель {name!r}; есть: {', '.join(sorted(models))}")
    spec = dict(models[name])
    # env-переопределения: эндпоинт и имя модели никогда не хардкодятся
    for key, env_key in (("endpoint", spec.get("endpoint_env")), ("model", spec.get("model_env"))):
        if env_key:
            value = os.environ.get(env_key)
            if value:
                spec[key] = value
    if "endpoint" not in spec:
        env_key = spec.get("endpoint_env")
        default = spec.get("endpoint_default") or ""
        if not default and env_key is None:
            spec["endpoint"] = ""
        elif env_key and not default:
            raise SystemExit(
                f"ai: модель {name}: не задан эндпоинт. "
                f"Установите {env_key} (см. ai/models.yaml) — в конфиг реальный URL не пишется."
            )
        else:
            spec["endpoint"] = default
    spec.setdefault("timeout_sec", 120)
    spec.setdefault("supports_tools", False)
    return spec


def task_chain(cfg: dict, task: str) -> list[str]:
    tasks = cfg.get("tasks", {})
    if task not in tasks:
        raise SystemExit(f"ai: неизвестный тип задачи {task!r}; есть: {', '.join(sorted(tasks))}")
    chain = tasks[task]
    if isinstance(chain, str):
        chain = [chain]
    return list(chain)


# ---------------------------------------------------------------------------
# Провайдеры
# ---------------------------------------------------------------------------
class ProviderError(Exception):
    """Ошибка, после которой имеет смысл эскалировать."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        kind = "http_5xx" if exc.code >= 500 else "http_4xx"
        raise ProviderError(kind, f"HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise ProviderError("timeout", str(exc)) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            raise ProviderError("timeout", str(reason)) from exc
        raise ProviderError("network", str(reason)) from exc
    except json.JSONDecodeError as exc:
        raise ProviderError("empty_response", f"не-JSON ответ: {exc}") from exc


def call_ollama(spec: dict, prompt: str, system: str | None) -> tuple[str, dict]:
    endpoint = spec["endpoint"].rstrip("/")
    payload: dict[str, Any] = {
        "model": spec["model"],
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": int(spec.get("context_tokens", 8192))},
    }
    if system:
        payload["system"] = system
    data = _post_json(f"{endpoint}/api/generate", payload, {}, float(spec["timeout_sec"]))
    if data.get("error"):
        raise ProviderError("http_4xx", str(data["error"]))
    text = (data.get("response") or "").strip()
    if not text:
        raise ProviderError("empty_response", "Ollama вернула пустой ответ")
    usage = {
        "prompt_tokens": data.get("prompt_eval_count"),
        "completion_tokens": data.get("eval_count"),
    }
    return text, usage


def call_anthropic_compatible(spec: dict, prompt: str, system: str | None) -> tuple[str, dict]:
    endpoint = spec["endpoint"].rstrip("/")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    if not token:
        raise ProviderError(
            "config",
            "нет ANTHROPIC_AUTH_TOKEN/ANTHROPIC_API_KEY в окружении (секреты только через env)",
        )
    headers = {
        "x-api-key": token,
        "authorization": f"Bearer {token}",
        "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
    }
    payload: dict[str, Any] = {
        "model": spec["model"],
        "max_tokens": int(os.environ.get("AI_MAX_TOKENS", "1024")),
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    data = _post_json(f"{endpoint}/v1/messages", payload, headers, float(spec["timeout_sec"]))
    blocks = data.get("content") or []
    # Только блоки type == "text": reasoning-модели gateway (deepseek, qwen)
    # возвращают ещё и {"type": "thinking", "thinking": "..."} — рассуждения
    # не должны попадать в вывод задачи.
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type", "text") == "text").strip()
    if not text:
        kinds = [b.get("type") for b in blocks if isinstance(b, dict)]
        raise ProviderError("empty_response", f"нет блока text (получено: {kinds})")
    usage = {
        "prompt_tokens": (data.get("usage") or {}).get("input_tokens"),
        "completion_tokens": (data.get("usage") or {}).get("output_tokens"),
    }
    return text, usage


def call_model(spec: dict, prompt: str, system: str | None) -> tuple[str, dict]:
    provider = spec.get("provider", "")
    if provider == "ollama":
        return call_ollama(spec, prompt, system)
    if provider == "anthropic-compatible":
        return call_anthropic_compatible(spec, prompt, system)
    raise ProviderError("config", f"неизвестный provider {provider!r}")


# ---------------------------------------------------------------------------
# Журнал событий
# ---------------------------------------------------------------------------
def log_event(cfg: dict, event: dict) -> None:
    log_cfg = cfg.get("logging") or {}
    rel = log_cfg.get("events_path") or "ai/logs/events.jsonl"
    path = PROJECT_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(log_cfg.get("max_bytes") or 5 * 1024 * 1024)
    keep = int(log_cfg.get("keep_files") or 5)
    if path.exists() and path.stat().st_size > max_bytes:
        for idx in range(keep - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{idx}")
            dst = path.with_suffix(path.suffix + f".{idx + 1}")
            if src.exists():
                src.replace(dst)
        path.replace(path.with_suffix(path.suffix + ".1"))
    event = {"ts": _now(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Запуск задачи с эскалацией
# ---------------------------------------------------------------------------
@dataclass
class Attempt:
    model: str
    ok: bool
    duration_sec: float
    error: str | None = None
    tokens: dict = field(default_factory=dict)


def run_task(
    cfg: dict,
    task: str,
    prompt: str,
    system: str | None = None,
    dry_run: bool = False,
) -> tuple[str | None, list[Attempt], str | None]:
    chain = task_chain(cfg, task)
    esc = cfg.get("escalation") or {}
    attempts_per_model = int(esc.get("attempts_per_model") or 1)
    retry_on = set(esc.get("retry_on") or [])
    attempts: list[Attempt] = []

    for name in chain:
        spec = resolve_model(cfg, name)
        for _ in range(max(1, attempts_per_model)):
            if dry_run:
                attempts.append(Attempt(model=name, ok=True, duration_sec=0.0, tokens={}))
                return (
                    f"[dry-run] задача {task!r} ушла бы в модель {name} "
                    f"({spec.get('model')} @ {spec.get('endpoint') or '<env>'})",
                    attempts,
                    None,
                )
            started = time.monotonic()
            try:
                text, usage = call_model(spec, prompt, system)
            except ProviderError as exc:
                duration = time.monotonic() - started
                attempts.append(Attempt(name, False, duration, f"{exc.kind}: {exc.detail}"))
                log_event(
                    cfg,
                    {
                        "event": "attempt_failed",
                        "task": task,
                        "model": name,
                        "provider": spec.get("provider"),
                        "duration_sec": round(duration, 3),
                        "error_kind": exc.kind,
                        "error": exc.detail[:300],
                        "escalate": exc.kind in retry_on,
                    },
                )
                if exc.kind not in retry_on:
                    return None, attempts, f"{name}: {exc.kind}: {exc.detail}"
                continue
            duration = time.monotonic() - started
            attempts.append(Attempt(name, True, duration, tokens=usage))
            log_event(
                cfg,
                {
                    "event": "attempt_ok",
                    "task": task,
                    "model": name,
                    "provider": spec.get("provider"),
                    "duration_sec": round(duration, 3),
                    "escalated": len(attempts) > 1,
                    "escalation_reason": (attempts[-2].error if len(attempts) > 1 and attempts[-2].error else None),
                    **{k: v for k, v in usage.items() if v is not None},
                },
            )
            return text, attempts, None
    return None, attempts, "цепочка эскалации исчерпана"


# ---------------------------------------------------------------------------
# Отчёт: до/после, где локальная, где облачная
# ---------------------------------------------------------------------------
def build_report(cfg: dict, since: str | None = None) -> dict:
    log_cfg = cfg.get("logging") or {}
    path = PROJECT_ROOT / (log_cfg.get("events_path") or "ai/logs/events.jsonl")
    if not path.exists():
        return {"events": 0, "message": f"журнал {path} пуст — запусков ещё не было"}

    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and ev.get("ts", "") < since:
            continue
        events.append(ev)

    ok = [e for e in events if e.get("event") == "attempt_ok"]
    failed = [e for e in events if e.get("event") == "attempt_failed"]
    models = cfg.get("models", {})
    by_model: dict[str, dict] = {}
    for e in ok:
        name = e.get("model", "?")
        bucket = by_model.setdefault(
            name,
            {"calls": 0, "duration_sec": 0.0, "prompt_tokens": 0, "completion_tokens": 0},
        )
        bucket["calls"] += 1
        bucket["duration_sec"] += float(e.get("duration_sec") or 0)
        bucket["prompt_tokens"] += int(e.get("prompt_tokens") or 0)
        bucket["completion_tokens"] += int(e.get("completion_tokens") or 0)

    def is_local(name: str) -> bool:
        return models.get(name, {}).get("provider") == "ollama"

    total = sum(b["calls"] for b in by_model.values())
    local_calls = sum(b["calls"] for n, b in by_model.items() if is_local(n))
    cloud_calls = total - local_calls
    # Экономия: вызовы, которые НЕ ушли в облако (локальная модель справилась).
    saved_calls = local_calls
    priced = [n for n in by_model if (models.get(n, {}).get("cost_per_1k_tokens_usd") or 0) > 0]
    saved_usd = None
    if priced:
        # Консервативная оценка: считаем по самой дешёвой известной облачной цене.
        rate = min(models[n]["cost_per_1k_tokens_usd"] for n in priced)
        tokens_saved = sum(
            (b["prompt_tokens"] or 0) + (b["completion_tokens"] or 0) for n, b in by_model.items() if is_local(n)
        )
        saved_usd = round(tokens_saved / 1000 * rate, 4)

    return {
        "events": len(events),
        "ok_calls": total,
        "failed_attempts": len(failed),
        "escalations": sum(1 for e in ok if e.get("escalated")),
        "local_calls": local_calls,
        "cloud_calls": cloud_calls,
        "local_share": round(local_calls / total, 3) if total else 0.0,
        "saved_local_calls": saved_calls,
        "saved_usd_estimate": saved_usd,
        "by_model": by_model,
        "failure_reasons": _count(failed, "error_kind"),
        "log_path": str(path.relative_to(PROJECT_ROOT)),
    }


def _count(items: Iterable[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for it in items:
        k = str(it.get(key) or "unknown")
        out[k] = out.get(k, 0) + 1
    return out


def print_report(cfg: dict, since: str | None) -> int:
    rep = build_report(cfg, since)
    if not rep.get("ok_calls"):
        print(rep.get("message") or "нет данных")
        return 0
    print(f"Период: {'весь журнал' if not since else 'с ' + since}")
    print(f"Журнал: {rep['log_path']}  (событий: {rep['events']})")
    print()
    print(f"Успешных вызовов:      {rep['ok_calls']}")
    print(f"Эскалаций:             {rep['escalations']}")
    print(f"Неудачных попыток:     {rep['failed_attempts']}  {rep['failure_reasons'] or ''}")
    print(f"Локальная модель:      {rep['local_calls']}  ({rep['local_share']:.0%})")
    print(f"Облако:                {rep['cloud_calls']}")
    print(f"Сэкономлено вызовов:   {rep['saved_local_calls']}")
    if rep["saved_usd_estimate"] is not None:
        print(f"Оценка экономии, $:    {rep['saved_usd_estimate']}")
    else:
        print("Оценка экономии, $:    n/a (цены моделей не заданы в ai/models.yaml)")
    print()
    print(f"{'модель':<22}{'вызовов':>9}{'сек':>9}{'in_tok':>10}{'out_tok':>10}")
    for name, b in sorted(rep["by_model"].items()):
        print(
            f"{name:<22}{b['calls']:>9}{b['duration_sec']:>9.1f}"
            f"{b['prompt_tokens']:>10}{b['completion_tokens']:>10}"
        )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if prompt == "-":
        prompt = sys.stdin.read()
    if not prompt.strip():
        print("ai: пустой промпт", file=sys.stderr)
        return 1
    text, attempts, error = run_task(cfg, args.task, prompt, args.system, args.dry_run)
    if args.json:
        print(
            json.dumps(
                {
                    "task": args.task,
                    "ok": error is None,
                    "error": error,
                    "model_used": next((a.model for a in reversed(attempts) if a.ok), None),
                    "attempts": [a.__dict__ for a in attempts],
                    "output": text,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif error is None and text is not None:
        print(text)
    if error:
        print(f"ai: {args.task}: {error}", file=sys.stderr)
        print(
            "ai: попытки: " + ", ".join(f"{a.model}({'ok' if a.ok else a.error})" for a in attempts),
            file=sys.stderr,
        )
        return 2
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    cfg = load_config()
    for name in sorted(cfg["models"], key=lambda n: cfg["models"][n].get("rank", 99)):
        spec = cfg["models"][name]
        try:
            resolved = resolve_model(cfg, name)
            endpoint = resolved.get("endpoint") or "<env>"
            model = resolved.get("model")
        except SystemExit as exc:
            endpoint, model = f"<err: {exc}>", spec.get("model")
        print(f"{name:<15} {spec.get('provider', ''):<22} {str(model):<44} {endpoint}")
    if args.tasks:
        print()
        for task, chain in cfg.get("tasks", {}).items():
            print(f"{task:<14} -> {' -> '.join(chain)}")
    return 0


def cmd_task_chain(args: argparse.Namespace) -> int:
    cfg = load_config()
    print(" ".join(task_chain(cfg, args.task)))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.json:
        print(json.dumps(build_report(cfg, args.since), ensure_ascii=False, indent=2))
        return 0
    return print_report(cfg, args.since)


def cmd_health(args: argparse.Namespace) -> int:
    """Проверка доступности эндпоинтов без отправки платных запросов."""
    cfg = load_config()
    rc = 0
    for name in sorted(cfg["models"], key=lambda n: cfg["models"][n].get("rank", 99)):
        spec = cfg["models"][name]
        try:
            resolved = resolve_model(cfg, name)
        except SystemExit as exc:
            print(f"{name:<15} SKIP  {exc}")
            continue
        endpoint = resolved.get("endpoint")
        if not endpoint:
            print(f"{name:<15} SKIP  эндпоинт не задан (env)")
            continue
        url = endpoint.rstrip("/") + ("/api/tags" if spec.get("provider") == "ollama" else "/health")
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                print(f"{name:<15} OK    {url} -> {resp.status}")
        except Exception as exc:  # noqa: BLE001 — health-проба, любая ошибка = недоступно
            print(f"{name:<15} DOWN  {url} -> {exc}")
            rc = 1
    return rc


def cmd_worktree(args: argparse.Namespace) -> int:
    script = PROJECT_ROOT / "scripts" / "ai" / "worktree"
    return subprocess.call([str(script), *args.rest])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai/run", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="выполнить задачу с эскалацией")
    run.add_argument("task", help="тип задачи из ai/models.yaml -> tasks")
    run.add_argument("-p", "--prompt", default="", help="текст промпта ('-' = stdin)")
    run.add_argument("-f", "--prompt-file", help="файл с промптом")
    run.add_argument("-s", "--system", help="system prompt")
    run.add_argument("--json", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="только маршрут, без вызова модели")
    run.set_defaults(func=cmd_run)

    models = sub.add_parser("models", help="список моделей и маршрутов")
    models.add_argument("--tasks", action="store_true")
    models.set_defaults(func=cmd_models)

    chain = sub.add_parser("chain", help="напечатать цепочку задачи")
    chain.add_argument("task")
    chain.set_defaults(func=cmd_task_chain)

    rep = sub.add_parser("report", help="отчёт по журналу")
    rep.add_argument("--since", help="ISO-дата, только события после неё")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_report)

    health = sub.add_parser("health", help="проверить доступность эндпоинтов")
    health.set_defaults(func=cmd_health)

    wt = sub.add_parser("worktree", help="прокси к scripts/ai/worktree")
    wt.add_argument("rest", nargs=argparse.REMAINDER)
    wt.set_defaults(func=cmd_worktree)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
