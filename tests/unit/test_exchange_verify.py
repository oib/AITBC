"""Tests for scripts/ops/exchange_verify.py (ETH-19 C7 read-only verifier).

Fixture DBs carry only the columns the verifier selects. Chain access is
stubbed: ``_post_rpc``/``_ait_transfers`` are monkeypatched with canned
replies, so no network is touched.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "exchange_verify.py"

BUYER = "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"
SELLER = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
ESCROW = "0x52908400098527886E0F7030069857D2E4169EE7"
BRIDGE = "0x8626f6940E2eb28930eFb4CeF49B2d1F2C9C1199"
SELLER_ETH = "0xdD2FD4581271e230360230F9337D5c0430Bf44C0"


def _load():
    spec = importlib.util.spec_from_file_location("exchange_verify", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["exchange_verify"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _exchange_db(path: Path, *, orders=(), debits=(), deposits=(), trades=(), registry=()) -> Path:
    """orders: (id, side, status, funded_state, backing_tx_hash, locked_ticks,
    user_address, account_nonce, filled_ticks, seller_eth_address)"""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, order_type TEXT, status TEXT, funded_state TEXT,
            backing_tx_hash TEXT, locked_ticks INTEGER, user_address TEXT,
            account_nonce INTEGER, filled_ticks INTEGER, seller_eth_address TEXT,
            amount_ticks INTEGER
        );
        CREATE TABLE prepaid_deposits (
            id INTEGER PRIMARY KEY, node_address TEXT, amount_eth TEXT, eth_tx_hash TEXT UNIQUE
        );
        CREATE TABLE prepaid_debits (
            id INTEGER PRIMARY KEY, node_address TEXT, order_id INTEGER UNIQUE,
            amount_eth TEXT, committed_eth TEXT DEFAULT '0', state TEXT DEFAULT 'open'
        );
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY, amount TEXT, price TEXT, total TEXT,
            buyer_address TEXT, seller_address TEXT, buy_order_id INTEGER, sell_order_id INTEGER,
            settlement_state TEXT, settlement_eth_tx_hash TEXT, settlement_ait_tx_hash TEXT,
            settlement_fee_tx_hash TEXT, fee_ait TEXT
        );
        CREATE TABLE node_registry (
            address TEXT PRIMARY KEY, label TEXT, status TEXT, eth_address TEXT
        );
        """
    )
    for o in orders:
        conn.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(o) + (None,) * (11 - len(o)))
    for d in debits:
        conn.execute(
            "INSERT INTO prepaid_debits (node_address, order_id, amount_eth, committed_eth, state) VALUES (?,?,?,?,?)",
            d,
        )
    for d in deposits:
        conn.execute("INSERT INTO prepaid_deposits (node_address, amount_eth, eth_tx_hash) VALUES (?,?,?)", d)
    for t in trades:
        conn.execute("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", t)
    for r in registry:
        conn.execute("INSERT INTO node_registry VALUES (?,?,?,?)", r)
    conn.commit()
    conn.close()
    return path


def _bridge_db(path: Path, *, prepay_rows=(), marks=(), settlements=()) -> Path:
    """prepay_rows: (tx_hash, recipient_tag, amount_eth); marks: (mark, outcome);
    settlements: (id, kind, ref_id, status[, settle_ait_tx_hash])."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE eth_deposits (
            id TEXT PRIMARY KEY, tx_hash TEXT UNIQUE, from_address TEXT, recipient TEXT,
            amount_eth TEXT, amount_ait TEXT, status TEXT
        );
        CREATE TABLE exchange_monitor_marks (mark TEXT PRIMARY KEY, detail TEXT, outcome TEXT);
        CREATE TABLE exchange_settlements (
            id TEXT PRIMARY KEY, kind TEXT, ref_id INTEGER, status TEXT, settle_ait_tx_hash TEXT
        );
        """
    )
    for i, (txh, tag, amt) in enumerate(prepay_rows):
        conn.execute(
            "INSERT INTO eth_deposits (id, tx_hash, recipient, amount_eth, status) VALUES (?,?,?,?,'exchange_prepay')",
            (f"dep_{i}", txh, tag, amt),
        )
    for m in marks:
        conn.execute("INSERT INTO exchange_monitor_marks (mark, detail, outcome) VALUES (?,?,?)", (m[0], "", m[1]))
    for s in settlements:
        conn.execute("INSERT INTO exchange_settlements VALUES (?,?,?,?,?)", tuple(s) + (None,) * (5 - len(s)))
    conn.commit()
    conn.close()
    return path


def _findings(tool, db_path, **kwargs):
    """Run the check functions directly; returns list[(severity, scope, msg)]."""
    found = []

    def add(s, sc, m):
        found.append((s, sc, m))

    conn = tool._db(str(db_path))
    try:
        tool.check_db_internal(
            conn, add, settlement_enabled=kwargs.get("settlement", False), bridge_db_path=kwargs.get("bridge_db")
        )
        if "bridge_db" in kwargs:
            tool.check_bridge_db(conn, kwargs["bridge_db"], add)
        if kwargs.get("eth"):
            tool.check_eth_chain(conn, kwargs.get("rpc_url", "http://rpc.test"), kwargs.get("bridge_address"), add)
        if kwargs.get("ait"):
            tool.check_ait_chain(
                conn, kwargs["ait_rpc"], kwargs["escrow_address"], add, bridge_db_path=kwargs.get("bridge_db")
            )
    finally:
        conn.close()
    return found


def _severities(found):
    return [s for s, _sc, _m in found]


# --- DB-internal ------------------------------------------------------------


def test_clean_db_passes(tool, tmp_path):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[
            (1, "BUY", "open", "funded", None, None, BUYER, 1, 0, None),
            (2, "SELL", "open", "funded", "0xlock1", 360_000_000, SELLER, 1, 0, SELLER_ETH),
        ],
        debits=[(BUYER, 1, "0.05", "0", "open")],
        registry=[(SELLER, "n-seller", "registered", SELLER_ETH)],
    )
    found = _findings(tool, db)
    assert "FAIL" not in _severities(found), found


def test_funded_buy_without_debit_fails(tool, tmp_path):
    db = _exchange_db(tmp_path / "ex.db", orders=[(1, "BUY", "open", "funded", None, None, BUYER, 1, 0, None)])
    found = _findings(tool, db)
    assert any(s == "FAIL" and "prepaid_debits" in m for s, _c, m in found)


def test_funded_sell_without_backing_fails(tool, tmp_path):
    db = _exchange_db(tmp_path / "ex.db", orders=[(2, "SELL", "open", "funded", None, None, SELLER, 1, 0, SELLER_ETH)])
    found = _findings(tool, db)
    assert any(s == "FAIL" and "backing_tx_hash" in m for s, _c, m in found)


def test_unfunded_order_with_backing_fails(tool, tmp_path):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "open", "unfunded", "0xstray", None, SELLER, 1, 0, None)],
    )
    found = _findings(tool, db)
    assert any(s == "FAIL" and "backing_tx_hash set" in m for s, _c, m in found)


def test_backing_expired_with_refunded_row_ok(tool, tmp_path):
    """Cancel-after-funding leaves funded_state=backing_expired and keeps
    backing_tx_hash — the refund monitor needs it non-NULL. A terminal
    'refunded' order_refund row accounts for the lock: no FAIL (D4 order 23)."""
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "cancelled", "backing_expired", "0xlock2", 360_000_000, SELLER, 1, 0, SELLER_ETH)],
    )
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "order_refund", 2, "refunded")])
    found = _findings(tool, db, bridge_db=bdb)
    assert "FAIL" not in _severities(found), found


def test_backing_expired_with_pending_refund_ok(tool, tmp_path):
    """A refund still in flight ('refunding') is a live refund path — the
    lock is not stranded."""
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "cancelled", "backing_expired", "0xlock2", 360_000_000, SELLER, 1, 0, SELLER_ETH)],
    )
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "order_refund", 2, "refunding")])
    found = _findings(tool, db, bridge_db=bdb)
    assert "FAIL" not in _severities(found), found


def test_backing_expired_without_refund_row_fails(tool, tmp_path):
    """backing_expired + hash and no order_refund row = stranded lock."""
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "cancelled", "backing_expired", "0xlock2", 360_000_000, SELLER, 1, 0, SELLER_ETH)],
    )
    bdb = _bridge_db(tmp_path / "br.db")
    found = _findings(tool, db, bridge_db=bdb)
    assert any(s == "FAIL" and "stranded lock" in m for s, _c, m in found), found


def test_backing_expired_failed_refund_fails(tool, tmp_path):
    """A 'failed' order_refund row means the refund could not pay — the lock
    is still stranded and must stay a FAIL."""
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "cancelled", "backing_expired", "0xlock2", 360_000_000, SELLER, 1, 0, SELLER_ETH)],
    )
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "order_refund", 2, "failed")])
    found = _findings(tool, db, bridge_db=bdb)
    assert any(s == "FAIL" and "refund row failed" in m for s, _c, m in found), found


def test_backing_expired_no_bridge_db_is_info(tool, tmp_path):
    """Without --bridge-db the refund link cannot be checked — INFO, never
    FAIL (the verifier must not guess at a monitor DB it cannot see)."""
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "cancelled", "backing_expired", "0xlock2", 360_000_000, SELLER, 1, 0, SELLER_ETH)],
    )
    found = _findings(tool, db)
    assert "FAIL" not in _severities(found), found
    assert any(s == "INFO" and "refund link unchecked" in m for s, _c, m in found), found


def _settled_trade_fixture(tmp_path, *, eth_hash="0xeth", ait_hash=None):
    """Orders 24 (SELL) / 25 (BUY) filled at 1 AIT; trade 7 settled — the D2
    shape. trades.settlement_ait_tx_hash stays NULL like the live row."""
    return _exchange_db(
        tmp_path / "ex.db",
        orders=[
            (24, "SELL", "filled", "funded", "0xlock", 360_000_000, SELLER, 1, 100_000_000, SELLER_ETH, 100_000_000),
            (25, "BUY", "filled", "funded", None, None, BUYER, 2, 100_000_000, None),
        ],
        debits=[(BUYER, 25, "0.00011493", "0", "open")],
        trades=[(7, "1", "0.00011493", "0.00011493", BUYER, SELLER, 25, 24, "settled", eth_hash, ait_hash, None, "0")],
    )


def test_settled_trade_hash_in_ledger_row_ok(tool, tmp_path):
    """D2 trade 7: the tape's settlement_ait_tx_hash is NULL but the settled
    ledger row carries it — the hash link is explained, no FAIL."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xait1")])
    found = _findings(tool, db, bridge_db=bdb)
    assert "FAIL" not in _severities(found), found


def test_settled_trade_hash_no_ledger_row_fails(tool, tmp_path):
    """bridge-db readable but no settled row for the trade — the hash is
    genuinely absent, still a FAIL."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db")
    found = _findings(tool, db, bridge_db=bdb)
    assert any(s == "FAIL" and "missing settlement tx hash" in m for s, _c, m in found), found


def test_settled_trade_hash_empty_in_ledger_row_fails(tool, tmp_path):
    """A settled row without settle_ait_tx_hash does not qualify — the hash
    never reached any store."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled")])
    found = _findings(tool, db, bridge_db=bdb)
    assert any(s == "FAIL" and "missing settlement tx hash" in m for s, _c, m in found), found


def test_settled_trade_hash_no_bridge_db_is_info(tool, tmp_path):
    """Without --bridge-db the settlement-hash link cannot be checked —
    INFO, never a guess-FAIL."""
    db = _settled_trade_fixture(tmp_path)
    found = _findings(tool, db)
    assert "FAIL" not in _severities(found), found
    assert any(s == "INFO" and "hash link unchecked" in m for s, _c, m in found), found


def test_settled_trade_missing_eth_hash_still_fails(tool, tmp_path):
    """The ledger fallback covers only the AIT leg — a missing ETH hash is
    still a FAIL even when the AIT hash is explained."""
    db = _settled_trade_fixture(tmp_path, eth_hash=None)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xait1")])
    found = _findings(tool, db, bridge_db=bdb)
    assert any(s == "FAIL" and "missing settlement tx hash" in m for s, _c, m in found), found


def test_settled_trade_with_both_hashes_unaffected(tool, tmp_path):
    """A fully-mirrored settled trade needs no ledger lookup at all."""
    db = _settled_trade_fixture(tmp_path, ait_hash="0xait1")
    found = _findings(tool, db)
    assert "FAIL" not in _severities(found), found


def test_over_committed_debit_fails(tool, tmp_path):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(1, "BUY", "open", "funded", None, None, BUYER, 1, 0, None)],
        debits=[(BUYER, 1, "0.05", "0.06", "open")],
    )
    found = _findings(tool, db)
    assert any(s == "FAIL" and "committed_eth" in m for s, _c, m in found)


def test_duplicate_account_nonce_fails(tool, tmp_path):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[
            (1, "BUY", "open", "unfunded", None, None, BUYER, 3, 0, None),
            (2, "BUY", "open", "unfunded", None, None, BUYER, 3, 0, None),
        ],
    )
    found = _findings(tool, db)
    assert any(s == "FAIL" and "account_nonce" in m for s, _c, m in found)


def test_registered_node_without_eth_address_flag_off_warns(tool, tmp_path):
    """REPO-2: without --settlement the verifier treats the flag as off —
    payout is not yet needed, so a bare registration is a WARN even when
    the node already has orders (the 15 Oct waiver case)."""
    db = _exchange_db(
        tmp_path / "ex.db",
        registry=[(SELLER, "n-s", "registered", None)],
        orders=[(1, "SELL", "open", "unfunded", None, 0, SELLER, 1, 0, None)],
    )
    found = _findings(tool, db)
    assert any(s == "WARN" and "eth_address" in m for s, _c, m in found)
    assert not any(s == "FAIL" and "eth_address" in m for s, _c, m in found)


def test_registered_node_without_eth_address_settlement_no_orders_warns(tool, tmp_path):
    """REPO-2: --settlement on, node registered but no orders yet — payout
    is still not needed → WARN, not FAIL."""
    db = _exchange_db(tmp_path / "ex.db", registry=[(SELLER, "n-s", "registered", None)])
    found = _findings(tool, db, settlement=True)
    assert any(s == "WARN" and "eth_address" in m for s, _c, m in found)
    assert not any(s == "FAIL" and "eth_address" in m for s, _c, m in found)


def test_registered_node_without_eth_address_settlement_with_orders_fails(tool, tmp_path):
    """REPO-2: --settlement on and the node has orders — a seller cannot be
    paid → FAIL."""
    db = _exchange_db(
        tmp_path / "ex.db",
        registry=[(SELLER, "n-s", "registered", None)],
        orders=[(1, "SELL", "open", "unfunded", None, 0, SELLER, 1, 0, None)],
    )
    found = _findings(tool, db, settlement=True)
    assert any(s == "FAIL" and "eth_address" in m for s, _c, m in found)


def test_registered_node_with_eth_address_unaffected(tool, tmp_path):
    """The new rule never fires on a node that did set its payout."""
    db = _exchange_db(
        tmp_path / "ex.db",
        registry=[(SELLER, "n-s", "registered", SELLER_ETH)],
        orders=[(1, "SELL", "open", "unfunded", None, 0, SELLER, 1, 0, None)],
    )
    found = _findings(tool, db, settlement=True)
    assert not any("eth_address" in m for _s, _c, m in found)


def test_pre_phase3_schema_reported_not_crash(tool, tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, order_type TEXT)")
    conn.commit()
    conn.close()
    found = _findings(tool, path)
    assert any(s == "FAIL" and "phase-3" in m for s, _c, m in found)


# --- bridge-db cross-check ---------------------------------------------------


def test_prepay_rows_classified(tool, tmp_path):
    ex = _exchange_db(tmp_path / "ex.db", deposits=[(BUYER, "0.02", "0xcredited1")])
    bridge = _bridge_db(
        tmp_path / "bridge.db",
        prepay_rows=[
            ("0xcredited1", f"EXCHANGE_DEPOSIT:{BUYER}", "0.02"),
            ("0xpending2", f"EXCHANGE_DEPOSIT:{BUYER}", "0.03"),
            ("0xrejected3", "EXCHANGE_DEPOSIT:not-an-addr", "0.01"),
        ],
        marks=[("credit:0xrejected3", "rejected")],
    )
    found = _findings(tool, ex, bridge_db=str(bridge))
    assert "FAIL" not in _severities(found)
    assert any(s == "WARN" and "0xpending2" in m for s, _c, m in found)
    assert any("0xrejected3" in m and "operator" in m for s, _c, m in found)


# --- ETH chain ---------------------------------------------------------------


def _stub_rpc(tool, monkeypatch, replies):
    def fake(rpc_url, method, params, timeout=15.0):
        return replies[(method, params[0])]

    monkeypatch.setattr(tool, "_post_rpc", fake)


def _eth_ok(tx_hash, *, to, value_wei, data=b""):
    return {
        ("eth_getTransactionByHash", tx_hash): {
            "to": to,
            "value": hex(value_wei),
            "input": "0x" + data.hex(),
        },
        ("eth_getTransactionReceipt", tx_hash): {"status": "0x1"},
    }


def test_eth_deposit_verified(tool, tmp_path, monkeypatch):
    db = _exchange_db(tmp_path / "ex.db", deposits=[(BUYER, "0.02", "0xdep1")])
    _stub_rpc(
        tool,
        monkeypatch,
        _eth_ok(
            "0xdep1",
            to=BRIDGE,
            value_wei=20_000_000_000_000_000,
            data=f"EXCHANGE_DEPOSIT:{BUYER}".encode(),
        ),
    )
    found = _findings(tool, db, eth=True, bridge_address=BRIDGE)
    assert "FAIL" not in _severities(found), found


def test_eth_deposit_wrong_value_and_tag_fail(tool, tmp_path, monkeypatch):
    db = _exchange_db(tmp_path / "ex.db", deposits=[(BUYER, "0.02", "0xdep1")])
    _stub_rpc(
        tool,
        monkeypatch,
        _eth_ok("0xdep1", to=BRIDGE, value_wei=1, data=b"random"),
    )
    found = _findings(tool, db, eth=True, bridge_address=BRIDGE)
    assert sum(s == "FAIL" for s, _c, m in found) >= 2  # value + tag


def test_eth_unsealed_is_warn_not_fail(tool, tmp_path, monkeypatch):
    db = _exchange_db(tmp_path / "ex.db", deposits=[(BUYER, "0.02", "0xdep1")])
    _stub_rpc(
        tool,
        monkeypatch,
        {
            ("eth_getTransactionByHash", "0xdep1"): {"to": BRIDGE, "value": hex(int(2e16)), "input": "0x"},
            ("eth_getTransactionReceipt", "0xdep1"): None,
        },
    )
    found = _findings(tool, db, eth=True, bridge_address=BRIDGE)
    assert "FAIL" not in _severities(found)
    assert any(s == "WARN" and "unsealed" in m for s, _c, m in found)


# --- AIT chain -----------------------------------------------------------------


def _ait_stub(tool, monkeypatch, txs):
    monkeypatch.setattr(tool, "_ait_transfers", lambda rpc, addr, timeout=15.0: {t["tx_hash"]: t for t in txs})


def _lock_tx(tx_hash, *, order_id, sender=SELLER, value=400_000_000):
    return {
        "tx_hash": tx_hash,
        "sender": sender,
        "recipient": ESCROW,
        "value": value,
        "payload": {"sell_quote": order_id},
        "block_height": 100,
    }


def _leg_tx(tx_hash, *, recipient=BUYER, value=36_000_000):
    """Escrow → buyer settle leg for trade 7's 1 AIT (amount × UNITS_PER_AIT)."""
    return {
        "tx_hash": tx_hash,
        "sender": ESCROW,
        "recipient": recipient,
        "value": value,
        "payload": {"exs_ref": "exs_1", "reason": "settling"},
        "block_height": 100,
    }


def _ait_leg_errors(found):
    return [m for s, sc, m in found if s == "FAIL" and sc == "ait" and "ait leg" in m]


def test_ait_backing_verified(tool, tmp_path, monkeypatch):
    # 10 AIT lock: 10 * 36e6 = 360_000_000 units; send extra to cover fee.
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "open", "funded", "0xlock1", 360_000_000, SELLER, 1, 0, SELLER_ETH, 1_000_000_000)],
    )
    _ait_stub(tool, monkeypatch, [_lock_tx("0xlock1", order_id=2, value=400_000_000)])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW)
    assert "FAIL" not in _severities(found), found


def test_ait_stranger_lock_fails(tool, tmp_path, monkeypatch):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "open", "funded", "0xlock1", 360_000_000, SELLER, 1, 0, SELLER_ETH, 1_000_000_000)],
    )
    _ait_stub(tool, monkeypatch, [_lock_tx("0xlock1", order_id=2, sender=BUYER)])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW)
    assert any(s == "FAIL" and "owner" in m for s, _c, m in found)


def test_ait_missing_backing_fails(tool, tmp_path, monkeypatch):
    db = _exchange_db(
        tmp_path / "ex.db",
        orders=[(2, "SELL", "open", "funded", "0xabsent", 360_000_000, SELLER, 1, 0, SELLER_ETH, 1_000_000_000)],
    )
    _ait_stub(tool, monkeypatch, [])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW)
    assert any(s == "FAIL" and "not in escrow" in m for s, _c, m in found)


_LOCK_24 = _lock_tx("0xlock", order_id=24)


def test_ait_leg_tape_hash_checked(tool, tmp_path, monkeypatch):
    """Tape-carried hash is checked as today and counted 'from tape'."""
    db = _settled_trade_fixture(tmp_path, ait_hash="0xleg1")
    _ait_stub(tool, monkeypatch, [_LOCK_24, _leg_tx("0xleg1")])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW)
    assert _ait_leg_errors(found) == []
    assert any("1 settlement AIT legs checked (1 from tape, 0 from ledger)" in m for _s, _c, m in found)


def test_ait_leg_ledger_hash_checked(tool, tmp_path, monkeypatch):
    """VERIFY-3: settled trade with empty tape hash takes the leg hash from
    the settled ledger row and checks it against escrow history."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xleg2")])
    _ait_stub(tool, monkeypatch, [_LOCK_24, _leg_tx("0xleg2")])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW, bridge_db=str(bdb))
    assert _ait_leg_errors(found) == []
    assert any("1 settlement AIT legs checked (0 from tape, 1 from ledger)" in m for _s, _c, m in found)


def test_ait_leg_both_hashes_tape_wins(tool, tmp_path, monkeypatch):
    """Tape hash present + ledger hash present — the tape hash is used; the
    ledger hash is never even looked up."""
    db = _settled_trade_fixture(tmp_path, ait_hash="0xtape")
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xledger")])
    _ait_stub(tool, monkeypatch, [_LOCK_24, _leg_tx("0xtape")])  # 0xledger deliberately absent
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW, bridge_db=str(bdb))
    assert _ait_leg_errors(found) == []
    assert any("1 from tape, 0 from ledger" in m for _s, _c, m in found)


def test_ait_leg_neither_hash_skips(tool, tmp_path, monkeypatch):
    """Settled trade with no tape hash and no ledger row: the AIT lane
    skips it (the DB check already FAILs the missing hash — no double
    report)."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db")
    _ait_stub(tool, monkeypatch, [_LOCK_24])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW, bridge_db=str(bdb))
    assert _ait_leg_errors(found) == []
    assert any("0 settlement AIT legs checked (0 from tape, 0 from ledger)" in m for _s, _c, m in found)


def test_ait_leg_ledger_hash_not_in_escrow_fails(tool, tmp_path, monkeypatch):
    """Ledger-carried hash pointing at a tx absent from escrow history is
    the same FAIL a tape hash gets."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xgone")])
    _ait_stub(tool, monkeypatch, [_LOCK_24])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW, bridge_db=str(bdb))
    assert any("0xgone" in m and "not in escrow" in m for m in _ait_leg_errors(found))


def test_ait_leg_ledger_wrong_recipient_fails(tool, tmp_path, monkeypatch):
    """Ledger-carried hash resolving to a leg sent to the wrong address is
    the same FAIL a tape hash gets."""
    db = _settled_trade_fixture(tmp_path)
    bdb = _bridge_db(tmp_path / "br.db", settlements=[("exs_1", "trade", 7, "settled", "0xleg3")])
    _ait_stub(tool, monkeypatch, [_LOCK_24, _leg_tx("0xleg3", recipient=SELLER)])
    found = _findings(tool, db, ait=True, ait_rpc="http://ait.test", escrow_address=ESCROW, bridge_db=str(bdb))
    assert any("!= buyer" in m for m in _ait_leg_errors(found))


# --- read-only guarantee -------------------------------------------------------


def test_db_never_written(tool, tmp_path):
    """mode=ro sqlite means the verifier can run against a live file."""
    db = _exchange_db(tmp_path / "ex.db")
    db.chmod(0o444)
    found = _findings(tool, db)
    assert "FAIL" not in _severities(found)


# --- --db default resolution (CLI-5) -----------------------------------------


def test_service_db_path_default(tool, monkeypatch):
    monkeypatch.delenv("EXCHANGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("AITBC_DATA_DIR", raising=False)
    assert tool._service_db_path() == "/var/lib/aitbc/data/exchange/exchange.db"


def test_service_db_path_aitbc_data_dir(tool, monkeypatch):
    monkeypatch.delenv("EXCHANGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("AITBC_DATA_DIR", "/scratch/aitbc")
    assert tool._service_db_path() == "/scratch/aitbc/data/exchange/exchange.db"


def test_service_db_path_exchange_database_url(tool, monkeypatch):
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", "sqlite:////srv/exchange/ex.db")
    assert tool._service_db_path() == "/srv/exchange/ex.db"


def test_resolve_db_explicit_wins(tool, tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", "sqlite:////nonexistent/x.db")
    db = tmp_path / "ex.db"
    db.write_bytes(b"x")
    assert tool._resolve_db(str(db)) == str(db)


def test_resolve_db_uses_readable_default(tool, tmp_path, monkeypatch):
    db = tmp_path / "data" / "exchange" / "exchange.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"x")
    monkeypatch.delenv("EXCHANGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    assert tool._resolve_db(None) == str(db)


def test_resolve_db_missing_default_errors(tool, tmp_path, monkeypatch):
    monkeypatch.delenv("EXCHANGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as e:
        tool._resolve_db(None)
    assert "--db is required" in str(e.value)


def test_ait_skip_hint_names_enabling_flags(tool, tmp_path, monkeypatch, capsys):
    """main() without --ait-rpc prints a one-line hint explaining how to
    enable the AIT checks (not just 'skipped')."""
    db = _exchange_db(tmp_path / "ex.db")
    monkeypatch.setattr(tool, "check_eth_chain", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["exchange_verify.py", "--db", str(db)])
    rc = tool.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "AIT chain checks skipped" in out
    assert "--ait-rpc" in out and "--escrow-address" in out


def test_main_default_db_roundtrip(tool, tmp_path, monkeypatch, capsys):
    """main() with no --db picks up the service default end-to-end."""
    (tmp_path / "data" / "exchange").mkdir(parents=True)
    _exchange_db(tmp_path / "data" / "exchange" / "exchange.db")
    monkeypatch.delenv("EXCHANGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["exchange_verify.py", "--no-chain"])
    rc = tool.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "OK" in out
