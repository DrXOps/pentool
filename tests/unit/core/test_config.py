"""Unit-тесты: core/config.py

Покрывает: Config dataclass, save/load, get_config, set_config.
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
        """Неизвестные ключи в YAML не вызывают ошибок."""
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
    """Unit-тесты для Network настроек (Блок 4.10)."""

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
