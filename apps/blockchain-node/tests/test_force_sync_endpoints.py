import hashlib
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.rpc import router as rpc_router


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_force_sync_endpoints.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def _session_scope():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rpc_router, "session_scope", _session_scope)
    return engine


@pytest.mark.asyncio
async def test_export_chain_filters_records_by_chain_id(isolated_engine):
    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("chain-a-block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=1,
            )
        )
        session.add(
            Block(
                chain_id="chain-a",
                height=1,
                hash=_hex("chain-a-block-1"),
                parent_hash=_hex("chain-a-block-0"),
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-block-0"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 2),
                tx_count=1,
            )
        )
        session.add(Account(chain_id="chain-a", address="alice", balance=10, nonce=1))
        session.add(Account(chain_id="chain-b", address="mallory", balance=99, nonce=5))
        session.add(
            Transaction(
                chain_id="chain-a",
                tx_hash=_hex("chain-a-tx"),
                block_height=0,
                sender="alice",
                recipient="bob",
                payload={"kind": "payment"},
                value=7,
                fee=1,
                nonce=2,
                status="confirmed",
                timestamp="2026-01-01T00:00:00",
                tx_metadata="meta-a",
            )
        )
        session.add(
            Transaction(
                chain_id="chain-b",
                tx_hash=_hex("chain-b-tx"),
                block_height=0,
                sender="mallory",
                recipient="eve",
                payload={"kind": "payment"},
                value=3,
                fee=1,
                nonce=1,
                status="confirmed",
                timestamp="2026-01-01T00:00:02",
                tx_metadata="meta-b",
            )
        )
        session.commit()

    result = await rpc_router.export_chain(chain_id="chain-a")

    assert result["success"] is True
    assert result["export_data"]["chain_id"] == "chain-a"
    assert [block["height"] for block in result["export_data"]["blocks"]] == [0, 1]
    assert {block["chain_id"] for block in result["export_data"]["blocks"]} == {"chain-a"}
    assert len(result["export_data"]["accounts"]) == 1
    assert len(result["export_data"]["transactions"]) == 1
    assert result["export_data"]["transactions"][0]["tx_hash"] == _hex("chain-a-tx")
    assert result["export_data"]["transactions"][0]["payload"] == {"kind": "payment"}


@pytest.mark.asyncio
async def test_import_chain_dedupes_duplicate_heights_and_preserves_transaction_fields(isolated_engine):
    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("old-chain-a-block"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2025, 12, 31, 23, 59, 59),
                tx_count=0,
            )
        )
        session.add(Account(chain_id="chain-a", address="alice", balance=1, nonce=0))
        session.add(
            Transaction(
                chain_id="chain-a",
                tx_hash=_hex("old-chain-a-tx"),
                block_height=0,
                sender="alice",
                recipient="bob",
                payload={"kind": "payment"},
                value=1,
                fee=1,
                nonce=0,
                status="pending",
                timestamp="2025-12-31T23:59:59",
                tx_metadata="old",
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-existing-block"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.commit()

    import_payload = {
        "chain_id": "chain-a",
        "blocks": [
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("incoming-block-0-old"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:00",
                "tx_count": 0,
            },
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("incoming-block-0-new"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:01",
                "tx_count": 1,
            },
            {
                "chain_id": "chain-a",
                "height": 1,
                "hash": _hex("incoming-block-1"),
                "parent_hash": _hex("incoming-block-0-new"),
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:02",
                "tx_count": 1,
            },
        ],
        "accounts": [
            {"chain_id": "chain-a", "address": "alice", "balance": 25, "nonce": 2}
        ],
        "transactions": [
            {
                "chain_id": "chain-a",
                "tx_hash": _hex("incoming-tx-1"),
                "block_height": 1,
                "sender": "alice",
                "recipient": "bob",
                "payload": {"kind": "payment"},
                "value": 10,
                "fee": 1,
                "nonce": 2,
                "timestamp": "2026-01-02T00:00:02",
                "status": "confirmed",
                "created_at": "2026-01-02T00:00:02",
                "tx_metadata": "new",
            }
        ],
    }

    result = await rpc_router.import_chain(import_payload)

    assert result["success"] is True
    assert result["imported_blocks"] == 2
    assert result["imported_transactions"] == 1

    with Session(isolated_engine) as session:
        chain_a_blocks = session.exec(
            select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)
        ).all()
        chain_b_blocks = session.exec(
            select(Block).where(Block.chain_id == "chain-b").order_by(Block.height)
        ).all()
        chain_a_accounts = session.exec(
            select(Account).where(Account.chain_id == "chain-a")
        ).all()
        chain_a_transactions = session.exec(
            select(Transaction).where(Transaction.chain_id == "chain-a")
        ).all()

    assert [block.height for block in chain_a_blocks] == [0, 1]
    assert chain_a_blocks[0].hash == _hex("incoming-block-0-new")
    assert len(chain_b_blocks) == 1
    assert chain_b_blocks[0].hash == _hex("chain-b-existing-block")
    assert len(chain_a_accounts) == 1
    assert chain_a_accounts[0].balance == 25
    assert len(chain_a_transactions) == 1
    assert chain_a_transactions[0].tx_hash == _hex("incoming-tx-1")
    assert chain_a_transactions[0].timestamp == "2026-01-02T00:00:02"


async def test_import_chain_clears_hash_conflicts_across_chains(isolated_engine):
    """Test that import-chain clears blocks with conflicting hashes across different chains."""
    from aitbc_chain.rpc import router as rpc_router
    from aitbc_chain.database import get_engine

    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("chain-a-block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-a",
                height=1,
                hash=_hex("chain-a-block-1"),
                parent_hash=_hex("chain-a-block-0"),
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-block-0"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=1,
                hash=_hex("chain-b-block-1"),
                parent_hash=_hex("chain-b-block-0"),
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.commit()

    with Session(isolated_engine) as session:
        chain_a_blocks = session.exec(
            select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)
        ).all()

    conflicting_hash = chain_a_blocks[0].hash

    import_payload = {
        "chain_id": "chain-c",
        "blocks": [
            {
                "chain_id": "chain-c",
                "height": 0,
                "hash": conflicting_hash,
                "parent_hash": _hex("parent-0"),
                "proposer": _hex("proposer-0"),
                "timestamp": "2026-01-01T00:00:00",
                "tx_count": 0,
            },
            {
                "chain_id": "chain-c",
                "height": 1,
                "hash": _hex("chain-c-block-1"),
                "parent_hash": conflicting_hash,
                "proposer": _hex("proposer-1"),
                "timestamp": "2026-01-01T00:00:01",
                "tx_count": 0,
            },
        ],
    }

    result = await rpc_router.import_chain(import_payload)

    assert result["success"] is True
    assert result["imported_blocks"] == 2

    with Session(isolated_engine) as session:
        chain_c_blocks = session.exec(
            select(Block).where(Block.chain_id == "chain-c").order_by(Block.height)
        ).all()
        chain_a_blocks_after = session.exec(
            select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)
        ).all()

    assert [block.height for block in chain_c_blocks] == [0, 1]
    assert chain_c_blocks[0].hash == conflicting_hash
    assert len(chain_a_blocks_after) == 1
    assert chain_a_blocks_after[0].height == 1
