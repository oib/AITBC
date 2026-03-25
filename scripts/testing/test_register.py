import asyncio
from apps.agent_services.agent_bridge.src.integration_layer import AgentServiceBridge

async def main():
    bridge = AgentServiceBridge()
    # Let's inspect the actual payload
    payload = {
        "name": "test-agent-123",
        "type": "trading",
        "capabilities": ["trade"],
        "chain_id": "ait-mainnet",
        "endpoint": "http://localhost:8005",
        "version": "1.0.0",
        "description": "Test trading agent"
    }
    async with bridge.integration as integration:
        result = await integration.register_agent_with_coordinator(payload)
        print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
