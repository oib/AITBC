# Agent Staking Lifecycle — stake → add → unbond → complete

**Level**: Advanced (operator lane)
**Prerequisites**: v17 armed (`STATE_TRANSITION_V17_HEIGHT` set, head past the pin)
**Estimated Time**: 20 minutes + lock maturity
**Last Updated**: 2026-10-28
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Agent Staking Lifecycle

---

## Scenario Overview

Agent staking is **operator-signed** — no `aitbc` CLI surface exists.
The coordinator-api on hub signs server-side via
`AGENT_ECONOMICS_OPERATOR_*` and forwards the `payload.auth`-bearing
`STAKE_LOCK`/`STAKE_RELEASE` emissions. This play walks the full
position lifecycle:

- **stake** — create a position → `STAKE_LOCK` seals
- **add** — top up the position → `STAKE_LOCK` seals
- **unbond** — begin release → gated on the position's `locked_until`
- **complete** — settle the release → `STAKE_RELEASE` seals

**v17 gate:** the agent-staking endpoints answer **HTTP 410** while the
next height resolves below `STATE_TRANSITION_V17_HEIGHT`; live at/after
the pin. (The wallet-side `aitbc wallet stake`/`unstake` plays are
scenario 01 steps 26–27; wallet-gate option refusals are scenario 83.)

**Lock-maturity gate:** `unbond` and `complete` are refused while the
position's `locked_until` is in the future — the same ~24h wall-clock +
v4 height-window (`lock_height + lock_days*1440`) rule as wallet
staking. Deploy the position with `lock_days=1` (the minimum) if the
release half must complete within a day.

### Prerequisites

- coordinator-api on hub with `AGENT_ECONOMICS_OPERATOR_ADDRESS` +
  `AGENT_ECONOMICS_OPERATOR_KEY` configured
- a funded wallet to back the position
- head ≥ `STATE_TRANSITION_V17_HEIGHT`

---

## Steps — coordinator-api on hub

```bash
API=http://<hub-coordinator-api>   # coordinator-api on hub
```

### Step 1: Create a stake position → `STAKE_LOCK`

```bash
curl -s -X POST "$API/stake" -H 'content-type: application/json' -d '{
  "agent_wallet": "<agent address>",
  "amount": "<units>",
  "lock_days": 1
}'
```

Record `stake_id`. A `STAKE_LOCK` seals with the operator's
`payload.auth`; the position's `locked_until` starts now.

### Step 2: Add to the position → `STAKE_LOCK`

```bash
curl -s -X POST "$API/stake/<stake_id>/add" -H 'content-type: application/json' -d '{
  "amount": "<additional units>"
}'
```

A second `STAKE_LOCK` seals; `locked_until` may extend per the position
rules — re-read `GET /stake/<stake_id>` before proceeding.

### Step 3: Unbond — release-window gate

```bash
curl -s -X POST "$API/stake/<stake_id>/unbond" -H 'content-type: application/json' -d '{}'
```

**Expected while locked:** refusal naming `locked_until` — this is the
intended gate, not a failure. Once `locked_until` (wall-clock) and the
height window have passed, unbond begins the release.

### Step 4: Complete the release → `STAKE_RELEASE`

```bash
curl -s -X POST "$API/stake/<stake_id>/complete" -H 'content-type: application/json' -d '{}'
```

After the unbonding window settles, complete finalizes the position and
a `STAKE_RELEASE` seals returning the principal to the agent wallet.

---

## Alternative path: direct signed node RPC

Same mechanics as the bounty lane — the node RPC on `hub:8202` accepts
operator-signed bodies directly:

1. Strip `signature` from the payload.
2. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
3. `digest = keccak256(canonical_bytes)`; sign via eth_keys
   `sign_msg_hash` with `AGENT_ECONOMICS_OPERATOR_KEY`.
4. Attach as `signature` and POST.

Working reference: `hub:/root/v17-bounty_cycle.py` (bounty flavor, same
recipe).

---

## Validation

```bash
sqlite3 /var/lib/aitbc/data/<chain_id>/chain.db \
  "SELECT block_height, type, sender, recipient FROM transaction \
   WHERE type IN ('STAKE_LOCK','STAKE_RELEASE') ORDER BY rowid DESC LIMIT 10;"

curl -s "$API/stake/<stake_id>" | python3 -m json.tool
```

**Expected:**

- two `STAKE_LOCK` rows (create + add) carrying `payload.auth`
- one `STAKE_RELEASE` row after complete — recipient = agent wallet
- the stake record shows `locked_until` and transitions
  staked → unbonding → completed

---

## Related Resources

- [Bounty lifecycle](./86_bounty_lifecycle.md) — same operator-signing machinery
- [Scenario 01](./01_wallet_basics.md) steps 26–27 — wallet-signed staking
- [Scenario 83](./83_stake_options.md) — wallet-gate refusal plays
- [v17 activation runbook](../ops/v17-activation-runbook.md)
- [v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution)

---

*Last updated: 2026-10-28*
*Version: 1.0*
