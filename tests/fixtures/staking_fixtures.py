"""
Shared fixtures for staking tests
Reusable fixtures for service and integration tests to avoid duplication
"""

import sys
from pathlib import Path
from datetime import datetime, UTC, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlmodel import SQLModel

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/coordinator-api/src"))

from app.domain.bounty import (
    AgentStake, AgentMetrics, StakingPool, 
    StakeStatus, PerformanceTier
)
from app.services.staking_service import StakingService


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def staking_service(db_session):
    """Create StakingService instance with test session"""
    return StakingService(db_session)


@pytest.fixture
def agent_wallet():
    """Default test agent wallet address"""
    return "0x1234567890123456789012345678901234567890"


@pytest.fixture
def staker_address():
    """Default test staker address"""
    return "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


@pytest.fixture
def agent_metrics(agent_wallet):
    """Create test agent metrics with GOLD tier"""
    return AgentMetrics(
        agent_wallet=agent_wallet,
        total_submissions=10,
        successful_submissions=9,
        average_accuracy=95.0,
        current_tier=PerformanceTier.GOLD,
        tier_score=85.0,
        total_staked=0.0,
        staker_count=0,
        total_rewards_distributed=0.0,
        last_update_time=datetime.now(UTC)
    )


@pytest.fixture
def agent_metrics_bronze(agent_wallet):
    """Create test agent metrics with BRONZE tier"""
    return AgentMetrics(
        agent_wallet=agent_wallet,
        total_submissions=5,
        successful_submissions=4,
        average_accuracy=80.0,
        current_tier=PerformanceTier.BRONZE,
        tier_score=60.0,
        total_staked=0.0,
        staker_count=0,
        total_rewards_distributed=0.0,
        last_update_time=datetime.now(UTC)
    )


@pytest.fixture
def agent_metrics_diamond(agent_wallet):
    """Create test agent metrics with DIAMOND tier"""
    return AgentMetrics(
        agent_wallet=agent_wallet,
        total_submissions=50,
        successful_submissions=48,
        average_accuracy=98.0,
        current_tier=PerformanceTier.DIAMOND,
        tier_score=95.0,
        total_staked=0.0,
        staker_count=0,
        total_rewards_distributed=0.0,
        last_update_time=datetime.now(UTC)
    )


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
        last_distribution_time=datetime.now(UTC),
        distribution_frequency=1
    )
    db_session.add(pool)
    db_session.commit()
    db_session.refresh(pool)
    return pool


@pytest.fixture
def stake_data():
    """Default stake creation data"""
    return {
        "amount": 1000.0,
        "lock_period": 30,
        "auto_compound": False
    }


@pytest.fixture
def large_stake_data():
    """Large stake creation data"""
    return {
        "amount": 50000.0,
        "lock_period": 90,
        "auto_compound": True
    }


@pytest.fixture
def small_stake_data():
    """Small stake creation data"""
    return {
        "amount": 100.0,
        "lock_period": 7,
        "auto_compound": False
    }


@pytest.fixture
def invalid_stake_data():
    """Invalid stake creation data (below minimum)"""
    return {
        "amount": 50.0,
        "lock_period": 30,
        "auto_compound": False
    }


@pytest.fixture
def created_stake(staking_service, agent_metrics, staker_address, stake_data):
    """Create a stake for testing"""
    return staking_service.create_stake(
        staker_address=staker_address,
        agent_wallet=agent_metrics.agent_wallet,
        amount=stake_data["amount"],
        lock_period=stake_data["lock_period"],
        auto_compound=stake_data["auto_compound"]
    )


@pytest.fixture
def active_stake(db_session, agent_wallet, staker_address):
    """Create an active stake directly in database"""
    stake = AgentStake(
        stake_id="stake_test_001",
        staker_address=staker_address,
        agent_wallet=agent_wallet,
        amount=1000.0,
        lock_period=30,
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=30),
        status=StakeStatus.ACTIVE,
        accumulated_rewards=0.0,
        last_reward_time=datetime.now(UTC),
        current_apy=8.25,
        agent_tier=PerformanceTier.GOLD,
        performance_multiplier=1.5,
        auto_compound=False
    )
    db_session.add(stake)
    db_session.commit()
    db_session.refresh(stake)
    return stake


@pytest.fixture
def unbonding_stake(db_session, agent_wallet, staker_address):
    """Create an unbonding stake directly in database"""
    stake = AgentStake(
        stake_id="stake_test_002",
        staker_address=staker_address,
        agent_wallet=agent_wallet,
        amount=1000.0,
        lock_period=30,
        start_time=datetime.now(UTC) - timedelta(days=35),
        end_time=datetime.now(UTC) - timedelta(days=5),
        status=StakeStatus.UNBONDING,
        accumulated_rewards=50.0,
        last_reward_time=datetime.now(UTC) - timedelta(days=5),
        current_apy=8.25,
        agent_tier=PerformanceTier.GOLD,
        performance_multiplier=1.5,
        auto_compound=False,
        unbonding_time=datetime.now(UTC) - timedelta(days=5)
    )
    db_session.add(stake)
    db_session.commit()
    db_session.refresh(stake)
    return stake


@pytest.fixture
def completed_stake(db_session, agent_wallet, staker_address):
    """Create a completed stake directly in database"""
    stake = AgentStake(
        stake_id="stake_test_003",
        staker_address=staker_address,
        agent_wallet=agent_wallet,
        amount=1000.0,
        lock_period=30,
        start_time=datetime.now(UTC) - timedelta(days=70),
        end_time=datetime.now(UTC) - timedelta(days=40),
        status=StakeStatus.COMPLETED,
        accumulated_rewards=100.0,
        last_reward_time=datetime.now(UTC) - timedelta(days=40),
        current_apy=8.25,
        agent_tier=PerformanceTier.GOLD,
        performance_multiplier=1.5,
        auto_compound=False,
        unbonding_time=datetime.now(UTC) - timedelta(days=40)
    )
    db_session.add(stake)
    db_session.commit()
    db_session.refresh(stake)
    return stake


@pytest.fixture
def multiple_stakes(db_session, agent_wallet, staker_address):
    """Create multiple stakes for testing"""
    stakes = []
    
    # Stake 1: Active, 30-day lock
    stake1 = AgentStake(
        stake_id="stake_test_001",
        staker_address=staker_address,
        agent_wallet=agent_wallet,
        amount=1000.0,
        lock_period=30,
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=30),
        status=StakeStatus.ACTIVE,
        accumulated_rewards=0.0,
        last_reward_time=datetime.now(UTC),
        current_apy=8.25,
        agent_tier=PerformanceTier.GOLD,
        performance_multiplier=1.5,
        auto_compound=False
    )
    
    # Stake 2: Active, 90-day lock with auto-compound
    stake2 = AgentStake(
        stake_id="stake_test_002",
        staker_address=staker_address,
        agent_wallet=agent_wallet,
        amount=2000.0,
        lock_period=90,
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=90),
        status=StakeStatus.ACTIVE,
        accumulated_rewards=0.0,
        last_reward_time=datetime.now(UTC),
        current_apy=10.0,
        agent_tier=PerformanceTier.GOLD,
        performance_multiplier=1.5,
        auto_compound=True
    )
    
    db_session.add_all([stake1, stake2])
    db_session.commit()
    
    for stake in [stake1, stake2]:
        db_session.refresh(stake)
        stakes.append(stake)
    
    return stakes


def calculate_expected_apy(base_apy=5.0, tier_multiplier=1.0, lock_multiplier=1.0):
    """Calculate expected APY based on parameters"""
    apy = base_apy * tier_multiplier * lock_multiplier
    return min(apy, 20.0)  # Cap at 20%


def get_tier_multiplier(tier):
    """Get tier multiplier for APY calculation"""
    multipliers = {
        PerformanceTier.BRONZE: 1.0,
        PerformanceTier.SILVER: 1.25,
        PerformanceTier.GOLD: 1.5,
        PerformanceTier.PLATINUM: 2.0,
        PerformanceTier.DIAMOND: 3.0
    }
    return multipliers.get(tier, 1.0)


def get_lock_multiplier(lock_period_days):
    """Get lock period multiplier for APY calculation"""
    if lock_period_days >= 365:
        return 2.0
    elif lock_period_days >= 90:
        return 1.5
    elif lock_period_days >= 30:
        return 1.1
    else:
        return 1.0
