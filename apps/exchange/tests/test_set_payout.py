"""ETH-8 phase 3 (C2): the exchange_set_payout signed verb — a node's ETH
payout address, claimed once and audited. Flag-gated: the route exists only
under EXCHANGE_SETTLEMENT_ENABLED.

Throwaway keys + throwaway DBs only.
"""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from apps.exchange.simple_exchange import db as exchange_db
from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EXCHANGE_CHAIN_ID", "ait-localnet")
    monkeypatch.delenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", raising=False)
    monkeypatch.setenv("EXCHANGE_REGISTER_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_READS_PER_MIN", "100000")
    # Hermetic: real operational addresses must not leak into the blocklist.
    for name in (
        "AIT_SELL_ESCROW",
        "BRIDGE_PAYOUT_ADDRESS",
        "GENESIS_WALLET_ADDRESS",
        "BRIDGE_ETH_ADDRESS",
        "SELL_TREASURY_ADDRESS",
    ):
        monkeypatch.delenv(name, raising=False)
    buckets = ExchangeMixin.handle_node_register.__globals__.get("_RATE_BUCKETS")
    lock = ExchangeMixin.handle_node_register.__globals__.get("_RATE_LOCK")
    if buckets is not None and lock is not None:
        with lock:
            buckets.clear()


@pytest.fixture
def settlement_on(monkeypatch):
    monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite://{path}")
    exchange_db.init_db()
    return path


def _sign(envelope, privkey):
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, privkey)


def _handler():
    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    for name in (
        "handle_node_register",
        "handle_set_payout",
        "handle_exchange_nodes",
        "_commit_register",
        "_commit_payout",
        "_verify_signed_body",
        "_registry_status",
        "_expected_nonce",
        "_claim_nonce",
        "_node_rows",
        "_watchlisted_addresses",
    ):
        if hasattr(ExchangeMixin, name):
            attr = getattr(ExchangeMixin, name)
            if name in ("_expected_nonce", "_claim_nonce", "_watchlisted_addresses"):
                setattr(h, name, attr)
            else:
                setattr(h, name, attr.__get__(h, ExchangeMixin))
    return h


def _register(db_path, address, privkey, label="sellernode", head=None):
    """Seed + run the real signed registration path (nonce 0)."""
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')", (address, label))
    conn.commit()
    conn.close()
    h = _handler()
    env = {
        "action": "exchange_register",
        "address": address,
        "label": label,
        "account_nonce": 0,
        "chain_id": "ait-localnet",
    }
    h._read_json_body = MagicMock(return_value={"envelope": env, "signature": _sign(env, privkey), "user_address": address})
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_node_register()
    assert not h.send_error.called, h.send_error.call_args_list
    return h


def _payout_body(address, privkey, *, eth_address, nonce=1, action="exchange_set_payout", fields_full=True):
    env = {"action": action, "eth_address": eth_address, "account_nonce": nonce, "chain_id": "ait-localnet"}
    return {"envelope": env, "signature": _sign(env, privkey), "user_address": address}


def _set_payout(db_path, h, body):
    h._read_json_body = MagicMock(return_value=body)
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_set_payout()


def _row(db_path, address):
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT eth_address, eth_address_set_at, status FROM node_registry WHERE address = ?", (address,)
    ).fetchone()
    conn.close()
    return row


def _audit(db_path, address):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT old_eth_address, new_eth_address FROM payout_address_audit WHERE address = ? ORDER BY id", (address,)
    ).fetchall()
    conn.close()
    return rows


def test_flag_off_route_404s(db_path):
    """EXCHANGE_SETTLEMENT_ENABLED unset — the route is inert, exactly like an
    unknown path. No row is touched."""
    acct = Account.create()
    h = _register(db_path, acct.address, acct.key.hex())
    _set_payout(db_path, h, _payout_body(acct.address, acct.key.hex(), eth_address=acct.address))
    assert h.send_error.called and h.send_error.call_args[0][0] == 404
    assert _row(db_path, acct.address)[0] is None


def test_happy_path_sets_and_audits(db_path, settlement_on):
    node, payout = Account.create(), Account.create()
    h = _register(db_path, node.address, node.key.hex())
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=payout.address))
    assert not h.send_error.called
    resp = h.send_json_response.call_args[0][0]
    assert resp["status"] == "payout_set" and resp["eth_address"] == payout.address
    assert resp["previous_eth_address"] is None
    eth, set_at, status = _row(db_path, node.address)
    assert eth == payout.address and set_at and status == "registered"
    assert _audit(db_path, node.address) == [(None, payout.address)]


def test_reclaim_records_old_and_new(db_path, settlement_on):
    node, a, b = Account.create(), Account.create(), Account.create()
    h = _register(db_path, node.address, node.key.hex())
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=a.address, nonce=1))
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=b.address, nonce=2))
    assert _row(db_path, node.address)[0] == b.address
    assert _audit(db_path, node.address) == [(None, a.address), (a.address, b.address)]


def test_unregistered_node_refused(db_path, settlement_on):
    acct, payout = Account.create(), Account.create()
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, 'straynode', 'seeded')", (acct.address,))
    conn.commit()
    conn.close()
    h = _handler()
    _set_payout(db_path, h, _payout_body(acct.address, acct.key.hex(), eth_address=payout.address, nonce=0))
    resp = h.send_json_response.call_args[0][0]
    assert h.send_json_response.call_args[1]["status"] == 403 or resp.get("error") == "Node not registered"
    assert _row(db_path, acct.address)[0] is None


def test_lowercase_and_typo_addresses_rejected(db_path, settlement_on):
    node = Account.create()
    h = _register(db_path, node.address, node.key.hex())
    # Known EIP-55 address whose checksum contains uppercase letters —
    # all-lowercase can never satisfy it (no crypto lottery).
    known = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=known.lower()))
    assert h.send_error.called and h.send_error.call_args[0][0] == 400
    # One letter's case flipped: that position can never still satisfy the
    # checksum (deterministic — never a digit no-op).
    bad = known[:5] + known[5].swapcase() + known[6:]
    assert bad != known
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=bad))
    assert h.send_error.called and h.send_error.call_args[0][0] == 400
    assert _row(db_path, node.address)[0] is None


def test_burn_and_operational_addresses_rejected(db_path, settlement_on, monkeypatch):
    """Burn addresses and the hub's own operational accounts can never be a
    payout destination — a typo or hostile claim would strand or loop funds."""
    node = Account.create()
    h = _register(db_path, node.address, node.key.hex())
    # Known EIP-55 strings: zero/dead pass is_checksum_address trivially or
    # famously, so the blocklist (not the checksum) must be what rejects them.
    blocked = [
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dEaD",
    ]
    for name, addr in (
        ("AIT_SELL_ESCROW", "0xCf1719140054AB3fD52ce8aa3128dec9317426E3"),
        ("BRIDGE_PAYOUT_ADDRESS", "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"),
        ("SELL_TREASURY_ADDRESS", Account.create().address),
    ):
        monkeypatch.setenv(name, addr)
        blocked.append(addr)
    for addr in blocked:
        _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=addr))
        assert h.send_error.called and h.send_error.call_args[0][0] == 400, addr
        h.send_error.reset_mock()
    assert _row(db_path, node.address)[0] is None


def test_stale_nonce_refused(db_path, settlement_on):
    node, payout = Account.create(), Account.create()
    h = _register(db_path, node.address, node.key.hex())
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=payout.address, nonce=1))
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=payout.address, nonce=1))
    resp = h.send_json_response.call_args[0][0]
    assert resp.get("error") == "Stale account_nonce"


def test_wrong_action_rejected(db_path, settlement_on):
    node, payout = Account.create(), Account.create()
    h = _register(db_path, node.address, node.key.hex())
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=payout.address, action="exchange_cancel"))
    assert h.send_error.called and h.send_error.call_args[0][0] == 400


def test_other_node_signature_cannot_set(db_path, settlement_on):
    """A payout claim signed by node B for node A's address fails at signature
    verify — the recovered signer is the only claimable address."""
    a, b, payout = Account.create(), Account.create(), Account.create()
    _register(db_path, a.address, a.key.hex())
    _register(db_path, b.address, b.key.hex(), label="othernode")
    h = _handler()
    env = {"action": "exchange_set_payout", "eth_address": payout.address, "account_nonce": 1, "chain_id": "ait-localnet"}
    # user_address says A, signature is B's -> verification fails before DB.
    body = {"envelope": env, "signature": _sign(env, b.key.hex()), "user_address": a.address}
    h._read_json_body = MagicMock(return_value=body)
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_set_payout()
    assert h.send_error.called and h.send_error.call_args[0][0] == 401
    assert _row(db_path, a.address)[0] is None


def test_board_shows_payout_address(db_path, settlement_on):
    node, payout = Account.create(), Account.create()
    h = _register(db_path, node.address, node.key.hex())
    _set_payout(db_path, h, _payout_body(node.address, node.key.hex(), eth_address=payout.address))
    conn = sqlite3.connect(db_path)
    rows = h._node_rows(conn)
    conn.close()
    mine = [r for r in rows if r["label"] == "sellernode"][0]
    assert mine["eth_address"] == payout.address[:6] + "…" + payout.address[-4:]
