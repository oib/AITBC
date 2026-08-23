# IPFS Storage

**Level**: Beginner
**Prerequisites**: Scenario 10 Agent SDK Identity
**Estimated Time**: 20 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

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

> **Live vs. simulated:** `aitbc ipfs` is **live** when the local Kubo daemon is running. If the daemon is down, the CLI stores/retrieves data through a local filesystem CID shim. Install the `aitbc-ipfs` service for live behavior.

This scenario demonstrates how to store and retrieve content-addressed artifacts with the real `aitbc ipfs` group, then announce a CID for sale with `aitbc oracle`. The live implementation is a **filesystem-backed** IPFS-compatible surface (`/var/lib/aitbc/ipfs`), not a separate IPFS daemon. The `aitbc_agent` SDK wraps the same CLI.

### Use Case

A training agent finishes a fine-tuning run and wants to (1) persist the resulting model weights to IPFS so they are reproducible and addressable by CID, (2) retrieve a previously stored dataset by its CID, and (3) announce the model artifact as available for purchase on the AITBC data oracle so other agents can buy it.

### What You'll Learn

- Upload, list, pin, and download files with `aitbc ipfs`
- Announce a CID for sale with `aitbc oracle store` and inspect listings with `aitbc oracle listings`
- Optionally wrap the same commands through the `aitbc_agent` SDK

---

## Prerequisites

### Knowledge Required

- Scenario 10 (Agent SDK Identity) — how to construct an `Agent` with `AgentIdentity` and `AgentCapabilities`
- Familiarity with content-addressed storage (CIDs)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Write access to `/var/lib/aitbc/ipfs` (created automatically on first `aitbc ipfs` invocation when the process can write there)
- Optional: `aitbc_agent` SDK (`pip install aitbc-agent-sdk`) for the SDK extras below

### Setup Required

- Confirm the CLI group exists: `aitbc ipfs --help`
- Confirm the oracle group exists: `aitbc oracle --help`

---

## Step-by-Step Workflow

The operator path is `aitbc ipfs` / `aitbc oracle`. The SDK examples below call the same commands.

### Step 1: Upload a file and get a CID

```bash
echo 'finetune-run-042 weights payload' > /tmp/finetune-run-042.weights
aitbc ipfs upload --file /tmp/finetune-run-042.weights --name finetune-run-042.weights --pin
```

**Expected output:** JSON including a `cid` that starts with `Qm` (SHA-256 digest of the bytes, not a real IPFS multihash from a daemon).

### Step 2: List and pin

```bash
aitbc ipfs list
aitbc ipfs pin "$CID"
```

**Expected output:** the uploaded item appears in the local index; pin reports success.

### Step 3: Download by CID

```bash
aitbc ipfs download "$CID" --output /tmp/finetune-run-042.restored
cmp /tmp/finetune-run-042.weights /tmp/finetune-run-042.restored && echo ROUNDTRIP_OK
```

### Step 4: Announce the CID on the data oracle

`aitbc oracle store` refuses CIDs that are not already in `/var/lib/aitbc/ipfs`.

```bash
aitbc oracle store --cid "$CID" --price 15.0 --description "Fine-tuned model weights, run 042"
aitbc oracle listings
```

**Expected output:** an `announcement_id` like `ann_…` and a listings payload that includes the CID at price `15.0`.

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

- Upload, list, pin, and download artifacts with `aitbc ipfs`
- Announce a CID for sale with `aitbc oracle store` and list announcements with `aitbc oracle listings`
- Optionally drive the same surface from the `aitbc_agent` SDK

---

## Validation

```bash
aitbc ipfs list
aitbc oracle listings
cmp /tmp/finetune-run-042.weights /tmp/finetune-run-042.restored && echo ROUNDTRIP_OK
```

---

## Related Resources

- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- Next: [Reputation Management](./12_reputation_management.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
