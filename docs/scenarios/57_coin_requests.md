# Coin Requests (Initial Grant Workflow)

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 15 minutes
**Last Updated**: 2026-09-16
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Coin Requests

---

## See Also

- **Previous Scenario**: [Energy Pricing & Provider Registry](./56_energy_pricing.md)
- **Next Scenario**: [Economics & OpenClaw DAO](./58_economics_dao.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/coin_requests.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc coin-requests` is **live** — requests are
> stored by the agent/coordinator service and `execute` submits a real signed
> chain transaction. `reconcile` checks executed requests against the chain.

This scenario covers the initial-coin-grant workflow: a fresh node requests a
one-time coin grant, and an operator reviews, approves, executes, and
reconciles it.

### Use Case

A newly-joined node has no AIT to pay fees. It files a coin request; the hub
operator approves and executes the grant.

### What You'll Learn

- How a node files a grant request (`request`)
- How an operator reviews the queue (`list`, `show`)
- How to approve/reject and execute a grant (`approve`, `reject`, `execute`)
- How to audit executed grants against the chain (`reconcile`, `reopen`)

---

## Prerequisites

- Requester side: a wallet to receive the coins (`--wallet`)
- Operator side: hub access — `list`/`approve`/`reject`/`execute` run against
  the agent API on the coordinator host

---

## Steps

### 1. File a request (requester node)

```bash
aitbc coin-requests request --wallet default --amount 100
```

`--sender` defaults to `<hostname>-<wallet-suffix>`; `--recipient` defaults to
`hub-coordinator`; `--request-id` defaults to a unique value.

### 2. Review the queue (operator)

```bash
aitbc coin-requests list                       # all requests
aitbc coin-requests list --status pending      # pending only
aitbc coin-requests show --request-id req-123  # one request's details
```

Verified live: the fleet queue currently shows a real pending
`req-node1-… 100 AIT` request.

### 3. Approve or reject

```bash
aitbc coin-requests approve --request-id req-123 --reason "new node bootstrap"
aitbc coin-requests reject  --request-id req-124 --reason "duplicate request"
```

`--reason` is required for `reject`, optional for `approve`.

### 4. Execute the grant

```bash
aitbc coin-requests execute --request-id req-123
```

Submits the signed transfer transaction on behalf of the hub wallet.

### 5. Reconcile against the chain

```bash
aitbc coin-requests reconcile             # report discrepancies
aitbc coin-requests reconcile --annotate  # + record them in each request's audit log
```

### 6. Reopen a stuck request

```bash
aitbc coin-requests reopen --request-id req-123            # clears tx hash for retry
aitbc coin-requests reopen --request-id req-123 --force    # even if the chain still has it
```

---

## Verification

- `list --status pending` empties after `execute`; `reconcile` reports no
  discrepancies once the transfer seals.

## Troubleshooting

- `reconcile` flags a request — use `reopen` to clear the recorded tx hash and
  `execute` again once the chain state is understood.
