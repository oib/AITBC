# AITBC System Flow: From CLI Prompt to On-Chain Settlement

> **Authoritative port configuration** is in [Service Ports Reference](../reference/SERVICE_PORTS.md). This document describes the current CLI-driven flow on the live hub/shop island, not the historical `aitbc-cli.sh` wrapper.

The canonical customer path on AITBC v0.10.18 is:

```text
aitbc wallet create → aitbc wallet fund → aitbc auth login
     → aitbc ai submit --wait
     → coordinator (8203) → blockchain (8202) → miner (8107)
     → GPU service (8101) → Ollama (11434)
     → result → coordinator → ESCROW_RELEASE on blockchain
     → aitbc ai results, aitbc wallet transactions
```

## Overview

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐
│ Customer │ → │  aitbc   │ → │ Coordinator  │ ↔ │ Blockchain   │ ← │  Shop    │ → │  Ollama  │
│  wallet  │   │   CLI    │   │   8203       │   │   8202       │   │  miner   │   │  11434   │
└──────────┘   └──────────┘   └──────────────┘   └──────────────┘   └──────────┘   └──────────┘
                                                                  ↑
                                                           GPU service 8101
                                                           marketplace 8102
                                                           pool-hub    8210
```

Public customer access to hub services is through nginx (`https://hub.aitbc.bubuit.net/...`) because the coordinator, exchange, and wallet daemon bind `127.0.0.1` by default.

## Step-by-step flow

### 1. Acquire AIT and authenticate

```bash
aitbc wallet create customer-wallet
aitbc wallet fund customer-wallet --amount-ait 10.0
aitbc auth login --wallet customer-wallet --private-key-file ~/.aitbc/wallets/customer-wallet.key
```

`aitbc auth login` performs a wallet-signed nonce challenge against `POST /v1/auth/nonce` and `POST /v1/login` on the coordinator, then stores the returned JWT in the CLI credential store (`~/.aitbc/credentials.json`).

### 2. Discover compute

```bash
aitbc market list --service-type ollama
aitbc gpu list-gpus
```

A shop publishes a GPU software offer with:

```bash
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
```

This writes a `GPU_MARKETPLACE` transaction and makes the offer discoverable from the hub.

### 3. Submit a paid job

```bash
aitbc ai submit --prompt "What is machine learning?" --model llama3.2:3b \
  --payment 1.0 --wallet customer-wallet --provider-address <provider> --wait
```

The CLI posts to `POST /v1/jobs` on the coordinator with the JWT from `aitbc auth login`. The coordinator creates an escrow contract and queues the job.

### 4. Match and execute

The coordinator assigns the job to a registered shop miner. The miner:

1. Polls `/v1/miners/poll` on the coordinator (port 8107, agent-coordinator).
2. Calls the local GPU service (port 8101) to select a device.
3. Runs inference against the local Ollama server (port 11434).
4. Returns the result and a receipt to the coordinator.

### 5. Escrow release and settlement

When the coordinator verifies the result, it calls the blockchain node's `POST /escrow/create` and then triggers `ESCROW_RELEASE`. The blockchain node submits a `ESCROW_RELEASE` transaction to `POST /transactions/marketplace` on the hub, signed by the configured settlement key (Phase 8 decouples this from the genesis key).

The provider receives compute-seconds (1 AIT = 3600 compute-seconds, minus the fee). A 1.0 AIT job currently pays ~0.975 AIT to the provider.

### 6. Inspect results

```bash
aitbc ai status <job_id>
aitbc ai results <job_id>
aitbc wallet transactions <provider-wallet>
aitbc explorer chain-head
```

## Components and ports

| Component | Port | CLI group | Responsibility |
|-----------|------|-----------|----------------|
| aitbc CLI | — | — | User interface and credential store |
| Blockchain node RPC | 8202 | `aitbc chain`, `aitbc explorer`, `aitbc transactions` | Blocks, accounts, transactions, `/escrow/*` |
| Coordinator API | 8203 | `aitbc ai`, `aitbc auth` | Job submission, JWT auth, result collection |
| Agent-coordinator | 8107 | `aitbc agent-comm` | Miner polling and assignment |
| Wallet daemon | 8108 | `aitbc wallet`, `aitbc account` | Wallet operations and balance |
| GPU service | 8101 | `aitbc gpu` | Local GPU discovery and resource management |
| Marketplace | 8102 | `aitbc market`, `aitbc marketplace` | `market` = GPU/software offers; `marketplace` = chain listings |
| Exchange | 8106 | `aitbc exchange-island` | Simple on-island exchange |
| Pool hub | 8210 | `aitbc pool-hub` | Miner capacity, SLA, billing |
| Ollama | 11434 | — | AI model inference |

## Notes

- The `X-Api-Key` / `--api-key` header is still accepted, but `aitbc auth login` is the preferred customer path.
- The old `aitbc-cli.sh` wrapper and Tendermint RPC port `26657` references in this directory are historical.
- See [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) for the current gap analysis and P0 wish list.

## Monitoring

- Coordinator logs: `journalctl -u aitbc-coordinator-api`
- Miner logs: `journalctl -u aitbc-miner`
- Blockchain logs: `journalctl -u aitbc-blockchain-node`
