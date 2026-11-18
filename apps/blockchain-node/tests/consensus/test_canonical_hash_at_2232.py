"""#2232 — the attester's canonical-hash lookup must return the hash, not its first character.

``select(Block.hash)...first()`` yields the bare string in SQLModel; indexing it gave ``"0"``,
so every attest request at or below the local head was refused ``stale_height_rival`` even when
the requested hash was the sealed block. The existing tip-authorization tests stub
``_canonical_hash_at`` and never reached the real query.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block
from sqlmodel import Session, create_engine

CHAIN = "test-chain"
H99 = "0x" + "99" * 32
H100 = "0x" + "aa" * 32
RIVAL = "0x" + "bb" * 32


@pytest.fixture
def svc(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as s:
        s.add(
            Block(chain_id=CHAIN, height=99, hash=H99, parent_hash="0x" + "00" * 32, proposer="p", timestamp=now, tx_count=0)
        )
        s.add(Block(chain_id=CHAIN, height=100, hash=H100, parent_hash=H99, proposer="p", timestamp=now, tx_count=0))
        s.commit()
    service = RemoteAttestationService(CHAIN, {}, session_factory=lambda: Session(engine))
    yield service
    engine.dispose()


def test_canonical_hash_at_returns_the_full_hash(svc):
    assert svc._canonical_hash_at(100) == H100
    assert svc._canonical_hash_at(99) == H99
    assert svc._canonical_hash_at(101) is None


def test_request_for_the_sealed_block_is_authorized(svc):
    """Idempotent re-sign / proof path: the canonical hash at a decided height passes."""
    assert svc._tip_authorizes({"parent_hash": H99}, 100, H100) is None
    assert svc._tip_authorizes({"parent_hash": "0x" + "00" * 32}, 99, H99) is None


def test_rival_hash_at_a_decided_height_is_still_refused(svc):
    assert svc._tip_authorizes({"parent_hash": H99}, 100, RIVAL) == "stale_height_rival"
    assert svc._tip_authorizes({"parent_hash": H99}, 98, RIVAL) == "unknown_height"


def test_tip_extension_and_future_height_unchanged(svc):
    assert svc._tip_authorizes({"parent_hash": H100}, 101, "0x" + "cc" * 32) is None
    assert svc._tip_authorizes({"parent_hash": H99}, 101, "0x" + "cc" * 32) == "parent_mismatch"
    assert svc._tip_authorizes({"parent_hash": H100}, 102, "0x" + "cc" * 32) == "future_height"
