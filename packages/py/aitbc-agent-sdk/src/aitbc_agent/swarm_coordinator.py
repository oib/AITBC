"""
Swarm Coordinator - for agents participating in collective intelligence
"""

import asyncio
import json
from typing import Dict, List, Optional, Any  # noqa: F401
from datetime import datetime, UTC
from dataclasses import dataclass
from .agent import Agent

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SwarmMessage:
    """Swarm communication message"""

    swarm_id: str
    sender_id: str
    message_type: str
    priority: str
    payload: Dict[str, Any]
    timestamp: str
    swarm_signature: str


@dataclass
class SwarmDecision:
    """Collective swarm decision"""

    swarm_id: str
    decision_type: str
    proposal: Dict[str, Any]
    votes: Dict[str, str]  # agent_id -> vote
    consensus: bool
    implementation_plan: Dict[str, Any]
    timestamp: str


class SwarmCoordinator(Agent):
    """Agent that participates in swarm intelligence"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.joined_swarms: Dict[str, Dict[str, Any]] = {}
        self.swarm_reputation: Dict[str, float] = {}
        self.contribution_score = 0.0

    async def join_swarm(self, swarm_type: str, config: Dict[str, Any]) -> bool:
        """Join a swarm for collective intelligence"""
        try:
            swarm_id = f"{swarm_type}-v1"

            # Register with swarm
            registration = {
                "agent_id": self.identity.id,
                "swarm_id": swarm_id,
                "role": config.get("role", "participant"),
                "capabilities": {
                    "compute_type": self.capabilities.compute_type,
                    "performance_score": self.capabilities.performance_score,
                    "specialization": self.capabilities.specialization,
                },
                "contribution_level": config.get("contribution_level", "medium"),
                "data_sharing_consent": config.get("data_sharing_consent", True),
            }

            # Sign swarm registration
            signature = self.identity.sign_message(registration)
            registration["signature"] = signature

            # Submit to swarm coordinator
            await self._register_with_swarm(swarm_id, registration)

            # Store swarm membership
            self.joined_swarms[swarm_id] = {
                "type": swarm_type,
                "role": config.get("role", "participant"),
                "joined_at": datetime.now(timezone.utc).isoformat(),
                "contribution_count": 0,
                "last_activity": datetime.now(timezone.utc).isoformat(),
            }

            # Initialize swarm reputation
            self.swarm_reputation[swarm_id] = 0.5  # Starting reputation

            # Start swarm participation tasks
            asyncio.create_task(self._swarm_participation_loop(swarm_id))

            logger.info(
                f"Joined swarm: {swarm_id} as {config.get('role', 'participant')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to join swarm {swarm_type}: {e}")
            return False

    async def _swarm_participation_loop(self, swarm_id: str) -> None:
        """Background task for active swarm participation"""
        while swarm_id in self.joined_swarms:
            try:
                # Listen for swarm messages
                await self._process_swarm_messages(swarm_id)

                # Contribute data if enabled
                swarm_config = self.joined_swarms[swarm_id]
                if swarm_config.get("data_sharing", True):
                    await self._contribute_swarm_data(swarm_id)

                # Participate in collective decisions
                await self._participate_in_decisions(swarm_id)

                # Update activity timestamp
                swarm_config["last_activity"] = datetime.now(timezone.utc).isoformat()

            except Exception as e:
                logger.error(f"Swarm participation error for {swarm_id}: {e}")

            # Wait before next participation cycle
            await asyncio.sleep(60)  # 1 minute

    async def broadcast_to_swarm(self, message: SwarmMessage) -> bool:
        """Broadcast a message to the swarm"""
        try:
            # Verify swarm membership
            if message.swarm_id not in self.joined_swarms:
                return False

            # Sign swarm message
            swarm_signature = self.identity.sign_message(
                {
                    "swarm_id": message.swarm_id,
                    "sender_id": message.sender_id,
                    "message_type": message.message_type,
                    "payload": message.payload,
                    "timestamp": message.timestamp,
                }
            )
            message.swarm_signature = swarm_signature

            # Broadcast to swarm network
            await self._broadcast_to_swarm_network(message)

            # Update contribution count
            self.joined_swarms[message.swarm_id]["contribution_count"] += 1

            logger.info(
                f"Broadcasted to swarm {message.swarm_id}: {message.message_type}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to broadcast to swarm: {e}")
            return False

    async def _contribute_swarm_data(self, swarm_id: str) -> None:
        """Contribute data to swarm intelligence"""
        try:
            swarm_type = self.joined_swarms[swarm_id]["type"]

            if swarm_type == "load_balancing":
                data = await self._get_load_balancing_data()
            elif swarm_type == "pricing":
                data = await self._get_pricing_data()
            elif swarm_type == "security":
                data = await self._get_security_data()
            else:
                data = await self._get_general_data()

            message = SwarmMessage(
                swarm_id=swarm_id,
                sender_id=self.identity.id,
                message_type="data_contribution",
                priority="medium",
                payload=data,
                timestamp=datetime.now(timezone.utc).isoformat(),
                swarm_signature="",  # Will be added in broadcast_to_swarm
            )

            await self.broadcast_to_swarm(message)

        except Exception as e:
            logger.error(f"Failed to contribute swarm data: {e}")

    async def _get_load_balancing_data(self) -> Dict[str, Any]:
        """Get actual load balancing metrics from coordinator"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/load-balancing/metrics",
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Failed to get load balancing metrics: {response.status_code}")
                    return self._get_default_load_balancing_data()
        except Exception as e:
            logger.error(f"Error fetching load balancing data: {e}")
            return self._get_default_load_balancing_data()
    
    def _get_default_load_balancing_data(self) -> Dict[str, Any]:
        """Default load balancing data when API is unavailable"""
        return {
            "resource_type": "gpu_memory",
            "availability": 0.75,
            "location": "us-west-2",
            "pricing_trend": "stable",
            "current_load": 0.6,
            "capacity_utilization": 0.8,
        }

    async def _get_pricing_data(self) -> Dict[str, Any]:
        """Get actual pricing data from coordinator marketplace API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/marketplace/pricing/trends",
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Failed to get pricing data: {response.status_code}")
                    return self._get_default_pricing_data()
        except Exception as e:
            logger.error(f"Error fetching pricing data: {e}")
            return self._get_default_pricing_data()
    
    def _get_default_pricing_data(self) -> Dict[str, Any]:
        """Default pricing data when API is unavailable"""
        return {
            "current_demand": "high",
            "price_trends": "increasing",
            "resource_constraints": "gpu_memory",
            "competitive_landscape": "moderate",
            "market_volatility": 0.15,
        }

    async def _get_security_data(self) -> Dict[str, Any]:
        """Get actual security metrics from coordinator security API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/security/metrics",
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Failed to get security metrics: {response.status_code}")
                    return self._get_default_security_data()
        except Exception as e:
            logger.error(f"Error fetching security data: {e}")
            return self._get_default_security_data()
    
    def _get_default_security_data(self) -> Dict[str, Any]:
        """Default security data when API is unavailable"""
        return {
            "threat_level": "low",
            "anomaly_count": 2,
            "verification_success_rate": 0.98,
            "network_health": "good",
            "security_events": [],
        }

    async def _get_general_data(self) -> Dict[str, Any]:
        """Get general performance data for swarm contribution"""
        return {
            "performance_metrics": {
                "response_time": 30.5,
                "success_rate": 0.95,
                "quality_score": 0.92,
            },
            "network_status": "healthy",
            "agent_status": "active",
        }

    async def coordinate_task(self, task: str, collaborators: int) -> Dict[str, Any]:
        """Coordinate a collaborative task with other agents"""
        try:
            # Create coordination proposal
            proposal = {
                "task_id": f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                "task_type": task,
                "coordinator_id": self.identity.id,
                "required_collaborators": collaborators,
                "task_description": f"Collaborative {task} task",
                "estimated_duration": "2h",
                "resource_requirements": {
                    "compute_type": "general",
                    "min_performance": 0.8,
                },
            }

            # Submit to swarm for coordination
            coordination_result = await self._submit_coordination_proposal(proposal)

            logger.info(
                f"Task coordination initiated: {task} with {collaborators} collaborators"
            )
            return coordination_result

        except Exception as e:
            logger.error(f"Failed to coordinate task: {e}")
            return {"success": False, "error": str(e)}

    async def get_market_intelligence(self) -> Dict[str, Any]:
        """Get collective market intelligence from swarm"""
        try:
            # Request market intelligence from pricing swarm
            if "pricing-v1" in self.joined_swarms:
                intel_request = SwarmMessage(
                    swarm_id="pricing-v1",
                    sender_id=self.identity.id,
                    message_type="intelligence_request",
                    priority="high",
                    payload={"request_type": "market_intelligence"},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    swarm_signature="",
                )

                await self.broadcast_to_swarm(intel_request)

                # Wait for intelligence response (simulate)
                await asyncio.sleep(2)

                return {
                    "demand_forecast": "increasing",
                    "price_trends": "stable_to_rising",
                    "competition_analysis": "moderate",
                    "opportunity_areas": ["specialized_models", "batch_processing"],
                    "risk_factors": ["gpu_shortages", "price_volatility"],
                }
            else:
                return {"error": "Not joined to pricing swarm"}

        except Exception as e:
            logger.error(f"Failed to get market intelligence: {e}")
            return {"error": str(e)}

    async def analyze_swarm_benefits(self) -> Dict[str, Any]:
        """Analyze benefits of swarm participation"""
        try:
            # Calculate benefits based on swarm participation
            total_contributions = sum(
                swarm["contribution_count"] for swarm in self.joined_swarms.values()
            )

            avg_reputation = (
                sum(self.swarm_reputation.values()) / len(self.swarm_reputation)
                if self.swarm_reputation
                else 0
            )

            # Simulate benefit analysis
            earnings_boost = total_contributions * 0.15  # 15% boost per contribution
            utilization_improvement = (
                avg_reputation * 0.25
            )  # 25% utilization improvement

            return {
                "earnings_boost": f"{earnings_boost:.1%}",
                "utilization_improvement": f"{utilization_improvement:.1%}",
                "total_contributions": total_contributions,
                "swarm_reputation": avg_reputation,
                "joined_swarms": len(self.joined_swarms),
            }

        except Exception as e:
            logger.error(f"Failed to analyze swarm benefits: {e}")
            return {"error": str(e)}

    async def _register_with_swarm(
        self, swarm_id: str, registration: Dict[str, Any]
    ) -> None:
        """Register with swarm coordinator via API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/swarm/{swarm_id}/register",
                    json={
                        "agent_id": self.identity.id,
                        "registration": registration
                    },
                    timeout=10
                )
                if response.status_code == 201:
                    logger.info(f"Successfully registered with swarm: {swarm_id}")
                else:
                    logger.warning(f"Failed to register with swarm {swarm_id}: {response.status_code}")
        except Exception as e:
            logger.error(f"Error registering with swarm: {e}")

    async def _broadcast_to_swarm_network(self, message: SwarmMessage) -> None:
        """Broadcast message to swarm network via API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/swarm/{message.swarm_id}/broadcast",
                    json=message.__dict__,
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"Message broadcast to swarm: {message.swarm_id}")
                else:
                    logger.warning(f"Failed to broadcast to swarm: {response.status_code}")
        except Exception as e:
            logger.error(f"Error broadcasting to swarm: {e}")

    async def _process_swarm_messages(self, swarm_id: str) -> None:
        """Process incoming swarm messages via API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.coordinator_url}/v1/swarm/{swarm_id}/messages",
                    timeout=10
                )
                if response.status_code == 200:
                    messages = response.json()
                    logger.info(f"Received {len(messages.get('messages', []))} messages from swarm")
                else:
                    logger.warning(f"Failed to get swarm messages: {response.status_code}")
        except Exception as e:
            logger.error(f"Error processing swarm messages: {e}")

    async def _participate_in_decisions(self, swarm_id: str) -> None:
        """Participate in swarm decision making via API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/swarm/{swarm_id}/decisions/participate",
                    json={"agent_id": self.identity.id},
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info(f"Participating in decisions for swarm: {swarm_id}")
                else:
                    logger.warning(f"Failed to participate in decisions: {response.status_code}")
        except Exception as e:
            logger.error(f"Error participating in swarm decisions: {e}")

    async def _submit_coordination_proposal(
        self, proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Submit coordination proposal to swarm via API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.coordinator_url}/v1/swarm/coordination/proposals",
                    json=proposal,
                    timeout=10
                )
                if response.status_code == 201:
                    result = response.json()
                    logger.info(f"Coordination proposal submitted: {proposal['task_id']}")
                    return result
                else:
                    logger.warning(f"Failed to submit coordination proposal: {response.status_code}")
                    return {
                        "success": False,
                        "proposal_id": proposal["task_id"],
                        "status": "failed",
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            logger.error(f"Error submitting coordination proposal: {e}")
            return {
                "success": False,
                "proposal_id": proposal["task_id"],
                "status": "error",
                "error": str(e)
            }
