"""v0.18.0 B4 — validator rotation determinism.

Equal stake/reputation/score must resolve to the same ordering on every
node; address is the final tiebreaker.
"""

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.rotation import RotationConfig, RotationStrategy, ValidatorRotation


def _consensus_with_ties(addresses: list[str]) -> MultiValidatorPoA:
    consensus = MultiValidatorPoA("test-rotation")
    for addr in addresses:
        consensus.add_validator(addr, 1000.0)  # identical stake + reputation
    return consensus


def _proposer_after_rotation(consensus: MultiValidatorPoA, strategy: RotationStrategy) -> str:
    rotation = ValidatorRotation(
        consensus,
        RotationConfig(strategy=strategy, rotation_interval=1, min_stake=0, reputation_threshold=0.0, max_validators=10),
    )
    assert rotation.rotate_validators(1) is True
    proposers = [a for a, v in consensus.validators.items() if v.role == ValidatorRole.PROPOSER]
    assert len(proposers) == 1
    return proposers[0]


def test_rotation_deterministic_regardless_of_insertion_order():
    forward = ["0xaaa", "0xbbb", "0xccc", "0xddd"]
    shuffled = ["0xccc", "0xaaa", "0xddd", "0xbbb"]
    for strategy in (
        RotationStrategy.ROUND_ROBIN,
        RotationStrategy.STAKE_WEIGHTED,
        RotationStrategy.REPUTATION_BASED,
        RotationStrategy.HYBRID,
    ):
        assert _proposer_after_rotation(_consensus_with_ties(forward), strategy) == _proposer_after_rotation(
            _consensus_with_ties(shuffled), strategy
        ), strategy
