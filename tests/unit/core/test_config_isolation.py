"""Projects directory follows the config file (T-024).

`--config /tmp/run/config.yaml` used to switch only the values written in that file: the
database, certificates, plugins, logs and `--url` projects still landed in
`~/.config/pentool`, so two "isolated" runs shared one history. Now a config file outside the
default directory moves those paths next to itself, while values written in the file win.
"""

from __future__ import annotations

import yaml

from pentool.core.config import DEFAULT_CONFIG_DIR, Config


class TestExplicitConfigPath:
    def test_default_paths_move_next_to_the_config_file(self, tmp_path) -> None:
        cfg_file = tmp_path / "run" / "config.yaml"
        cfg_file.parent.mkdir()

        cfg = Config.load(cfg_file)

        base = cfg_file.parent
        assert cfg.db_path == str(base / "pentool.db")
        assert cfg.cert_dir == str(base / "certs")
        assert cfg.plugins_dir == str(base / "plugins")
        assert cfg.log_file == str(base / "logs" / "pentool.log")
        assert cfg.projects_dir == str(base / "projects")

    def test_values_written_in_the_file_win(self, tmp_path) -> None:
        cfg_file = tmp_path / "run" / "config.yaml"
        cfg_file.parent.mkdir()
        cfg_file.write_text(
            yaml.dump({"db_path": "/custom/run.db", "projects_dir": "/custom/projects"}),
            encoding="utf-8",
        )

        cfg = Config.load(cfg_file)

        assert cfg.db_path == "/custom/run.db"
        assert cfg.projects_dir == "/custom/projects"
        # Untouched paths still follow the file.
        assert cfg.cert_dir == str(cfg_file.parent / "certs")

    def test_save_writes_back_to_the_loaded_file(self, tmp_path) -> None:
        cfg_file = tmp_path / "run" / "config.yaml"
        cfg_file.parent.mkdir()
        cfg_file.write_text("proxy_port: 8099\n", encoding="utf-8")

        cfg = Config.load(cfg_file)
        cfg.add_recent_project(str(tmp_path / "some.db"))

        saved = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        assert saved["proxy_port"] == 8099
        assert saved["projects_dir"] == cfg.projects_dir == str(cfg_file.parent / "projects")
        assert saved["db_path"] == str(cfg_file.parent / "pentool.db")

    def test_default_config_dir_is_what_it_always_was(self) -> None:
        cfg = Config()
        assert cfg.projects_dir == str(DEFAULT_CONFIG_DIR / "projects")
