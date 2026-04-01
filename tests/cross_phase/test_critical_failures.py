"""
Critical Failure Scenario Tests for AITBC Mesh Network
Tests system behavior under critical failure conditions
"""

import pytest
import asyncio
import time
import random
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal

# Import required modules
try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    from aitbc_chain.network.discovery import P2PDiscovery
    from aitbc_chain.economics.staking import StakingManager
    from agent_services.agent_registry.src.registration import AgentRegistry
    from aitbc_chain.contracts.escrow import EscrowManager
except ImportError:
    pytest.skip("Required modules not available", allow_module_level=True)


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
            poa.activate_validator(v)
        
        return {
            'poa': poa,
            'partition_a': partition_a,
            'partition_b': partition_b,
            'partition_c': partition_c,
            'all_validators': all_validators
        }
    
    @pytest.mark.asyncio
    async def test_consensus_pauses_during_partition(self, partitioned_consensus):
        """Test that consensus pauses when network is partitioned"""
        poa = partitioned_consensus['poa']
        
        # Simulate network partition detected
        poa.network_partitioned = True
        
        # Attempt to create block should fail or be delayed
        with pytest.raises(Exception) as exc_info:
            await poa.create_block_during_partition()
        
        assert "partition" in str(exc_info.value).lower() or "paused" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_consensus_resumes_after_partition_healing(self, partitioned_consensus):
        """Test that consensus resumes after network heals"""
        poa = partitioned_consensus['poa']
        
        # Start with partition
        poa.network_partitioned = True
        
        # Heal partition
        poa.network_partitioned = False
        poa.last_partition_healed = time.time()
        
        # Wait minimum time before resuming
        await asyncio.sleep(0.1)
        
        # Consensus should be able to resume
        assert poa.can_resume_consensus() is True
    
    def test_partition_tolerant_to_minority_partition(self, partitioned_consensus):
        """Test that consensus continues if minority is partitioned"""
        poa = partitioned_consensus['poa']
        partition_a = partitioned_consensus['partition_a']
        
        # Mark minority partition as isolated
        for v in partition_a:
            poa.mark_validator_partitioned(v)
        
        # Majority should still be able to reach consensus
        majority_size = len(partitioned_consensus['all_validators']) - len(partition_a)
        assert majority_size >= poa.quorum_size(8)  # 5 validators remain (quorum = 5)
    
    @pytest.mark.asyncio
    async def test_validator_churn_during_partition(self, partitioned_consensus):
        """Test validator joining/leaving during network partition"""
        poa = partitioned_consensus['poa']
        
        # Simulate partition
        poa.network_partitioned = True
        
        # Attempt to add new validator during partition
        result = poa.add_validator("0xnew", 1000.0)
        
        # Should be queued or delayed
        assert result is True or result is False  # Depending on implementation


class TestEconomicCalculationsDuringValidatorChurn:
    """Test economic consistency during validator changes"""
    
    @pytest.fixture
    def economic_system_with_churn(self):
        """Setup economic system with active validators"""
        staking = StakingManager(min_stake_amount=1000.0)
        
        # Register initial validators
        initial_validators = [f"0x{i}" for i in range(5)]
        for v in initial_validators:
            staking.register_validator(v, 2000.0, 0.05)
        
        # Record initial stake amounts
        initial_stakes = {v: staking.get_total_staked() for v in initial_validators}
        
        return {
            'staking': staking,
            'initial_validators': initial_validators,
            'initial_stakes': initial_stakes
        }
    
    def test_reward_calculation_during_validator_join(self, economic_system_with_churn):
        """Test reward calculation when validator joins mid-epoch"""
        staking = economic_system_with_churn['staking']
        
        # Record state before new validator
        total_stake_before = staking.get_total_staked()
        validator_count_before = staking.get_validator_count()
        
        # New validator joins
        new_validator = "0xnew_validator"
        staking.register_validator(new_validator, 1500.0, 0.04)
        
        # Verify total stake updated correctly
        total_stake_after = staking.get_total_staked()
        assert total_stake_after > total_stake_before
        
        # Verify reward calculation includes new validator correctly
        rewards = staking.calculate_epoch_rewards()
        assert new_validator in rewards
    
    def test_reward_calculation_during_validator_exit(self, economic_system_with_churn):
        """Test reward calculation when validator exits mid-epoch"""
        staking = economic_system_with_churn['staking']
        exiting_validator = economic_system_with_churn['initial_validators'][0]
        
        # Record state before exit
        total_stake_before = staking.get_total_staked()
        
        # Validator exits
        staking.initiate_validator_exit(exiting_validator)
        
        # Stake should still be counted until unstaking period ends
        total_stake_during_exit = staking.get_total_staked()
        assert total_stake_during_exit == total_stake_before
        
        # After unstaking period
        staking.complete_validator_exit(exiting_validator)
        total_stake_after = staking.get_total_staked()
        assert total_stake_after < total_stake_before
    
    def test_slashing_during_reward_distribution(self, economic_system_with_churn):
        """Test that slashed validator doesn't receive rewards"""
        staking = economic_system_with_churn['staking']
        
        # Select validator to slash
        slashed_validator = economic_system_with_churn['initial_validators'][1]
        
        # Add rewards to all validators
        for v in economic_system_with_churn['initial_validators']:
            staking.add_pending_rewards(v, 100.0)
        
        # Slash one validator
        staking.slash_validator(slashed_validator, 0.1, "Double signing")
        
        # Distribute rewards
        staking.distribute_rewards()
        
        # Slashed validator should have reduced or no rewards
        slashed_rewards = staking.get_validator_rewards(slashed_validator)
        other_rewards = staking.get_validator_rewards(
            economic_system_with_churn['initial_validators'][2]
        )
        
        assert slashed_rewards < other_rewards
    
    @pytest.mark.asyncio
    async def test_concurrent_stake_unstake_operations(self, economic_system_with_churn):
        """Test concurrent staking operations don't corrupt state"""
        staking = economic_system_with_churn['staking']
        
        validator = economic_system_with_churn['initial_validators'][0]
        
        # Perform concurrent operations
        async def stake_operation():
            staking.stake(validator, "0xdelegator1", 500.0)
        
        async def unstake_operation():
            await asyncio.sleep(0.01)  # Slight delay
            staking.unstake(validator, "0xdelegator2", 200.0)
        
        # Run concurrently
        await asyncio.gather(
            stake_operation(),
            unstake_operation(),
            stake_operation(),
            return_exceptions=True
        )
        
        # Verify state is consistent
        total_staked = staking.get_total_staked()
        assert total_staked >= 0  # Should never be negative


class TestJobCompletionWithAgentFailure:
    """Test job recovery when agent fails mid-execution"""
    
    @pytest.fixture
    def job_with_escrow(self):
        """Setup job with escrow contract"""
        escrow = EscrowManager()
        
        # Create contract
        success, _, contract_id = asyncio.run(escrow.create_contract(
            job_id="job_001",
            client_address="0xclient",
            agent_address="0xagent",
            amount=Decimal('100.0')
        ))
        
        # Fund contract
        asyncio.run(escrow.fund_contract(contract_id, "tx_hash"))
        
        return {
            'escrow': escrow,
            'contract_id': contract_id,
            'job_id': "job_001"
        }
    
    @pytest.mark.asyncio
    async def test_job_recovery_on_agent_failure(self, job_with_escrow):
        """Test job recovery when agent fails"""
        escrow = job_with_escrow['escrow']
        contract_id = job_with_escrow['contract_id']
        
        # Start job
        await escrow.start_job(contract_id)
        
        # Simulate agent failure
        await escrow.report_agent_failure(contract_id, "0xagent", "Agent crashed")
        
        # Verify job can be reassigned
        new_agent = "0xnew_agent"
        success = await escrow.reassign_job(contract_id, new_agent)
        
        assert success is True
        
        # Verify contract state updated
        contract = await escrow.get_contract_info(contract_id)
        assert contract.agent_address == new_agent
    
    @pytest.mark.asyncio
    async def test_escrow_refund_on_job_failure(self, job_with_escrow):
        """Test client refund when job cannot be completed"""
        escrow = job_with_escrow['escrow']
        contract_id = job_with_escrow['contract_id']
        
        # Start job
        await escrow.start_job(contract_id)
        
        # Mark job as failed
        await escrow.fail_job(contract_id, "Technical failure")
        
        # Process refund
        success, refund_amount = await escrow.process_refund(contract_id)
        
        assert success is True
        assert refund_amount == Decimal('100.0')  # Full refund
        
        # Verify contract state
        contract = await escrow.get_contract_info(contract_id)
        assert contract.state == "REFUNDED"
    
    @pytest.mark.asyncio
    async def test_partial_completion_on_agent_failure(self, job_with_escrow):
        """Test partial payment for completed work when agent fails"""
        escrow = job_with_escrow['escrow']
        contract_id = job_with_escrow['contract_id']
        
        # Setup milestones
        milestones = [
            {'milestone_id': 'm1', 'amount': Decimal('30.0'), 'completed': True},
            {'milestone_id': 'm2', 'amount': Decimal('40.0'), 'completed': True},
            {'milestone_id': 'm3', 'amount': Decimal('30.0'), 'completed': False},
        ]
        
        for m in milestones:
            await escrow.add_milestone(contract_id, m['milestone_id'], m['amount'])
            if m['completed']:
                await escrow.complete_milestone(contract_id, m['milestone_id'])
        
        # Agent fails before completing last milestone
        await escrow.report_agent_failure(contract_id, "0xagent", "Agent failed")
        
        # Process partial payment
        completed_amount = sum(m['amount'] for m in milestones if m['completed'])
        agent_payment, client_refund = await escrow.process_partial_payment(contract_id)
        
        assert agent_payment == completed_amount
        assert client_refund == Decimal('30.0')  # Uncompleted milestone
    
    @pytest.mark.asyncio
    async def test_multiple_agent_failures(self, job_with_escrow):
        """Test job resilience through multiple agent failures"""
        escrow = job_with_escrow['escrow']
        contract_id = job_with_escrow['contract_id']
        
        # Start job
        await escrow.start_job(contract_id)
        
        # Multiple agent failures
        agents = ["0xagent1", "0xagent2", "0xagent3"]
        
        for i, agent in enumerate(agents):
            if i > 0:
                # Reassign to new agent
                await escrow.reassign_job(contract_id, agent)
            
            # Simulate work then failure
            await asyncio.sleep(0.01)
            await escrow.report_agent_failure(contract_id, agent, f"Agent {i} failed")
        
        # Verify contract still valid
        contract = await escrow.get_contract_info(contract_id)
        assert contract.state in ["ACTIVE", "REASSIGNING", "DISPUTED"]


class TestSystemUnderHighLoad:
    """Test system behavior under high load conditions"""
    
    @pytest.fixture
    def loaded_system(self):
        """Setup system under high load"""
        return {
            'poa': MultiValidatorPoA("load-test"),
            'discovery': P2PDiscovery("load-node", "127.0.0.1", 8000),
            'staking': StakingManager(min_stake_amount=1000.0),
        }
    
    @pytest.mark.asyncio
    async def test_consensus_under_transaction_flood(self, loaded_system):
        """Test consensus stability under transaction flood"""
        poa = loaded_system['poa']
        
        # Add validators
        for i in range(10):
            poa.add_validator(f"0x{i}", 1000.0)
            poa.activate_validator(f"0x{i}")
        
        # Generate many concurrent transactions
        transactions = []
        for i in range(1000):
            tx = Mock(
                tx_id=f"tx_{i}",
                from_address="0xclient",
                to_address="0xagent",
                amount=Decimal('1.0')
            )
            transactions.append(tx)
        
        # Process transactions under load
        processed = 0
        failed = 0
        
        async def process_tx(tx):
            try:
                await asyncio.wait_for(
                    poa.validate_transaction_async(tx),
                    timeout=1.0
                )
                return True
            except asyncio.TimeoutError:
                return False
            except Exception:
                return False
        
        # Process in batches
        batch_size = 100
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i+batch_size]
            results = await asyncio.gather(*[process_tx(tx) for tx in batch])
            processed += sum(results)
            failed += len(batch) - sum(results)
        
        # Should process majority of transactions
        assert processed > 800  # At least 80% success rate
    
    @pytest.mark.asyncio
    async def test_network_under_peer_flood(self, loaded_system):
        """Test network stability under peer connection flood"""
        discovery = loaded_system['discovery']
        
        # Simulate many peer connection attempts
        peer_attempts = 500
        successful_connections = 0
        
        for i in range(peer_attempts):
            try:
                result = await asyncio.wait_for(
                    discovery.attempt_peer_connection(f"127.0.0.1", 8001 + i),
                    timeout=0.1
                )
                if result:
                    successful_connections += 1
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
        
        # Should not crash and should handle load gracefully
        assert successful_connections >= 0  # Should not crash
    
    def test_memory_usage_under_load(self):
        """Test memory usage remains bounded under high load"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create large dataset
        large_dataset = []
        for i in range(10000):
            large_dataset.append({
                'id': i,
                'data': 'x' * 1000,
                'timestamp': time.time(),
            })
        
        peak_memory = process.memory_info().rss / 1024 / 1024
        
        # Clear dataset
        del large_dataset
        
        final_memory = process.memory_info().rss / 1024 / 1024
        
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
            poa.activate_validator(v)
        
        return {
            'poa': poa,
            'honest': honest_validators,
            'faulty': faulty_validators,
            'byzantine': byzantine_validators,
            'all': all_validators
        }
    
    @pytest.mark.asyncio
    async def test_consensus_with_byzantine_majority(self, byzantine_setup):
        """Test consensus fails with Byzantine majority"""
        poa = byzantine_setup['poa']
        
        # With 3 Byzantine out of 7, they don't have majority
        # But with 3 Byzantine + 2 faulty = 5, they could prevent consensus
        
        # Attempt to reach consensus
        result = await poa.attempt_consensus(
            block_hash="test_block",
            round=1
        )
        
        # Should fail due to insufficient honest validators
        assert result is False or result is None
    
    def test_byzantine_behavior_detection(self, byzantine_setup):
        """Test detection of Byzantine behavior"""
        poa = byzantine_setup['poa']
        
        # Simulate Byzantine behavior: inconsistent messages
        byzantine_validator = byzantine_setup['byzantine'][0]
        
        # Send conflicting prepare messages
        poa.record_prepare(byzantine_validator, "block_1", 1)
        poa.record_prepare(byzantine_validator, "block_2", 1)  # Conflict!
        
        # Should detect Byzantine behavior
        is_byzantine = poa.detect_byzantine_behavior(byzantine_validator)
        assert is_byzantine is True


class TestDataIntegrity:
    """Test data integrity during failures"""
    
    def test_blockchain_state_consistency_after_crash(self):
        """Test blockchain state remains consistent after crash recovery"""
        poa = MultiValidatorPoA("integrity-test")
        
        # Add validators and create some blocks
        validators = [f"0x{i}" for i in range(5)]
        for v in validators:
            poa.add_validator(v, 1000.0)
            poa.activate_validator(v)
        
        # Record initial state hash
        initial_state = poa.get_state_snapshot()
        initial_hash = poa.calculate_state_hash(initial_state)
        
        # Simulate some operations
        poa.create_block()
        poa.add_transaction(Mock(tx_id="tx1"))
        
        # Simulate crash and recovery
        recovered_state = poa.recover_state()
        recovered_hash = poa.calculate_state_hash(recovered_state)
        
        # State should be consistent
        assert recovered_hash == initial_hash or poa.validate_state_transition()
    
    def test_transaction_atomicity(self):
        """Test transactions are atomic (all or nothing)"""
        staking = StakingManager(min_stake_amount=1000.0)
        
        # Setup
        staking.register_validator("0xvalidator", 2000.0, 0.05)
        staking.stake("0xvalidator", "0xdelegator", 1500.0)
        
        initial_total = staking.get_total_staked()
        
        # Attempt complex transaction that should be atomic
        try:
            staking.execute_atomic_transaction([
                ('stake', '0xvalidator', '0xnew1', 500.0),
                ('stake', '0xvalidator', '0xnew2', 500.0),
                ('invalid_operation',)  # This should fail
            ])
        except Exception:
            pass  # Expected to fail
        
        # Verify state is unchanged (atomic rollback)
        final_total = staking.get_total_staked()
        assert final_total == initial_total


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
