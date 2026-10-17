"""Tests for ``aitbc bridge unlock --wallet-name`` signing (CLI-UNLOCK-SIGN-1).

Previously ``unlock`` took only a raw ``--signature``, so a refund needed a
signature built outside the CLI. Now ``--wallet-name``/``--wallet-password``
mirror ``lock``: the command signs ``{transfer_id, sender, action: "unlock"}``
in-process — the exact dict the server verifies
(``aitbc_chain.rpc.bridge.bridge_unlock``). Raw ``--signature`` still works;
both-given and a sender/wallet mismatch are refused before any request.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner
from eth_keys import keys as eth_keys

import aitbc_cli.commands.bridge as bridge_mod
from aitbc_cli.commands.bridge import unlock

_PRIV = "0x" + "11" * 32
_PRIV2 = "0x" + "22" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _addr(priv: str) -> str:
    return str(eth_keys.PrivateKey(bytes.fromhex(priv.removeprefix("0x"))).public_key.to_checksum_address())


def _mk_wallet(tmp_path, name: str, body: dict) -> str:
    (tmp_path / f"{name}.json").write_text(json.dumps(body))
    return str(tmp_path)


def _fake_client():
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.unlock = mock.AsyncMock(return_value={"success": True, "status": "refunded"})
    return client


_ARGS_BASE = ["--transfer-id", "0xTID", "--rpc-url", "http://localhost:8202/rpc"]


class TestUnlockWalletSign:
    def test_wallet_signs_the_server_dict(self, runner, tmp_path, monkeypatch):
        wallet_dir = _mk_wallet(tmp_path, "w", {"private_key": _PRIV})
        monkeypatch.setenv("AITBC_WALLET_DIR", wallet_dir)
        sender = _addr(_PRIV)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", sender, "--wallet-name", "w"],
            )
        assert result.exit_code == 0, result.output
        sig = client.unlock.call_args.kwargs["signature"]
        # Recompute what the server does: canonical-hash the exact dict and
        # recover the signer — must be the wallet's address.
        msg_hash = bridge_mod._canonical_hash({"transfer_id": "0xTID", "sender": sender, "action": "unlock"})
        recovered = eth_keys.Signature(signature_bytes=bytes.fromhex(sig.removeprefix("0x"))).recover_public_key_from_msg_hash(
            msg_hash
        )
        assert str(recovered.to_checksum_address()) == sender
        # signature itself is never printed
        assert sig not in result.output

    def test_raw_signature_path_unchanged(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", "0xabc", "--signature", "0xsig"],
            )
        assert result.exit_code == 0, result.output
        assert client.unlock.call_args.kwargs["signature"] == "0xsig"

    def test_both_signature_and_wallet_refused(self, runner, tmp_path, monkeypatch):
        wallet_dir = _mk_wallet(tmp_path, "w", {"private_key": _PRIV})
        monkeypatch.setenv("AITBC_WALLET_DIR", wallet_dir)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", _addr(_PRIV), "--signature", "0xsig", "--wallet-name", "w"],
            )
        assert result.exit_code != 0
        assert "not both" in result.output
        client.unlock.assert_not_called()

    def test_sender_wallet_mismatch_refused(self, runner, tmp_path, monkeypatch):
        wallet_dir = _mk_wallet(tmp_path, "w", {"private_key": _PRIV})
        monkeypatch.setenv("AITBC_WALLET_DIR", wallet_dir)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", _addr(_PRIV2), "--wallet-name", "w"],
            )
        assert result.exit_code != 0
        assert "does not match" in result.output
        client.unlock.assert_not_called()

    def test_encrypted_wallet_without_password_refused(self, runner, tmp_path, monkeypatch):
        wallet_dir = _mk_wallet(tmp_path, "w", {"private_key": {"ciphertext": "x"}})
        monkeypatch.setenv("AITBC_WALLET_DIR", wallet_dir)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", _addr(_PRIV), "--wallet-name", "w"],
            )
        assert result.exit_code != 0
        assert "encrypted" in result.output
        client.unlock.assert_not_called()

    def test_neither_signature_nor_wallet_refused(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                unlock,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xTID", "--sender", "0xabc"],
            )
        assert result.exit_code != 0
        assert "required" in result.output
        client.unlock.assert_not_called()
