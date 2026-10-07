"""Fixture tests for --emit-blobs / --validator-blob (A35 custody flow).

Emit runs on the key-owning host and writes a public blob
``{chain_id,address,public_key,signature}``; consume verifies the
self-signature recovers to the declared address and needs no validator key.
No key material is ever printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import register_bridge_validators as rbv  # noqa: E402

CHAIN = "ait-hub.aitbc.bubuit.net"
VAL_KEY = "01" * 32
ADMIN_KEY = "02" * 32


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "BRIDGE_VALIDATOR_PRIVATE_KEY_1",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1",
        "BRIDGE_VALIDATOR_ADDRESS_1",
        "BRIDGE_ADMIN_PRIVATE_KEY",
        "BRIDGE_ADMIN_PRIVATE_KEY_FILE",
        "BRIDGE_ADMIN_PRIVATE_KEY_SOURCE",
        "BRIDGE_ADMIN_ADDRESS",
        "PROPOSER_KEY",
        "GENESIS_PRIVATE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def _argv(*args: str) -> list[str]:
    return ["register_bridge_validators.py", "--chain-id", CHAIN, *args]


def test_emit_blobs_writes_signed_blob(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_1", VAL_KEY)
    monkeypatch.setattr(sys, "argv", _argv("--emit-blobs", str(tmp_path)))
    assert rbv._main() == 0
    blob = json.loads((tmp_path / "validator-1.json").read_text())
    assert set(blob) == {"chain_id", "address", "public_key", "signature"}
    assert blob["chain_id"] == CHAIN
    derived, _ = rbv._derive_address_and_public_key(VAL_KEY)
    assert rbv._normalize_address(blob["address"]) == rbv._normalize_address(derived)
    # the blob signature must recover to the declared address
    rec = rbv._recover_address(
        {"chain_id": CHAIN, "address": blob["address"], "public_key": blob["public_key"], "action": "register"},
        blob["signature"],
    )
    assert rbv._normalize_address(rec) == rbv._normalize_address(derived)
    out = capsys.readouterr().out
    assert VAL_KEY not in out


def test_emit_needs_no_admin_key(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_1", VAL_KEY)
    monkeypatch.setattr(sys, "argv", _argv("--emit-blobs", str(tmp_path)))
    # would _die if it tried to read an admin key — none is set
    assert rbv._main() == 0


def test_validator_blob_dry_run(tmp_path, monkeypatch, capsys):
    f = tmp_path / "v.json"
    addr, pub = rbv._derive_address_and_public_key(VAL_KEY)
    sig = rbv._sign_dict(VAL_KEY, rbv._self_sign_data(CHAIN, addr, pub))
    f.write_text(json.dumps({"chain_id": CHAIN, "address": addr, "public_key": pub, "signature": sig}))
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY", ADMIN_KEY)
    monkeypatch.setattr(sys, "argv", _argv("--validator-blob", str(f), "--dry-run"))
    assert rbv._main() == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and addr in out


def test_validator_blob_wrong_signer_dies(tmp_path, monkeypatch):
    addr, pub = rbv._derive_address_and_public_key(VAL_KEY)
    sig = rbv._sign_dict(ADMIN_KEY, rbv._self_sign_data(CHAIN, addr, pub))  # signed by wrong key
    f = tmp_path / "v.json"
    f.write_text(json.dumps({"chain_id": CHAIN, "address": addr, "public_key": pub, "signature": sig}))
    monkeypatch.setattr(sys, "argv", _argv("--validator-blob", str(f), "--dry-run"))
    with pytest.raises(SystemExit):
        rbv._main()


def test_validator_blob_wrong_chain_dies(tmp_path, monkeypatch):
    addr, pub = rbv._derive_address_and_public_key(VAL_KEY)
    sig = rbv._sign_dict(VAL_KEY, rbv._self_sign_data("other-chain", addr, pub))
    f = tmp_path / "v.json"
    f.write_text(json.dumps({"chain_id": "other-chain", "address": addr, "public_key": pub, "signature": sig}))
    monkeypatch.setattr(sys, "argv", _argv("--validator-blob", str(f), "--dry-run"))
    with pytest.raises(SystemExit):
        rbv._main()


def test_validator_blob_missing_field_dies(tmp_path, monkeypatch):
    f = tmp_path / "v.json"
    f.write_text(json.dumps({"chain_id": CHAIN, "address": "0xabc"}))
    monkeypatch.setattr(sys, "argv", _argv("--validator-blob", str(f), "--dry-run"))
    with pytest.raises(SystemExit):
        rbv._main()
