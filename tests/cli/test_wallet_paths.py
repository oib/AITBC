"""Tests for AITBC_WALLET_DIR resolution."""

from __future__ import annotations

import json
from pathlib import Path

from aitbc_cli.commands.agent import _resolve_wallet_address
from aitbc_cli.utils.wallet_paths import wallet_dir


def test_wallet_dir_defaults_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr("os.getuid", lambda: 12345)
    assert wallet_dir() == tmp_path / ".aitbc" / "wallets"


def test_wallet_dir_defaults_to_var_lib_for_aitbc_user(monkeypatch, tmp_path):
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/aitbc")))
    monkeypatch.setattr("os.getuid", lambda: 983)
    monkeypatch.setattr("pwd.getpwuid", lambda uid: type("Pw", (), {"pw_name": "aitbc"})())
    assert wallet_dir() == Path("/var/lib/aitbc/wallets")


def test_wallet_dir_defaults_to_var_lib_when_home_is_var_lib(monkeypatch, tmp_path):
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/var/lib/aitbc")))
    assert wallet_dir() == Path("/var/lib/aitbc/wallets")


def test_wallet_dir_honours_env(monkeypatch, tmp_path):
    target = tmp_path / "hub-wallets"
    monkeypatch.setenv("AITBC_WALLET_DIR", str(target))
    assert wallet_dir() == target


def test_wallet_dir_override_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "env"))
    override = tmp_path / "explicit"
    assert wallet_dir(override) == override


def test_resolve_wallet_address_uses_env_dir(monkeypatch, tmp_path):
    wallet_path = tmp_path / "shop.json"
    wallet_path.write_text(json.dumps({"address": "ait1testaddress00000000000000000000000000"}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    assert _resolve_wallet_address("shop") == "ait1testaddress00000000000000000000000000"


def test_resolve_wallet_address_missing_env_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "does-not-exist"))
    assert _resolve_wallet_address("shop") is None
