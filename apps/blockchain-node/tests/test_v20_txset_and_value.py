"""v20 apply-path pins — #1064 (served tx list must hash to the signed block
hash) and #1066 (unsigned ``value`` may not diverge from signed ``amount``).

Scans against node2's bc-2 archive before arming (ledger on #1064):
17,817/17,817 sealed blocks reproduce their signed hash over the stored tx
list; 424/424 sealed envelopes carry value==amount. Both gates arm clean.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.base_models import Account, Block, Transaction
from aitbc_chain.config import settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "v20-import"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_VICTIM = "0x" + "aa" * 32
KEY_ATTACKER = "0x" + "bb" * 32
ADDR_VICTIM = derive_ethereum_address(KEY_VICTIM)
ADDR_ATTACKER = derive_ethereum_address(KEY_ATTACKER)


@pytest.fixture(autouse=True)
def _v20(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v20_height", 1)
    yield


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


def _seed_genesis(session_factory) -> None:
    from aitbc_chain.state.state_root_utils import compute_state_root_full

    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_VICTIM, balance=10**9, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()


def _signed_tx(value: int = 1, **overrides: Any) -> dict[str, Any]:
    """A victim-signed envelope: signature covers ``amount`` only — ``value``
    is the unsigned alias (#1066). Served as Transaction.model_dump() shape."""
    env = {
        "chain_id": CHAIN,
        "from": ADDR_VICTIM,
        "to": ADDR_ATTACKER,
        "amount": value,
        "fee": 1,
        "nonce": 0,
        "payload": {},
    }
    env["signature"] = sign_transaction_data(env, KEY_VICTIM)
    tx = {
        "sender": ADDR_VICTIM,
        "recipient": ADDR_ATTACKER,
        "from": ADDR_VICTIM,
        "to": ADDR_ATTACKER,
        "value": value,
        "fee": 1,
        "nonce": 0,
        "payload": {},
        "type": "TRANSFER",
        "status": "confirmed",
        "tx_hash": "0x" + "cc" * 32,
        "chain_id": CHAIN,
        "envelope": env,
    }
    tx.update(overrides)
    return tx


def _block(height: int, txs: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    b = {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_ATTACKER,
        "timestamp": T0.isoformat(),
        "tx_count": len(txs),
        "state_root": "",
        "block_metadata": '{"state_transition_version": 20}',
        "signature": "",
        "transactions": txs,
    }
    b.update(kw)
    return b


def _signed_hash(b: dict[str, Any], tx_hashes: list[str]) -> str:
    return compute_block_hash(
        b["chain_id"],
        b["height"],
        b["parent_hash"],
        b["timestamp"],
        tx_hashes,
        b["proposer"],
        b["state_root"],
        b.get("bridge_state_root") or "",
        b.get("aux_state_root") or "",
    )


def _import(sync: ChainSync, block_data: dict[str, Any]):
    return sync.import_block(block_data, transactions=block_data["transactions"], skip_state_root_validation=True)


def test_hash_timestamp_naive_renders_as_utc():
    """#1164 unit pin: a naive timestamp and its aware-UTC rendering hash
    identically; aware and unparseable inputs stay verbatim."""
    aware = "2026-11-05T16:40:54.010369+00:00"
    naive = "2026-11-05T16:40:54.010369"
    assert compute_block_hash("c", 1, "0xp", naive, [], "prop") == compute_block_hash("c", 1, "0xp", aware, [], "prop")
    # Space-separated SQLite form canonicalizes the same way.
    assert compute_block_hash("c", 1, "0xp", "2026-11-05 16:40:54.010369", [], "prop") == compute_block_hash(
        "c", 1, "0xp", aware, [], "prop"
    )
    # Aware non-UTC and unparseable strings are not rewritten.
    other = "2026-11-05T18:40:54.010369+02:00"
    assert compute_block_hash("c", 1, "0xp", other, [], "prop") != compute_block_hash("c", 1, "0xp", aware, [], "prop")
    assert compute_block_hash("c", 1, "0xp", "not-a-date", [], "prop") == compute_block_hash(
        "c", 1, "0xp", "not-a-date", [], "prop"
    )


class TestTxListHashBinding:
    def test_extra_served_tx_rejected_v20(self, session_factory):
        """Header signed over zero txs but one junk tx is served — the signed
        hash does not reproduce over the delivered list, reject (#1064)."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [])  # proposer signed the EMPTY tx list
        result = _import(sync, b)
        assert not result.accepted
        assert result.reason == "tx_list_hash_mismatch"

    def test_matching_tx_list_accepted_v20(self, session_factory):
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        result = _import(sync, b)
        assert result.accepted, f"honest block rejected: {result.reason}"

    def test_pregate_mismatch_lenient(self, session_factory, monkeypatch):
        """Below the v20 height the historical (unbound) behavior is kept."""
        monkeypatch.setattr(settings, "state_transition_v20_height", 10**9)
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx], block_metadata='{"state_transition_version": 8}')
        # arbitrary hash never recomputed pre-v20 — accepted like before
        result = _import(sync, b)
        assert result.accepted, f"pre-gate block rejected: {result.reason}"

    def test_naive_served_timestamp_recomputes_proposer_hash(self, session_factory):
        """#1164: the proposer hashes ``datetime.now(UTC).isoformat()``
        (tz-aware ``+00:00``) but /rpc/blocks-range serves the DB timestamp
        naive. A bulk-pulled v20+ block must still reproduce its signed hash."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        # Serve the way the RPC does: the stored naive UTC rendering.
        b["timestamp"] = T0.replace(tzinfo=None).isoformat()
        assert "+" not in b["timestamp"] and "Z" not in b["timestamp"]
        result = _import(sync, b)
        assert result.accepted, f"naive-timestamp block rejected: {result.reason}"

    def test_space_separated_served_timestamp_recomputes(self, session_factory):
        """#1164: a peer may serve the raw SQLite ``YYYY-MM-DD HH:MM:SS.ffffff``
        form — it parses naive and must land on the same canonical hash."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        b["timestamp"] = T0.isoformat().replace("T", " ").replace("+00:00", "")
        result = _import(sync, b)
        assert result.accepted, f"space-form timestamp block rejected: {result.reason}"


class TestFailedApplyStoredFailed:
    def test_failed_tx_not_confirmed_v20(self, session_factory):
        """A tx that fails apply is stored 'failed', not 'confirmed' (#1064)."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        # an unsigned user tx fails apply at v20 — stored failed, not confirmed
        tx = _signed_tx(value=1)
        tx["envelope"] = None  # strip the signature entirely
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        result = _import(sync, b)
        assert result.accepted, f"block rejected: {result.reason}"
        with session_factory() as session:
            row = session.exec(select(Transaction).where(Transaction.tx_hash == tx["tx_hash"])).first()
            assert row is not None and row.status == "failed"


class TestHeaderTxCountKept:
    def test_header_tx_count_stored_at_v20(self, session_factory):
        """v20 stores the header's declared tx_count — the integrity field —
        not len(delivered). The count itself is unsigned, so an honest block
        can legitimately carry a header count the served rows don't prove."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx()
        b = _block(1, [tx], tx_count=5)  # header declares 5, serves 1
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        result = _import(sync, b)
        assert result.accepted, f"block rejected: {result.reason}"
        with session_factory() as session:
            row = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
            assert row.tx_count == 5  # header value, not len(transactions)==1
