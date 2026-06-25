# Staking Basics

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 25 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Staking Basics

---

## See Also

- **Previous Scenario**: [Mining Setup](./13_mining_setup.md)
- **Next Scenario**: [Blockchain Monitoring](./15_blockchain_monitoring.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Staking CLI source](../../cli/aitbc_cli/commands/wallet/staking.py)

---

## Scenario Overview

This scenario shows how an AI agent stakes and unstakes AITBC tokens to earn staking rewards and liquidity-pool yield. The staking commands live on the `aitbc wallet` group (registered directly in `cli/aitbc_cli/commands/wallet/staking.py` via `@wallet.command(...)`), so the real invocation paths are `aitbc wallet stake`, `aitbc wallet unstake`, `aitbc wallet staking-info`, `aitbc wallet liquidity-stake`, and `aitbc wallet liquidity-unstake` — not a `wallet staking` subgroup. On-chain staking posts to the blockchain RPC (`/rpc/staking/stake`, `/rpc/staking/unstake`); liquidity staking is recorded in the local wallet file with APY tiers.

### Use Case

An agent holding AITBC tokens wants to (1) lock some tokens on-chain for a fixed duration to earn validator rewards, (2) check its active stakes, (3) unstake when the lock expires, and (4) separately stake into a liquidity pool for a higher APY tier, then withdraw with accrued rewards.

### What You'll Learn

- Stake tokens on-chain with `aitbc wallet stake <amount> --duration <days>`
- View on-chain staking info with `aitbc wallet staking-info`
- Unstake by stake ID with `aitbc wallet unstake <stake_id>`
- Stake into a liquidity pool with `aitbc wallet liquidity-stake <amount> --pool <name> --lock-days <int>`
- Withdraw from a liquidity pool with `aitbc wallet liquidity-unstake <stake_id>`

---

## Prerequisites

### Knowledge Required

- Scenario 01 (Wallet Basics) — you need a funded wallet and to understand `--wallet-name` / `--wallet-path`
- The blockchain node must be reachable for on-chain staking (RPC default `http://localhost:8202`)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A funded wallet in the keystore

### Setup Required

- Create and fund a wallet (Scenario 01): `aitbc wallet create --name staker`
- Confirm a balance: `aitbc wallet --wallet-name staker balance`
- For encrypted wallets, export `AITBC_WALLET_PASSWORD` (or `AITBC_WALLET_PASSWORD_STAKER`) so non-interactive commands can decrypt

---

## Step-by-Step Workflow

All commands below are grounded in `cli/aitbc_cli/commands/wallet/staking.py`. The `wallet` group (`cli/aitbc_cli/commands/wallet/__init__.py`) accepts `--wallet-name` / `--wallet-path`; the active wallet resolves from CLI arg → `AITBC_DEFAULT_WALLET` env → `~/.aitbc/config.yaml` `active_wallet` → `default`.

### Step 1: Stake tokens on-chain

`aitbc wallet stake <amount>` posts `{address, amount (wei), lock_days, chain_id}` to `POST /rpc/staking/stake`. `amount` is a float in AITBC; `--duration` is the lock in days (default `30`).

```bash
aitbc wallet --wallet-name staker stake 100.0 --duration 90
```

**Expected output:**
```
Staked 100.0 AITBC for 90 days
wallet: staker
stake_id: 7
amount: 100.0
duration_days: 90
locked_until: 2026-09-23T12:00:00Z
remaining_balance: 400.0
chain_id: ait-hub.aitbc.bubuit.net
```

### Step 2: Check on-chain staking info

`aitbc wallet staking-info` calls `GET /rpc/staking/<hex_address>?chain_id=<id>` and prints total staked, active stake count, and the active stakes list.

```bash
aitbc wallet --wallet-name staker staking-info
```

**Expected output:**
```
wallet: staker
address: 0x1a2b3c4d...
chain_id: ait-hub.aitbc.bubuit.net
total_staked: 100
active_stake_count: 1
active_stakes:
  - stake_id: 7
    amount: 100
    locked_until: 2026-09-23T12:00:00Z
```

### Step 3: Unstake on-chain

`aitbc wallet unstake <stake_id>` posts `{address, stake_id, chain_id}` to `POST /rpc/staking/unstake`. The `stake_id` is the integer returned from `stake` / shown in `staking-info`.

```bash
aitbc wallet --wallet-name staker unstake 7
```

**Expected output:**
```
Unstaked tokens from stake 7
wallet: staker
stake_id: 7
amount: 100
new_balance: 500.0
status: unstaked
chain_id: ait-hub.aitbc.bubuit.net
```

### Step 4: Stake into a liquidity pool

`aitbc wallet liquidity-stake <amount>` records a liquidity stake in the local wallet file. Options: `--pool` (default `main`), `--lock-days` (default `0`). APY tiers (from source): `>=90` days → 12% platinum, `>=30` → 8% gold, `>=7` → 5% silver, else 3% bronze. The wallet must have sufficient `balance`.

```bash
aitbc wallet --wallet-name staker liquidity-stake 50.0 --pool main --lock-days 90
```

**Expected output:**
```
Staked 50.0 AITBC into 'main' pool (platinum tier, 12.0% APY)
stake_id: liq_a1b2c3d4e5f6
pool: main
amount: 50.0
apy: 12.0
tier: platinum
lock_days: 90
new_balance: 350.0
```

### Step 5: Withdraw from a liquidity pool

`aitbc wallet liquidity-unstake <stake_id>` finds the active liquidity record, enforces the lock period, computes rewards as `principal * (apy/100) * (days_staked/365)`, marks the record completed, and credits `principal + rewards` to the wallet balance.

```bash
aitbc wallet --wallet-name staker liquidity-unstake liq_a1b2c3d4e5f6
```

**Expected output:**
```
Withdrawn 51.500000 AITBC (principal: 50.0, rewards: 1.500000)
stake_id: liq_a1b2c3d4e5f6
pool: main
principal: 50.0
rewards: 1.5
total_returned: 51.5
days_staked: 91.25
apy: 12.0
new_balance: 401.5
```

If the lock hasn't expired you'll see `Stake is locked until <unlock_date>` and the command exits non-zero.

---

## Code Examples Using Agent SDK

The `aitbc_agent` SDK exposes staking through `Agent.add_stake(amount, validator_id=None) -> str` (delegating to `ExtendedOperations`), which wraps the CLI staking path. For the full on-chain and liquidity flows, agents shell out to the real `aitbc wallet ...` commands shown above.

### Example 1: Add stake via the SDK

```python
from aitbc_agent import Agent

agent = Agent.create(name="staker-agent", agent_type="processing",
                     capabilities={"compute_type": "processing"})

# Delegate stake to a validator (validator_id optional)
stake_ref = agent.add_stake(amount=100.0, validator_id="validator_01")
print(stake_ref)
```

### Example 2: Drive the full CLI flow from an agent

```python
import subprocess

def run(*args: str) -> str:
    return subprocess.run(["aitbc", "wallet", "--wallet-name", "staker", *args],
                          capture_output=True, text=True, check=True).stdout

print(run("stake", "100.0", "--duration", "90"))
print(run("staking-info"))
print(run("unstake", "7"))
print(run("liquidity-stake", "50.0", "--pool", "main", "--lock-days", "90"))
print(run("liquidity-unstake", "liq_a1b2c3d4e5f6"))
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Stake AITBC on-chain for a chosen lock duration and receive a stake ID
- Inspect active on-chain stakes for your wallet
- Unstake by stake ID once the lock period allows
- Stake into a liquidity pool with APY-tiered lock periods
- Withdraw liquidity stakes with accrued rewards

---

## Validation

```bash
# On-chain stakes
aitbc wallet --wallet-name staker staking-info

# Wallet balance reflects stake/unstake activity
aitbc wallet --wallet-name staker balance

# Liquidity records are stored in the wallet file
python -c "import json,pathlib; d=json.load(pathlib.Path.home()/'.aitbc'/'wallets'/'staker.json'); print(len(d.get('liquidity',[])), 'liquidity records')"
```

---

## Related Resources

- [Staking CLI source](../../cli/aitbc_cli/commands/wallet/staking.py)
- [Wallet group registration](../../cli/aitbc_cli/commands/wallet/__init__.py)
- [Wallet Basics](./01_wallet_basics.md)
- Next: [Blockchain Monitoring](./15_blockchain_monitoring.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
