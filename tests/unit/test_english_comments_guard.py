"""Гвард «комментарии в коде — на английском» (трещотка).

Долг проекта: 3466 строк кириллицы в комментариях и докстрингах (2026-11-19).
Переводить всё сразу нельзя — это переписывание полутора тысяч строк
вперемешку с логикой. Гвард держит потолок: новый русский комментарий роняет
коммит, а пофайловый перевод понижает базу.
"""

from __future__ import annotations

import json

import pytest

import tools.check_english_comments as guard


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Свой корень и своя база — не трогаем реальный репозиторий."""
    package = tmp_path / "pentool"
    package.mkdir()
    # Корень тоже подменяем: пути в отчёте считаются от него.
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
    # номер строки тоже отдаётся (для --list и правок)
    assert guard.list_violations() == [("pentool/bad.py", 1)]


def test_russian_docstring_is_detected(sandbox) -> None:
    package, _ = sandbox
    (package / "bad_doc.py").write_text(
        '"""Модуль для проверки."""\n\n\ndef run() -> None:\n    """Запуск."""\n',
        encoding="utf-8",
    )
    assert guard.scan() == {"pentool/bad_doc.py": 2}


def test_russian_string_data_is_not_a_violation(sandbox) -> None:
    """Кириллица в данных — это не комментарий: локализация UI и тестовые строки."""
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

    # перевели одну строку — потолок опускается
    (package / "two.py").write_text("# one\n# два\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/two.py": 1}

    # выросли снова — база НЕ поднимается, обычный прогон падает
    (package / "two.py").write_text("# one\n# два\n# три\n", encoding="utf-8")
    guard.main(["--update"])
    assert json.loads(baseline.read_text(encoding="utf-8")) == {"pentool/two.py": 1}
    assert guard.main([]) == 1


def test_repository_baseline_is_sorted_and_positive() -> None:
    """База репозитория должна быть валидной: пути отсортированы, значения > 0."""
    baseline = guard.load_baseline()
    assert baseline, "база пуста: значит замер не делался"
    keys = list(baseline)
    assert keys == sorted(keys)
    assert all(value > 0 for value in baseline.values())
