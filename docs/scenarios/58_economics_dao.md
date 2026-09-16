# Economics & OpenClaw DAO Parameter Proposals

**Level**: Intermediate
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 15 minutes
**Last Updated**: 2026-09-16
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Economics & OpenClaw DAO

---

## See Also

- **Previous Scenario**: [Coin Requests](./57_coin_requests.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/economics.py`

---

## Scenario Overview

> **Live vs. simulated:** `propose`, `vote`, and `status` are **live** — they
> hit the coordinator's `/v1/economic-proposals` API and require stored
> credentials (`aitbc auth login`) or an API key; unauthenticated calls 401.
> `market`, `model`, and `distributed` are **simulated** analyses — the CLI
> labels them `status: simulated` and they change nothing.

This scenario covers reading and steering economic parameters through the
OpenClaw DAO proposal flow.

### Use Case

The operator wants to lower `tx_fee` from `0.001` to `0.0005` AIT; the change
goes through a DAO parameter proposal and a vote.

### What You'll Learn

- How to submit an economic-parameter proposal (`propose`)
- How to vote on a proposal (`vote`)
- How to check proposal status (`status`)
- Which economics commands are simulated analyses (`market`, `model`,
  `distributed`)

---

## Prerequisites

- Stored credentials (`aitbc auth login`) or a coordinator API key for
  `propose`/`vote`/`status` — the endpoint is auth-gated.

---

## Steps

### 1. Submit a proposal (auth required)

```bash
aitbc economics propose \
  --parameter tx_fee --current 0.001 --proposed 0.0005 \
  --unit AIT --proposer-id operator-1
```

Posts to the coordinator's `/v1/economic-proposals`; without credentials it
fails closed with `401 Unauthorized` (verified live).

### 2. Vote on the proposal

```bash
aitbc economics vote --proposal-id <id> --vote for
aitbc economics vote --proposal-id <id> --vote against --voting-power 2.0
```

`--vote` accepts `for`, `against`, or `abstain`; `--voting-power` is optional.

### 3. Check status

```bash
aitbc economics status --proposal-id <id>
```

### 4. Simulated analyses (no state change)

```bash
aitbc economics market            # market analysis — status: simulated
aitbc economics model             # run the configured economic model
aitbc economics distributed       # distributed cost optimization
```

These are computation previews, not live queries — they return
`status: simulated` and are safe to run anywhere.

---

## Verification

- `status --proposal-id` reflects the proposal and its vote tally.

## Troubleshooting

- `401 Unauthorized` on `propose`/`vote`/`status` — run `aitbc auth login` or
  pass a coordinator API key.
