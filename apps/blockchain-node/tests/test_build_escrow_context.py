"""S-4: build_escrow_context prefetches per-job lock metadata for the
parallel path.

The pure/parallel compute_state_delta cannot touch the DB; callers that run
v3 blocks in parallel must supply {job_id: {lock_version,
expected_beneficiary, escrow_addr}} for every ESCROW_RELEASE/ESCROW_REFUND in
the batch. A missing lock returns None so the caller keeps the sequential
path, whose own missing-lock rules apply.
"""

import json

from aitbc_chain.base_models import Block, Transaction
from aitbc_chain.state.pure_state_transition import _escrow_address
from aitbc_chain.state.state_transition import build_escrow_context

CHAIN = "test"


def _seed_v3_lock(session, job_id: str, provider: str = "ait1provider") -> None:
    block = Block(
        chain_id=CHAIN,
        height=10,
        hash="0xlockblock" + job_id,
        parent_hash="0x0",
        proposer="ait1proposer",
        block_metadata=json.dumps({"state_transition_version": 3}),
    )
    session.add(block)
    lock = Transaction(
        chain_id=CHAIN,
        tx_hash="0xlock" + job_id,
        block_height=10,
        sender="ait1buyer",
        recipient=_escrow_address(job_id),
        type="ESCROW_LOCK",
        payload={"job_id": job_id, "provider": provider},
        value=100,
    )
    session.add(lock)
    session.commit()


def test_context_for_release_prefetches_lock_metadata(session):
    _seed_v3_lock(session, "job-a")
    release = {
        "from": "ait1buyer",
        "to": "ait1provider",
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-a"},
    }
    ctx = build_escrow_context(session, CHAIN, [release])
    assert ctx is not None
    entry = ctx["job-a"]
    assert entry["lock_version"] == 3
    assert entry["expected_beneficiary"].endswith("provider") or entry["expected_beneficiary"] == "ait1provider"
    assert entry["escrow_addr"] == _escrow_address("job-a")


def test_context_for_refund_targets_buyer(session):
    _seed_v3_lock(session, "job-b")
    refund = {
        "from": "ait1resolver",
        "to": "ait1buyer",
        "type": "ESCROW_REFUND",
        "payload": {"job_id": "job-b"},
    }
    ctx = build_escrow_context(session, CHAIN, [refund])
    assert ctx is not None
    assert ctx["job-b"]["expected_beneficiary"] == "ait1buyer"


def test_missing_lock_returns_none(session):
    release = {
        "from": "ait1buyer",
        "to": "ait1provider",
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "no-such-job"},
    }
    assert build_escrow_context(session, CHAIN, [release]) is None


def test_non_escrow_batch_returns_empty(session):
    transfer = {"from": "ait1a", "to": "ait1b", "type": "TRANSFER", "amount": 1}
    assert build_escrow_context(session, CHAIN, [transfer]) == {}


def test_conflicting_release_and_refund_returns_none(session):
    _seed_v3_lock(session, "job-c")
    batch = [
        {"type": "ESCROW_RELEASE", "payload": {"job_id": "job-c"}},
        {"type": "ESCROW_REFUND", "payload": {"job_id": "job-c"}},
    ]
    assert build_escrow_context(session, CHAIN, batch) is None
