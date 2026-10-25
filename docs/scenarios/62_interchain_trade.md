# Inter-Chain Trading

**Level**: Intermediate
**Prerequisites**: Scenario 06 Basic Trading, Scenario 20 Cross-Chain Transfer
**Estimated Time**: 25 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Inter-Chain Trading

---

## See Also

- **Previous Scenario**: [Node Mesh Management](./61_node_mesh_management.md)
- **Next Scenario**: [CLI Configuration](./63_cli_configuration.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/trade.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc trade` talks to the **trading service**
> (`/v1/trading/*`). There is no simulated fallback — when the service is
> not running, commands end in a `Network error`. Trade creation, escrow,
> and settlement move real value between chains.

This scenario covers the full `aitbc trade` surface: chain registry,
offer discovery/search/watch, trade creation and matching, and the
escrowed settlement path (`lock-escrow` → `settle` / `refund`).

### Use Case

A trader (or trading agent) discovers offers on a destination chain, opens
an inter-chain trade, locks the escrow, and settles it with the released
secret — or refunds it when the counterparty stalls.

### What You'll Learn

- Which chains the trading service knows (`chains`, `register-chain`, `health`)
- Offer discovery (`discover`, `search`, `sync`, `sync-status`, `watch`, `subscription-status`)
- Trade lifecycle (`create`, `list`, `get`, `status`, `history`, `match`, `match-all`)
- Escrowed settlement (`lock-escrow`, `settlement-status`, `settle`, `refund`)

---

## Prerequisites

- Trading service reachable (the CLI reports `Network error` otherwise)
- For writes: sender/recipient addresses on both chains and funds on the
  source chain (integer units; `UNITS_PER_AIT = 36_000_000`)

---

## Steps

### 1. Chain registry (read-only)

```bash
aitbc trade chains
aitbc trade health --chain-id ait-mainnet
aitbc trade settlement-status --trade-id <trade-id>
```

`aitbc trade register-chain --chain-id <id> --endpoint <url>` adds a chain
to the trading service — a registry write; not played without the
operator's line.

### 2. Offer discovery (read-only)

```bash
aitbc trade sync-status
aitbc trade subscription-status
aitbc trade discover --source-chain ait-mainnet --dest-chain ait-side --service-type gpu \
    --min-price 0 --max-price 100 --limit 20
aitbc trade search --query gpu --chain-id ait-mainnet --limit 20
```

`aitbc trade sync` forces the offer index to refresh — a service-side write;

```bash
aitbc trade sync --chain-id ait-mainnet --service-type gpu        # operator line
aitbc trade sync --force
```

`aitbc trade watch --chain-id ait-mainnet --service-type gpu` opens a
long-lived subscription stream of matching offers — safe to run but blocks
until interrupted.

### 3. Trade lifecycle

```bash
aitbc trade list
aitbc trade list --status pending --source-chain ait-mainnet
aitbc trade get    <trade-id>
aitbc trade status --trade-id <trade-id>
aitbc trade history --source-chain ait-mainnet --limit 20
```

**Writes — need the operator's line on a live island:**

```bash
aitbc trade create --source-chain ait-mainnet --dest-chain ait-side \
    --sender 0x<src> --recipient 0x<dst> --amount 36000000 \
    --offer-id <offer-id> --price 1.0 --quantity 1
aitbc trade match     <trade-id>
aitbc trade match-all
```

`--amount` and `--quantity` are integers; `--price` is the agreed price
ratio. `create` opens a real inter-chain trade.

### 4. Escrowed settlement

```bash
aitbc trade lock-escrow      --trade-id <trade-id> --node-url http://localhost:8202
aitbc trade settlement-status --trade-id <trade-id>
aitbc trade settle           --trade-id <trade-id> --secret <secret>
aitbc trade refund           --trade-id <trade-id>
```

All four commit on-chain state via the node RPC (`--node-url`,
`--api-key`/`--timeout` available): `lock-escrow` escrows the payment,
`settle` releases it with the hashlock secret, `refund` reclaims an expired
trade. Not played without the operator's line; `settlement-status` is the
read-only check to run between them.

---

## Cost Table

| Step | Spend |
|---|---|
| Read-only registry/discovery/status steps | 0 AIT |
| `trade create` / `lock-escrow` / `settle` / `refund` | `--amount` escrowed + chain fee — not played |

---

## Verification

- `aitbc trade get <id>` moves through `pending → matched →
  locked → settled` (or `refunded`).
- `aitbc trade history` lists the trade with its final state.

## Troubleshooting

- `Network error` on every step — the trading service is down; `aitbc
  trade` has no simulated fallback.
- `discover` returns nothing — run `trade sync-status` to check the offer
  index freshness.
