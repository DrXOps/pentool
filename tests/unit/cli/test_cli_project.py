"""Unit tests: cli/project.py — `pentool project init/list`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from pentool.cli.project import project


def test_project_init_with_path(tmp_path):
    r = CliRunner().invoke(project, ["init", "--name", "testproj", "--path", str(tmp_path)])
    assert r.exit_code == 0
    proj_dir = tmp_path / "testproj"
    assert proj_dir.is_dir()
    # init_db creates the SQLite file + config.yaml during `project init`
    assert (proj_dir / "pentool.db").exists()
    assert (proj_dir / "config.yaml").exists()
    assert "testproj" in r.output


def test_project_init_sets_db_path_in_config(tmp_path):
    r = CliRunner().invoke(project, ["init", "--name", "p1", "--path", str(tmp_path)])
    assert r.exit_code == 0
    cfg_yaml = (tmp_path / "p1" / "config.yaml").read_text()
    # db_path, cert_dir, plugins_dir baked into the saved config
    assert str(tmp_path / "p1" / "pentool.db") in cfg_yaml


def test_project_init_uses_home_default(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with patch.object(Path, "home", classmethod(lambda cls: home)):
        r = CliRunner().invoke(project, ["init", "--name", "proj_default"])
    assert r.exit_code == 0
    assert (home / ".config" / "pentool" / "projects" / "proj_default").is_dir()


def test_project_init_db_error_exits(tmp_path):
    from pentool.core.db_schema import init_db
    with patch("pentool.cli.project.init_db", side_effect=RuntimeError("disk full")):
        r = CliRunner().invoke(project, ["init", "--name", "x", "--path", str(tmp_path)])
    assert r.exit_code == 1
    assert "Error initializing database" in r.output


def test_project_list_empty_when_no_projects_dir(tmp_path):
    home = tmp_path / "nohome"
    home.mkdir()
    with patch.object(Path, "home", classmethod(lambda cls: home)):
        r = CliRunner().invoke(project, ["list"])
    assert r.exit_code == 0
    assert "No projects found." in r.output


def test_project_list_empty_when_no_subdirs(tmp_path):
    home = tmp_path / "home"
    (home / ".config" / "pentool" / "projects").mkdir(parents=True)
    with patch.object(Path, "home", classmethod(lambda cls: home)):
        r = CliRunner().invoke(project, ["list"])
    assert r.exit_code == 0
    assert "No projects found." in r.output


def test_project_list_shows_projects(tmp_path):
    home = tmp_path / "home"
    proj_dir = home / ".config" / "pentool" / "projects"
    (proj_dir / "alpha").mkdir(parents=True)
    (proj_dir / "beta").mkdir()
    with patch.object(Path, "home", classmethod(lambda cls: home)):
        r = CliRunner().invoke(project, ["list"])
    assert r.exit_code == 0
    assert "alpha" in r.output
    assert "beta" in r.output
