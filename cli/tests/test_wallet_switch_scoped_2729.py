"""Pin for WALLET-SWITCH-SCRATCH-1 (#2729).

``wallet switch`` under ``AITBC_WALLET_DIR`` must record the active wallet
in an env-scoped pointer (``<dir>/.active_wallet``) and leave the global
``~/.aitbc/config.yaml`` untouched — a scratch wallet name must never
break unscoped invocations. Resolution under the override reads the scoped
pointer and ignores the global config.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from aitbc_cli.commands.wallet import wallet
from aitbc_cli.utils.wallet_loader import _resolve_wallet_name_and_path
from aitbc_cli.utils.wallet_paths import (
    env_wallet_dir_override_active,
    read_scoped_active_wallet,
    scoped_active_wallet_path,
)

ADDR = "0x" + "11" * 20


def _make_wallet(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps({"wallet_id": name, "type": "simple", "address": ADDR}))


def _invoke(args, obj=None):
    return CliRunner().invoke(wallet, args, obj=obj or {"output_format": "table"})


def test_switch_under_env_writes_scoped_pointer_not_global(tmp_path, monkeypatch):
    wallet_dir = tmp_path / "scratch" / "wallets"
    _make_wallet(wallet_dir, "r6-simple")
    home = tmp_path / "home"
    (home / ".aitbc").mkdir(parents=True)
    config_file = home / ".aitbc" / "config.yaml"
    config_file.write_text("active_wallet: real-active\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))

    result = _invoke(["switch", "--name", "r6-simple"])
    assert result.exit_code == 0, result.output

    # Scoped pointer written inside the env dir; global config untouched.
    assert (wallet_dir / ".active_wallet").read_text().strip() == "r6-simple"
    assert "active_wallet: real-active" in config_file.read_text()


def test_switch_without_env_still_writes_global_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    wallet_dir = home / ".aitbc" / "wallets"
    _make_wallet(wallet_dir, "real-active")
    (home / ".aitbc").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.setenv("AITBC_DEFAULT_WALLET", "")

    result = _invoke(["switch", "--name", "real-active"])
    assert result.exit_code == 0, result.output
    config_file = home / ".aitbc" / "config.yaml"
    assert "active_wallet: real-active" in config_file.read_text()
    assert not (wallet_dir / ".active_wallet").exists()


def test_resolution_under_env_uses_scoped_pointer(tmp_path, monkeypatch):
    wallet_dir = tmp_path / "scratch" / "wallets"
    _make_wallet(wallet_dir, "r6-simple")
    (wallet_dir / ".active_wallet").write_text("r6-simple\n")
    home = tmp_path / "home"
    (home / ".aitbc").mkdir(parents=True)
    (home / ".aitbc" / "config.yaml").write_text("active_wallet: real-active\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))
    monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
    monkeypatch.delenv("AITBC_MARKET_WALLET", raising=False)

    name, path = _resolve_wallet_name_and_path()
    assert name == "r6-simple"
    assert path.name == "r6-simple.json"


def test_resolution_without_env_uses_global_config(tmp_path, monkeypatch):
    wallet_dir = tmp_path / "wallets"
    _make_wallet(wallet_dir, "real-active")
    home = tmp_path / "home"
    (home / ".aitbc").mkdir(parents=True)
    (home / ".aitbc" / "config.yaml").write_text("active_wallet: real-active\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
    monkeypatch.delenv("AITBC_MARKET_WALLET", raising=False)

    name, path = _resolve_wallet_name_and_path()
    assert name == "real-active"


def test_scoped_helpers(tmp_path, monkeypatch):
    wallet_dir = tmp_path / "w"
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))
    assert env_wallet_dir_override_active()
    assert scoped_active_wallet_path() == wallet_dir / ".active_wallet"
    assert read_scoped_active_wallet() is None
    from aitbc_cli.utils.wallet_paths import write_scoped_active_wallet

    write_scoped_active_wallet("scratch-1")
    assert read_scoped_active_wallet() == "scratch-1"
    write_scoped_active_wallet(None)
    assert read_scoped_active_wallet() is None
    assert not (wallet_dir / ".active_wallet").exists()
