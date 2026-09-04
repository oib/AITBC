"""Regression tests for the ETH bridge address generator.

The generator must never emit private key material to stdout, stderr, or logs.
"""

import importlib.util
import logging
from pathlib import Path


def _load_generate_module():
    """Load the bridge generator directly from its source path."""
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "apps/wallet/src/wallet_app/bridge/generate_eth_address.py"
    spec = importlib.util.spec_from_file_location("wallet_app.bridge.generate_eth_address", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_eth_address_does_not_leak_private_key(capsys, caplog):
    """generate_eth_address returns the key but never writes it anywhere."""
    module = _load_generate_module()

    with caplog.at_level(logging.INFO, logger="wallet_app.bridge.generate_eth_address"):
        address, private_key = module.generate_eth_address()

    captured = capsys.readouterr()

    assert address.startswith("0x")
    assert private_key and private_key != address
    assert private_key not in captured.out
    assert private_key not in captured.err
    assert private_key not in caplog.text
    assert address in caplog.text
