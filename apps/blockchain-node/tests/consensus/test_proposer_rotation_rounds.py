"""Round-aware proposer rotation (v0.25.6).

Before this, select_proposer was a pure function of block height, so a
view change could bump PBFTState.current_view all it liked and the slot
still belonged to the same, unavailable validator. The network produced one
block after the hub went down and then stalled.

The round is now derived from block timestamps: every round_seconds a
height goes without a block hands the slot to the next validator. Both inputs
are on-chain, so all nodes agree without exchanging view-change messages.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aitbc_chain.consensus.multi_validator_poa import (
    MultiValidatorPoA,
    ValidatorRole,
    proposer_round,
)
from aitbc_chain.models import Block

PARENT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)


def _consensus(n: int = 4) -> MultiValidatorPoA:
    consensus = MultiValidatorPoA("test-rounds")
    for i in range(n):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [(0, 0), (1, 0), (119, 0), (120, 1), (241, 2), (600, 5)],
)
def test_round_is_derived_from_elapsed_time(elapsed, expected):
    assert proposer_round(PARENT, PARENT + timedelta(seconds=elapsed), 120) == expected


def test_round_is_zero_without_a_parent_or_when_time_runs_backwards():
    assert proposer_round(None, PARENT, 120) == 0
    assert proposer_round(PARENT, PARENT - timedelta(seconds=300), 120) == 0
    assert proposer_round(PARENT, PARENT + timedelta(seconds=300), 0) == 0


def test_naive_timestamps_are_treated_as_utc():
    naive_parent = PARENT.replace(tzinfo=None)
    assert proposer_round(naive_parent, PARENT + timedelta(seconds=130), 120) == 1


def test_each_round_hands_the_slot_to_the_next_validator():
    consensus = _consensus(4)
    height = 100
    picked = [consensus.select_proposer(height, r) for r in range(4)]
    assert len(set(picked)) == 4, "four rounds must cover four distinct validators"
    assert consensus.select_proposer(height, 4) == picked[0], "round must wrap"


def test_round_zero_is_unchanged_from_the_height_only_schedule():
    consensus = _consensus(4)
    for height in range(20):
        active = sorted(consensus.validators.values(), key=lambda v: v.address)
        assert consensus.select_proposer(height) == active[height % 4].address


@pytest.fixture(autouse=True)
def _round_seconds(monkeypatch):
    """Pin the round length so the offsets below do not track the deployed default."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 120, raising=False)


def _block(height: int, proposer: str, offset_seconds: int) -> Block:
    return Block(
        chain_id="test-rounds",
        height=height,
        hash="0x" + "11" * 32,
        parent_hash="0x" + "00" * 32,
        proposer=proposer,
        timestamp=PARENT + timedelta(seconds=offset_seconds),
        tx_count=0,
        state_root="0x" + "22" * 32,
    )


def test_validate_block_accepts_the_stand_in_after_a_missed_round():
    consensus = _consensus(4)
    consensus._require_block_signatures = False
    height = 100
    standin = consensus.select_proposer(height, 1)

    # 130s after the parent is round 1, which belongs to the stand-in.
    assert consensus.validate_block(_block(height, standin, 130), standin, parent_timestamp=PARENT)


def test_validate_block_rejects_a_proposer_that_jumped_the_queue():
    consensus = _consensus(4)
    consensus._require_block_signatures = False
    height = 100
    standin = consensus.select_proposer(height, 1)

    # The same validator 10s after the parent is still round 0, not its turn.
    assert not consensus.validate_block(_block(height, standin, 10), standin, parent_timestamp=PARENT)


def test_validate_block_without_a_parent_timestamp_keeps_the_old_behaviour():
    consensus = _consensus(4)
    consensus._require_block_signatures = False
    height = 100
    standin = consensus.select_proposer(height, 1)
    assert consensus.validate_block(_block(height, standin, 10), standin)
