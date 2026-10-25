"""CLI-NODEREG-1: a stale multichain registry must not blind read commands.

node0's registry carried aitbc-primary/aitbc-secondary on a dead port, so
analytics and `blockchain status` failed while the local RPC was healthy.
`load_multichain_config` now always offers the configured
blockchain_rpc_url as a `local-rpc` fallback node.
"""

from unittest.mock import patch

from aitbc_cli.core.config import MultiChainConfig, NodeConfig, _with_local_rpc_fallback


def _cfg(nodes):
    return MultiChainConfig(nodes=nodes)


def test_stale_registry_gains_local_rpc():
    with patch("aitbc_cli.config.get_config") as gc:
        gc.return_value.blockchain_rpc_url = "http://127.0.0.1:8202"
        config = _with_local_rpc_fallback(
            _cfg({"aitbc-primary": NodeConfig(id="aitbc-primary", endpoint="http://127.0.0.1:8082")})
        )
    assert "local-rpc" in config.nodes
    assert config.nodes["local-rpc"].endpoint == "http://127.0.0.1:8202"
    assert "aitbc-primary" in config.nodes  # kept, not removed


def test_existing_endpoint_not_duplicated():
    with patch("aitbc_cli.config.get_config") as gc:
        gc.return_value.blockchain_rpc_url = "http://127.0.0.1:8202"
        config = _with_local_rpc_fallback(_cfg({"mine": NodeConfig(id="mine", endpoint="http://127.0.0.1:8202")}))
    assert "local-rpc" not in config.nodes


def test_empty_registry_gets_local_rpc():
    with patch("aitbc_cli.config.get_config") as gc:
        gc.return_value.blockchain_rpc_url = "http://10.0.0.1:8202"
        config = _with_local_rpc_fallback(_cfg({}))
    assert config.nodes["local-rpc"].endpoint == "http://10.0.0.1:8202"


def test_no_configured_url_defaults_to_loopback():
    with patch("aitbc_cli.config.get_config") as gc:
        gc.return_value.blockchain_rpc_url = ""
        config = _with_local_rpc_fallback(_cfg({}))
    assert config.nodes["local-rpc"].endpoint == "http://127.0.0.1:8202"
