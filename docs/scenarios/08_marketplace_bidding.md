# Marketplace Bidding

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 07 AI Job Submission
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Marketplace Bidding

---

## See Also

- **Previous Scenario**: [AI Job Submission](./07_ai_job_submission.md)
- **Next Scenario**: [GPU Listing](./09_gpu_listing.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Marketplace Commands](../../cli/aitbc_cli/commands/marketplace_cmd.py)

---

## Scenario Overview

This scenario demonstrates how an AI agent lists chains for sale on the global chain marketplace, searches listings, purchases a chain, and completes the transaction with an on-chain hash.

### Use Case

A network operator wants to sell access to a private chain (e.g., a GPU-optimized compute chain) and an AI agent buyer wants to discover, evaluate, and purchase it. The agent lists the chain with specs and pricing, a buyer searches and purchases it, and the seller completes the transaction once the on-chain payment confirms.

### What You'll Learn

- How to list a chain for sale with specifications and metadata
- How to search and filter marketplace listings
- How to purchase a listed chain
- How to complete a marketplace transaction with a transaction hash

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — purchases produce on-chain transactions
- Scenario 07 (AI Job Submission) — familiarity with coordinator-mediated operations

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A wallet with funds in the listing currency (default `ETH`)
- Marketplace service reachable (configured via CLI config)

### Setup Required

- Configure the marketplace service URL via `aitbc config`
- Have a seller ID and buyer ID (typically wallet addresses or agent IDs)
- Know the chain type you are listing (must be a valid `ChainType` enum value)

---

## Step-by-Step Workflow

> **Argument shapes** (from `cli/aitbc_cli/commands/marketplace_cmd.py`): `list` takes six positional arguments (`chain_id`, `chain_name`, `chain_type`, `description`, `seller_id`, `price`) plus `--currency`, `--specs`, `--metadata`. `buy` takes positional `listing_id` and `buyer_id` plus `--payment`. `complete` takes positional `transaction_id` and `transaction_hash`.

### Step 1: List a chain for sale

List a chain with a price in the chosen currency. `--specs` and `--metadata` accept JSON strings.

```bash
# List a GPU compute chain for 2.5 ETH
aitbc marketplace list \
  gpu-chain-01 \
  "GPU Compute Chain" \
  private \
  "High-throughput GPU compute chain for inference workloads" \
  seller-agent-01 \
  2.5 \
  --currency ETH \
  --specs '{"gpu_count": 8, "gpu_model": "RTX 4090", "vram_gb": 192}' \
  --metadata '{"region": "us-east", "sla": "99.9%"}'
```

**Expected output:**
```
Chain listed successfully! Listing ID: chain_listing_20260625143012

Listing ID    chain_listing_20260625143012
Chain ID      gpu-chain-01
Chain Name    GPU Compute Chain
Type          private
Price         2.5 ETH
Seller        seller-agent-01
Status        active
Created       2026-06-25 14:30:12
```

> **Chain types**: The `chain_type` argument is validated against the `ChainType` enum. Invalid values are rejected with the list of valid values printed.

### Step 2: Search the marketplace

Search and filter listings by type, price range, seller, or status.

```bash
# Search for private chains under 3 ETH
aitbc marketplace search --type private --max-price 3 --format table

# Filter by a specific seller
aitbc marketplace search --seller seller-agent-01

# Only active listings
aitbc marketplace search --status active
```

**Expected output:**
```
Chain Listings
==============
Listing ID                  Chain ID        Chain Name          Type      Price     Seller
chain_listing_20260625...   gpu-chain-01    GPU Compute Chain   private   2.5 ETH   seller-agent-01
chain_listing_20260624...   ai-chain-02     AI Training Chain   private   1.8 ETH   seller-agent-02
```

### Step 3: Purchase a chain

Buy a listing by its ID. The `buyer_id` is a positional argument; `--payment` selects the payment method (default `crypto`).

```bash
# Purchase the GPU compute chain as buyer-agent-01
aitbc marketplace buy chain_listing_20260625143012 buyer-agent-01 --payment crypto
```

**Expected output:**
```
Purchase initiated! Transaction ID: tx_abc123def456789

Transaction ID    tx_abc123def456789
Listing ID        chain_listing_20260625143012
Buyer             buyer-agent-01
Payment Method    crypto
Status            pending
Created           2026-06-25 14:32:00
```

### Step 4: Complete the transaction

Once the on-chain payment confirms, complete the marketplace transaction with the blockchain transaction hash.

```bash
# Complete with the on-chain transaction hash
aitbc marketplace complete tx_abc123def456789 0x9f8e7d6c5b4a3928f1e0d2c3b4a5968778695a4b
```

**Expected output:**
```
Transaction tx_abc123def456789 completed successfully!

Transaction ID      tx_abc123def456789
Transaction Hash    0x9f8e7d6c5b4a3928f1e0d2c3b4a5968778695a4b
Status              completed
Completed           2026-06-25 14:35:10
```

---

## Code Examples Using Agent SDK

The marketplace flow is coordinated through the CLI's `GlobalChainMarketplace` core module. AI agents automate it by invoking the real `aitbc marketplace` commands. For programmatic access, the `aitbc_agent` SDK's `Agent` base class provides the HTTP client and identity used to interact with coordinator-mediated services.

### Example 1: List, search, and buy via the CLI

```python
import subprocess
import json

def run(cmd: list[str]) -> str:
    return subprocess.run(["aitbc", *cmd], capture_output=True, text=True, check=True).stdout

# 1. List a chain for sale
run([
    "marketplace", "list",
    "gpu-chain-01", "GPU Compute Chain", "private",
    "High-throughput GPU compute chain",
    "seller-agent-01", "2.5",
    "--currency", "ETH",
    "--specs", json.dumps({"gpu_count": 8}),
])

# 2. Search for private chains under 3 ETH
results = run(["marketplace", "search", "--type", "private", "--max-price", "3", "--format", "json"])
print(results)

# 3. Buy the first matching listing
listing_id = json.loads(results)[0]["listing_id"]
run(["marketplace", "buy", listing_id, "buyer-agent-01", "--payment", "crypto"])
```

### Example 2: Use an Agent identity to sign marketplace metadata

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# Create an agent to act as the buyer
agent = Agent.create(
    name="marketplace-buyer",
    agent_type="consumer",
    capabilities={"compute_type": "processing", "max_concurrent_jobs": 1},
)

# Sign a purchase intent message with the agent's RSA key
intent = {"listing_id": "chain_listing_20260625143012", "buyer_id": agent.identity.id}
signature = agent.identity.sign_message(intent)
print(f"Signed intent for {agent.identity.id}: {signature[:32]}...")

# Verify the signature round-trips
assert agent.identity.verify_signature(intent, signature)
print("Signature verified")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- List a chain for sale with specs, metadata, and a priced currency
- Search and filter marketplace listings by type, price, seller, and status
- Purchase a listing and complete the transaction with an on-chain hash
- Automate the marketplace flow from Python using the real CLI and the `aitbc_agent` identity primitives

---

## Validation

Verify the listing and transaction lifecycle:

```bash
# The listing should appear in search results
aitbc marketplace search --status active

# The purchase transaction should be completable
aitbc marketplace complete <transaction_id> <transaction_hash>

# Confirm the listing is no longer active after completion
aitbc marketplace search --status active --seller seller-agent-01
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/marketplace_cmd.py` (list, buy, complete, search)
- Core: `cli/aitbc_cli/core/marketplace.py` (`GlobalChainMarketplace`, `ChainType`, `MarketplaceStatus`)
- [Next Scenario: GPU Listing](./09_gpu_listing.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
