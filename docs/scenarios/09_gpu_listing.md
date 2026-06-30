# GPU Listing

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending
**Estimated Time**: 25 minutes
**Last Updated**: 2026-06-30
**Version**: 1.1

> **⚠️ DEPRECATION NOTICE (v0.4.7)**: The GPU-only marketplace with bidding was deprecated in v0.4.7. This scenario describes on-chain GPU resource registration which is still valid, but the marketplace bidding functionality referenced in prerequisites is no longer available. The current marketplace focuses on hardware+software bundles with fixed pricing.

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > GPU Listing

---

## See Also

- **Previous Scenario**: [Transaction Sending](./02_transaction_sending.md)
- **Next Scenario**: [Agent SDK Identity](./10_agent_sdk_identity.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Local GPU Commands](../../cli/aitbc_cli/commands/gpu_marketplace.py), [On-Chain GPU Commands](../../cli/aitbc_cli/commands/gpu_resources.py), [Resource Commands](../../cli/aitbc_cli/commands/resource.py)

---

## Scenario Overview

This scenario demonstrates how an AI agent registers GPUs with the local GPU service, records them immutably on the blockchain, queries and lists registered GPUs, and allocates GPU time to clients. It covers both the local `gpu` service commands and the on-chain `gpu-onchain` commands.

### Use Case

A compute provider agent has NVIDIA GPUs and wants to advertise them on the AITBC network. It auto-discovers GPU specs, registers them with the local GPU service, records the specs on-chain for verifiability, lists available GPUs, and allocates GPU time to a paying client.

### What You'll Learn

- How to auto-discover local GPU specifications with `nvidia-smi`
- How to register and unregister GPUs with the local GPU service (`gpu` group)
- How to register, query, and list GPUs on the blockchain (`gpu-onchain` group)
- How to allocate GPU time to a client on-chain
- How to model a compute provider with the `ComputeProvider` SDK class

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — on-chain GPU registration and allocation are blockchain transactions
- Scenario 08 (Marketplace Bidding) — familiarity with listing resources for sale

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- NVIDIA drivers and `nvidia-smi` available (for auto-discovery)
- A wallet for signing on-chain GPU transactions
- Blockchain RPC reachable at `http://localhost:8202`; GPU service reachable via CLI config

### Setup Required

- Configure `gpu_service_url` and `blockchain_rpc_url` via `aitbc config`
- Create a wallet (Scenario 01) to sign on-chain registrations
- Ensure the GPU service and blockchain node are running

---

## Step-by-Step Workflow

> **Two command groups**: The local GPU service commands are in the `gpu` group (`cli/aitbc_cli/commands/gpu_marketplace.py`). The on-chain GPU tracking commands are in the `gpu-onchain` group (`cli/aitbc_cli/commands/gpu_resources.py`, registered with `name="gpu-onchain"`). The `resource` group (`cli/aitbc_cli/commands/resource.py`) contains experimental allocation/utilization helpers.

### Step 1: Auto-discover local GPU specifications

Probe the local hardware via the GPU service (which calls `nvidia-smi`).

```bash
aitbc gpu discover
```

**Expected output:**
```
GPU discovery completed
GPU ID      Model          Memory (GB)   CUDA Version   Driver Version
gpu-0       RTX 4090       24            12.4           550.54.14
gpu-1       RTX 4090       24            12.4           550.54.14
```

### Step 2: Register a GPU with the local GPU service

Register a GPU by ID. Specs are auto-discovered if `--specs` is omitted; otherwise pass a JSON string.

```bash
# Auto-discovered specs
aitbc gpu register gpu-0

# Explicit specs override
aitbc gpu register gpu-0 --specs '{"model": "RTX 4090", "memory_gb": 24, "cuda_version": "12.4"}'
```

**Expected output:**
```
GPU gpu-0 registered successfully
GPU ID      Model        Memory (GB)   Price/Hour       Status
gpu-0       RTX 4090     24            0.0500 AIT       available
```

### Step 3: List and update local GPUs

```bash
# List all locally registered GPUs
aitbc gpu list

# Update pricing and status
aitbc gpu update gpu-0 --pricing '{"price_per_hour": 0.075}' --status active
```

**Expected output (list):**
```
Local Registered GPUs
=====================
GPU ID      Model        Memory (GB)   Price/Hour       Status      Region
gpu-0       RTX 4090     24            0.0750 AIT       active      us-east
gpu-1       RTX 4090     24            0.0500 AIT       available   us-east
```

### Step 4: Register a GPU on-chain (immutable specs)

Record the GPU's specifications on the blockchain so buyers can verify them. This uses the `gpu-onchain` group and requires a signing wallet.

```bash
aitbc gpu-onchain register \
  --gpu-id gpu-0 \
  --miner-id provider-agent-01 \
  --model "RTX 4090" \
  --memory-gb 24 \
  --cuda-version "12.4" \
  --region "us-east" \
  --capabilities inference training \
  --price-per-hour 0.075 \
  --wallet agent-wallet \
  --format json
```

**Expected output:**
```json
{
  "gpu_id": "gpu-0",
  "miner_id": "provider-agent-01",
  "model": "RTX 4090",
  "memory_gb": 24,
  "cuda_version": "12.4",
  "region": "us-east",
  "capabilities": ["inference", "training"],
  "price_per_hour": 0.075,
  "registered_by": "0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4",
  "status": "registered",
  "chain_id": "ait-mainnet"
}
```

### Step 5: Query and list on-chain GPUs

```bash
# Query a single GPU's on-chain record
aitbc gpu-onchain query gpu-0 --format table

# List all GPUs on-chain, filter by status
aitbc gpu-onchain list --status active --format table

# Query allocation history for a GPU
aitbc gpu-onchain allocations gpu-0
```

**Expected output (list):**
```
GPU ID      Model        Memory (GB)   Price/Hour       Status    Miner ID
gpu-0       RTX 4090     24            0.0750 AIT       active    provider-agent-01
gpu-1       RTX 4090     24            0.0500 AIT       active    provider-agent-01
```

### Step 6: Allocate GPU time to a client

Record a GPU allocation on-chain. The `--client-id` is the client's wallet address; `--wallet` is the signing wallet of the allocator.

```bash
aitbc gpu-onchain allocate \
  --gpu-id gpu-0 \
  --client-id 0x9f8e7d6c5b4a3928f1e0d2c3b4a5968778695a4b \
  --duration-hours 4.0 \
  --total-cost 0.30 \
  --wallet agent-wallet \
  --format json
```

**Expected output:**
```json
{
  "gpu_id": "gpu-0",
  "client_id": "0x9f8e7d6c5b4a3928f1e0d2c3b4a5968778695a4b",
  "duration_hours": 4.0,
  "total_cost": 0.30,
  "allocated_by": "0x1a2b3c4d5e6f7890a1b2c3d4e5f67890a1b2c3d4",
  "status": "allocated",
  "chain_id": "ait-mainnet"
}
```

### Step 7: Unregister a local GPU

Remove a GPU from the local GPU service (does not affect the on-chain record).

```bash
aitbc gpu unregister gpu-1
```

**Expected output:**
```
GPU gpu-1 unregistered successfully
```

### Step 8: Inspect resource status via coordinator (experimental)

The `resource` group exposes coordinator-mediated resource status and deallocation. The `allocate`, `list`, `release`, `utilization`, and `optimize` subcommands are experimental and require `--mock` for testing.

```bash
# Resource status from coordinator-api
aitbc resource status

# Deallocate a resource (use --force to skip confirmation)
aitbc resource deallocate alloc_12345 --force
```

---

## Code Examples Using Agent SDK

The `aitbc_agent` package exposes `ComputeProvider`, an `Agent` subclass for agents that provide compute resources. It offers resources on the marketplace, manages dynamic pricing, and accepts jobs.

### Example 1: Create a provider and offer resources

```python
import asyncio
from aitbc_agent import ComputeProvider

async def main() -> None:
    # Create a provider with a pricing model (keys generated automatically)
    provider = ComputeProvider.create_provider(
        name="gpu-provider-01",
        capabilities={
            "compute_type": "inference",
            "gpu_memory": 24,
            "supported_models": ["llama-3", "mistral-7b"],
            "performance_score": 0.9,
            "max_concurrent_jobs": 3,
            "specialization": "llm-inference",
        },
        pricing_model={"base_rate": 0.075, "currency": "AIT"},
    )
    provider.coordinator_url = "http://localhost:8203"
    await provider.register()

    # Offer resources on the marketplace at 0.075 AIT/hour
    ok = await provider.offer_resources(
        price_per_hour=0.075,
        availability_schedule={"monday": ["09:00-17:00"], "tuesday": ["09:00-17:00"]},
        max_concurrent_jobs=3,
    )
    print(f"Offer submitted: {ok}")
    print(f"Active offers: {len(provider.current_offers)}")

asyncio.run(main())
```

### Example 2: Enable dynamic pricing based on demand

```python
import asyncio
from aitbc_agent import ComputeProvider

async def main() -> None:
    provider = ComputeProvider.create_provider(
        name="gpu-provider-01",
        capabilities={"compute_type": "inference", "gpu_memory": 24, "max_concurrent_jobs": 3},
        pricing_model={"base_rate": 0.075, "currency": "AIT"},
    )
    provider.coordinator_url = "http://localhost:8203"
    await provider.register()
    await provider.offer_resources(0.075, {"default": "24x7"}, max_concurrent_jobs=3)

    # Dynamic pricing: raise price when utilization exceeds 80%, cap at 2x
    await provider.enable_dynamic_pricing(
        base_rate=0.075,
        demand_threshold=0.8,
        max_multiplier=2.0,
        adjustment_frequency="15min",
    )
    print("Dynamic pricing enabled")

asyncio.run(main())
```

### Example 3: Update availability and accept a job

```python
import asyncio
from aitbc_agent import ComputeProvider

async def main() -> None:
    provider = ComputeProvider.create_provider(
        name="gpu-provider-01",
        capabilities={"compute_type": "inference", "gpu_memory": 24, "max_concurrent_jobs": 3},
        pricing_model={"base_rate": 0.075, "currency": "AIT"},
    )
    provider.coordinator_url = "http://localhost:8203"
    await provider.register()
    await provider.offer_resources(0.075, {"default": "24x7"}, max_concurrent_jobs=3)

    # Update the availability schedule for all current offers
    await provider.set_availability({"weekday": "08:00-20:00", "weekend": "closed"})

    # Accept an incoming job request
    accepted = await provider.accept_job({
        "job_id": "job_abc123",
        "consumer_id": "consumer_01",
        "estimated_hours": 2.0,
    })
    print(f"Job accepted: {accepted}")
    print(f"Active jobs: {len(provider.active_jobs)}")

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Auto-discover and register local GPUs with the GPU service
- Record GPU specs immutably on the blockchain and query/list them
- Allocate GPU time to clients on-chain with a signed transaction
- Model a compute provider with the `ComputeProvider` SDK class and offer resources with dynamic pricing

---

## Validation

Verify both the local and on-chain GPU state:

```bash
# Local GPU service registry
aitbc gpu list

# On-chain GPU registry
aitbc gpu-onchain list --status active
aitbc gpu-onchain query gpu-0

# Allocation history
aitbc gpu-onchain allocations gpu-0

# Coordinator resource status
aitbc resource status
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/gpu_marketplace.py` (`gpu` group: discover, register, unregister, update, list)
- Source: `cli/aitbc_cli/commands/gpu_resources.py` (`gpu-onchain` group: register, query, allocate, allocations, list)
- Source: `cli/aitbc_cli/commands/resource.py` (`resource` group: status, deallocate, experimental allocate/list/release/utilization/optimize)
- SDK: `packages/py/aitbc-agent-sdk/src/aitbc_agent/compute_provider.py` (`ComputeProvider.create_provider`, `offer_resources`, `set_availability`, `enable_dynamic_pricing`, `accept_job`)
- [Next Scenario: Agent SDK Identity](./10_agent_sdk_identity.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
