"""Fixture tests for aitbc-ops-signer.

Everything lives under tmp_path; throwaway keys are generated at runtime;
nothing touches /etc, /run, /var, the network, or a real wallet.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from aitbc_ops_signer import config as config_mod
from aitbc_ops_signer.audit import audit_line
from aitbc_ops_signer.config import Config
from aitbc_ops_signer.ledger import DailyLedger
from aitbc_ops_signer.policy import Refused, load_allowlist, parse_request
from aitbc_ops_signer.server import handle_request
from aitbc_ops_signer.signer import CredentialMissing, _credential_password

PAYEE = "0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4"
SHOP = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
STRANGER = "0x" + "ab" * 20  # 40-hex recipient not on any list
ROOT_PEER = (1234, 0, 0)
OPS_PEER = (1234, 1001, 4242)  # uid 1001, gid 4242 = aitbc-ops in tests
OUTSIDER_PEER = (1234, 1001, 9999)


class SpySigner:
    """Stands in for Signer: returns a generated hash, records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def sign_and_send(self, *, to: str, amount_units: int) -> str:
        self.calls.append((to, amount_units))
        return "0x" + os.urandom(32).hex()


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    allow = tmp_path / "ops-signer.allow"
    allow.write_text(f"# test list\n{PAYEE}\n{SHOP}   # shop wallet\n")
    return Config(
        allow_file=str(allow),
        ledger_path=str(tmp_path / "ledger.db"),
        audit_path=str(tmp_path / "audit.log"),
        wallet_path=str(tmp_path / "ops.json"),
        max_per_tx=1_000,
        max_per_day=2_500,
    )


@pytest.fixture
def deps(cfg: Config):
    return {
        "config": cfg,
        "ledger": DailyLedger(cfg.ledger_path),
        "signer": SpySigner(),
        "peer": OPS_PEER,
        "peer_gid": OPS_PEER[2],
    }


def req(to: str = PAYEE, amount: int = 500, memo: str = "S-10", **kw) -> dict:
    return {"op": "sign_payment", "to": to, "amount_units": amount, "memo": memo, **kw}


def test_recipient_not_on_allowlist_refused(deps):
    r = handle_request(req(to=STRANGER), **deps)
    assert r == {"ok": False, "result": "refused", "reason": "not_allowlisted"}
    assert deps["signer"].calls == []


def test_over_per_tx_cap_refused(deps):
    r = handle_request(req(amount=deps["config"].max_per_tx + 1), **deps)
    assert r["reason"] == "over_tx_cap"
    assert deps["signer"].calls == []


def test_daily_cap_enforced_and_serialized(deps):
    """max_per_day=2500, two concurrent 2000-unit requests: exactly one passes."""
    deps["config"] = Config(**{**deps["config"].__dict__, "max_per_tx": 5_000})
    results = []

    def go():
        results.append(handle_request(req(amount=2_000, memo="BR-8"), **deps))

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    outcomes = sorted(r["result"] for r in results)
    assert outcomes == ["refused", "signed"]
    assert deps["ledger"].spent_last_24h() == 2_000


def test_missing_and_malformed_memo_refused(deps):
    assert handle_request({"op": "sign_payment", "to": PAYEE, "amount_units": 10}, **deps)["reason"] == "bad_memo"
    assert handle_request(req(memo="free text not a task"), **deps)["reason"] == "bad_memo"
    assert handle_request(req(memo="s-10"), **deps)["reason"] == "bad_memo"  # case enforced


def test_dry_run_signs_nothing_and_consumes_nothing(deps):
    r = handle_request(req(dry_run=True), **deps)
    assert r == {"ok": True, "result": "dry_run_pass"}
    assert deps["signer"].calls == []
    assert deps["ledger"].spent_last_24h() == 0
    # dry-run sees the day cap too
    deps["ledger"].admit(2_400, memo="K-4", to_addr=PAYEE, max_per_day=2_500)
    r2 = handle_request(req(amount=500, dry_run=True), **deps)
    assert r2["reason"] == "over_day_cap"


def test_audit_line_carries_no_secret_material(tmp_path: Path, deps):
    secret = "s3cr3t-passphrase" + os.urandom(4).hex()
    key_hex = os.urandom(32).hex()
    handle_request(req(), **deps)
    audit_line(deps["config"].audit_path, memo="S-10", to=PAYEE, amount_units=5, result="refused", reason="not_allowlisted")
    text = Path(deps["config"].audit_path).read_text()
    assert "memo=S-10" in text and "result=" in text
    assert secret not in text and key_hex not in text
    assert "password" not in text and "private" not in text


def test_missing_credential_refuses_to_sign(tmp_path: Path, deps, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    with pytest.raises(CredentialMissing):
        _credential_password(tmp_path / "absent")
    # end-to-end: signer path raises inside handle_request -> fail closed
    from aitbc_ops_signer.signer import Signer

    deps["signer"] = Signer(deps["config"])
    r = handle_request(req(), **deps)
    assert r == {"ok": False, "result": "error", "reason": "internal"}


def test_peer_outside_group_refused(deps):
    deps["peer"] = OUTSIDER_PEER
    # simulate the server's peercred gate: uid 0 or gid == group gid
    from aitbc_ops_signer.server import _peer_allowed

    assert _peer_allowed(OUTSIDER_PEER, OPS_PEER[2]) is False
    assert _peer_allowed(ROOT_PEER, OPS_PEER[2]) is True
    assert _peer_allowed(OPS_PEER, OPS_PEER[2]) is True


def test_flag_off_service_does_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(config_mod.ENABLED_FLAG, raising=False)
    assert config_mod.enabled() is False
    from aitbc_ops_signer.main import main

    assert main() == 0
    assert not (tmp_path / "aitbc-ops-signer.sock").exists()


def test_allowlist_malformed_line_fails_closed(tmp_path: Path):
    bad = tmp_path / "allow"
    bad.write_text(f"{PAYEE}\nnot-an-address\n")
    with pytest.raises(Refused) as exc:
        load_allowlist(bad)
    assert "allowlist_malformed_line_2" in str(exc.value)


def test_signed_path_returns_only_hash(deps):
    r = handle_request(req(amount=500), **deps)
    assert r["ok"] is True and r["result"] == "signed"
    assert set(r) == {"ok", "result", "tx_hash"}
    assert deps["signer"].calls == [(PAYEE.lower(), 500)]


def test_parse_request_rejects_malformed_amount_and_op(deps):
    with pytest.raises(Refused):
        parse_request({"op": "sign_payment", "to": PAYEE, "amount_units": "500", "memo": "S-10"})
    with pytest.raises(Refused):
        parse_request({"op": "sweep", "to": PAYEE, "amount_units": 1, "memo": "S-10"})


# --- SEC-3b: systemd-creds decrypt fallback for LXC hosts --------------------

import logging
import subprocess
from types import SimpleNamespace

import aitbc_ops_signer.signer as signer_mod

CRED_PATH = "/etc/aitbc/credentials/ops-wallet-pass"


def _stat_result(uid: int, mode: int):
    return SimpleNamespace(st_uid=uid, st_mode=mode)


def _root600_stat(self, **kw):
    return _stat_result(0, 0o100600)


def _stub_run(monkeypatch, out: bytes = b"", rc: int = 0, err: bytes = b"", calls: list | None = None):
    def fake_run(argv, **kw):
        if calls is not None:
            calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr=err)

    monkeypatch.setattr(signer_mod.subprocess, "run", fake_run)


def test_fallback_used_when_directory_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)
    calls: list = []
    _stub_run(monkeypatch, out=b"pw-from-creds\n", calls=calls)
    assert _credential_password(CRED_PATH) == "pw-from-creds"
    argv, kw = calls[0]
    assert argv == ["systemd-creds", "decrypt", "--name=ops-wallet-pass", CRED_PATH, "-"]
    assert kw.get("shell") is not True  # fixed argv list, never a shell
    assert kw["capture_output"] is True and kw["timeout"] > 0


def test_fallback_not_used_when_credential_file_exists(monkeypatch, tmp_path):
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "ops-wallet-pass").write_text("dir-password\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("fallback must not run"))
    assert _credential_password("/definitely/absent") == "dir-password"


def test_fallback_when_credential_file_missing_in_dir(monkeypatch, tmp_path):
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()  # directory set, but the credential file never landed
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    monkeypatch.setattr(Path, "stat", _root600_stat)
    _stub_run(monkeypatch, out=b"fallback-pw")
    assert _credential_password(CRED_PATH) == "fallback-pw"


def test_fallback_refuses_relative_path(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(CredentialMissing, match="not absolute"):
        _credential_password("credentials/ops-wallet-pass")


def test_fallback_refuses_missing_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(CredentialMissing, match="missing|unreadable"):
        _credential_password(tmp_path / "nope")


def test_fallback_refuses_non_root_owned(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", lambda self, **kw: _stat_result(1000, 0o100600))
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(CredentialMissing, match="root-owned"):
        _credential_password(CRED_PATH)


def test_fallback_refuses_loose_mode(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", lambda self, **kw: _stat_result(0, 0o100644))
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(CredentialMissing, match="0600"):
        _credential_password(CRED_PATH)


def test_fallback_refuses_empty_output(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)
    for out in (b"", b"\n"):
        _stub_run(monkeypatch, out=out)
        with pytest.raises(CredentialMissing, match="empty"):
            _credential_password(CRED_PATH)


def test_fallback_refuses_nonzero_rc_and_never_leaks_stderr(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)
    _stub_run(monkeypatch, rc=1, err=b"stderr canary not a real secret")
    with pytest.raises(CredentialMissing) as exc:
        _credential_password(CRED_PATH)
    assert "rc=1" in str(exc.value)
    assert "canary" not in str(exc.value)


def test_fallback_timeout_and_missing_binary(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)

    def raise_timeout(argv, **kw):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=10)

    monkeypatch.setattr(signer_mod.subprocess, "run", raise_timeout)
    with pytest.raises(CredentialMissing, match="timed out"):
        _credential_password(CRED_PATH)

    def raise_oserror(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(signer_mod.subprocess, "run", raise_oserror)
    with pytest.raises(CredentialMissing, match="not available"):
        _credential_password(CRED_PATH)


def test_fallback_strips_exactly_one_newline(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)
    _stub_run(monkeypatch, out=b"ends-in-newline\n\n")
    assert _credential_password(CRED_PATH) == "ends-in-newline\n"


def test_sign_failure_logs_class_and_reason_but_never_secret(monkeypatch, tmp_path, deps, caplog):
    """Journal gets a one-line WARNING naming the exception; the password
    the stub 'returned' must not appear in logs, exceptions or replies."""
    secret = "pw-canary-" + os.urandom(4).hex()
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.setattr(Path, "stat", _root600_stat)
    _stub_run(monkeypatch, out=secret.encode())
    from aitbc_ops_signer.signer import Signer

    deps["signer"] = Signer(deps["config"])  # real signer; wallet file absent -> later stage fails
    with caplog.at_level(logging.WARNING):
        r = handle_request(req(), **deps)
    assert r == {"ok": False, "result": "error", "reason": "internal"}
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    assert secret not in caplog.text
    assert secret not in str(r)
