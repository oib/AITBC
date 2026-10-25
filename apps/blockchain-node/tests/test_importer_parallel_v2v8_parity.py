"""FORK-PARALLEL-V2V8-1 (#432) — the v2-v8 parallel import path must create the
same account rows as the sequential path and the proposer.

The parallel path (``sync_block_import`` ~L451-L469, gated
``settings.parallel_tx_validation and 2 <= block_version <= 8``) prefetches
every raw ``to`` address and creates a ``balance=0, nonce=0`` row for any
missing one before the pure delta stage. The sequential path and the
proposer's ``apply_transaction`` create a recipient only for ``value > 0``
or a credited type — so a zero-value tx to a fresh address leaves a phantom
row (and a different state root) on the parallel path that the proposer
never produced. bc-2 has no v2-v8 blocks, so only a synthetic fixture can
show it; ``PARALLEL_TX_VALIDATION=true`` is set fleet-wide, so any real
v2-v8 replay takes this path.

Each case applies the tx through ``apply_transaction`` alone (the proposer
shape), imports the same block sequentially, then imports it again on a
fresh fixture with ``parallel_tx_validation`` forced on, and requires all
three to agree on the account set and the stored state root. Cases where
the paths diverge are committed ``xfail(strict=True)`` naming the rows;
v9 cases pin the upper bound of the gate (sequential regardless of the
flag).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.config import settings as chain_settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition, use_account_nonce_override
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

from .test_importer_recipient_precreation import (
    ADDR_A,
    ADDR_B,
    ADDR_BRIDGE,
    ADDR_NEW,
    CHAIN,
    KEY_A,
    T0,
    _accounts,
    _bridge_lock_tx,
    _bridge_release_tx,
    _gpu_market_tx,
    _signed_tx,
)


def _make_db(tmp_path, name: str):
    """fixture_db equivalent for a named subdirectory — one fresh store per
    code path so the sequential and parallel imports start identical."""
    db_path = tmp_path / name / "chain.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=1))
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
        session.add(ChainParameter(chain_id=CHAIN, parameter="bridge_release_authority", value=ADDR_BRIDGE, applied_height=0))
        session.flush()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()
    return engine, factory


def _proposer_result(engine, tx: dict[str, Any], block_version: int, height: int = 1):
    """apply_transaction alone on a dedicated store — the proposer shape.
    Commits so the returned account map, state root and aux fingerprint are
    read from the persisted post-apply state (the v2-era apply path does not
    reliably surface its mutations to a rolled-back session)."""
    st = StateTransition()
    with Session(engine) as session:
        data = dict(tx)
        data.setdefault("value", data.get("amount", 0))
        sender = session.get(Account, (CHAIN, data.get("from", "")))
        if sender is not None and use_account_nonce_override(data, block_version):
            data["nonce"] = sender.nonce
        ok, err = st.apply_transaction(session, CHAIN, data, data["tx_hash"], block_version=block_version, block_height=height)
        assert ok, f"fixture tx must apply on the proposer path at v{block_version}: {err}"
        session.commit()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, block_version)["fingerprint"]
        want = _accounts(session)
    return root, aux, want


def _block_v(height: int, txs: list[dict[str, Any]], state_root: str, aux: str, block_version: int) -> dict[str, Any]:
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
        "block_metadata": f'{{"state_transition_version": {block_version}}}',
        "signature": "",
        "transactions": txs,
    }


def _import(fixture, txs, root, aux, block_version, *, parallel: bool, monkeypatch):
    engine, factory = fixture
    if parallel:
        monkeypatch.setattr(chain_settings, "parallel_tx_validation", True)
    else:
        monkeypatch.setattr(chain_settings, "parallel_tx_validation", False)
    block = _block_v(1, txs, root, aux, block_version)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    return engine, sync.import_block(block, transactions=txs)


def _assert_paths_agree(tmp_path, monkeypatch, tx, block_version):
    """Proposer, sequential import and forced-parallel import must produce
    the same account set and stored state root."""
    tx_seq = dict(tx)
    prop_engine, _ = _make_db(tmp_path, "prop")
    root, aux, want = _proposer_result(prop_engine, tx_seq, block_version)
    seq_engine, seq_factory = _make_db(tmp_path, "seq")
    _, result = _import((seq_engine, seq_factory), [tx_seq], root, aux, block_version, parallel=False, monkeypatch=monkeypatch)
    assert result.accepted, f"v{block_version} sequential import rejected {tx['type']}: {result.reason}"
    with Session(seq_engine) as session:
        assert _accounts(session) == want

    tx_par = dict(tx)
    par_engine, par_factory = _make_db(tmp_path, "par")
    _, result = _import((par_engine, par_factory), [tx_par], root, aux, block_version, parallel=True, monkeypatch=monkeypatch)
    assert result.accepted, f"v{block_version} parallel import rejected {tx['type']}: {result.reason}"
    with Session(par_engine) as session:
        assert _accounts(session) == want
        stored = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert stored.state_root == root


# tx shapes diverging on current main: the parallel prefetch creates a
# phantom recipient row for a zero-value tx to a fresh address, so the
# import's computed state root differs from the proposer-stamped root and
# the block is REJECTED ("State root mismatch") — a dormant 1462-class
# defect. Measured 25 Oct: the phantom row is the tx's `to` address
# (0x0 for GPU_MARKET, ADDR_NEW for MESSAGE); transfer0->new passes both
# paths, so it is not in this set.
_DIVERGENT_CASES = [
    ("gpu_market->0x0", lambda: _gpu_market_tx()),
    (
        "message->new",
        lambda: _signed_tx(KEY_A, ADDR_A, 1, tx_type="MESSAGE", amount=0, to=ADDR_NEW, tx_hash="0x" + "77" * 32),
    ),
]

# tx shapes the parallel path already gets right.
_AGREEING_CASES = [
    (
        "transfer0->new",
        lambda: _signed_tx(KEY_A, ADDR_A, 1, amount=0, to=ADDR_NEW, tx_hash="0x" + "7b" * 32),
    ),
    (
        "transfer->new",
        lambda: _signed_tx(KEY_A, ADDR_A, 1, amount=123, to=ADDR_NEW, tx_hash="0x" + "78" * 32),
    ),
    ("bridge_lock", lambda: _bridge_lock_tx()),
    ("bridge_release", lambda: _bridge_release_tx()),
]

_ALL_CASES = _DIVERGENT_CASES + _AGREEING_CASES


@pytest.mark.parametrize("tx_id,tx_factory", _DIVERGENT_CASES, ids=[c[0] for c in _DIVERGENT_CASES])
@pytest.mark.parametrize("block_version", [2, 5, 8], ids=["v2", "v5", "v8"])
def test_parallel_diverges_on_zero_value_fresh_recipient(tmp_path, monkeypatch, tx_id, tx_factory, block_version):
    """#432 → FORK-GUARD-1: the v2-v8 parallel gate is disabled, so the
    import takes the serial path and agrees with the proposer. Was
    xfail(strict) while parallel was selectable."""
    _assert_paths_agree(tmp_path, monkeypatch, tx_factory(), block_version)


@pytest.mark.parametrize("tx_id,tx_factory", _AGREEING_CASES, ids=[c[0] for c in _AGREEING_CASES])
@pytest.mark.parametrize("block_version", [2, 5, 8], ids=["v2", "v5", "v8"])
def test_parallel_import_matches_sequential_and_proposer(tmp_path, monkeypatch, tx_id, tx_factory, block_version):
    """For these shapes the forced-parallel import must equal the
    sequential import and the proposer's apply — account set and stored
    state root."""
    _assert_paths_agree(tmp_path, monkeypatch, tx_factory(), block_version)


@pytest.mark.parametrize("tx_id,tx_factory", _ALL_CASES, ids=[c[0] for c in _ALL_CASES])
def test_v9_stays_sequential_with_flag_on(tmp_path, monkeypatch, tx_id, tx_factory):
    """Pin on the gate's upper bound: at block_version 9 the parallel flag
    must have no effect — the import takes the sequential path and agrees
    with the proposer."""
    _assert_paths_agree(tmp_path, monkeypatch, tx_factory(), 9)
