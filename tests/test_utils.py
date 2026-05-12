"""
Tests for AITBC utility modules
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from aitbc.utils.paths import (
    get_data_path,
    get_config_path,
    get_log_path,
    get_repo_path,
    ensure_dir,
    ensure_file_dir,
    resolve_path,
    get_keystore_path,
    get_blockchain_data_path,
    get_marketplace_data_path,
)
from aitbc.utils.env import (
    get_env_var,
    get_required_env_var,
    get_bool_env_var,
    get_int_env_var,
    get_float_env_var,
    get_list_env_var,
)
from aitbc.utils.json_utils import (
    load_json,
    save_json,
    merge_json,
    json_to_string,
    string_to_json,
    get_nested_value,
    set_nested_value,
    flatten_json,
)
from aitbc.exceptions import ConfigurationError


class TestPaths:
    """Tests for path utility functions"""

    def test_get_data_path_no_subpath(self):
        """Test get_data_path without subpath"""
        result = get_data_path()
        assert isinstance(result, Path)

    def test_get_data_path_with_subpath(self):
        """Test get_data_path with subpath"""
        result = get_data_path("test")
        assert isinstance(result, Path)
        assert str(result).endswith("test")

    def test_get_config_path(self):
        """Test get_config_path"""
        result = get_config_path("config.yaml")
        assert isinstance(result, Path)
        assert str(result).endswith("config.yaml")

    def test_get_log_path(self):
        """Test get_log_path"""
        result = get_log_path("app.log")
        assert isinstance(result, Path)
        assert str(result).endswith("app.log")

    def test_get_repo_path_no_subpath(self):
        """Test get_repo_path without subpath"""
        result = get_repo_path()
        assert isinstance(result, Path)

    def test_get_repo_path_with_subpath(self):
        """Test get_repo_path with subpath"""
        result = get_repo_path("src")
        assert isinstance(result, Path)
        assert str(result).endswith("src")

    def test_ensure_dir(self):
        """Test ensure_dir creates directory"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test" / "nested"
            result = ensure_dir(test_path)
            assert result.exists()
            assert result.is_dir()

    def test_ensure_file_dir(self):
        """Test ensure_file_dir creates parent directory"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test" / "nested" / "file.txt"
            result = ensure_file_dir(test_path)
            assert result.exists()
            assert result.is_dir()

    def test_resolve_path_absolute(self):
        """Test resolve_path with absolute path"""
        result = resolve_path("/tmp/test")
        assert result.is_absolute()

    def test_resolve_path_relative(self):
        """Test resolve_path with relative path"""
        result = resolve_path("test")
        assert result.is_absolute()  # Relative paths are resolved to absolute

    def test_get_keystore_path_no_wallet(self):
        """Test get_keystore_path without wallet name"""
        result = get_keystore_path()
        assert isinstance(result, Path)
        assert str(result).endswith("keystore")

    def test_get_keystore_path_with_wallet(self):
        """Test get_keystore_path with wallet name"""
        result = get_keystore_path("mywallet")
        assert isinstance(result, Path)
        assert str(result).endswith("mywallet.json")

    def test_get_blockchain_data_path_default(self):
        """Test get_blockchain_data_path with default chain"""
        result = get_blockchain_data_path()
        assert isinstance(result, Path)
        assert str(result).endswith("ait-mainnet")

    def test_get_blockchain_data_path_custom(self):
        """Test get_blockchain_data_path with custom chain"""
        result = get_blockchain_data_path("custom-chain")
        assert isinstance(result, Path)
        assert str(result).endswith("custom-chain")

    def test_get_marketplace_data_path_no_subpath(self):
        """Test get_marketplace_data_path without subpath"""
        result = get_marketplace_data_path()
        assert isinstance(result, Path)
        assert str(result).endswith("marketplace")

    def test_get_marketplace_data_path_with_subpath(self):
        """Test get_marketplace_data_path with subpath"""
        result = get_marketplace_data_path("orders")
        assert isinstance(result, Path)
        assert str(result).endswith("orders")


class TestEnv:
    """Tests for environment variable utilities"""

    def test_get_env_var_with_value(self):
        """Test get_env_var with set value"""
        os.environ["TEST_VAR"] = "test_value"
        result = get_env_var("TEST_VAR")
        assert result == "test_value"
        del os.environ["TEST_VAR"]

    def test_get_env_var_with_default(self):
        """Test get_env_var with default value"""
        result = get_env_var("NONEXISTENT_VAR", "default")
        assert result == "default"

    def test_get_required_env_var_with_value(self):
        """Test get_required_env_var with set value"""
        os.environ["TEST_VAR"] = "test_value"
        result = get_required_env_var("TEST_VAR")
        assert result == "test_value"
        del os.environ["TEST_VAR"]

    def test_get_required_env_var_without_value(self):
        """Test get_required_env_var without value raises error"""
        with pytest.raises(ConfigurationError):
            get_required_env_var("NONEXISTENT_VAR")

    def test_get_bool_env_var_true(self):
        """Test get_bool_env_var with true values"""
        for value in ["true", "TRUE", "1", "yes", "YES", "on", "ON"]:
            os.environ["TEST_VAR"] = value
            assert get_bool_env_var("TEST_VAR") is True
        del os.environ["TEST_VAR"]

    def test_get_bool_env_var_false(self):
        """Test get_bool_env_var with false values"""
        for value in ["false", "FALSE", "0", "no", "NO", "off", "OFF"]:
            os.environ["TEST_VAR"] = value
            assert get_bool_env_var("TEST_VAR") is False
        del os.environ["TEST_VAR"]

    def test_get_bool_env_var_default(self):
        """Test get_bool_env_var with default"""
        assert get_bool_env_var("NONEXISTENT_VAR", True) is True
        assert get_bool_env_var("NONEXISTENT_VAR", False) is False

    def test_get_int_env_var_valid(self):
        """Test get_int_env_var with valid integer"""
        os.environ["TEST_VAR"] = "42"
        assert get_int_env_var("TEST_VAR") == 42
        del os.environ["TEST_VAR"]

    def test_get_int_env_var_invalid(self):
        """Test get_int_env_var with invalid value returns default"""
        os.environ["TEST_VAR"] = "not_a_number"
        assert get_int_env_var("TEST_VAR", 10) == 10
        del os.environ["TEST_VAR"]

    def test_get_int_env_var_default(self):
        """Test get_int_env_var with default"""
        assert get_int_env_var("NONEXISTENT_VAR", 100) == 100

    def test_get_float_env_var_valid(self):
        """Test get_float_env_var with valid float"""
        os.environ["TEST_VAR"] = "3.14"
        assert get_float_env_var("TEST_VAR") == 3.14
        del os.environ["TEST_VAR"]

    def test_get_float_env_var_invalid(self):
        """Test get_float_env_var with invalid value returns default"""
        os.environ["TEST_VAR"] = "not_a_number"
        assert get_float_env_var("TEST_VAR", 2.5) == 2.5
        del os.environ["TEST_VAR"]

    def test_get_float_env_var_default(self):
        """Test get_float_env_var with default"""
        assert get_float_env_var("NONEXISTENT_VAR", 1.5) == 1.5

    def test_get_list_env_var_valid(self):
        """Test get_list_env_var with valid list"""
        os.environ["TEST_VAR"] = "item1,item2,item3"
        result = get_list_env_var("TEST_VAR")
        assert result == ["item1", "item2", "item3"]
        del os.environ["TEST_VAR"]

    def test_get_list_env_var_custom_separator(self):
        """Test get_list_env_var with custom separator"""
        os.environ["TEST_VAR"] = "item1;item2;item3"
        result = get_list_env_var("TEST_VAR", separator=";")
        assert result == ["item1", "item2", "item3"]
        del os.environ["TEST_VAR"]

    def test_get_list_env_var_empty(self):
        """Test get_list_env_var with empty value returns default"""
        os.environ["TEST_VAR"] = ""
        result = get_list_env_var("TEST_VAR", default=["default"])
        assert result == ["default"]
        del os.environ["TEST_VAR"]

    def test_get_list_env_var_default(self):
        """Test get_list_env_var with default"""
        result = get_list_env_var("NONEXISTENT_VAR", default=["a", "b"])
        assert result == ["a", "b"]


class TestJsonUtils:
    """Tests for JSON utility functions"""

    def test_json_to_string(self):
        """Test json_to_string"""
        data = {"key": "value"}
        result = json_to_string(data)
        assert '"key"' in result
        assert '"value"' in result

    def test_string_to_json_valid(self):
        """Test string_to_json with valid JSON"""
        json_str = '{"key": "value"}'
        result = string_to_json(json_str)
        assert result == {"key": "value"}

    def test_string_to_json_invalid(self):
        """Test string_to_json with invalid JSON raises error"""
        with pytest.raises(ConfigurationError):
            string_to_json("not valid json")

    def test_get_nested_value_found(self):
        """Test get_nested_value when key exists"""
        data = {"a": {"b": {"c": "value"}}}
        result = get_nested_value(data, "a", "b", "c")
        assert result == "value"

    def test_get_nested_value_not_found(self):
        """Test get_nested_value when key doesn't exist returns default"""
        data = {"a": {"b": {"c": "value"}}}
        result = get_nested_value(data, "a", "b", "d", default="default")
        assert result == "default"

    def test_get_nested_value_default_none(self):
        """Test get_nested_value with default None"""
        data = {"a": {"b": {"c": "value"}}}
        result = get_nested_value(data, "x", "y", "z")
        assert result is None

    def test_set_nested_value(self):
        """Test set_nested_value"""
        data = {}
        set_nested_value(data, "a", "b", "c", value="test")
        assert data["a"]["b"]["c"] == "test"

    def test_flatten_json(self):
        """Test flatten_json"""
        data = {"a": {"b": {"c": "value"}}, "d": "simple"}
        result = flatten_json(data)
        assert "a.b.c" in result
        assert result["a.b.c"] == "value"
        assert result["d"] == "simple"

    def test_flatten_json_custom_separator(self):
        """Test flatten_json with custom separator"""
        data = {"a": {"b": "value"}}
        result = flatten_json(data, separator="_")
        assert "a_b" in result
        assert result["a_b"] == "value"

    def test_load_json(self, tmp_path):
        """Test load_json"""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"key": "value"}')
        result = load_json(test_file)
        assert result == {"key": "value"}

    def test_load_json_not_found(self, tmp_path):
        """Test load_json with non-existent file raises error"""
        with pytest.raises(ConfigurationError):
            load_json(tmp_path / "nonexistent.json")

    def test_load_json_invalid(self, tmp_path):
        """Test load_json with invalid JSON raises error"""
        test_file = tmp_path / "invalid.json"
        test_file.write_text("not valid json")
        with pytest.raises(ConfigurationError):
            load_json(test_file)

    def test_save_json(self, tmp_path):
        """Test save_json"""
        test_file = tmp_path / "test.json"
        data = {"key": "value"}
        save_json(data, test_file)
        assert test_file.exists()
        result = load_json(test_file)
        assert result == data

    def test_merge_json(self, tmp_path):
        """Test merge_json"""
        file1 = tmp_path / "file1.json"
        file2 = tmp_path / "file2.json"
        file1.write_text('{"a": 1, "b": 2}')
        file2.write_text('{"b": 3, "c": 4}')
        result = merge_json(file1, file2)
        assert result == {"a": 1, "b": 3, "c": 4}
