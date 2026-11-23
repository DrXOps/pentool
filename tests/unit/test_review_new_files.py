"""Gate for new files: the "keep in the repository" or "add to .gitignore" decision.

We check the decision itself, not the directory: `pre-commit-guard` already filters
junk by path, but inside allowed directories drafts and one-off scripts slipped
through silently (that is how `aaaaaaaaaaaa.png`, `bug.png`, `tui-lab/` and the
ELF binary `bin/xclip` ended up in origin).
"""

from __future__ import annotations

import pytest

from tools.review_new_files import DECISIONS, IGNORE, KEEP, check, load_decisions, main, save_decision


def test_no_added_files_means_no_problems() -> None:
    assert check([], {}, set()) == []


def test_undecided_file_blocks_the_commit_and_names_the_command() -> None:
    problems = check(["tools/new_thing.py"], {}, set())
    assert len(problems) == 1
    assert "--decide tools/new_thing.py" in problems[0]
    assert "keep|ignore" in problems[0]


def test_keep_decision_passes() -> None:
    assert check(["tools/new_thing.py"], {"tools/new_thing.py": KEEP}, set()) == []


def test_ignore_decision_requires_a_real_gitignore_rule() -> None:
    """Otherwise the "local" file still goes to origin on the next git add -A."""
    problems = check(["scratch.py"], {"scratch.py": IGNORE}, set())
    assert len(problems) == 1
    assert ".gitignore" in problems[0]

    assert check(["scratch.py"], {"scratch.py": IGNORE}, {"scratch.py"}) == []


def test_decision_for_another_file_does_not_cover_this_one() -> None:
    problems = check(["a.py"], {"b.py": KEEP}, set())
    assert len(problems) == 1


def test_decisions_roundtrip(tmp_path) -> None:
    path = tmp_path / "decisions.tsv"
    save_decision("tools/a.py", KEEP, path=path)
    save_decision("scratch/b.py", IGNORE, path=path)

    decisions = load_decisions(path)
    assert decisions == {"tools/a.py": KEEP, "scratch/b.py": IGNORE}


def test_unknown_decision_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        save_decision("x.py", "maybe", path=tmp_path / "d.tsv")


def test_cli_decide_writes_decision(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tools.review_new_files.DECISIONS", tmp_path / "decisions.tsv")
    assert main(["--decide", "tools/a.py", "keep"]) == 0
    assert load_decisions(tmp_path / "decisions.tsv") == {"tools/a.py": KEEP}


def test_repository_decisions_file_is_parseable(tmp_path) -> None:
    """The repository decisions file (if any) must load without garbage."""
    if not DECISIONS.is_file():
        pytest.skip("журнал решений ещё не создан")
    decisions = load_decisions()
    assert all(value in (KEEP, IGNORE) for value in decisions.values())
