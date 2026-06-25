# Mining Setup

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Mining Setup

---

## See Also

- **Previous Scenario**: [Reputation Management](./12_reputation_management.md)
- **Next Scenario**: [Staking Basics](./14_staking_basics.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Mining CLI source](../../cli/aitbc_cli/commands/mining.py)

---

## Scenario Overview

This scenario walks an AI agent through starting, monitoring, and stopping a blockchain miner using the `aitbc mining` CLI group. Mining secures the chain and pays block rewards to the miner's wallet address. The CLI talks to the blockchain RPC (default `http://localhost:8202`) and reads the miner's address from the local keystore wallet created in Scenario 01.

### Use Case

A node-operating agent wants to dedicate spare compute to securing the network and earning block rewards. It starts mining into an existing wallet, periodically checks status, lists active miners on the node, and cleanly stops mining when the compute is needed elsewhere.

### What You'll Learn

- Start mining with `aitbc mining start <wallet_name>` and tune thread count
- Check mining status with `aitbc mining status`
- List active miners with `aitbc mining list`
- Stop mining with `aitbc mining stop`
- Override the blockchain RPC URL per command

---

## Prerequisites

### Knowledge Required

- Scenario 01 (Wallet Basics) — you need a funded wallet in the keystore to mine into
- The blockchain node must be running and reachable at the RPC URL (default `http://localhost:8202`)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A wallet JSON in the keystore directory (`~/.aitbc/wallets/<name>.json`)

### Setup Required

- Create a wallet (Scenario 01): `aitbc wallet create --name miner-wallet`
- Confirm the wallet file exists and has an `address` field
- Start a blockchain node with RPC listening on `http://localhost:8202`

---

## Step-by-Step Workflow

All commands below are grounded in `cli/aitbc_cli/commands/mining.py`. The default RPC URL is `http://localhost:8202` (`DEFAULT_RPC_URL`); override it with `--rpc-url` on any command.

### Step 1: Start mining into a wallet

`aitbc mining start <wallet_name>` loads `<wallet_name>.json` from the keystore, reads its `address`, and posts `{miner_address, threads, enabled: true}` to `POST /rpc/mining/start`. Options: `--threads` (default `1`), `--rpc-url`.

```bash
aitbc mining start miner-wallet --threads 4
```

**Expected output:**
```
Mining started with wallet 'miner-wallet'
Miner address: 0x1a2b3c4d5e6f...
Threads: 4
Status: started
```

If the wallet is missing you'll see `Wallet 'miner-wallet' not found`. Point at a different node with `--rpc-url`:

```bash
aitbc mining start miner-wallet --threads 4 --rpc-url http://node-2.local:8202
```

### Step 2: Check mining status

`aitbc mining status` calls `GET /rpc/mining/status` and prints the JSON result.

```bash
aitbc mining status
```

**Expected output:**
```json
{
  "enabled": true,
  "miner_address": "0x1a2b3c4d5e6f...",
  "threads": 4,
  "blocks_mined": 12,
  "hashrate": 18432,
  "status": "running"
}
```

### Step 3: List active miners on the node

`aitbc mining list` calls `GET /rpc/mining/miners`.

```bash
aitbc mining list
```

**Expected output:**
```json
{
  "miners": [
    {
      "address": "0x1a2b3c4d5e6f...",
      "threads": 4,
      "status": "running",
      "blocks_mined": 12
    }
  ],
  "count": 1
}
```

### Step 4: Stop mining

`aitbc mining stop` calls `POST /rpc/mining/stop`.

```bash
aitbc mining stop
```

**Expected output:**
```
Mining stopped
Status: stopped
```

Verify it stopped:

```bash
aitbc mining status
```
```json
{
  "enabled": false,
  "status": "stopped"
}
```

---

## Code Examples Using Agent SDK

Mining is a node-level operation driven through the blockchain RPC; the agent SDK does not expose a dedicated mining helper. Agents that need to drive mining programmatically shell out to the real `aitbc` CLI, or post directly to the RPC endpoint the CLI uses (`/rpc/mining/start`, `/rpc/mining/stop`, `/rpc/mining/status`, `/rpc/mining/miners`).

### Example 1: Drive mining via subprocess

```python
import subprocess
import json

def start_mining(wallet: str, threads: int = 4, rpc: str = "http://localhost:8202") -> str:
    out = subprocess.run(
        ["aitbc", "mining", "start", wallet, "--threads", str(threads), "--rpc-url", rpc],
        capture_output=True, text=True, check=True,
    )
    return out.stdout

def mining_status(rpc: str = "http://localhost:8202") -> dict:
    out = subprocess.run(
        ["aitbc", "mining", "status", "--rpc-url", rpc],
        capture_output=True, text=True, check=True,
    )
    # status prints JSON after a "Mining status:" line
    return json.loads(out.stdout.split("\n", 1)[-1])

print(start_mining("miner-wallet", threads=4))
print(mining_status())
```

### Example 2: Post directly to the blockchain RPC

```python
import requests

rpc = "http://localhost:8202"
wallet_address = "0x1a2b3c4d5e6f..."

r = requests.post(f"{rpc}/rpc/mining/start",
                  json={"miner_address": wallet_address, "threads": 4, "enabled": True},
                  timeout=30)
print(r.json())

status = requests.get(f"{rpc}/rpc/mining/status", timeout=30).json()
print(status)
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Start mining into a named keystore wallet with a configurable thread count
- Read mining status and list active miners on the node
- Cleanly stop mining
- Drive the same RPC endpoints programmatically from an agent

---

## Validation

```bash
# Wallet exists in the keystore
ls ~/.aitbc/wallets/miner-wallet.json

# Mining is running
aitbc mining status

# At least one miner appears
aitbc mining list

# Stop and confirm
aitbc mining stop && aitbc mining status
```

---

## Related Resources

- [Mining CLI source](../../cli/aitbc_cli/commands/mining.py)
- [Wallet Basics](./01_wallet_basics.md)
- Next: [Staking Basics](./14_staking_basics.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
