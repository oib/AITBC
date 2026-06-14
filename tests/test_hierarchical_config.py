"""Tests for aitbc.hierarchical_config"""

import tempfile
from pathlib import Path

from aitbc.hierarchical_config import HierarchicalConfig


class TestHierarchicalConfig:
    def test_init_defaults(self):
        hc = HierarchicalConfig()
        assert hc.config_file is not None

    def test_load_empty_defaults(self):
        hc = HierarchicalConfig(config_file=None, env_file=None)
        config = hc.load_config()
        assert "debug" in config

    def test_load_from_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("debug: true\n")
            f.flush()
            path = Path(f.name)
        try:
            hc = HierarchicalConfig(config_file=path, env_file=None)
            config = hc.load_config()
            assert config["debug"] is True
        finally:
            path.unlink(missing_ok=True)

    def test_load_from_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"debug": true}')
            f.flush()
            path = Path(f.name)
        try:
            hc = HierarchicalConfig(config_file=path, env_file=None)
            config = hc.load_config()
            assert config["debug"] is True
        finally:
            path.unlink(missing_ok=True)

    def test_cache(self):
        hc = HierarchicalConfig(config_file=None, env_file=None)
        config1 = hc.load_config()
        config2 = hc.load_config()
        assert config1 is config2
