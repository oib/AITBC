# Wallet CLI Options

**Level**: Intermediate
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Wallet CLI Options

---

## Scenario Overview

> **Option-coverage scenario (WALLET-OPTS-1).** This play walks the 29
> previously unexercised non-secret `aitbc wallet` options — the bridge
> sell/settlements/float reads, the ETH-balance and ETH-send lane, the
> liquidity family, `send`, `inspect`, `staking-info`, `transactions`,
> and `address --name`.
>
> Played on node0 against the live hub bridge mount at
> `https://hub.aitbc.bubuit.net`. Every command that would sign a
> transaction, move funds, or write a wallet file on success runs under
> `aitbc wallet --wallet-name nosuch-walletopts1` (a wallet that does not
> exist), a dead endpoint (`http://127.0.0.1:9`), or a guard argument
> (`--amount-eth 0`), so the play stops at a **free refusal** — the
> wallet-file check aborts before any key is loaded, signed, or
> submitted. Read-only flags are played live. Nothing is signed, nothing
> is spent, no wallet file, key, address record, or chain write is
> created.
>
> One drift is recorded for separate registration:
> `wallet bridge status --ait-tx-hash` **ignores `--hub-url`** — it
> always queries the configured wallet daemon
> (`get_wallet_client()`, `cli/aitbc_cli/commands/wallet/bridge.py`)
> instead of the `_hub_bridge_client(hub_url)` used by every sibling
> route, so on a customer node the flag is accepted but silently routed
> to localhost.

### What You'll Learn

- Which `aitbc wallet bridge` reads are public on the hub (float,
  settlements, status windows) and which path needs a wallet (sell
  quote/lock)
- How the shared wallet gate (`wallet_path.exists()` in
  `_resolve_wallet` / the staking commands) refuses an unknown
  `--wallet-name` before any signing or network write
- How `eth-send` orders its guards: `--amount-eth` positivity before
  the wallet file read, the wallet file read before any RPC contact
- The `--hub-url` drift on `bridge status --ait-tx-hash`

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- For the live reads: the hub bridge mount reachable at
  `https://hub.aitbc.bubuit.net`
- No wallet named `nosuch-walletopts1` (the refusing argument)

---

## Steps

### Step 1: Wallet address lookup (free refusal)

`address --name` resolves the named wallet file; a nonexistent name
aborts at the search report — nothing is created:

```bash
aitbc wallet address --name nosuch-walletopts1
```

**Expected output (exit 4):**

```
Wallet 'nosuch-walletopts1' not found as a file wallet.
  searched: /root/.aitbc/wallets, /var/lib/aitbc/wallets
  pass --wallet-path <file> to point at it directly
```

### Step 2: Bridge float and settlements (live reads)

`float` reads the bridge payout account float and the day-cap window —
public through the hub's nginx bridge mount:

```bash
aitbc wallet bridge float --hub-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 0):** JSON with `eth_address`, `balance_eth`,
`available_eth`, `windows.today`/`last_24h` (each carrying
`withdrawals_eth`, `sell_eth`, `exchange_eth`, `total_eth`) and
`sell_daily_cap` (`max_eth_per_day 0.03`, `committed_24h`,
`remaining`).

`settlements` lists trade/order-refund settlement rows; `--state` and
`--kind` are server-side filters:

```bash
aitbc wallet bridge settlements --state needs_review --kind trade --hub-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 0):**

```
{
  "settlements": [],
  "count": 0,
  "limit": 50,
  "offset": 0
}
```

A dead endpoint exercises `--hub-url`'s error path — the flag is
accepted, the GET fails on connect:

```bash
aitbc wallet bridge settlements --hub-url http://127.0.0.1:9
```

**Expected output (exit 1):**
`Failed to list settlements: GET request failed: ... Connection refused`

### Step 3: Bridge status windows and the tx-hash drift

`status` needs exactly one selector. The two windowed modes honor
`--hub-url`:

```bash
aitbc wallet bridge status --today --hub-url https://hub.aitbc.bubuit.net
aitbc wallet bridge status --24h
```

**Expected output (exit 0, each):** JSON with `window`
(`today (since 00:00 host-local)` / `last 24h (rolling)`), `timezone`,
`since`, the four `*_eth` counters, and `sell_daily_cap`. The `--24h`
run uses the configured wallet daemon (default hub URL).

```bash
aitbc wallet bridge status --hub-url http://127.0.0.1:9
```

**Expected output (exit 1):**
`status needs exactly one of --ait-tx-hash, --today, --24h` — the
selector guard fires before any HTTP.

**Drift.** The `--ait-tx-hash` selector ignores `--hub-url`: it queries
the configured wallet daemon (`http://localhost:8108` on node0) no
matter what was passed:

```bash
aitbc wallet bridge status --ait-tx-hash 0x0000000000000000000000000000000000000000000000000000000000000000 --hub-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 1):**

```
Failed to get withdrawal status: GET request failed: 404 Client Error: Not Found for url: http://localhost:8108/v1/bridge/withdraw/0x000...
```

The URL in the error proves the flag was dropped — the request went to
`localhost:8108`, not the passed hub origin. Registered as a drift row.

### Step 4: Bridge sell quote/lock (wallet-gate refusals)

Both sell commands resolve the wallet file first
(`_resolve_wallet`), so a nonexistent `--wallet-name` aborts before the
quote POST or the lock signature — nothing reaches the hub:

```bash
aitbc wallet bridge sell quote --amount 1 --eth-address 0x0000000000000000000000000000000000000001 --wallet-name nosuch-walletopts1 --hub-url https://hub.aitbc.bubuit.net
aitbc wallet bridge sell lock --quote-id nosuch-quote --wallet-name nosuch-walletopts1 --hub-url http://127.0.0.1:9
```

**Expected output (exit 1, each):**

```
Wallet 'nosuch-walletopts1' not found as a file wallet.
  searched: /root/.aitbc/wallets, /var/lib/aitbc/wallets
  pass --wallet-path <file> to point at it directly
```

### Step 5: ETH balance and send lane

`eth-balance` takes either `--address` or `--wallet`; with a dead
`--eth-rpc-url` both flags are exercised on the connect error:

```bash
aitbc wallet eth-balance --address 0x0000000000000000000000000000000000000001 --eth-rpc-url http://127.0.0.1:9
```

**Expected output (exit 2):**
`EVM RPC eth_chainId failed at http://127.0.0.1:9: [Errno 111] Connection refused`

`eth-send` guards `--amount-eth` positivity **before** touching the
wallet file — a zero amount refuses even though the wallet name is also
bogus:

```bash
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet eth-send --to 0x0000000000000000000000000000000000000001 --amount-eth 0 --chain-id 11155111 --eth-rpc-url http://127.0.0.1:9 --max-gas-gwei 1 --allow-contract --confirm --wait
```

**Expected output (exit 4):** `--amount-eth must be positive`

With a positive amount the wallet gate fires next — still before any
RPC call or signing:

```bash
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet eth-send --to 0x0000000000000000000000000000000000000001 --amount-eth 0.0001 --chain-id 11155111 --eth-rpc-url http://127.0.0.1:9 --max-gas-gwei 1 --confirm
```

**Expected output (exit 4):**
`cannot read wallet file /root/.aitbc/wallets/nosuch-walletopts1.json: [Errno 2] No such file or directory`

### Step 6: Inspect, liquidity family, send, staking-info, transactions

`inspect --field` reads a wallet file directly; a missing path is a
clean refusal:

```bash
aitbc wallet inspect --path /tmp/nosuch-walletopts1.json --field balance
```

**Expected output (exit 1):**
`Wallet file not found: /tmp/nosuch-walletopts1.json`

All three liquidity commands hit the shared wallet gate first — the
nonexistent wallet selected via `AITBC_DEFAULT_WALLET` aborts before stake-id lookup,
signing, or submission (no stake row or chain write is possible):

```bash
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet liquidity-claim --stake-id nosuch --fee 0
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet liquidity-stake --amount 0 --lock-days 1 --fee 0
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet liquidity-unstake --stake-id nosuch --fee 0
```

**Expected output (exit 1, each):**
`Wallet 'nosuch-walletopts1' not found ...` (`liquidity-claim` prints
`not found as a file wallet.`; the stake/unstake pair prints
`not found in the configured wallet directory.` — a message-variant
note, both exit 1 before signing).

`send` is the same wallet gate — `--fee`, `--wait`, and `--rpc-url` are
parsed, the wallet resolution aborts before the transaction is built:

```bash
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet send --to-address 0x0000000000000000000000000000000000000001 --amount 0 --fee 0 --wait --rpc-url http://127.0.0.1:9
```

**Expected output (exit 4):**
`Wallet 'nosuch-walletopts1' not found as a file wallet.`

`staking-info --address` is a free read — an address with no stake
returns the zeroed shape:

```bash
AITBC_DEFAULT_WALLET=nosuch-walletopts1 aitbc wallet staking-info --address 0x0000000000000000000000000000000000000001
```

**Expected output (exit 0):**

```
{
  "wallet": "(by address)",
  "address": "0x0000000000000000000000000000000000000001",
  "chain_id": "bc-2",
  "total_staked": "0",
  "active_stake_count": 0,
  "active_stakes": []
}
```

`transactions --limit` is a read of the active wallet's ledger:

```bash
aitbc wallet transactions --limit 5
```

**Expected output (exit 0):** a `Transactions: default` table — JSON
with `wallet`, `address`, `count`, and up to `limit` rows (`tx_id`,
`tx_hash`, `sender`, `recipient`, `value`, `fee`, `status`,
`timestamp`).

---

## Option coverage result

29 previously-unexercised non-secret options exercised across the
`wallet` census group (all outputs verified live on node0,
`logger -t coderA`):

| Option | Command | Play | Exit class |
|---|---|---|---|
| `--name` | `wallet address` | wallet-gate refusal | expected-refusal (4) |
| `--hub-url` | `wallet bridge float` | live hub read | ok (0) |
| `--hub-url` | `wallet bridge sell lock` | wallet gate before connect | expected-refusal (1) |
| `--wallet-name` | `wallet bridge sell quote` | wallet gate before POST | expected-refusal (1) |
| `--hub-url` | `wallet bridge sell quote` | wallet gate before POST | expected-refusal (1) |
| `--state` | `wallet bridge settlements` | live hub read | ok (0) |
| `--kind` | `wallet bridge settlements` | live hub read | ok (0) |
| `--hub-url` | `wallet bridge settlements` | live + conn-refused | ok (0) / expected-refusal (1) |
| `--ait-tx-hash` | `wallet bridge status` | daemon 404; `--hub-url` dropped | drift (1) |
| `--today` | `wallet bridge status` | live hub read | ok (0) |
| `--24h` | `wallet bridge status` | live daemon read | ok (0) |
| `--hub-url` | `wallet bridge status` | accepted, ignored on tx-hash path | drift (1) |
| `--address` | `wallet eth-balance` | conn-refused | expected-refusal (2) |
| `--eth-rpc-url` | `wallet eth-balance` | conn-refused | expected-refusal (2) |
| `--eth-rpc-url` | `wallet eth-send` | amount guard / wallet gate | expected-refusal (4) |
| `--max-gas-gwei` | `wallet eth-send` | amount guard / wallet gate | expected-refusal (4) |
| `--allow-contract` | `wallet eth-send` | amount guard | expected-refusal (4) |
| `--confirm` | `wallet eth-send` | amount guard / wallet gate | expected-refusal (4) |
| `--wait` | `wallet eth-send` | amount guard | expected-refusal (4) |
| `--field` | `wallet inspect` | file-not-found | expected-refusal (1) |
| `--fee` | `wallet liquidity-claim` | wallet gate before signing | expected-refusal (1) |
| `--lock-days` | `wallet liquidity-stake` | wallet gate before signing | expected-refusal (1) |
| `--fee` | `wallet liquidity-stake` | wallet gate before signing | expected-refusal (1) |
| `--fee` | `wallet liquidity-unstake` | wallet gate before signing | expected-refusal (1) |
| `--fee` | `wallet send` | wallet gate before signing | expected-refusal (4) |
| `--wait` | `wallet send` | wallet gate before signing | expected-refusal (4) |
| `--rpc-url` | `wallet send` | wallet gate before signing | expected-refusal (4) |
| `--address` | `wallet staking-info` | live read (zeroed shape) | ok (0) |
| `--limit` | `wallet transactions` | live read | ok (0) |

**Drift registered for a separate row:** `wallet bridge status
--ait-tx-hash` drops `--hub-url` (routes to the configured daemon
instead of `_hub_bridge_client(hub_url)`; `bridge.py` `status()`).
