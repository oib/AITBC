"""
Ecosystem Analytics Service
Business logic for developer ecosystem metrics and analytics
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta
import uuid

from ..domain.bounty import (
    EcosystemMetrics, BountyStats, AgentMetrics, AgentStake,
    Bounty, BountySubmission, BountyStatus, PerformanceTier
)
from ..storage import get_session
from ..app_logging import get_logger



class EcosystemService:
    """Service for ecosystem analytics and metrics"""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def get_developer_earnings(self, period: str = "monthly") -> Dict[str, Any]:
        """Get developer earnings metrics"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.utcnow() - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get total earnings from completed bounties
            earnings_stmt = select(
                func.sum(Bounty.reward_amount).label('total_earnings'),
                func.count(func.distinct(Bounty.winner_address)).label('unique_earners'),
                func.avg(Bounty.reward_amount).label('average_earnings')
            ).where(
                and_(
                    Bounty.status == BountyStatus.COMPLETED,
                    Bounty.creation_time >= start_date
                )
            )
            
            earnings_result = self.session.execute(earnings_stmt).first()
            
            total_earnings = earnings_result.total_earnings or 0.0
            unique_earners = earnings_result.unique_earners or 0
            average_earnings = earnings_result.average_earnings or 0.0
            
            # Get top earners
            top_earners_stmt = select(
                Bounty.winner_address,
                func.sum(Bounty.reward_amount).label('total_earned'),
                func.count(Bounty.bounty_id).label('bounties_won')
            ).where(
                and_(
                    Bounty.status == BountyStatus.COMPLETED,
                    Bounty.creation_time >= start_date,
                    Bounty.winner_address.isnot(None)
                )
            ).group_by(Bounty.winner_address).order_by(
                func.sum(Bounty.reward_amount).desc()
            ).limit(10)
            
            top_earners_result = self.session.execute(top_earners_stmt).all()
            
            top_earners = [
                {
                    "address": row.winner_address,
                    "total_earned": float(row.total_earned),
                    "bounties_won": row.bounties_won,
                    "rank": i + 1
                }
                for i, row in enumerate(top_earners_result)
            ]
            
            # Calculate earnings growth (compare with previous period)
            previous_start = start_date - timedelta(days=30) if period == "monthly" else start_date - timedelta(days=7)
            previous_earnings_stmt = select(func.sum(Bounty.reward_amount)).where(
                and_(
                    Bounty.status == BountyStatus.COMPLETED,
                    Bounty.creation_time >= previous_start,
                    Bounty.creation_time < start_date
                )
            )
            
            previous_earnings = self.session.execute(previous_earnings_stmt).scalar() or 0.0
            earnings_growth = ((total_earnings - previous_earnings) / previous_earnings * 100) if previous_earnings > 0 else 0.0
            
            return {
                "total_earnings": total_earnings,
                "average_earnings": average_earnings,
                "top_earners": top_earners,
                "earnings_growth": earnings_growth,
                "active_developers": unique_earners
            }
            
        except Exception as e:
            logger.error(f"Failed to get developer earnings: {e}")
            raise
    
    async def get_agent_utilization(self, period: str = "monthly") -> Dict[str, Any]:
        """Get agent utilization metrics"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.utcnow() - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get agent metrics
            agents_stmt = select(
                func.count(AgentMetrics.agent_wallet).label('total_agents'),
                func.sum(AgentMetrics.total_submissions).label('total_submissions'),
                func.avg(AgentMetrics.average_accuracy).label('avg_accuracy')
            ).where(
                AgentMetrics.last_update_time >= start_date
            )
            
            agents_result = self.session.execute(agents_stmt).first()
            
            total_agents = agents_result.total_agents or 0
            total_submissions = agents_result.total_submissions or 0
            average_accuracy = agents_result.avg_accuracy or 0.0
            
            # Get active agents (with submissions in period)
            active_agents_stmt = select(func.count(func.distinct(BountySubmission.submitter_address))).where(
                BountySubmission.submission_time >= start_date
            )
            active_agents = self.session.execute(active_agents_stmt).scalar() or 0
            
            # Calculate utilization rate
            utilization_rate = (active_agents / total_agents * 100) if total_agents > 0 else 0.0
            
            # Get top utilized agents
            top_agents_stmt = select(
                BountySubmission.submitter_address,
                func.count(BountySubmission.submission_id).label('submissions'),
                func.avg(BountySubmission.accuracy).label('avg_accuracy')
            ).where(
                BountySubmission.submission_time >= start_date
            ).group_by(BountySubmission.submitter_address).order_by(
                func.count(BountySubmission.submission_id).desc()
            ).limit(10)
            
            top_agents_result = self.session.execute(top_agents_stmt).all()
            
            top_utilized_agents = [
                {
                    "agent_wallet": row.submitter_address,
                    "submissions": row.submissions,
                    "avg_accuracy": float(row.avg_accuracy),
                    "rank": i + 1
                }
                for i, row in enumerate(top_agents_result)
            ]
            
            # Get performance distribution
            performance_stmt = select(
                AgentMetrics.current_tier,
                func.count(AgentMetrics.agent_wallet).label('count')
            ).where(
                AgentMetrics.last_update_time >= start_date
            ).group_by(AgentMetrics.current_tier)
            
            performance_result = self.session.execute(performance_stmt).all()
            performance_distribution = {row.current_tier.value: row.count for row in performance_result}
            
            return {
                "total_agents": total_agents,
                "active_agents": active_agents,
                "utilization_rate": utilization_rate,
                "top_utilized_agents": top_utilized_agents,
                "average_performance": average_accuracy,
                "performance_distribution": performance_distribution
            }
            
        except Exception as e:
            logger.error(f"Failed to get agent utilization: {e}")
            raise
    
    async def get_treasury_allocation(self, period: str = "monthly") -> Dict[str, Any]:
        """Get DAO treasury allocation metrics"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.utcnow() - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get bounty fees (treasury inflow)
            inflow_stmt = select(
                func.sum(Bounty.creation_fee + Bounty.success_fee + Bounty.platform_fee).label('total_inflow')
            ).where(
                Bounty.creation_time >= start_date
            )
            
            total_inflow = self.session.execute(inflow_stmt).scalar() or 0.0
            
            # Get rewards paid (treasury outflow)
            outflow_stmt = select(
                func.sum(Bounty.reward_amount).label('total_outflow')
            ).where(
                and_(
                    Bounty.status == BountyStatus.COMPLETED,
                    Bounty.creation_time >= start_date
                )
            )
            
            total_outflow = self.session.execute(outflow_stmt).scalar() or 0.0
            
            # Calculate DAO revenue (fees - rewards)
            dao_revenue = total_inflow - total_outflow
            
            # Get allocation breakdown by category
            allocation_breakdown = {
                "bounty_fees": total_inflow,
                "rewards_paid": total_outflow,
                "platform_revenue": dao_revenue
            }
            
            # Calculate burn rate
            burn_rate = (total_outflow / total_inflow * 100) if total_inflow > 0 else 0.0
            
            # Mock treasury balance (would come from actual treasury tracking)
            treasury_balance = 1000000.0  # Mock value
            
            return {
                "treasury_balance": treasury_balance,
                "total_inflow": total_inflow,
                "total_outflow": total_outflow,
                "dao_revenue": dao_revenue,
                "allocation_breakdown": allocation_breakdown,
                "burn_rate": burn_rate
            }
            
        except Exception as e:
            logger.error(f"Failed to get treasury allocation: {e}")
            raise
    
    async def get_staking_metrics(self, period: str = "monthly") -> Dict[str, Any]:
        """Get staking system metrics"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.utcnow() - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get staking metrics
            staking_stmt = select(
                func.sum(AgentStake.amount).label('total_staked'),
                func.count(func.distinct(AgentStake.staker_address)).label('total_stakers'),
                func.avg(AgentStake.current_apy).label('avg_apy')
            ).where(
                AgentStake.start_time >= start_date
            )
            
            staking_result = self.session.execute(staking_stmt).first()
            
            total_staked = staking_result.total_staked or 0.0
            total_stakers = staking_result.total_stakers or 0
            average_apy = staking_result.avg_apy or 0.0
            
            # Get total rewards distributed
            rewards_stmt = select(
                func.sum(AgentMetrics.total_rewards_distributed).label('total_rewards')
            ).where(
                AgentMetrics.last_update_time >= start_date
            )
            
            total_rewards = self.session.execute(rewards_stmt).scalar() or 0.0
            
            # Get top staking pools
            top_pools_stmt = select(
                AgentStake.agent_wallet,
                func.sum(AgentStake.amount).label('total_staked'),
                func.count(AgentStake.stake_id).label('stake_count'),
                func.avg(AgentStake.current_apy).label('avg_apy')
            ).where(
                AgentStake.start_time >= start_date
            ).group_by(AgentStake.agent_wallet).order_by(
                func.sum(AgentStake.amount).desc()
            ).limit(10)
            
            top_pools_result = self.session.execute(top_pools_stmt).all()
            
            top_staking_pools = [
                {
                    "agent_wallet": row.agent_wallet,
                    "total_staked": float(row.total_staked),
                    "stake_count": row.stake_count,
                    "avg_apy": float(row.avg_apy),
                    "rank": i + 1
                }
                for i, row in enumerate(top_pools_result)
            ]
            
            # Get tier distribution
            tier_stmt = select(
                AgentStake.agent_tier,
                func.count(AgentStake.stake_id).label('count')
            ).where(
                AgentStake.start_time >= start_date
            ).group_by(AgentStake.agent_tier)
            
            tier_result = self.session.execute(tier_stmt).all()
            tier_distribution = {row.agent_tier.value: row.count for row in tier_result}
            
            return {
                "total_staked": total_staked,
                "total_stakers": total_stakers,
                "average_apy": average_apy,
                "staking_rewards_total": total_rewards,
                "top_staking_pools": top_staking_pools,
                "tier_distribution": tier_distribution
            }
            
        except Exception as e:
            logger.error(f"Failed to get staking metrics: {e}")
            raise
    
    async def get_bounty_analytics(self, period: str = "monthly") -> Dict[str, Any]:
        """Get bounty system analytics"""
        try:
            # Calculate time period
            if period == "daily":
                start_date = datetime.utcnow() - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.utcnow() - timedelta(days=30)
            else:
                start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get bounty counts
            bounty_stmt = select(
                func.count(Bounty.bounty_id).label('total_bounties'),
                func.count(func.distinct(Bounty.bounty_id)).filter(
                    Bounty.status == BountyStatus.ACTIVE
                ).label('active_bounties')
            ).where(
                Bounty.creation_time >= start_date
            )
            
            bounty_result = self.session.execute(bounty_stmt).first()
            
            total_bounties = bounty_result.total_bounties or 0
            active_bounties = bounty_result.active_bounties or 0
            
            # Get completion rate
            completed_stmt = select(func.count(Bounty.bounty_id)).where(
                and_(
                    Bounty.creation_time >= start_date,
                    Bounty.status == BountyStatus.COMPLETED
                )
            )
            
            completed_bounties = self.session.execute(completed_stmt).scalar() or 0
            completion_rate = (completed_bounties / total_bounties * 100) if total_bounties > 0 else 0.0
            
            # Get average reward and volume
            reward_stmt = select(
                func.avg(Bounty.reward_amount).label('avg_reward'),
                func.sum(Bounty.reward_amount).label('total_volume')
            ).where(
                Bounty.creation_time >= start_date
            )
            
            reward_result = self.session.execute(reward_stmt).first()
            
            average_reward = reward_result.avg_reward or 0.0
            total_volume = reward_result.total_volume or 0.0
            
            # Get category distribution
            category_stmt = select(
                Bounty.category,
                func.count(Bounty.bounty_id).label('count')
            ).where(
                and_(
                    Bounty.creation_time >= start_date,
                    Bounty.category.isnot(None),
                    Bounty.category != ""
                )
            ).group_by(Bounty.category)
            
            category_result = self.session.execute(category_stmt).all()
            category_distribution = {row.category: row.count for row in category_result}
            
            # Get difficulty distribution
            difficulty_stmt = select(
                Bounty.difficulty,
                func.count(Bounty.bounty_id).label('count')
            ).where(
                and_(
                    Bounty.creation_time >= start_date,
                    Bounty.difficulty.isnot(None),
                    Bounty.difficulty != ""
                )
            ).group_by(Bounty.difficulty)
            
            difficulty_result = self.session.execute(difficulty_stmt).all()
            difficulty_distribution = {row.difficulty: row.count for row in difficulty_result}
            
            return {
                "active_bounties": active_bounties,
                "completion_rate": completion_rate,
                "average_reward": average_reward,
                "total_volume": total_volume,
                "category_distribution": category_distribution,
                "difficulty_distribution": difficulty_distribution
            }
            
        except Exception as e:
            logger.error(f"Failed to get bounty analytics: {e}")
            raise
    
    async def get_ecosystem_overview(self, period_type: str = "daily") -> Dict[str, Any]:
        """Get comprehensive ecosystem overview"""
        try:
            # Get all metrics
            developer_earnings = await self.get_developer_earnings(period_type)
            agent_utilization = await self.get_agent_utilization(period_type)
            treasury_allocation = await self.get_treasury_allocation(period_type)
            staking_metrics = await self.get_staking_metrics(period_type)
            bounty_analytics = await self.get_bounty_analytics(period_type)
            
            # Calculate health score
            health_score = await self._calculate_health_score({
                "developer_earnings": developer_earnings,
                "agent_utilization": agent_utilization,
                "treasury_allocation": treasury_allocation,
                "staking_metrics": staking_metrics,
                "bounty_analytics": bounty_analytics
            })
            
            # Calculate growth indicators
            growth_indicators = await self._calculate_growth_indicators(period_type)
            
            return {
                "developer_earnings": developer_earnings,
                "agent_utilization": agent_utilization,
                "treasury_allocation": treasury_allocation,
                "staking_metrics": staking_metrics,
                "bounty_analytics": bounty_analytics,
                "health_score": health_score,
                "growth_indicators": growth_indicators
            }
            
        except Exception as e:
            logger.error(f"Failed to get ecosystem overview: {e}")
            raise
    
    async def get_time_series_metrics(
        self,
        period_type: str = "daily",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get time-series ecosystem metrics"""
        try:
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=30)
            if not end_date:
                end_date = datetime.utcnow()
            
            # This is a simplified implementation
            # In production, you'd want more sophisticated time-series aggregation
            
            metrics = []
            current_date = start_date
            
            while current_date <= end_date and len(metrics) < limit:
                # Create a sample metric for each period
                metric = EcosystemMetrics(
                    timestamp=current_date,
                    period_type=period_type,
                    active_developers=100 + len(metrics) * 2,  # Mock data
                    new_developers=5 + len(metrics),  # Mock data
                    developer_earnings_total=1000.0 * (len(metrics) + 1),  # Mock data
                    total_agents=50 + len(metrics),  # Mock data
                    active_agents=40 + len(metrics),  # Mock data
                    total_staked=10000.0 * (len(metrics) + 1),  # Mock data
                    total_stakers=20 + len(metrics),  # Mock data
                    active_bounties=10 + len(metrics),  # Mock data
                    bounty_completion_rate=80.0 + len(metrics),  # Mock data
                    treasury_balance=1000000.0,  # Mock data
                    dao_revenue=1000.0 * (len(metrics) + 1)  # Mock data
                )
                
                metrics.append({
                    "timestamp": metric.timestamp,
                    "active_developers": metric.active_developers,
                    "developer_earnings_total": metric.developer_earnings_total,
                    "total_agents": metric.total_agents,
                    "total_staked": metric.total_staked,
                    "active_bounties": metric.active_bounties,
                    "dao_revenue": metric.dao_revenue
                })
                
                # Move to next period
                if period_type == "hourly":
                    current_date += timedelta(hours=1)
                elif period_type == "daily":
                    current_date += timedelta(days=1)
                elif period_type == "weekly":
                    current_date += timedelta(weeks=1)
                elif period_type == "monthly":
                    current_date += timedelta(days=30)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get time-series metrics: {e}")
            raise
    
    async def calculate_health_score(self, metrics_data: Dict[str, Any]) -> float:
        """Calculate overall ecosystem health score"""
        try:
            scores = []
            
            # Developer earnings health (0-100)
            earnings = metrics_data.get("developer_earnings", {})
            earnings_score = min(100, earnings.get("earnings_growth", 0) + 50)
            scores.append(earnings_score)
            
            # Agent utilization health (0-100)
            utilization = metrics_data.get("agent_utilization", {})
            utilization_score = utilization.get("utilization_rate", 0)
            scores.append(utilization_score)
            
            # Staking health (0-100)
            staking = metrics_data.get("staking_metrics", {})
            staking_score = min(100, staking.get("total_staked", 0) / 100)  # Scale down
            scores.append(staking_score)
            
            # Bounty health (0-100)
            bounty = metrics_data.get("bounty_analytics", {})
            bounty_score = bounty.get("completion_rate", 0)
            scores.append(bounty_score)
            
            # Treasury health (0-100)
            treasury = metrics_data.get("treasury_allocation", {})
            treasury_score = max(0, 100 - treasury.get("burn_rate", 0))
            scores.append(treasury_score)
            
            # Calculate weighted average
            weights = [0.25, 0.2, 0.2, 0.2, 0.15]  # Developer earnings weighted highest
            health_score = sum(score * weight for score, weight in zip(scores, weights))
            
            return round(health_score, 2)
            
        except Exception as e:
            logger.error(f"Failed to calculate health score: {e}")
            return 50.0  # Default to neutral score
    
    async def _calculate_growth_indicators(self, period: str) -> Dict[str, float]:
        """Calculate growth indicators"""
        try:
            # This is a simplified implementation
            # In production, you'd compare with previous periods
            
            return {
                "developer_growth": 15.5,  # Mock data
                "agent_growth": 12.3,      # Mock data
                "staking_growth": 25.8,    # Mock data
                "bounty_growth": 18.2,     # Mock data
                "revenue_growth": 22.1     # Mock data
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate growth indicators: {e}")
            return {}
    
    async def get_top_performers(
        self,
        category: str = "all",
        period: str = "monthly",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get top performers in different categories"""
        try:
            performers = []
            
            if category in ["all", "developers"]:
                # Get top developers
                developer_earnings = await self.get_developer_earnings(period)
                performers.extend([
                    {
                        "type": "developer",
                        "address": performer["address"],
                        "metric": "total_earned",
                        "value": performer["total_earned"],
                        "rank": performer["rank"]
                    }
                    for performer in developer_earnings.get("top_earners", [])
                ])
            
            if category in ["all", "agents"]:
                # Get top agents
                agent_utilization = await self.get_agent_utilization(period)
                performers.extend([
                    {
                        "type": "agent",
                        "address": performer["agent_wallet"],
                        "metric": "submissions",
                        "value": performer["submissions"],
                        "rank": performer["rank"]
                    }
                    for performer in agent_utilization.get("top_utilized_agents", [])
                ])
            
            # Sort by value and limit
            performers.sort(key=lambda x: x["value"], reverse=True)
            return performers[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get top performers: {e}")
            raise
    
    async def get_predictions(
        self,
        metric: str = "all",
        horizon: int = 30
    ) -> Dict[str, Any]:
        """Get ecosystem predictions based on historical data"""
        try:
            # This is a simplified implementation
            # In production, you'd use actual ML models
            
            predictions = {
                "earnings_prediction": 15000.0 * (1 + horizon / 30),  # Mock linear growth
                "staking_prediction": 50000.0 * (1 + horizon / 30),  # Mock linear growth
                "bounty_prediction": 100 * (1 + horizon / 30),       # Mock linear growth
                "confidence": 0.75,  # Mock confidence score
                "model": "linear_regression"  # Mock model name
            }
            
            if metric != "all":
                return {f"{metric}_prediction": predictions.get(f"{metric}_prediction", 0)}
            
            return predictions
            
        except Exception as e:
            logger.error(f"Failed to get predictions: {e}")
            raise
    
    async def get_alerts(self, severity: str = "all") -> List[Dict[str, Any]]:
        """Get ecosystem alerts and anomalies"""
        try:
            # This is a simplified implementation
            # In production, you'd have actual alerting logic
            
            alerts = [
                {
                    "id": "alert_1",
                    "type": "performance",
                    "severity": "medium",
                    "message": "Agent utilization dropped below 70%",
                    "timestamp": datetime.utcnow() - timedelta(hours=2),
                    "resolved": False
                },
                {
                    "id": "alert_2", 
                    "type": "financial",
                    "severity": "low",
                    "message": "Bounty completion rate decreased by 5%",
                    "timestamp": datetime.utcnow() - timedelta(hours=6),
                    "resolved": False
                }
            ]
            
            if severity != "all":
                alerts = [alert for alert in alerts if alert["severity"] == severity]
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get alerts: {e}")
            raise
    
    async def get_period_comparison(
        self,
        current_period: str = "monthly",
        compare_period: str = "previous",
        custom_start_date: Optional[datetime] = None,
        custom_end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Compare ecosystem metrics between periods"""
        try:
            # Get current period metrics
            current_metrics = await self.get_ecosystem_overview(current_period)
            
            # Get comparison period metrics
            if compare_period == "previous":
                comparison_metrics = await self.get_ecosystem_overview(current_period)
            else:
                # For custom comparison, you'd implement specific logic
                comparison_metrics = await self.get_ecosystem_overview(current_period)
            
            # Calculate differences
            comparison = {
                "developer_earnings": {
                    "current": current_metrics["developer_earnings"]["total_earnings"],
                    "previous": comparison_metrics["developer_earnings"]["total_earnings"],
                    "change": current_metrics["developer_earnings"]["total_earnings"] - comparison_metrics["developer_earnings"]["total_earnings"],
                    "change_percent": ((current_metrics["developer_earnings"]["total_earnings"] - comparison_metrics["developer_earnings"]["total_earnings"]) / comparison_metrics["developer_earnings"]["total_earnings"] * 100) if comparison_metrics["developer_earnings"]["total_earnings"] > 0 else 0
                },
                "staking_metrics": {
                    "current": current_metrics["staking_metrics"]["total_staked"],
                    "previous": comparison_metrics["staking_metrics"]["total_staked"],
                    "change": current_metrics["staking_metrics"]["total_staked"] - comparison_metrics["staking_metrics"]["total_staked"],
                    "change_percent": ((current_metrics["staking_metrics"]["total_staked"] - comparison_metrics["staking_metrics"]["total_staked"]) / comparison_metrics["staking_metrics"]["total_staked"] * 100) if comparison_metrics["staking_metrics"]["total_staked"] > 0 else 0
                }
            }
            
            return {
                "current_period": current_period,
                "compare_period": compare_period,
                "comparison": comparison,
                "summary": {
                    "overall_trend": "positive" if comparison["developer_earnings"]["change_percent"] > 0 else "negative",
                    "key_insights": [
                        "Developer earnings increased by {:.1f}%".format(comparison["developer_earnings"]["change_percent"]),
                        "Total staked changed by {:.1f}%".format(comparison["staking_metrics"]["change_percent"])
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get period comparison: {e}")
            raise
    
    async def export_data(
        self,
        format: str = "json",
        period_type: str = "daily",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Export ecosystem data in various formats"""
        try:
            # Get the data
            metrics = await self.get_time_series_metrics(period_type, start_date, end_date)
            
            # Mock export URL generation
            export_url = f"/exports/ecosystem_data_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{format}"
            
            return {
                "url": export_url,
                "file_size": len(str(metrics)) * 0.001,  # Mock file size in KB
                "expires_at": datetime.utcnow() + timedelta(hours=24),
                "record_count": len(metrics)
            }
            
        except Exception as e:
            logger.error(f"Failed to export data: {e}")
            raise
    
    async def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time ecosystem metrics"""
        try:
            # This would typically connect to real-time data sources
            # For now, return current snapshot
            
            return {
                "active_developers": 150,
                "active_agents": 75,
                "total_staked": 125000.0,
                "active_bounties": 25,
                "current_apy": 7.5,
                "recent_submissions": 12,
                "recent_completions": 8,
                "system_load": 45.2  # Mock system load percentage
            }
            
        except Exception as e:
            logger.error(f"Failed to get real-time metrics: {e}")
            raise
    
    async def get_kpi_dashboard(self) -> Dict[str, Any]:
        """Get KPI dashboard with key performance indicators"""
        try:
            return {
                "developer_kpis": {
                    "total_developers": 1250,
                    "active_developers": 150,
                    "average_earnings": 2500.0,
                    "retention_rate": 85.5
                },
                "agent_kpis": {
                    "total_agents": 500,
                    "active_agents": 75,
                    "average_accuracy": 87.2,
                    "utilization_rate": 78.5
                },
                "staking_kpis": {
                    "total_staked": 125000.0,
                    "total_stakers": 350,
                    "average_apy": 7.5,
                    "tvl_growth": 15.2
                },
                "bounty_kpis": {
                    "active_bounties": 25,
                    "completion_rate": 82.5,
                    "average_reward": 1500.0,
                    "time_to_completion": 4.2  # days
                },
                "financial_kpis": {
                    "treasury_balance": 1000000.0,
                    "monthly_revenue": 25000.0,
                    "burn_rate": 12.5,
                    "profit_margin": 65.2
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get KPI dashboard: {e}")
            raise
