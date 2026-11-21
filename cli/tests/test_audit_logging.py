"""Pins for #2421: sensitive CLI operations write to the tamper-evident
audit log (``~/.aitbc/audit/audit_secure.jsonl`` via
``aitbc_cli.utils.secure_audit.try_log_action``).

The commands lazy-import the logger, so tests redirect the module-global
``secure_audit_logger`` to a tmp dir — the same isolation pattern as
``tests/cli/test_secure_audit.py``. HOME is patched so wallet/config/auth
state never touches the real user directory, and entries must never carry
secret material (keys, passwords, JWTs, secret values).
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.utils.secure_audit as secure_audit
from aitbc_cli.commands.auth import auth
from aitbc_cli.commands.compliance import compliance
from aitbc_cli.commands.config import config
from aitbc_cli.commands.security import security
from aitbc_cli.commands.wallet import wallet


@pytest.fixture()
def audit_log(tmp_path, monkeypatch):
    """Redirect the tamper-evident audit log into ``tmp_path/audit``."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    logger = secure_audit.SecureAuditLogger(log_dir=tmp_path / "audit")
    monkeypatch.setattr(secure_audit, "secure_audit_logger", logger)
    return logger


def _entries(logger) -> list[dict]:
    if not logger.log_file.exists():
        return []
    return [json.loads(line) for line in logger.log_file.read_text().splitlines() if line.strip()]


def _invoke(group, args, **kwargs):
    kwargs.setdefault("obj", {"output_format": "json"})
    return CliRunner().invoke(group, args, **kwargs)


def _actions(entries):
    return [e["action"] for e in entries]


# -- wallet lifecycle ---------------------------------------------------------


def test_wallet_create_emits_audit_entry(audit_log, tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    result = _invoke(wallet, ["create", "--name", "audited", "--type", "simple", "--no-encrypt"])
    assert result.exit_code == 0, result.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["wallet_create"]
    entry = entries[0]
    assert entry["details"]["wallet"] == "audited"
    assert entry["details"]["type"] == "simple"
    assert entry["details"]["encrypted"] is False
    assert entry["user"]  # resolved to a real username, never blank
    # The private key must never appear anywhere in the trail.
    assert "private_key" not in json.dumps(entry)
    is_valid, _ = audit_log.verify_integrity()
    assert is_valid is True


def test_wallet_delete_emits_only_after_confirmed_removal(audit_log, tmp_path, monkeypatch):
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    (wallet_dir / "old.json").write_text(json.dumps({"wallet_id": "old", "address": "0x" + "1" * 40}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))

    # Declined confirmation: nothing is deleted, nothing is logged.
    declined = _invoke(wallet, ["delete", "--name", "old"], input="n\n")
    assert declined.exit_code == 0, declined.output
    assert _entries(audit_log) == []
    assert (wallet_dir / "old.json").exists()

    # Confirmed deletion logs exactly one entry.
    deleted = _invoke(wallet, ["delete", "--name", "old", "--confirm"])
    assert deleted.exit_code == 0, deleted.output
    entries = _entries(audit_log)
    assert _actions(entries) == ["wallet_delete"]
    assert entries[0]["details"] == {"wallet": "old"}
    assert not (wallet_dir / "old.json").exists()


def test_wallet_export_and_import_emit_audit_entries(audit_log, tmp_path, monkeypatch):
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    source = wallet_dir / "exp.json"
    source.write_text(json.dumps({"wallet_id": "exp", "name": "exp", "address": "0x" + "3" * 40, "private_key": "deadbeef"}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))
    destination = tmp_path / "exp_copy.json"

    exported = _invoke(wallet, ["--wallet-name", "exp", "export", "--destination", str(destination)])
    assert exported.exit_code == 0, exported.output

    imported = _invoke(wallet, ["import-wallet", "--file-path", str(destination), "--name", "imported-exp"])
    assert imported.exit_code == 0, imported.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["wallet_export", "wallet_import"]
    assert entries[0]["details"]["wallet"] == "exp"
    assert entries[0]["details"]["exported_to"] == str(destination)
    assert entries[1]["action"] == "wallet_import"
    assert entries[1]["details"]["wallet"] == "imported-exp"
    assert entries[1]["details"]["imported_from"] == str(destination)
    # Key material must never be recorded — the source file's private_key
    # value is "deadbeef" and must not appear in the trail.
    assert "deadbeef" not in logger_log_text(audit_log)


def logger_log_text(logger) -> str:
    return logger.log_file.read_text() if logger.log_file.exists() else ""


def test_wallet_send_emits_audit_entry_on_submission(audit_log, tmp_path, monkeypatch):
    """A submitted (even unconfirmed) send is a real funds movement — it
    must be audited with tx metadata, and a failed submission must not
    write a misleading entry."""
    import aitbc_cli.commands.wallet.basic as basic

    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    created = _invoke(wallet, ["create", "--name", "spender", "--type", "simple", "--no-encrypt"])
    assert created.exit_code == 0, created.output
    assert _actions(_entries(audit_log)) == ["wallet_create"]

    monkeypatch.setattr(basic, "_resolve_send_rpc_endpoint", lambda ctx, rpc_url: "http://127.0.0.1:1")
    monkeypatch.setattr(basic, "_send_chain_id", lambda ctx, rpc_url: "test-chain")
    monkeypatch.setattr(basic, "_send_nonce", lambda rpc_url, addr, chain_id: 0)
    monkeypatch.setattr(basic, "_resolve_wallet_address", lambda ctx, name: None)
    monkeypatch.setattr(basic, "_build_send_transaction", lambda **kwargs: {"to": kwargs["to_address"]})
    monkeypatch.setattr(basic, "_submit_send_transaction", lambda ctx, rpc_url, tx: "0x" + "ab" * 32)
    monkeypatch.setattr(basic, "_wait_send_seal", lambda ctx, rpc_url, tx_hash, wait: None)

    sent = _invoke(
        wallet,
        ["--wallet-name", "spender", "send", "--to-address", "0x" + "22" * 20, "--amount", "1.0"],
    )
    assert sent.exit_code == 0, sent.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["wallet_create", "wallet_send"]
    details = entries[1]["details"]
    assert details["wallet"] == "spender"
    assert details["to"] == "0x" + "22" * 20
    assert details["tx_hash"] == "0x" + "ab" * 32
    assert details["sealed"] is False
    # Neither the private key nor any password material may appear.
    assert "private_key" not in json.dumps(entries[1])

    # A submission failure aborts before the audit write — no phantom entry.
    def _boom(ctx, rpc_url, tx):
        raise RuntimeError("rpc down")

    monkeypatch.setattr(basic, "_submit_send_transaction", _boom)
    failed = _invoke(
        wallet,
        ["--wallet-name", "spender", "send", "--to-address", "0x" + "22" * 20, "--amount", "1.0"],
    )
    assert failed.exit_code != 0
    assert _actions(_entries(audit_log)) == ["wallet_create", "wallet_send"]


# -- security patch ------------------------------------------------------------


def test_security_patch_emits_audit_entry(audit_log, tmp_path, monkeypatch):
    import aitbc_cli.commands.security as security_mod

    monkeypatch.setattr(security_mod, "_SERVICE_WALLET_DIRS", ())
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    result = _invoke(security, ["patch"])
    assert result.exit_code == 0, result.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["security_patch"]
    details = entries[0]["details"]
    assert set(details) == {"applied", "skipped", "failed"}
    assert details["applied"] + details["skipped"] + details["failed"] >= 0


# -- config secrets ------------------------------------------------------------


def test_config_set_secret_logs_key_name_never_value(audit_log, tmp_path, monkeypatch):
    result = _invoke(config, ["set-secret", "--key", "api_key", "--value", "s3cr3t-value-123"])
    assert result.exit_code == 0, result.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["config_set_secret"]
    assert entries[0]["details"] == {"key": "api_key"}
    # The secret value must never reach the trail.
    assert "s3cr3t-value-123" not in logger_log_text(audit_log)


# -- auth credentials ----------------------------------------------------------


@pytest.fixture()
def auth_file_store(tmp_path, monkeypatch):
    """Force the file credential backend into tmp_path — never the real
    keyring or the real ``~/.aitbc/credentials.json``."""
    import aitbc_cli.auth as auth_mod

    creds = tmp_path / "credentials.json"
    monkeypatch.setattr(auth_mod, "_DEFAULT_STORE", creds)
    monkeypatch.setattr(auth_mod, "_resolve_keyring", lambda: None)
    return creds


def test_auth_logout_emits_audit_entry_only_on_removal(audit_log, auth_file_store):
    # Nothing stored: logout warns and must NOT write an audit entry.
    missing = _invoke(auth, ["logout"])
    assert missing.exit_code == 0, missing.output
    assert _entries(audit_log) == []

    auth_file_store.write_text(json.dumps({"default_client": "stored-jwt"}))
    removed = _invoke(auth, ["logout"])
    assert removed.exit_code == 0, removed.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["auth_logout"]
    assert entries[0]["details"] == {"environment": "default", "credential_name": "client"}


def test_auth_login_emits_audit_entry_without_token(audit_log, auth_file_store, monkeypatch):
    import aitbc_cli.commands.auth as auth_cmd

    monkeypatch.setattr(auth_cmd, "_fetch_login_nonce", lambda ctx, client, address: "nonce-1")
    monkeypatch.setattr(auth_cmd, "_post_login", lambda ctx, client, address, nonce, signature: "session-jwt-xyz")

    result = _invoke(
        auth,
        [
            "login",
            "--private-key",
            "0x" + "11" * 32,
            "--coordinator-url",
            "http://127.0.0.1:1",
            "--credential-name",
            "client",
        ],
    )
    assert result.exit_code == 0, result.output

    entries = _entries(audit_log)
    assert _actions(entries) == ["auth_login"]
    details = entries[0]["details"]
    assert details["environment"] == "default"
    assert details["credential_name"] == "client"
    assert details["address"].startswith("0x")
    # The JWT must never be recorded.
    assert "session-jwt-xyz" not in logger_log_text(audit_log)


# -- compliance audit export ----------------------------------------------------


def test_compliance_export_audit_emits_entry(audit_log, tmp_path, monkeypatch):
    import aitbc_cli.commands.compliance as compliance_mod

    # Force the offline/simulated path — no coordinator configured.
    monkeypatch.setattr(compliance_mod, "_api_client", lambda *a, **k: None)
    out = tmp_path / "audit-export.json"
    result = _invoke(compliance, ["export-audit", "--output-file", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()

    entries = _entries(audit_log)
    assert _actions(entries) == ["compliance_export_audit"]
    details = entries[0]["details"]
    assert details["output_file"] == str(out)
    assert details["status"] == "simulated"
