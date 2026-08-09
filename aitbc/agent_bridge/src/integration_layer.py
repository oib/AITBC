#!/usr/bin/env python3
"""
AITBC Agent Integration Layer
Connects agent protocols to existing AITBC services
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiohttp

from aitbc.constants import (
    AGENT_COORDINATOR_PORT,
    BLOCKCHAIN_RPC_URL,
    COORDINATOR_API_PORT,
    EXCHANGE_PORT,
    MARKETPLACE_PORT,
)

logger = logging.getLogger(__name__)


class AITBCServiceIntegration:
    """Integration layer for AITBC services"""

    def __init__(self):
        self.service_endpoints = {
            "coordinator_api": os.getenv("COORDINATOR_API_URL", f"http://localhost:{COORDINATOR_API_PORT}"),
            "blockchain_rpc": os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL),
            "exchange_service": os.getenv("EXCHANGE_SERVICE_URL", f"http://localhost:{EXCHANGE_PORT}"),
            "marketplace": os.getenv("MARKETPLACE_SERVICE_URL", f"http://localhost:{MARKETPLACE_PORT}"),
            "agent_coordinator": os.getenv("AGENT_COORDINATOR_URL", f"http://localhost:{AGENT_COORDINATOR_PORT}"),
        }
        self.session: aiohttp.ClientSession | None = None
        self._session_ref: int = 0
        self._session_lock = asyncio.Lock()

    async def __aenter__(self):
        async with self._session_lock:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession()
            self._session_ref += 1
            return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._session_lock:
            self._session_ref -= 1
            if self._session_ref <= 0 and self.session:
                await self.session.close()
                self.session = None
                self._session_ref = 0

    async def get_blockchain_info(self) -> dict[str, Any]:
        """Get blockchain information"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.get(f"{self.service_endpoints['blockchain_rpc']}/health") as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: blockchain_rpc")
            return {"error": str(e), "status": "unavailable"}

    async def get_exchange_status(self) -> dict[str, Any]:
        """Get exchange service status"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.get(f"{self.service_endpoints['exchange_service']}/api/health") as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: exchange_service")
            return {"error": str(e), "status": "unavailable"}

    async def get_coordinator_status(self) -> dict[str, Any]:
        """Get coordinator API status"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.get(f"{self.service_endpoints['coordinator_api']}/health") as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: coordinator_api")
            return {"error": str(e), "status": "unavailable"}

    async def submit_transaction(self, transaction_data: dict[str, Any]) -> dict[str, Any]:
        """Submit transaction to blockchain"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.post(
                f"{self.service_endpoints['blockchain_rpc']}/rpc/submit", json=transaction_data
            ) as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: blockchain_rpc (submit_transaction)")
            return {"error": str(e), "status": "failed"}

    async def get_market_data(self, symbol: str = "AITBC/BTC") -> dict[str, Any]:
        """Get market data from exchange"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.get(f"{self.service_endpoints['exchange_service']}/api/market/{symbol}") as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: exchange_service (get_market_data)")
            return {"error": str(e), "status": "failed"}

    async def register_agent_with_coordinator(self, agent_data: dict[str, Any]) -> dict[str, Any]:
        """Register agent with agent coordinator"""
        try:
            if self.session is None:
                raise RuntimeError("Session not initialized")
            async with self.session.post(
                f"{self.service_endpoints['agent_coordinator']}/agents/register", json=agent_data
            ) as response:
                return dict(await response.json())
        except Exception as e:
            logger.exception("Service call failed: agent_coordinator (register_agent)")
            return {"error": str(e), "status": "failed"}


class AgentServiceBridge:
    """Bridge between agents and AITBC services"""

    def __init__(self):
        self.integration = AITBCServiceIntegration()
        self.active_agents = {}
        self._lock = asyncio.Lock()

    async def start_agent(self, agent_id: str, agent_config: dict[str, Any]) -> bool:
        """Start an agent with service integration"""
        try:
            # Determine the next local endpoint port under the bridge lock.
            async with self._lock:
                endpoint_port = 8000 + len(self.active_agents) + 10

            # Register agent with coordinator
            async with self.integration as integration:
                registration_result = await integration.register_agent_with_coordinator(
                    {
                        "agent_id": agent_id,
                        "agent_type": agent_config.get("type", "generic"),
                        "capabilities": agent_config.get("capabilities", []),
                        "services": agent_config.get("services", []),
                        "endpoints": agent_config.get(
                            "endpoints",
                            {"http": agent_config.get("endpoint", f"http://localhost:{endpoint_port}")},
                        ),
                        "metadata": agent_config.get("metadata", {}),
                        "chain_id": agent_config.get("chain_id", "ait-mainnet"),
                        "island_id": agent_config.get("island_id"),
                    }
                )

            # The registry returns {"status": "success", "agent_id": ...} on success
            if registration_result and registration_result.get("agent_id") == agent_id:
                async with self._lock:
                    self.active_agents[agent_id] = {
                        "config": agent_config,
                        "registration": registration_result,
                        "started_at": datetime.now(UTC),
                    }
                return True
            else:
                logger.warning("Registration failed: %s", registration_result)
                return False
        except Exception as e:
            logger.error("Failed to start agent %s: %s", agent_id, e)
            return False

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop an agent"""
        async with self._lock:
            if agent_id in self.active_agents:
                del self.active_agents[agent_id]
                return True
            return False

    async def get_agent_status(self, agent_id: str) -> dict[str, Any]:
        """Get agent status with service integration"""
        async with self._lock:
            if agent_id not in self.active_agents:
                return {"status": "not_found"}
            agent_info = self.active_agents[agent_id]

        async with self.integration as integration:
            # Get service statuses
            blockchain_status = await integration.get_blockchain_info()
            exchange_status = await integration.get_exchange_status()
            coordinator_status = await integration.get_coordinator_status()

            return {
                "agent_id": agent_id,
                "status": "active",
                "started_at": agent_info["started_at"].isoformat(),
                "services": {"blockchain": blockchain_status, "exchange": exchange_status, "coordinator": coordinator_status},
            }

    async def execute_agent_task(self, agent_id: str, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute agent task with service integration"""
        async with self._lock:
            if agent_id not in self.active_agents:
                return {"status": "error", "message": "Agent not found"}

        task_type = task_data.get("type")

        if task_type == "market_analysis":
            return await self._execute_market_analysis(task_data)
        elif task_type == "trading":
            return await self._execute_trading_task(task_data)
        elif task_type == "compliance_check":
            return await self._execute_compliance_check(task_data)
        else:
            return {"status": "error", "message": f"Unknown task type: {task_type}"}

    async def _execute_market_analysis(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute market analysis task"""
        try:
            async with self.integration as integration:
                market_data = await integration.get_market_data(task_data.get("symbol", "AITBC/BTC"))

                # Perform basic analysis
                analysis_result = {
                    "symbol": task_data.get("symbol", "AITBC/BTC"),
                    "market_data": market_data,
                    "analysis": {"trend": "neutral", "volatility": "medium", "recommendation": "hold"},
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                return {"status": "success", "result": analysis_result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _execute_trading_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute trading task"""
        try:
            # Get market data first
            async with self.integration as integration:
                market_data = await integration.get_market_data(task_data.get("symbol", "AITBC/BTC"))

                # Create transaction
                transaction = {
                    "type": "trade",
                    "symbol": task_data.get("symbol", "AITBC/BTC"),
                    "side": task_data.get("side", "buy"),
                    "amount": Decimal(str(task_data.get("amount", "0.1"))),
                    "price": Decimal(str(task_data.get("price", market_data.get("price", "0.001")))),
                }

                # Submit transaction
                tx_result = await integration.submit_transaction(transaction)

                return {"status": "success", "transaction": tx_result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _execute_compliance_check(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute compliance check task.

        Not implemented. This previously returned a hardcoded
        ``{"status": "passed", "checks_performed": ["kyc", "aml", "sanctions"]}`` that
        ignored its inputs entirely -- no KYC, AML or sanctions screening was ever
        performed. Any caller treating that as a compliance gate was told every subject
        passes, which is worse than having no gate at all.

        Raises:
            NotImplementedError: always, until real screening is wired up.
        """
        raise NotImplementedError(
            "Agent-bridge compliance screening (kyc/aml/sanctions) is not implemented. "
            "Route compliance decisions through aitbc.compliance policy evaluation, or the "
            "coordinator-api compliance context -- do not treat this task type as a gate."
        )
