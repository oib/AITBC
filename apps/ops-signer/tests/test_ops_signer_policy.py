"""Coverage batch: policy, ledger, audit and signer unit edges.

Complements test_ops_signer.py (which drives handle_request end to end).
Everything stays under tmp_path; throwaway keys are generated at runtime;
nothing touches /etc, /run, /var, the network, or a real wallet.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any, cast

import pytest

from aitbc_ops_signer import signer as signer_mod
from aitbc_ops_signer.audit import audit_line
from aitbc_ops_signer.config import Config
from aitbc_ops_signer.ledger import DailyLedger
from aitbc_ops_signer.policy import (
    PaymentRequest,
    Refused,
    check_amount,
    check_recipient,
    load_allowlist,
    normalize_address,
    parse_request,
)
from aitbc_ops_signer.signer import (
    CredentialMissing,
    _credential_password,
    _load_wallet,
    _private_key,
    build_transfer,
    fetch_nonce,
    resolve_chain_id,
    sign_transaction,
)

PAYEE = "0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4"
payee_lower = "0x" + PAYEE[2:].lower()
SHOP = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


def req(to: str = PAYEE, amount: int = 500, memo: str = "S-10", **kw) -> dict:
    return {"op": "sign_payment", "to": to, "amount_units": amount, "memo": memo, **kw}


# --- normalize_address -------------------------------------------------------


def test_normalize_address_case_and_whitespace():
    assert normalize_address(PAYEE) == payee_lower
    # hex digits may be upper/mixed case; the 0x prefix must stay lowercase
    assert normalize_address("  0x" + PAYEE[2:].upper() + "  ") == payee_lower
    assert normalize_address("0x" + "aB" * 20) == "0x" + "ab" * 20


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "0x" + "ab" * 19,  # 38 hex
        "0x" + "ab" * 21,  # 42 hex
        "0x" + "zz" + "ab" * 19,  # non-hex
        "0X" + "ab" * 20,  # uppercase 0X prefix is not an address
        "ab" * 20,  # missing 0x
        None,
        12345,
        ["0x" + "ab" * 20],
    ],
)
def test_normalize_address_rejects(bad):
    with pytest.raises(Refused) as exc:
        normalize_address(cast(Any, bad))
    assert exc.value.reason == "bad_address"


# --- load_allowlist ----------------------------------------------------------


def test_allowlist_empty_and_comment_only(tmp_path: Path):
    for content in ("", "# only comments\n\n   \n# another\n"):
        f = tmp_path / "allow"
        f.write_text(content)
        assert load_allowlist(f) == frozenset()


def test_allowlist_crlf_and_duplicates(tmp_path: Path):
    f = tmp_path / "allow"
    f.write_bytes(f"{PAYEE}\r\n{payee_lower}\r\n{SHOP} # trailing comment\r\n".encode())
    listing = load_allowlist(f)
    assert listing == frozenset({payee_lower, "0x" + SHOP[2:].lower()})
    assert len(listing) == 2  # case-variant duplicate collapsed


def test_allowlist_unreadable_and_directory(tmp_path: Path):
    with pytest.raises(Refused) as exc:
        load_allowlist(tmp_path / "does-not-exist")
    assert exc.value.reason == "allowlist_unreadable"
    with pytest.raises(Refused) as exc2:
        load_allowlist(tmp_path)  # a directory is not a list file
    assert exc2.value.reason == "allowlist_unreadable"


@pytest.mark.parametrize(
    "lineno, line",
    [
        (1, "not-an-address"),
        (2, "0x" + "ab" * 19),
        (3, "0X" + "ab" * 20),
        (4, "0x" + "ab" * 20 + " extra"),
        (5, "0x" + "gg" + "ab" * 19),
    ],
)
def test_allowlist_malformed_line_number_reported(tmp_path: Path, lineno: int, line: str):
    f = tmp_path / "allow"
    f.write_text(f"{PAYEE}\n" * (lineno - 1) + line + "\n")
    with pytest.raises(Refused) as exc:
        load_allowlist(f)
    assert exc.value.reason == f"allowlist_malformed_line_{lineno}"


# --- parse_request -----------------------------------------------------------


def test_parse_request_accepts_boundary_memos():
    for memo in ("A-1", "S-0001", "ABCDEFGH-9999", "K-4"):
        parsed = parse_request(req(memo=memo))
        assert parsed.memo == memo and parsed.amount_units == 500


@pytest.mark.parametrize(
    "memo",
    [
        "ABCDEFGHI-1",  # 9-letter prefix
        "S-12345",  # 5-digit suffix
        "s-10",  # lowercase
        "S-10 ",  # trailing space
        "S-10\t",
        "S--10",
        "S_10",
        "10-S",
        "",
        "S-10\nX",  # embedded newline is not a task id
        "S-10\r\n",
    ],
)
def test_parse_request_rejects_bad_memos(memo: str):
    with pytest.raises(Refused) as exc:
        parse_request(req(memo=memo))
    assert exc.value.reason == "bad_memo"


def test_memo_trailing_newline_refused():
    """A memo must be exactly a task id — a trailing newline is not one."""
    with pytest.raises(Refused):
        parse_request(req(memo="S-10\n"))


def test_parse_request_memo_type_edges():
    for bad in (None, 10, ["S-10"], {"m": "S-10"}):
        with pytest.raises(Refused) as exc:
            parse_request(req(memo=cast(Any, bad)))
        assert exc.value.reason == "bad_memo"
    # missing memo key entirely
    p = req()
    del p["memo"]
    with pytest.raises(Refused) as exc:
        parse_request(p)
    assert exc.value.reason == "bad_memo"


def test_parse_request_non_dict_and_unknown_op():
    with pytest.raises(Refused) as exc:
        parse_request(cast(Any, ["not", "a", "dict"]))
    assert exc.value.reason == "malformed"
    with pytest.raises(Refused) as exc:
        parse_request(cast(Any, "sign_payment"))
    assert exc.value.reason == "malformed"
    with pytest.raises(Refused) as exc:
        parse_request(req(op="SIGN_PAYMENT"))  # case-sensitive op
    assert exc.value.reason == "unknown_op"
    with pytest.raises(Refused) as exc:
        parse_request(req(op=None))
    assert exc.value.reason == "unknown_op"
    with pytest.raises(Refused) as exc:
        parse_request(req(op=123))
    assert exc.value.reason == "unknown_op"


def test_parse_request_amount_type_edges():
    for bad in (True, False, 1.5, "500", None, [500], {"a": 1}):
        with pytest.raises(Refused) as exc:
            parse_request(req(amount=cast(Any, bad)))
        assert exc.value.reason == "bad_amount"


def test_parse_request_to_type_edges():
    for bad in (None, "", "0x123", 12345, [PAYEE], {"a": PAYEE}):
        with pytest.raises(Refused) as exc:
            parse_request(req(to=cast(Any, bad)))
        assert exc.value.reason == "bad_address"
    # missing 'to' key entirely
    p = req()
    del p["to"]
    with pytest.raises(Refused) as exc:
        parse_request(p)
    assert exc.value.reason == "bad_address"


def test_parse_request_extra_fields_ignored_and_dry_run_coercion():
    parsed = parse_request(req(extra_field="ignored", another=object()))
    assert parsed.to == payee_lower
    # dry_run uses bool(): any truthy value requests a dry run (never signs).
    assert parse_request(req(dry_run="false")).dry_run is True
    assert parse_request(req(dry_run=1)).dry_run is True
    assert parse_request(req()).dry_run is False
    assert parse_request(req(dry_run=False)).dry_run is False


# --- check_amount / check_recipient ------------------------------------------


def _payment(amount: int) -> PaymentRequest:
    return PaymentRequest(to=payee_lower, amount_units=amount, memo="S-10")


def test_check_amount_boundaries():
    check_amount(_payment(1), max_per_tx=1_000)  # smallest valid
    check_amount(_payment(1_000), max_per_tx=1_000)  # exactly the cap passes
    with pytest.raises(Refused) as exc:
        check_amount(_payment(0), max_per_tx=1_000)
    assert exc.value.reason == "bad_amount"
    with pytest.raises(Refused) as exc:
        check_amount(_payment(-1), max_per_tx=1_000)
    assert exc.value.reason == "bad_amount"
    with pytest.raises(Refused) as exc:
        check_amount(_payment(-(2**63)), max_per_tx=1_000)
    assert exc.value.reason == "bad_amount"
    with pytest.raises(Refused) as exc:
        check_amount(_payment(1_001), max_per_tx=1_000)
    assert exc.value.reason == "over_tx_cap"


def test_check_recipient_exact_and_case():
    listing = frozenset({payee_lower})
    check_recipient(_payment(1), listing)  # normalized lowercase matches
    with pytest.raises(Refused) as exc:
        check_recipient(PaymentRequest(to="0x" + "cd" * 20, amount_units=1, memo="S-1"), listing)
    assert exc.value.reason == "not_allowlisted"
    # an empty list refuses everything -- fail closed
    with pytest.raises(Refused):
        check_recipient(_payment(1), frozenset())


# --- DailyLedger --------------------------------------------------------------


def _ledger(tmp_path: Path, name: str = "ledger.db") -> DailyLedger:
    return DailyLedger(tmp_path / name)


def test_ledger_admit_day_cap_boundary(tmp_path: Path):
    led = _ledger(tmp_path)
    kw = {"memo": "S-1", "to_addr": payee_lower, "max_per_day": 1_000}
    assert led.admit(600, **kw) is not None
    # spent(600) + 400 == cap exactly -> admitted (cap is 'not exceed')
    assert led.admit(400, **kw) is not None
    assert led.spent_last_24h() == 1_000
    # one more unit would exceed -> refused, and nothing is recorded
    assert led.admit(1, **kw) is None
    assert led.spent_last_24h() == 1_000


def test_ledger_admit_returns_increasing_ids_and_stores_fields(tmp_path: Path):
    led = _ledger(tmp_path)
    kw = {"memo": "BR-8", "to_addr": payee_lower, "max_per_day": 10_000}
    id1 = led.admit(100, **kw)
    id2 = led.admit(200, **kw)
    assert id1 is not None and id2 is not None and id2 > id1
    row = (
        sqlite3.connect(tmp_path / "ledger.db")
        .execute("SELECT amount_units, memo, to_addr, tx_hash FROM spends WHERE id=?", (id2,))
        .fetchone()
    )
    assert row == (200, "BR-8", payee_lower, None)


def test_ledger_record_tx_hash_and_release(tmp_path: Path):
    led = _ledger(tmp_path)
    kw = {"memo": "K-4", "to_addr": payee_lower, "max_per_day": 1_000}
    row_id = led.admit(500, **kw)
    assert row_id is not None
    led.record_tx_hash(row_id, "0x" + "ab" * 32)
    stored = sqlite3.connect(tmp_path / "ledger.db").execute("SELECT tx_hash FROM spends WHERE id=?", (row_id,)).fetchone()
    assert stored == ("0x" + "ab" * 32,)
    led.release(row_id)
    assert led.spent_last_24h() == 0
    # releasing a non-existent id is a no-op, not an error
    led.release(999_999)
    led.record_tx_hash(999_999, "0x" + "00" * 32)  # no row -> no error


def test_ledger_window_boundary(tmp_path: Path):
    """Rows older than exactly 24h stop counting; the boundary is exclusive."""
    led = _ledger(tmp_path)
    kw = {"memo": "O-9", "to_addr": payee_lower, "max_per_day": 10_000}
    row_id = led.admit(700, **kw)
    assert row_id is not None
    ts = sqlite3.connect(tmp_path / "ledger.db").execute("SELECT ts FROM spends WHERE id=?", (row_id,)).fetchone()[0]
    # now = ts + 86400 -> threshold == ts -> 'ts > threshold' is false -> excluded
    assert led.spent_last_24h(now=ts + 86_400) == 0
    # one second inside the window it still counts
    assert led.spent_last_24h(now=ts + 86_399) == 700


def test_ledger_persists_across_instances(tmp_path: Path):
    "A 'restart' (new DailyLedger on the same file) keeps the rolling spend."
    kw = {"memo": "M-2", "to_addr": payee_lower, "max_per_day": 10_000}
    _ledger(tmp_path).admit(800, **kw)
    assert _ledger(tmp_path).spent_last_24h() == 800


def test_ledger_concurrent_admits_serialize_on_cap(tmp_path: Path):
    """6 threads x 300 units against a 1000 cap: exactly 3 may pass."""
    led = _ledger(tmp_path)
    kw = {"memo": "S-2", "to_addr": payee_lower, "max_per_day": 1_000}
    results: list[int | None] = []
    lock = threading.Lock()

    def go() -> None:
        row = led.admit(300, **kw)
        with lock:
            results.append(row)

    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(not t.is_alive() for t in threads)
    assert sum(1 for r in results if r is not None) == 3
    assert led.spent_last_24h() == 900


# --- audit_line ----------------------------------------------------------------


def test_audit_line_format_and_peer_uid(tmp_path: Path):
    path = tmp_path / "nested" / "audit.log"  # parent dirs are created
    audit_line(
        path,
        memo="S-10",
        to=payee_lower,
        amount_units=500,
        result="signed",
        reason="-",
        tx_hash="0x" + "ab" * 32,
        peer_uid=1001,
    )
    audit_line(path, memo="BR-8", to=payee_lower, amount_units=5, result="refused", reason="not_allowlisted")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert "op=sign_payment" in lines[0] and "memo=S-10" in lines[0]
    assert "to=" + payee_lower in lines[0] and "amount_units=500" in lines[0]
    assert "result=signed" in lines[0] and "tx=0x" + "ab" * 32 in lines[0]
    assert "peer_uid=1001" in lines[0]
    assert "result=refused" in lines[1] and "reason=not_allowlisted" in lines[1]
    assert "peer_uid=-" in lines[1]  # absent uid renders as '-'
    # one physical line per call for well-formed fields
    assert all("\n" not in ln for ln in lines)


# --- signer units ---------------------------------------------------------------


def test_build_transfer_field_set():
    tx = build_transfer(chain_id="c1", sender="0xS", to=payee_lower, amount_units=42, nonce=7, fee_units=3)
    assert tx == {
        "type": "TRANSFER",
        "chain_id": "c1",
        "from": "0xS",
        "to": payee_lower,
        "amount": 42,
        "nonce": 7,
        "fee": 3,
        "payload": {"amount": 42},
    }
    assert "signature" not in tx


def test_sign_transaction_signs_sorted_fields_without_signature():
    key_hex = "11" * 32
    tx = build_transfer(chain_id="c1", sender="0xS", to=payee_lower, amount_units=42, nonce=7, fee_units=3)
    sign_transaction(tx, _private_key({"private_key": "0x" + key_hex}))
    sig = tx["signature"]
    assert isinstance(sig, str) and len(sig) == 130  # 65-byte eth signature, hex
    # a pre-existing signature field is excluded from the signed message:
    # signing a tx that already carries a stale signature gives the same sig.
    tx2 = build_transfer(chain_id="c1", sender="0xS", to=payee_lower, amount_units=42, nonce=7, fee_units=3)
    tx2["signature"] = "ff" * 65
    sign_transaction(tx2, _private_key({"private_key": key_hex}))
    assert tx2["signature"] == sig


def _http_returning(payload: dict) -> Any:
    """Minimal http stub: every GET returns `payload`."""
    from types import SimpleNamespace

    return SimpleNamespace(get=lambda _path: payload)


def test_resolve_chain_id():
    assert resolve_chain_id(_http_returning({"supported_chains": ["aitbc-1"]})) == "aitbc-1"
    with pytest.raises(ValueError, match="cannot resolve"):
        resolve_chain_id(_http_returning({"supported_chains": ["a", "b"]}))
    with pytest.raises(ValueError, match="cannot resolve"):
        resolve_chain_id(_http_returning({"supported_chains": []}))
    with pytest.raises(ValueError, match="cannot resolve"):
        resolve_chain_id(_http_returning({}))


def test_fetch_nonce():
    assert fetch_nonce(_http_returning({"nonce": 7}), "0xS") == 7
    assert fetch_nonce(_http_returning({"nonce": "9"}), "0xS") == 9
    with pytest.raises(ValueError, match="no nonce"):
        fetch_nonce(_http_returning({}), "0xS")
    with pytest.raises(ValueError, match="no nonce"):
        fetch_nonce(_http_returning({"nonce": None}), "0xS")


def test_load_wallet_plaintext_and_missing_key(tmp_path: Path):
    w = tmp_path / "ops.json"
    w.write_text(json.dumps({"address": "0xS", "private_key": "0x" + "22" * 32}))
    data = _load_wallet(w, "pw")
    assert data["private_key"] == "0x" + "22" * 32
    w.write_text(json.dumps({"address": "0xS"}))
    with pytest.raises(ValueError, match="private_key"):
        _load_wallet(w, "pw")
    w.write_text(json.dumps({"private_key": 12345}))
    with pytest.raises(ValueError, match="private_key"):
        _load_wallet(w, "pw")
    w.write_text("{not json")
    with pytest.raises(ValueError):
        _load_wallet(w, "pw")


def test_load_wallet_encrypted_dict_uses_decrypt_value(tmp_path: Path, monkeypatch):
    import aitbc.security.encryption as enc

    seen: dict[str, Any] = {}

    def fake_decrypt(blob: Any, password: str) -> str:
        seen["blob"] = blob
        seen["password"] = password
        return "0x" + "33" * 32

    monkeypatch.setattr(enc, "decrypt_value", fake_decrypt)
    w = tmp_path / "ops.json"
    blob = {"ciphertext": "deadbeef"}
    w.write_text(json.dumps({"address": "0xS", "private_key": blob}))
    data = _load_wallet(w, "s3cret")
    assert seen == {"blob": blob, "password": "s3cret"}
    assert data["private_key"] == "0x" + "33" * 32


def test_private_key_hex_forms():
    key = _private_key({"private_key": "0x" + "44" * 32})
    assert key.public_key.to_checksum_address() == _private_key({"private_key": "44" * 32}).public_key.to_checksum_address()
    with pytest.raises(ValueError):
        _private_key({"private_key": "0xzz"})
    with pytest.raises(ValueError):
        _private_key({"private_key": "abc"})  # odd length
    from eth_utils.exceptions import ValidationError

    with pytest.raises(ValidationError, match="private key length"):
        _private_key({"private_key": "11" * 16})  # valid hex, wrong key size


def test_credential_password_dir_file_is_directory_falls_back(monkeypatch, tmp_path):
    """CREDENTIALS_DIRECTORY set but the entry is a directory -> fallback path."""
    cred_dir = tmp_path / "creds"
    (cred_dir / "ops-wallet-pass").mkdir(parents=True)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    monkeypatch.setattr(Path, "stat", lambda self, **kw: type("S", (), {"st_uid": 0, "st_mode": 0o100600})())
    monkeypatch.setattr(
        signer_mod.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=b"fallback-pw", stderr=b""),
    )
    assert _credential_password("/etc/aitbc/credentials/ops-wallet-pass") == "fallback-pw"


def test_credential_password_empty_dir_file_refuses(monkeypatch, tmp_path):
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "ops-wallet-pass").write_text("\n\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    monkeypatch.setattr(signer_mod.subprocess, "run", lambda *a, **k: pytest.fail("must not spawn"))
    with pytest.raises(CredentialMissing, match="empty"):
        _credential_password("/etc/aitbc/credentials/ops-wallet-pass")


class _FakeHttp:
    """Minimal stand-in for AITBCHTTPClient: scripted get/post."""

    def __init__(self, get_routes: dict[str, Any], post_result: dict[str, Any]) -> None:
        self._get = get_routes
        self._post_result = post_result
        self.posts: list[dict[str, Any]] = []

    def get(self, path: str) -> Any:
        for prefix, value in self._get.items():
            if path.startswith(prefix):
                return value
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, *, json: dict[str, Any]) -> Any:  # noqa: A002 - mirrors client kwarg
        assert path == "/rpc/transaction"
        self.posts.append(json)
        return self._post_result


def test_sign_and_send_happy_path_builds_and_posts_tx(tmp_path: Path, monkeypatch):
    cfg = Config(wallet_path=str(tmp_path / "ops.json"), chain_id="aitbc-test", fee_units=11, rpc_url="http://x")
    http = _FakeHttp({"/rpc/account/": {"nonce": 9}}, {"transaction_hash": "0x" + "cd" * 32})
    monkeypatch.setattr(signer_mod, "_credential_password", lambda _p: "pw")
    monkeypatch.setattr(
        signer_mod,
        "_load_wallet",
        lambda _p, _pw: {"address": "0x" + "aa" * 20, "private_key": "0x" + "55" * 32},
    )
    from aitbc_ops_signer.signer import Signer

    tx_hash = Signer(cfg, http_factory=lambda: http).sign_and_send(to=payee_lower, amount_units=123)
    assert tx_hash == "0x" + "cd" * 32
    assert len(http.posts) == 1
    tx = http.posts[0]
    assert tx["type"] == "TRANSFER" and tx["chain_id"] == "aitbc-test"
    assert tx["from"] == "0x" + "aa" * 20 and tx["to"] == payee_lower
    assert tx["amount"] == 123 and tx["nonce"] == 9 and tx["fee"] == 11
    assert tx["payload"] == {"amount": 123}
    assert isinstance(tx["signature"], str) and len(tx["signature"]) == 130


def test_sign_and_send_missing_hash_is_ambiguous(tmp_path: Path, monkeypatch):
    from aitbc.exceptions import AmbiguousRequestError
    from aitbc_ops_signer.signer import Signer

    cfg = Config(wallet_path=str(tmp_path / "ops.json"), chain_id="c", rpc_url="http://x")
    http = _FakeHttp({"/rpc/account/": {"nonce": 1}}, {"status": "ok"})  # 2xx but no hash
    monkeypatch.setattr(signer_mod, "_credential_password", lambda _p: "pw")
    monkeypatch.setattr(
        signer_mod,
        "_load_wallet",
        lambda _p, _pw: {"address": "0x" + "aa" * 20, "private_key": "0x" + "55" * 32},
    )
    with pytest.raises(AmbiguousRequestError):
        Signer(cfg, http_factory=lambda: http).sign_and_send(to=payee_lower, amount_units=1)


def test_sign_and_send_resolves_chain_id_when_unset(tmp_path: Path, monkeypatch):
    from aitbc_ops_signer.signer import Signer

    cfg = Config(wallet_path=str(tmp_path / "ops.json"), chain_id="", rpc_url="http://x")
    http = _FakeHttp(
        {"/health": {"supported_chains": ["resolved-chain"]}, "/rpc/account/": {"nonce": 4}},
        {"transaction_hash": "0x" + "ef" * 32},
    )
    monkeypatch.setattr(signer_mod, "_credential_password", lambda _p: "pw")
    monkeypatch.setattr(
        signer_mod,
        "_load_wallet",
        lambda _p, _pw: {"address": "0x" + "aa" * 20, "private_key": "0x" + "55" * 32},
    )
    Signer(cfg, http_factory=lambda: http).sign_and_send(to=payee_lower, amount_units=7)
    assert http.posts[0]["chain_id"] == "resolved-chain"
