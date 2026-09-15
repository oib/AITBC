# Cross-Chain Transfer

**Level**: Beginner
**Prerequisites**: [Scenario 19 Security Setup](./19_security_setup.md)
**Estimated Time**: 25 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Cross-Chain Transfer

---

## See Also

- **Previous Scenario**: [Scenario 19 Security Setup](./19_security_setup.md)
- **Next Scenario**: This is the final beginner scenario — return to [Agent Scenarios](./README.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Cross-Chain Reference](../blockchain/7_multichain.md)

---

## Scenario Overview

This scenario demonstrates how to perform cross-chain swaps, bridge operations, and atomic swaps using the `aitbc crosschain` and `aitbc bridge` CLI command groups, as well as the `aitbc_agent` SDK's atomic swap methods.

### Use Case

An agent needs to transfer tokens from one chain to another — either via a cross-chain swap through the exchange service, a bridge transaction, or an atomic swap using hash-locked smart contracts.

### What You'll Learn

- How to query cross-chain exchange rates with `aitbc crosschain rates`
- How to create and track cross-chain swaps with `aitbc crosschain swap` and `aitbc crosschain status`
- How to create bridge transactions with `aitbc crosschain bridge` and `aitbc crosschain bridge-status`
- How to manage the blockchain event bridge with `aitbc bridge start/status/stop`
- How to perform atomic swaps programmatically using the `aitbc_agent` SDK

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the `aitbc` CLI (see [Scenario 01 Wallet Basics](./01_wallet_basics.md))
- Understanding of cross-chain swaps, bridges, and atomic swap concepts (hashlock/timelock)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Python 3.13+ with the `aitbc_agent` package installed (`pip install aitbc-agent-sdk`)

### Setup Required

- A running blockchain node reachable at `http://localhost:8202` (RPC)
- A file wallet with a funded account on the source chain — `crosschain swap` and `crosschain bridge` sign the lock request with the wallet's private key (the same signing convention as `aitbc transactions send`)
- For SDK atomic swaps: a deployed `CrossChainAtomicSwap` contract and the `ContractConfig` set up

### Security Model for This Scenario

The bridge commands in this scenario exercise the **trusted-custodian bridge path** that is active in the default configuration:

- `bridge_release_enabled = False` (operator release)
- `bridge_multisig_enabled = False` (multi-sig verification not required)
- `bridge_require_merkle_proof = False` (Merkle inclusion proof not required)

The bridge supports a trust-minimized mode with multi-sig, Merkle proofs, and block-header verification, but those layers must be explicitly enabled and supplied with a validator set and source-chain block headers. Operators can inspect the current bridge security posture with `aitbc bridge security-status`.

### What "Real" Means Here (GAP-47)

`crosschain swap` and `crosschain bridge` submit a **signed `BRIDGE_LOCK` transaction** on the source chain. The `from_tx_hash`/`source_tx_hash` they print is the real hash of that on-chain transaction — it is also the bridge `transfer_id`. Settlement then follows the genuine bridge lifecycle:

| Status | Meaning |
|---|---|
| `pending` | Lock transaction submitted, awaiting block seal/finality |
| `locked` | Funds locked on the source chain |
| `confirmed` | Release recorded on the target chain, awaiting seal |
| `completed` | Release transaction sealed on the target chain |
| `failed` / `refunded` | Real failure or refund path |

A swap or bridge that cannot yet settle — because the lock is not sealed, finality is pending, or release infrastructure (`bridge_release_enabled`, validators, headers) is not configured — reports the honest intermediate state. The CLI never prints a `completed` status the bridge did not reach. `--wait` polls the real status endpoint until a terminal state or `--timeout`.

---

## Step-by-Step Workflow

### Step 1: Query Cross-Chain Exchange Rates

Check available exchange rates between chains. Without filters, all rates are displayed in a table.

```bash
# Show all cross-chain rates
aitbc crosschain rates

# Show rate for a specific pair
aitbc crosschain rates --from-chain ait-hub --to-chain ait-devnet
```

**Expected output (no rates configured):**

```
Cross-chain swap rates (operator-configured):

No configured swap rates; same-asset pairs settle at parity (1.0)
```

Rates come from the node's `cross_chain_swap_rates` setting (e.g. `ait-hub::ait-devnet=1.05`). There is no cross-chain AMM, so pairs without a configured rate are refused rather than priced from a fabricated table; same-asset pairs always settle at parity.

### Step 2: Create a Cross-Chain Swap

Initiate a token swap between two chains. The `--from-chain`, `--to-chain`, `--from-token`, `--to-token`, and `--amount` options are required; `--amount` is in AIT and is converted to compute-units for the signed lock. Slippage tolerance defaults to 0.01 (1%). The wallet named by `--wallet` (or the configured default wallet) signs the request; same-asset pairs settle at parity (rate 1.0), other pairs need an operator-configured rate in `cross_chain_swap_rates`.

```bash
aitbc crosschain swap \
    --from-chain ait-hub \
    --to-chain ait-devnet \
    --from-token AIT \
    --to-token AIT \
    --amount 100 \
    --slippage 0.02 \
    --wallet wallet-1 \
    --wait
```

**Expected output:**

```
Cross-chain swap locked on the source chain

Swap ID           swap_abc123
Transfer ID       0x9f2c...        # real BRIDGE_LOCK transaction hash
From Chain        ait-hub
To Chain          ait-devnet
Amount            100
Expected Amount   100
Rate              1.0
Total Fees        0.1
Status            pending
Source Tx Hash    0x9f2c...

Track swap with: aitbc crosschain status --swap-id swap_abc123
Swap status: ⏳ pending — lock submitted, awaiting block seal/finality
Swap status: ✓ confirmed — release recorded on target chain, awaiting seal
Swap status: ✅ completed — released on target chain
```

If the release path is not configured on the target side, `--wait` ends with the honest non-terminal state (e.g. `pending`/`locked`) instead of a fabricated `completed`.

### Step 3: Check Swap Status

Track the progress of a cross-chain swap using the swap ID returned from Step 2.

```bash
aitbc crosschain status --swap-id swap_abc123
```

**Expected output:**

```
⏳ pending — lock submitted, awaiting block seal/finality

Swap ID           swap_abc123
Transfer ID       0x9f2c...
From Chain        ait-hub
To Chain          ait-devnet
From Token        AIT
To Token          AIT
Amount            100
Expected Amount   100
Actual Amount     -
Status            pending
Lock Block Height -
Created At        2026-06-25T10:00:00Z
Completed At      -
Bridge Fee        0.1
From Tx Hash      0x9f2c...        # real BRIDGE_LOCK tx hash
To Tx Hash        -
```

`From Tx Hash` is the genuine on-chain lock transaction hash — queryable via the normal transaction/explorer endpoints. `To Tx Hash` only appears once a real release transaction exists on the target chain.

### Step 4: List Cross-Chain Swaps

List recent swaps, optionally filtered by user address or status.

```bash
# List recent swaps
aitbc crosschain swaps --limit 10

# Filter by status
aitbc crosschain swaps --status completed --limit 5
```

**Expected output:**

```
Found 3 cross-chain swaps:

+----------+----------+----------+--------+-----------+---------------------+
| ID       | From     | To       | Amount | Status    | Created             |
+==========+==========+==========+========+===========+=====================+
| swap_a...| ait-hub  | ait-dev  | 100    | pending   | 2026-06-25 10:00:00 |
| swap_b...| ait-dev  | ait-hub  | 50     | completed | 2026-06-25 09:30:00 |
| swap_c...| ait-hub  | ait-test | 200    | completed | 2026-06-25 08:15:00 |
+----------+----------+----------+--------+-----------+---------------------+
```

### Step 5: Create a Cross-Chain Bridge Transaction

Bridge tokens from one chain to another using the bridge subcommand.

```bash
aitbc crosschain bridge \
    --source-chain ait-hub \
    --target-chain ait-devnet \
    --token AIT \
    --amount 500 \
    --wallet wallet-1 \
    --recipient 0xrecipient789...
```

**Expected output:**

```
Cross-chain bridge lock submitted

Bridge ID         0x9f2c...        # transfer id == real source tx hash
Source Chain      ait-hub
Target Chain      ait-devnet
Token             AIT
Amount            500
Bridge Fee        0.5
Status            pending
Source Tx Hash    0x9f2c...

Track bridge with: aitbc crosschain bridge-status --bridge-id 0x9f2c...
```

### Step 6: Check Bridge Transaction Status

Track the bridge transaction using the bridge ID (the transfer id, equal to the source lock transaction hash). `--wait` polls until a terminal state.

```bash
aitbc crosschain bridge-status --bridge-id 0x9f2c... --wait
```

**Expected output:**

```
⏳ pending — lock submitted, awaiting block seal/finality

Bridge ID           0x9f2c...
Source Chain        ait-hub
Target Chain        ait-devnet
Asset               AIT
Amount              500
Sender              0xsender...
Recipient Address   0xrecipient789...
Status              pending
Lock Sealed         False
Lock Block Height   -
Created At          2026-06-25T10:05:00Z
Completed At        -
Source Tx Hash      0x9f2c...
Target Tx Hash      -
```

Once the lock is sealed and reaches finality, the node's bridge relayer confirms it automatically (when `bridge_relayer_enabled` and `bridge_release_enabled` are on). To relay a pending transfer manually — fetch its real Merkle proof and submit it to `/rpc/bridge/confirm` — use:

```bash
aitbc crosschain confirm --transfer-id 0x9f2c... --wallet wallet-1
```

### Step 7: View Liquidity Pools and Trading Stats

Check cross-chain liquidity pools and trading statistics.

```bash
# Show liquidity pools
aitbc crosschain pools

# Show trading statistics
aitbc crosschain stats
```

### Step 8: Manage the Blockchain Event Bridge

The `aitbc bridge` command group manages the blockchain event bridge service, which relays events between chains. It communicates with the blockchain RPC at `http://localhost:8202` by default.

```bash
# Start the bridge service
aitbc bridge start

# Check bridge status
aitbc bridge status

# Stop the bridge service
aitbc bridge stop

# Use a custom RPC URL
aitbc bridge start --rpc-url http://localhost:8202
```

**Expected output (start):**

```
Bridge Started

status          started
bridge_status   started
```

**Expected output (status):**

```
Bridge Status

status          running
bridge_status   active
```

**Expected output (stop):**

```
Bridge Stopped

status          stopped
bridge_status   stopped
```

---

## Code Examples Using Agent SDK

### Example 1: Atomic Swap via SDK Contract Integration

The `aitbc_agent` SDK provides four async atomic swap methods on the `Agent` class: `initiate_atomic_swap`, `complete_atomic_swap`, `get_swap_status`, and `refund_atomic_swap`. These require a `ContractConfig` with a `cross_chain_atomic_swap` contract address.

```python
import asyncio
import hashlib
import secrets
from aitbc_agent import Agent, AgentCapabilities
from aitbc_agent.contract_integration import ContractConfig

async def main():
    # Configure contract integration with the atomic swap contract address
    contract_config = ContractConfig(
        payment_processor="0xpayment...",
        agent_marketplace="0xmarket...",
        staking_contract="0xstaking...",
        treasury_manager="0xtreasury...",
        cross_chain_atomic_swap="0xatomic_swap_contract",
        use_cli=True,
        network="mainnet",
        rpc_url="http://localhost:8202",
    )

    # Create an agent with contract integration
    agent = Agent.create(
        name="Cross-Chain Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 1},
        # Note: contract_config is passed to the Agent constructor, not create()
    )

    # Rebuild agent with contract config (create() doesn't accept contract_config)
    from aitbc_agent import AgentIdentity
    agent = Agent(
        identity=agent.identity,
        capabilities=agent.capabilities,
        coordinator_url="http://localhost:8107",
        contract_config=contract_config,
    )

    await agent.register()

    # Generate a secret and hashlock for the atomic swap
    secret = secrets.token_hex(32)
    hashlock = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
    swap_id = f"swap_{secrets.token_hex(8)}"
    timelock = 3600  # 1 hour

    # Initiate the atomic swap
    print(f"Initiating atomic swap {swap_id}...")
    init_result = await agent.initiate_atomic_swap(
        swap_id=swap_id,
        token="AIT",
        amount=100,
        participant="0xparticipant123...",
        hashlock=hashlock,
        timelock=timelock,
        contract_address="0xatomic_swap_contract",
    )
    print(f"Initiated: {init_result}")

    # Check swap status
    status = await agent.get_swap_status(
        swap_id=swap_id,
        contract_address="0xatomic_swap_contract",
    )
    print(f"Swap status: {status}")

    # Complete the swap by revealing the secret
    complete_result = await agent.complete_atomic_swap(
        swap_id=swap_id,
        secret=secret,
        contract_address="0xatomic_swap_contract",
    )
    print(f"Completed: {complete_result}")

asyncio.run(main())
```

### Example 2: Refund an Expired Atomic Swap

If the counterparty does not complete the swap before the timelock expires, the initiator can reclaim their funds.

```python
import asyncio
from aitbc_agent import Agent
from aitbc_agent.contract_integration import ContractConfig

async def main():
    contract_config = ContractConfig(
        payment_processor="0xpayment...",
        agent_marketplace="0xmarket...",
        staking_contract="0xstaking...",
        treasury_manager="0xtreasury...",
        cross_chain_atomic_swap="0xatomic_swap_contract",
        use_cli=True,
        rpc_url="http://localhost:8202",
    )

    agent = Agent.create(
        name="Refund Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing"},
    )
    agent = Agent(
        identity=agent.identity,
        capabilities=agent.capabilities,
        contract_config=contract_config,
    )
    await agent.register()

    swap_id = "swap_expired_001"
    contract_address = "0xatomic_swap_contract"

    # Check if the swap is still pending past the timelock
    status = await agent.get_swap_status(swap_id=swap_id, contract_address=contract_address)
    print(f"Current status: {status}")

    # Refund the expired swap
    refund_result = await agent.refund_atomic_swap(
        swap_id=swap_id,
        contract_address=contract_address,
    )
    print(f"Refund result: {refund_result}")

asyncio.run(main())
```

### Example 3: Agent Orchestrates a Cross-Chain Swap via CLI

For swaps that go through the exchange service (rather than on-chain atomic swap contracts), an agent can use the `aitbc crosschain` CLI commands via subprocess.

```python
import asyncio
import subprocess
import json
from aitbc_agent import Agent, AgentCapabilities

async def main():
    agent = Agent.create(
        name="Swap Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 2},
    )
    await agent.register()

    # Create a cross-chain swap via the real aitbc CLI
    result = subprocess.run(
        [
            "aitbc", "crosschain", "swap",
            "--from-chain", "ait-hub",
            "--to-chain", "ait-devnet",
            "--from-token", "AIT",
            "--to-token", "AIT",
            "--amount", "100",
            "--slippage", "0.02",
        ],
        capture_output=True, text=True,
    )
    print("Swap created:", result.stdout)

    # Extract swap ID from output and poll status
    # (In production, parse the output to get the swap ID)
    swap_id = "swap_abc123"  # Extracted from the swap output

    status_result = subprocess.run(
        ["aitbc", "crosschain", "status", "--swap-id", swap_id],
        capture_output=True, text=True,
    )
    print("Swap status:", status_result.stdout)

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Query cross-chain exchange rates with `aitbc crosschain rates`
- Create and track cross-chain swaps with `aitbc crosschain swap` and `aitbc crosschain status`
- Create and track bridge transactions with `aitbc crosschain bridge` and `aitbc crosschain bridge-status`
- Manage the blockchain event bridge with `aitbc bridge start/status/stop`
- Perform atomic swaps programmatically using the `aitbc_agent` SDK's `initiate_atomic_swap`, `complete_atomic_swap`, `get_swap_status`, and `refund_atomic_swap` methods

---

## Validation

Verify that cross-chain operations are working:

```bash
# Confirm rates are available
aitbc crosschain rates

# Verify swap status is trackable
aitbc crosschain status --swap-id swap_abc123

# Check bridge service is running
aitbc bridge status

# Verify bridge transaction status (bridge-id == transfer id == source lock tx hash)
aitbc crosschain bridge-status --bridge-id 0x9f2c...

# Confirm liquidity pools are visible
aitbc crosschain pools
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `<hub-node>` ↔ shop `<node2>`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [Cross-Chain Documentation](../blockchain/7_multichain.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Back to Agent Scenarios](./README.md) — this is the final beginner scenario

---

*Last updated: 2026-09-15*
*Version: 1.3 — GAP-47: swap/bridge now submit signed real BRIDGE_LOCK transactions; statuses come from the genuine bridge lifecycle (`pending`/`locked`/`confirmed`/`completed`/`failed`/`refunded`), `--wait` polls real status, and `crosschain confirm` relays a pending transfer with its Merkle proof.*
