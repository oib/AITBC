# Dispute Lifecycle

**Level**: Intermediate
**Prerequisites**: Scenario 08 Market Bidding (an on-chain agreement to dispute)
**Estimated Time**: 25 minutes
**Last Updated**: 2026-09-16
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Dispute Lifecycle

---

## See Also

- **Previous Scenario**: [Paid Agent-to-Agent Delegation](./54_agent_paid_delegation.md)
- **Next Scenario**: [Energy Pricing & Provider Registry](./56_energy_pricing.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/dispute.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc dispute` is **live** — it reads and writes
> dispute state through the blockchain node RPC (`--node-url`, defaults to the
> configured node). `dispute resolve` additionally calls the coordinator to
> settle the disputed escrow.

This scenario walks the full dispute lifecycle: a customer files a dispute
against a market agreement, attaches evidence, arbitrators vote, and an
operator rules on the escrowed payment.

### Use Case

A paid job never returned a result (or the result failed a spot check). The
customer opens a dispute instead of accepting the escrow release.

### What You'll Learn

- How to file a dispute against an agreement (`dispute file`)
- How to inspect open disputes (`active`, `get`, `user`)
- How evidence is attached and verified (`evidence add|list|verify`)
- How arbitration votes are cast (`vote`, `votes`)
- How an operator resolves the escrow (`resolve`)

---

## Prerequisites

- A node wallet (Scenario 01) for signing the dispute transaction
- An existing agreement ID — create one via Scenario 08 (market order) or
  Scenario 06 (escrowed trade)
- Arbitrator/operator credentials are required for `vote`, `evidence verify`,
  and `resolve` — filing and reading disputes need none.

---

## Steps

### 1. File a dispute

```bash
aitbc dispute file \
  --agreement-id 12 \
  --respondent 0xab0797Ae... \
  --dispute-type non_delivery \
  --reason "job never returned a result" \
  --evidence-hash 0x9f2c...
```

All five options are required. `--evidence-hash` is the hash of the supporting
evidence bundle (e.g. the coordinator job log).

### 2. Confirm it is open

```bash
aitbc dispute active              # table of open disputes
aitbc dispute get 42              # one dispute with evidence and votes
aitbc dispute user 0xYourAddress  # disputes an address is party to
```

`active` answered `{"success": true, "disputes": [], "count": 0}` live on the
fleet — an empty list is the honest "no open disputes" response.

### 3. Attach evidence

```bash
aitbc dispute evidence add --dispute-id 42 --evidence-hash 0x9f2c... \
  --evidence-type transcript --description "coordinator job log"
aitbc dispute evidence list 42
```

### 4. Arbitration vote (arbitrators only)

```bash
aitbc dispute vote --dispute-id 42 --vote plaintiff \
  --reasoning "no result delivered within the SLA window"
aitbc dispute votes 42
```

### 5. Resolve the escrow (operator)

```bash
aitbc dispute resolve job-7f31 --outcome refund \
  --reason "spot-check mismatch" --yes
```

`--outcome refund` returns the escrowed payment to the buyer;
`--outcome release` pays the provider. The ruling is recorded on the
settlement.

---


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

### 6. List arbitrators

Lists addresses authorized to arbitrate disputes.

```bash
aitbc dispute arbitrator list
```

### 7. Show an arbitrator's queue

Lists disputes assigned to an arbitrator.

```bash
aitbc dispute arbitrator queue 0xArbitrator
```

### 8. Authorize an arbitrator

`aitbc dispute arbitrator authorize 0xArbitrator` is grants arbitration rights — an operator/signature-gated action; not played, needs the operator's line.

### 9. Verify dispute evidence

`aitbc dispute evidence verify --dispute-id 42 --evidence-id 1` is rules on evidence validity — arbitrator credentials required; not played, needs the operator's line.

### 10. Auto-adjudicate open disputes

`aitbc dispute auto-adjudicate --yes` is executes rulings on open disputes — irreversible, operator action; not played, needs the operator's line.

---

## Verification

- `dispute get <id>` shows status transitions (open → voting → resolved).
- The resolved escrow appears in `aitbc market escrow status` output.

## Troubleshooting

- `Missing option '--agreement-id'` — all five `file` options are required.
- `vote`/`resolve` rejected — those paths require arbitrator/operator
  credentials; check `aitbc auth status` and the node's operator wallet.
