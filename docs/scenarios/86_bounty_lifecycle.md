# Bounty Lifecycle — deploy → submit → verify (BOUNTY_PAYOUT) + expire (BOUNTY_REFUND)

**Level**: Advanced (operator lane)
**Status**: ✅ **Exercised on bc-2 (28 Oct)** — `BOUNTY_LOCK` @8904 `0x49dc1b37`, `BOUNTY_PAYOUT` @8908 `0x693ef99a`, `BOUNTY_LOCK` #2 @8908 `0xa3a804f3`, `BOUNTY_REFUND` @8912 `0xf8c98983` — all `payload.auth`-signed, 3 attestations, roots verified
**Prerequisites**: v17 armed (`STATE_TRANSITION_V17_HEIGHT` set, head past the pin)
**Estimated Time**: 30 minutes + seal time
**Last Updated**: 2026-10-28
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Bounty Lifecycle

---

## Scenario Overview

The bounty lifecycle is **operator-signed** — no `aitbc` CLI surface
exists, and the coordinator-api's full bounty router is **dead code**
(`main.py` mounts only the `bounty_flat` stub — `POST /bounties` etc.
in `contexts/bounty/routers/bounty.py` are never served). The working
path is the **signed node-RPC** `/v1/bounty/*` surface on `hub:8202`
with a body signed by `AGENT_ECONOMICS_OPERATOR_KEY`. This play runs
both halves of the lifecycle so both revived record types seal:

- deploy → submit → verify → **`BOUNTY_PAYOUT`** seals
- deploy → expire → **`BOUNTY_REFUND`** seals

**v17 gate:** the bounty endpoints answer **HTTP 410** while the next
block height resolves below `STATE_TRANSITION_V17_HEIGHT`; they go live
at/after the pin. Unsigned `payload`-less bodies are rejected outright —
the emissions seal only carrying a verified operator signature
(`BOUNTY_PAYOUT`/`BOUNTY_REFUND` were unsealable unsigned under v9–v16;
strict-xfail pins in `test_v9_type_coverage_replay.py` document that
defect).

### Prerequisites

- node RPC reachable at `hub:8202` with `AGENT_ECONOMICS_OPERATOR_ADDRESS`
  configured on the rpc unit (the verifying side)
- `AGENT_ECONOMICS_OPERATOR_KEY` available to the signing script (the
  reference below reads it on hub)
- a funded escrow/lock source wallet for the deploy steps
- head ≥ `STATE_TRANSITION_V17_HEIGHT` (else every play returns 410)

---

## Operator path: signed node RPC (`hub:8202`)

Every step signs the request body the same way:

1. Strip `signature` from the payload.
2. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
3. `digest = keccak256(canonical_bytes)`; sign via eth_keys
   `sign_msg_hash` with `AGENT_ECONOMICS_OPERATOR_KEY`.
4. Attach the hex signature as `signature` and POST to the node RPC.

Working reference implementation: `hub:/root/v17-bounty_cycle.py`
(operator-held, not in the repo) — it already exercises the full cycle
below; the steps here annotate what each call does on-chain. Plays use
`curl` because no `aitbc` CLI surface exists.

```bash
RPC=http://hub:8202   # node RPC on hub
```

### Step 1: Confirm the gate is open

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$RPC/v1/bounty/deploy" -H 'content-type: application/json' -d '{}'
```

**Expected:** `410` while unarmed (next height < pin); a non-410
validation/signature error once armed. Do not proceed on 410.

### Step 2: Deploy a bounty → `BOUNTY_LOCK`

Sign and POST a deploy body — title, `reward` (units), `funder_wallet`,
`deadline_height` (give the payout leg generous margin):

```bash
curl -s -X POST "$RPC/v1/bounty/deploy" -H 'content-type: application/json' -d @signed-deploy.json
```

A `BOUNTY_LOCK` seals moving `reward` into bounty escrow. Record the
`bounty_id` from the response.

### Step 3: Submit work

Sign and POST the submission body (`bounty_id`, `worker_wallet`,
`result_uri`):

```bash
curl -s -X POST "$RPC/v1/bounty/<bounty_id>/submit" -H 'content-type: application/json' -d @signed-submit.json
```

### Step 4: Verify the submission → `BOUNTY_PAYOUT`

Sign and POST the verify body (`bounty_id`, `submission_id`, verdict
accepted):

```bash
curl -s -X POST "$RPC/v1/bounty/<bounty_id>/verify" -H 'content-type: application/json' -d @signed-verify.json
```

The node re-verifies the operator `payload.auth` and emits a
`BOUNTY_PAYOUT`, which seals and pays the worker.

### Step 5: Deploy a second bounty, then expire → `BOUNTY_REFUND`

Deploy as in step 2 with `deadline_height` only a few blocks ahead —
expiry triggers on the record's own deadline. Once the deadline height
has passed, sign and POST the expire body:

```bash
curl -s -X POST "$RPC/v1/bounty/<bounty_id>/expire" -H 'content-type: application/json' -d @signed-expire.json
```

A `BOUNTY_REFUND` seals returning the escrowed reward to the funder.

---

## Validation

```bash
# sealed records on the hub node
sqlite3 /var/lib/aitbc/data/<chain_id>/chain.db \
  "SELECT block_height, type, sender, recipient FROM transaction \
   WHERE type IN ('BOUNTY_LOCK','BOUNTY_PAYOUT','BOUNTY_REFUND') ORDER BY rowid DESC LIMIT 10;"

# bounty record state — read via the node RPC bounty router
curl -s "$RPC/v1/bounty/<bounty_id>" | python3 -m json.tool
```

**Expected:**

- `BOUNTY_LOCK` after step 2 and step 5's deploy
- `BOUNTY_PAYOUT` after step 4 — recipient = worker wallet
- `BOUNTY_REFUND` after step 5 — recipient = funder wallet
- All three rows carry a non-empty auth signature on the payload

---

## Related Resources

- [On-chain record coverage](./README.md#on-chain-record-coverage)
- [v17 activation runbook](../ops/v17-activation-runbook.md) — gate semantics
- [v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution--option-1-implemented-staking--bounty) — why these types revive
- [Agent staking lifecycle](./87_agent_staking.md) — same operator-signing machinery

---

*Last updated: 2026-10-28*
*Version: 1.0*
