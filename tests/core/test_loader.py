# tests/core/test_loader.py
from __future__ import annotations

import os
import pytest
from pathlib import Path

from celine.dt.core.loader import (
    import_attr,
    substitute_env_vars,
    load_yaml_files,
)


class TestImportAttr:
    def test_import_valid_path(self):
        # Import a known stdlib function
        result = import_attr("os.path:join")
        assert result is os.path.join

    def test_import_invalid_format_no_colon(self):
        with pytest.raises(ValueError, match="expected 'module:attr'"):
            import_attr("os.path.join")

    def test_import_nonexistent_module(self):
        with pytest.raises(ImportError):
            import_attr("nonexistent.module:attr")

    def test_import_nonexistent_attr(self):
        with pytest.raises(AttributeError):
            import_attr("os.path:nonexistent_function")


class TestSubstituteEnvVars:
    def test_substitute_simple_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        result = substitute_env_vars("${TEST_VAR}")
        assert result == "hello"

    def test_substitute_var_with_default_uses_env(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "from_env")
        result = substitute_env_vars("${TEST_VAR:-default_value}")
        assert result == "from_env"

    def test_substitute_var_with_default_uses_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        result = substitute_env_vars("${MISSING_VAR:-default_value}")
        assert result == "default_value"

    def test_substitute_missing_var_no_default_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="not set"):
            substitute_env_vars("${MISSING_VAR}")

    def test_substitute_in_dict(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        
        result = substitute_env_vars({
            "host": "${DB_HOST}",
            "port": "${DB_PORT}",
            "static": "value",
        })
        
        assert result == {
            "host": "localhost",
            "port": "5432",
            "static": "value",
        }

    def test_substitute_in_list(self, monkeypatch):
        monkeypatch.setenv("ITEM1", "a")
        monkeypatch.setenv("ITEM2", "b")
        
        result = substitute_env_vars(["${ITEM1}", "${ITEM2}", "static"])
        assert result == ["a", "b", "static"]

    def test_substitute_nested(self, monkeypatch):
        monkeypatch.setenv("NESTED_VAR", "nested_value")
        
        result = substitute_env_vars({
            "outer": {
                "inner": "${NESTED_VAR}"
            }
        })
        
        assert result == {"outer": {"inner": "nested_value"}}

    def test_substitute_non_string_passthrough(self):
        assert substitute_env_vars(42) == 42
        assert substitute_env_vars(3.14) == 3.14
        assert substitute_env_vars(True) is True
        assert substitute_env_vars(None) is None

    def test_substitute_empty_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        result = substitute_env_vars("${MISSING_VAR:-}")
        assert result == ""


class TestLoadYamlFiles:
    def test_load_single_file(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n", encoding="utf-8")

        result = load_yaml_files([str(config_file)])
        
        assert len(result) == 1
        assert result[0] == {"key": "value"}

    def test_load_multiple_files_sorted(self, tmp_path: Path):
        (tmp_path / "02_second.yaml").write_text("order: 2\n", encoding="utf-8")
        (tmp_path / "01_first.yaml").write_text("order: 1\n", encoding="utf-8")

        result = load_yaml_files([str(tmp_path / "*.yaml")])
        
        assert len(result) == 2
        assert result[0] == {"order": 1}
        assert result[1] == {"order": 2}

    def test_load_no_matching_files_returns_empty(self, tmp_path: Path):
        result = load_yaml_files([str(tmp_path / "nonexistent/*.yaml")])
        assert result == []

    def test_load_empty_file(self, tmp_path: Path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("", encoding="utf-8")

        result = load_yaml_files([str(config_file)])
        
        assert len(result) == 1
        assert result[0] == {}
