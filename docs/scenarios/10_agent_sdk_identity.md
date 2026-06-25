# Agent SDK Identity

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics, Scenario 09 GPU Listing
**Estimated Time**: 25 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Agent SDK Identity

---

## See Also

- **Previous Scenario**: [GPU Listing](./09_gpu_listing.md)
- **Next Scenario**: [IPFS Storage](./11_ipfs_storage.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Agent SDK CLI Commands](../../cli/aitbc_cli/commands/agent_sdk.py), [Agent SDK Core](../../packages/py/aitbc-agent-sdk/src/aitbc_agent/agent.py)

---

## Scenario Overview

This scenario demonstrates how an AI agent creates and configures its own identity using the `aitbc_agent` SDK and the `aitbc agent` CLI group. It covers creating an agent with generated cryptographic keys, registering it on the network, managing its local configuration file, and validating/importing/exporting that configuration.

### Use Case

A new AI agent joins the AITBC network. It needs a persistent identity (RSA keypair, agent ID, address), a set of capabilities describing what it can do, and a local configuration file so it can be reused across sessions. The agent also registers its identity on-chain so other participants can discover and verify it.

### What You'll Learn

- How to create an agent with the `aitbc agent create` command and the `Agent.create` SDK method
- How to register an agent on the network and on-chain
- How to list, inspect, and check the status of local agents
- How to set, get, validate, import, and export agent configuration files

---

## Prerequisites

### Knowledge Required

- Scenario 01 (Wallet Basics) — agent config files live alongside wallet configs under `~/.aitbc/`
- Scenario 09 (GPU Listing) — capabilities describe the compute resources an agent offers

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- The `aitbc_agent` SDK installed (`pip install aitbc-agent-sdk`; import `aitbc_agent`)
- Coordinator API reachable at `http://localhost:8203`; agent-coordinator at `http://localhost:9001`; blockchain RPC at `http://localhost:8202`

### Setup Required

- Install the Agent SDK: `pip install aitbc-agent-sdk`
- Ensure the coordinator-api and agent-coordinator services are running
- Have a wallet for on-chain identity registration

---

## Step-by-Step Workflow

> **Command group**: The agent SDK commands live in the `agent` group (`cli/aitbc_cli/commands/agent_sdk.py`, registered as `cli.add_command(agent, name="agent")` in `cli/aitbc_cli/core/main.py`). This is distinct from the `agent-msg` (messaging) and `agent-comm` (cross-chain communication) groups.

### Step 1: Create a new agent

Create an agent with a name, type, and capabilities. The CLI generates an RSA keypair and saves a config file to `~/.aitbc/agents/<name>.json`.

```bash
# Create a provider agent that offers inference on a 24GB GPU
aitbc agent create my-provider \
  --type provider \
  --compute-type inference \
  --gpu-memory 24 \
  --models llama-3,mistral-7b \
  --performance 0.9 \
  --max-jobs 3 \
  --specialization llm-inference \
  --coordinator-url http://localhost:8203 \
  --format table
```

**Expected output:**
```
Agent created successfully!

Agent Created
=============
Field              Value
Agent ID           agent_a1b2c3d4
Name               my-provider
Address            0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4
Type               provider
Compute Type       inference
GPU Memory         24 GB
Performance Score  0.90
Max Jobs           3
Config File        /home/agent/.aitbc/agents/my-provider.json
```

> **Auto-detect**: Pass `--auto-detect` instead of manual capability flags to probe the local system via `ComputeProvider.assess_capabilities()`.

### Step 2: List local agents

List all agent configurations stored under `~/.aitbc/agents/`.

```bash
aitbc agent list --format table
```

**Expected output:**
```
Local Agents
============
Name          Type       Address                                      File
my-provider   provider   0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4   /home/agent/.aitbc/agents/my-provider.json
my-consumer   consumer   0x9f8e7d6c5b4a3928f1e0d2c3b4a5968778695a4b   /home/agent/.aitbc/agents/my-consumer.json
```

### Step 3: Check agent status

Query the coordinator for an agent's status, reputation, and last-seen timestamp.

```bash
aitbc agent status agent_a1b2c3d4 --format table
```

**Expected output:**
```
Agent Status: agent_a1b2c3d4
============================
Field              Value
Agent ID           agent_a1b2c3d4
Status             active
Registered         True
Reputation Score   0.850
Last Seen          2026-04-29T09:40:00Z
Message            Agent status retrieved (simulated)
```

### Step 4: Register the agent on the network

Register the agent with the coordinator. The default coordinator URL is `http://localhost:8107`; override with `--coordinator-url`.

```bash
aitbc agent register agent_a1b2c3d4 --coordinator-url http://localhost:8203 --format table
```

**Expected output:**
```
Agent agent_a1b2c3d4 registered successfully!

Agent Registration
==================
Field              Value
Agent ID           agent_a1b2c3d4
Registered         True
Coordinator URL    http://localhost:8203
Message            Agent registered successfully (simulated)
```

### Step 5: Register agent identity on-chain

Record the agent's identity on the blockchain so it can be discovered and verified by other participants. Requires the agent's address (bech32) and a display name.

```bash
aitbc agent register-identity agent_a1b2c3d4 0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4 \
  --display-name "My Provider Agent" \
  --agent-type provider \
  --format json
```

**Expected output:**
```json
{
  "identity_id": "id_abc123",
  "agent_id": "agent_a1b2c3d4",
  "agent_address": "0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4",
  "chain_id": "ait-mainnet",
  "status": "registered",
  "is_verified": false
}
```

### Step 6: Get and verify on-chain identity

```bash
# Fetch the on-chain identity record
aitbc agent get-identity agent_a1b2c3d4 --format table

# Verify the identity with a verifier address
aitbc agent verify-identity agent_a1b2c3d4 0xverifieraddress123 --format json
```

### Step 7: Manage agent configuration

Set, get, and validate configuration values on the agent's local JSON file.

```bash
# Set a configuration value (JSON values are parsed; plain strings are stored as-is)
aitbc agent config-set my-provider pricing_model '{"base_rate": 0.075, "currency": "AIT"}'

# Retrieve a single key
aitbc agent config-get my-provider --key pricing_model --format table

# Retrieve the full configuration
aitbc agent config-get my-provider --format table

# Validate the configuration (checks required fields and capabilities structure)
aitbc agent config-validate my-provider
```

**Expected output (validate):**
```
Configuration is valid: my-provider
```

> **Validation rules** (from `validate_agent_config`): required fields are `agent_id`, `name`, `address`, `agent_type`, `capabilities`; `capabilities` must contain a `compute_type` key.

### Step 8: Export and import agent configuration

Move an agent configuration between machines.

```bash
# Export to a file
aitbc agent config-export my-provider ./my-provider-backup.json

# Import on another machine (optionally override the name)
aitbc agent config-import ./my-provider-backup.json --name my-provider-restored
```

**Expected output (export):**
```
Configuration exported: my-provider -> ./my-provider-backup.json
```

### Step 9: Discover agents by capability

Use the agent-coordinator (port 9001) to discover agents matching a capability.

```bash
aitbc agent discover agents \
  --capability inference \
  --agent-type provider \
  --min-health 0.5 \
  --limit 20 \
  --coordinator-url http://localhost:9001 \
  --format table
```

---

## Code Examples Using Agent SDK

The `aitbc_agent` package exposes `Agent`, `AgentIdentity`, and `AgentCapabilities`. `Agent.create` generates an RSA keypair and returns a ready-to-register agent. `AgentIdentity` holds the id, name, address, and keys; `AgentCapabilities` describes compute resources.

### Example 1: Create an agent and register it

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

async def main() -> None:
    # Create a general agent with capabilities (RSA keys generated automatically)
    agent = Agent.create(
        name="my-agent",
        agent_type="general",
        capabilities={
            "compute_type": "inference",
            "gpu_memory": 24,
            "supported_models": ["llama-3", "mistral-7b"],
            "performance_score": 0.9,
            "max_concurrent_jobs": 3,
            "specialization": "llm-inference",
        },
    )
    # Point at the local coordinator (default is http://localhost:9001)
    agent.coordinator_url = "http://localhost:8203"

    print(f"Agent ID:  {agent.identity.id}")
    print(f"Name:      {agent.identity.name}")
    print(f"Address:   {agent.identity.address}")

    # Register on the network (async, signs the registration with the agent's key)
    ok = await agent.register()
    print(f"Registered: {ok} (agent.registered={agent.registered})")

asyncio.run(main())
```

### Example 2: Build AgentIdentity and AgentCapabilities manually

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# Construct capabilities directly (dataclass)
caps = AgentCapabilities(
    compute_type="training",
    gpu_memory=80,
    supported_models=["llama-3-70b"],
    performance_score=0.95,
    max_concurrent_jobs=2,
    specialization="large-model-training",
)

# Construct an identity from existing keys (e.g. loaded from a config file)
identity = AgentIdentity(
    id="agent_a1b2c3d4",
    name="my-agent",
    address="0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4",
    public_key="<PEM public key string>",
    private_key="<PEM private key string>",
)

agent = Agent(identity, caps, coordinator_url="http://localhost:8203")
print(f"Loaded agent {agent.identity.name} ({agent.identity.id})")
```

### Example 3: Sign and verify a message with the agent's key

```python
from aitbc_agent import Agent

agent = Agent.create(name="signer", agent_type="general", capabilities={"compute_type": "processing"})

message = {"action": "bid", "listing_id": "chain_listing_123", "amount": 2.5}
signature = agent.identity.sign_message(message)
print(f"Signature: {signature[:32]}...")

# Any party with the public key can verify
valid = agent.identity.verify_signature(message, signature)
print(f"Signature valid: {valid}")
assert valid
```

### Example 4: Query reputation after registration

```python
import asyncio
from aitbc_agent import Agent

async def main() -> None:
    agent = Agent.create(name="my-agent", agent_type="general", capabilities={"compute_type": "inference"})
    agent.coordinator_url = "http://localhost:8203"
    await agent.register()

    reputation = await agent.get_reputation()
    print(f"Reputation: {reputation}")

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Create an agent with generated RSA keys via the CLI and the `Agent.create` SDK method
- Register the agent on the network and record its identity on-chain
- List, inspect, and check the status of local agents
- Set, get, validate, import, and export agent configuration files
- Construct `AgentIdentity` and `AgentCapabilities` manually and sign/verify messages

---

## Validation

Verify the agent identity and configuration are consistent:

```bash
# The agent config file should exist and validate
aitbc agent list
aitbc agent config-validate my-provider

# The on-chain identity should be retrievable
aitbc agent get-identity agent_a1b2c3d4

# The agent should be discoverable via the agent-coordinator
aitbc agent discover agents --capability inference --coordinator-url http://localhost:9001

# Confirm the config file on disk
cat ~/.aitbc/agents/my-provider.json
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/agent_sdk.py` (`agent` group: create, register, register-identity, get-identity, verify-identity, list, status, capabilities, config-set, config-get, config-validate, config-import, config-export, discover)
- Registration: `cli/aitbc_cli/core/main.py` (`cli.add_command(agent, name="agent")`)
- SDK: `packages/py/aitbc-agent-sdk/src/aitbc_agent/agent.py` (`Agent`, `AgentIdentity`, `AgentCapabilities`)
- SDK: `packages/py/aitbc-agent-sdk/src/aitbc_agent/__init__.py` (lazy exports)
- [Next Scenario: IPFS Storage](./11_ipfs_storage.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
