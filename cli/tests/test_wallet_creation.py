"""Verify file wallet creation generates real, encrypted key material."""

import json
from pathlib import Path

from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter


def test_file_wallet_uses_real_private_key(monkeypatch, tmp_path):
    """CLI-01: file wallet private key must not be predictable or plaintext."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    adapter = DualModeWalletAdapter()
    result = adapter.create_wallet("test_wallet", "test-password-123", wallet_type="simple")

    assert result["mode"] == "file"
    assert result["wallet_name"] == "test_wallet"
    assert result["wallet_type"] == "simple"
    # Valid Ethereum-style address derived from real key material.
    assert result["address"].startswith("0x")
    assert len(result["address"]) == 42

    wallet_file = tmp_path / ".aitbc" / "wallets" / "test_wallet.json"
    wallet_data = json.loads(wallet_file.read_text())

    # The private key must be encrypted, never a predictable "simple_key_..." string.
    assert wallet_data["encrypted"] is True
    assert isinstance(wallet_data["private_key"], dict)
    assert "encrypted_data" in wallet_data["private_key"]
    assert "salt" in wallet_data["private_key"]
    assert "simple_key_" not in json.dumps(wallet_data)
