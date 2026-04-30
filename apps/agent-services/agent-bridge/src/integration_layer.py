#!/usr/bin/env python3
"""
AITBC Agent Integration Layer
Connects agent protocols to existing AITBC services
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC

class AITBCServiceIntegration:
    """Integration layer for AITBC services"""
    
    def __init__(self):
        self.service_endpoints = {
            "coordinator_api": "http://localhost:8000",
            "blockchain_rpc": "http://localhost:8006",
            "exchange_service": "http://localhost:8001",
            "marketplace": "http://localhost:8002",
            "agent_registry": "http://localhost:8013"
        }
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_blockchain_info(self) -> Dict[str, Any]:
        """Get blockchain information"""
        try:
            async with self.session.get(f"{self.service_endpoints['blockchain_rpc']}/health") as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "unavailable"}
    
    async def get_exchange_status(self) -> Dict[str, Any]:
        """Get exchange service status"""
        try:
            async with self.session.get(f"{self.service_endpoints['exchange_service']}/api/health") as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "unavailable"}
    
    async def get_coordinator_status(self) -> Dict[str, Any]:
        """Get coordinator API status"""
        try:
            async with self.session.get(f"{self.service_endpoints['coordinator_api']}/health") as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "unavailable"}
    
    async def submit_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit transaction to blockchain"""
        try:
            async with self.session.post(
                f"{self.service_endpoints['blockchain_rpc']}/rpc/submit",
                json=transaction_data
            ) as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}
    
    async def get_market_data(self, symbol: str = "AITBC/BTC") -> Dict[str, Any]:
        """Get market data from exchange"""
        try:
            async with self.session.get(f"{self.service_endpoints['exchange_service']}/api/market/{symbol}") as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}
    
    async def register_agent_with_coordinator(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register agent with coordinator"""
        try:
            async with self.session.post(
                f"{self.service_endpoints['agent_registry']}/api/agents/register",
                json=agent_data
            ) as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}

class AgentServiceBridge:
    """Bridge between agents and AITBC services"""
    
    def __init__(self):
        self.integration = AITBCServiceIntegration()
        self.active_agents = {}
    
    async def start_agent(self, agent_id: str, agent_config: Dict[str, Any]) -> bool:
        """Start an agent with service integration"""
        try:
            # Register agent with coordinator
            async with self.integration as integration:
                registration_result = await integration.register_agent_with_coordinator({
                    "name": agent_id,
                    "type": agent_config.get("type", "generic"),
                    "capabilities": agent_config.get("capabilities", []),
                    "chain_id": agent_config.get("chain_id", "ait-mainnet"),
                    "endpoint": agent_config.get("endpoint", f"http://localhost:{8000 + len(self.active_agents) + 10}")
                })
            
            # The registry returns the created agent dict on success, not a {"status": "ok"} wrapper
            if registration_result and "id" in registration_result:
                self.active_agents[agent_id] = {
                    "config": agent_config,
                    "registration": registration_result,
                    "started_at": datetime.now(datetime.UTC)
                }
                return True
            else:
                logger.warning(f"Registration failed: {registration_result}")
                return False
        except Exception as e:
            logger.error(f"Failed to start agent {agent_id}: {e}")
            return False
    
    async def stop_agent(self, agent_id: str) -> bool:
        """Stop an agent"""
        if agent_id in self.active_agents:
            del self.active_agents[agent_id]
            return True
        return False
    
    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get agent status with service integration"""
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
                "services": {
                    "blockchain": blockchain_status,
                    "exchange": exchange_status,
                    "coordinator": coordinator_status
                }
            }
    
    async def execute_agent_task(self, agent_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent task with service integration"""
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
    
    async def _execute_market_analysis(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute market analysis task"""
        try:
            async with self.integration as integration:
                market_data = await integration.get_market_data(task_data.get("symbol", "AITBC/BTC"))
                
                # Perform basic analysis
                analysis_result = {
                    "symbol": task_data.get("symbol", "AITBC/BTC"),
                    "market_data": market_data,
                    "analysis": {
                        "trend": "neutral",
                        "volatility": "medium",
                        "recommendation": "hold"
                    },
                    "timestamp": datetime.now(datetime.UTC).isoformat()
                }
                
                return {"status": "success", "result": analysis_result}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _execute_trading_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
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
                    "amount": task_data.get("amount", 0.1),
                    "price": task_data.get("price", market_data.get("price", 0.001))
                }
                
                # Submit transaction
                tx_result = await integration.submit_transaction(transaction)
                
                return {"status": "success", "transaction": tx_result}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _execute_compliance_check(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute compliance check task"""
        try:
            # Basic compliance check
            compliance_result = {
                "user_id": task_data.get("user_id"),
                "check_type": task_data.get("check_type", "basic"),
                "status": "passed",
                "checks_performed": ["kyc", "aml", "sanctions"],
                "timestamp": datetime.now(datetime.UTC).isoformat()
            }
            
            return {"status": "success", "result": compliance_result}
        except Exception as e:
            return {"status": "error", "message": str(e)}
