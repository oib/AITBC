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


def test_list_wallets_reports_file_type_key(monkeypatch, tmp_path):
    """#2391: `wallet list` must show the stored type for both on-disk
    shapes — CLI-created files use ``type``, adapter-created use
    ``wallet_type``; neither may collapse to the 'hd' default."""
    import json as _json
    from unittest.mock import patch

    from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter

    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    (tmp_path / "cli-simple.json").write_text(
        _json.dumps({"wallet_id": "cli-simple", "type": "simple", "address": "0x" + "11" * 20})
    )
    (tmp_path / "adapter-hd.json").write_text(
        _json.dumps({"wallet_id": "adapter-hd", "wallet_type": "hd", "address": "0x" + "22" * 20})
    )
    (tmp_path / "legacy.json").write_text(_json.dumps({"wallet_id": "legacy", "address": "0x" + "33" * 20}))

    adapter = DualModeWalletAdapter(use_daemon=False)
    with patch("aitbc_cli.utils.dual_mode_wallet_adapter.wallet_search_dirs", return_value=[tmp_path]):
        wallets = {w["wallet_name"]: w["wallet_type"] for w in adapter.list_wallets()}

    assert wallets["cli-simple"] == "simple"
    assert wallets["adapter-hd"] == "hd"
    assert wallets["legacy"] == "hd"  # absent key still defaults to hd
