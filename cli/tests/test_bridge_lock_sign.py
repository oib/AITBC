"""SEC-REPLAY-1: ``aitbc bridge lock --wallet-name`` signs issued_at + nonce.

The six-field lock dict is replayable; wallet-signed locks now add
``issued_at`` (epoch seconds) and ``nonce`` (random 16-byte hex) inside the
signed dict, and send both in the request.

CALLERS-NEWFORM-1: the raw ``--signature`` path accepts ``--issued-at`` /
``--nonce`` so an external signer can submit the replay-guarded form; both or
neither is required, and the old form still sends with a warning.
"""

import json
from unittest import mock

import click
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
    _WALLET_ARGS = [
        "--target-chain",
        "ait-side",
        "--recipient",
        "0x" + "cc" * 20,
        "--amount",
        "3600000",
    ]

    def test_wallet_signs_the_replay_guarded_dict(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _fake_client()
        with (
            mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client),
            mock.patch.object(bridge_mod, "_resolve_node_chain_id", return_value="ait-testchain"),
        ):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._WALLET_ARGS, "--sender", sender, "--wallet-name", "w"],
            )
        assert result.exit_code == 0, result.output
        kwargs = client.lock.call_args.kwargs
        issued_at, nonce = kwargs["issued_at"], kwargs["nonce"]
        assert isinstance(issued_at, int) and issued_at > 0
        assert isinstance(nonce, str) and len(nonce) == 32

        # CLI-SRCCHAIN-1: the resolved chain ID is signed AND sent — the
        # server verifies exactly the value the body carries.
        assert kwargs["source_chain"] == "ait-testchain"

        # Recompute the server-side check: canonical-hash the exact dict
        # (including issued_at/nonce) and recover the signer.
        signed = {
            "source_chain": "ait-testchain",
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

    def test_wallet_explicit_source_chain_skips_resolution(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _fake_client()
        with (
            mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client),
            mock.patch.object(bridge_mod, "_resolve_node_chain_id") as resolver,
        ):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._WALLET_ARGS, "--sender", sender, "--wallet-name", "w", "--source-chain", "ait-explicit"],
            )
        assert result.exit_code == 0, result.output
        resolver.assert_not_called()
        assert client.lock.call_args.kwargs["source_chain"] == "ait-explicit"

    def test_wallet_unresolvable_chain_id_errors(self, runner, tmp_path, monkeypatch):
        (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV}))
        monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
        sender = _addr(_PRIV)
        client = _fake_client()
        with (
            mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client),
            mock.patch.object(
                bridge_mod,
                "_resolve_node_chain_id",
                side_effect=click.ClickException("Could not resolve the node's chain ID"),
            ),
        ):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._WALLET_ARGS, "--sender", sender, "--wallet-name", "w"],
            )
        assert result.exit_code != 0
        assert "chain ID" in result.output
        client.lock.assert_not_called()

    def test_resolve_node_chain_id_mirrors_server_default(self, runner, monkeypatch):
        """/rpc/proposer returning an empty/absent chain_id must fail loudly —
        signing with a guessed id would produce a signature the node rejects."""
        resp = mock.Mock()
        resp.json.return_value = {"chain_id": "ait-from-node"}
        resp.raise_for_status = lambda: None
        with mock.patch.object(bridge_mod.httpx, "get", return_value=resp) as get:
            assert bridge_mod._resolve_node_chain_id("http://n:8202/rpc/") == "ait-from-node"
        get.assert_called_once_with("http://n:8202/rpc/proposer", timeout=5.0)

        resp.json.return_value = {"proposer_id": "0x0"}
        with mock.patch.object(bridge_mod.httpx, "get", return_value=resp):
            with pytest.raises(click.ClickException, match="chain ID"):
                bridge_mod._resolve_node_chain_id("http://n:8202/rpc")

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

    _RAW_ARGS = [
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
    ]

    def test_raw_signature_with_replay_fields(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._RAW_ARGS, "--issued-at", "1760000000", "--nonce", "ab12cd34"],
            )
        assert result.exit_code == 0, result.output
        kwargs = client.lock.call_args.kwargs
        assert kwargs["issued_at"] == 1760000000
        assert kwargs["nonce"] == "ab12cd34"

    def test_raw_signature_old_form_warns(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=self._RAW_ARGS,
            )
        assert result.exit_code == 0, result.output
        assert "old-form" in result.output

    def test_issued_at_without_nonce_fails(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._RAW_ARGS, "--issued-at", "1760000000"],
            )
        assert result.exit_code != 0
        assert "given together" in result.output
        client.lock.assert_not_called()

    def test_nonce_without_issued_at_fails(self, runner):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                lock,
                obj={"output_format": "table"},
                args=[*self._RAW_ARGS, "--nonce", "ab12cd34"],
            )
        assert result.exit_code != 0
        assert "given together" in result.output
        client.lock.assert_not_called()
