"""COMMITTED-SURFACE-2 regression (#756) — the import-time aux_state_root
check must run compare-only on eras whose committed set includes
node-local-written tables.

``sync_block_import`` recomputes ``committed_fingerprint`` over *live*
local tables. For block_version < 18 the era set includes ``stake``
(queue-time staking RPC + aux sync) and for < 15 also
``edge_node_registration`` (the node's own edge-register RPC): the sealed
digest mixed the sealer's own local rows, which no other node can
reproduce — a verifier carrying its own rows (e.g. aux-synced stake)
mismatched every pre-v18 historical block and stalled replay.

The fix gates strict rejection on ``aux_check_verifiable``: eras whose
set is entirely apply-authored (v18+) still reject on mismatch; volatile
eras compare-and-warn via ``sync_aux_root_unverifiable_total``.

Fixture shape mirrors test_importer_recipient_precreation.py: the
proposer computes roots over clean state, the block is fed to
``ChainSync.import_block``, the follower path.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block, Stake
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.gpu_resources import EdgeNodeRegistration
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "volatile-era-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_A = "0x" + "11" * 32

from aitbc.crypto.crypto import derive_ethereum_address

ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address("0x" + "33" * 32)


@pytest.fixture()
def fixture_db(tmp_path, monkeypatch):
    """A file-backed sqlite DB with genesis + funded sender (nonce 0)."""
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
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
            )
        )
        session.flush()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()
    return engine, factory


def _signed_tx(nonce: int = 0, tx_hash: str = "0x" + "42" * 32) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": ADDR_A,
        "to": ADDR_B,
        "amount": 10,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
        "tx_hash": tx_hash,
    }
    tx["signature"] = sign_transaction_data(tx, KEY_A)
    return tx


def _proposer_roots(engine, txs: list[dict[str, Any]], version: int, height: int = 1) -> tuple[str | None, str]:
    """Apply on clean sealer state (no local volatile rows), read the roots
    the sealed header carries, then roll back."""
    st = StateTransition()
    with Session(engine) as session:
        for tx in txs:
            data = dict(tx)
            data.setdefault("value", data.get("amount", 0))
            ok, err = st.apply_transaction(session, CHAIN, data, data["tx_hash"], block_version=version, block_height=height)
            assert ok, f"fixture tx must apply on the proposer path: {err}"
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, version)["fingerprint"]
        session.rollback()
    return root, aux


def _block(height: int, txs: list[dict[str, Any]], state_root: str | None, aux: str | None, version: int) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_A,
        "timestamp": (T0 + timedelta(seconds=60 * height)).isoformat(),
        "tx_count": len(txs),
        "state_root": state_root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {version}}}',
        "signature": "",
        "transactions": txs,
    }


def _seed_volatile_rows(engine) -> None:
    """The verifier's own node-local rows — the #756 poison."""
    with Session(engine) as session:
        session.add(
            Stake(
                chain_id=CHAIN,
                address=ADDR_A,
                amount=36_000_000,
                locked_until=T0 + timedelta(days=7),
            )
        )
        session.add(
            EdgeNodeRegistration(
                chain_id=CHAIN,
                node_id="edge-local-1",
                endpoint="https://edge.invalid/",
                region="eu",
                gpu_count=1,
                total_vram=80,
                capabilities=[],
                registered_by=ADDR_A,
            )
        )
        session.commit()


def _unverifiable_total() -> float:
    return metrics_registry._counters.get("sync_aux_root_unverifiable_total", 0.0)


def test_v14_block_accepts_despite_local_volatile_rows(fixture_db):
    """#756 poison case: a v14 block sealed while the sealer's stake/edge
    tables were empty must not be rejected just because this node carries
    its own local rows."""
    engine, factory = fixture_db
    txs = [_signed_tx()]
    root, aux = _proposer_roots(engine, txs, 14)
    _seed_volatile_rows(engine)
    before = _unverifiable_total()
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(_block(1, txs, root, aux, 14), transactions=txs)
    assert result.accepted, f"v14 block with local volatile rows must not be rejected: {result.reason}"
    assert _unverifiable_total() == before + 1


def test_v15_block_accepts_despite_local_stake_row(fixture_db):
    """v15 dropped edge_node_registration but kept stake — a local stake row
    still makes the sealed digest unreproducible on this node."""
    engine, factory = fixture_db
    txs = [_signed_tx(tx_hash="0x" + "55" * 32)]
    root, aux = _proposer_roots(engine, txs, 15)
    with Session(engine) as session:
        session.add(Stake(chain_id=CHAIN, address=ADDR_A, amount=36_000_000, locked_until=T0 + timedelta(days=7)))
        session.commit()
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(_block(1, txs, root, aux, 15), transactions=txs)
    assert result.accepted, f"v15 block with a local stake row must not be rejected: {result.reason}"


def test_v18_block_still_rejects_aux_mismatch(fixture_db):
    """Strict rejection is retained where the check is verifiable: a v18
    block stamped with a wrong aux root must not import."""
    engine, factory = fixture_db
    txs = [_signed_tx(tx_hash="0x" + "66" * 32)]
    root, aux = _proposer_roots(engine, txs, 18)
    tampered = aux[:-1] + ("0" if aux[-1] != "0" else "1")
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(_block(1, txs, root, tampered, 18), transactions=txs)
    assert not result.accepted
    assert "Aux state root mismatch" in (result.reason or "")


def test_v18_block_ignores_local_volatile_rows(fixture_db):
    """Sanity the other way: at v18 the volatile tables are out of the set,
    so local rows change nothing — a correctly stamped block imports."""
    engine, factory = fixture_db
    txs = [_signed_tx(tx_hash="0x" + "77" * 32)]
    root, aux = _proposer_roots(engine, txs, 18)
    _seed_volatile_rows(engine)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(_block(1, txs, root, aux, 18), transactions=txs)
    assert result.accepted, f"v18 block must import regardless of volatile rows: {result.reason}"


def test_v14_block_accepts_when_verifier_is_clean(fixture_db):
    """Baseline: the compare-only path must not break matching state."""
    engine, factory = fixture_db
    txs = [_signed_tx(tx_hash="0x" + "88" * 32)]
    root, aux = _proposer_roots(engine, txs, 14)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(_block(1, txs, root, aux, 14), transactions=txs)
    assert result.accepted, f"clean v14 block must import: {result.reason}"
