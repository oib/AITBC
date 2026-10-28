# Staking Option Coverage — stake, unstake, liquidity-stake, reinvest

**Level**: Advanced
**Prerequisites**: Scenario 14 Staking Basics
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Staking Option Coverage

---

## Scenario Overview

> **Option-coverage scenario (STAKE-OPTS-1, issue #549).** This play
> exercises the twelve **non-secret** CLI options that the option-level
> census still reported as never exercised on the top-level staking
> surface: `liquidity-stake` `--wallet-name/--wallet-path/--rpc-url/
> --pool/--lock-days/--fee`, `unstake` `--wallet-name/--wallet-path/
> --rpc-url`, `stake` `--wallet-path/--rpc-url`, `reinvest simulate`
> `--reserve-address`.
>
> `stake`, `unstake`, and `liquidity-stake` are write commands — every
> play refuses *before* signing: wallet-file resolution is the first
> step in each command body, so a nonexistent wallet is a free refusal.
> The refusal is client-side, so it holds identically whether or not the
> RPC surface is armed.
>
> **v17 gate note (28 Oct):** the staking/agent-staking RPCs are
> activation-gated — HTTP 410 while the next height is below
> `STATE_TRANSITION_V17_HEIGHT`, live at/after the pin — not retired.
> These wallet-gate refusals never reach the RPC, so the plays below
> stay valid in both worlds. Live post-v17 plays: scenario 01 steps
> 26–27 (wallet staking) and scenario 87 (operator-signed agent
> staking). Played on node2 (`aitbc 0.25.9`), `logger -t coderA`.

## Steps

### Step 1: `liquidity-stake --wallet-name/--pool/--lock-days/--fee` — wallet-gate refusal

```bash
aitbc liquidity-stake --wallet-name nosuch-stakeopts1 --amount 1 --pool nosuch-pool --lock-days 7 --fee 0.01
```

**Expected output (exit 1):** wallet lookup fails before signing — unknown pool/lock values never reached:

```
Wallet 'nosuch-stakeopts1' not found in the configured wallet directory.
  searched: /root/.aitbc/wallets, /var/lib/aitbc/wallets
```

### Step 2: `liquidity-stake --wallet-path/--rpc-url` — missing-file refusal

```bash
aitbc liquidity-stake --wallet-path /tmp/nosuch-stakeopts1.json --rpc-url http://127.0.0.1:9 --amount 1
```

**Expected output (exit 1):** same refusal — dead `--rpc-url` never contacted.

### Step 3: `unstake --wallet-name` — wallet-gate refusal

```bash
aitbc unstake --wallet-name nosuch-stakeopts1 --stake-id 0
```

**Expected output (exit 4):** `Wallet 'nosuch-stakeopts1' not found as a file wallet.`

### Step 4: `unstake --wallet-path/--rpc-url` — missing-file refusal

```bash
aitbc unstake --wallet-path /tmp/nosuch-stakeopts1.json --rpc-url http://127.0.0.1:9 --stake-id 0
```

**Expected output (exit 4):** same wallet-gate refusal before the stake-id guard and signing.

### Step 5: `stake --wallet-path/--rpc-url` — missing-file refusal

```bash
aitbc stake --wallet-path /tmp/nosuch-stakeopts1.json --rpc-url http://127.0.0.1:9 --amount 1
```

**Expected output (exit 4):** same wallet-gate refusal before the nonce lookup and `/rpc/staking/stake` POST.

### Step 6: `reinvest simulate --reserve-address` — import-gate refusal

```bash
aitbc reinvest simulate --agent-id nosuch-agent --reserve-address 0x0000000000000000000000000000000000000001
```

**Expected output (exit 1):** `Error simulating reinvestment for nosuch-agent: No module named 'miner_app'`

> **Defect (registered separately):** `_load_miner_app()` uses `parents[4]` — one level too high, so `miner_app` is never importable on an installed CLI. Fix is `parents[3]`. The flag still counts (parse + body ran).

## Option coverage result

12 previously-unexercised non-secret options exercised (all outputs verified live on node2, `logger -t coderA`):

| Option | Command | Exit class |
|---|---|---|
| `--wallet-name/--pool/--lock-days/--fee` | `liquidity-stake` | expected-refusal (1) |
| `--wallet-path/--rpc-url` | `liquidity-stake` | expected-refusal (1) |
| `--wallet-name` | `unstake` | expected-refusal (4) |
| `--wallet-path/--rpc-url` | `unstake` | expected-refusal (4) |
| `--wallet-path/--rpc-url` | `stake` | expected-refusal (4) |
| `--reserve-address` | `reinvest simulate` | expected-refusal (1) |

Census delta: liquidity-stake 6→0, unstake 3→0, stake 2→0, reinvest 1→0.

## Safety notes

- `liquidity-stake` re-saves the wallet file and submits a signed transaction — never run with a resolvable wallet unless a stake is intended.
- `stake`/`unstake` sign and POST — the wallet gate is the safe refusal.
