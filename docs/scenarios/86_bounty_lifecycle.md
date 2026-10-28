# Bounty Lifecycle — deploy → submit → verify (BOUNTY_PAYOUT) + expire (BOUNTY_REFUND)

**Level**: Advanced (operator lane)
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
exists. The preferred path is the coordinator-api on hub, which signs
server-side with `AGENT_ECONOMICS_OPERATOR_*` and forwards the
`payload.auth`-bearing protocol emissions to the node. This play runs
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

- coordinator-api running on hub with `AGENT_ECONOMICS_OPERATOR_ADDRESS`
  + `AGENT_ECONOMICS_OPERATOR_KEY` configured (fleet-wide per A's
  report)
- a funded escrow/lock source wallet for the deploy steps
- head ≥ `STATE_TRANSITION_V17_HEIGHT` (else every play returns 410)

---

## Operator path (preferred): coordinator-api on hub

Set the base URL once; the plays below use `curl` because no CLI
surface exists for the operator lane.

```bash
API=http://<hub-coordinator-api>   # coordinator-api on hub
```

### Step 1: Confirm the gate is open

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$API/bounties" -H 'content-type: application/json' -d '{}'
```

**Expected:** `410` while unarmed (next height < pin); a non-410
validation/auth response once armed. Do not proceed on 410.

### Step 2: Deploy a bounty → `BOUNTY_LOCK`

```bash
curl -s -X POST "$API/bounties" -H 'content-type: application/json' -d '{
  "title": "scenario-86 payout leg",
  "reward": "<units>",
  "funder_wallet": "<funded wallet address>",
  "deadline_height": "<current head + generous margin>"
}'
```

A `BOUNTY_LOCK` seals moving `reward` into bounty escrow. Record the
`bounty_id` from the response.

### Step 3: Submit work

```bash
curl -s -X POST "$API/bounties/<bounty_id>/submit" -H 'content-type: application/json' -d '{
  "worker_wallet": "<worker address>",
  "result_uri": "ipfs://<proof-of-work reference>"
}'
```

### Step 4: Verify the submission → `BOUNTY_PAYOUT`

```bash
curl -s -X POST "$API/bounties/<bounty_id>/verify" -H 'content-type: application/json' -d '{
  "submission_id": "<id from step 3>",
  "verdict": "accepted"
}'
```

The coordinator signs the payout authorization; the node emits a
`BOUNTY_PAYOUT` carrying `payload.auth`, which seals and pays the
worker.

### Step 5: Deploy a second bounty, then let it expire → `BOUNTY_REFUND`

Deploy as in step 2 with `deadline_height` only a few blocks ahead —
expiry triggers on the record's own deadline. Once the deadline height
has passed:

```bash
curl -s -X POST "$API/bounties/<bounty_id_2>/expire" -H 'content-type: application/json' -d '{}'
```

The coordinator signs the refund; a `BOUNTY_REFUND` seals returning the
escrowed reward to the funder.

---

## Alternative path: direct signed node RPC

The node RPC on `hub:8202` exposes the same lifecycle under its bounty
router (`/v1/bounty/*`) but requires a **pre-signed body** — sign
server-side yourself:

1. Strip `signature` from the payload.
2. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
3. `digest = keccak256(canonical_bytes)`; sign via eth_keys
   `Account.sign_msg_hash`/`sign_msg_hash` with the operator key
   (`AGENT_ECONOMICS_OPERATOR_KEY`).
4. Attach the hex signature as `signature` and POST.

Working reference implementation: `hub:/root/v17-bounty_cycle.py`
(operator-held, not in the repo).

---

## Validation

```bash
# sealed records on the hub node
sqlite3 /var/lib/aitbc/data/<chain_id>/chain.db \
  "SELECT block_height, type, sender, recipient FROM transaction \
   WHERE type IN ('BOUNTY_LOCK','BOUNTY_PAYOUT','BOUNTY_REFUND') ORDER BY rowid DESC LIMIT 10;"

# bounty record state
curl -s "$API/bounties/<bounty_id>" | python3 -m json.tool
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
- [v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution) — why these types revive
- [Agent staking lifecycle](./87_agent_staking.md) — same operator-signing machinery

---

*Last updated: 2026-10-28*
*Version: 1.0*
