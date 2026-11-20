"""Tests for ``aitbc security audit|scan|patch`` (#2341).

The commands run real local checks: audit-log integrity via
``SecureAuditLogger.verify_integrity()`` and filesystem permission checks
on wallet/credential/audit files.  Tests isolate ``HOME`` (and the service
wallet dir) with ``tmp_path`` so the host's real ``~/.aitbc`` never leaks in.
"""

from __future__ import annotations

import json
import os
import stat

import pytest
from aitbc_cli.commands import security as security_mod
from aitbc_cli.commands.security import security
from aitbc_cli.utils.secure_audit import SecureAuditLogger
from click.testing import CliRunner


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    """Point HOME at a fresh tmp dir and keep service dirs out of the scan."""
    home = tmp_path / "home"
    home.mkdir()
    # Pre-create ~/.aitbc at 0700: SecureAuditLogger mkdir(parents=True)
    # would otherwise leave it at the umask default (0755) and every test
    # would start with a dir-permission finding.
    aitbc_dir = home / ".aitbc"
    aitbc_dir.mkdir(mode=0o700)
    os.chmod(aitbc_dir, 0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AITBC_WALLET_DIR", raising=False)
    monkeypatch.setattr(security_mod, "_SERVICE_WALLET_DIRS", ())
    return home


def _run(args, fmt="json"):
    return CliRunner().invoke(security, args, obj={"output_format": fmt})


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_audit_clean_home_is_live_and_top_grade(isolated_home):
    data = _json(_run(["audit"]))
    assert data["status"] == "live"
    assert data["security_score"] == "A+"
    assert data["vulnerabilities"] == 0
    assert data["audit_log"]["verified"] is True
    assert data["checks"], "expected per-check rows"


def test_scan_reports_world_readable_wallet_and_patch_fixes_it(isolated_home):
    wallet = isolated_home / ".aitbc" / "wallets" / "bob.json"
    wallet.parent.mkdir(parents=True, exist_ok=True)
    wallet.write_text("{}")
    os.chmod(wallet, 0o644)

    scan_data = _json(_run(["scan"]))
    assert scan_data["status"] == "live"
    assert scan_data["issues_found"] >= 1
    rows = [i for i in scan_data["issues"] if i["check"] == "wallet_file_perms"]
    assert rows and rows[0]["target"] == str(wallet)
    assert rows[0]["actual"] == "0644"
    assert rows[0]["expected"] == "0600"
    assert rows[0]["severity"] == "high"

    patch_data = _json(_run(["patch"]))
    assert patch_data["status"] == "live"
    applied = [r for r in patch_data["results"] if r["target"] == str(wallet)]
    assert applied and applied[0]["action"] == "applied"
    assert applied[0]["before"] == "0644"
    assert applied[0]["after"] == "0600"
    assert stat.S_IMODE(wallet.stat().st_mode) == 0o600

    # A second patch run reports the file as already compliant.
    patch_again = _json(_run(["patch"]))
    applied2 = [r for r in patch_again["results"] if r["target"] == str(wallet)]
    assert applied2 and applied2[0]["action"] == "skipped"
    assert applied2[0]["detail"] == "already compliant"


def test_audit_reports_tampered_audit_log(isolated_home):
    audit_dir = isolated_home / ".aitbc" / "audit"
    logger = SecureAuditLogger(log_dir=audit_dir)
    logger.log("wallet_create", {"wallet": "alice"}, user="test")

    # Tamper: rewrite the first log line so its stored hash no longer matches.
    log_file = audit_dir / "audit_secure.jsonl"
    lines = log_file.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["action"] = "wallet_delete"
    lines[0] = json.dumps(entry)
    log_file.write_text("\n".join(lines) + "\n")

    data = _json(_run(["audit"]))
    assert data["status"] == "live"
    assert data["audit_log"]["verified"] is False
    assert data["audit_log"]["issues"], "expected integrity issues"
    integrity_rows = [c for c in data["checks"] if c["check"] == "audit_log_integrity"]
    assert integrity_rows and integrity_rows[0]["passed"] is False
    assert data["vulnerabilities"] >= 1
    assert data["security_score"] != "A+"


def test_missing_files_are_skipped_not_failures(isolated_home):
    # No wallets, no credentials — only the audit dir the logger creates.
    data = _json(_run(["scan"]))
    assert data["status"] == "live"
    assert data["issues_found"] == 0


def test_credentials_file_permission_checked(isolated_home):
    creds = isolated_home / ".aitbc" / "credentials.json"
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text("{}")
    os.chmod(creds, 0o640)

    data = _json(_run(["scan"]))
    rows = [i for i in data["issues"] if i["check"] == "credentials_file_perms"]
    assert rows and rows[0]["actual"] == "0640"

    _json(_run(["patch"]))
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600
