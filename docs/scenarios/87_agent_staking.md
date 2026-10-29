# Agent Staking Lifecycle — stake → add → unbond → complete

**Level**: Advanced (operator lane)
**Status**: ✅ **Exercised on bc-2 (28 Oct)** — agent `STAKE_LOCK` @8912 `0x4a18e3f3`, `payload.auth`-signed, 3 attestations, roots verified
**Prerequisites**: v17 armed (`STATE_TRANSITION_V17_HEIGHT` set, head past the pin)
**Estimated Time**: 20 minutes + lock maturity
**Last Updated**: 2026-10-28
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Agent Staking Lifecycle

---

## Scenario Overview

Agent staking is **operator-signed** — since `3465dc438` the
`aitbc agent-staking` group (`stake`/`add`/`unbond`/`complete`/
`performance`/`distribute`/`claim`/`status`) is the operator-facing
surface; the curl evidence below predates it and remains the
sealed-proof reference.
The working path is the **signed node-RPC** surface on `hub:8202`
(`/v1/agent-staking/*`): the node re-verifies the operator's
`payload.auth` and forwards `STAKE_LOCK`/`STAKE_RELEASE` emissions.
This play walks the full position lifecycle:

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
staking. The refusal reads `Lock period has not ended`. Deploy the
position with the minimum lock period (1 day) if the release half must
complete within a day.

### Prerequisites

- node RPC reachable at `hub:8202` with `AGENT_ECONOMICS_OPERATOR_ADDRESS`
  configured on the rpc unit
- `AGENT_ECONOMICS_OPERATOR_KEY` available to the signing script
- a funded wallet to back the position
- head ≥ `STATE_TRANSITION_V17_HEIGHT`

---

## Operator path: signed node RPC (`hub:8202`)

Every step signs the request body the same way:

1. Strip `signature` from the payload.
2. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
3. `digest = keccak256(canonical_bytes)`; sign via eth_keys
   `sign_msg_hash` with `AGENT_ECONOMICS_OPERATOR_KEY`.
4. Attach the hex signature as `signature` and POST.

Working reference implementation: `hub:/root/v17-bounty_cycle.py`
(bounty flavor, same recipe — operator-held, not in the repo).

```bash
RPC=http://hub:8202   # node RPC on hub
```

### Step 1: Create a stake position → `STAKE_LOCK`

Sign and POST a stake body (`agent_wallet`, `amount`, `lock_period`):

```bash
curl -s -X POST "$RPC/v1/agent-staking/stake" -H 'content-type: application/json' -d @signed-stake.json
```

Record `stake_id`. A `STAKE_LOCK` seals with the operator's
`payload.auth`; the position's `locked_until` starts now and its status
is `active`.

### Step 2: Add to the position → `STAKE_LOCK`

Sign and POST the add body (`additional_amount`):

```bash
curl -s -X POST "$RPC/v1/agent-staking/stake/<stake_id>/add" -H 'content-type: application/json' -d @signed-add.json
```

A second `STAKE_LOCK` seals; `locked_until` may extend per the position
rules — re-read the position (`GET /v1/agent-staking/stake/<stake_id>`)
before proceeding.

### Step 3: Unbond — release-window gate

```bash
curl -s -X POST "$RPC/v1/agent-staking/stake/<stake_id>/unbond" -H 'content-type: application/json' -d @signed-unbond.json
```

**Expected while locked:** refusal `Lock period has not ended` — this
is the intended gate, not a failure. Once `locked_until` (wall-clock)
and the height window have passed, unbond begins the release.

### Step 4: Complete the release → `STAKE_RELEASE`

```bash
curl -s -X POST "$RPC/v1/agent-staking/stake/<stake_id>/complete" -H 'content-type: application/json' -d @signed-complete.json
```

After the unbonding window settles, complete finalizes the position and
a `STAKE_RELEASE` seals returning the principal to the agent wallet.

---

## Secondary path: coordinator-api (`/v1/stake`)

The coordinator-api on hub serves the same lifecycle under `/v1`
(`POST /v1/stake`, `/v1/stake/{id}/add`, `/v1/stake/{id}/unbond`,
`/v1/stake/{id}/complete`) and signs server-side via
`AGENT_ECONOMICS_OPERATOR_KEY` — but every handler requires
`get_current_user_required` (a coordinator account JWT), so it is
secondary for ops plays. Field shape differs from the node path:
`lock_period` (int, days, 1–365; not `lock_days`), `amount` in **AIT**
(`ait_to_units` conversion server-side; minimum 100 AIT, maximum
100 000 AIT), and the add step takes `additional_amount`.

---

## Validation

```bash
sqlite3 /var/lib/aitbc/data/<chain_id>/chain.db \
  "SELECT block_height, type, sender, recipient FROM transaction \
   WHERE type IN ('STAKE_LOCK','STAKE_RELEASE') ORDER BY rowid DESC LIMIT 10;"

curl -s "$RPC/v1/agent-staking/stake/<stake_id>" | python3 -m json.tool
```

**Expected:**

- two `STAKE_LOCK` rows (create + add) carrying `payload.auth`
- one `STAKE_RELEASE` row after complete — recipient = agent wallet
- the stake record shows `locked_until` and transitions
  active → unbonding → completed

---

## Related Resources

- [Bounty lifecycle](./86_bounty_lifecycle.md) — same operator-signing machinery
- [Scenario 01](./01_wallet_basics.md) steps 26–27 — wallet-signed staking
- [Scenario 83](./83_stake_options.md) — wallet-gate refusal plays
- [v17 activation runbook](../ops/v17-activation-runbook.md)
- [v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution--option-1-implemented-staking--bounty)

---

*Last updated: 2026-10-28*
*Version: 1.1*
