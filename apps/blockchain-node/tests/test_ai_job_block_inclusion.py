"""AI job end-to-end: a submitted job reaches a block.

Issue #162 was that ``/rpc/ai/submit`` wrote a terminal ``Transaction`` row and
never enqueued the job, so the chain produced 103k empty blocks while a job sat
queued. The submission-to-mempool bug is already fixed and unit-tested; this
suite adds the missing block-inclusion smoke check.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from collections.abc import Generator

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc.utils import ait_to_seconds
from aitbc_chain.base_models import Account, Block, Transaction
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.rpc.ai_services import AI_JOB_TX_TYPE, AI_SERVICE_RECIPIENT

PK_HEX = "4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"
ADDR = keys.PrivateKey(bytes.fromhex(PK_HEX)).public_key.to_checksum_address()


def _sign(tx_data: dict[str, Any]) -> str:
    """Sign the canonical JSON of a tx (minus signature), as the proposer expects."""
    unsigned = {k: v for k, v in tx_data.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(PK_HEX))
    return pk.sign_msg_hash(keccak(message)).to_bytes().hex()


@pytest.fixture
def test_db() -> Generator[Session]:
    """Create an in-memory SQLite database with all chain tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Block.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def session_factory(test_db: Session):
    """Context manager that returns a fresh session bound to the same engine."""
    engine = test_db.get_bind()

    @contextmanager
    def factory() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    return factory


@pytest.fixture
def proposer(session_factory) -> PoAProposer:
    """Create a PoA proposer bound to the test database."""
    config = ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-proposer",
        interval_seconds=1,
        max_txs_per_block=10,
        max_block_size_bytes=1_000_000,
    )
    return PoAProposer(config=config, session_factory=session_factory)


@pytest.fixture
def mempool(monkeypatch) -> InMemoryMempool:
    """Create a fresh in-memory mempool for the test chain."""
    monkeypatch.setattr(settings, "chain_id", "test-chain")
    monkeypatch.setattr(settings, "supported_chains", "test-chain")
    return InMemoryMempool(chain_id="test-chain")


@pytest.mark.asyncio
async def test_ai_job_is_included_in_next_block(
    monkeypatch,
    proposer: PoAProposer,
    session_factory,
    mempool: InMemoryMempool,
) -> None:
    """A valid AI job in the mempool is mined into the next block."""
    from unittest.mock import AsyncMock, patch

    monkeypatch.setattr(settings, "chain_id", "test-chain")
    monkeypatch.setattr(settings, "supported_chains", "test-chain")

    payment = 2.0
    fee = 36
    tx_data: dict[str, Any] = {
        "from": ADDR,
        "to": AI_SERVICE_RECIPIENT,
        "amount": ait_to_seconds(payment),
        "fee": fee,
        "nonce": 0,
        "type": AI_JOB_TX_TYPE,
        "payload": {
            "job_type": "inference",
            "prompt": "hello world",
            "payment": payment,
            "parameters": {},
        },
        "chain_id": "test-chain",
    }
    tx_data["signature"] = _sign(tx_data)

    # Seed sender and AI service accounts so validation passes.
    with session_factory() as session:
        session.add(Account(chain_id="test-chain", address=ADDR, balance=10_000, nonce=0))
        session.add(Account(chain_id="test-chain", address=AI_SERVICE_RECIPIENT, balance=0, nonce=0))
        session.commit()

    tx_hash = mempool.add(tx_data, chain_id="test-chain")

    with (
        patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
        patch("aitbc_chain.consensus.poa.gossip_broker", new=AsyncMock()),
    ):
        result = await proposer._propose_block()

    assert result is True, "proposer should create a block"

    with session_factory() as session:
        block = session.exec(select(Block).where(Block.chain_id == "test-chain").order_by(Block.height.desc())).first()
        assert block is not None
        assert block.tx_count == 1

        tx = session.exec(
            select(Transaction).where(Transaction.chain_id == "test-chain", Transaction.tx_hash == tx_hash)
        ).first()
        assert tx is not None
        assert tx.block_height == block.height
        assert tx.type == AI_JOB_TX_TYPE
        assert tx.status == "confirmed"
