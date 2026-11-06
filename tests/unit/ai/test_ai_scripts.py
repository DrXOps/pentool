"""Tests for .claude/hooks/context-state.sh and scripts/ai/worktree.

Both are shell scripts that a broken edit can silently damage, and both run
inside hooks where a non-zero exit or stray stdout has consequences:
`context-state.sh --restore` prints straight into the model's context, and
`worktree` mutates git state. These tests drive real subprocesses in a
throwaway git repo.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_HOOK = REPO_ROOT / ".claude" / "hooks" / "context-state.sh"
WORKTREE = REPO_ROOT / "scripts" / "ai" / "worktree"


def _run(cmd, cwd, stdin: str | None = None, env: dict | None = None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        cwd=cwd,
        input=stdin if stdin is not None else "",
        text=True,
        capture_output=True,
        env=full_env,
        timeout=60,
    )


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Мини-репозиторий: один коммит, один незакоммиченный файл."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", key, value], check=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "init"],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        },
    )
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# context-state.sh
# ---------------------------------------------------------------------------
def test_save_writes_snapshot_and_instructions(project: Path):
    res = _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    assert res.returncode == 0, res.stderr
    latest = project / ".claude" / "state" / "context" / "latest.md"
    assert latest.exists()
    body = latest.read_text(encoding="utf-8")
    assert "b.py" in body, "незакоммиченный файл должен попасть в состояние"
    # stdout PreCompact = инструкции для сжатия
    assert "обязательно сохрани" in res.stdout.lower()


def test_save_is_idempotent(project: Path):
    _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    first = _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    snaps = list((project / ".claude" / "state" / "context" / "snapshots").glob("*.md"))
    assert len(snaps) == 1, "повторный save без изменений не должен плодить снапшоты"
    assert "не изменилось" in first.stderr


def test_save_creates_new_snapshot_when_state_changes(project: Path):
    _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    (project / "c.py").write_text("z = 3\n", encoding="utf-8")
    _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    snaps = list((project / ".claude" / "state" / "context" / "snapshots").glob("*.md"))
    assert len(snaps) == 2


def test_save_rotates_snapshots(project: Path):
    for i in range(5):
        (project / f"f{i}.py").write_text(f"v = {i}\n", encoding="utf-8")
        _run(
            ["bash", str(CONTEXT_HOOK), "--save"],
            project,
            json.dumps({"trigger": "auto"}),
            env={"CONTEXT_KEEP": "2"},
        )
    snaps = list((project / ".claude" / "state" / "context" / "snapshots").glob("*.md"))
    assert len(snaps) == 2


def test_restore_is_silent_without_state(project: Path):
    res = _run(["bash", str(CONTEXT_HOOK), "--restore"], project, json.dumps({"source": "startup"}))
    assert res.returncode == 0
    assert res.stdout.strip() == "", "без снапшота хук не должен ничего вставлять в контекст"


def test_restore_marks_compact_source(project: Path):
    _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    res = _run(["bash", str(CONTEXT_HOOK), "--restore"], project, json.dumps({"source": "compact"}))
    assert res.returncode == 0
    assert "после сжатия" in res.stdout
    assert "b.py" in res.stdout


def test_restore_truncates_long_state(project: Path):
    for i in range(60):
        (project / f"many_{i}.py").write_text("x=1\n", encoding="utf-8")
    _run(["bash", str(CONTEXT_HOOK), "--save"], project, json.dumps({"trigger": "auto"}))
    res = _run(
        ["bash", str(CONTEXT_HOOK), "--restore"],
        project,
        json.dumps({"source": "startup"}),
        env={"CONTEXT_RESTORE_CHARS": "200"},
    )
    assert "обрезана" in res.stdout
    assert len(res.stdout) < 600


def test_log_appends_without_storing_summary(project: Path):
    payload = json.dumps({"trigger": "auto", "compact_summary": "SECRET-SUMMARY-TEXT" * 20})
    _run(["bash", str(CONTEXT_HOOK), "--log"], project, payload)
    log = project / ".claude" / "state" / "context" / "compactions.jsonl"
    assert log.exists()
    content = log.read_text(encoding="utf-8")
    assert "SECRET-SUMMARY-TEXT" not in content, "тело сводки не должно писаться в журнал"
    entry = json.loads(content.strip().splitlines()[-1])
    assert entry["trigger"] == "auto"
    assert entry["summary_chars"] == len("SECRET-SUMMARY-TEXT" * 20)


def test_unknown_mode_fails(project: Path):
    res = _run(["bash", str(CONTEXT_HOOK), "--bogus"], project)
    assert res.returncode == 1


def test_hook_works_without_jq(project: Path):
    """jq не обязателен: хуки должны пережить его отсутствие."""
    path = ":".join(p for p in os.environ.get("PATH", "").split(":") if p and not (Path(p) / "jq").exists())
    res = _run(
        ["bash", str(CONTEXT_HOOK), "--save"],
        project,
        json.dumps({"trigger": "auto", "session_id": "S"}),
        env={"PATH": path},
    )
    assert res.returncode == 0
    assert (project / ".claude" / "state" / "context" / "latest.md").exists()


# ---------------------------------------------------------------------------
# scripts/ai/worktree
# ---------------------------------------------------------------------------
def test_worktree_create_list_remove(project: Path):
    res = _run(["bash", str(WORKTREE), "create", "agent-a"], project)
    assert res.returncode == 0, res.stderr
    wt = project / ".worktrees" / "agent-a"
    assert wt.is_dir()
    assert (wt / ".worktree-env").exists()
    # Каталог worktrees должен быть в .gitignore, иначе он попадёт в коммит.
    ignore = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".worktrees/" in ignore

    listed = _run(["bash", str(WORKTREE), "list"], project)
    assert "agent-a" in listed.stdout

    removed = _run(["bash", str(WORKTREE), "remove", "agent-a"], project)
    assert removed.returncode == 0, removed.stderr
    assert not wt.exists()


def test_worktree_env_isolation(project: Path):
    _run(["bash", str(WORKTREE), "create", "agent-b"], project)
    res = _run(["bash", str(WORKTREE), "env", "agent-b"], project)
    assert res.returncode == 0
    values = {}
    for line in res.stdout.splitlines():
        if line.startswith("export "):
            key, _, value = line[len("export ") :].partition("=")
            values[key] = value.strip("'")
    assert values["AI_WORKTREE_NAME"] == "agent-b"
    assert values["AI_WORKTREE_PATH"].endswith(".worktrees/agent-b")
    assert values["TMPDIR"].endswith(".worktrees/agent-b/tmp")
    # Порт из стабильного диапазона, а не общий для всех worktree.
    assert values["AI_PORT"].isdigit()
    assert int(values["AI_PORT"]) >= 9100


def test_worktree_ports_differ_per_name(project: Path):
    _run(["bash", str(WORKTREE), "create", "one"], project)
    _run(["bash", str(WORKTREE), "create", "two"], project)
    ports = []
    for name in ("one", "two"):
        res = _run(["bash", str(WORKTREE), "env", name], project)
        ports.append(res.stdout.split("AI_PORT='")[1].split("'")[0])
    assert ports[0] != ports[1], "worktree должны получать разные порты"


def test_worktree_create_is_idempotent(project: Path):
    first = _run(["bash", str(WORKTREE), "create", "dup"], project)
    second = _run(["bash", str(WORKTREE), "create", "dup"], project)
    assert first.returncode == 0 and second.returncode == 0
    assert "уже существует" in second.stdout


def test_worktree_remove_preserves_unmerged_branch(project: Path):
    _run(["bash", str(WORKTREE), "create", "wip"], project)
    wt = project / ".worktrees" / "wip"
    (wt / "new.py").write_text("n = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(wt), "add", "."], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "wip"], check=True)
    res = _run(["bash", str(WORKTREE), "remove", "--force", "wip"], project)
    assert "сохранена" in res.stdout
    branches = subprocess.run(
        ["git", "-C", str(project), "branch", "--list", "ai/wip"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "ai/wip" in branches
