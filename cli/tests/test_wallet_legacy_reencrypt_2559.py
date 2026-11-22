"""#2559: loading a legacy plaintext wallet re-encrypts it as a NEW password
(two-source confirm semantics), verifies the blob, keeps a .bak, and
replaces the file atomically — a bad prompt must never strand the key."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from aitbc_cli.commands.wallet import _load_wallet, decrypt_value
from aitbc_cli.utils.error_handling import CLIError

PRIV = "0x" + "ab" * 32
NEW_PW = "correct-horse-battery"


@pytest.fixture
def wallet_file(tmp_path):
    path = tmp_path / "w1.json"
    path.write_text(
        json.dumps(
            {
                "name": "w1",
                "address": "0xabc",
                "encrypted": True,
                "private_key": PRIV,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    os.chmod(path, 0o600)
    return path


@pytest.fixture
def pw_file(tmp_path):
    p = tmp_path / "pw.txt"
    p.write_text(NEW_PW + "\n")
    os.chmod(p, 0o600)
    return p


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_successful_reencrypt_verifies_backs_up_and_replaces(wallet_file, pw_file):
    before = wallet_file.read_bytes()
    result = _load_wallet(wallet_file, "w1", password_file=str(pw_file))
    assert result["private_key"] == PRIV  # plaintext for in-memory use

    on_disk = json.loads(wallet_file.read_text())
    assert isinstance(on_disk["private_key"], dict)  # really encrypted now
    assert decrypt_value(on_disk["private_key"], NEW_PW) == PRIV
    with pytest.raises(ValueError):
        decrypt_value(on_disk["private_key"], "wrong-password")

    bak = wallet_file.with_name("w1.json.bak")
    assert bak.read_bytes() == before  # byte-faithful backup of the legacy file
    assert _mode(bak) == 0o600
    assert _mode(wallet_file) == 0o600
    assert not wallet_file.with_name("w1.json.tmp").exists()
    # the re-encrypted file differs from the backup — a real rewrite happened
    assert wallet_file.read_bytes() != before


def test_uses_new_password_resolver_not_existing_wallet_one(wallet_file, monkeypatch):
    """The legacy path must resolve through resolve_new_wallet_password —
    the resolver with confirmation semantics — never resolve_wallet_password."""
    import aitbc_cli.utils.wallet_secret as ws

    calls = []

    def _new_pw(*a, **k):
        calls.append("new")
        return NEW_PW

    def _old_pw(*a, **k):
        calls.append("old")
        raise AssertionError("resolve_wallet_password must not run for a new password")

    monkeypatch.setattr(ws, "resolve_new_wallet_password", _new_pw)
    monkeypatch.setattr(ws, "resolve_wallet_password", _old_pw)
    _load_wallet(wallet_file, "w1")
    assert calls == ["new"]


def test_tty_mismatch_aborts_without_touching_file(wallet_file, monkeypatch):
    """A mistyped confirmation must leave the legacy file byte-identical and
    produce no .bak — the key is never stranded by a bad prompt."""
    import getpass

    import aitbc_cli.utils.wallet_secret as ws

    class _TtyStdin:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", _TtyStdin())
    monkeypatch.setattr(ws, "_env_password", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_keyring_password", lambda *a, **k: None)
    # first prompt: new password; confirm: mismatch; reprompt: prompt failure -> abort
    prompts = iter(["pw-one", "pw-two", RuntimeError("no tty")])

    def _getpass(prompt=""):
        v = next(prompts)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(getpass, "getpass", _getpass)

    before = wallet_file.read_bytes()
    with pytest.raises(CLIError):
        _load_wallet(wallet_file, "w1")
    assert wallet_file.read_bytes() == before
    assert not wallet_file.with_name("w1.json.bak").exists()
