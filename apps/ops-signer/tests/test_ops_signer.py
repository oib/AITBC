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
        _credential_password()
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
