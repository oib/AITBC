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


def _load(monkeypatch, mempool_entries, sealed_entries):
    """Load the router module with DB + network layer stubbed."""
    for name in list(sys.modules):
        if "coin_requests" in name:
            del sys.modules[name]

    rows = {}
    released = []

    class _Q:
        def __init__(self, *a, **k):
            pass

        def filter(self, *a):
            return self

        def update(self, vals, **k):
            if vals.get("transaction_hash") is None:
                released.append(True)
            rows.update(vals)
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

    class _Client:
        def __init__(self, *a, **k):
            pass

        def get_json(self, url, params=None):
            if url == "/rpc/mempool":
                return {"transactions": mempool_entries}
            if url == "/rpc/transactions":
                return sealed_entries
            raise AssertionError(url)

    svc = types.ModuleType("aitbc")
    net = types.ModuleType("aitbc.network")
    net.AITBCHTTPClient = _Client
    sys.modules["aitbc.network"] = net
    sys.modules.setdefault("aitbc", svc)

    types.ModuleType("fake_cr")

    # pull the function plus its deps out of the real file
    text = (SRC / "agent_app/routers/coin_requests.py").read_text()
    mod = types.ModuleType("cr_under_test")
    mod.__dict__["get_db_session"] = lambda: _Sess()
    mod.__dict__["CoinRequest"] = types.SimpleNamespace(id="id", transaction_hash="th")
    mod.__dict__["logger"] = types.SimpleNamespace(info=print, warning=print, error=print, exception=print)
    mod.__dict__["sys"] = sys
    mod.__dict__["aitbc"] = svc

    # execute only the two helpers we need verbatim

    src_rec = text[text.index("def _compute_attempt_hash") : text.index("def _release_claim(")]
    src_rel = text[text.index("def _release_claim(") :]
    src_rel = src_rel[: src_rel.index("\n\n\n") if "\n\n\n" in src_rel else len(src_rel)]
    mod.__dict__["sys"].modules["aitbc.network"] = net
    exec(compile(src_rel + "\n\n" + src_rec, "coin_requests.py", "exec"), mod.__dict__)
    return mod, released


def _entry_pending():
    # the real mempool shape: tx_hash + content{from,to,nonce,...}
    return {
        "tx_hash": HASH1,
        "content": {"from": GENESIS, "to": RECIP, "nonce": 7, "amount": 5},
        "received_at": 1.0,
        "fee": 36,
        "size_bytes": 100,
    }


def test_pending_mempool_tx_keeps_and_finalizes(monkeypatch):
    mod, released = _load(monkeypatch, [_entry_pending()], [])

    class TxSvc:
        rpc_url = "http://x"
        genesis_address = GENESIS

    sys.modules["aitbc"].TransactionService = None
    mod.__dict__["TransactionService"] = TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found == HASH1  # recovered the real hash, not released
    assert not released


def test_absent_tx_releases(monkeypatch):
    mod, released = _load(monkeypatch, [], [])

    class TxSvc:
        rpc_url = "http://x"
        genesis_address = GENESIS

    mod.__dict__["TransactionService"] = TxSvc
    found = mod._recover_claimed_attempt("r1", "claiming:t:nonce=7", 5, RECIP)
    assert found is None
    assert released
