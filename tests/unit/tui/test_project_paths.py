"""`--url` projects follow the config (T-024)."""

from __future__ import annotations

from pathlib import Path

from pentool.core.config import Config
from pentool.tui.app import PentoolApp


def _app_with_config(config: Config) -> PentoolApp:
    # The method only needs `_cfg`; building the whole app (config load, proxy service) is
    # what these tests are trying to avoid.
    app = PentoolApp.__new__(PentoolApp)
    app._cfg = config
    return app


def test_project_path_uses_the_configured_projects_dir(tmp_path) -> None:
    config = Config(projects_dir=str(tmp_path / "projects"))
    app = _app_with_config(config)

    path = app._project_path_for_target("https://example.com/login")

    assert Path(path).parent == tmp_path / "projects"
    assert Path(path).parent.is_dir(), "каталог проектов должен создаваться по требованию"
    assert Path(path).name.startswith("example.com_")
    assert Path(path).suffix == ".db"


def test_project_path_isolated_under_an_explicit_config_file(tmp_path) -> None:
    cfg_file = tmp_path / "run" / "config.yaml"
    cfg_file.parent.mkdir()
    app = _app_with_config(Config.load(cfg_file))

    path = app._project_path_for_target("example.com")

    assert Path(path).parent == cfg_file.parent / "projects"
