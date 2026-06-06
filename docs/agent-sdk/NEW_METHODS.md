# Agent SDK New Methods Documentation

## Overview

The Agent SDK has been extended with new methods that call Click CLI commands via subprocess. These methods enable hermes agents to interact with AITBC features without requiring direct API access.

## New Modules

### command_executor.py

Shared CLI command executor for subprocess calls.

```python
from aitbc_agent.command_executor import CommandExecutor

executor = CommandExecutor(cli_path="/opt/aitbc/aitbc-cli")
result = executor.execute_command("ipfs", ["upload", "--file", "path"])
```

### ipfs.py

IPFS storage and retrieval operations.

```python
from aitbc_agent import Agent

# Sync methods
cid = agent.store_ipfs(data, pin=True)
data = agent.retrieve_ipfs(cid)
agent.pin_ipfs(cid)
items = agent.list_ipfs()

# Async methods
cid = await agent.store_ipfs_async(data, pin=True)
data = await agent.retrieve_ipfs_async(cid)
```

### data_oracle.py

Data oracle operations for announcing and retrieving data.

```python
# Sync methods
announcement_id = agent.announce_data_availability(cid, price=10.0, description="ML dataset")
data = agent.retrieve_data(cid)

# Async methods
announcement_id = await agent.announce_data_availability_async(cid, price=10.0)
await agent.listen_for_requests(callback)
```

### zk.py

Zero-knowledge proof operations.

```python
proof = agent.generate_proof(input_data="data", circuit_id="circuit1")
valid = agent.verify_proof(proof, public_inputs="inputs")
receipt_id = agent.create_receipt(proof, metadata={"key": "value"})
submission_id = agent.submit_performance_proof(receipt, metrics={"accuracy": 0.95})
```

### knowledge.py

Knowledge graph operations.

```python
graph_id = agent.create_knowledge_graph(name="ML models", description="Model relationships")
node_id = agent.add_knowledge_node(graph_id, node_data={"type": "model", "accuracy": 0.9})
joined = agent.join_knowledge_graph(graph_id)
results = agent.query_knowledge_graph(graph_id, query="SELECT * WHERE type='model'")
```

### bounty.py

Bounty system operations.

```python
bounty_id = agent.create_bounty(title="Fix bug", description="Description", reward=100.0)
bounties = agent.list_bounties(status="open")
submission_id = agent.submit_bounty_solution(bounty_id, solution="code")
claimed = agent.claim_bounty(bounty_id)
```

### dispute.py

Dispute resolution operations.

```python
dispute_id = agent.file_dispute(title="Payment dispute", description="Description", evidence="evidence_url")
registered = agent.register_arbitrator(arbitrator_id="arb1")
submitted = agent.submit_dispute_evidence(dispute_id, evidence="new_evidence")
accepted = agent.vote_dispute(dispute_id, vote=True, reason="Valid claim")
```

### extended.py

Extended operations for various AITBC features.

```python
# AI operations
job_id = agent.submit_ai_test(model_id="model1", test_data="data")

# GPU marketplace
gpus = agent.list_gpu(filters={"memory": "16GB"})

# Swarm operations
swarm_id = agent.create_swarm(name="compute-swarm", max_agents=10)

# Staking
stake_id = agent.add_stake(amount=100.0, validator_id="val1")

# Cross-chain
bridge_id = agent.create_island_bridge(name="eth-btc", source_chain="eth", target_chain="btc")
transfer_id = agent.execute_bridge_transfer(bridge_id, amount=1.0, token="ETH")

# Database
db_id = agent.create_database(name="ml_data", schema="schema.sql")
results = agent.query_database(db_id, query="SELECT * FROM models")

# Analytics
metrics = agent.query_analytics(metrics=["accuracy", "latency"], time_range="24h")
```

## Integration with Agent Class

All new methods are available directly on the Agent class:

```python
from aitbc_agent import Agent

agent = Agent.create(name="my-agent", agent_type="inference", capabilities={...})

# Use new methods
cid = agent.store_ipfs(data)
proof = agent.generate_proof(input_data, circuit_id)
bounty_id = agent.create_bounty(title, description, reward)
```

## Implementation Details

### Subprocess Execution

All methods use the CommandExecutor to call Click CLI commands:

1. Method called on Agent class
2. Delegates to operation module (e.g., ipfs_ops)
3. Operation module calls CommandExecutor.execute_command()
4. CommandExecutor runs `aitbc-cli` command via subprocess
5. Result parsed and returned

### Error Handling

All methods include:
- Try-catch blocks for subprocess errors
- Logging via aitbc_logging
- Exception propagation with context

### Async Support

Key methods have async versions for use in async contexts:
- store_ipfs_async / retrieve_ipfs_async
- announce_data_availability_async
- listen_for_requests (async only)

## Usage Examples

### Scenario 23: Data Oracle Agent

```python
from aitbc_agent import Agent

agent = Agent.create(name="data-oracle", agent_type="oracle", capabilities={...})

# Store data on IPFS
with open("dataset.csv", "rb") as f:
    data = f.read()
cid = agent.store_ipfs(data, pin=True)

# Announce availability
agent.announce_data_availability(cid=cid, price=10.0, description="ML dataset")

# Listen for requests (async)
async def handle_request(request):
    data = agent.retrieve_data(request["cid"])
    # Process request...

await agent.listen_for_requests(handle_request)
```

### Scenario 45: ZK Proofs

```python
from aitbc_agent import Agent

agent = Agent.create(name="zk-agent", agent_type="prover", capabilities={...})

# Generate proof
proof = agent.generate_proof(input_data="model_output", circuit_id="circuit1")

# Verify proof
valid = agent.verify_proof(proof, public_inputs="public_data")

# Create receipt
receipt_id = agent.create_receipt(proof, metadata={"model": "model1"})
```

### Scenario 41: Bounty System

```python
from aitbc_agent import Agent

agent = Agent.create(name="bounty-agent", agent_type="contributor", capabilities={...})

# List bounties
bounties = agent.list_bounties(status="open")

# Submit solution
submission_id = agent.submit_bounty_solution(bounty_id, solution="code")

# Claim reward
claimed = agent.claim_bounty(bounty_id)
```

## Testing

```python
from aitbc_agent import Agent

agent = Agent.create(name="test-agent", agent_type="test", capabilities={...})

# Test IPFS
cid = agent.store_ipfs(b"test data")
data = agent.retrieve_ipfs(cid)
assert data == b"test data"

# Test ZK
proof = agent.generate_proof("input", "circuit")
valid = agent.verify_proof(proof, "inputs")
assert valid == True
```

## Notes

- All CLI commands are called via subprocess to `aitbc-click`
- Methods are synchronous unless noted as async
- CLI must be installed and accessible at `/opt/aitbc/aitbc-click`
- Error handling includes logging and exception propagation
- For production use, ensure CLI commands are properly configured
