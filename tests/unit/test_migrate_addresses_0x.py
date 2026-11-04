"""#936 pin: a migrated 0x wallet keeps public_key and creates no mismatch
copy, and an env file with no legacy addresses is left untouched."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

eth_account = pytest.importorskip("eth_account")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/utils/migrate_addresses_to_0x.py"
spec = importlib.util.spec_from_file_location("migrate_addresses_to_0x", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

KEY = "0x" + "ab" * 32


def _wallet(tmp_path: Path, address: str, public_key: str = "0xpub") -> Path:
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"private_key": KEY, "address": address, "public_key": public_key}))
    return p


def test_0x_wallet_keeps_public_key_and_no_mismatch_copy(tmp_path):
    from eth_account import Account

    addr = Account.from_key(KEY).address
    w = _wallet(tmp_path, addr)
    mod.migrate_wallets(tmp_path)
    data = json.loads(w.read_text())
    assert data["address"] == addr
    assert data["public_key"] == "0xpub"  # kept, not blanked
    assert not (tmp_path / "w.json.pre-0x-mismatch").exists()


def test_env_without_legacy_addresses_untouched(tmp_path):
    env = tmp_path / "app.env"
    content = 'SET={"a": "0x' + "ab" * 20 + '", "n": 1}\nOTHER=plain\n'
    env.write_text(content)
    mod.migrate_env_files(tmp_path)
    assert env.read_text() == content
    assert not (tmp_path / "app.env.pre-0x-migration").exists()


def test_env_with_legacy_address_is_migrated_and_backup_0600(tmp_path):
    env = tmp_path / "app.env"
    env.write_text("ADDR=ait1" + "ab" * 20 + "\n")
    mod.migrate_env_files(tmp_path)
    assert "0x" + "ab" * 20 in env.read_text() or "0x" in env.read_text()
    backup = tmp_path / "app.env.pre-0x-migration"
    assert backup.exists() and (backup.stat().st_mode & 0o777) == 0o600


def test_backups_are_0600_under_permissive_umask(tmp_path):
    """Both backup copies hold secrets (private key / env lines): a permissive
    umask must not widen them. Pin: Path.touch(0o600) on both backup paths."""
    old = os.umask(0o000)  # most permissive: touch() without a mode would give 0666
    try:
        # wallet leg: stored address mismatches the derived one -> .pre-0x-mismatch
        _wallet(tmp_path, "0x" + "00" * 20)
        mod.migrate_wallets(tmp_path)
        wb = tmp_path / "w.json.pre-0x-mismatch"
        assert wb.exists(), "mismatch backup was not created"
        assert (wb.stat().st_mode & 0o777) == 0o600

        # env leg: a legacy ait1 address -> .pre-0x-migration
        env = tmp_path / "app.env"
        env.write_text("ADDR=ait1" + "cd" * 20 + "\n")
        mod.migrate_env_files(tmp_path)
        eb = tmp_path / "app.env.pre-0x-migration"
        assert eb.exists(), "env backup was not created"
        assert (eb.stat().st_mode & 0o777) == 0o600
    finally:
        os.umask(old)
