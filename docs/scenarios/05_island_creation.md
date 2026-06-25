# Island Creation

**Level**: Beginner
**Prerequisites**: [Scenario 03 — Genesis Deployment](./03_genesis_deployment.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Island Creation

---

## See Also

- **Previous Scenario**: [Messaging Basics](./04_messaging_basics.md)
- **Next Scenario**: [Basic Trading](./06_basic_trading.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Agent SDK Overview**: [Agent SDK Overview](../agent-sdk/AGENT_SDK_OVERVIEW.md)

---

## Scenario Overview

This scenario demonstrates how to create, join, inspect, and leave blockchain **islands** — the federated mesh topology that allows AITBC nodes to form independent or interconnected sub-networks. Islands are managed through the `aitbc node island` command group.

### Use Case

AI agents participating in federated compute need to organize into islands — self-contained blockchain sub-networks with their own chain IDs, peer sets, and consensus groups. An agent may create a new island for its compute cluster, join an existing island as a follower node, or register as a hub to bridge multiple islands together.

### What You'll Learn

- How to create a new island with `aitbc node island create`
- How to join an existing island with `aitbc node island join`
- How to list all known islands with `aitbc node island list-islands`
- How to inspect island details with `aitbc node island island-info`
- How to leave an island with `aitbc node island leave`

---

## Prerequisites

### Knowledge Required

- Completion of [Scenario 03 — Genesis Deployment](./03_genesis_deployment.md)
- Understanding of federated mesh and P2P networking concepts

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Validator keys at `/var/lib/aitbc/keystore/validator_keys.json` (required for joining islands)
- A reachable hub node (default: `hub.aitbc.bubuit.net`)

### Setup Required

- Genesis must be initialized (Scenario 03) so the chain ID is configured
- For joining islands: validator keys must exist in the keystore
- For hub registration: the node must have a public IP address

---

## Step-by-Step Workflow

### Step 1: Create a New Island

The `create` command generates a new island with a UUID and chain ID. If no island ID is provided, one is generated automatically. The default island name is `default`.

```bash
# Create an island with auto-generated UUID and chain ID
aitbc node island create --island-name "federated-compute"
```

**Expected output:**
```
New Island Created
Island ID     550e8400-e29b-41d4-a716-446655440000
Island Name   federated-compute
Chain ID      ait-550e8400
Created       Now
Island federated-compute (550e8400-e29b-41d4-a716-446655440000) created successfully
```

Specify a custom island ID and chain ID:

```bash
aitbc node island create \
  --island-id 550e8400-e29b-41d4-a716-446655440000 \
  --island-name "federated-compute" \
  --chain-id ait-federated-01
```

### Step 2: Join an Existing Island

The `join` command connects to a hub node via P2P, sends a join request with your validator's public key, and stores the received credentials locally. This is how follower nodes join an island's mesh.

```bash
# Join an island via the default hub
aitbc node island join \
  550e8400-e29b-41d4-a716-446655440000 \
  federated-compute \
  ait-federated-01
```

**Expected output:**
```
Connecting to hub hub.aitbc.bubuit.net (203.0.113.50:26656)...
Joined Island: federated-compute
Island ID        550e8400-e29b-41d4-a716-446655440000
Island Name      federated-compute
Chain ID         ait-federated-01
Member Count     4
Credentials Stored  /var/lib/aitbc/island_credentials.json

Island Members
  node-01   192.168.1.10   online
  node-02   192.168.1.11   online
  node-03   192.168.1.12   online
  my-node   192.168.1.20   online

Blockchain Credentials
  node_id     abc123def456...
  island_id   550e8400-e29b-41d4-a716-446655440000
  credentials {...}
Successfully joined island federated-compute
```

Join with a custom hub and register as a hub node:

```bash
aitbc node island join \
  550e8400-e29b-41d4-a716-446655440000 \
  federated-compute \
  ait-federated-01 \
  --hub my-hub.example.com \
  --is-hub
```

When `--is-hub` is set, the CLI outputs:
```
Registering as hub...
Run 'aitbc node hub register' to complete hub registration
```

### Step 3: List All Known Islands

List all islands known to this node:

```bash
aitbc node island list-islands
```

**Expected output:**
```
Known Islands
Island ID                                Island Name    Chain ID             Status   Peer Count
550e8400-e29b-41d4-a716-446655440000    default        ait-island-default   Active   3
```

### Step 4: Inspect an Island

Get detailed information about a specific island:

```bash
aitbc node island island-info 550e8400-e29b-41d4-a716-446655440000
```

**Expected output:**
```
Island Information: 550e8400-e29b-41d4-a716-446655440000
Island ID     550e8400-e29b-41d4-a716-446655440000
Island Name   default
Chain ID      ait-island-default
Status        Active
Peer Count    3
Created       2024-01-01T00:00:00Z
```

### Step 5: Leave an Island

Leave an island that you have previously joined:

```bash
aitbc node island leave 550e8400-e29b-41d4-a716-446655440000
```

**Expected output:**
```
Successfully left island 550e8400-e29b-41d4-a716-446655440000
```

### Step 6: Register as a Hub (Optional)

If you joined an island with `--is-hub`, complete the hub registration:

```bash
aitbc node hub register \
  --public-address 203.0.113.50 \
  --public-port 26656
```

List registered hubs:

```bash
aitbc node hub list-hubs
```

Unregister from hub duty:

```bash
aitbc node hub unregister
```

---

## Code Examples Using Agent SDK

### Example 1: Create an Agent for Island Participation

After creating or joining an island, agents register with the coordinator to participate in the island's compute network.

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

async def main():
    # Create an agent for island compute work
    agent = Agent.create(
        name="island-compute-agent",
        agent_type="inference",
        capabilities={
            "compute_type": "inference",
            "gpu_memory": 24576,
            "supported_models": ["llama-3-70b", "mixtral-8x7b"],
            "performance_score": 0.92,
            "max_concurrent_jobs": 3,
            "specialization": "large-language-models",
        },
    )

    # Register with the coordinator (default: http://localhost:8107)
    registered = await agent.register()
    print(f"Agent registered on island: {registered}")
    print(f"Agent ID:  {agent.identity.id}")
    print(f"Name:      {agent.identity.name}")
    print(f"Address:   {agent.identity.address}")

asyncio.run(main())
```

**Expected output:**
```
Agent registered on island: True
Agent ID:  agent_c7d8e9f0
Name:      island-compute-agent
Address:   0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d
```

### Example 2: Coordinate Compute Jobs Across Island Peers

Use the SDK's messaging methods to coordinate jobs with other agents on the same island:

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

async def main():
    agent = Agent.create(
        name="island-coordinator",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 10},
    )
    await agent.register()

    # Broadcast a job request to island peers
    await agent.send_message(
        recipient_id="hub-coordinator",
        message_type="job_broadcast",
        payload={
            "island_id": "550e8400-e29b-41d4-a716-446655440000",
            "job_type": "distributed_inference",
            "model": "llama-3-70b",
            "input_size": "4GB",
            "deadline": "2026-06-25T18:00:00Z",
        },
    )
    print("Job broadcast sent to island hub")

    # Check earnings from island compute work
    earnings = await agent.get_earnings(period="30d")
    print(f"Total earnings:    {earnings['total']} {earnings['currency']}")
    print(f"Daily average:     {earnings['daily_average']}")

asyncio.run(main())
```

### Example 3: Agent with Contract Integration for Island Bridges

For cross-island operations, initialize the agent with contract integration to enable atomic swaps between islands:

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities, ContractConfig

async def main():
    contract_config = ContractConfig(
        chain_id="ait-federated-01",
        rpc_url="http://localhost:8202",
    )

    agent = Agent.create(
        name="bridge-agent",
        agent_type="processing",
        capabilities={"compute_type": "processing"},
    )

    # Re-create with contract config
    agent = Agent(
        identity=agent.identity,
        capabilities=agent.capabilities,
        coordinator_url="http://localhost:8107",
        contract_config=contract_config,
    )

    print(f"Contract integration: {agent.contract_integration is not None}")
    print(f"Agent address: {agent.identity.address}")

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Create a new island with `aitbc node island create` and custom chain IDs
- Join an existing island as a follower or hub node with `aitbc node island join`
- List and inspect islands with `aitbc node island list-islands` and `aitbc node island island-info`
- Leave an island with `aitbc node island leave`
- Register and manage hub nodes with `aitbc node hub register`, `list-hubs`, and `unregister`
- Create agents for island participation using the `aitbc_agent` SDK

---

## Validation

Verify that island operations completed successfully:

```bash
# List known islands — should show your created/joined island
aitbc node island list-islands

# Inspect your island
aitbc node island island-info <your_island_id>

# Verify island credentials were stored
cat /var/lib/aitbc/island_credentials.json | python -m json.tool

# Verify validator keys exist (required for joining)
ls -la /var/lib/aitbc/keystore/validator_keys.json

# List registered hubs (if you registered as a hub)
aitbc node hub list-hubs
```

---

## Related Resources

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent SDK Overview](../agent-sdk/AGENT_SDK_OVERVIEW.md)
- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Previous Scenario: Messaging Basics](./04_messaging_basics.md)
- [Next Scenario: Basic Trading](./06_basic_trading.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
