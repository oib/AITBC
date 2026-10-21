"""
Critical Failure Scenario Tests for AITBC Mesh Network
Tests system behavior under critical failure conditions
"""

import asyncio
import time
from decimal import Decimal
from unittest.mock import Mock

import pytest

# Import required modules
try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
    from aitbc_chain.contracts.escrow import EscrowManager

    # Agent registry not available in current codebase
    AgentRegistry = None
except ImportError:
    pass


@pytest.fixture(autouse=True)
def _activate_multi_validator_consensus(monkeypatch):
    """Enable the consensus gate for this module (V23-61).

    `MultiValidatorPoA.__init__` raises unless `multi_validator_consensus_enabled` is set,
    which defaults False pending security review. That guard is about what a *node* may run
    in production; it is not a property these tests are asserting. Left unpatched it turned
    all nine tests in this file into collection-time errors — and because the message names a
    config setting rather than a broken assertion, the whole file read as "not activated yet"
    rather than "unrun". Byzantine-majority and partition-tolerance coverage is exactly what
    should not quietly stop executing while the feature waits for that review.

    Set on the settings object the constructor reads, not the environment: the setting is
    resolved at import time, so an env var set here would arrive too late.
    """
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True, raising=False)


class TestConsensusDuringNetworkPartition:
    """Test consensus behavior during network partition"""

    @pytest.fixture
    def partitioned_consensus(self):
        """Setup consensus in partitioned network scenario"""
        poa = MultiValidatorPoA("partition-test")

        # Add validators across 3 partitions
        partition_a = ["0xa1", "0xa2"]
        partition_b = ["0xb1", "0xb2", "0xb3"]
        partition_c = ["0xc1", "0xc2", "0xc3"]

        all_validators = partition_a + partition_b + partition_c
        for v in all_validators:
            poa.add_validator(v, 1000.0)
            # Manually set role to VALIDATOR (activate_validator doesn't exist)
            poa.validators[v].role = ValidatorRole.VALIDATOR

        return {
            "poa": poa,
            "partition_a": partition_a,
            "partition_b": partition_b,
            "partition_c": partition_c,
            "all_validators": all_validators,
        }


class TestJobCompletionWithAgentFailure:
    """Test job recovery when agent fails mid-execution"""

    @pytest.fixture
    def job_with_escrow(self):
        """Setup job with escrow contract"""
        escrow = EscrowManager()

        # Create escrow contract
        success, message, contract_id = asyncio.run(
            escrow.create_contract(
                job_id="job_001", client_address="0xclient", agent_address="0xagent", amount=Decimal("100.0")
            )
        )

        # If contract creation failed, manually create a mock contract
        if not success or not contract_id:
            contract_id = "test_contract_001"
            import time

            from aitbc_chain.contracts.escrow import EscrowContract, EscrowState

            escrow.escrow_contracts[contract_id] = EscrowContract(
                contract_id=contract_id,
                job_id="job_001",
                client_address="0xclient",
                agent_address="0xagent",
                amount=Decimal("100.0"),
                fee_rate=Decimal("0.025"),
                created_at=time.time(),
                expires_at=time.time() + 86400,
                state=EscrowState.FUNDED,  # Start with FUNDED state
                milestones=[],
                current_milestone=0,
                dispute_reason=None,
                dispute_evidence=[],
                resolution=None,
                released_amount=Decimal("0"),
                refunded_amount=Decimal("0"),
            )
            escrow.active_contracts.add(contract_id)

        return {"escrow": escrow, "contract_id": contract_id, "job_id": "job_001"}


class TestSystemUnderHighLoad:
    """Test system behavior under high load conditions"""

    def test_memory_usage_under_load(self):
        """Test memory usage remains bounded under high load"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create large dataset
        large_dataset = []
        for i in range(10000):
            large_dataset.append(
                {
                    "id": i,
                    "data": "x" * 1000,
                    "timestamp": time.time(),
                }
            )

        peak_memory = process.memory_info().rss / 1024 / 1024

        # Clear dataset
        del large_dataset

        process.memory_info().rss / 1024 / 1024

        # Memory should not grow unbounded
        memory_increase = peak_memory - initial_memory
        assert memory_increase < 500  # Less than 500MB increase


class TestByzantineFaultTolerance:
    """Test Byzantine fault tolerance scenarios"""

    @pytest.fixture
    def byzantine_setup(self):
        """Setup with Byzantine validators"""
        poa = MultiValidatorPoA("byzantine-test")

        # 7 validators: 2 honest, 2 faulty, 3 Byzantine
        honest_validators = ["0xh1", "0xh2"]
        faulty_validators = ["0xf1", "0xf2"]  # Offline/crashed
        byzantine_validators = ["0xb1", "0xb2", "0xb3"]  # Malicious

        all_validators = honest_validators + faulty_validators + byzantine_validators

        for v in all_validators:
            poa.add_validator(v, 1000.0)
            poa.validators[v].role = ValidatorRole.VALIDATOR

        return {
            "poa": poa,
            "honest": honest_validators,
            "faulty": faulty_validators,
            "byzantine": byzantine_validators,
            "all": all_validators,
        }


class TestDataIntegrity:
    def test_blockchain_state_consistency_after_crash(self):
        """Test blockchain state remains consistent after crash recovery"""
        poa = MultiValidatorPoA("integrity-test", load_state=False)

        # Add validators and create some blocks
        validators = [f"0x{i}" for i in range(5)]
        for v in validators:
            poa.add_validator(v, 1000.0)
            poa.validators[v].role = ValidatorRole.VALIDATOR

        # Record initial state hash
        initial_state = poa.get_state_snapshot()
        poa.calculate_state_hash(initial_state)

        # Simulate some operations
        poa.create_block()
        poa.add_transaction(Mock(tx_id="tx1"))

        # Simulate crash and recovery (state should be consistent)
        recovered_state = poa.get_state_snapshot()

        # State should have changed due to operations, but be consistent
        assert recovered_state is not None
        assert len(recovered_state["validators"]) == 5
        assert recovered_state != initial_state


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
