"""Tests for AITBC_WALLET_DIR resolution and the shared send-path search."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.agent import _resolve_wallet_address
from aitbc_cli.utils.wallet_paths import (
    ambiguous_wallet_note,
    find_wallet_file,
    find_wallet_file_report,
    wallet_dir,
    wallet_not_found_hint,
    wallet_not_found_message,
)


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
    wallet_path.write_text(json.dumps({"address": "0xAC2A166407d6e39f1b3B884b93319686b658B276"}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    assert _resolve_wallet_address("shop") == "0xAC2A166407d6e39f1b3B884b93319686b658B276"


def test_resolve_wallet_address_missing_env_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "does-not-exist"))
    assert _resolve_wallet_address("shop") is None


# ---------------------------------------------------------------------------
# Shared send-path search (CLI-6): configured dir, then service wallet dir.
# Every fixture lives under tmp_path — the real /var/lib/aitbc and /etc/aitbc
# are never touched: _SERVICE_WALLET_DIRS is monkeypatched to the temp dir.
# ---------------------------------------------------------------------------


@pytest.fixture
def two_wallet_dirs(monkeypatch, tmp_path):
    """AITBC_WALLET_DIR + a fake service wallet dir, both under tmp_path."""
    configured = tmp_path / "configured"
    service = tmp_path / "service-wallets"
    configured.mkdir()
    service.mkdir()
    monkeypatch.setenv("AITBC_WALLET_DIR", str(configured))
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths._SERVICE_WALLET_DIRS", [str(service)])
    return configured, service


def _write_wallet(directory: Path, name: str, **overrides) -> Path:
    data = {"address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "private_key": "not-a-real-key", "encrypted": False}
    data.update(overrides)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(data))
    return path


def test_find_wallet_file_service_dir_only(two_wallet_dirs):
    _, service = two_wallet_dirs
    _write_wallet(service, "sepolia")
    assert find_wallet_file("sepolia") == service / "sepolia.json"


def test_find_wallet_file_configured_dir_wins(two_wallet_dirs):
    configured, service = two_wallet_dirs
    _write_wallet(configured, "dup")
    _write_wallet(service, "dup")
    report = find_wallet_file_report("dup")
    assert report.path == configured / "dup.json"
    assert len(report.matches) == 2
    note = ambiguous_wallet_note(report)
    assert note and str(configured / "dup.json") in note


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission bits — dir stays readable")
def test_report_marks_unreadable_dir(two_wallet_dirs):
    configured, service = two_wallet_dirs
    service.chmod(0o000)
    try:
        report = find_wallet_file_report("sepolia")
    finally:
        service.chmod(0o700)
    assert report.path is None
    assert service in report.unreadable
    hint = wallet_not_found_hint(report)
    assert str(configured) in hint and "unreadable" in hint


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission bits — file stays readable")
def test_report_marks_unreadable_file(two_wallet_dirs):
    configured, _ = two_wallet_dirs
    path = _write_wallet(configured, "locked")
    path.chmod(0o000)
    try:
        report = find_wallet_file_report("locked")
    finally:
        path.chmod(0o600)
    assert report.path is None
    assert path in report.unreadable


def test_not_found_message_lists_every_dir(two_wallet_dirs, monkeypatch):
    configured, service = two_wallet_dirs
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths.daemon_keystore_has", lambda name: None)
    message = wallet_not_found_message(find_wallet_file_report("ghost"))
    assert str(configured) in message and str(service) in message
    assert "--wallet-path" in message


def test_not_found_message_names_daemon_keystore(two_wallet_dirs, monkeypatch):
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths.daemon_keystore_has", lambda name: True)
    message = wallet_not_found_message(find_wallet_file_report("daemon-only"))
    assert "daemon keystore" in message and "--wallet-path" in message


# ---------------------------------------------------------------------------
# Command level: `transactions send` / `wallet send` must find service-dir
# wallets and report a dir-aware error when nothing resolves.
# ---------------------------------------------------------------------------


def test_transactions_send_finds_service_dir_wallet(two_wallet_dirs):
    """A wallet that only exists in the service dir is found, read, and its
    path printed before signing (CLI-6 ASK: path only, never contents)."""
    _, service = two_wallet_dirs
    _write_wallet(service, "sepolia")
    from aitbc_cli.commands.transactions import transactions

    result = CliRunner().invoke(
        transactions, ["send", "--from", "sepolia", "--to", "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "--amount", "1"]
    )
    # The wallet was found and opened — the failure is the bogus test key,
    # which proves resolution reached the file, not the not-found branch.
    assert "not found" not in result.output.lower()
    assert "Error loading private key" in result.output
    assert f"Using wallet file: {service / 'sepolia.json'}" in result.output
    assert "not-a-real-key" not in result.output


def test_transactions_send_configured_dir_wins_and_reports(two_wallet_dirs, monkeypatch):
    """Same name in both dirs: AITBC_WALLET_DIR wins and the output names the
    path actually used (CLI-6 ASK)."""
    configured, service = two_wallet_dirs
    _write_wallet(configured, "dup")
    _write_wallet(service, "dup")
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths.daemon_keystore_has", lambda name: None)
    from aitbc_cli.commands.transactions import transactions

    result = CliRunner().invoke(
        transactions,
        ["send", "--from", "dup", "--to", "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "--amount", "1", "--password", "pw"],
    )
    assert str(configured / "dup.json") in result.output
    # The service-dir path must not be claimed as the one in use.
    assert f"Using wallet file: {service / 'dup.json'}" not in result.output


def test_transactions_send_not_found_lists_dirs(two_wallet_dirs, monkeypatch):
    configured, service = two_wallet_dirs
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths.daemon_keystore_has", lambda name: None)
    from aitbc_cli.commands.transactions import transactions

    result = CliRunner().invoke(
        transactions,
        ["send", "--from", "ghost", "--to", "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "--amount", "1", "--password", "pw"],
    )
    assert str(configured) in result.output and str(service) in result.output


def test_wallet_send_finds_service_dir_wallet(two_wallet_dirs, monkeypatch):
    """`wallet send` resolves the group wallet_path through the search order."""
    _, service = two_wallet_dirs
    _write_wallet(service, "sepolia")
    monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet.get_config",
        lambda: type("C", (), {"blockchain_rpc_url": "http://127.0.0.1:1", "wallet_url": "http://127.0.0.1:1"})(),
    )
    from aitbc_cli.commands.wallet import wallet

    result = CliRunner().invoke(
        wallet,
        [
            "--wallet-name",
            "sepolia",
            "send",
            "--to-address",
            "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
            "--amount",
            "1",
            "--password",
            "pw",
        ],
    )
    assert "not found" not in result.output.lower()
    assert f"Using wallet file: {service / 'sepolia.json'}" in result.output


def test_wallet_send_not_found_lists_dirs(two_wallet_dirs, monkeypatch):
    configured, service = two_wallet_dirs
    monkeypatch.setattr("aitbc_cli.utils.wallet_paths.daemon_keystore_has", lambda name: None)
    monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet.get_config",
        lambda: type("C", (), {"blockchain_rpc_url": "http://127.0.0.1:1", "wallet_url": "http://127.0.0.1:1"})(),
    )
    from aitbc_cli.commands.wallet import wallet

    result = CliRunner().invoke(
        wallet,
        ["--wallet-name", "ghost", "send", "--to-address", "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "--amount", "1"],
    )
    assert str(configured) in result.output and str(service) in result.output


def test_wallet_group_explicit_path_wins(two_wallet_dirs, monkeypatch, tmp_path):
    """--wallet-path overrides every searched directory."""
    explicit = tmp_path / "elsewhere" / "sepolia.json"
    explicit.parent.mkdir()
    explicit.write_text(json.dumps({"address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "encrypted": False}))
    _, service = two_wallet_dirs
    _write_wallet(service, "sepolia")
    monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet.get_config",
        lambda: type("C", (), {"blockchain_rpc_url": "http://127.0.0.1:1", "wallet_url": "http://127.0.0.1:1"})(),
    )
    from aitbc_cli.commands.wallet import wallet

    captured = {}
    import aitbc_cli.commands.wallet.basic as basic

    real = basic._load_wallet
    monkeypatch.setattr(
        basic,
        "_load_wallet",
        lambda path, name, password=None: captured.setdefault("path", Path(path)) or real(path, name, password=password),
    )
    CliRunner().invoke(
        wallet,
        [
            "--wallet-path",
            str(explicit),
            "send",
            "--to-address",
            "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
            "--amount",
            "1",
        ],
    )
    assert captured.get("path") == explicit


def test_wallet_delete_does_not_reach_service_dir(two_wallet_dirs, monkeypatch):
    """Destructive ops stay narrow (CLI-6 ASK): `wallet delete --name` must NOT
    find a wallet that exists only in the service dir."""
    _, service = two_wallet_dirs
    service_wallet = _write_wallet(service, "sepolia")
    monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
    monkeypatch.setattr(
        "aitbc_cli.commands.wallet.get_config",
        lambda: type("C", (), {"blockchain_rpc_url": "http://127.0.0.1:1", "wallet_url": "http://127.0.0.1:1"})(),
    )
    configured, _ = two_wallet_dirs
    from aitbc_cli.commands.wallet import wallet

    result = CliRunner().invoke(wallet, ["delete", "--name", "sepolia", "--confirm"])
    assert "does not exist" in result.output
    assert str(configured) in result.output
    assert service_wallet.exists()
