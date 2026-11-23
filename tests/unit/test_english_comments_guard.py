"""Guard "comments in code are in English" (ratchet).

Project debt: 3466 lines of Cyrillic in comments and docstrings (2026-11-19).
Translating everything at once is not allowed — that means rewriting one and a
half thousand lines interleaved with logic. The guard holds the ceiling: a new
Russian comment fails the commit, while per-file translation lowers the baseline.
"""

from __future__ import annotations

import json

import pytest

import tools.check_english_comments as guard


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Own root and own baseline — the real repository is left untouched."""
    package = tmp_path / "pentool"
    package.mkdir()
    # The root is replaced as well: paths in the report are counted from it.
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "TARGETS", [package])
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(guard, "BASELINE", baseline)
    return package, baseline


def test_english_comments_are_clean(sandbox) -> None:
    package, _ = sandbox
    (package / "ok.py").write_text(
        '"""Module docstring in English."""\n\n# A comment in English.\nVALUE = 1\n',
        encoding="utf-8",
    )
    assert guard.scan() == {}


def test_russian_comment_is_detected(sandbox) -> None:
    package, _ = sandbox
    (package / "bad.py").write_text("# Проверяем значение\nVALUE = 1\n", encoding="utf-8")

    assert guard.scan() == {"pentool/bad.py": 1}
    # the line number is returned too (for --list and for fixes)
    assert guard.list_violations() == [("pentool/bad.py", 1)]


def test_russian_docstring_is_detected(sandbox) -> None:
    package, _ = sandbox
    (package / "bad_doc.py").write_text(
        '"""Модуль для проверки."""\n\n\ndef run() -> None:\n    """Запуск."""\n',
        encoding="utf-8",
    )
    assert guard.scan() == {"pentool/bad_doc.py": 2}


def test_russian_string_data_is_not_a_violation(sandbox) -> None:
    """Cyrillic in data is not a comment: UI localization and test strings."""
    package, _ = sandbox
    (package / "data.py").write_text('LABEL = "Сохранить"\n', encoding="utf-8")
    assert guard.scan() == {}


def test_pragma_allows_deliberate_russian(sandbox) -> None:
    package, _ = sandbox
    (package / "pragmatic.py").write_text(
        "# i18n-ok: пример локали в тесте\nLABEL = 1\n",
        encoding="utf-8",
    )
    assert guard.scan() == {}


def test_growth_over_baseline_fails(sandbox, capsys) -> None:
    package, baseline = sandbox
    (package / "one.py").write_text("# один\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/one.py": 1}

    (package / "one.py").write_text("# один\n# два\n", encoding="utf-8")
    assert guard.main([]) == 1
    assert "one.py: 1 -> 2" in capsys.readouterr().err


def test_update_lowers_but_never_raises(sandbox, capsys) -> None:
    package, baseline = sandbox
    (package / "two.py").write_text("# один\n# два\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/two.py": 2}

    # one line translated — the ceiling goes down
    (package / "two.py").write_text("# one\n# два\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/two.py": 1}

    # grew again — the baseline does NOT rise, a normal run fails
    (package / "two.py").write_text("# one\n# два\n# три\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/two.py": 1}
    assert guard.main([]) == 1


def test_repository_baseline_is_sorted_and_positive() -> None:
    """The repository baseline must be valid: paths sorted, values > 0."""
    baseline = guard.load_baseline()
    keys = list(baseline)
    assert keys == sorted(keys)
    assert all(value > 0 for value in baseline.values())


def test_empty_baseline_means_no_remaining_debt() -> None:
    """An empty baseline is the goal (debt paid), never a skipped measurement."""
    if not guard.load_baseline():
        assert guard.scan() == {}, "baseline is empty while violations still exist — run --update"
