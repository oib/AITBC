"""
Staking Lifecycle Integration Tests
Test 3.1.1: Complete staking lifecycle integration test
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "apps/coordinator-api/src"))
sys.path.insert(0, str(repo_root / "contracts"))

# Import after path setup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlmodel import SQLModel

from app.domain.bounty import AgentStake, AgentMetrics, StakingPool, StakeStatus, PerformanceTier
from app.services.staking_service import StakingService


@pytest.fixture
def db_session():
    """Create SQLite in-memory database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def staking_service(db_session):
    """Create staking service instance"""
    return StakingService(db_session)


@pytest.fixture
def agent_wallet():
    """Test agent wallet address"""
    return "0x1234567890123456789012345678901234567890"


@pytest.fixture
def staker_address():
    """Test staker address"""
    return "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


@pytest.fixture
def agent_metrics(db_session, agent_wallet):
    """Create test agent metrics"""
    metrics = AgentMetrics(
        agent_wallet=agent_wallet,
        total_staked=0.0,
        staker_count=0,
        total_rewards_distributed=0.0,
        average_accuracy=95.0,
        total_submissions=10,
        successful_submissions=9,
        success_rate=90.0,
        current_tier=PerformanceTier.GOLD,
        tier_score=80.0
    )
    db_session.add(metrics)
    db_session.commit()
    db_session.refresh(metrics)
    return metrics


class TestStakingLifecycle:
    """Test 3.1.1: Complete staking lifecycle integration test"""

    async def test_complete_staking_lifecycle(
        self, 
        staking_service, 
        agent_metrics, 
        staker_address,
        agent_wallet
    ):
        """Test complete staking lifecycle: create stake → unbond → complete"""
        
        # Step 1: Create stake
        print("\n=== Step 1: Creating stake ===")
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        assert stake is not None
        assert stake.status == StakeStatus.ACTIVE
        assert stake.amount == 1000.0
        print(f"✓ Stake created: {stake.stake_id}")
        
        # Verify agent metrics updated
        updated_metrics = await staking_service.get_agent_metrics(agent_wallet)
        assert updated_metrics.total_staked == 1000.0
        assert updated_metrics.staker_count == 1
        print(f"✓ Agent metrics updated: total_staked={updated_metrics.total_staked}")
        
        # Verify staking pool updated
        updated_pool = await staking_service.get_staking_pool(agent_wallet)
        assert updated_pool.total_staked == 1000.0
        print(f"✓ Staking pool updated: total_staked={updated_pool.total_staked}")
        
        # Step 2: Calculate rewards
        print("\n=== Step 2: Calculating rewards ===")
        rewards = await staking_service.calculate_rewards(stake.stake_id)
        print(f"✓ Rewards calculated: {rewards}")
        
        # Step 3: Simulate time passing (lock period elapsed)
        print("\n=== Step 3: Simulating lock period ===")
        # In a real scenario, this would be actual time passing
        # For testing, we'll just verify the logic works
        stake.end_time = datetime.utcnow() - timedelta(days=1)  # Lock period ended
        staking_service.session.commit()
        print(f"✓ Lock period simulated as ended")
        
        # Step 4: Initiate unbonding
        print("\n=== Step 4: Initiating unbonding ===")
        unbonded_stake = await staking_service.unbond_stake(stake.stake_id)
        assert unbonded_stake.status == StakeStatus.UNBONDING
        print(f"✓ Unbonding initiated: status={unbonded_stake.status}")
        
        # Step 5: Simulate unbonding period
        print("\n=== Step 5: Simulating unbonding period ===")
        unbonded_stake.unbonding_time = datetime.utcnow() - timedelta(days=8)  # 8 days ago
        staking_service.session.commit()
        print(f"✓ Unbonding period simulated as ended")
        
        # Step 6: Complete unbonding
        print("\n=== Step 6: Completing unbonding ===")
        result = await staking_service.complete_unbonding(stake.stake_id)
        
        assert result is not None
        assert "total_amount" in result
        assert "total_rewards" in result
        assert "penalty" in result
        print(f"✓ Unbonding completed:")
        print(f"  - Total amount: {result['total_amount']}")
        print(f"  - Total rewards: {result['total_rewards']}")
        print(f"  - Penalty: {result['penalty']}")
        
        # Verify stake status
        completed_stake = await staking_service.get_stake(stake.stake_id)
        assert completed_stake.status == StakeStatus.COMPLETED
        print(f"✓ Stake status: {completed_stake.status}")
        
        # Verify agent metrics updated
        final_metrics = await staking_service.get_agent_metrics(agent_wallet)
        assert final_metrics.total_staked == 0.0
        assert final_metrics.staker_count == 0
        print(f"✓ Agent metrics reset: total_staked={final_metrics.total_staked}")
        
        # Verify staking pool updated
        final_pool = await staking_service.get_staking_pool(agent_wallet)
        assert final_pool.total_staked == 0.0
        assert staker_address not in final_pool.active_stakers
        print(f"✓ Staking pool reset: total_staked={final_pool.total_staked}")
        
        print("\n=== Complete staking lifecycle test PASSED ===")

    async def test_stake_accumulation_over_time(
        self, 
        staking_service, 
        agent_metrics, 
        staker_address,
        agent_wallet
    ):
        """Test rewards accumulation over time"""
        
        # Create stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Calculate initial rewards
        initial_rewards = await staking_service.calculate_rewards(stake.stake_id)
        print(f"Initial rewards: {initial_rewards}")
        
        # Simulate time passing by updating last_reward_time
        stake.last_reward_time = datetime.utcnow() - timedelta(days=10)
        staking_service.session.commit()
        
        # Calculate rewards after 10 days
        rewards_after_10_days = await staking_service.calculate_rewards(stake.stake_id)
        print(f"Rewards after 10 days: {rewards_after_10_days}")
        
        # Rewards should have increased
        assert rewards_after_10_days >= initial_rewards
        print("✓ Rewards accumulated over time")

    async def test_multiple_stakes_same_agent(
        self, 
        staking_service, 
        agent_metrics, 
        staker_address,
        agent_wallet
    ):
        """Test multiple stakes on the same agent"""
        
        # Create first stake
        stake1 = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_wallet,
            amount=500.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Create second stake
        stake2 = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_wallet,
            amount=1500.0,
            lock_period=60,
            auto_compound=True
        )
        
        # Verify both stakes exist
        assert stake1.stake_id != stake2.stake_id
        assert stake1.amount == 500.0
        assert stake2.amount == 1500.0
        assert stake2.auto_compound == True
        
        # Verify agent metrics
        metrics = await staking_service.get_agent_metrics(agent_wallet)
        assert metrics.total_staked == 2000.0
        assert metrics.staker_count == 1  # Same staker
        
        # Verify staking pool
        pool = await staking_service.get_staking_pool(agent_wallet)
        assert pool.total_staked == 2000.0
        
        print("✓ Multiple stakes on same agent created successfully")

    async def test_stake_with_different_tiers(
        self, 
        staking_service, 
        db_session, 
        staker_address,
        agent_wallet
    ):
        """Test stakes on agents with different performance tiers"""
        
        # Create agents with different tiers
        bronze_agent = "0x1111111111111111111111111111111111111111"
        silver_agent = "0x2222222222222222222222222222222222222222"
        gold_agent = agent_wallet
        
        bronze_metrics = AgentMetrics(
            agent_wallet=bronze_agent,
            total_staked=0.0,
            staker_count=0,
            total_rewards_distributed=0.0,
            average_accuracy=65.0,
            total_submissions=10,
            successful_submissions=7,
            success_rate=70.0,
            current_tier=PerformanceTier.BRONZE,
            tier_score=60.0
        )
        
        silver_metrics = AgentMetrics(
            agent_wallet=silver_agent,
            total_staked=0.0,
            staker_count=0,
            total_rewards_distributed=0.0,
            average_accuracy=85.0,
            total_submissions=10,
            successful_submissions=8,
            success_rate=80.0,
            current_tier=PerformanceTier.SILVER,
            tier_score=70.0
        )
        
        gold_metrics = AgentMetrics(
            agent_wallet=gold_agent,
            total_staked=0.0,
            staker_count=0,
            total_rewards_distributed=0.0,
            average_accuracy=95.0,
            total_submissions=10,
            successful_submissions=9,
            success_rate=90.0,
            current_tier=PerformanceTier.GOLD,
            tier_score=80.0
        )
        
        db_session.add_all([bronze_metrics, silver_metrics, gold_metrics])
        db_session.commit()
        
        # Create stakes on each agent
        bronze_stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=bronze_agent,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        silver_stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=silver_agent,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        gold_stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=gold_agent,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Verify APY increases with tier
        assert bronze_stake.current_apy < silver_stake.current_apy
        assert silver_stake.current_apy < gold_stake.current_apy
        
        print(f"✓ Bronze tier APY: {bronze_stake.current_apy}%")
        print(f"✓ Silver tier APY: {silver_stake.current_apy}%")
        print(f"✓ Gold tier APY: {gold_stake.current_apy}%")
        print("✓ APY correctly increases with performance tier")
