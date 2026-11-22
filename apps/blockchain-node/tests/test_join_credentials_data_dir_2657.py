"""AUDIT-BN-JOIN-CREDENTIALS-HARDCODED-DATA-DIR-1 (#2657): the island join
credentials must resolve genesis.json and validator_keys.json through
``aitbc.constants`` (DATA_DIR / KEYSTORE_DIR), not the literal
``/var/lib/aitbc`` — a node with a non-default AITBC_DATA_DIR previously got
credentials with no genesis_block_hash / genesis_address and no warning.
"""

from __future__ import annotations

import json

from aitbc_chain.rpc import islands as rpc_islands


def _seed_data_dir(root) -> None:
    genesis_dir = root / "data" / "chain-x"
    genesis_dir.mkdir(parents=True)
    (genesis_dir / "genesis.json").write_text(json.dumps({"blocks": [{"hash": "0xfeed"}]}))
    keystore = root / "keystore"
    keystore.mkdir()
    (keystore / "validator_keys.json").write_text(json.dumps({"0xvalidator-key-1": {"pubkey": "0xpub"}}))


def test_join_credentials_use_configured_data_dir(tmp_path, monkeypatch):
    _seed_data_dir(tmp_path)
    monkeypatch.setattr(rpc_islands, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rpc_islands, "KEYSTORE_DIR", tmp_path / "keystore")

    creds = rpc_islands._build_join_credentials("island-1", "Island One", "chain-x")

    assert creds["genesis_block_hash"] == "0xfeed"
    assert creds["genesis_address"] == "0xvalidator-key-1"


def test_join_credentials_warn_and_omit_when_no_genesis(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "keystore").mkdir()
    monkeypatch.setattr(rpc_islands, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rpc_islands, "KEYSTORE_DIR", tmp_path / "keystore")

    creds = rpc_islands._build_join_credentials("island-1", "Island One", "chain-x")

    assert "genesis_block_hash" not in creds
    assert "genesis_address" not in creds
