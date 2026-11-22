"""#2579: multichain config writes must be atomic and empty files must not
brick every loader.

``save_multichain_config`` truncated the YAML before serialising, so a
failed dump left a partial/empty file; ``load_multichain_config`` then fed
``None`` to ``MultiChainConfig(**...)`` and every ``node``/``chain``/
``analytics`` command failed with a pydantic TypeError.
"""

from __future__ import annotations

import yaml

from aitbc_cli.core.config import (
    MultiChainConfig,
    NodeConfig,
    load_multichain_config,
    save_multichain_config,
)


def test_empty_config_file_loads_defaults(tmp_path):
    path = tmp_path / "multichain_config.yaml"
    path.write_text("")
    cfg = load_multichain_config(str(path))
    assert isinstance(cfg, MultiChainConfig)
    assert cfg.logging_level == "INFO"
    assert cfg.chains.max_concurrent_chains == 100


def test_failed_dump_leaves_previous_file_intact(tmp_path, monkeypatch):
    path = tmp_path / "multichain_config.yaml"
    cfg = MultiChainConfig(nodes={"n1": NodeConfig(id="n1", endpoint="http://x:1")})
    save_multichain_config(cfg, str(path))
    before = path.read_bytes()

    def _boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(yaml, "dump", _boom)
    try:
        save_multichain_config(cfg, str(path))
    except ValueError:
        pass
    else:  # pragma: no cover - must raise
        raise AssertionError("save should have raised")
    assert path.read_bytes() == before
    # and the surviving file still loads
    loaded = load_multichain_config(str(path))
    assert "n1" in loaded.nodes


def test_save_round_trips_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "multichain_config.yaml"
    cfg = MultiChainConfig(nodes={"n1": NodeConfig(id="n1", endpoint="http://x:1")})
    save_multichain_config(cfg, str(path))
    loaded = load_multichain_config(str(path))
    assert loaded.nodes["n1"].endpoint == "http://x:1"
    assert list(tmp_path.glob("*.tmp")) == []
