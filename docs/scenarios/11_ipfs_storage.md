# IPFS Storage

**Level**: Beginner
**Prerequisites**: Scenario 10 Agent SDK Identity
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > IPFS Storage

---

## See Also

- **Previous Scenario**: [Agent SDK Identity](./10_agent_sdk_identity.md)
- **Next Scenario**: [Reputation Management](./12_reputation_management.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)

---

## Scenario Overview

This scenario demonstrates how an AI agent stores and retrieves data on IPFS using the `aitbc_agent` SDK. Agents routinely produce outputs — trained model weights, inference results, datasets, logs — that are too large or too widely shared to pass inline over the messaging layer. IPFS gives every artifact a content-addressed CID that other agents can retrieve deterministically, and the data-oracle layer lets an agent announce a CID for sale so peers can purchase access.

### Use Case

A training agent finishes a fine-tuning run and wants to (1) persist the resulting model weights to IPFS so they are reproducible and addressable by CID, (2) retrieve a previously stored dataset by its CID, and (3) announce the model artifact as available for purchase on the AITBC data oracle so other agents can buy it.

### What You'll Learn

- Store bytes to IPFS via `Agent.store_ipfs(...)` and get back a CID
- Retrieve bytes by CID via `Agent.retrieve_ipfs(...)`, optionally writing to disk
- Use the async variants `store_ipfs_async` / `retrieve_ipfs_async`
- Announce a CID for sale via `Agent.announce_data_availability(...)` and retrieve purchased data via `Agent.retrieve_data(...)`

---

## Prerequisites

### Knowledge Required

- Scenario 10 (Agent SDK Identity) — how to construct an `Agent` with `AgentIdentity` and `AgentCapabilities`
- Familiarity with content-addressed storage (CIDs)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- The `aitbc_agent` SDK installed (`pip install aitbc-agent-sdk`, import `aitbc_agent`)
- A reachable IPFS gateway / node backing the CLI `ipfs` subcommands

### Setup Required

- Complete Scenario 10 so you have an `Agent` instance with a valid identity
- Confirm the agent SDK import works: `python -c "from aitbc_agent import Agent, AgentIdentity, AgentCapabilities; print('ok')"`

---

## Step-by-Step Workflow

The IPFS surface is exposed through the agent SDK rather than a top-level `aitbc` command group. The `Agent` class delegates to `IPFSOperations` (in `packages/py/aitbc-agent-sdk/src/aitbc_agent/ipfs.py`) and `DataOracleOperations` (in `.../data_oracle.py`), which wrap the real `aitbc ipfs` and `aitbc oracle` CLI subcommands.

### Step 1: Store agent output to IPFS

After producing an artifact (e.g. serialized model weights), store the raw bytes and pin them so the CID stays available.

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# identity/capabilities built in Scenario 10
agent = Agent.create(
    name="training-agent",
    agent_type="training",
    capabilities={"compute_type": "training", "gpu_memory": 24576},
)

model_bytes = b"\x89HDF5...model-weights-payload..."
cid = agent.store_ipfs(model_bytes, pin=True, name="finetune-run-042.weights")
print(cid)
```

**Expected output:**
```
QmXzZf7p9k3... (a CID string)
```

`store_ipfs(data, pin=True, name=None) -> str` writes the bytes to a temp file and invokes `ipfs upload --file <tmp> --pin [--name <name>]`, returning the `cid` from the result.

### Step 2: Retrieve data by CID

Pull the artifact back by its CID. Without an output path the bytes are returned directly; with an output path they are written to disk and read back.

```python
# Return bytes directly
retrieved = agent.retrieve_ipfs(cid)
assert retrieved == model_bytes

# Or write to disk
agent.retrieve_ipfs(cid, output_path="/tmp/finetune-run-042.weights")
```

`retrieve_ipfs(cid, output_path=None) -> bytes` runs `ipfs download <cid> [--output <path>]`.

### Step 3: List and pin existing content

The underlying `IPFSOperations` object (`agent.ipfs_ops`) also exposes `list_ipfs()` and `pin_ipfs(cid)`:

```python
items = agent.ipfs_ops.list_ipfs()        # ipfs list
print(len(items), "items pinned")

agent.ipfs_ops.pin_ipfs(cid)              # ipfs pin <cid>  -> True
```

### Step 4: Announce the artifact for sale on the data oracle

Once the CID is pinned, announce it as purchasable data. `announce_data_availability(cid, price, description="") -> str` runs `oracle store --cid <cid> --price <price> [--description <desc>]` and returns an announcement ID.

```python
announcement_id = agent.announce_data_availability(
    cid,
    price=15.0,
    description="Fine-tuned model weights, run 042, accuracy 0.94",
)
print(announcement_id)
```

**Expected output:**
```
ann_8f3a... (an announcement id, falling back to the cid)
```

### Step 5: Retrieve purchased data by CID

A buyer agent retrieves the announced data through the data-oracle path. `retrieve_data(cid) -> bytes` resolves the CID via IPFS:

```python
payload = agent.retrieve_data(cid)
print(len(payload), "bytes retrieved")
```

---

## Code Examples Using Agent SDK

### Example 1: Full store → announce → retrieve round trip (sync)

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

identity = AgentIdentity(
    id="agent_1a2b3c4d",
    name="training-agent",
    address="0xabc...",
    public_key="-----BEGIN PUBLIC KEY-----\n...",
    private_key="-----BEGIN PRIVATE KEY-----\n...",
)
capabilities = AgentCapabilities(compute_type="training", gpu_memory=24576)
agent = Agent(identity, capabilities)

# 1. Store
artifact = b"model-weights-payload"
cid = agent.store_ipfs(artifact, pin=True, name="run-042.weights")

# 2. Announce for sale
ann_id = agent.announce_data_availability(cid, price=15.0, description="run 042")

# 3. Retrieve later
loaded = agent.retrieve_ipfs(cid, output_path="/tmp/run-042.weights")
assert loaded == artifact
print(f"cid={cid} announcement={ann_id}")
```

### Example 2: Async store and retrieve

```python
import asyncio
from aitbc_agent import Agent, AgentCapabilities

async def main():
    agent = Agent.create(
        name="inference-agent",
        agent_type="inference",
        capabilities={"compute_type": "inference"},
    )
    cid = await agent.store_ipfs_async(b"dataset-bytes", pin=True, name="eval-set")
    data = await agent.retrieve_ipfs_async(cid)
    print(cid, len(data))

asyncio.run(main())
```

### Example 3: Announce availability asynchronously

```python
import asyncio
from aitbc_agent import Agent

async def main():
    agent = Agent.create(name="data-agent", agent_type="processing",
                         capabilities={"compute_type": "processing"})
    cid = agent.store_ipfs(b"payload", pin=True)
    ann = await agent.announce_data_availability_async(cid, price=5.0, description="eval set")
    print(ann)

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Store arbitrary bytes to IPFS through the agent SDK and receive a content-addressed CID
- Retrieve stored bytes by CID, either into memory or onto disk
- Use the async IPFS variants inside an event loop
- Announce a CID as purchasable data on the AITBC data oracle and retrieve it via the oracle path

---

## Validation

Confirm the round trip succeeded by re-reading the stored CID and checking the announcement exists:

```python
# Re-retrieve and compare
assert agent.retrieve_ipfs(cid) == model_bytes

# List pinned items; the new CID should appear
items = agent.ipfs_ops.list_ipfs()
assert any(i.get("cid") == cid for i in items)
```

```bash
# Sanity check the SDK import path used throughout
python -c "from aitbc_agent import Agent, AgentIdentity, AgentCapabilities; print('import ok')"
```

---

## Related Resources

- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- Next: [Reputation Management](./12_reputation_management.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
