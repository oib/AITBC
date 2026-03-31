"""
Cross-Chain Reputation Service for Advanced Agent Features
Implements portable reputation scores across multiple blockchain networks
"""

import asyncio
import logging

logger = logging.getLogger(__name__)
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class ReputationTier(StrEnum):
    """Reputation tiers for agents"""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class ReputationEvent(StrEnum):
    """Types of reputation events"""

    TASK_SUCCESS = "task_success"
    TASK_FAILURE = "task_failure"
    TASK_TIMEOUT = "task_timeout"
    TASK_CANCELLED = "task_cancelled"
    POSITIVE_FEEDBACK = "positive_feedback"
    NEGATIVE_FEEDBACK = "negative_feedback"
    REPUTATION_STAKE = "reputation_stake"
    REPUTATION_DELEGATE = "reputation_delegate"
    CROSS_CHAIN_SYNC = "cross_chain_sync"


class ChainNetwork(StrEnum):
    """Supported blockchain networks"""

    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BSC = "bsc"
    AVALANCHE = "avalanche"
    FANTOM = "fantom"


@dataclass
class ReputationScore:
    """Reputation score data"""

    agent_id: str
    chain_id: int
    score: int  # 0-10000
    task_count: int
    success_count: int
    failure_count: int
    last_updated: datetime
    sync_timestamp: datetime
    is_active: bool
    tier: ReputationTier = field(init=False)

    def __post_init__(self):
        self.tier = self.calculate_tier()

    def calculate_tier(self) -> ReputationTier:
        """Calculate reputation tier based on score"""
        if self.score >= 9000:
            return ReputationTier.DIAMOND
        elif self.score >= 7500:
            return ReputationTier.PLATINUM
        elif self.score >= 6000:
            return ReputationTier.GOLD
        elif self.score >= 4500:
            return ReputationTier.SILVER
        else:
            return ReputationTier.BRONZE


@dataclass
class ReputationStake:
    """Reputation stake information"""

    agent_id: str
    amount: int
    lock_period: int  # seconds
    start_time: datetime
    end_time: datetime
    is_active: bool
    reward_rate: float  # APY
    multiplier: float  # Reputation multiplier


@dataclass
class ReputationDelegation:
    """Reputation delegation information"""

    delegator: str
    delegate: str
    amount: int
    start_time: datetime
    is_active: bool
    fee_rate: float  # Fee rate for delegation


@dataclass
class CrossChainSync:
    """Cross-chain synchronization data"""

    agent_id: str
    source_chain: int
    target_chain: int
    reputation_score: int
    sync_timestamp: datetime
    verification_hash: str
    is_verified: bool


@dataclass
class ReputationAnalytics:
    """Reputation analytics data"""

    agent_id: str
    total_score: int
    effective_score: int
    success_rate: float
    stake_amount: int
    delegation_amount: int
    chain_count: int
    tier: ReputationTier
    reputation_age: int  # days
    last_activity: datetime


class CrossChainReputationService:
    """Service for managing cross-chain reputation systems"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.reputation_data: dict[str, ReputationScore] = {}
        self.chain_reputations: dict[str, dict[int, ReputationScore]] = {}
        self.reputation_stakes: dict[str, list[ReputationStake]] = {}
        self.reputation_delegations: dict[str, list[ReputationDelegation]] = {}
        self.cross_chain_syncs: list[CrossChainSync] = []

        # Configuration
        self.base_score = 1000
        self.success_bonus = 100
        self.failure_penalty = 50
        self.min_stake_amount = 100 * 10**18  # 100 AITBC
        self.max_delegation_ratio = 1.0  # 100%
        self.sync_cooldown = 3600  # 1 hour
        self.tier_thresholds = {
            ReputationTier.BRONZE: 4500,
            ReputationTier.SILVER: 6000,
            ReputationTier.GOLD: 7500,
            ReputationTier.PLATINUM: 9000,
            ReputationTier.DIAMOND: 9500,
        }

        # Chain configuration
        self.supported_chains = {
            ChainNetwork.ETHEREUM: 1,
            ChainNetwork.POLYGON: 137,
            ChainNetwork.ARBITRUM: 42161,
            ChainNetwork.OPTIMISM: 10,
            ChainNetwork.BSC: 56,
            ChainNetwork.AVALANCHE: 43114,
            ChainNetwork.FANTOM: 250,
        }

        # Stake rewards
        self.stake_rewards = {
            ReputationTier.BRONZE: 0.05,  # 5% APY
            ReputationTier.SILVER: 0.08,  # 8% APY
            ReputationTier.GOLD: 0.12,  # 12% APY
            ReputationTier.PLATINUM: 0.18,  # 18% APY
            ReputationTier.DIAMOND: 0.25,  # 25% APY
        }

    async def initialize(self):
        """Initialize the cross-chain reputation service"""
        logger.info("Initializing Cross-Chain Reputation Service")

        # Load existing reputation data
        await self._load_reputation_data()

        # Start background tasks
        asyncio.create_task(self._monitor_reputation_sync())
        asyncio.create_task(self._process_stake_rewards())
        asyncio.create_task(self._cleanup_expired_stakes())

        logger.info("Cross-Chain Reputation Service initialized")

    async def initialize_agent_reputation(
        self, agent_id: str, initial_score: int = 1000, chain_id: int | None = None
    ) -> ReputationScore:
        """Initialize reputation for a new agent"""

        try:
            if chain_id is None:
                chain_id = self.supported_chains[ChainNetwork.ETHEREUM]

            logger.info(f"Initializing reputation for agent {agent_id} on chain {chain_id}")

            # Create reputation score
            reputation = ReputationScore(
                agent_id=agent_id,
                chain_id=chain_id,
                score=initial_score,
                task_count=0,
                success_count=0,
                failure_count=0,
                last_updated=datetime.utcnow(),
                sync_timestamp=datetime.utcnow(),
                is_active=True,
            )

            # Store reputation data
            self.reputation_data[agent_id] = reputation

            # Initialize chain reputations
            if agent_id not in self.chain_reputations:
                self.chain_reputations[agent_id] = {}
            self.chain_reputations[agent_id][chain_id] = reputation

            logger.info(f"Reputation initialized for agent {agent_id}: {initial_score}")
            return reputation

        except Exception as e:
            logger.error(f"Failed to initialize reputation for agent {agent_id}: {e}")
            raise

    async def update_reputation(
        self, agent_id: str, event_type: ReputationEvent, weight: int = 1, chain_id: int | None = None
    ) -> ReputationScore:
        """Update agent reputation based on event"""

        try:
            if agent_id not in self.reputation_data:
                await self.initialize_agent_reputation(agent_id)

            reputation = self.reputation_data[agent_id]
            old_score = reputation.score

            # Calculate score change
            score_change = await self._calculate_score_change(event_type, weight)

            # Update reputation
            if event_type in [ReputationEvent.TASK_SUCCESS, ReputationEvent.POSITIVE_FEEDBACK]:
                reputation.score = min(10000, reputation.score + score_change)
                reputation.success_count += 1
            elif event_type in [ReputationEvent.TASK_FAILURE, ReputationEvent.NEGATIVE_FEEDBACK]:
                reputation.score = max(0, reputation.score - score_change)
                reputation.failure_count += 1
            elif event_type == ReputationEvent.TASK_TIMEOUT:
                reputation.score = max(0, reputation.score - score_change // 2)
                reputation.failure_count += 1

            reputation.task_count += 1
            reputation.last_updated = datetime.utcnow()
            reputation.tier = reputation.calculate_tier()

            # Update chain reputation
            if chain_id:
                if chain_id not in self.chain_reputations[agent_id]:
                    self.chain_reputations[agent_id][chain_id] = reputation
                else:
                    self.chain_reputations[agent_id][chain_id] = reputation

            logger.info(f"Updated reputation for agent {agent_id}: {old_score} -> {reputation.score}")
            return reputation

        except Exception as e:
            logger.error(f"Failed to update reputation for agent {agent_id}: {e}")
            raise

    async def sync_reputation_cross_chain(self, agent_id: str, target_chain: int, signature: str) -> bool:
        """Synchronize reputation across chains"""

        try:
            if agent_id not in self.reputation_data:
                raise ValueError(f"Agent {agent_id} not found")

            reputation = self.reputation_data[agent_id]

            # Check sync cooldown
            time_since_sync = (datetime.utcnow() - reputation.sync_timestamp).total_seconds()
            if time_since_sync < self.sync_cooldown:
                logger.warning(f"Sync cooldown not met for agent {agent_id}")
                return False

            # Verify signature (simplified)
            verification_hash = await self._verify_cross_chain_signature(agent_id, target_chain, signature)

            # Create sync record
            sync = CrossChainSync(
                agent_id=agent_id,
                source_chain=reputation.chain_id,
                target_chain=target_chain,
                reputation_score=reputation.score,
                sync_timestamp=datetime.utcnow(),
                verification_hash=verification_hash,
                is_verified=True,
            )

            self.cross_chain_syncs.append(sync)

            # Update target chain reputation
            if target_chain not in self.chain_reputations[agent_id]:
                self.chain_reputations[agent_id][target_chain] = ReputationScore(
                    agent_id=agent_id,
                    chain_id=target_chain,
                    score=reputation.score,
                    task_count=reputation.task_count,
                    success_count=reputation.success_count,
                    failure_count=reputation.failure_count,
                    last_updated=reputation.last_updated,
                    sync_timestamp=datetime.utcnow(),
                    is_active=True,
                )
            else:
                target_reputation = self.chain_reputations[agent_id][target_chain]
                target_reputation.score = reputation.score
                target_reputation.sync_timestamp = datetime.utcnow()

            # Update sync timestamp
            reputation.sync_timestamp = datetime.utcnow()

            logger.info(f"Synced reputation for agent {agent_id} to chain {target_chain}")
            return True

        except Exception as e:
            logger.error(f"Failed to sync reputation for agent {agent_id}: {e}")
            raise

    async def stake_reputation(self, agent_id: str, amount: int, lock_period: int) -> ReputationStake:
        """Stake reputation tokens"""

        try:
            if agent_id not in self.reputation_data:
                raise ValueError(f"Agent {agent_id} not found")

            if amount < self.min_stake_amount:
                raise ValueError(f"Amount below minimum: {self.min_stake_amount}")

            reputation = self.reputation_data[agent_id]

            # Calculate reward rate based on tier
            reward_rate = self.stake_rewards[reputation.tier]

            # Create stake
            stake = ReputationStake(
                agent_id=agent_id,
                amount=amount,
                lock_period=lock_period,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(seconds=lock_period),
                is_active=True,
                reward_rate=reward_rate,
                multiplier=1.0 + (reputation.score / 10000) * 0.5,  # Up to 50% bonus
            )

            # Store stake
            if agent_id not in self.reputation_stakes:
                self.reputation_stakes[agent_id] = []
            self.reputation_stakes[agent_id].append(stake)

            logger.info(f"Staked {amount} reputation for agent {agent_id}")
            return stake

        except Exception as e:
            logger.error(f"Failed to stake reputation for agent {agent_id}: {e}")
            raise

    async def delegate_reputation(self, delegator: str, delegate: str, amount: int) -> ReputationDelegation:
        """Delegate reputation to another agent"""

        try:
            if delegator not in self.reputation_data:
                raise ValueError(f"Delegator {delegator} not found")

            if delegate not in self.reputation_data:
                raise ValueError(f"Delegate {delegate} not found")

            delegator_reputation = self.reputation_data[delegator]

            # Check delegation limits
            total_delegated = await self._get_total_delegated(delegator)
            max_delegation = int(delegator_reputation.score * self.max_delegation_ratio)

            if total_delegated + amount > max_delegation:
                raise ValueError(f"Exceeds delegation limit: {max_delegation}")

            # Calculate fee rate based on delegate tier
            delegate_reputation = self.reputation_data[delegate]
            fee_rate = 0.02 + (1.0 - delegate_reputation.score / 10000) * 0.08  # 2-10% based on reputation

            # Create delegation
            delegation = ReputationDelegation(
                delegator=delegator,
                delegate=delegate,
                amount=amount,
                start_time=datetime.utcnow(),
                is_active=True,
                fee_rate=fee_rate,
            )

            # Store delegation
            if delegator not in self.reputation_delegations:
                self.reputation_delegations[delegator] = []
            self.reputation_delegations[delegator].append(delegation)

            logger.info(f"Delegated {amount} reputation from {delegator} to {delegate}")
            return delegation

        except Exception as e:
            logger.error(f"Failed to delegate reputation: {e}")
            raise

    async def get_reputation_score(self, agent_id: str, chain_id: int | None = None) -> int:
        """Get reputation score for agent on specific chain"""

        if agent_id not in self.reputation_data:
            return 0

        if chain_id is None or chain_id == self.supported_chains[ChainNetwork.ETHEREUM]:
            return self.reputation_data[agent_id].score

        if agent_id in self.chain_reputations and chain_id in self.chain_reputations[agent_id]:
            return self.chain_reputations[agent_id][chain_id].score

        return 0

    async def get_effective_reputation(self, agent_id: str) -> int:
        """Get effective reputation score including delegations"""

        if agent_id not in self.reputation_data:
            return 0

        base_score = self.reputation_data[agent_id].score

        # Add delegated from others
        delegated_from = await self._get_delegated_from(agent_id)

        # Subtract delegated to others
        delegated_to = await self._get_total_delegated(agent_id)

        return base_score + delegated_from - delegated_to

    async def get_reputation_analytics(self, agent_id: str) -> ReputationAnalytics:
        """Get comprehensive reputation analytics"""

        if agent_id not in self.reputation_data:
            raise ValueError(f"Agent {agent_id} not found")

        reputation = self.reputation_data[agent_id]

        # Calculate metrics
        success_rate = (reputation.success_count / reputation.task_count * 100) if reputation.task_count > 0 else 0
        stake_amount = sum(stake.amount for stake in self.reputation_stakes.get(agent_id, []) if stake.is_active)
        delegation_amount = sum(
            delegation.amount for delegation in self.reputation_delegations.get(agent_id, []) if delegation.is_active
        )
        chain_count = len(self.chain_reputations.get(agent_id, {}))
        reputation_age = (datetime.utcnow() - reputation.last_updated).days

        return ReputationAnalytics(
            agent_id=agent_id,
            total_score=reputation.score,
            effective_score=await self.get_effective_reputation(agent_id),
            success_rate=success_rate,
            stake_amount=stake_amount,
            delegation_amount=delegation_amount,
            chain_count=chain_count,
            tier=reputation.tier,
            reputation_age=reputation_age,
            last_activity=reputation.last_updated,
        )

    async def get_chain_reputations(self, agent_id: str) -> list[ReputationScore]:
        """Get all chain reputations for an agent"""

        if agent_id not in self.chain_reputations:
            return []

        return list(self.chain_reputations[agent_id].values())

    async def get_top_agents(self, limit: int = 100, chain_id: int | None = None) -> list[ReputationAnalytics]:
        """Get top agents by reputation score"""

        analytics = []
        for agent_id in self.reputation_data:
            try:
                agent_analytics = await self.get_reputation_analytics(agent_id)
                if chain_id is None or agent_id in self.chain_reputations and chain_id in self.chain_reputations[agent_id]:
                    analytics.append(agent_analytics)
            except Exception as e:
                logger.error(f"Error getting analytics for agent {agent_id}: {e}")
                continue

        # Sort by effective score
        analytics.sort(key=lambda x: x.effective_score, reverse=True)

        return analytics[:limit]

    async def get_reputation_tier_distribution(self) -> dict[str, int]:
        """Get distribution of agents across reputation tiers"""

        distribution = {tier.value: 0 for tier in ReputationTier}

        for reputation in self.reputation_data.values():
            distribution[reputation.tier.value] += 1

        return distribution

    async def _calculate_score_change(self, event_type: ReputationEvent, weight: int) -> int:
        """Calculate score change based on event type and weight"""

        base_changes = {
            ReputationEvent.TASK_SUCCESS: self.success_bonus,
            ReputationEvent.TASK_FAILURE: self.failure_penalty,
            ReputationEvent.POSITIVE_FEEDBACK: self.success_bonus // 2,
            ReputationEvent.NEGATIVE_FEEDBACK: self.failure_penalty // 2,
            ReputationEvent.TASK_TIMEOUT: self.failure_penalty // 2,
            ReputationEvent.TASK_CANCELLED: self.failure_penalty // 4,
            ReputationEvent.REPUTATION_STAKE: 0,
            ReputationEvent.REPUTATION_DELEGATE: 0,
            ReputationEvent.CROSS_CHAIN_SYNC: 0,
        }

        base_change = base_changes.get(event_type, 0)
        return base_change * weight

    async def _verify_cross_chain_signature(self, agent_id: str, chain_id: int, signature: str) -> str:
        """Verify cross-chain signature (simplified)"""
        # In production, implement proper cross-chain signature verification
        import hashlib

        hash_input = f"{agent_id}:{chain_id}:{datetime.utcnow().isoformat()}".encode()
        return hashlib.sha256(hash_input).hexdigest()

    async def _get_total_delegated(self, agent_id: str) -> int:
        """Get total amount delegated by agent"""

        total = 0
        for delegation in self.reputation_delegations.get(agent_id, []):
            if delegation.is_active:
                total += delegation.amount

        return total

    async def _get_delegated_from(self, agent_id: str) -> int:
        """Get total amount delegated to agent"""

        total = 0
        for _delegator_id, delegations in self.reputation_delegations.items():
            for delegation in delegations:
                if delegation.delegate == agent_id and delegation.is_active:
                    total += delegation.amount

        return total

    async def _load_reputation_data(self):
        """Load existing reputation data"""
        # In production, load from database
        pass

    async def _monitor_reputation_sync(self):
        """Monitor and process reputation sync requests"""
        while True:
            try:
                # Process pending sync requests
                await self._process_pending_syncs()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in reputation sync monitoring: {e}")
                await asyncio.sleep(60)

    async def _process_pending_syncs(self):
        """Process pending cross-chain sync requests"""
        # In production, implement pending sync processing
        pass

    async def _process_stake_rewards(self):
        """Process stake rewards"""
        while True:
            try:
                # Calculate and distribute stake rewards
                await self._distribute_stake_rewards()
                await asyncio.sleep(3600)  # Process every hour
            except Exception as e:
                logger.error(f"Error in stake reward processing: {e}")
                await asyncio.sleep(3600)

    async def _distribute_stake_rewards(self):
        """Distribute rewards for active stakes"""
        current_time = datetime.utcnow()

        for agent_id, stakes in self.reputation_stakes.items():
            for stake in stakes:
                if stake.is_active and current_time >= stake.end_time:
                    # Calculate reward
                    reward_amount = int(stake.amount * stake.reward_rate * (stake.lock_period / 31536000))  # APY calculation

                    # Distribute reward (simplified)
                    logger.info(f"Distributing {reward_amount} reward to {agent_id}")

                    # Mark stake as inactive
                    stake.is_active = False

    async def _cleanup_expired_stakes(self):
        """Clean up expired stakes and delegations"""
        while True:
            try:
                current_time = datetime.utcnow()

                # Clean up expired stakes
                for _agent_id, stakes in self.reputation_stakes.items():
                    for stake in stakes:
                        if stake.is_active and current_time > stake.end_time:
                            stake.is_active = False

                # Clean up expired delegations
                for _delegator_id, delegations in self.reputation_delegations.items():
                    for delegation in delegations:
                        if delegation.is_active and current_time > delegation.start_time + timedelta(days=30):
                            delegation.is_active = False

                await asyncio.sleep(3600)  # Clean up every hour
            except Exception as e:
                logger.error(f"Error in cleanup: {e}")
                await asyncio.sleep(3600)

    async def get_cross_chain_sync_status(self, agent_id: str) -> list[CrossChainSync]:
        """Get cross-chain sync status for agent"""

        return [sync for sync in self.cross_chain_syncs if sync.agent_id == agent_id]

    async def get_reputation_history(self, agent_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Get reputation history for agent"""

        # In production, fetch from database
        return []

    async def export_reputation_data(self, format: str = "json") -> str:
        """Export reputation data"""

        data = {
            "reputation_data": {k: asdict(v) for k, v in self.reputation_data.items()},
            "chain_reputations": {k: {str(k2): asdict(v2) for k2, v2 in v.items()} for k, v in self.chain_reputations.items()},
            "reputation_stakes": {k: [asdict(s) for s in v] for k, v in self.reputation_stakes.items()},
            "reputation_delegations": {k: [asdict(d) for d in v] for k, v in self.reputation_delegations.items()},
            "export_timestamp": datetime.utcnow().isoformat(),
        }

        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def import_reputation_data(self, data: str, format: str = "json"):
        """Import reputation data"""

        if format.lower() == "json":
            parsed_data = json.loads(data)

            # Import reputation data
            for agent_id, rep_data in parsed_data.get("reputation_data", {}).items():
                self.reputation_data[agent_id] = ReputationScore(**rep_data)

            # Import chain reputations
            for agent_id, chain_data in parsed_data.get("chain_reputations", {}).items():
                self.chain_reputations[agent_id] = {
                    int(chain_id): ReputationScore(**rep_data) for chain_id, rep_data in chain_data.items()
                }

            logger.info("Reputation data imported successfully")
        else:
            raise ValueError(f"Unsupported format: {format}")
