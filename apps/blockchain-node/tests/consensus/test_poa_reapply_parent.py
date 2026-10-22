"""FORK-POA-REPAIR-1 — parent-repair must not pre-create recipient accounts.

``PoAProposer._reapply_parent_block`` is the fallback that re-runs a parent
block's transactions when local account state lags the canonical parent root.
It used to ``_ensure_account`` every tx's recipient before re-applying — the
same pre-creation that forked bc-2 at 1462. On a parent carrying a zero-value
tx to a nonexistent recipient (``GPU_MARKET`` offers carry ``to=0x0000…0000``)
the pre-created row entered the trie, so the recomputed root could *never*
equal the parent's recorded root: repair always failed closed on exactly the
blocks it exists to repair, and the phantom row stayed flushed in the session
for an unlucky caller to commit.

The fix mirrors the importer fix (c7c186744): recipients are created solely by
``apply_transaction`` on the paths that credit them, and the re-apply runs
inside a savepoint so a failed repair rolls back cleanly.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block, Transaction
from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition
from aitbc.crypto.crypto import derive_ethereum_address
from sqlmodel import Session, create_engine, select

CHAIN = "poa-repair-fixture"
VERSION = 14
T0 = datetime(2026, 1, 1, tzinfo=UTC)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

KEY_A = "0x" + "11" * 32
ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address("0x" + "33" * 32)


def _signed_tx(nonce: int = 1, tx_type: str = "GPU_MARKET", **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": ADDR_A,
        "to": extra.pop("to", ZERO_ADDRESS),
        "amount": extra.pop("amount", 0),
        "fee": extra.pop("fee", DEFAULT_TX_FEE_UNITS),
        "nonce": nonce,
        "payload": extra.pop("payload", {}),
        "type": tx_type,
        "chain_id": CHAIN,
        "tx_hash": extra.pop("tx_hash", "0x" + "5e" * 32),
        **extra,
    }
    tx["signature"] = sign_transaction_data(tx, KEY_A)
    return tx


def _gpu_market_1462() -> dict[str, Any]:
    """The fork shape: value-0 software offer addressed to the zero account."""
    return _signed_tx(
        nonce=1,
        tx_type="GPU_MARKET",
        amount=0,
        to=ZERO_ADDRESS,
        payload={
            "action": "software_offer",
            "offer_id": "sw_offer_repair_fixture",
            "service_type": "whisper",
            "model": "base",
            "price": 0.02,
            "price_unit": "per_audio_min",
            "provider_address": ADDR_A,
            "provider_node_id": "fixture-node",
            "gpu_name": "FIXTURE GPU",
            "endpoint": "https://fixture.invalid/whisper",
            "status": "active",
        },
    )


def _engine(tmp_path, name: str):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    chain_metadata.create_all(engine)
    return engine


def _seed_lagging(engine, *, include_b: bool = True) -> None:
    """The pre-parent account state: sender at nonce 1 (one earlier tx), no
    zero-address row — exactly the account set a lagging proposer holds."""
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=1))
        if include_b:
            session.add(Account(chain_id=CHAIN, address=ADDR_B, balance=0, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
                block_metadata=json.dumps({"state_transition_version": VERSION}),
            )
        )
        session.commit()


def _parent_block(height: int, state_root: str | None, txs: list[dict[str, Any]]) -> Block:
    return Block(
        chain_id=CHAIN,
        height=height,
        hash="0x" + "42" * 32,
        parent_hash="0x" + "00" * 32,
        proposer=ADDR_A,
        timestamp=T0 + timedelta(seconds=70),
        tx_count=len(txs),
        state_root=state_root,
        block_metadata=json.dumps({"state_transition_version": VERSION}),
        signature="",
    )


def _record_parent(engine, block: Block, txs: list[dict[str, Any]]) -> None:
    with Session(engine) as session:
        session.add(block)
        for tx in txs:
            session.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=tx["tx_hash"],
                    block_height=block.height,
                    sender=tx["from"],
                    recipient=tx["to"],
                    payload=tx["payload"],
                    envelope=dict(tx),
                    type=tx["type"],
                    value=tx["amount"],
                    fee=tx["fee"],
                    nonce=tx["nonce"],
                    status="confirmed",
                )
            )
        session.commit()


def _proposer(engine) -> PoAProposer:
    config = ProposerConfig(
        chain_id=CHAIN,
        proposer_id=ADDR_A,
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return PoAProposer(config=config, session_factory=factory)


def _correct_root(tmp_path, txs: list[dict[str, Any]], *, include_b: bool = True) -> str:
    """The root the canonical parent carries: apply-only, no pre-creation —
    the same semantics the committing proposer used."""
    engine = _engine(tmp_path, "expected.db")
    _seed_lagging(engine, include_b=include_b)
    st = StateTransition()
    with Session(engine) as session:
        for tx in txs:
            data = dict(tx)
            data["value"] = data["amount"]
            ok, err = st.apply_transaction(session, CHAIN, data, data["tx_hash"], block_version=VERSION, block_height=1)
            assert ok, f"fixture tx must apply: {err}"
        session.flush()
        root = compute_state_root_full(session, CHAIN)
    engine.dispose()
    assert root is not None
    return root


def _accounts(engine) -> dict[str, tuple[int, int]]:
    with Session(engine) as session:
        return {
            a.address: (int(a.balance), int(a.nonce))
            for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
        }


def test_repair_parent_with_zero_value_recipient(tmp_path):
    """Parent carries the 1462 shape (GPU_MARKET to 0x0). Old code ensured the
    zero row, so recompute could never match — repair failed. Post-fix it
    converges on the parent's recorded root."""
    tx = _gpu_market_1462()
    root = _correct_root(tmp_path, [tx])

    engine = _engine(tmp_path, "fixture.db")
    _seed_lagging(engine)
    parent = _parent_block(1, root, [tx])
    _record_parent(engine, parent, [tx])

    proposer = _proposer(engine)
    with Session(engine) as session:
        bound = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert proposer._reapply_parent_block(session, bound) is True
        session.commit()

    accounts = _accounts(engine)
    assert ZERO_ADDRESS not in accounts
    assert accounts[ADDR_A] == (10**9 - DEFAULT_TX_FEE_UNITS, 2)


def test_repair_parent_plain_transfer(tmp_path):
    """Regression: a non-zero transfer to a fresh address still repairs —
    the transition creates the recipient itself."""
    tx = _signed_tx(nonce=1, tx_type="TRANSFER", amount=250, to=ADDR_B, tx_hash="0x" + "99" * 32)
    root = _correct_root(tmp_path, [tx], include_b=False)

    engine = _engine(tmp_path, "fixture.db")
    _seed_lagging(engine, include_b=False)
    parent = _parent_block(1, root, [tx])
    _record_parent(engine, parent, [tx])

    proposer = _proposer(engine)
    with Session(engine) as session:
        bound = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert proposer._reapply_parent_block(session, bound) is True
        session.commit()

    accounts = _accounts(engine)
    assert accounts[ADDR_B] == (250, 0)
    assert accounts[ADDR_A] == (10**9 - 250 - DEFAULT_TX_FEE_UNITS, 2)


def test_failed_repair_leaves_no_pending_rows(tmp_path):
    """A repair that cannot converge must roll its savepoint back — no phantom
    recipient or half-applied sender debit may linger in the session."""
    tx = _gpu_market_1462()
    engine = _engine(tmp_path, "fixture.db")
    _seed_lagging(engine)
    # Parent claims a root that re-apply can never reach.
    parent = _parent_block(1, "0x" + "ff" * 32, [tx])
    _record_parent(engine, parent, [tx])

    proposer = _proposer(engine)
    with Session(engine) as session:
        before = _accounts(engine)
        bound = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert proposer._reapply_parent_block(session, bound) is False
        # Same session must be clean of everything the failed repair touched.
        assert session.get(Account, (CHAIN, ZERO_ADDRESS)) is None
        assert _accounts(engine) == before
        sender = session.get(Account, (CHAIN, ADDR_A))
        assert sender is not None and (int(sender.balance), int(sender.nonce)) == (10**9, 1)
