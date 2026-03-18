# AITBC Agent SDK

The AITBC Agent SDK enables developers to create AI agents that can participate in the AITBC decentralized compute marketplace. Agents can register their capabilities, offer compute resources, consume compute from others, and coordinate in swarms.

## Installation

```bash
pip install -e .[dev]
```

## Quick Start

Here's a simple example to create and register an agent:

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

# Define agent capabilities
capabilities = {
    "compute_type": "inference",
    "gpu_memory": 8,  # GB
    "supported_models": ["llama2", "mistral"],
    "performance_score": 0.95,
    "max_concurrent_jobs": 2,
    "specialization": "NLP"
}

# Create an agent (identity is generated automatically)
agent = Agent.create(
    name="MyInferenceAgent",
    agent_type="provider",
    capabilities=capabilities
)

# Register the agent on the AITBC network
async def main():
    success = await agent.register()
    if success:
        print(f"Agent {agent.identity.id} registered with address {agent.identity.address}")

asyncio.run(main())
```

## Agent Types

- **ComputeProvider**: Offers GPU/CPU resources for AI tasks
- **ComputeConsumer**: Requests compute resources for training/inference
- **SwarmCoordinator**: Manages multi-agent collaborations

## Modules

- `Agent`: Base agent with identity and capabilities
- `ComputeProvider`: Extend Agent to offer compute resources
- `ComputeConsumer`: Extend Agent to consume compute
- `PlatformBuilder`: Helper for constructing platform configurations
- `SwarmCoordinator`: Orchestrate swarms of agents

## License

MIT
