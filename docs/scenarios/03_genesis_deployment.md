# Genesis Deployment

**Level**: Beginner
**Prerequisites**: [Scenario 02 — Transaction Sending](./02_transaction_sending.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Genesis Deployment

---

## See Also

- **Previous Scenario**: [Transaction Sending](./02_transaction_sending.md)
- **Next Scenario**: [Messaging Basics](./04_messaging_basics.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Agent SDK Overview**: [Agent SDK Overview](../agent-sdk/AGENT_SDK_OVERVIEW.md)

---

## Scenario Overview

This scenario demonstrates how to initialize a blockchain's genesis block, verify its integrity, and inspect genesis configuration. The genesis block is the first block in a chain and defines the initial state — including token allocations, the proposer, and the chain ID.

### Use Case

Before an AI agent can send transactions or participate in consensus, a blockchain must be initialized with a genesis block. This scenario covers running the genesis generation script, verifying that the genesis block and accounts are correctly stored in the database, and inspecting genesis metadata.

### What You'll Learn

- How to initialize a genesis block with `aitbc genesis init`
- How to verify genesis integrity with `aitbc genesis verify`
- How to inspect genesis configuration with `aitbc genesis info`
- How to sync genesis from a hub node with `aitbc genesis sync-from-hub`

---

## Prerequisites

### Knowledge Required

- Completion of [Scenario 02 — Transaction Sending](./02_transaction_sending.md)
- Understanding of genesis blocks and blockchain initialization

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- The genesis generation script at `/opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py`
- Write access to `/var/lib/aitbc/data/` (for genesis files and database)

### Setup Required

- Set the `CHAIN_ID` environment variable or configure it in the AITBC config (e.g., `ait-mainnet`)
- Ensure the data directory `/var/lib/aitbc/data/` exists

---

## Step-by-Step Workflow

### Step 1: Initialize the Genesis Block

The `init` command runs the unified genesis generation script (`unified_genesis.py`). It creates the genesis block, allocates initial token balances, and optionally creates a genesis wallet with a secure random key.

```bash
# Initialize genesis with auto-detected chain ID and a genesis wallet
aitbc genesis init --chain-id ait-mainnet --create-wallet
```

You will be prompted for a wallet password (or provide it with `--password`).

**Expected output:**
```
Running genesis generation for ait-mainnet...
Genesis generation completed successfully
```

**Key options:**

| Option | Description |
|--------|-------------|
| `--chain-id` | Chain ID (auto-detected from config if not provided) |
| `--create-wallet` | Create a genesis wallet with a secure random key |
| `--password` | Wallet password (auto-generated if not provided) |
| `--proposer` | Proposer address (defaults to genesis wallet) |
| `--force` | Force overwrite existing genesis |
| `--register-service` | Register genesis wallet with the wallet service |
| `--service-url` | Wallet service URL (default: `http://localhost:8003`) |

### Step 2: Force Re-Initialize Genesis

If a genesis already exists, use `--force` to overwrite it:

```bash
aitbc genesis init --chain-id ait-mainnet --create-wallet --force
```

### Step 3: Verify Genesis Integrity

The `verify` command checks three things:
1. The genesis config file exists at `/var/lib/aitbc/data/<chain_id>/genesis.json`
2. The genesis block (height 0) exists in the chain database
3. The genesis wallet exists at `/var/lib/aitbc/keystore/genesis.json`

```bash
aitbc genesis verify --chain-id ait-mainnet
```

**Expected output:**
```
✓ Genesis config found: /var/lib/aitbc/data/ait-mainnet/genesis.json
chain_id           ait-mainnet
genesis_hash       0x0000000000000000000000000000000000000000000000000000000000000000
proposer           aitbc1genesis000000000000000000000000000000
allocations_count  3
✓ Genesis block found in database
height   0
hash     0x0000000000000000000000000000000000000000000000000000000000000000
proposer  aitbc1genesis000000000000000000000000000000
✓ Found 3 accounts in database
✓ Genesis wallet found: /var/lib/aitbc/keystore/genesis.json
address     aitbc1genesis000000000000000000000000000000
public_key  -----BEGIN PUBLIC-----
```

### Step 4: Inspect Genesis Information

The `info` command displays detailed genesis block data including block hash, parent hash, proposer, timestamp, and the first 5 token allocations.

```bash
aitbc genesis info --chain-id ait-mainnet
```

**Expected output:**
```
chain_id  ait-mainnet
genesis_block
  height        0
  hash          0x0000000000000000000000000000000000000000000000000000000000000000
  parent_hash   0x00
  proposer      aitbc1genesis000000000000000000000000000000
  timestamp     2026-06-25T12:00:00Z
  tx_count      0
allocations
  address       aitbc1genesis000000000000000000000000000000
  balance       1000000000
  nonce         0
total_allocations  3
```

If the chain ID is not provided, it is auto-detected from the running blockchain node's RPC health endpoint:

```bash
# Auto-detect chain ID from the node at http://localhost:8202
aitbc genesis info --rpc-url http://localhost:8202
```

### Step 5: Sync Genesis from a Hub Node

For follower nodes joining an existing network, use `sync-from-hub` to fetch the genesis block from a hub's RPC endpoint:

```bash
aitbc genesis sync-from-hub \
  --chain-id ait-mainnet \
  --rpc-url http://localhost:8202
```

**Expected output:**
```
Fetching genesis from hub: http://localhost:8202
Chain ID: ait-mainnet
✓ Genesis synced successfully: /var/lib/aitbc/data/ait-mainnet/genesis.json
chain_id      ait-mainnet
genesis_hash  0x0000000000000000000000000000000000000000000000000000000000000000
timestamp     2026-06-25T12:00:00Z
file_path     /var/lib/aitbc/data/ait-mainnet/genesis.json
```

Use `--force` to overwrite an existing genesis file:

```bash
aitbc genesis sync-from-hub --chain-id ait-mainnet --force
```

---

## Code Examples Using Agent SDK

### Example 1: Register an Agent After Genesis Initialization

Once the genesis block is deployed and the blockchain node is running, agents can register with the coordinator network. The `Agent.create()` method generates the identity, and `agent.register()` submits it to the coordinator.

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

async def main():
    # Create an agent for the newly initialized chain
    agent = Agent.create(
        name="genesis-agent",
        agent_type="inference",
        capabilities={
            "compute_type": "inference",
            "gpu_memory": 16384,
            "supported_models": ["llama-3"],
            "performance_score": 0.9,
            "max_concurrent_jobs": 2,
        },
    )

    # Register with the coordinator (default: http://localhost:9001)
    success = await agent.register()
    print(f"Registration successful: {success}")
    print(f"Agent ID: {agent.identity.id}")
    print(f"Address:  {agent.identity.address}")
    print(f"Registered: {agent.registered}")

asyncio.run(main())
```

**Expected output:**
```
Registration successful: True
Agent ID: agent_a1b2c3d4
Address:  0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b
Registered: True
```

### Example 2: Use Agent as Async Context Manager

The `Agent` class supports `async with` — it automatically registers on entry and logs cleanup on exit:

```python
import asyncio
from aitbc_agent import Agent

async def main():
    agent = Agent.create(
        name="context-agent",
        agent_type="processing",
        capabilities={"compute_type": "processing"},
    )

    async with agent:
        print(f"Agent {agent.identity.id} registered: {agent.registered}")
        # Perform agent operations here...
    # Agent cleanup logged on exit

asyncio.run(main())
```

### Example 3: Query Agent Reputation After Genesis

After the chain is live and the agent is registered, query its reputation score:

```python
import asyncio
from aitbc_agent import Agent

async def main():
    agent = Agent.create(
        name="reputation-agent",
        agent_type="inference",
        capabilities={"compute_type": "inference"},
    )
    await agent.register()

    reputation = await agent.get_reputation()
    print(f"Overall score:      {reputation['overall_score']}")
    print(f"Job success rate:   {reputation['job_success_rate']}")
    print(f"Avg response time:  {reputation['avg_response_time']}s")

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Initialize a genesis block with `aitbc genesis init` and a genesis wallet
- Verify genesis integrity (config file, database block, wallet) with `aitbc genesis verify`
- Inspect genesis block details and token allocations with `aitbc genesis info`
- Sync genesis from a hub node for follower deployment with `aitbc genesis sync-from-hub`
- Register an agent with the coordinator after chain initialization

---

## Validation

Verify that genesis was correctly deployed:

```bash
# Verify genesis block and accounts exist in the database
aitbc genesis verify --chain-id ait-mainnet

# Inspect genesis configuration
aitbc genesis info --chain-id ait-mainnet

# Verify the genesis file exists
ls -la /var/lib/aitbc/data/ait-mainnet/genesis.json

# Verify the genesis wallet exists
ls -la /var/lib/aitbc/keystore/genesis.json

# Check the blockchain node is running and reporting the correct chain ID
curl -s http://localhost:8202/rpc/health | python -m json.tool
```

---

## Related Resources

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent SDK Overview](../agent-sdk/AGENT_SDK_OVERVIEW.md)
- [Previous Scenario: Transaction Sending](./02_transaction_sending.md)
- [Next Scenario: Messaging Basics](./04_messaging_basics.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
