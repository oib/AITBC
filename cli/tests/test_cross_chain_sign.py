"""SEC-REPLAY-2: ``aitbc crosschain swap``/``bridge`` sign issued_at + nonce.

Both commands put the replay-guard fields inside the signed dict and send them
in the request body (the payload is ``dict(sign_data)``). The signature must
recover the wallet address over the exact dict the server verifies
(``aitbc_chain.rpc.routers.cross_chain._lock_transfer``).
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner
from eth_keys import keys as eth_keys
from eth_utils import keccak

import aitbc_cli.commands.cross_chain as cross_mod
from aitbc_cli.commands.cross_chain import bridge, swap

_PRIV = "0x" + "11" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _addr(priv: str) -> str:
    return str(eth_keys.PrivateKey(bytes.fromhex(priv.removeprefix("0x"))).public_key.to_checksum_address())


def _posted():
    client = mock.Mock()
    client.post = mock.Mock(return_value={"success": True, "swap_id": "swap_x", "transfer_id": "0xT"})
    return client


class TestCrossChainReplaySign:
    def test_swap_signs_and_sends_guard_fields(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV, "address": _addr(_PRIV)}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _posted()
        with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
            result = runner.invoke(
                swap,
                obj={"output_format": "table"},
                args=[
                    "--from-chain",
                    "chain-a",
                    "--to-chain",
                    "chain-b",
                    "--from-token",
                    "AIT",
                    "--to-token",
                    "AIT",
                    "--amount",
                    "1",
                    "--wallet",
                    "w",
                ],
            )
        assert result.exit_code == 0, result.output
        payload = (
            client.post.call_args.kwargs["json"]
            if client.post.call_args.kwargs
            else client.post.call_args[1].get("json") or client.post.call_args[0][1]
        )
        # The posted body IS the signed dict plus signature — guard fields ride inside.
        sign_data = {k: v for k, v in payload.items() if k != "signature"}
        assert isinstance(sign_data.get("issued_at"), int) and sign_data["issued_at"] > 0
        assert isinstance(sign_data.get("nonce"), str) and len(sign_data["nonce"]) == 32
        msg_hash = keccak(json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode())
        recovered = eth_keys.Signature(
            signature_bytes=bytes.fromhex(payload["signature"].removeprefix("0x"))
        ).recover_public_key_from_msg_hash(msg_hash)
        assert str(recovered.to_checksum_address()) == sender

    def test_bridge_signs_and_sends_guard_fields(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV, "address": _addr(_PRIV)}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _posted()
        with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
            result = runner.invoke(
                bridge,
                obj={"output_format": "table"},
                args=[
                    "--source-chain",
                    "chain-a",
                    "--target-chain",
                    "chain-b",
                    "--token",
                    "AIT",
                    "--amount",
                    "1",
                    "--wallet",
                    "w",
                ],
            )
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"] if client.post.call_args.kwargs else client.post.call_args[0][1]
        sign_data = {k: v for k, v in payload.items() if k != "signature"}
        assert isinstance(sign_data.get("issued_at"), int) and sign_data["issued_at"] > 0
        assert isinstance(sign_data.get("nonce"), str) and len(sign_data["nonce"]) == 32
        msg_hash = keccak(json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode())
        recovered = eth_keys.Signature(
            signature_bytes=bytes.fromhex(payload["signature"].removeprefix("0x"))
        ).recover_public_key_from_msg_hash(msg_hash)
        assert str(recovered.to_checksum_address()) == sender
