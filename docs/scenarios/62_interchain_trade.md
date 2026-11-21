# Inter-Chain Trading

**Level**: Intermediate
**Prerequisites**: Scenario 06 Basic Trading, Scenario 20 Cross-Chain Transfer
**Estimated Time**: 25 minutes
**Last Updated**: 2026-11-20
**Version**: 1.1

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
> not running, commands end in a `Network error`. Trade creation and
> matching are live; the HTLC escrowed-settlement rail is **retired**
> (#2385) — see Step 4.

This scenario covers the `aitbc trade` surface: chain registry, offer
discovery/search/watch, trade creation and matching, and the read-only
settlement status check. The escrowed settlement commands (`lock-escrow`,
`settle`, `refund`) are kept for interface compatibility but answer
"retired" — inter-chain HTLC settlement cannot seal at block version 9.

### Use Case

A trader (or trading agent) discovers offers on a destination chain and
opens an inter-chain trade. Settlement of that trade over the HTLC rail is
no longer possible; `settlement-status` remains the read-only view of any
legacy escrow records.

### What You'll Learn

- Which chains the trading service knows (`chains`, `register-chain`, `health`)
- Offer discovery (`discover`, `search`, `sync`, `sync-status`, `watch`, `subscription-status`)
- Trade lifecycle (`create`, `list`, `get`, `status`, `history`, `match`, `match-all`)
- Settlement status (`settlement-status`, read-only) and the retired
  settlement commands (`lock-escrow`, `settle`, `refund` — #2385)

---

## Prerequisites

- Trading service reachable (the CLI reports `Network error` otherwise)
- For writes: sender/recipient addresses on both chains
- A real second participant — self-trade is prohibited.

---

## Steps

### 1. Chain registry (read-only)

```bash
aitbc trade chains
aitbc trade health --chain-id bc-2
aitbc trade settlement-status --trade-id <trade-id>
```

`aitbc trade register-chain --chain-id <id> --endpoint <url>` adds a chain
to the trading service — a registry write; not played without the
operator's line.

### 2. Offer discovery (read-only)

```bash
aitbc trade sync-status
aitbc trade subscription-status
aitbc trade discover --source-chain bc-2 --dest-chain bc-2-island-1 --service-type gpu \
    --min-price 0 --max-price 100 --limit 20
aitbc trade search --query gpu --chain-id bc-2 --limit 20
```

`aitbc trade sync` forces the offer index to refresh — a service-side write;

```bash
aitbc trade sync --chain-id bc-2 --service-type gpu              # operator line
aitbc trade sync --force
```

`aitbc trade watch --chain-id bc-2 --service-type gpu` opens a
long-lived subscription stream of matching offers — safe to run but blocks
until interrupted.

### 3. Trade lifecycle

```bash
aitbc trade list
aitbc trade list --status pending --source-chain bc-2
aitbc trade get    <trade-id>
aitbc trade status --trade-id <trade-id>
aitbc trade history --source-chain bc-2 --limit 20
```

**Writes — need the operator's line on a live island:**

```bash
aitbc trade create --source-chain bc-2 --dest-chain bc-2-island-1 \
    --sender 0x<src> --recipient 0x<dst> --amount 36000000 \
    --offer-id <offer-id> --price 1.0 --quantity 1
aitbc trade match     <trade-id>
aitbc trade match-all
```

`--amount` and `--quantity` are integers; `--price` is the agreed price
ratio. `create` opens a real inter-chain trade.

### 4. Escrowed settlement — RETIRED (#2385)

The HTLC inter-chain settlement rail is **retired**: HTLC emissions
carry no `payload.auth` and cannot seal at block version 9, so no escrow
could ever lock, verify, settle, or refund. The node's
`/rpc/bridge/settlement/*` mutating endpoints and the trading service's
`lock-escrow`/`settle` routes answer **410 Gone**; the CLI surfaces the
retirement message. Only the read legs remain:

```bash
aitbc trade settlement-status --trade-id <trade-id>   # read-only, still works
```

The retired commands remain for interface compatibility and fail
honestly:

```bash
aitbc trade lock-escrow --trade-id <trade-id> --node-url http://localhost:8202   # → retired
aitbc trade settle      --trade-id <trade-id> --secret <secret>                  # → retired
aitbc trade refund      --trade-id <trade-id>                                    # → retired
```

`settlement-status` reports the trade's local `settlement_phase` plus the
live escrow status for any legacy escrow row. Escrow legs of this
scenario are descoped; do not attempt them on a live island.

---

## Cost Table

| Step | Spend |
|---|---|
| Read-only registry/discovery/status steps | 0 AIT |
| `trade create` / `match` / `match-all` | chain fee only — settlement itself is retired (#2385) |
| `lock-escrow` / `settle` / `refund` | 0 AIT — refused with 410 before any state changes |

---

## Verification

- `aitbc trade get <id>` moves through `pending → matched` (settlement
  legs `locked → settled`/`refunded` are unreachable — rail retired).
- `aitbc trade history` lists the trade with its final state.
- `aitbc trade lock-escrow --trade-id <id>` prints the retired message
  and exits non-zero; `settlement-status` still answers.

## Troubleshooting

- `Network error` on every step — the trading service is down; `aitbc
  trade` has no simulated fallback.
- `discover` returns nothing — run `trade sync-status` to check the offer
  index freshness.
- `lock-escrow`/`settle`/`refund` report "Settlement is retired" —
  expected since #2385; the HTLC rail cannot seal at block version 9.
