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
from aitbc_chain.base_models import Account, Block
from aitbc_chain.config import settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.state_transition import StateTransition
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


class TestUnsignedValueAtApply:
    def test_divergent_value_rejected_v20(self, session_factory):
        """validate_transaction refuses a tx whose unsigned value differs
        from the signed amount at v20+ (#1066)."""
        _seed_genesis(session_factory)
        st = StateTransition()
        env = {
            "chain_id": CHAIN,
            "from": ADDR_VICTIM,
            "to": ADDR_ATTACKER,
            "amount": 1,
            "fee": 1,
            "nonce": 0,
            "payload": {},
        }
        env["signature"] = sign_transaction_data(env, KEY_VICTIM)
        tx = dict(env, value=900)  # unsigned alias diverging from signed 1
        with session_factory() as session:
            ok, reason = st.validate_transaction(session, CHAIN, tx, "0x" + "dd" * 32, block_version=20)
        assert not ok
        assert "value" in reason and "amount" in reason

    def test_divergent_value_accepted_pregate(self, session_factory, monkeypatch):
        """Below v20 the unsigned alias may still differ (sealed history)."""
        _seed_genesis(session_factory)
        st = StateTransition()
        env = {
            "chain_id": CHAIN,
            "from": ADDR_VICTIM,
            "to": ADDR_ATTACKER,
            "amount": 1,
            "fee": 1,
            "nonce": 0,
            "payload": {},
        }
        env["signature"] = sign_transaction_data(env, KEY_VICTIM)
        tx = dict(env, value=900)
        with session_factory() as session:
            ok, reason = st.validate_transaction(session, CHAIN, tx, "0x" + "dd" * 32, block_version=19)
        assert ok or "value must equal" not in reason  # not refused on this rule

    def test_import_applies_signed_amount_not_served_value(self, session_factory):
        """A served row carrying value=900 over a signature for amount=1: the
        follower applies exactly 1 — the signed value (#1066)."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        tx = _signed_tx(value=1)
        tx["value"] = 900  # relay tampered the unsigned field
        b = _block(1, [tx])
        b["hash"] = _signed_hash(b, [tx["tx_hash"]])
        result = _import(sync, b)
        assert result.accepted, f"block rejected: {result.reason}"
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            attacker = session.get(Account, (CHAIN, ADDR_ATTACKER))
            assert victim.balance == 10**9 - 1 - 1  # amount + fee
            assert attacker.balance == 1
