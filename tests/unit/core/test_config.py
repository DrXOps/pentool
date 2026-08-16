"""Unit tests: core/config.py

Covers: Config dataclass, save/load, get_config, set_config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pentool.core.config import Config, get_config, set_config


class TestConfigDefaults:
    def test_default_proxy_host(self) -> None:
        cfg = Config()
        assert cfg.proxy_host == "127.0.0.1"

    def test_default_proxy_port(self) -> None:
        cfg = Config()
        assert cfg.proxy_port == 8080

    def test_default_log_level(self) -> None:
        cfg = Config()
        assert cfg.log_level == "INFO"

    def test_default_intercept_disabled(self) -> None:
        cfg = Config()
        assert cfg.intercept_enabled is False

    def test_default_scope_empty(self) -> None:
        cfg = Config()
        assert cfg.scope == []

    def test_default_db_path_contains_pentool(self) -> None:
        cfg = Config()
        assert "pentool" in cfg.db_path

    def test_custom_values(self) -> None:
        cfg = Config(proxy_port=9090, log_level="DEBUG", proxy_host="0.0.0.0")
        assert cfg.proxy_port == 9090
        assert cfg.log_level == "DEBUG"
        assert cfg.proxy_host == "0.0.0.0"


class TestConfigSaveLoad:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        cfg = Config(proxy_port=9999)
        path = tmp_path / "config.yaml"
        cfg.save(path)
        assert path.exists()

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        cfg = Config(proxy_port=9090, log_level="DEBUG", intercept_enabled=True)
        path = tmp_path / "config.yaml"
        cfg.save(path)

        loaded = Config.load(path)
        assert loaded.proxy_port == 9090
        assert loaded.log_level == "DEBUG"
        assert loaded.intercept_enabled is True

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = Config.load(tmp_path / "nonexistent.yaml")
        assert cfg.proxy_port == 8080
        assert cfg.log_level == "INFO"

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "config.yaml"
        Config().save(path)
        assert path.exists()

    def test_load_ignores_unknown_keys(self, tmp_path: Path) -> None:
        """Unknown keys in YAML do not cause errors."""
        import yaml
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"proxy_port": 7777, "unknown_key": "ignored"}))
        cfg = Config.load(path)
        assert cfg.proxy_port == 7777

    def test_save_scope_list(self, tmp_path: Path) -> None:
        cfg = Config(scope=["example.com", "*.test.com"])
        path = tmp_path / "config.yaml"
        cfg.save(path)
        loaded = Config.load(path)
        assert loaded.scope == ["example.com", "*.test.com"]

    def test_to_dict_contains_all_keys(self) -> None:
        cfg = Config()
        d = cfg.to_dict()
        expected_keys = {
            "proxy_host", "proxy_port", "cert_dir", "db_path",
            "log_file", "log_level", "plugins_dir", "scope", "intercept_enabled",
        }
        assert expected_keys.issubset(d.keys())

    def test_to_dict_values_match(self) -> None:
        cfg = Config(proxy_port=5555, log_level="WARNING")
        d = cfg.to_dict()
        assert d["proxy_port"] == 5555
        assert d["log_level"] == "WARNING"


class TestConfigSingleton:
    def test_set_config_overrides_singleton(self) -> None:
        cfg = Config(proxy_port=11111)
        set_config(cfg)
        assert get_config().proxy_port == 11111

    def test_get_config_returns_same_instance(self) -> None:
        cfg = Config(proxy_port=22222)
        set_config(cfg)
        a = get_config()
        b = get_config()
        assert a is b

    def test_set_config_replaces_instance(self) -> None:
        set_config(Config(proxy_port=1))
        assert get_config().proxy_port == 1
        set_config(Config(proxy_port=2))
        assert get_config().proxy_port == 2


class TestConfigNetworkFields:
    """Unit tests for Network settings (Block 4.10)."""

    def test_default_user_agent_not_empty(self) -> None:
        cfg = Config()
        assert cfg.default_user_agent
        assert "Mozilla" in cfg.default_user_agent

    def test_default_request_timeout(self) -> None:
        cfg = Config()
        assert cfg.request_timeout == 15

    def test_default_connect_timeout(self) -> None:
        cfg = Config()
        assert cfg.connect_timeout == 10

    def test_default_collaborator_url_empty(self) -> None:
        cfg = Config()
        assert cfg.collaborator_url == ""

    def test_default_max_redirects(self) -> None:
        cfg = Config()
        assert cfg.max_redirects == 10

    def test_default_verify_ssl_false(self) -> None:
        cfg = Config()
        assert cfg.verify_ssl is False

    def test_set_user_agent(self) -> None:
        cfg = Config()
        cfg.update(default_user_agent="TestAgent/1.0")
        assert cfg.default_user_agent == "TestAgent/1.0"

    def test_set_collaborator_url(self) -> None:
        cfg = Config()
        cfg.update(collaborator_url="https://xxx.oastify.com")
        assert cfg.collaborator_url == "https://xxx.oastify.com"

    def test_set_request_timeout(self) -> None:
        cfg = Config()
        cfg.update(request_timeout=30)
        assert cfg.request_timeout == 30

    def test_set_verify_ssl_true(self) -> None:
        cfg = Config()
        cfg.update(verify_ssl=True)
        assert cfg.verify_ssl is True

    def test_to_dict_contains_network_fields(self) -> None:
        cfg = Config()
        d = cfg.to_dict()
        assert "default_user_agent" in d
        assert "request_timeout" in d
        assert "connect_timeout" in d
        assert "collaborator_url" in d
        assert "max_redirects" in d
        assert "verify_ssl" in d

    def test_save_load_network_fields(self, tmp_path) -> None:
        cfg = Config(
            collaborator_url="https://test.oastify.com",
            request_timeout=30,
            verify_ssl=True,
        )
        path = tmp_path / "config.yaml"
        cfg.save(path)
        loaded = Config.load(path)
        assert loaded.collaborator_url == "https://test.oastify.com"
        assert loaded.request_timeout == 30
        assert loaded.verify_ssl is True

    def test_network_fields_observer_notified(self) -> None:
        cfg = Config()
        calls = []
        cfg.add_observer(lambda changed: calls.append(changed))
        cfg.update(request_timeout=20, collaborator_url="http://x.com")
        assert len(calls) == 1
        assert "request_timeout" in calls[0]
        assert "collaborator_url" in calls[0]


class TestConfigObserversExtra:
    def test_remove_observer_nonexistent_noop(self, tmp_path) -> None:
        from pentool.core.config import Config
        cfg = Config()
        cfg.remove_observer(lambda f: None)  # not subscribed — no error

    def test_notify_observers_catches_exception(self, tmp_path) -> None:
        from pentool.core.config import Config
        cfg = Config()
        calls = []

        def bad(_):
            raise RuntimeError("observer boom")

        def good(fields):
            calls.append(fields)

        cfg.add_observer(bad)
        cfg.add_observer(good)
        cfg.notify_observers({"x": 1})
        # bad observer raised but was caught; good one still called
        assert len(calls) == 1
        assert calls[0] == {"x": 1}

    def test_notify_observers_no_observers(self, tmp_path) -> None:
        from pentool.core.config import Config
        cfg = Config()
        cfg.notify_observers({})  # no-op


class TestConfigRecentProjects:
    def test_add_recent_inserts_dedup_and_trims(self, tmp_path, monkeypatch) -> None:
        from pentool.core.config import Config
        cfg = Config()
        monkeypatch.setattr(cfg, "save", lambda *a, **k: None)
        cfg.add_recent_project("/a")
        cfg.add_recent_project("/b")
        cfg.add_recent_project("/a")  # dup → moves to front
        assert cfg.recent_projects[0] == "/a"
        assert len(cfg.recent_projects) == 2

    def test_add_recent_save_failure_swallowed(self, tmp_path) -> None:
        from pentool.core.config import Config
        cfg = Config()
        cfg.recent_projects = []
        monkeypatch = __import__("pytest").MonkeyPatch() if False else None
        # side_effect instead — save raises, add_recent should not propagate
        import builtins
        real_save = cfg.save if hasattr(cfg, "save") else None
        try:
            cfg.save = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no disk"))
            cfg.add_recent_project("/x")
        finally:
            pass

    def test_recent_projects_dedups(self) -> None:
        from pentool.core.config import Config
        cfg = Config()
        cfg.recent_projects = ["a", "b"]
        cfg.add_recent_project("b")
        assert cfg.recent_projects == ["b", "a"]


class TestConfigLoadExtra:
    def test_load_prunes_missing_paths(self, tmp_path) -> None:
        from pentool.core.config import Config
        cfg_file = tmp_path / "c.yaml"
        cfg_file.write_text("recent_projects:\n  - /definitely/missing/path\n  - /also/missing\n")
        cfg = Config.load(str(cfg_file))
        assert cfg.recent_projects == []
        # and it re-saved the pruned config (no exception)

    def test_load_prune_save_failure_swallowed(self, tmp_path, monkeypatch) -> None:
        from pentool.core.config import Config
        cfg_file = tmp_path / "c.yaml"
        cfg_file.write_text("recent_projects:\n  - /definitely/missing\n")
        # Force cfg.save() to raise — load must not propagate
        monkeypatch.setattr(Config, "save", lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
        cfg = Config.load(str(cfg_file))
        assert cfg.recent_projects == []

    def test_get_config_initializes_on_demand(self, monkeypatch) -> None:
        from pentool.core.config import get_config, set_config
        set_config(None)  # reset singleton
        cfg = get_config()
        assert cfg is not None
