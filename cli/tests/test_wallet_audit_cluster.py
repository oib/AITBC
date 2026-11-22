"""Regression tests for the wallet audit cluster.

#2568 wrong-password raw crypto errors in legacy keystore branches,
#2569 unbounded PBKDF2 count in the aes-256-gcm branch,
#2570 empty AITBC_WALLET_PASSWORD treated as a real password,
#2598 load_wallet_for_payment trusting the file's address field,
#2601 --use-daemon declared as an always-true flag.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from eth_account import Account

from aitbc_cli.utils import wallet_loader
from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.wallet import decrypt_private_key
from aitbc_cli.utils.wallet_secret import _env_password

PASSWORD = "correct horse battery"


def _write_keystore(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "keystore.json"
    path.write_text(json.dumps(doc))
    return path


def _gcm_keystore(password: str, iterations: int = 100_000) -> dict:
    salt = os.urandom(32)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations, backend=default_backend())
    key = kdf.derive(password.encode())
    nonce = os.urandom(12)
    priv = AESGCM(key).encrypt(nonce, b"\x11" * 32, None)
    return {
        "crypto": {
            "cipher": "aes-256-gcm",
            "kdfparams": {"salt": salt.hex(), "c": iterations},
            "cipherparams": {"nonce": nonce.hex()},
            "ciphertext": priv.hex(),
        }
    }


def _fernet_keystore(password: str, iterations: int = 100_000, cipher: str = "fernet") -> dict:
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=32)
    ct = Fernet(base64.urlsafe_b64encode(dk)).encrypt(b"deadbeef")
    return {
        "crypto": {
            "cipher": cipher,
            "kdfparams": {"salt": base64.b64encode(salt).decode(), "c": iterations},
            "ciphertext": base64.b64encode(ct).decode(),
        }
    }


# ------------------------------------------------------------------ #2568


class TestLegacyKeystoreWrongPassword:
    @pytest.mark.parametrize("builder", [_gcm_keystore, _fernet_keystore])
    def test_wrong_password_raises_value_error(self, tmp_path, builder):
        path = _write_keystore(tmp_path, builder(PASSWORD))
        with pytest.raises(ValueError, match="Invalid password or corrupted encrypted data"):
            decrypt_private_key(path, "wrong-password")

    @pytest.mark.parametrize("builder", [_gcm_keystore, _fernet_keystore])
    def test_right_password_decrypts(self, tmp_path, builder):
        path = _write_keystore(tmp_path, builder(PASSWORD))
        out = decrypt_private_key(path, PASSWORD)
        assert out in ("11" * 32, "deadbeef")

    def test_fernet_variant_cipher_name(self, tmp_path):
        path = _write_keystore(tmp_path, _fernet_keystore(PASSWORD, cipher="PBKDF2-SHA256-Fernet"))
        with pytest.raises(ValueError, match="Invalid password"):
            decrypt_private_key(path, "nope")
        assert decrypt_private_key(path, PASSWORD) == "deadbeef"


# ------------------------------------------------------------------ #2569


class TestGcmIterationBound:
    @pytest.mark.parametrize("bad", [1, 9_999, 10_000_001, 10**12])
    def test_implausible_iterations_refused(self, tmp_path, bad):
        # Craft the doc directly: deriving with an absurd count would hang.
        doc = _gcm_keystore(PASSWORD, iterations=100_000)
        doc["crypto"]["kdfparams"]["c"] = bad
        path = _write_keystore(tmp_path, doc)
        with pytest.raises(ValueError, match="implausible PBKDF2 iteration count"):
            decrypt_private_key(path, PASSWORD)

    def test_boundary_iterations_ok(self, tmp_path):
        doc = _gcm_keystore(PASSWORD, iterations=10_000)
        path = _write_keystore(tmp_path, doc)
        assert decrypt_private_key(path, PASSWORD) == "11" * 32


# ------------------------------------------------------------------ #2570


class TestEmptyEnvPassword:
    def test_empty_env_treated_as_unset(self, monkeypatch):
        monkeypatch.delenv("AITBC_WALLET_PASSWORD_FILE", raising=False)
        monkeypatch.setenv("AITBC_WALLET_PASSWORD", "")
        assert _env_password(None, (), None) is None

    def test_empty_env_falls_through_to_legacy(self, monkeypatch):
        monkeypatch.delenv("AITBC_WALLET_PASSWORD_FILE", raising=False)
        monkeypatch.setenv("AITBC_WALLET_PASSWORD", "")
        monkeypatch.setenv("AITBC_WALLET_PASSWORD_OLD", "legacy-secret")
        assert _env_password(None, ("AITBC_WALLET_PASSWORD_OLD",), None) == "legacy-secret"

    def test_nonempty_env_still_returned(self, monkeypatch):
        monkeypatch.delenv("AITBC_WALLET_PASSWORD_FILE", raising=False)
        monkeypatch.setenv("AITBC_WALLET_PASSWORD", "real-secret")
        assert _env_password(None, (), None) == "real-secret"


# ------------------------------------------------------------------ #2598


class TestLoaderKeyAddressConsistency:
    def _patch_loader(self, monkeypatch, wallet_path: Path, wallet_doc: dict):
        monkeypatch.setattr(wallet_loader, "_resolve_wallet_name_and_path", lambda *a, **k: ("w", None))
        monkeypatch.setattr(wallet_loader, "find_wallet_file_report", lambda name: SimpleNamespace(path=None))
        monkeypatch.setattr(wallet_loader, "_resolve_signing_password", lambda *a, **k: "pw")
        monkeypatch.setattr("aitbc_cli.commands.wallet._load_wallet", lambda *a, **k: wallet_doc)

    def test_mismatched_address_aborts(self, monkeypatch, tmp_path):
        key_account = Account.create()
        other = Account.create()
        wallet_path = tmp_path / "w.json"
        wallet_path.write_text("{}")
        self._patch_loader(
            monkeypatch,
            wallet_path,
            {"address": other.address, "private_key": key_account.key.hex()},
        )
        with pytest.raises(CLIError, match="does not match the address derived"):
            wallet_loader.load_wallet_for_payment(None, wallet_name="w", wallet_path=str(wallet_path))

    def test_matching_address_returns(self, monkeypatch, tmp_path):
        key_account = Account.create()
        wallet_path = tmp_path / "w.json"
        wallet_path.write_text("{}")
        key_hex = key_account.key.hex()
        self._patch_loader(
            monkeypatch,
            wallet_path,
            {"address": key_account.address, "private_key": key_hex},
        )
        address, private_key, name = wallet_loader.load_wallet_for_payment(None, wallet_name="w", wallet_path=str(wallet_path))
        assert address.lower() == key_account.address.lower()
        assert private_key == key_hex
        assert name == "w"


# ------------------------------------------------------------------ #2601


def test_use_daemon_is_a_real_flag_pair():
    from aitbc_cli.commands.wallet import wallet

    param = next(p for p in wallet.params if p.name == "use_daemon")
    assert "--no-daemon" in param.secondary_opts
    assert param.default is True
