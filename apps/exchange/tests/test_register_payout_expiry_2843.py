"""#2843: exchange_register / exchange_set_payout envelopes must carry
expiry_height and be refused once the chain head passes it — a leaked
signed claim may not stay valid until its nonce is consumed."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin

CHAIN_ID = "ait-localnet"


@pytest.fixture(autouse=True)
def _chain_env(monkeypatch):
    monkeypatch.setenv("EXCHANGE_CHAIN_ID", CHAIN_ID)
    # Sibling test files toggle the signed-orders flag via os.environ — pin it
    # on so a leaked 'false' can't 404 these routes mid-suite.
    monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "true")
    # Register/payout rate-limit buckets are module-global and shared across
    # the whole pytest session — clear them so sibling files can't starve
    # this file's calls.
    buckets = ExchangeMixin.handle_node_register.__globals__.get("_RATE_BUCKETS")
    lock = ExchangeMixin.handle_node_register.__globals__.get("_RATE_LOCK")
    if buckets is not None and lock is not None:
        with lock:
            buckets.clear()


def _sign(envelope, privkey):
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, privkey)


def _handler(head=1000):
    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    h._chain_head_height = MagicMock(return_value=head)
    for name in (
        "handle_node_register",
        "handle_set_payout",
        "_verify_signed_body",
        "_commit_register",
        "_commit_payout",
        "_live_head_if_unexpired",
        "_expected_nonce",
        "_claim_nonce",
        "_registry_status",
    ):
        if hasattr(ExchangeMixin, name):
            attr = getattr(ExchangeMixin, name)
            if name in ("_expected_nonce", "_claim_nonce"):
                setattr(h, name, attr)
            else:
                setattr(h, name, attr.__get__(h, ExchangeMixin))
    return h


@pytest.fixture
def keys():
    acct = Account.create()
    return acct.address, acct.key.hex()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "exchange.db")
    monkeypatch.setenv("EXCHANGE_DATABASE_URL", f"sqlite://{path}")
    from apps.exchange.simple_exchange import db as exchange_db

    exchange_db.init_db()
    return path


def _seed_registered(db_path, address, label="n1"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO node_registry (address, label, status, registered_at) VALUES (?, ?, 'registered', '2026-01-01')",
        (address, label),
    )
    conn.execute("INSERT OR IGNORE INTO order_nonces (address, next_nonce) VALUES (?, 1)", (address,))
    conn.commit()
    conn.close()


def _body(env, privkey, address):
    return {"envelope": env, "signature": _sign(env, privkey), "user_address": address}


def _register_env(address, expiry=2000, nonce=0):
    return {
        "action": "exchange_register",
        "address": address,
        "label": "n1",
        "expiry_height": expiry,
        "account_nonce": nonce,
        "chain_id": CHAIN_ID,
    }


def _payout_env(address, expiry=2000, nonce=1):
    return {
        "action": "exchange_set_payout",
        "eth_address": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
        "expiry_height": expiry,
        "account_nonce": nonce,
        "chain_id": CHAIN_ID,
    }


class TestRegisterExpiry:
    def test_expired_register_envelope_rejected(self, db_path, keys):
        address, privkey = keys
        h = _handler(head=1000)
        env = _register_env(address, expiry=1000)  # <= head
        h._read_json_body = MagicMock(return_value=_body(env, privkey, address))
        with patch("apps.exchange.simple_exchange.handlers.exchange_nodes.get_db_path", return_value=db_path):
            h.handle_node_register()
        assert h.send_json_response.call_args is not None, f"send_error={h.send_error.call_args_list}"
        assert h.send_json_response.call_args[0][0] == {"error": "Register envelope expired"}
        assert h.send_json_response.call_args[1].get("status") == 400

    def test_missing_expiry_field_rejected(self, db_path, keys):
        address, privkey = keys
        h = _handler()
        env = _register_env(address)
        del env["expiry_height"]
        h._read_json_body = MagicMock(return_value=_body(env, privkey, address))
        with patch("apps.exchange.simple_exchange.handlers.exchange_nodes.get_db_path", return_value=db_path):
            h.handle_node_register()
        # envelope field-set check fires before any DB work
        assert h.send_error.called

    def test_live_register_envelope_passes_expiry_gate(self, db_path, keys):
        """expiry > head clears the new gate (registration itself may still
        fail on registry state — the point is it is NOT the expiry 400)."""
        address, privkey = keys
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')", (address, "n1"))
        conn.commit()
        conn.close()
        h = _handler(head=1000)
        env = _register_env(address, expiry=2000)
        h._read_json_body = MagicMock(return_value=_body(env, privkey, address))
        with patch("apps.exchange.simple_exchange.handlers.exchange_nodes.get_db_path", return_value=db_path):
            h.handle_node_register()
        # registered OK (nonce 0 expected) — proves the expiry gate passed
        assert h.send_json_response.called
        assert h.send_json_response.call_args[0][0].get("status") == "registered"


class TestPayoutExpiry:
    def test_expired_payout_envelope_rejected(self, db_path, keys, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        address, privkey = keys
        _seed_registered(db_path, address)
        h = _handler(head=1000)
        env = _payout_env(address, expiry=999)
        h._read_json_body = MagicMock(return_value=_body(env, privkey, address))
        with patch("apps.exchange.simple_exchange.handlers.exchange_nodes.get_db_path", return_value=db_path):
            h.handle_set_payout()
        assert h.send_json_response.call_args[0][0] == {"error": "Payout envelope expired"}
        assert h.send_json_response.call_args[1].get("status") == 400
