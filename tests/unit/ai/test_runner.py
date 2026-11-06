"""Unit tests for the ai/ task router (ai/runner.py).

Covers the parts that are easy to break and expensive to debug in a real run:
config parsing (including the stdlib fallback), task-chain resolution,
env-based endpoint/model overrides, provider payload shaping, escalation
behaviour and the report aggregation.

No network: `_post_json` is monkeypatched. No real credentials.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

AI_DIR = Path(__file__).resolve().parents[3] / "ai"


def _load_runner():
    spec = importlib.util.spec_from_file_location("ai_runner_under_test", AI_DIR / "runner.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


@pytest.fixture()
def cfg():
    return runner.load_config()


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
def test_config_has_models_and_tasks(cfg):
    assert cfg["models"], "в models.yaml нет моделей"
    assert cfg["tasks"], "в models.yaml нет маршрутов задач"
    # Каждая цепочка ссылается только на известные модели.
    for task, chain in cfg["tasks"].items():
        for name in chain:
            assert name in cfg["models"], f"{task}: неизвестная модель {name}"


def test_config_documents_context_window(cfg):
    window = cfg["context"]["window_tokens"]
    assert 100_000 <= window <= 1_000_000, "autoCompactWindow вне допустимого диапазона"


def test_yaml_fallback_matches_pyyaml(cfg):
    """Встроенный парсер обязан давать тот же результат, что PyYAML.

    ai/ кладётся в проекты без Python-зависимостей — там PyYAML может
    отсутствовать, и работает фолбэк. Расхождение между ними — тихий баг.
    """
    yaml = pytest.importorskip("yaml")
    text = (AI_DIR / "models.yaml").read_text(encoding="utf-8")
    assert runner._parse_yaml_subset(text) == yaml.safe_load(text)


def test_yaml_fallback_rejects_bad_line():
    with pytest.raises(ValueError):
        runner._parse_yaml_subset("models: 1\n  broken line without colon\n")


def test_parse_scalar_types():
    assert runner._parse_scalar("42") == 42
    assert runner._parse_scalar("1.5") == 1.5
    assert runner._parse_scalar("true") is True
    assert runner._parse_scalar("null") is None
    assert runner._parse_scalar("[a, b]") == ["a", "b"]
    assert runner._parse_scalar("plain") == "plain"


# ---------------------------------------------------------------------------
# Маршрутизация
# ---------------------------------------------------------------------------
def test_task_chain_order(cfg):
    chain = runner.task_chain(cfg, "test-fix")
    assert chain[0] == "local-coder", "рутина должна начинаться с экономной модели"
    assert chain[-1] == "deepseek-pro", "эскалация должна заканчиваться сильной моделью"


def test_unknown_task_raises(cfg):
    with pytest.raises(SystemExit):
        runner.task_chain(cfg, "no-such-task")


def test_unknown_model_raises(cfg):
    with pytest.raises(SystemExit):
        runner.resolve_model(cfg, "no-such-model")


# ---------------------------------------------------------------------------
# Переопределения через окружение
# ---------------------------------------------------------------------------
def test_endpoint_and_model_from_env(cfg, monkeypatch):
    monkeypatch.setenv("OLLAMA_ENDPOINT", "http://example.invalid:1234")
    monkeypatch.setenv("OLLAMA_MODEL", "custom:1b")
    spec = runner.resolve_model(cfg, "local-coder")
    assert spec["endpoint"] == "http://example.invalid:1234"
    assert spec["model"] == "custom:1b"


def test_missing_endpoint_env_is_explicit_error(cfg, monkeypatch):
    """Облачная модель без эндпоинта — понятная ошибка, а не пустой URL."""
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        runner.resolve_model(cfg, "deepseek-flash")
    assert "ANTHROPIC_BASE_URL" in str(exc.value)


# ---------------------------------------------------------------------------
# Провайдеры (без сети)
# ---------------------------------------------------------------------------
def test_anthropic_text_blocks_only(cfg, monkeypatch):
    """Блоки thinking не должны попадать в вывод задачи."""
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://gw.invalid")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    spec = runner.resolve_model(cfg, "deepseek-flash")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "content": [
                {"type": "thinking", "thinking": "internal reasoning"},
                {"type": "text", "text": "PONG"},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

    monkeypatch.setattr(runner, "_post_json", fake_post)
    text, usage = runner.call_anthropic_compatible(spec, "say PONG", None)
    assert text == "PONG"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 2}
    assert captured["url"] == "http://gw.invalid/v1/messages"
    assert captured["payload"]["model"] == spec["model"]


def test_anthropic_missing_token_is_config_error(cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://gw.invalid")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = runner.resolve_model(cfg, "deepseek-flash")
    with pytest.raises(runner.ProviderError) as exc:
        runner.call_anthropic_compatible(spec, "x", None)
    assert exc.value.kind == "config"


def test_ollama_payload_shape(cfg, monkeypatch):
    spec = runner.resolve_model(cfg, "local-coder")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured.update(url=url, payload=payload)
        return {"response": "ok", "prompt_eval_count": 3, "eval_count": 1}

    monkeypatch.setattr(runner, "_post_json", fake_post)
    text, usage = runner.call_ollama(spec, "hello", "sys")
    assert text == "ok"
    assert captured["url"].endswith("/api/generate")
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["system"] == "sys"
    assert usage["prompt_tokens"] == 3


# ---------------------------------------------------------------------------
# Эскалация
# ---------------------------------------------------------------------------
def test_escalation_on_network_error(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "log_event", lambda *a, **k: None)
    calls = []

    def fake_call(spec, prompt, system):
        calls.append(spec["model"])
        if spec["provider"] == "ollama":
            raise runner.ProviderError("network", "down")
        return "answer", {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(runner, "call_model", fake_call)
    text, attempts, error = runner.run_task(cfg, "lint", "prompt")
    assert error is None
    assert text == "answer"
    assert [a.model for a in attempts] == ["local-coder", "deepseek-flash"]
    assert attempts[0].ok is False and attempts[1].ok is True


def test_no_escalation_on_config_error(cfg, monkeypatch):
    """Ошибка конфигурации не лечится сменой модели — цепочка сразу падает."""
    monkeypatch.setattr(runner, "log_event", lambda *a, **k: None)

    def fake_call(spec, prompt, system):
        raise runner.ProviderError("config", "no token")

    monkeypatch.setattr(runner, "call_model", fake_call)
    text, attempts, error = runner.run_task(cfg, "test-fix", "prompt")
    assert text is None
    assert error and "config" in error
    assert len(attempts) == 1


def test_exhausted_chain_returns_error(cfg, monkeypatch):
    monkeypatch.setattr(runner, "log_event", lambda *a, **k: None)

    def fake_call(spec, prompt, system):
        raise runner.ProviderError("timeout", "too slow")

    monkeypatch.setattr(runner, "call_model", fake_call)
    text, attempts, error = runner.run_task(cfg, "lint", "prompt")
    assert text is None
    assert error == "цепочка эскалации исчерпана"
    assert len(attempts) == len(runner.task_chain(cfg, "lint"))


def test_dry_run_touches_no_provider(cfg, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry-run не должен вызывать модель")

    monkeypatch.setattr(runner, "call_model", boom)
    text, attempts, error = runner.run_task(cfg, "docs", "x", dry_run=True)
    assert error is None
    assert text and text.startswith("[dry-run]")


# ---------------------------------------------------------------------------
# Отчёт и журнал
# ---------------------------------------------------------------------------
def _write_events(tmp_path, path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n")


def test_report_aggregates_local_and_cloud(tmp_path, cfg, monkeypatch):
    log = tmp_path / "events.jsonl"
    _write_events(
        tmp_path,
        log,
        [
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "attempt_ok",
                "model": "local-coder",
                "duration_sec": 2.0,
                "prompt_tokens": 100,
                "completion_tokens": 50,
            },
            {
                "ts": "2026-01-01T00:00:01Z",
                "event": "attempt_ok",
                "model": "deepseek-flash",
                "duration_sec": 1.0,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "escalated": True,
            },
            {
                "ts": "2026-01-01T00:00:02Z",
                "event": "attempt_failed",
                "model": "local-coder",
                "error_kind": "timeout",
            },
        ],
    )
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    cfg = json.loads(json.dumps(cfg))
    cfg["logging"]["events_path"] = "events.jsonl"

    rep = runner.build_report(cfg)
    assert rep["ok_calls"] == 2
    assert rep["local_calls"] == 1
    assert rep["cloud_calls"] == 1
    assert rep["escalations"] == 1
    assert rep["saved_local_calls"] == 1
    assert rep["failure_reasons"] == {"timeout": 1}
    assert rep["local_share"] == 0.5


def test_report_on_empty_log(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    cfg = json.loads(json.dumps(cfg))
    cfg["logging"]["events_path"] = "missing.jsonl"
    rep = runner.build_report(cfg)
    assert rep["events"] == 0
    assert "message" in rep


def test_log_event_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    cfg = {"logging": {"events_path": "logs/e.jsonl", "max_bytes": 200, "keep_files": 2}}
    for i in range(10):
        runner.log_event(cfg, {"event": "attempt_ok", "model": "m", "n": i})
    files = sorted(p.name for p in (tmp_path / "logs").iterdir())
    assert "e.jsonl" in files
    assert any(name.startswith("e.jsonl.") for name in files)
    assert len([f for f in files if f.startswith("e.jsonl")]) <= 3  # текущий + keep_files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_chain_prints_expected_order(capsys):
    rc = runner.main(["chain", "debug"])
    assert rc == 0
    out = capsys.readouterr().out.split()
    assert out[0] == "deepseek-flash"


def test_cli_rejects_empty_prompt(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: "")})())
    rc = runner.main(["run", "lint", "-p", "-"])
    assert rc == 1
    assert "пустой промпт" in capsys.readouterr().err
