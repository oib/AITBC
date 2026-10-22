"""FORK-ESCROW-PHANTOM-1 / issue #381 — the escrow create route must not
write committed ``account`` rows outside a block.

After ``_verify_funding_lock`` succeeded, ``create_escrow`` opened a
``session_scope`` that inserted ``Account(balance=0, nonce=0)`` rows for the
buyer and provider when missing. ``account`` is a committed table: the write
landed on exactly the node that received the RPC call — the broadcast
ESCROW_LOCK is the only fleet-visible artifact — so two nodes with identical
chains but different call history committed different ``account`` tables and
computed different ``state_root`` values for the next block. If the lock
then never sealed (evicted, dropped, re-orged), the phantom row was
permanent: the 1462 phantom-recipient shape, user-reachable at RPC level.

Nothing reads those rows: ``_resolve_chain_account`` explicitly does not
require existence (v0.25.5 — "the block state transition creates recipient
accounts on first credit"), ``_get_account_nonce`` defaults to 0, the buyer
must already exist to have signed and funded the lock, and the provider row
is created inside the block by ``apply_transaction`` when the ESCROW_LOCK
seals. The ``Escrow`` record itself is local bookkeeping — not a committed
table — and stays.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aitbc_chain.contracts.escrow import EscrowManager, EscrowState
from aitbc_chain.base_models import Account
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.mempool import compute_tx_hash
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Escrow
import aitbc_chain.rpc.escrow_routes as escrow_routes
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition
from sqlmodel import Session, create_engine

CHAIN = "escrow-phantom-fixture"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
NODE_WALLET = "0xADC923a0928B8415E666206D3703a870C1d578CE"
JOB_ID = "job-phantom-1462-shape"
AMOUNT = Decimal("1.0")
SETTLEMENT_KEY = "0x2222222222222222222222222222222222222222222222222222222222222222"

# An unrelated next-block transfer: the payer key signs it, payee is a fresh
# address the block apply credits — identical on both nodes.
PAYER_KEY = "0x3333333333333333333333333333333333333333333333333333333333333333"
PAYER = derive_ethereum_address(PAYER_KEY)
PAYEE = derive_ethereum_address("0x" + "44" * 32)  # never seeded


def _engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    return engine


def _scope(engine):
    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    return scope


def _seed_node(engine) -> None:
    """The shared pre-call state: a funded payer, a funded buyer, no provider."""
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=PAYER, balance=10_000, nonce=0))
        session.add(Account(chain_id=CHAIN, address=BUYER, balance=5_000, nonce=1))
        session.commit()


async def _run_create(engine, monkeypatch) -> None:
    """Drive ``create_escrow`` end to end against ``engine`` — the serving
    node's persist block runs inside the monkeypatched ``session_scope``."""
    mgr = EscrowManager()
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", NODE_WALLET)
    monkeypatch.setattr(escrow_routes, "_chain_id", lambda: CHAIN)
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_PRIVATE_KEY", SETTLEMENT_KEY)
    monkeypatch.setattr(escrow_routes, "_GENESIS_WALLET_PRIVATE_KEY", "")
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_ADDRESS", "")
    monkeypatch.setattr(escrow_routes, "get_escrow_manager", lambda: mgr)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes, "session_scope", _scope(engine))

    lock_tx, _ = escrow_routes._build_lock_tx(JOB_ID, BUYER, PROVIDER, AMOUNT, nonce=0)
    lock_tx["signature"] = "0xdeadbeef"
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value=compute_tx_hash(lock_tx)))

    mempool = MagicMock()
    mempool.status_code = 200
    mempool.json.return_value = {"success": True, "transactions": [lock_tx], "count": 1}
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=mempool))

    result = await escrow_routes.create_escrow(
        {"job_id": JOB_ID, "buyer": BUYER, "provider": PROVIDER, "amount": str(AMOUNT), "lock_tx": lock_tx}
    )
    assert result["success"] is True
    contract = next(c for c in mgr.escrow_contracts.values() if c.job_id == JOB_ID)
    assert contract.state is EscrowState.FUNDED


def _apply_next_block(engine) -> None:
    """Apply the identical next block on a node: one plain transfer whose
    recipient is a fresh address — created by the block apply itself."""
    tx: dict[str, Any] = {
        "chain_id": CHAIN,
        "type": "TRANSFER",
        "from": PAYER,
        "to": PAYEE,
        "amount": 100,
        "value": 100,
        "fee": 36,
        "nonce": 0,
        "payload": {},
        "timestamp": int(datetime.now(UTC).timestamp()),
    }
    tx["signature"] = sign_transaction_data(tx, PAYER_KEY)
    tx["tx_hash"] = compute_tx_hash(tx)
    with Session(engine) as session:
        ok, err = StateTransition().apply_transaction(
            session, CHAIN, dict(tx), tx["tx_hash"], block_version=14, block_height=2
        )
        assert ok, err
        session.commit()


async def test_create_escrow_writes_no_account_rows(engine, monkeypatch):
    """The persist block must write only the local ``Escrow`` bookkeeping
    row — never the committed ``account`` table. On the old code this fails:
    a ``balance=0, nonce=0`` provider row appears on the serving node."""
    _seed_node(engine)
    await _run_create(engine, monkeypatch)

    with Session(engine) as session:
        assert session.get(Account, (CHAIN, escrow_routes._to_canonical(PROVIDER))) is None
        # Buyer existed before the call (it signed the lock); unchanged.
        buyer = session.get(Account, (CHAIN, BUYER))
        assert buyer is not None and buyer.balance == 5_000
        # The local record still lands — it is what release/refund reconstruct from.
        record = session.get(Escrow, JOB_ID)
        assert record is not None
        assert record.status == "locked"
        assert record.provider == escrow_routes._to_canonical(PROVIDER)


async def test_two_nodes_equal_roots_after_different_call_history(monkeypatch):
    """Node A served the create call, node B never saw it. Apply the same
    next block on both: the committed account roots must be identical —
    on the old code A carries the phantom provider row and diverges."""
    engine_a, engine_b = _engine(), _engine()
    _seed_node(engine_a)
    _seed_node(engine_b)

    await _run_create(engine_a, monkeypatch)

    _apply_next_block(engine_a)
    _apply_next_block(engine_b)

    with Session(engine_a) as sa, Session(engine_b) as sb:
        root_a = compute_state_root_full(sa, CHAIN)
        root_b = compute_state_root_full(sb, CHAIN)
    assert root_a == root_b
