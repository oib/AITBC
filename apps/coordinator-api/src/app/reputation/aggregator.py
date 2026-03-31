"""
Cross-Chain Reputation Aggregator
Aggregates reputation data from multiple blockchains and normalizes scores
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

from sqlmodel import Session, select

from ..domain.cross_chain_reputation import (
    CrossChainReputationAggregation,
    CrossChainReputationConfig,
)
from ..domain.reputation import AgentReputation, ReputationEvent


class CrossChainReputationAggregator:
    """Aggregates reputation data from multiple blockchains"""

    def __init__(self, session: Session, blockchain_clients: dict[int, Any] | None = None):
        self.session = session
        self.blockchain_clients = blockchain_clients or {}

    async def collect_chain_reputation_data(self, chain_id: int) -> list[dict[str, Any]]:
        """Collect reputation data from a specific blockchain"""

        try:
            # Get all reputations for the chain
            stmt = select(AgentReputation).where(
                AgentReputation.chain_id == chain_id if hasattr(AgentReputation, "chain_id") else True
            )

            # Handle case where reputation doesn't have chain_id
            if not hasattr(AgentReputation, "chain_id"):
                # For now, return all reputations (assume they're on the primary chain)
                stmt = select(AgentReputation)

            reputations = self.session.exec(stmt).all()

            chain_data = []
            for reputation in reputations:
                chain_data.append(
                    {
                        "agent_id": reputation.agent_id,
                        "trust_score": reputation.trust_score,
                        "reputation_level": reputation.reputation_level,
                        "total_transactions": getattr(reputation, "transaction_count", 0),
                        "success_rate": getattr(reputation, "success_rate", 0.0),
                        "dispute_count": getattr(reputation, "dispute_count", 0),
                        "last_updated": reputation.updated_at,
                        "chain_id": getattr(reputation, "chain_id", chain_id),
                    }
                )

            return chain_data

        except Exception as e:
            logger.error(f"Error collecting reputation data for chain {chain_id}: {e}")
            return []

    async def normalize_reputation_scores(self, scores: dict[int, float]) -> float:
        """Normalize reputation scores across chains"""

        try:
            if not scores:
                return 0.0

            # Get chain configurations
            chain_configs = {}
            for chain_id in scores.keys():
                config = await self._get_chain_config(chain_id)
                chain_configs[chain_id] = config

            # Apply chain-specific normalization
            normalized_scores = {}
            total_weight = 0.0
            weighted_sum = 0.0

            for chain_id, score in scores.items():
                config = chain_configs.get(chain_id)

                if config and config.is_active:
                    # Apply chain weight
                    weight = config.chain_weight
                    normalized_score = score * weight

                    normalized_scores[chain_id] = normalized_score
                    total_weight += weight
                    weighted_sum += normalized_score

            # Calculate final normalized score
            if total_weight > 0:
                final_score = weighted_sum / total_weight
            else:
                # If no valid configurations, use simple average
                final_score = sum(scores.values()) / len(scores)

            return max(0.0, min(1.0, final_score))

        except Exception as e:
            logger.error(f"Error normalizing reputation scores: {e}")
            return 0.0

    async def apply_chain_weighting(self, scores: dict[int, float]) -> dict[int, float]:
        """Apply chain-specific weighting to reputation scores"""

        try:
            weighted_scores = {}

            for chain_id, score in scores.items():
                config = await self._get_chain_config(chain_id)

                if config and config.is_active:
                    weight = config.chain_weight
                    weighted_scores[chain_id] = score * weight
                else:
                    # Default weight if no config
                    weighted_scores[chain_id] = score

            return weighted_scores

        except Exception as e:
            logger.error(f"Error applying chain weighting: {e}")
            return scores

    async def detect_reputation_anomalies(self, agent_id: str) -> list[dict[str, Any]]:
        """Detect reputation anomalies across chains"""

        try:
            anomalies = []

            # Get cross-chain aggregation
            stmt = select(CrossChainReputationAggregation).where(CrossChainReputationAggregation.agent_id == agent_id)
            aggregation = self.session.exec(stmt).first()

            if not aggregation:
                return anomalies

            # Check for consistency anomalies
            if aggregation.consistency_score < 0.7:
                anomalies.append(
                    {
                        "agent_id": agent_id,
                        "anomaly_type": "low_consistency",
                        "detected_at": datetime.utcnow(),
                        "description": f"Low consistency score: {aggregation.consistency_score:.2f}",
                        "severity": "high" if aggregation.consistency_score < 0.5 else "medium",
                        "consistency_score": aggregation.consistency_score,
                        "score_variance": aggregation.score_variance,
                        "score_range": aggregation.score_range,
                    }
                )

            # Check for score variance anomalies
            if aggregation.score_variance > 0.25:
                anomalies.append(
                    {
                        "agent_id": agent_id,
                        "anomaly_type": "high_variance",
                        "detected_at": datetime.utcnow(),
                        "description": f"High score variance: {aggregation.score_variance:.2f}",
                        "severity": "high" if aggregation.score_variance > 0.5 else "medium",
                        "score_variance": aggregation.score_variance,
                        "score_range": aggregation.score_range,
                        "chain_scores": aggregation.chain_scores,
                    }
                )

            # Check for missing chain data
            expected_chains = await self._get_active_chain_ids()
            missing_chains = set(expected_chains) - set(aggregation.active_chains)

            if missing_chains:
                anomalies.append(
                    {
                        "agent_id": agent_id,
                        "anomaly_type": "missing_chain_data",
                        "detected_at": datetime.utcnow(),
                        "description": f"Missing data for chains: {list(missing_chains)}",
                        "severity": "medium",
                        "missing_chains": list(missing_chains),
                        "active_chains": aggregation.active_chains,
                    }
                )

            return anomalies

        except Exception as e:
            logger.error(f"Error detecting reputation anomalies for agent {agent_id}: {e}")
            return []

    async def batch_update_reputations(self, updates: list[dict[str, Any]]) -> dict[str, bool]:
        """Batch update reputation scores for multiple agents"""

        try:
            results = {}

            for update in updates:
                agent_id = update["agent_id"]
                chain_id = update.get("chain_id", 1)
                new_score = update["score"]

                try:
                    # Get existing reputation
                    stmt = select(AgentReputation).where(
                        AgentReputation.agent_id == agent_id,
                        AgentReputation.chain_id == chain_id if hasattr(AgentReputation, "chain_id") else True,
                    )

                    if not hasattr(AgentReputation, "chain_id"):
                        stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)

                    reputation = self.session.exec(stmt).first()

                    if reputation:
                        # Update reputation
                        reputation.trust_score = new_score * 1000  # Convert to 0-1000 scale
                        reputation.reputation_level = self._determine_reputation_level(new_score)
                        reputation.updated_at = datetime.utcnow()

                        # Create event record
                        event = ReputationEvent(
                            agent_id=agent_id,
                            event_type="batch_update",
                            impact_score=new_score - (reputation.trust_score / 1000.0),
                            trust_score_before=reputation.trust_score,
                            trust_score_after=reputation.trust_score,
                            event_data=update,
                            occurred_at=datetime.utcnow(),
                        )

                        self.session.add(event)
                        results[agent_id] = True
                    else:
                        # Create new reputation
                        reputation = AgentReputation(
                            agent_id=agent_id,
                            trust_score=new_score * 1000,
                            reputation_level=self._determine_reputation_level(new_score),
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )

                        self.session.add(reputation)
                        results[agent_id] = True

                except Exception as e:
                    logger.error(f"Error updating reputation for agent {agent_id}: {e}")
                    results[agent_id] = False

            self.session.commit()

            # Update cross-chain aggregations
            for agent_id in updates:
                if results.get(agent_id):
                    await self._update_cross_chain_aggregation(agent_id)

            return results

        except Exception as e:
            logger.error(f"Error in batch reputation update: {e}")
            return {update["agent_id"]: False for update in updates}

    async def get_chain_statistics(self, chain_id: int) -> dict[str, Any]:
        """Get reputation statistics for a specific chain"""

        try:
            # Get all reputations for the chain
            stmt = select(AgentReputation).where(
                AgentReputation.chain_id == chain_id if hasattr(AgentReputation, "chain_id") else True
            )

            if not hasattr(AgentReputation, "chain_id"):
                # For now, get all reputations
                stmt = select(AgentReputation)

            reputations = self.session.exec(stmt).all()

            if not reputations:
                return {
                    "chain_id": chain_id,
                    "total_agents": 0,
                    "average_reputation": 0.0,
                    "reputation_distribution": {},
                    "total_transactions": 0,
                    "success_rate": 0.0,
                }

            # Calculate statistics
            total_agents = len(reputations)
            total_reputation = sum(rep.trust_score for rep in reputations)
            average_reputation = total_reputation / total_agents / 1000.0  # Convert to 0-1 scale

            # Reputation distribution
            distribution = {}
            for reputation in reputations:
                level = reputation.reputation_level.value
                distribution[level] = distribution.get(level, 0) + 1

            # Transaction statistics
            total_transactions = sum(getattr(rep, "transaction_count", 0) for rep in reputations)
            successful_transactions = sum(
                getattr(rep, "transaction_count", 0) * getattr(rep, "success_rate", 0) / 100.0 for rep in reputations
            )
            success_rate = successful_transactions / max(total_transactions, 1)

            return {
                "chain_id": chain_id,
                "total_agents": total_agents,
                "average_reputation": average_reputation,
                "reputation_distribution": distribution,
                "total_transactions": total_transactions,
                "success_rate": success_rate,
                "last_updated": datetime.utcnow(),
            }

        except Exception as e:
            logger.error(f"Error getting chain statistics for chain {chain_id}: {e}")
            return {"chain_id": chain_id, "error": str(e), "total_agents": 0, "average_reputation": 0.0}

    async def sync_cross_chain_reputations(self, agent_ids: list[str]) -> dict[str, bool]:
        """Synchronize reputation data across chains for multiple agents"""

        try:
            results = {}

            for agent_id in agent_ids:
                try:
                    # Re-aggregate cross-chain reputation
                    await self._update_cross_chain_aggregation(agent_id)
                    results[agent_id] = True

                except Exception as e:
                    logger.error(f"Error syncing cross-chain reputation for agent {agent_id}: {e}")
                    results[agent_id] = False

            return results

        except Exception as e:
            logger.error(f"Error in cross-chain reputation sync: {e}")
            return dict.fromkeys(agent_ids, False)

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

    async def _get_active_chain_ids(self) -> list[int]:
        """Get list of active chain IDs"""

        try:
            stmt = select(CrossChainReputationConfig.chain_id).where(CrossChainReputationConfig.is_active)

            configs = self.session.exec(stmt).all()
            return [config.chain_id for config in configs]

        except Exception as e:
            logger.error(f"Error getting active chain IDs: {e}")
            return [1]  # Default to Ethereum mainnet

    async def _update_cross_chain_aggregation(self, agent_id: str) -> None:
        """Update cross-chain aggregation for an agent"""

        try:
            # Get all reputations for the agent
            stmt = select(AgentReputation).where(AgentReputation.agent_id == agent_id)
            reputations = self.session.exec(stmt).all()

            if not reputations:
                return

            # Extract chain scores
            chain_scores = {}
            for reputation in reputations:
                chain_id = getattr(reputation, "chain_id", 1)
                chain_scores[chain_id] = reputation.trust_score / 1000.0  # Convert to 0-1 scale

            # Apply weighting
            await self.apply_chain_weighting(chain_scores)

            # Calculate aggregation metrics
            if chain_scores:
                avg_score = sum(chain_scores.values()) / len(chain_scores)
                variance = sum((score - avg_score) ** 2 for score in chain_scores.values()) / len(chain_scores)
                score_range = max(chain_scores.values()) - min(chain_scores.values())
                consistency_score = max(0.0, 1.0 - (variance / 0.25))
            else:
                avg_score = 0.0
                variance = 0.0
                score_range = 0.0
                consistency_score = 1.0

            # Update or create aggregation
            stmt = select(CrossChainReputationAggregation).where(CrossChainReputationAggregation.agent_id == agent_id)

            aggregation = self.session.exec(stmt).first()

            if aggregation:
                aggregation.aggregated_score = avg_score
                aggregation.chain_scores = chain_scores
                aggregation.active_chains = list(chain_scores.keys())
                aggregation.score_variance = variance
                aggregation.score_range = score_range
                aggregation.consistency_score = consistency_score
                aggregation.last_updated = datetime.utcnow()
            else:
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
            logger.error(f"Error updating cross-chain aggregation for agent {agent_id}: {e}")

    def _determine_reputation_level(self, score: float) -> str:
        """Determine reputation level based on score"""

        # Map to existing reputation levels
        if score >= 0.9:
            return "master"
        elif score >= 0.8:
            return "expert"
        elif score >= 0.6:
            return "advanced"
        elif score >= 0.4:
            return "intermediate"
        elif score >= 0.2:
            return "beginner"
        else:
            return "beginner"
