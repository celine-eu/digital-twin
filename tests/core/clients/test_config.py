# tests/core/clients/test_config.py
from __future__ import annotations

import pytest
from pathlib import Path

from celine.dt.core.clients.config import load_clients_config, ClientSpec


class TestLoadClientsConfig:
    def test_load_simple_client(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BASE_URL", "http://example.com")

        config_file = tmp_path / "clients.yaml"
        config_file.write_text(
            """
clients:
  my_client:
    class: some.module:MyClass
    config:
      base_url: "${BASE_URL}"
      timeout: 30
""",
            encoding="utf-8",
        )

        cfg = load_clients_config([str(config_file)])

        assert len(cfg.clients) == 1
        client = cfg.clients[0]
        assert client.name == "my_client"
        assert client.class_path == "some.module:MyClass"
        assert client.config["base_url"] == "http://example.com"
        assert client.config["timeout"] == 30

    def test_load_client_with_inject(self, tmp_path: Path):
        config_file = tmp_path / "clients.yaml"
        config_file.write_text(
            """
clients:
  auth_client:
    class: some.module:AuthClient
    inject:
      - token_provider
      - other_service
    config:
      base_url: "http://localhost"
""",
            encoding="utf-8",
        )

        cfg = load_clients_config([str(config_file)])

        assert len(cfg.clients) == 1
        client = cfg.clients[0]
        assert client.inject == ["token_provider", "other_service"]

    def test_load_multiple_clients(self, tmp_path: Path):
        config_file = tmp_path / "clients.yaml"
        config_file.write_text(
            """
clients:
  client_a:
    class: module.a:ClientA
    config:
      key: a
  client_b:
    class: module.b:ClientB
    config:
      key: b
""",
            encoding="utf-8",
        )

        cfg = load_clients_config([str(config_file)])

        assert len(cfg.clients) == 2
        names = {c.name for c in cfg.clients}
        assert names == {"client_a", "client_b"}

    def test_later_file_overrides(self, tmp_path: Path):
        (tmp_path / "01_base.yaml").write_text(
            """
clients:
  my_client:
    class: module:Original
    config:
      value: original
""",
            encoding="utf-8",
        )

        (tmp_path / "02_override.yaml").write_text(
            """
clients:
  my_client:
    class: module:Override
    config:
      value: overridden
""",
            encoding="utf-8",
        )

        cfg = load_clients_config([str(tmp_path / "*.yaml")])

        assert len(cfg.clients) == 1
        client = cfg.clients[0]
        assert client.class_path == "module:Override"
        assert client.config["value"] == "overridden"

    def test_missing_class_raises(self, tmp_path: Path):
        config_file = tmp_path / "clients.yaml"
        config_file.write_text(
            """
clients:
  invalid_client:
    config:
      key: value
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="missing required 'class'"):
            load_clients_config([str(config_file)])

    def test_env_var_substitution_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)

        config_file = tmp_path / "clients.yaml"
        config_file.write_text(
            """
clients:
  bad_client:
    class: module:Class
    config:
      url: "${MISSING_VAR}"
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="config error"):
            load_clients_config([str(config_file)])

    def test_empty_config_returns_empty_list(self, tmp_path: Path):
        config_file = tmp_path / "clients.yaml"
        config_file.write_text("clients: {}\n", encoding="utf-8")

        cfg = load_clients_config([str(config_file)])
        assert cfg.clients == []

    def test_no_files_returns_empty_list(self, tmp_path: Path):
        cfg = load_clients_config([str(tmp_path / "nonexistent.yaml")])
        assert cfg.clients == []
