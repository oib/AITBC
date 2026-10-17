"""SEC-REPLAY-1: ``aitbc bridge lock --wallet-name`` signs issued_at + nonce.

The six-field lock dict is replayable; wallet-signed locks now add
``issued_at`` (epoch seconds) and ``nonce`` (random 16-byte hex) inside the
signed dict, and send both in the request. The raw ``--signature`` path stays
old-form for compatibility while the server flag is off.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner
from eth_keys import keys as eth_keys

import aitbc_cli.commands.bridge as bridge_mod
from aitbc_cli.commands.bridge import lock

_PRIV = "0x" + "11" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _addr(priv: str) -> str:
    return str(eth_keys.PrivateKey(bytes.fromhex(priv.removeprefix("0x"))).public_key.to_checksum_address())


def _fake_client():
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.lock = mock.AsyncMock(return_value={"success": True, "status": "locked"})
    return client


class TestLockWalletSign:
    def test_wallet_signs_the_replay_guarded_dict(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[
                    "--target-chain",
                    "ait-side",
                    "--sender",
                    sender,
                    "--recipient",
                    "0x" + "cc" * 20,
                    "--amount",
                    "3600000",
                    "--wallet-name",
                    "w",
                ],
            )
        assert result.exit_code == 0, result.output
        kwargs = client.lock.call_args.kwargs
        issued_at, nonce = kwargs["issued_at"], kwargs["nonce"]
        assert isinstance(issued_at, int) and issued_at > 0
        assert isinstance(nonce, str) and len(nonce) == 32

        # Recompute the server-side check: canonical-hash the exact dict
        # (including issued_at/nonce) and recover the signer.
        signed = {
            "source_chain": "",
            "target_chain": "ait-side",
            "sender": sender,
            "recipient": "0x" + "cc" * 20,
            "amount": 3600000,
            "asset": "native",
            "issued_at": issued_at,
            "nonce": nonce,
        }
        msg_hash = bridge_mod._canonical_hash(signed)
        recovered = eth_keys.Signature(
            signature_bytes=bytes.fromhex(kwargs["signature"].removeprefix("0x"))
        ).recover_public_key_from_msg_hash(msg_hash)
        assert str(recovered.to_checksum_address()) == sender

    def test_raw_signature_stays_old_form(self, runner, tmp_path):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[
                    "--target-chain",
                    "ait-side",
                    "--sender",
                    "0x" + "dd" * 20,
                    "--recipient",
                    "0x" + "cc" * 20,
                    "--amount",
                    "3600000",
                    "--signature",
                    "0x" + "ee" * 65,
                ],
            )
        assert result.exit_code == 0, result.output
        kwargs = client.lock.call_args.kwargs
        assert kwargs["issued_at"] is None and kwargs["nonce"] is None
        assert kwargs["signature"] == "0x" + "ee" * 65
