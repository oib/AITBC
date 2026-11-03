"""Pin for CLI-WALLET-FILE-MODES-1 (#845).

Wallet-bearing files must be written 0600 with no umask window:
``os.open(O_NOFOLLOW, 0600)`` + ``fchmod`` on every write (``write_json_0600``).
Covers create, import-wallet, export, restore, multisig-create, the shared
resave path, and symlink refusal.
"""

import json
import os
import stat

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.wallet import wallet
from aitbc_cli.utils.wallet_loader import write_json_0600


def _invoke(tmp_path, args, monkeypatch):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    return CliRunner().invoke(wallet, args, obj={"output_format": "table"})


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture(autouse=True)
def _umask_022(monkeypatch):
    """Force a permissive umask so a mode leak cannot hide behind 077."""
    old = os.umask(0o022)
    yield
    os.umask(old)


def test_write_json_0600_creates_owner_only(tmp_path):
    target = tmp_path / "w.json"
    write_json_0600(target, {"private_key": "x"})
    assert _mode(target) == 0o600
    assert json.loads(target.read_text()) == {"private_key": "x"}


def test_write_json_0600_tightens_existing_lax_file(tmp_path):
    target = tmp_path / "w.json"
    target.write_text("{}")
    os.chmod(target, 0o644)
    write_json_0600(target, {"a": 1})
    assert _mode(target) == 0o600


def test_write_json_0600_refuses_symlink(tmp_path):
    victim = tmp_path / "victim.json"
    victim.write_text('{"keep": true}')
    link = tmp_path / "w.json"
    link.symlink_to(victim)
    with pytest.raises(OSError):
        write_json_0600(link, {"private_key": "x"})
    assert json.loads(victim.read_text()) == {"keep": True}


def test_create_writes_0600(tmp_path, monkeypatch):
    result = _invoke(tmp_path, ["create", "--name", "w1", "--type", "simple", "--no-encrypt"], monkeypatch)
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path / "wallets" / "w1.json") == 0o600


def test_import_writes_0600(tmp_path, monkeypatch):
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"name": "imp", "address": "0xabc"}))
    result = _invoke(tmp_path, ["import-wallet", "--file-path", str(src)], monkeypatch)
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path / "wallets" / "imp.json") == 0o600


def test_export_writes_0600(tmp_path, monkeypatch):
    dest = tmp_path / "out.json"
    result = _invoke(
        tmp_path,
        ["create", "--name", "w2", "--type", "simple", "--no-encrypt"],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    result = _invoke(tmp_path, ["--wallet-name", "w2", "export", "--destination", str(dest)], monkeypatch)
    assert result.exit_code == 0, result.output
    assert _mode(dest) == 0o600


def test_restore_writes_0600(tmp_path, monkeypatch):
    backup = tmp_path / "bak.json"
    backup.write_text(json.dumps({"private_key": "0x" + "11" * 32, "address": "0xabc"}))
    result = _invoke(
        tmp_path,
        ["restore", "--backup-path", str(backup), "--name", "rst", "--force"],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path / "wallets" / "rst.json") == 0o600


def test_multisig_create_writes_0600(tmp_path, monkeypatch):
    result = _invoke(
        tmp_path,
        [
            "multisig-create",
            "--signers",
            "0x" + "aa" * 20,
            "--signers",
            "0x" + "bb" * 20,
            "--threshold",
            "2",
            "--name",
            "ms",
        ],
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path / "wallets" / "ms_multisig.json") == 0o600
