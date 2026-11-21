# Dispute Lifecycle

**Level**: Intermediate
**Prerequisites**: Scenario 08 Market Bidding (an on-chain agreement to dispute)
**Estimated Time**: 25 minutes
**Last Updated**: 2026-11-21
**Version**: 1.1

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
> configured node), persisted to `disputes.json` beside `chain.db` and shared
> across the node's RPC workers. Two different objects sit behind the group:
> the **chain arbitration store** (`/rpc/disputes/*` — file, evidence, votes,
> auto-resolve) and the **coordinator job-payment ruling** (`dispute resolve`,
> `auto-adjudicate` — a different object keyed by job).

This scenario walks the chain-side dispute lifecycle: a customer files a
dispute against an on-chain rental agreement, attaches evidence, authorized
arbitrators vote, and the dispute **auto-resolves once every authorized
arbitrator has voted** (plurality wins; a tie or an expired
`arbitration_deadline` escalates instead). `dispute resolve` is the separate
coordinator path that rules on disputed *job payments* — it does not touch
this store.

### Use Case

A paid job never returned a result (or the result failed a spot check). The
customer opens a dispute instead of accepting the escrow release.

### What You'll Learn

- How to file a dispute against an agreement (`dispute file`)
- How to inspect open disputes (`active`, `get`, `user`)
- How evidence is attached and verified (`evidence add|list|verify`)
- How arbitration votes are cast (`vote`, `votes`)
- How the dispute auto-resolves at arbitrator quorum (and escalates on tie/deadline)
- How an operator rules on a disputed job payment (`resolve` — coordinator path)

---

## Prerequisites

- A node wallet (Scenario 01) for signing the dispute transaction
- An existing **AIPowerRental agreement ID** — mint one on the Sepolia EVM
  rail with `aitbc market gpu agreement-create` (the id is the contract's
  `agreementCounter`, a uint256 — *not* a market-order or trade-agreement
  string id). When the node has `AITBC_DISPUTE_AGREEMENT_RPC_URL` /
  `AITBC_DISPUTE_AGREEMENT_CONTRACT` set, `dispute file` first validates the
  agreement on-chain: it must exist and the filer/respondent must be its
  provider/consumer pair.
- Arbitrator identities come from `AITBC_DISPUTE_ARBITRATORS`
  (`0xaddr:score` list) seeded at node start — the fleet runs three real
  arbitrator addresses; the historical `0x1111…` placeholders only appear
  when the env is unset. `aitbc dispute arbitrator authorize` (owner +
  signature) still works for runtime additions.
- `vote`/`evidence verify` require an authorized arbitrator identity;
  filing and reading need none. `resolve`/`auto-adjudicate` are
  coordinator admin calls — operator credentials, a different object.

---

## Steps

### 1. File a dispute

```bash
aitbc dispute file \
  --agreement-id 12 \
  --respondent 0xab0797Ae... \
  --dispute-type Performance \
  --reason "job never returned a result" \
  --evidence-hash 0x9f2c...
```

`--agreement-id` is the AIPowerRental `agreementCounter` id (see
Prerequisites) — the EVM gate rejects ids that don't exist or whose
provider/consumer pair doesn't match filer/respondent. All five options are
required. `--evidence-hash` is the hash of the supporting
evidence bundle (e.g. the coordinator job log). `--dispute-type` must be one of
the on-chain enum values — `Performance`, `Payment`, `ServiceQuality`,
`Availability`, `Other` (PascalCase; e.g. `non_delivery` is rejected).

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

Each authorized arbitrator votes once; a changed verdict may be re-cast
(latest vote counts), an identical re-cast is rejected as a duplicate.
Votes are refused after `arbitration_deadline` (~7 days from filing);
evidence closes after `evidence_deadline` (~3 days).

### 5. Resolution

**Chain side (automatic):** once every authorized arbitrator has voted,
the dispute resolves itself — plurality of latest-votes-per-arbitrator
decides `winner` (initiator or respondent) with a `resolution_reason`;
a tie escalates. Disputes past `arbitration_deadline` escalate on the next
state access. Resolved/escalated disputes reject further evidence and votes.

**Coordinator side (operator, different object):**

```bash
aitbc dispute resolve job-7f31 --outcome refund \
  --reason "spot-check mismatch" --yes
```

`--outcome refund` returns the escrowed payment to the buyer;
`--outcome release` pays the provider. This rules on a disputed *job
payment* in the coordinator — it is not the chain arbitration verdict.

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

`aitbc dispute arbitrator authorize 0xArbitrator` is grants arbitration rights — an operator/signature-gated action.

### 9. Verify dispute evidence

`aitbc dispute evidence verify --dispute-id 42 --evidence-id 1` is rules on evidence validity — arbitrator credentials required.

### 10. Auto-adjudicate open disputes

`aitbc dispute auto-adjudicate --yes` is executes rulings on open disputes — irreversible, operator action.

---

## Verification

- `dispute get <id>` shows status transitions (`filed` →
  `evidence_submitted` → `arbitration_in_progress` → `resolved` /
  `escalated`); `winner` and `resolution_reason` are populated on resolve.
- Chain resolution is **record-only** — it stores the verdict; no escrow
  or payment moves. Escrow settlement for the underlying job is a
  separate coordinator/market path.

## Troubleshooting

- `Missing option '--agreement-id'` — all five `file` options are required.
- `Agreement <id> not found or unverifiable` / `not a participant` — the
  EVM agreement gate rejected the id: mint a real agreement via
  `aitbc market gpu agreement-create` and file as its provider or consumer.
- `Dispute is closed` / `deadline has passed` — resolved, escalated, or
  deadline-expired disputes refuse further evidence and votes.
- `Dispute N not found` on a dispute you just filed — the node predates the
  shared-state store (#2387); upgrade/restart `aitbc-blockchain-rpc`.
- `vote` rejected with "Not an authorized arbitrator" — the address isn't in
  `AITBC_DISPUTE_ARBITRATORS` or the runtime registry; check
  `aitbc dispute arbitrator list`.
- `vote`/`resolve` rejected — those paths require arbitrator/operator
  credentials; check `aitbc auth status` and the node's operator wallet.
