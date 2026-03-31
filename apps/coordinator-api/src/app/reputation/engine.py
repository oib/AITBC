"""
Cross-Chain Reputation Engine
Core reputation calculation and aggregation engine for multi-chain agent reputation
"""

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

from sqlmodel import Session, select

from ..domain.cross_chain_reputation import (
    CrossChainReputationAggregation,
    CrossChainReputationConfig,
)
from ..domain.reputation import AgentReputation, ReputationEvent, ReputationLevel


class CrossChainReputationEngine:
    """Core reputation calculation and aggregation engine"""

    def __init__(self, session: Session):
        self.session = session

    async def calculate_reputation_score(
        self, agent_id: str, chain_id: int, transaction_data: dict[str, Any] | None = None
    ) -> float:
        """Calculate reputation score for an agent on a specific chain"""

        try:
            # Get existing reputation
            stmt = select(AgentReputation).where(
                AgentReputation.agent_id == agent_id,
                AgentReputation.chain_id == chain_id if hasattr(AgentReputation, "chain_id") else True,
            )

            # Handle case where existing reputation doesn't have chain_id
            if not hasattr(AgentReputation, "chain_id"):
                stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)

            reputation = self.session.exec(stmt).first()

            if reputation:
                # Update existing reputation based on transaction data
                score = await self._update_reputation_from_transaction(reputation, transaction_data)
            else:
                # Create new reputation with base score
                config = await self._get_chain_config(chain_id)
                base_score = config.base_reputation_bonus if config else 0.0
                score = max(0.0, min(1.0, base_score))

                # Create new reputation record
                new_reputation = AgentReputation(
                    agent_id=agent_id,
                    trust_score=score * 1000,  # Convert to 0-1000 scale
                    reputation_level=self._determine_reputation_level(score),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                self.session.add(new_reputation)
                self.session.commit()

            return score

        except Exception as e:
            logger.error(f"Error calculating reputation for agent {agent_id} on chain {chain_id}: {e}")
            return 0.0

    async def aggregate_cross_chain_reputation(self, agent_id: str) -> dict[int, float]:
        """Aggregate reputation scores across all chains for an agent"""

        try:
            # Get all reputation records for the agent
            stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)
            reputations = self.session.exec(stmt).all()

            if not reputations:
                return {}

            # Get chain configurations
            chain_configs = {}
            for reputation in reputations:
                chain_id = getattr(reputation, "chain_id", 1)  # Default to chain 1 if not set
                config = await self._get_chain_config(chain_id)
                chain_configs[chain_id] = config

            # Calculate weighted scores
            chain_scores = {}
            total_weight = 0.0
            weighted_sum = 0.0

            for reputation in reputations:
                chain_id = getattr(reputation, "chain_id", 1)
                config = chain_configs.get(chain_id)

                if config and config.is_active:
                    # Convert trust score to 0-1 scale
                    score = min(1.0, reputation.trust_score / 1000.0)
                    weight = config.chain_weight

                    chain_scores[chain_id] = score
                    total_weight += weight
                    weighted_sum += score * weight

            # Normalize scores
            if total_weight > 0:
                normalized_scores = {
                    chain_id: score * (total_weight / len(chain_scores)) for chain_id, score in chain_scores.items()
                }
            else:
                normalized_scores = chain_scores

            # Store aggregation
            await self._store_cross_chain_aggregation(agent_id, chain_scores, normalized_scores)

            return chain_scores

        except Exception as e:
            logger.error(f"Error aggregating cross-chain reputation for agent {agent_id}: {e}")
            return {}

    async def update_reputation_from_event(self, event_data: dict[str, Any]) -> bool:
        """Update reputation from a reputation-affecting event"""

        try:
            agent_id = event_data["agent_id"]
            chain_id = event_data.get("chain_id", 1)
            event_type = event_data["event_type"]
            impact_score = event_data["impact_score"]

            # Get existing reputation
            stmt = select(AgentReputation).where(
                AgentReputation.agent_id == agent_id,
                AgentReputation.chain_id == chain_id if hasattr(AgentReputation, "chain_id") else True,
            )

            if not hasattr(AgentReputation, "chain_id"):
                stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)

            reputation = self.session.exec(stmt).first()

            if not reputation:
                # Create new reputation record
                config = await self._get_chain_config(chain_id)
                base_score = config.base_reputation_bonus if config else 0.0

                reputation = AgentReputation(
                    agent_id=agent_id,
                    trust_score=max(0, min(1000, (base_score + impact_score) * 1000)),
                    reputation_level=self._determine_reputation_level(base_score + impact_score),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                self.session.add(reputation)
            else:
                # Update existing reputation
                old_score = reputation.trust_score / 1000.0
                new_score = max(0.0, min(1.0, old_score + impact_score))

                reputation.trust_score = new_score * 1000
                reputation.reputation_level = self._determine_reputation_level(new_score)
                reputation.updated_at = datetime.utcnow()

            # Create reputation event record
            event = ReputationEvent(
                agent_id=agent_id,
                event_type=event_type,
                impact_score=impact_score,
                trust_score_before=reputation.trust_score - (impact_score * 1000),
                trust_score_after=reputation.trust_score,
                event_data=event_data,
                occurred_at=datetime.utcnow(),
            )

            self.session.add(event)
            self.session.commit()

            # Update cross-chain aggregation
            await self.aggregate_cross_chain_reputation(agent_id)

            logger.info(f"Updated reputation for agent {agent_id} from {event_type} event")
            return True

        except Exception as e:
            logger.error(f"Error updating reputation from event: {e}")
            return False

    async def get_reputation_trend(self, agent_id: str, days: int = 30) -> list[float]:
        """Get reputation trend for an agent over specified days"""

        try:
            # Get reputation events for the period
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            stmt = (
                select(ReputationEvent)
                .where(ReputationEvent.agent_id == agent_id, ReputationEvent.occurred_at >= cutoff_date)
                .order_by(ReputationEvent.occurred_at)
            )

            events = self.session.exec(stmt).all()

            # Extract scores from events
            scores = []
            for event in events:
                if event.trust_score_after is not None:
                    scores.append(event.trust_score_after / 1000.0)  # Convert to 0-1 scale

            return scores

        except Exception as e:
            logger.error(f"Error getting reputation trend for agent {agent_id}: {e}")
            return []

    async def detect_reputation_anomalies(self, agent_id: str) -> list[dict[str, Any]]:
        """Detect reputation anomalies for an agent"""

        try:
            anomalies = []

            # Get recent reputation events
            stmt = (
                select(ReputationEvent)
                .where(ReputationEvent.agent_id == agent_id)
                .order_by(ReputationEvent.occurred_at.desc())
                .limit(10)
            )

            events = self.session.exec(stmt).all()

            if len(events) < 2:
                return anomalies

            # Check for sudden score changes
            for i in range(len(events) - 1):
                current_event = events[i]
                previous_event = events[i + 1]

                if current_event.trust_score_after and previous_event.trust_score_after:
                    score_change = abs(current_event.trust_score_after - previous_event.trust_score_after) / 1000.0

                    if score_change > 0.3:  # 30% change threshold
                        anomalies.append(
                            {
                                "agent_id": agent_id,
                                "chain_id": getattr(current_event, "chain_id", 1),
                                "anomaly_type": "sudden_score_change",
                                "detected_at": current_event.occurred_at,
                                "description": f"Sudden reputation change of {score_change:.2f}",
                                "severity": "high" if score_change > 0.5 else "medium",
                                "previous_score": previous_event.trust_score_after / 1000.0,
                                "current_score": current_event.trust_score_after / 1000.0,
                                "score_change": score_change,
                                "confidence": min(1.0, score_change / 0.3),
                            }
                        )

            return anomalies

        except Exception as e:
            logger.error(f"Error detecting reputation anomalies for agent {agent_id}: {e}")
            return []

    async def _update_reputation_from_transaction(
        self, reputation: AgentReputation, transaction_data: dict[str, Any] | None
    ) -> float:
        """Update reputation based on transaction data"""

        if not transaction_data:
            return reputation.trust_score / 1000.0

        # Extract transaction metrics
        success = transaction_data.get("success", True)
        gas_efficiency = transaction_data.get("gas_efficiency", 0.5)
        response_time = transaction_data.get("response_time", 1.0)

        # Calculate impact based on transaction outcome
        config = await self._get_chain_config(getattr(reputation, "chain_id", 1))

        if success:
            impact = config.transaction_success_weight if config else 0.1
            impact *= gas_efficiency  # Bonus for gas efficiency
            impact *= 2.0 - min(response_time, 2.0)  # Bonus for fast response
        else:
            impact = config.transaction_failure_weight if config else -0.2

        # Update reputation
        old_score = reputation.trust_score / 1000.0
        new_score = max(0.0, min(1.0, old_score + impact))

        reputation.trust_score = new_score * 1000
        reputation.reputation_level = self._determine_reputation_level(new_score)
        reputation.updated_at = datetime.utcnow()

        # Update transaction metrics if available
        if "transaction_count" in transaction_data:
            reputation.transaction_count = transaction_data["transaction_count"]

        self.session.commit()

        return new_score

    async def _get_chain_config(self, chain_id: int) -> CrossChainReputationConfig | None:
        """Get configuration for a specific chain"""

        stmt = select(CrossChainReputationConfig).where(
            CrossChainReputationConfig.chain_id == chain_id, CrossChainReputationConfig.is_active
        )

        config = self.session.exec(stmt).first()

        if not config:
            # Create default config
            config = CrossChainReputationConfig(
                chain_id=chain_id,
                chain_weight=1.0,
                base_reputation_bonus=0.0,
                transaction_success_weight=0.1,
                transaction_failure_weight=-0.2,
                dispute_penalty_weight=-0.3,
                minimum_transactions_for_score=5,
                reputation_decay_rate=0.01,
                anomaly_detection_threshold=0.3,
            )

            self.session.add(config)
            self.session.commit()

        return config

    async def _store_cross_chain_aggregation(
        self, agent_id: str, chain_scores: dict[int, float], normalized_scores: dict[int, float]
    ) -> None:
        """Store cross-chain reputation aggregation"""

        try:
            # Calculate aggregation metrics
            if chain_scores:
                avg_score = sum(chain_scores.values()) / len(chain_scores)
                variance = sum((score - avg_score) ** 2 for score in chain_scores.values()) / len(chain_scores)
                score_range = max(chain_scores.values()) - min(chain_scores.values())
                consistency_score = max(0.0, 1.0 - (variance / 0.25))  # Normalize variance
            else:
                avg_score = 0.0
                variance = 0.0
                score_range = 0.0
                consistency_score = 1.0

            # Check if aggregation already exists
            stmt = select(CrossChainReputationAggregation).where(CrossChainReputationAggregation.agent_id == agent_id)

            aggregation = self.session.exec(stmt).first()

            if aggregation:
                # Update existing aggregation
                aggregation.aggregated_score = avg_score
                aggregation.chain_scores = chain_scores
                aggregation.active_chains = list(chain_scores.keys())
                aggregation.score_variance = variance
                aggregation.score_range = score_range
                aggregation.consistency_score = consistency_score
                aggregation.last_updated = datetime.utcnow()
            else:
                # Create new aggregation
                aggregation = CrossChainReputationAggregation(
                    agent_id=agent_id,
                    aggregated_score=avg_score,
                    chain_scores=chain_scores,
                    active_chains=list(chain_scores.keys()),
                    score_variance=variance,
                    score_range=score_range,
                    consistency_score=consistency_score,
                    verification_status="pending",
                    created_at=datetime.utcnow(),
                    last_updated=datetime.utcnow(),
                )

                self.session.add(aggregation)

            self.session.commit()

        except Exception as e:
            logger.error(f"Error storing cross-chain aggregation for agent {agent_id}: {e}")

    def _determine_reputation_level(self, score: float) -> ReputationLevel:
        """Determine reputation level based on score"""

        if score >= 0.9:
            return ReputationLevel.MASTER
        elif score >= 0.8:
            return ReputationLevel.EXPERT
        elif score >= 0.6:
            return ReputationLevel.ADVANCED
        elif score >= 0.4:
            return ReputationLevel.INTERMEDIATE
        elif score >= 0.2:
            return ReputationLevel.BEGINNER
        else:
            return ReputationLevel.BEGINNER  # Map to existing levels

    async def get_agent_reputation_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive reputation summary for an agent"""

        try:
            # Get basic reputation
            stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)
            reputation = self.session.exec(stmt).first()

            if not reputation:
                return {
                    "agent_id": agent_id,
                    "trust_score": 0.0,
                    "reputation_level": ReputationLevel.BEGINNER,
                    "total_transactions": 0,
                    "success_rate": 0.0,
                    "cross_chain": {"aggregated_score": 0.0, "chain_count": 0, "active_chains": [], "consistency_score": 1.0},
                }

            # Get cross-chain aggregation
            stmt = select(CrossChainReputationAggregation).where(CrossChainReputationAggregation.agent_id == agent_id)
            aggregation = self.session.exec(stmt).first()

            # Get reputation trend
            trend = await self.get_reputation_trend(agent_id, 30)

            # Get anomalies
            anomalies = await self.detect_reputation_anomalies(agent_id)

            return {
                "agent_id": agent_id,
                "trust_score": reputation.trust_score,
                "reputation_level": reputation.reputation_level,
                "performance_rating": getattr(reputation, "performance_rating", 3.0),
                "reliability_score": getattr(reputation, "reliability_score", 50.0),
                "total_transactions": getattr(reputation, "transaction_count", 0),
                "success_rate": getattr(reputation, "success_rate", 0.0),
                "dispute_count": getattr(reputation, "dispute_count", 0),
                "last_activity": getattr(reputation, "last_activity", datetime.utcnow()),
                "cross_chain": {
                    "aggregated_score": aggregation.aggregated_score if aggregation else 0.0,
                    "chain_count": aggregation.chain_count if aggregation else 0,
                    "active_chains": aggregation.active_chains if aggregation else [],
                    "consistency_score": aggregation.consistency_score if aggregation else 1.0,
                    "chain_scores": aggregation.chain_scores if aggregation else {},
                },
                "trend": trend,
                "anomalies": anomalies,
                "created_at": reputation.created_at,
                "updated_at": reputation.updated_at,
            }

        except Exception as e:
            logger.error(f"Error getting reputation summary for agent {agent_id}: {e}")
            return {"agent_id": agent_id, "error": str(e)}
