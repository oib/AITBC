# DAO Grants

**Level**: Intermediate
**Prerequisites**: Scenario 17 Governance Voting, Scenario 72 Developer Registry
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > DAO Grants

---

## See Also

- **Previous Scenario**: [Coordinator Workflows](./66_coordinator_workflows.md)
- **Next Scenario**: [RPC Performance](./68_rpc_performance.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/grant.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc grant` calls the coordinator's
> `/v1/grants` endpoints — real records, no simulated fallback. `create`
> opens a real proposal, `vote` casts a recorded vote, `disburse` pays out
> funds.

This scenario covers the grant lifecycle: a registered developer files a
grant proposal, token holders vote, and an approved grant is disbursed per
milestone.

### Use Case

The DAO funds ecosystem work: a developer (scenario 72) requests funding,
the community votes `for`/`against`/`abstain`, and passed grants pay out
against milestones.

### What You'll Learn

- `grant create` — open a grant proposal
- `grant list` — review proposals with filters
- `grant vote` — cast a vote with voting power
- `grant disburse` — release funds to a milestone or in full

---

## Prerequisites

- Coordinator reachable; a registered developer id (scenario 72) for
  `create`
- Voting power on the voter address for `vote`

---

## Steps

### 1. Review existing grants (read-only)

```bash
aitbc grant list
aitbc grant list --status voting --limit 50
aitbc grant list --developer-id dev-1
aitbc grant list --status approved --format json
```

### 2. Create a proposal (write — operator line)

```bash
aitbc grant create --developer-id dev-1 --title 'AI SDK improvements' \
    --description 'Extend the SDK' --requested-amount 1000 --voting-days 14
```

`--requested-amount` is a decimal string; `voting_days` defaults to 7.
Creates a real proposal on the coordinator — not played without the
operator's line.

### 3. Vote (write — operator line)

```bash
aitbc grant vote --grant-id <grant-id> --vote for --voting-power 1.0
```

`--vote` is `for`/`against`/`abstain`; `--voting-power` records how much
power the vote carries. Votes are recorded server-side — not played on a
live proposal without the operator's line.

### 4. Disburse (write — operator line)

```bash
aitbc grant disburse --grant-id <grant-id>
aitbc grant disburse --grant-id <grant-id> --milestone-id ms-1 --amount 250
```

Releases grant funds — a real payout. Not played without the operator's
line and a passed proposal.

---

## Cost Table

| Step | Spend |
|---|---|
| `grant list` (all filters) | 0 AIT |
| `create`, `vote` | record writes — not played |
| `disburse` | `--amount` paid out — not played |

---

## Verification

- `grant list --status voting` shows the new proposal after `create`.
- After `disburse`, the grant's status/record reflects the payout.

## Troubleshooting

- `developer not found` — register the developer first (scenario 72).
- `Network error` — coordinator unreachable; no fallback.
