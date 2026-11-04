"""Pins for #1131: CLI governance writes carry the route signature.

The governance service (#1091) refuses unsigned write bodies. The CLI must
sign: votes sign the whole body from the voter's key, execute/close sign
{"action": ..., "proposal_id": ...} from caller_address, and proposals sign
the unsigned body. Tests capture the posted JSON and verify the signature
the way the service does.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from eth_keys import keys
from eth_utils import keccak

pytest.importorskip("aitbc.crypto.signature_recovery", reason="signature checks need the crypto package")

from aitbc.crypto.signature_recovery import verify_signature  # noqa: E402

from aitbc_cli.commands.governance import _sign_body, governance  # noqa: E402

PK = keys.PrivateKey(b"\x0d" * 32)
ADDR = PK.public_key.to_checksum_address()


def _verify(addr: str, sig: str, payload: dict) -> bool:
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    try:
        return verify_signature(keccak(msg), sig, addr)
    except Exception:
        return False


def _fake_client(captured: dict):
    client = MagicMock()

    def _post(path, json=None, **kw):
        captured["path"], captured["json"] = path, json
        return {"ok": True}

    client.post = _post
    return client


def test_sign_body_roundtrips_service_verification() -> None:
    payload = {"b": 2, "a": "x"}
    sig = _sign_body(PK.to_hex(), payload)
    assert _verify(ADDR, sig, payload)


def test_close_posts_signed_body() -> None:
    captured: dict = {}
    with (
        patch("aitbc_cli.commands.governance._get_client", return_value=_fake_client(captured)),
        patch("aitbc_cli.commands.governance._wallet_signer", return_value=(ADDR, PK.to_hex())),
        patch("aitbc_cli.commands.governance.output"),
    ):
        result = CliRunner().invoke(governance, ["close", "--proposal-id", "prop_1"])
    assert result.exit_code == 0, result.output
    body = captured["json"]
    assert body["caller_address"] == ADDR
    assert _verify(ADDR, body["signature"], {"action": "close", "proposal_id": "prop_1"})


def test_execute_posts_signed_body() -> None:
    captured: dict = {}
    with (
        patch("aitbc_cli.commands.governance._get_client", return_value=_fake_client(captured)),
        patch("aitbc_cli.commands.governance._wallet_signer", return_value=(ADDR, PK.to_hex())),
        patch("aitbc_cli.commands.governance._governance_rpc", return_value=(MagicMock(), "c")),
        patch("aitbc_cli.commands.governance._sign_governance_tx", return_value={"signed": True}),
        patch("aitbc_cli.commands.governance.output"),
    ):
        result = CliRunner().invoke(governance, ["execute", "--proposal-id", "prop_2"])
    assert result.exit_code == 0, result.output
    body = captured["json"]
    assert body["caller_address"] == ADDR
    assert _verify(ADDR, body["signature"], {"action": "execute", "proposal_id": "prop_2"})


def test_vote_signs_whole_body_and_binds_voter() -> None:
    captured: dict = {}
    with (
        patch("aitbc_cli.commands.governance._get_client", return_value=_fake_client(captured)),
        patch("aitbc_cli.commands.governance._wallet_signer", return_value=(ADDR, PK.to_hex())),
        patch("aitbc_cli.commands.governance._governance_rpc", return_value=(MagicMock(), "c")),
        patch("aitbc_cli.commands.governance._get_governance_account", return_value={"balance": 5}),
        patch("aitbc_cli.commands.governance._sign_governance_tx", return_value={"signed": True}),
        patch("aitbc_cli.commands.governance.output"),
    ):
        result = CliRunner().invoke(governance, ["vote", "--proposal-id", "prop_3", "--vote", "for", "--voter-id", ADDR])
    assert result.exit_code == 0, result.output
    body = captured["json"]
    assert body["voter_id"] == ADDR
    unsigned = {k: v for k, v in body.items() if k != "signature"}
    assert _verify(ADDR, body["signature"], unsigned)


def test_close_without_wallet_posts_no_signature() -> None:
    captured: dict = {}
    with (
        patch("aitbc_cli.commands.governance._get_client", return_value=_fake_client(captured)),
        patch("aitbc_cli.commands.governance._wallet_signer", return_value=None),
        patch("aitbc_cli.commands.governance.output"),
    ):
        result = CliRunner().invoke(governance, ["close", "--proposal-id", "prop_4"])
    assert result.exit_code == 0, result.output
    assert captured["json"] is None


def test_propose_signs_body_and_binds_proposer() -> None:
    captured: dict = {}
    with (
        patch("aitbc_cli.commands.governance._get_client", return_value=_fake_client(captured)),
        patch("aitbc_cli.commands.governance._wallet_signer", return_value=(ADDR, PK.to_hex())),
        patch("aitbc_cli.commands.governance._governance_rpc", return_value=(MagicMock(), "c")),
        patch("aitbc_cli.commands.governance._get_governance_account", return_value={"balance": 5}),
        patch("aitbc_cli.commands.governance._sign_governance_tx", return_value={"signed": True}),
        patch("aitbc_cli.commands.governance.output"),
    ):
        result = CliRunner().invoke(
            governance,
            ["propose", "--title", "t", "--description", "d", "--proposer-id", "profile-name"],
        )
    assert result.exit_code == 0, result.output
    body = captured["json"]
    assert body["proposer_id"] == ADDR
    unsigned = {k: v for k, v in body.items() if k != "signature"}
    assert _verify(ADDR, body["signature"], unsigned)
