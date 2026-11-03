"""Pin for CLI-WALLET-IMPORT-NAME-TRAVERSAL-1 (#846).

Every wallet name joined into ``wallet_dir / f"{name}.json"`` must pass
validate_wallet_name: letters, digits, ``-``, ``_``, ``.`` only, never a
path separator and never starting with a dot. A hostile import file can no
longer steer the write path outside the wallet directory.
"""

import json

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.wallet import wallet
from aitbc_cli.utils.wallet_loader import validate_wallet_name

BAD_NAMES = ["../../x", "../escape", "a/b", "/abs/path", "..", ".", ".hidden", "x\x00y", "", "with space"]


def _invoke(tmp_path, args, monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    obj = {"output_format": "table"}
    return runner.invoke(wallet, args, obj=obj)


@pytest.mark.parametrize("name", BAD_NAMES)
def test_validate_rejects_traversal(name):
    with pytest.raises(ValueError):
        validate_wallet_name(name)


@pytest.mark.parametrize("name", ["genesis", "shop-1", "w_2", "v1.2"])
def test_validate_accepts_normal_names(name):
    assert validate_wallet_name(name) == name


def test_import_refuses_traversal_name_option(tmp_path, monkeypatch):
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"address": "0xabc"}))
    result = _invoke(tmp_path, ["import-wallet", "--file-path", str(src), "--name", "../../x"], monkeypatch)
    assert result.exit_code != 0
    assert not (tmp_path / "x.json").exists()


def test_import_ignores_hostile_file_name(tmp_path, monkeypatch):
    """File's own 'name' is ignored when it fails validation; --name absent
    falls back to the source file's stem — the write stays inside wallet_dir."""
    src = tmp_path / "safe-stem.json"
    src.write_text(json.dumps({"name": "../../x", "address": "0xabc"}))
    result = _invoke(tmp_path, ["import-wallet", "--file-path", str(src)], monkeypatch)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "wallets" / "safe-stem.json").exists()
    assert not (tmp_path / "x.json").exists()


def test_import_aborts_when_nothing_valid(tmp_path, monkeypatch):
    src = tmp_path / ".bad.json"  # stem '.bad' fails validation too
    src.write_text(json.dumps({"name": "../x", "address": "0xabc"}))
    result = _invoke(tmp_path, ["import-wallet", "--file-path", str(src)], monkeypatch)
    assert result.exit_code != 0
    assert not list((tmp_path / "wallets").glob("*.json"))


def test_create_refuses_traversal(tmp_path, monkeypatch):
    result = _invoke(tmp_path, ["create", "--name", "../../x", "--type", "simple", "--no-encrypt"], monkeypatch)
    assert result.exit_code != 0
    assert not (tmp_path / "x.json").exists()


def test_restore_refuses_traversal(tmp_path, monkeypatch):
    backup_file = tmp_path / "bak.json"
    backup_file.write_text(json.dumps({"private_key": "0x" + "11" * 32}))
    result = _invoke(tmp_path, ["restore", "--backup-path", str(backup_file), "--name", "../x", "--force"], monkeypatch)
    assert result.exit_code != 0
    assert not (tmp_path / "x.json").exists()


def test_delete_refuses_traversal(tmp_path, monkeypatch):
    # A traversal delete would unlink() a file outside the wallet dir.
    victim = tmp_path / "victim.json"
    victim.write_text("{}")
    result = _invoke(tmp_path, ["delete", "--name", "../victim", "--confirm"], monkeypatch)
    assert result.exit_code != 0
    assert victim.exists()


def test_switch_refuses_traversal(tmp_path, monkeypatch):
    result = _invoke(tmp_path, ["switch", "--name", "../victim"], monkeypatch)
    assert result.exit_code != 0


def test_backup_refuses_traversal(tmp_path, monkeypatch):
    result = _invoke(tmp_path, ["backup", "--name", "../victim"], monkeypatch)
    assert result.exit_code != 0


def test_multisig_create_refuses_traversal(tmp_path, monkeypatch):
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
            "../x",
        ],
        monkeypatch,
    )
    assert result.exit_code != 0
    assert not (tmp_path / "x_multisig.json").exists()


def test_group_wallet_name_refuses_traversal(tmp_path, monkeypatch):
    result = _invoke(
        tmp_path, ["--wallet-name", "..", "create", "--name", "ok", "--type", "simple", "--no-encrypt"], monkeypatch
    )
    assert result.exit_code != 0
