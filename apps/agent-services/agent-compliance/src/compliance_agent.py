#!/usr/bin/env python3
"""
AITBC Compliance Agent
Automated compliance and regulatory monitoring agent
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List
from datetime import datetime, UTC
import sys
import os

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))

from apps.agent_services.agent_bridge.src.integration_layer import AgentServiceBridge

class ComplianceAgent:
    """Automated compliance agent"""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.bridge = AgentServiceBridge()
        self.is_running = False
        self.check_interval = config.get("check_interval", 300)  # 5 minutes
        self.monitored_entities = config.get("monitored_entities", [])
    
    async def start(self) -> bool:
        """Start compliance agent"""
        try:
            success = await self.bridge.start_agent(self.agent_id, {
                "type": "compliance",
                "capabilities": ["kyc_check", "aml_screening", "regulatory_reporting"],
                "endpoint": f"http://localhost:8006"
            })
            
            if success:
                self.is_running = True
                logger.info(f"Compliance agent {self.agent_id} started successfully")
                return True
            else:
                logger.warning(f"Failed to start compliance agent {self.agent_id}")
                return False
        except Exception as e:
            logger.error(f"Error starting compliance agent: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop compliance agent"""
        self.is_running = False
        success = await self.bridge.stop_agent(self.agent_id)
        if success:
            logger.info(f"Compliance agent {self.agent_id} stopped successfully")
        return success
    
    async def run_compliance_loop(self):
        """Main compliance monitoring loop"""
        while self.is_running:
            try:
                for entity in self.monitored_entities:
                    await self._perform_compliance_check(entity)
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in compliance loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _perform_compliance_check(self, entity_id: str) -> None:
        """Perform compliance check for entity"""
        try:
            compliance_task = {
                "type": "compliance_check",
                "user_id": entity_id,
                "check_type": "full",
                "monitored_activities": ["trading", "transfers", "wallet_creation"]
            }
            
            result = await self.bridge.execute_agent_task(self.agent_id, compliance_task)
            
            if result.get("status") == "success":
                compliance_result = result["result"]
                await self._handle_compliance_result(entity_id, compliance_result)
            else:
                logger.warning(f"Compliance check failed for {entity_id}: {result}")
        
        except Exception as e:
            logger.error(f"Error performing compliance check for {entity_id}: {e}")
    
    async def _handle_compliance_result(self, entity_id: str, result: Dict[str, Any]) -> None:
        """Handle compliance check result"""
        status = result.get("status", "unknown")
        
        if status == "passed":
            logger.info(f"Compliance check passed for {entity_id}")
        elif status == "failed":
            logger.warning(f"Compliance check failed for {entity_id}")
            # Trigger alert or further investigation
            await self._trigger_compliance_alert(entity_id, result)
        else:
            logger.warning(f"Compliance check inconclusive for {entity_id}")
    
    async def _trigger_compliance_alert(self, entity_id: str, result: Dict[str, Any]) -> None:
        """Trigger compliance alert"""
        alert_data = {
            "entity_id": entity_id,
            "alert_type": "compliance_failure",
            "severity": "high",
            "details": result,
            "timestamp": datetime.now(datetime.UTC).isoformat()
        }
        
        # In a real implementation, this would send to alert system
        logger.warning(f"COMPLIANCE ALERT: {json.dumps(alert_data)}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        status = await self.bridge.get_agent_status(self.agent_id)
        status["monitored_entities"] = len(self.monitored_entities)
        status["check_interval"] = self.check_interval
        return status

# Main execution
async def main():
    """Main compliance agent execution"""
    agent_id = "compliance-agent-001"
    config = {
        "check_interval": 60,  # 1 minute for testing
        "monitored_entities": ["user001", "user002", "user003"]
    }
    
    agent = ComplianceAgent(agent_id, config)
    
    # Start agent
    if await agent.start():
        try:
            # Run compliance loop
            await agent.run_compliance_loop()
        except KeyboardInterrupt:
            print("Shutting down compliance agent...")
        finally:
            await agent.stop()
    else:
        print("Failed to start compliance agent")

if __name__ == "__main__":
    asyncio.run(main())
