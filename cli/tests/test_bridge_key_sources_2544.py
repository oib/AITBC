"""Tests for bridge private-key sources (#2544).

Regression: every bridge signing option took the key only as an argv flag,
so `ps` exposed validator/admin key material to every local user. The key
now resolves --<name>-key-file > env var > hidden prompt > deprecated argv
(warns). These tests pin each source end to end through click's CliRunner.
"""

import json
import os
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.bridge as bridge_mod
from aitbc_cli.commands.bridge import attest, confirm, sign_proof, store_header


@pytest.fixture
def runner():
    return CliRunner()


_KEY = "0x" + "11" * 32
_KEY2 = "0x" + "22" * 32

_PROOF = {
    "chain_id": "ait-mainnet",
    "block_height": 100,
    "block_hash": "0x" + "ab" * 32,
    "state_root": "0x" + "cd" * 32,
}

_UNSIGNED_PROOF = {"transfer_id": "0xabc123", "block_height": 51044, "merkle_proof": ["deadbeef"]}


def _write(tmp_path, doc, name="proof.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def _write_key(tmp_path, key=_KEY, name="key.hex"):
    path = tmp_path / name
    path.write_text(key + "\n")
    os.chmod(path, 0o600)
    return str(path)


def _fake_client():
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.store_block_header = mock.AsyncMock(return_value={"stored": True})
    client.confirm = mock.AsyncMock(return_value={"confirmed": True})
    return client


def _store_args(tmp_path, *extra):
    return ["--proof-file", _write(tmp_path, _PROOF), *extra]


class TestStoreHeaderKeySources:
    def test_key_file_signs_without_argv(self, runner, tmp_path):
        key_file = _write_key(tmp_path)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                store_header,
                obj={"output_format": "table"},
                args=_store_args(tmp_path, "--admin-private-key-file", key_file),
            )
        assert result.exit_code == 0, result.output
        assert "process list" not in result.output
        client.store_block_header.assert_awaited_once()

    def test_env_var_signs_without_argv(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("AITBC_BRIDGE_ADMIN_PRIVATE_KEY", _KEY)
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(store_header, obj={"output_format": "table"}, args=_store_args(tmp_path))
        assert result.exit_code == 0, result.output
        client.store_block_header.assert_awaited_once()

    def test_hidden_prompt_signs_without_argv(self, runner, tmp_path):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                store_header,
                obj={"output_format": "table"},
                args=_store_args(tmp_path),
                input=_KEY + "\n",
            )
        assert result.exit_code == 0, result.output
        assert "admin-private-key private key" in result.output
        client.store_block_header.assert_awaited_once()

    def test_argv_key_still_works_but_warns(self, runner, tmp_path):
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                store_header,
                obj={"output_format": "table"},
                args=_store_args(tmp_path, "--admin-private-key", _KEY),
            )
        assert result.exit_code == 0, result.output
        assert "process list" in result.output


class TestSignProofKeySources:
    def test_key_files_sign_multi_sig_without_argv(self, runner, tmp_path):
        k1 = _write_key(tmp_path, _KEY, "k1.hex")
        k2 = _write_key(tmp_path, _KEY2, "k2.hex")
        proof_file = _write(tmp_path, _UNSIGNED_PROOF)
        out = tmp_path / "signed.json"
        result = runner.invoke(
            sign_proof,
            obj={"output_format": "table"},
            args=[
                "--proof-file",
                proof_file,
                "--private-key-file",
                k1,
                "--private-key-file",
                k2,
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        signed = json.loads(out.read_text())
        assert len(signed["validator_signatures"]) == 2

    def test_env_var_comma_separated_signs_without_argv(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("AITBC_BRIDGE_PRIVATE_KEYS", f"{_KEY},{_KEY2}")
        proof_file = _write(tmp_path, _UNSIGNED_PROOF)
        out = tmp_path / "signed.json"
        result = runner.invoke(
            sign_proof,
            obj={"output_format": "table"},
            args=["--proof-file", proof_file, "--output", str(out)],
        )
        assert result.exit_code == 0, result.output
        signed = json.loads(out.read_text())
        assert len(signed["validator_signatures"]) == 2


class TestConfirmKeyFile:
    def test_confirmer_key_file_signs_without_argv(self, runner, tmp_path):
        key_file = _write_key(tmp_path)
        proof = _write(tmp_path, {"transfer_id": "tx-1", "proof": []}, "lock-proof.json")
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                confirm,
                obj={"output_format": "table"},
                args=[
                    "--transfer-id",
                    "tx-1",
                    "--confirmer",
                    "0xAbc",
                    "--confirmer-private-key-file",
                    key_file,
                    "--proof-file",
                    proof,
                ],
            )
        assert result.exit_code == 0, result.output
        client.confirm.assert_awaited_once()
        assert client.confirm.await_args.kwargs["signature"].startswith("0x")


class TestAttestKeySources:
    def test_attest_env_key_signs_without_argv(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("AITBC_BRIDGE_PRIVATE_KEY", _KEY)
        header = {
            "chain_id": "ait-mainnet",
            "height": 5,
            "hash": "0x" + "11" * 32,
            "state_root": "0x" + "22" * 32,
        }
        header_file = _write(tmp_path, header, "header.json")
        client = _fake_client()
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                attest,
                obj={"output_format": "table"},
                args=["--header-file", header_file],
            )
        assert result.exit_code == 0, result.output
        client.store_block_header.assert_awaited_once()
        assert client.store_block_header.await_args.args[0]["signature"]
