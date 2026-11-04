"""#1080 pins: _recover_claimed_attempt must see a PENDING mempool tx (real
entry shape: tx_hash + content{from,to,nonce}), keep the claim while the tx
may be pending, and release only on definitive absence."""

from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "apps/agent-coordinator/src"

GENESIS = "0xgenesis"
RECIP = "0xrecip"
HASH1 = "0x" + "ab" * 32


class _Row:
    transaction_hash = None
    id = "id"


class _Q:
    released: list[bool] = []

    def filter(self, *a):
        return self

    def update(self, vals, **k):
        if vals.get("transaction_hash") is None:
            _Q.released.append(True)
        return 1

    def first(self):
        return types.SimpleNamespace(transaction_hash="x", audit_log="")


class _Sess:
    def query(self, *a):
        return _Q()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _make_client(mempool_entries, sealed_entries):
    class _Client:
        def __init__(self, *a, **k):
            pass

        def get_json(self, url, params=None):
            if url == "/rpc/mempool":
                return {"transactions": mempool_entries}
            if url == "/rpc/transactions":
                return sealed_entries
            raise AssertionError(url)

    return _Client


def _extract_functions(mod):
    """Exec only the helpers under test, verbatim, out of the router file."""
    text = (SRC / "agent_app/routers/coin_requests.py").read_text()
    src_rec = text[text.index("def _compute_attempt_hash") : text.index("def _release_claim(")]
    src_rel = text[text.index("def _release_claim(") :]
    end = src_rel.index("\n\n\n") if "\n\n\n" in src_rel else len(src_rel)
    exec(compile(src_rel[:end] + "\n\n" + src_rec, "coin_requests.py", "exec"), mod.__dict__)


def _load(mempool_entries, sealed_entries):
    _Q.released = []
    net = types.ModuleType("aitbc.network")
    net.AITBCHTTPClient = _make_client(mempool_entries, sealed_entries)
    sys.modules["aitbc.network"] = net
    sys.modules.setdefault("aitbc", types.ModuleType("aitbc"))
    sys.modules.setdefault("aitbc.crypto", types.ModuleType("aitbc.crypto"))
    sig = types.ModuleType("aitbc.crypto.signature_recovery")
    sig.canonical_address = lambda a, *k: a
    sys.modules["aitbc.crypto.signature_recovery"] = sig

    mod = types.ModuleType("cr_under_test")
    mod.__dict__["get_db_session"] = lambda: _Sess()
    mod.__dict__["CoinRequest"] = _Row
    mod.__dict__["logger"] = types.SimpleNamespace(info=print, warning=print, error=print, exception=print)
    _extract_functions(mod)
    return mod, _Q.released


class _TxSvc:
    rpc_url = "http://x"
    genesis_address = GENESIS


def _entry_pending():
    # the real mempool shape: tx_hash + content{from,to,nonce,...}
    return {
        "tx_hash": HASH1,
        "content": {"from": GENESIS, "to": RECIP, "nonce": 7, "amount": 5},
        "received_at": 1.0,
        "fee": 36,
        "size_bytes": 100,
    }


def test_pending_mempool_tx_keeps_and_finalizes():
    mod, released = _load([_entry_pending()], [])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found == HASH1  # recovered the real hash, not released
    assert not released


def test_absent_tx_releases():
    mod, released = _load([], [])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found is None
    assert released


def _entry_sealed(tx_hash=HASH1, nonce=7, sender=GENESIS, recipient=RECIP):
    # the real /rpc/transactions shape: sender/recipient keys, no from/to
    return {"tx_hash": tx_hash, "sender": sender, "recipient": recipient, "nonce": nonce}


def test_sealed_hash_match_finalizes():
    mod, released = _load([], [_entry_sealed()])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found == HASH1
    assert not released


def test_sealed_nonce_match_finalizes():
    mod, released = _load([], [_entry_sealed(tx_hash="0x" + "cd" * 32)])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found == "0x" + "cd" * 32
    assert not released


def test_sealed_wrong_recipient_on_hash_holds():
    mod, released = _load([], [_entry_sealed(recipient="0xother")])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", f"claiming:t:nonce=7:tx={HASH1}", 5, RECIP)
    assert found is None
    assert not released  # claim kept — never release while the tx may be pending


def test_sealed_lowercase_row_vs_checksummed_recipient():
    """The sealed query is case-insensitive; a lower-case row must still match
    a checksummed recipient — else the claim releases and pays twice."""
    lc_recip = "0xaBcD1234"
    mod, released = _load(
        [],
        [
            _entry_sealed(recipient=lc_recip.lower()),
            _entry_sealed(tx_hash="0x" + "ef" * 32, nonce=7, recipient=lc_recip.lower()),
        ],
    )
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, lc_recip)
    assert found in (HASH1, "0x" + "ef" * 32)
    assert not released


def test_sealed_lowercase_row_hash_match_finalizes():
    lc_recip = "0xaBcD1234"
    mod, released = _load([], [_entry_sealed(recipient=lc_recip.lower())])
    mod.__dict__["TransactionService"] = _TxSvc
    found = mod._recover_claimed_attempt("r1", f"claiming:t:nonce=7:tx={HASH1}", 5, lc_recip)
    assert found == HASH1
    assert not released
