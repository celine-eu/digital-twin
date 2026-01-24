# tests/core/values/test_config.py
from __future__ import annotations

import pytest
from pathlib import Path

from celine.dt.core.values.config import load_values_config, ValueFetcherSpec
from celine.dt.core.modules.config import ModulesConfig, ModuleSpec


class TestLoadValuesConfig:
    def test_load_simple_fetcher(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  weather:
    client: dataset_api
    query: SELECT * FROM weather
    limit: 50
""",
            encoding="utf-8",
        )

        cfg = load_values_config([str(config_file)])

        assert len(cfg.fetchers) == 1
        fetcher = cfg.fetchers[0]
        assert fetcher.id == "weather"
        assert fetcher.client == "dataset_api"
        assert fetcher.query == "SELECT * FROM weather"
        assert fetcher.limit == 50

    def test_load_fetcher_with_payload_schema(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  filtered:
    client: dataset_api
    query: SELECT * FROM data WHERE id = :id
    payload:
      type: object
      required: [id]
      properties:
        id:
          type: integer
""",
            encoding="utf-8",
        )

        cfg = load_values_config([str(config_file)])

        fetcher = cfg.fetchers[0]
        assert fetcher.payload_schema is not None
        assert fetcher.payload_schema["type"] == "object"
        assert "id" in fetcher.payload_schema["required"]

    def test_load_fetcher_with_output_mapper(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  mapped:
    client: dataset_api
    query: SELECT * FROM data
    output_mapper: my.module:MyMapper
""",
            encoding="utf-8",
        )

        cfg = load_values_config([str(config_file)])

        fetcher = cfg.fetchers[0]
        assert fetcher.output_mapper == "my.module:MyMapper"

    def test_default_limit_and_offset(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  defaults:
    client: dataset_api
""",
            encoding="utf-8",
        )

        cfg = load_values_config([str(config_file)])

        fetcher = cfg.fetchers[0]
        assert fetcher.limit == 100
        assert fetcher.offset == 0

    def test_later_file_overrides(self, tmp_path: Path):
        (tmp_path / "01_base.yaml").write_text(
            """
values:
  my_fetcher:
    client: old_client
    limit: 10
""",
            encoding="utf-8",
        )

        (tmp_path / "02_override.yaml").write_text(
            """
values:
  my_fetcher:
    client: new_client
    limit: 100
""",
            encoding="utf-8",
        )

        cfg = load_values_config([str(tmp_path / "*.yaml")])

        assert len(cfg.fetchers) == 1
        fetcher = cfg.fetchers[0]
        assert fetcher.client == "new_client"
        assert fetcher.limit == 100

    def test_module_namespaced_fetchers(self, tmp_path: Path):
        modules_cfg = ModulesConfig(
            modules=[
                ModuleSpec(
                    name="my_module",
                    version="1.0.0",
                    import_path="my.module:module",
                    values={
                        "my_fetcher": {
                            "client": "dataset_api",
                            "query": "SELECT 1",
                        }
                    },
                )
            ]
        )

        cfg = load_values_config(
            [str(tmp_path / "nonexistent.yaml")],
            modules_cfg=modules_cfg,
        )

        assert len(cfg.fetchers) == 1
        fetcher = cfg.fetchers[0]
        assert fetcher.id == "my_module.my_fetcher"

    def test_root_and_module_fetchers_combined(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  root_fetcher:
    client: dataset_api
""",
            encoding="utf-8",
        )

        modules_cfg = ModulesConfig(
            modules=[
                ModuleSpec(
                    name="mod",
                    version="1.0.0",
                    import_path="mod:module",
                    values={
                        "mod_fetcher": {
                            "client": "dataset_api",
                        }
                    },
                )
            ]
        )

        cfg = load_values_config([str(config_file)], modules_cfg=modules_cfg)

        assert len(cfg.fetchers) == 2
        ids = {f.id for f in cfg.fetchers}
        assert ids == {"root_fetcher", "mod.mod_fetcher"}

    def test_disabled_module_values_ignored(self, tmp_path: Path):
        modules_cfg = ModulesConfig(
            modules=[
                ModuleSpec(
                    name="disabled_mod",
                    version="1.0.0",
                    import_path="mod:module",
                    enabled=False,
                    values={
                        "should_not_load": {
                            "client": "dataset_api",
                        }
                    },
                )
            ]
        )

        cfg = load_values_config(
            [str(tmp_path / "nonexistent.yaml")],
            modules_cfg=modules_cfg,
        )

        assert len(cfg.fetchers) == 0

    def test_missing_client_raises(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text(
            """
values:
  invalid:
    query: SELECT 1
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="missing required 'client'"):
            load_values_config([str(config_file)])

    def test_empty_config(self, tmp_path: Path):
        config_file = tmp_path / "values.yaml"
        config_file.write_text("values: {}\n", encoding="utf-8")

        cfg = load_values_config([str(config_file)])
        assert cfg.fetchers == []
