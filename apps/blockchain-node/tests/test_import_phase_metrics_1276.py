"""#1276 pins — ``sync_import_phase_seconds{phase}`` records per-phase timing
inside ``import_block``/``_append_block``.

node1 showed p95 import latency ~10s vs ~0.45s fleet-wide on otherwise-empty
blocks, which pointed at *waiting* rather than compute. The phase histogram
attributes each import to signature_validation / db_health_check /
block_lookup / tx_apply / commit so the outlier can be named from /metrics.

Additive observability only: no control-flow, validation, or commit
behavior may change. These pins assert the series exist and advance on a
real accepted import, on the signature-validation path, and on a
lookup-phase rejection.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block
from aitbc_chain.metrics import sync_import_phase_seconds
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.sync import ChainSync
from aitbc_chain.sync_validator import ProposerSignatureValidator
from aitbc.crypto.crypto import derive_ethereum_address
from sqlmodel import Session, create_engine, select

CHAIN = "import-phase-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
BLOCK_VERSION = 14
KEY_A = "0x" + "11" * 32
ADDR_A = derive_ethereum_address(KEY_A)

PHASES = ("signature_validation", "db_health_check", "block_lookup", "tx_apply", "commit")


def _phase_counts() -> dict[str, float]:
    counts: dict[str, float] = {}
    for metric in sync_import_phase_seconds.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                counts[sample.labels["phase"]] = sample.value
    return counts


@pytest.fixture()
def fixture_db(tmp_path, monkeypatch):
    """File-backed sqlite with genesis (height 0) so height-1 imports append."""
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    from aitbc_chain.metadata import chain_metadata

    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
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


def _roots(engine) -> tuple[str, str]:
    """State root + aux fingerprint over the untouched fixture state — what an
    empty block commits to."""
    with Session(engine) as session:
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, BLOCK_VERSION)["fingerprint"]
    return root, aux


def _empty_block(height: int, parent_hash: str, root: str, aux: str) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": parent_hash,
        "proposer": ADDR_A,
        "timestamp": (T0 + timedelta(seconds=60 * height)).isoformat(),
        "tx_count": 0,
        "state_root": root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {BLOCK_VERSION}}}',
        "signature": "",
        "transactions": [],
    }


def test_accepted_import_records_all_apply_phases(fixture_db):
    """A successful empty-block import must advance db_health_check,
    block_lookup, tx_apply and commit — the four phases on the hot path."""
    engine, factory = fixture_db
    root, aux = _roots(engine)
    block = _empty_block(1, "0x" + "00" * 32, root, aux)
    before = _phase_counts()

    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(block, transactions=[])

    assert result.accepted, f"empty block rejected: {result.reason}"
    after = _phase_counts()
    for phase in ("db_health_check", "block_lookup", "tx_apply", "commit"):
        assert after.get(phase, 0.0) > before.get(phase, 0.0), f"{phase} not observed"
    for phase in PHASES:
        assert phase in after or phase == "signature_validation"


def test_signature_validation_phase_recorded(fixture_db):
    """With signature validation on, the signature_validation series advances
    even when the block is later rejected — the phase boundary sits around
    ``validate_block_signature`` itself."""
    engine, factory = fixture_db

    class _RejectingValidator(ProposerSignatureValidator):
        def validate_block_signature(self, block_data):  # type: ignore[override]
            return (False, "fixture rejection")

    root, aux = _roots(engine)
    block = _empty_block(1, "0x" + "00" * 32, root, aux)
    before = _phase_counts()

    sync = ChainSync(factory, chain_id=CHAIN, validator=_RejectingValidator([]), validate_signatures=True)
    result = sync.import_block(block, transactions=[])

    assert result.accepted is False
    after = _phase_counts()
    assert after.get("signature_validation", 0.0) > before.get("signature_validation", 0.0)


def test_lookup_phase_rejection_still_records(fixture_db):
    """An import that reaches the lookup branch but fails append validation
    (bad state root) still records block_lookup — the metric must not depend
    on the import succeeding."""
    engine, factory = fixture_db
    block = _empty_block(1, "0x" + "00" * 32, "0x" + "ff" * 32, "0x" + "ee" * 32)
    before = _phase_counts()

    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(block, transactions=[])

    assert result.accepted is False
    after = _phase_counts()
    assert after.get("block_lookup", 0.0) > before.get("block_lookup", 0.0)
