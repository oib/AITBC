"""CLI-5: ``aitbc wallet inspect`` — public-field-only wallet file reads.

The command exists so an operator can read a wallet's address/metadata
without a password and without dumping key material: ``aitbc system file``
on an encrypted wallet would print the encrypted private_key blob. Every
case uses a REAL wallet JSON fixture (a fake encrypted blob in the shape
``_save_wallet`` writes) — no mocks of the file itself.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.wallet.misc import inspect as inspect_cmd

ADDRESS = "0x40c7181b639A2642294A802b1CD60C7a0d531a07"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def enc_wallet_file(tmp_path):
    """An encrypted wallet file with a fake blob — address stays plaintext."""
    path = tmp_path / "shop.json"
    path.write_text(
        json.dumps(
            {
                "wallet_id": "shop",
                "type": "simple",
                "address": ADDRESS,
                "public_key": "04" + "ab" * 64,
                "private_key": {
                    "encrypted_data": "Z0FBQUFBQm9mUQ==",
                    "salt": "c2FsdHNhbHQ=",
                    "algorithm": "PBKDF2+Fernet",
                    "iterations": 390000,
                    "version": 1,
                },
                "encrypted": True,
                "created_at": "2026-10-15T01:02:03Z",
                "balance": "42.5",
                "transactions": [],
            }
        )
    )
    return path


@pytest.fixture
def keystore_wallet_file(tmp_path):
    """eth-keystore shape: `encrypted` carries the whole crypto object.

    Some keystore formats store `encrypted` as an object holding the
    ciphertext — the field is public-named but its value must not dump.
    """
    path = tmp_path / "keystore.json"
    path.write_text(
        json.dumps(
            {
                "wallet_id": "keystore",
                "type": "simple",
                "address": ADDRESS,
                "encrypted": {
                    "ciphertext": "c1ph3rt3xtbG9i",
                    "cipherparams": {"iv": "aXY="},
                    "cipher": "aes-128-ctr",
                    "kdf": "scrypt",
                    "kdfparams": {"salt": "c2FsdHNhbHQ=", "n": 262144},
                },
                "created_at": "2026-10-15T01:02:03Z",
            }
        )
    )
    return path


def _invoke(runner, *args):
    return runner.invoke(inspect_cmd, list(args), obj={"output_format": "json"})


class TestPublicFields:
    def test_field_address_prints_value(self, runner, enc_wallet_file):
        result = _invoke(runner, "--path", str(enc_wallet_file), "--field", "address")
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)
        assert doc["value"] == ADDRESS

    def test_no_password_needed_for_encrypted(self, runner, enc_wallet_file):
        """Encrypted fixture + no password source → still reads metadata."""
        result = _invoke(runner, "--path", str(enc_wallet_file), "--field", "wallet_id")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["value"] == "shop"

    def test_no_field_prints_public_subset(self, runner, enc_wallet_file):
        result = _invoke(runner, "--path", str(enc_wallet_file))
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)
        assert doc["address"] == ADDRESS
        assert doc["encrypted"] is True
        # never dumps the whole file — no private or unknown keys
        assert "private_key" not in doc
        assert "transactions" not in doc


class TestPrivateRefusal:
    @pytest.mark.parametrize(
        "field",
        [
            "private_key",
            "seed",
            "seed_phrase",
            "mnemonic",
            "password",
            "secret",
            "keystore",
            "encrypted_data",
            "salt",
            "nonce",
            "iv",
            "xprv",
        ],
    )
    def test_private_names_refused(self, runner, enc_wallet_file, field):
        result = _invoke(runner, "--path", str(enc_wallet_file), "--field", field)
        assert result.exit_code != 0
        assert "private field" in result.output
        assert "encrypted_data" not in result.output.split("private field")[-1]
        # key material never reaches stdout/stderr
        assert "Z0FBQUFBQm9mUQ==" not in result.output
        assert "c2FsdHNhbHQ=" not in result.output

    def test_unknown_field_refused_with_allowlist(self, runner, enc_wallet_file):
        result = _invoke(runner, "--path", str(enc_wallet_file), "--field", "transactions")
        assert result.exit_code != 0
        assert "not a public wallet field" in result.output
        assert "address" in result.output  # allowlist is named in the error

    def test_error_paths_leak_no_blob(self, runner, enc_wallet_file):
        """Even the failure output never echoes the encrypted material."""
        result = _invoke(runner, "--path", str(enc_wallet_file), "--field", "private_key")
        assert "Z0FBQUFBQm9mUQ==" not in (result.output or "")
        assert "c2FsdHNhbHQ=" not in (result.output or "")


class TestContainerValues:
    def test_field_refuses_object_value(self, runner, keystore_wallet_file):
        result = _invoke(runner, "--path", str(keystore_wallet_file), "--field", "encrypted")
        assert result.exit_code != 0
        assert "structured value" in result.output
        # the crypto object never reaches stdout/stderr
        assert "c1ph3rt3xtbG9i" not in result.output
        assert "c2FsdHNhbHQ=" not in result.output

    def test_field_refuses_list_value(self, runner, tmp_path):
        path = tmp_path / "listy.json"
        path.write_text(json.dumps({"wallet_id": "w", "address": ADDRESS, "name": ["a", "b"]}))
        result = _invoke(runner, "--path", str(path), "--field", "name")
        assert result.exit_code != 0
        assert "structured value" in result.output

    def test_view_redacts_container_values(self, runner, keystore_wallet_file):
        result = _invoke(runner, "--path", str(keystore_wallet_file))
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)
        assert doc["address"] == ADDRESS
        assert doc["encrypted"] == "<redacted: structured value>"
        assert "c1ph3rt3xtbG9i" not in result.output
        assert "c2FsdHNhbHQ=" not in result.output

    def test_scalars_still_print_on_keystore_file(self, runner, keystore_wallet_file):
        result = _invoke(runner, "--path", str(keystore_wallet_file), "--field", "address")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["value"] == ADDRESS


class TestBadInput:
    def test_missing_file(self, runner, tmp_path):
        result = _invoke(runner, "--path", str(tmp_path / "nope.json"))
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_non_json_file(self, runner, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{")
        result = _invoke(runner, "--path", str(bad))
        assert result.exit_code != 0
        assert "Not a JSON" in result.output

    def test_non_object_json(self, runner, tmp_path):
        bad = tmp_path / "list.json"
        bad.write_text("[1,2,3]")
        result = _invoke(runner, "--path", str(bad))
        assert result.exit_code != 0
        assert "not a wallet json object" in result.output.lower()
