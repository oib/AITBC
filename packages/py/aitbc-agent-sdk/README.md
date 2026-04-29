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

## Detailed Usage

### Compute Provider

The ComputeProvider agent offers computational resources on the marketplace:

```python
import asyncio
from aitbc_agent import ComputeProvider

async def main():
    # Create a compute provider with auto-detected capabilities
    capabilities = ComputeProvider.assess_capabilities()
    
    provider = ComputeProvider.create_provider(
        name="GPU-Provider-1",
        capabilities=capabilities,
        pricing_model={
            "base_rate": 50.0,  # AITBC per hour
            "currency": "AITBC"
        }
    )
    
    # Register the provider
    await provider.register()
    
    # Offer resources on the marketplace
    availability = {
        "start_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-12-31T23:59:59Z",
        "timezone": "UTC",
        "schedule": {
            "monday": {"start": "09:00", "end": "18:00"},
            "tuesday": {"start": "09:00", "end": "18:00"},
            # ... other days
        }
    }
    
    await provider.offer_resources(
        price_per_hour=50.0,
        availability_schedule=availability,
        max_concurrent_jobs=3
    )
    
    # Enable dynamic pricing
    await provider.enable_dynamic_pricing(
        base_rate=50.0,
        demand_threshold=0.8,
        max_multiplier=2.0
    )
    
    # Get performance metrics
    metrics = await provider.get_performance_metrics()
    print(f"Utilization: {metrics['utilization_rate']:.2%}")
    print(f"Earnings: {metrics['total_earnings']} AITBC")

asyncio.run(main())
```

### Compute Consumer

The ComputeConsumer agent requests computational resources:

```python
import asyncio
from aitbc_agent import ComputeConsumer

async def main():
    # Create a compute consumer
    consumer = ComputeConsumer.create(
        name="ML-Training-Consumer",
        agent_type="consumer",
        capabilities={
            "compute_type": "training",
            "specialization": "computer-vision"
        }
    )
    
    # Register the consumer
    await consumer.register()
    
    # Submit a training job
    job_id = await consumer.submit_job(
        job_type="training",
        input_data={
            "model": "resnet50",
            "dataset": "imagenet",
            "epochs": 10
        },
        requirements={
            "gpu_memory": 16,
            "compute_type": "training"
        },
        max_price=100.0
    )
    
    print(f"Job submitted: {job_id}")
    
    # Monitor job status
    while True:
        status = await consumer.get_job_status(job_id)
        print(f"Job status: {status['status']}")
        
        if status['status'] in ['completed', 'failed']:
            break
        
        await asyncio.sleep(5)
    
    # Get spending summary
    summary = consumer.get_spending_summary()
    print(f"Total spent: {summary['total_spent']} AITBC")

asyncio.run(main())
```

### High-Level AITBCAgent

For quick prototyping, use the convenience wrapper:

```python
import asyncio
from aitbc_agent import AITBCAgent

async def main():
    # Simple agent creation
    agent = AITBCAgent(
        agent_id="quick-agent",
        compute_type="inference",
        capabilities=["text-generation", "summarization"]
    )
    
    # Register and use
    await agent.register()
    
    # Convert to dict for inspection
    agent_info = agent.to_dict()
    print(f"Agent: {agent_info}")

asyncio.run(main())
```

### Agent Communication

Agents can communicate with each other through the messaging protocol:

```python
import asyncio
from aitbc_agent import Agent

async def main():
    # Create two agents
    agent1 = Agent.create(
        name="Agent-1",
        agent_type="provider",
        capabilities={"compute_type": "inference"}
    )
    
    agent2 = Agent.create(
        name="Agent-2",
        agent_type="consumer",
        capabilities={"compute_type": "training"}
    )
    
    await agent1.register()
    await agent2.register()
    
    # Send a message
    message_payload = {
        "job_type": "inference",
        "model": "llama2",
        "prompt": "Hello world"
    }
    
    success = await agent1.send_message(
        recipient_id=agent2.identity.id,
        message_type="job_request",
        payload=message_payload
    )
    
    print(f"Message sent: {success}")

asyncio.run(main())
```

## Advanced Features

### GPU Auto-Detection

The ComputeProvider can automatically detect GPU capabilities:

```python
from aitbc_agent import ComputeProvider

capabilities = ComputeProvider.assess_capabilities()
print(f"GPU Memory: {capabilities['gpu_memory']} MiB")
print(f"Supported Models: {capabilities['supported_models']}")
print(f"Performance Score: {capabilities['performance_score']}")
```

### Dynamic Pricing

Enable market-responsive pricing:

```python
await provider.enable_dynamic_pricing(
    base_rate=50.0,
    demand_threshold=0.8,  # 80% utilization triggers price increase
    max_multiplier=2.0,     # Maximum 2x base rate
    adjustment_frequency="15min"  # Adjust every 15 minutes
)
```

### Reputation and Earnings

Track agent performance and earnings:

```python
# Get reputation metrics
reputation = await agent.get_reputation()
print(f"Overall score: {reputation['overall_score']}")
print(f"Success rate: {reputation['job_success_rate']}")

# Get earnings information
earnings = await agent.get_earnings(period="30d")
print(f"Total earnings: {earnings['total']} AITBC")
print(f"Daily average: {earnings['daily_average']} AITBC")
```

## Configuration

### Coordinator URL

By default, agents connect to `http://localhost:8001`. Customize this:

```python
agent = Agent.create(
    name="MyAgent",
    agent_type="provider",
    capabilities={"compute_type": "inference"}
)
agent.coordinator_url = "http://custom-coordinator:8001"
```

### Custom Capabilities

Define detailed agent capabilities:

```python
capabilities = {
    "compute_type": "inference",
    "gpu_memory": 24,  # GB
    "supported_models": [
        "llama3.2",
        "mistral",
        "deepseek",
        "gpt-j"
    ],
    "performance_score": 0.95,
    "max_concurrent_jobs": 4,
    "specialization": "NLP",
    "latency_ms": 50,
    "throughput_tokens_per_sec": 100
}
```

## Error Handling

The SDK provides comprehensive error handling:

```python
import asyncio
from aitbc_agent import Agent
from aitbc.exceptions import NetworkError

async def main():
    try:
        agent = Agent.create(
            name="MyAgent",
            agent_type="provider",
            capabilities={"compute_type": "inference"}
        )
        
        success = await agent.register()
        
        if success:
            print("Registration successful")
        else:
            print("Registration failed")
            
    except NetworkError as e:
        print(f"Network error: {e}")
        # Implement retry logic or fallback
    except Exception as e:
        print(f"Unexpected error: {e}")

asyncio.run(main())
```

## Testing

Run the test suite:

```bash
cd packages/py/aitbc-agent-sdk
pytest tests/
```

## License

MIT
