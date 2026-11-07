"""Regression pin — commit-phase equivocation must be slashable (#1235).

PREPARE-phase equivocation is recorded by ``record_prepare`` →
``detect_byzantine_behavior`` → ``SlashingManager.detect_double_sign`` →
``apply_slashing``. The COMMIT branch of ``handle_incoming_message`` now
records through ``record_commit`` into the same detection path, so a
validator committing two different digests at the same height:round is
slashed identically to prepare-phase equivocation — while identical
retransmits stay deduped and different-round commits stay legal.
"""

from __future__ import annotations

import secrets

import pytest

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus, PBFTMessageType


def _consensus(n: int = 4) -> MultiValidatorPoA:
    c = MultiValidatorPoA("test-commit-equivocation")
    for _ in range(n):
        addr = f"0x{secrets.token_hex(20)}"
        c.add_validator(addr, 1000.0)
        c.validators[addr].role = ValidatorRole.PROPOSER
    return c


def _commit(pbft: PBFTConsensus, sender: str, seq: int, view: int, block_hash: str) -> dict:
    return {
        "message_type": PBFTMessageType.COMMIT.value,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": pbft.get_message_digest(block_hash, seq, view),
        "signature": "",
        "timestamp": 0.0,
        "block_hash": block_hash,
    }


@pytest.mark.asyncio
async def test_commit_equivocation_produces_double_sign_slash():
    """A validator committing two different digests in one round must be
    detected and slashed, exactly as prepare-phase equivocation is."""
    consensus = _consensus()
    byz_addr = f"0x{secrets.token_hex(20)}"
    consensus.add_validator(byz_addr, 1000.0)
    consensus.validators[byz_addr].role = ValidatorRole.PROPOSER
    stake_before = consensus.validators[byz_addr].stake

    pbft = PBFTConsensus(consensus, private_key="", chain_id="test-commit-equivocation")

    for h in ("0x" + "11" * 32, "0x" + "22" * 32):
        await pbft.handle_incoming_message(_commit(pbft, byz_addr, 1, 0, h))

    events = consensus.get_slashing_history()
    double_signs = [e for e in events if e.condition.value == "double_sign"]
    assert double_signs, "commit-phase equivocation recorded no slashing event"
    assert double_signs[0].is_applied
    assert consensus.validators[byz_addr].stake < stake_before


@pytest.mark.asyncio
async def test_commit_dedup_still_holds_for_identical_messages():
    """Control: replaying the SAME commit must stay deduped — the fix must
    not turn honest retransmits into slashing events."""
    consensus = _consensus()
    member = next(iter(consensus.validators))
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test-commit-equivocation")
    msg = _commit(pbft, member, 1, 0, "0x" + "33" * 32)
    await pbft.handle_incoming_message(msg)
    await pbft.handle_incoming_message(msg)
    assert len(pbft.state.committed_messages.get("1:0", [])) == 1
    assert consensus.get_slashing_history() == []


@pytest.mark.asyncio
async def test_commit_different_rounds_do_not_false_positive():
    """Different-round commits for different digests are legal (view
    change) — only same-round equivocation is slashable."""
    consensus = _consensus()
    member = next(iter(consensus.validators))
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test-commit-equivocation")
    await pbft.handle_incoming_message(_commit(pbft, member, 1, 0, "0x" + "44" * 32))
    await pbft.handle_incoming_message(_commit(pbft, member, 1, 1, "0x" + "55" * 32))
    assert consensus.get_slashing_history() == []
