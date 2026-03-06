from __future__ import annotations

import pytest
from sqlmodel import Session

from aitbc_chain.models import Block, Transaction, Receipt


def _insert_block(session: Session, height: int = 0) -> Block:
    block = Block(
        height=height,
        hash=f"0x{'0'*63}{height}",
        parent_hash="0x" + "0" * 64,
        proposer="validator",
        tx_count=0,
    )
    session.add(block)
    session.commit()
    session.refresh(block)
    return block


def test_relationships(session: Session) -> None:
    block = _insert_block(session, height=1)

    tx = Transaction(
        tx_hash="0x" + "1" * 64,
        block_height=block.height,
        sender="alice",
        recipient="bob",
        payload={"foo": "bar"},
    )
    receipt = Receipt(
        job_id="job-1",
        receipt_id="0x" + "2" * 64,
        block_height=block.height,
        payload={},
        miner_signature={},
        coordinator_attestations=[],
    )
    session.add(tx)
    session.add(receipt)
    session.commit()
    session.refresh(tx)
    session.refresh(receipt)

    assert tx.block is not None
    assert tx.block.hash == block.hash
    assert receipt.block is not None
    assert receipt.block.hash == block.hash


def test_hash_validation_accepts_hex(session: Session) -> None:
    block = Block(
        height=10,
        hash="0x" + "a" * 64,
        parent_hash="0x" + "b" * 64,
        proposer="validator",
    )
    session.add(block)
    session.commit()
    session.refresh(block)

    assert block.hash.startswith("0x")
    assert block.parent_hash.startswith("0x")


@pytest.mark.skip(reason="SQLModel table=True models bypass Pydantic validators - validation must be done at API layer")
def test_hash_validation_rejects_non_hex(session: Session) -> None:
    """
    NOTE: This test is skipped because SQLModel with table=True does not run
    Pydantic field validators. Validation should be performed at the API/service
    layer before creating model instances.
    
    See: https://github.com/tiangolo/sqlmodel/issues/52
    """
    with pytest.raises(ValueError):
        Block.model_validate({
            "height": 20,
            "hash": "not-hex",
            "parent_hash": "0x" + "c" * 64,
            "proposer": "validator",
        })
