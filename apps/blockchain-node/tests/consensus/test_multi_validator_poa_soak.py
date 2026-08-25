"""P1.4 — MultiValidatorPoA soak tests.

These tests stress the multi-validator consensus engine with many rounds to
verify that proposer rotation, partition tolerance, and PBFT consensus remain
stable over an extended run. They do not require a live network; they exercise
the in-process engine with flags enabled by ``tests/consensus/conftest.py``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole


def _make_consensus(n_validators: int = 5, chain_id: str = "test-soak") -> MultiValidatorPoA:
    """Create a MultiValidatorPoA with ``n_validators`` active proposers."""
    consensus = MultiValidatorPoA(chain_id)
    for i in range(n_validators):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


def test_round_robin_soak_distribution() -> None:
    """Run 1000 proposer selections and verify round-robin distribution."""
    n = 5
    consensus = _make_consensus(n)
    addresses = [f"0x{i:040x}" for i in range(n)]

    counts = dict.fromkeys(addresses, 0)
    for height in range(1000):
        proposer = consensus.select_proposer(height)
        assert proposer is not None, f"No proposer at height {height}"
        assert proposer in addresses, f"Unexpected proposer {proposer}"
        counts[proposer] += 1

    # Round-robin over 1000 heights with 5 validators -> 200 each
    expected = 1000 // n
    for addr in addresses:
        assert counts[addr] == expected, f"Proposer {addr} expected {expected}, got {counts[addr]}"


def test_proposer_rotation_with_validator_changes() -> None:
    """Soak proposer selection while adding and removing validators mid-run."""
    consensus = _make_consensus(3)
    added_addr = "0xadd0000000000000000000000000000000000000"

    counts_after_add: dict[str, int] = {}
    counts_after_remove: dict[str, int] = {}
    for height in range(500):
        if height == 100:
            consensus.add_validator(added_addr, 1000.0)
            consensus.validators[added_addr].role = ValidatorRole.PROPOSER
        if height == 300:
            consensus.remove_validator("0x0000000000000000000000000000000000000000")

        proposer = consensus.select_proposer(height)
        assert proposer is not None

        if 100 <= height < 300:
            counts_after_add[proposer] = counts_after_add.get(proposer, 0) + 1
        elif height >= 300:
            counts_after_remove[proposer] = counts_after_remove.get(proposer, 0) + 1

    # While 4 validators were active, every selected proposer should be active.
    assert added_addr in counts_after_add
    for addr in [
        "0x0000000000000000000000000000000000000000",
        "0x0000000000000000000000000000000000000001",
        "0x0000000000000000000000000000000000000002",
        added_addr,
    ]:
        assert counts_after_add.get(addr, 0) > 0, f"{addr} was never selected while active"

    # After removing the first original, only the other two originals + the added
    # validator should be selected.
    assert "0x0000000000000000000000000000000000000000" not in counts_after_remove
    assert added_addr in counts_after_remove
    assert counts_after_remove.get("0x0000000000000000000000000000000000000001", 0) > 0
    assert counts_after_remove.get("0x0000000000000000000000000000000000000002", 0) > 0


def test_partition_tolerance_soak() -> None:
    """Mark validators as partitioned over many rounds and verify liveness rules."""
    consensus = _make_consensus(5)

    # Normal operation: consensus should succeed
    assert asyncio.run(consensus.attempt_consensus("block-0")) is True

    for i in range(3):
        consensus.mark_validator_partitioned(f"0x{i:040x}")

    # 3 out of 5 partitioned -> consensus cannot be reached
    result = asyncio.run(consensus.attempt_consensus("block-partitioned"))
    assert result is False

    # Heal the partition and run many more consensus attempts
    consensus.partitioned_validators.clear()
    consensus.last_partition_healed = time.time()

    for i in range(50):
        result = asyncio.run(consensus.attempt_consensus(f"block-{i}"))
        assert result is True, f"Consensus failed after healing at round {i}"


def test_pbft_many_sequences() -> None:
    """Run PBFT through 100 consecutive blocks and ensure the engine stays stable."""
    consensus = _make_consensus(4)

    for i in range(100):
        result = asyncio.run(consensus.attempt_consensus(f"soak-block-{i}"))
        assert result is True, f"PBFT consensus failed at block {i}"

    # Each attempt increments the consensus counter on the engine.
    assert consensus.consensus_attempts == 100


if __name__ == "__main__":
    pytest.main([__file__])
