"""#2457: operator-signed protocol transfers must survive gossip/P2P intake.

``queue_protocol_transfer`` emits BOUNTY_*/agent-STAKE_*/STAKE_UNBOND
envelopes without a top-level signature; the wallet-auth carve (#713)
rejected them all — operator RPC bodies carry no timestamp/nonce — so a
bounty or agent stake submitted to a non-proposing host sat in that host's
local mempool and only sealed when the originator's proposer slot came
around. The operator variant re-verifies the same ``payload.auth``
evidence: the signer must be this host's ``AGENT_ECONOMICS_OPERATOR_ADDRESS``
(the env every fleet validator shares), the signed body must bind the
transfer via ``_payload_auth_binds_transfer``, and the escrow leg must be
the canonical one for the type. Types whose payee/amount are resolved
server-side after signing (BOUNTY_PAYOUT/BOUNTY_REFUND, agent
STAKE_RELEASE) stay local-only — a gossip copy could be re-pointed.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool import compute_tx_hash
from aitbc_chain.protocol_escrow import bounty_escrow_address, stake_escrow_address
from aitbc_chain.rpc.transactions import _drop_sealed_pending, _validate_transaction_admission
from aitbc_chain.rpc.utils import gossip_transaction_drop_reason

CHAIN = "ait-test-2457"
OPERATOR_KEY = keys.PrivateKey(b"\x55" * 32)
OPERATOR = OPERATOR_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\x66" * 32)
USER = USER_KEY.public_key.to_checksum_address()
ATTACKER = keys.PrivateKey(b"\x99" * 32).public_key.to_checksum_address()
STAKE_ESCROW = stake_escrow_address()
BOUNTY_ESCROW = bounty_escrow_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey = OPERATOR_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any], signer: str = OPERATOR, key: keys.PrivateKey = OPERATOR_KEY) -> dict[str, Any]:
    return {"signer": signer, "message": message, "signature": _sign(message, key)}


def _operator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OPERATOR)


def _bounty_lock_tx(**overrides: Any) -> dict[str, Any]:
    message = {
        "bounty_id": "b-1",
        "user_address": USER,
        "reward_amount": 500,
        "auth_nonce": "bn-lock-1",
        "chain_id": CHAIN,
    }
    tx: dict[str, Any] = {
        "from": USER,
        "to": BOUNTY_ESCROW,
        "amount": 500,
        "fee": 0,
        "nonce": 3,
        "type": "BOUNTY_LOCK",
        "payload": {"bounty_id": "b-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _agent_stake_lock_tx(**overrides: Any) -> dict[str, Any]:
    message = {
        "stake_id": "s-1",
        "user_address": USER,
        "amount": 700,
        "auth_nonce": "sn-lock-1",
        "chain_id": CHAIN,
    }
    tx: dict[str, Any] = {
        "from": USER,
        "to": STAKE_ESCROW,
        "amount": 700,
        "fee": 0,
        "nonce": 3,
        "type": "STAKE_LOCK",
        "payload": {"agent_stake_id": "s-1", "lock_days": 30, "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _stake_unbond_tx(**overrides: Any) -> dict[str, Any]:
    message = {"stake_id": "s-1", "user_address": USER, "auth_nonce": "unb-1", "chain_id": CHAIN}
    tx: dict[str, Any] = {
        "from": STAKE_ESCROW,
        "to": STAKE_ESCROW,
        "amount": 700,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_UNBOND",
        "payload": {"agent_stake_id": "s-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


# --- transport pre-filter ---


def test_operator_bounty_lock_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_bounty_lock_tx()) is None


def test_operator_agent_stake_lock_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_agent_stake_lock_tx()) is None


def test_operator_stake_unbond_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_stake_unbond_tx()) is None


def test_operator_types_without_operator_env_dropped(monkeypatch):
    monkeypatch.delenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", raising=False)
    assert gossip_transaction_drop_reason(_bounty_lock_tx()) == "invalid_protocol_auth"


def test_bounty_lock_wrong_escrow_leg_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _bounty_lock_tx(**{"to": ATTACKER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_bounty_lock_amount_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _bounty_lock_tx(amount=999)
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_bounty_lock_bounty_id_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _bounty_lock_tx(payload={"bounty_id": "b-2", "auth": _bounty_lock_tx()["payload"]["auth"]})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_agent_stake_lock_wrong_escrow_leg_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _agent_stake_lock_tx(**{"to": BOUNTY_ESCROW})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_agent_stake_lock_agent_stake_id_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _agent_stake_lock_tx(payload={"agent_stake_id": "s-2", "auth": _agent_stake_lock_tx()["payload"]["auth"]})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_unbond_non_escrow_sender_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _stake_unbond_tx(**{"from": USER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_unbond_split_legs_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _stake_unbond_tx(**{"to": USER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_operator_claim_with_foreign_signature_dropped(monkeypatch):
    """auth.signer naming the operator but signed by another key fails."""
    _operator_env(monkeypatch)
    message = {"bounty_id": "b-1", "user_address": USER, "reward_amount": 500, "auth_nonce": "forged-1", "chain_id": CHAIN}
    forged = _auth(message, signer=OPERATOR, key=USER_KEY)
    tx = _bounty_lock_tx(payload={"bounty_id": "b-1", "auth": forged})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_bounty_payout_unbound_stays_local_only(monkeypatch):
    """Without signed to/amount the payout cannot bind its legs — dropped."""
    _operator_env(monkeypatch)
    message = {"bounty_id": "b-1", "submission_id": "sub-1", "auth_nonce": "po-unb-1", "chain_id": CHAIN}
    tx: dict[str, Any] = {
        "from": BOUNTY_ESCROW,
        "to": USER,
        "amount": 500,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_PAYOUT",
        "payload": {"bounty_id": "b-1", "submission_id": "sub-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_bounty_refund_unbound_stays_local_only(monkeypatch):
    _operator_env(monkeypatch)
    message = {"bounty_id": "b-1", "user_address": USER, "auth_nonce": "re-unb-1", "chain_id": CHAIN}
    tx: dict[str, Any] = {
        "from": BOUNTY_ESCROW,
        "to": USER,
        "amount": 500,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_REFUND",
        "payload": {"bounty_id": "b-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_operator_stake_release_unbound_stays_local_only(monkeypatch):
    """Agent STAKE_RELEASE amount is server-resolved — wallet-auth shape
    required, so an operator body (no nonce/timestamp) cannot ride gossip."""
    _operator_env(monkeypatch)
    message = {"stake_id": "s-1", "user_address": USER, "auth_nonce": "sr-unb-1", "chain_id": CHAIN}
    tx: dict[str, Any] = {
        "from": STAKE_ESCROW,
        "to": USER,
        "amount": 700,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_RELEASE",
        "payload": {
            "agent_stake_id": "s-1",
            "lock_tx_hashes": ["0x" + "ab" * 32],
            "auth": _auth(message),
        },
        "chain_id": CHAIN,
    }
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


# --- admission gate (session-backed) ---


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=3))
        s.add(Account(chain_id=CHAIN, address=STAKE_ESCROW, balance=10**9, nonce=0))
        s.add(Account(chain_id=CHAIN, address=BOUNTY_ESCROW, balance=10**9, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    _operator_env(monkeypatch)

    def submit(tx: dict[str, Any]) -> None:
        _validate_transaction_admission(tx, None)

    return submit


def test_admission_accepts_operator_bounty_lock(door):
    door(_bounty_lock_tx())


def test_admission_accepts_operator_agent_stake_lock(door):
    door(_agent_stake_lock_tx())


def test_admission_accepts_operator_stake_unbond(door):
    door(_stake_unbond_tx())


def test_admission_rejects_repointed_bounty_lock(door):
    with pytest.raises(ValueError):
        door(_bounty_lock_tx(**{"to": ATTACKER}))


def test_admission_rejects_unsigned_protocol_without_auth(door):
    tx = _bounty_lock_tx(payload={"bounty_id": "b-1"})
    with pytest.raises(ValueError, match="no admissible payload.auth"):
        door(tx)


# --- nonce stamping at queue time ---


def test_queue_protocol_transfer_stamps_sender_nonce(monkeypatch):
    """Pending surfaces must show the sender's real nonce, not 0 (#2457)."""
    from aitbc_chain import protocol_escrow

    class _FakeMempool:
        def __init__(self):
            self.added: list[dict] = []

        def add(self, tx, chain_id=None, tx_hash=None):
            self.added.append(tx)
            return "0x" + "cd" * 32

    mempool = _FakeMempool()
    monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mempool)
    monkeypatch.setattr(
        "aitbc_chain.rpc.transactions._queue_peer_fanout",
        lambda chain_id, tx_data: None,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)

    @contextmanager
    def _scope(chain_id=None):
        with Session(engine) as s:
            yield s

    sender = "0x" + "11" * 20
    with Session(engine) as s:
        s.add(Account(chain_id="bc-2", address=sender, balance=10**9, nonce=7))
        s.commit()
    monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)

    protocol_escrow.queue_protocol_transfer(
        sender=sender,
        recipient="0x" + "22" * 20,
        amount=100,
        chain_id="bc-2",
        tx_type="STAKE_LOCK",
        payload={"agent_stake_id": "s-9"},
    )
    assert mempool.added[0]["nonce"] == 7


def test_queue_protocol_transfer_nonce_zero_without_account(monkeypatch):
    """Missing account row keeps the old placeholder — never worse."""
    from aitbc_chain import protocol_escrow

    class _FakeMempool:
        def __init__(self):
            self.added: list[dict] = []

        def add(self, tx, chain_id=None, tx_hash=None):
            self.added.append(tx)
            return "0x" + "ef" * 32

    mempool = _FakeMempool()
    monkeypatch.setattr("aitbc_chain.mempool.get_mempool", lambda: mempool)
    monkeypatch.setattr(
        "aitbc_chain.rpc.transactions._queue_peer_fanout",
        lambda chain_id, tx_data: None,
    )

    def _boom(chain_id=None):
        raise RuntimeError("no db")

    monkeypatch.setattr("aitbc_chain.database.session_scope", _boom)

    protocol_escrow.queue_protocol_transfer(
        sender="0x" + "33" * 20,
        recipient="0x" + "44" * 20,
        amount=100,
        chain_id="bc-2",
        tx_type="BOUNTY_LOCK",
        payload={"bounty_id": "b-9"},
    )
    assert mempool.added[0]["nonce"] == 0


# --- sealed filtering on the pending surface ---


def test_drop_sealed_pending_evicts_and_tags(monkeypatch):
    tx = _bounty_lock_tx()
    sealed_tx = {k: v for k, v in tx.items() if k != "payload"}
    sealed_tx["payload"] = {"bounty_id": "b-1"}
    live_tx = _agent_stake_lock_tx()
    pending = [sealed_tx, live_tx]

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    sealed_hash = compute_tx_hash(sealed_tx)
    with Session(engine) as s:
        s.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=sealed_hash,
                sender=USER,
                recipient=BOUNTY_ESCROW,
                status="confirmed",
                block_height=42,
                type="BOUNTY_LOCK",
            )
        )
        s.commit()

    @contextmanager
    def _scope(chain_id=None):
        with Session(engine) as s:
            yield s

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)

    class _FakeMempool:
        def __init__(self):
            self.reconciled: list[str] = []

        def reconcile_sealed(self, chain_id, hashes):
            self.reconciled.extend(hashes)
            return len(list(hashes))

    mempool = _FakeMempool()
    out = _drop_sealed_pending(CHAIN, mempool, pending)
    assert [t["type"] for t in out] == ["STAKE_LOCK"]
    assert out[0]["state"] == "pending"
    assert sealed_hash in mempool.reconciled


def test_drop_sealed_pending_keeps_unsealed(monkeypatch):
    pending = [_agent_stake_lock_tx()]

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)

    @contextmanager
    def _scope(chain_id=None):
        with Session(engine) as s:
            yield s

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)

    class _FakeMempool:
        def reconcile_sealed(self, chain_id, hashes):
            return 0

    out = _drop_sealed_pending(CHAIN, _FakeMempool(), pending)
    assert len(out) == 1
    assert out[0]["state"] == "pending"
