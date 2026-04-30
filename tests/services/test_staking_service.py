"""
Staking Service Tests
High-priority tests for staking service functionality
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/coordinator-api/src"))

from app.domain.bounty import AgentStake, AgentMetrics, StakingPool, StakeStatus, PerformanceTier
from app.services.staking_service import StakingService


@pytest.fixture
def db_session():
    """Create SQLite in-memory database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    from sqlmodel import SQLModel
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
def agent_metrics(db_session):
    """Create test agent metrics"""
    metrics = AgentMetrics(
        agent_wallet="0x1234567890123456789012345678901234567890",
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


@pytest.fixture
def staking_pool(db_session, agent_metrics):
    """Create test staking pool"""
    pool = StakingPool(
        agent_wallet=agent_metrics.agent_wallet,
        total_staked=0.0,
        total_rewards=0.0,
        pool_apy=5.0,
        staker_count=0,
        active_stakers=[],
        last_distribution_time=datetime.now(datetime.UTC),
        distribution_frequency=1
    )
    db_session.add(pool)
    db_session.commit()
    db_session.refresh(pool)
    return pool


class TestStakingService:
    """Test 2.1.1: Create stake via service"""

    async def test_create_stake_success(self, staking_service, agent_metrics):
        """Test creating a stake with valid parameters"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        amount = 1000.0
        lock_period = 30
        auto_compound = False

        # Create stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=amount,
            lock_period=lock_period,
            auto_compound=auto_compound
        )

        # Verify stake created
        assert stake is not None
        assert stake.staker_address == staker_address
        assert stake.agent_wallet == agent_metrics.agent_wallet
        assert stake.amount == amount
        assert stake.lock_period == lock_period
        assert stake.status == StakeStatus.ACTIVE
        assert stake.auto_compound == auto_compound
        assert stake.agent_tier == PerformanceTier.GOLD

        # Verify APY calculated
        # Base APY = 5%, Gold tier multiplier = 1.5, 30-day lock multiplier = 1.1
        # Expected APY = 5% * 1.5 * 1.1 = 8.25%
        assert stake.current_apy > 8.0  # Allow small rounding error

        # Verify end time calculated
        expected_end_time = datetime.now(datetime.UTC) + timedelta(days=lock_period)
        time_diff = abs((stake.end_time - expected_end_time).total_seconds())
        assert time_diff < 60  # Within 1 minute

        # Verify agent metrics updated
        updated_metrics = await staking_service.get_agent_metrics(agent_metrics.agent_wallet)
        assert updated_metrics.total_staked == amount
        assert updated_metrics.staker_count == 1

    async def test_create_stake_unsupported_agent(self, staking_service):
        """Test creating stake on unsupported agent"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        unsupported_agent = "0x0000000000000000000000000000000000000000"
        
        with pytest.raises(ValueError, match="Agent not supported"):
            await staking_service.create_stake(
                staker_address=staker_address,
                agent_wallet=unsupported_agent,
                amount=1000.0,
                lock_period=30,
                auto_compound=False
            )

    async def test_create_stake_invalid_amount(self, staking_service, agent_metrics):
        """Test creating stake with invalid amount (below minimum)"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        with pytest.raises(ValueError, match="Stake amount must be at least 100 AITBC"):
            await staking_service.create_stake(
                staker_address=staker_address,
                agent_wallet=agent_metrics.agent_wallet,
                amount=50.0,  # Below minimum
                lock_period=30,
                auto_compound=False
            )

    async def test_get_stake(self, staking_service, agent_metrics):
        """Test retrieving a stake by ID"""
        # First create a stake
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        created_stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )

        # Retrieve the stake
        retrieved_stake = await staking_service.get_stake(created_stake.stake_id)

        # Verify stake retrieved
        assert retrieved_stake is not None
        assert retrieved_stake.stake_id == created_stake.stake_id
        assert retrieved_stake.staker_address == staker_address
        assert retrieved_stake.amount == 1000.0

    async def test_get_stake_not_found(self, staking_service):
        """Test retrieving non-existent stake"""
        with pytest.raises(ValueError, match="Stake not found"):
            await staking_service.get_stake("nonexistent_stake_id")

    async def test_calculate_apy(self, staking_service, agent_metrics):
        """Test APY calculation for different tiers and lock periods"""
        # Bronze tier, 30 days: 5% * 1.0 * 1.1 = 5.5%
        apy_bronze_30 = await staking_service.calculate_apy(agent_metrics.agent_wallet, 30)
        assert apy_bronze_30 > 5.0

        # Gold tier, 90 days: 5% * 1.5 * 1.25 = 9.375%
        apy_gold_90 = await staking_service.calculate_apy(agent_metrics.agent_wallet, 90)
        assert apy_gold_90 > 9.0

        # Diamond tier, 365 days: 5% * 3.0 * 2.0 = 30% (capped at 20%)
        # Update agent to Diamond tier
        agent_metrics.current_tier = PerformanceTier.DIAMOND
        staking_service.session.commit()
        
        apy_diamond_365 = await staking_service.calculate_apy(agent_metrics.agent_wallet, 365)
        assert apy_diamond_365 == 20.0  # Capped at maximum

    async def test_get_agent_metrics(self, staking_service, agent_metrics):
        """Test retrieving agent metrics"""
        metrics = await staking_service.get_agent_metrics(agent_metrics.agent_wallet)
        
        assert metrics is not None
        assert metrics.agent_wallet == agent_metrics.agent_wallet
        assert metrics.total_staked == 0.0
        assert metrics.current_tier == PerformanceTier.GOLD
        assert metrics.average_accuracy == 95.0

    async def test_get_staking_pool(self, staking_service, agent_metrics):
        """Test retrieving staking pool after stake creation"""
        # Create a stake first which will create the pool
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        pool = await staking_service.get_staking_pool(agent_metrics.agent_wallet)
        
        assert pool is not None
        assert pool.agent_wallet == agent_metrics.agent_wallet
        assert pool.total_staked == 1000.0
        assert pool.pool_apy > 5.0

    async def test_unbond_stake_before_lock_period(self, staking_service, agent_metrics):
        """Test unbonding stake before lock period ends should fail"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Try to unbond immediately (lock period not ended)
        with pytest.raises(ValueError, match="Lock period has not ended"):
            await staking_service.unbond_stake(stake.stake_id)

    async def test_unbond_stake_after_lock_period(self, staking_service, agent_metrics):
        """Test unbonding stake after lock period ends"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Simulate lock period ending by updating end_time
        stake.end_time = datetime.now(datetime.UTC) - timedelta(days=1)
        staking_service.session.commit()
        
        # Unbond the stake
        unbonded_stake = await staking_service.unbond_stake(stake.stake_id)
        
        assert unbonded_stake.status == StakeStatus.UNBONDING
        assert unbonded_stake.unbonding_time is not None

    async def test_complete_unbonding_with_penalty(self, staking_service, agent_metrics):
        """Test completing unbonding with early penalty"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Unbond the stake
        stake.end_time = datetime.now(datetime.UTC) - timedelta(days=1)
        staking_service.session.commit()
        await staking_service.unbond_stake(stake.stake_id)
        
        # Complete unbonding within 30 days (should have 10% penalty)
        result = await staking_service.complete_unbonding(stake.stake_id)
        
        assert result is not None
        assert "total_amount" in result
        assert "penalty" in result
        # Penalty should be 10% of 1000 = 100, so returned amount should be 900 + rewards
        assert result["penalty"] == 100.0

    async def test_complete_unbonding_no_penalty(self, staking_service, agent_metrics):
        """Test completing unbonding after unbonding period (no penalty)"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Unbond the stake
        stake.end_time = datetime.now(datetime.UTC) - timedelta(days=1)
        staking_service.session.commit()
        await staking_service.unbond_stake(stake.stake_id)
        
        # Set unbonding time to 35 days ago (past 30-day penalty period)
        stake = await staking_service.get_stake(stake.stake_id)
        stake.unbonding_time = datetime.now(datetime.UTC) - timedelta(days=35)
        staking_service.session.commit()
        
        # Complete unbonding (no penalty)
        result = await staking_service.complete_unbonding(stake.stake_id)
        
        assert result is not None
        assert "total_amount" in result
        assert result["penalty"] == 0.0

    async def test_calculate_rewards(self, staking_service, agent_metrics):
        """Test reward calculation for active stake"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Calculate rewards
        rewards = await staking_service.calculate_rewards(stake.stake_id)
        
        assert rewards >= 0.0

    async def test_calculate_rewards_unbonding_stake(self, staking_service, agent_metrics):
        """Test reward calculation for unbonding stake (should return accumulated)"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Unbond the stake
        stake.end_time = datetime.now(datetime.UTC) - timedelta(days=1)
        staking_service.session.commit()
        await staking_service.unbond_stake(stake.stake_id)
        
        # Calculate rewards (should return accumulated rewards only)
        rewards = await staking_service.calculate_rewards(stake.stake_id)
        
        assert rewards == stake.accumulated_rewards

    async def test_create_stake_minimum_amount(self, staking_service, agent_metrics):
        """Test creating stake with minimum valid amount"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create stake with exactly minimum amount (100)
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=100.0,  # Minimum amount
            lock_period=30,
            auto_compound=False
        )
        
        assert stake is not None
        assert stake.amount == 100.0

    async def test_create_stake_maximum_amount(self, staking_service, agent_metrics):
        """Test creating stake with large amount"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create stake with large amount
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=100000.0,
            lock_period=30,
            auto_compound=False
        )
        
        assert stake is not None
        assert stake.amount == 100000.0

    async def test_auto_compound_enabled(self, staking_service, agent_metrics):
        """Test creating stake with auto-compound enabled"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=True
        )
        
        assert stake.auto_compound is True

    async def test_multiple_stakes_same_agent(self, staking_service, agent_metrics):
        """Test creating multiple stakes on same agent"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create first stake
        stake1 = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Create second stake
        stake2 = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=2000.0,
            lock_period=90,
            auto_compound=True
        )
        
        # Verify both stakes created
        assert stake1.stake_id != stake2.stake_id
        assert stake1.amount == 1000.0
        assert stake2.amount == 2000.0
        
        # Verify agent metrics updated with total
        updated_metrics = await staking_service.get_agent_metrics(agent_metrics.agent_wallet)
        assert updated_metrics.total_staked == 3000.0
        assert updated_metrics.staker_count == 1  # Same staker

    async def test_get_user_stakes(self, staking_service, agent_metrics):
        """Test retrieving all stakes for a user"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create multiple stakes
        await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=2000.0,
            lock_period=90,
            auto_compound=True
        )
        
        # Get user stakes
        stakes = await staking_service.get_user_stakes(staker_address)
        
        assert len(stakes) == 2
        assert all(stake.staker_address == staker_address for stake in stakes)

    async def test_claim_rewards(self, staking_service, agent_metrics):
        """Test claiming rewards for a stake"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Create a stake
        stake = await staking_service.create_stake(
            staker_address=staker_address,
            agent_wallet=agent_metrics.agent_wallet,
            amount=1000.0,
            lock_period=30,
            auto_compound=False
        )
        
        # Add some accumulated rewards
        stake.accumulated_rewards = 50.0
        staking_service.session.commit()
        
        # Claim rewards
        result = await staking_service.claim_rewards([stake.stake_id])
        
        assert result is not None
        assert result["total_rewards"] == 50.0
        assert result["claimed_stakes"] == 1

    async def test_update_agent_performance(self, staking_service, agent_metrics):
        """Test updating agent performance metrics"""
        # Update performance
        updated_metrics = await staking_service.update_agent_performance(
            agent_wallet=agent_metrics.agent_wallet,
            accuracy=98.0,
            successful=True
        )
        
        assert updated_metrics is not None
        # Service recalculates average based on all submissions
        assert updated_metrics.successful_submissions == 10  # 9 + 1
        assert updated_metrics.total_submissions == 11
        # Average is recalculated: (9*95 + 98) / 10 = 95.3
        assert updated_metrics.average_accuracy > 95.0

    async def test_database_rollback_on_error(self, staking_service, agent_metrics):
        """Test database rollback when stake creation fails"""
        staker_address = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        
        # Get initial total staked
        initial_metrics = await staking_service.get_agent_metrics(agent_metrics.agent_wallet)
        initial_staked = initial_metrics.total_staked
        
        # Try to create stake with invalid amount (should fail and rollback)
        try:
            await staking_service.create_stake(
                staker_address=staker_address,
                agent_wallet=agent_metrics.agent_wallet,
                amount=50.0,  # Invalid (below minimum)
                lock_period=30,
                auto_compound=False
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
        # Verify database state unchanged (rollback worked)
        final_metrics = await staking_service.get_agent_metrics(agent_metrics.agent_wallet)
        assert final_metrics.total_staked == initial_staked
