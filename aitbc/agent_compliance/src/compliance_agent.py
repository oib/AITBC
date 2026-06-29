#!/usr/bin/env python3
"""
AITBC Compliance Agent
Automated compliance and regulatory monitoring agent
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from aitbc.agent_bridge.src.integration_layer import AgentServiceBridge

from aitbc import get_logger

logger = get_logger(__name__)


class ComplianceAgent:
    """Automated compliance agent"""

    def __init__(self, agent_id: str, config: dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.bridge = AgentServiceBridge()
        self.is_running = False
        self.check_interval = config.get("check_interval", 300)  # 5 minutes
        self.monitored_entities = config.get("monitored_entities", [])

    async def start(self) -> bool:
        """Start compliance agent"""
        try:
            success = await self.bridge.start_agent(
                self.agent_id,
                {
                    "type": "compliance",
                    "capabilities": ["kyc_check", "aml_screening", "regulatory_reporting"],
                    "endpoint": "http://localhost:8202",
                },
            )

            if success:
                self.is_running = True
                logger.info("Compliance agent %s started successfully", self.agent_id)
                return True
            else:
                logger.warning("Failed to start compliance agent %s", self.agent_id)
                return False
        except Exception as e:
            logger.error("Error starting compliance agent: %s", e)
            return False

    async def stop(self) -> bool:
        """Stop compliance agent"""
        self.is_running = False
        success = await self.bridge.stop_agent(self.agent_id)
        if success:
            logger.info("Compliance agent %s stopped successfully", self.agent_id)
        return bool(success)

    async def run_compliance_loop(self):
        """Main compliance monitoring loop"""
        while self.is_running:
            try:
                for entity in self.monitored_entities:
                    await self._perform_compliance_check(entity)

                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error("Error in compliance loop: %s", e)
                await asyncio.sleep(30)  # Wait before retrying

    async def _perform_compliance_check(self, entity_id: str) -> None:
        """Perform compliance check for entity"""
        try:
            compliance_task = {
                "type": "compliance_check",
                "user_id": entity_id,
                "check_type": "full",
                "monitored_activities": ["trading", "transfers", "wallet_creation"],
            }

            result = await self.bridge.execute_agent_task(self.agent_id, compliance_task)

            if result.get("status") == "success":
                compliance_result = result["result"]
                await self._handle_compliance_result(entity_id, compliance_result)
            else:
                logger.warning("Compliance check failed for %s: %s", entity_id, result)

        except Exception as e:
            logger.error("Error performing compliance check for %s: %s", entity_id, e)

    async def _handle_compliance_result(self, entity_id: str, result: dict[str, Any]) -> None:
        """Handle compliance check result"""
        status = result.get("status", "unknown")

        if status == "passed":
            logger.info("Compliance check passed for %s", entity_id)
        elif status == "failed":
            logger.warning("Compliance check failed for %s", entity_id)
            # Trigger alert or further investigation
            await self._trigger_compliance_alert(entity_id, result)
        else:
            logger.warning("Compliance check inconclusive for %s", entity_id)

    async def _trigger_compliance_alert(self, entity_id: str, result: dict[str, Any]) -> None:
        """Trigger compliance alert"""
        alert_data = {
            "entity_id": entity_id,
            "alert_type": "compliance_failure",
            "severity": "high",
            "details": result,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # In a real implementation, this would send to alert system
        logger.warning("COMPLIANCE ALERT: %s", json.dumps(alert_data))

    async def get_status(self) -> dict[str, Any]:
        """Get agent status"""
        status = await self.bridge.get_agent_status(self.agent_id)
        result = dict(status) if isinstance(status, dict) else {"status": "unknown"}
        result["monitored_entities"] = len(self.monitored_entities)
        result["check_interval"] = self.check_interval
        return result


# Main execution
async def main():
    """Main compliance agent execution"""
    agent_id = "compliance-agent-001"
    config = {
        "check_interval": 60,  # 1 minute for testing
        "monitored_entities": ["user001", "user002", "user003"],
    }

    agent = ComplianceAgent(agent_id, config)

    # Start agent
    if await agent.start():
        try:
            # Run compliance loop
            await agent.run_compliance_loop()
        except KeyboardInterrupt:
            logger.info("Shutting down compliance agent...")
        finally:
            await agent.stop()
    else:
        logger.error("Failed to start compliance agent")


if __name__ == "__main__":
    asyncio.run(main())
