# Market Escrow Alias Binding — squat-refusal replay (#2326)

**Level**: Advanced (operator lane)
**Status**: bindings live on main (`1c81c8c5d`, #2326) — play is runnable
**Prerequisites**: market service reachable; a funded buyer wallet; `MARKET_API_KEY` (user tier)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-11-21
**Version**: 1.1

**Legs**: 4

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Market Escrow Alias Binding

---

## Scenario Overview

`POST /v1/market/jobs` accepts caller-controlled `payload.escrow_job_id` —
the alias that lets an `ai submit` market job point at the coordinator
escrow keyed by the coordinator job id. Before #2326 residuals, the
user-tier `MARKET_API_KEY` (distributed to every CLI user) plus predictable
job ids let a squatter register a guessed escrow key first and have the
victim's locked escrow authorize the squatter's shop token.

Two bindings now close it:

1. **Buyer signature** — alias claims require a secp256k1 signature over
   `(escrow_job_id, buyer_address)` bound to `/v1/market/jobs`; the
   recovered signer must be the declared buyer. The API key alone is
   never sufficient.
2. **Lock-tx `market_job_id`** — `ai submit`/`ai pay` embed the market job
   id in the signed ESCROW_LOCK payload; alias token verification fetches
   the escrow's `lock_tx_hash` and requires `payload.market_job_id ==
   job.id`. Absent or mismatched binding fails closed.

This play replays the refusal legs live and confirms the bound path still
works. All refusal legs are pre-effect — nothing is signed or locked.

### What You'll Learn

- The difference between the user-tier API key and a wallet signature
- How `payload.escrow_job_id` aliases differ from self-bound jobs
- That escrow authority comes from the on-chain lock payload, not
  caller-supplied job fields

---

## Prerequisites

- `aitbc` CLI on `$PATH`, a funded wallet (`--wallet`)
- Market API reachable (hub `aitbc-market`); the user-tier key is resolved
  from `MARKET_API_KEY` / the node's market env file, or passed per
  invocation with `aitbc market --api-key "$API_KEY" …` (#2454)
- `aitbc market job-probe` for the raw-API legs — it posts the same
  `POST /v1/market/jobs` body shape with a caller-controlled
  `payload.escrow_job_id`, signature fields, and reports the HTTP status

---

## Step-by-Step Workflow

Set once:

```bash
export API_KEY="<user-tier MARKET_API_KEY>"   # only needed if env resolution doesn't already pick it up
BUYER=$(aitbc wallet info --wallet <buyer> --output json | jq -r .address)
```

The market service URL and API key resolve from the node config; pass
`--api-key "$API_KEY"` on the `market` group when you need an explicit
user-tier key. Every leg below prints a JSON record with `http_status`.

### Step 1: Unsigned alias claim is refused

```bash
aitbc market --api-key "$API_KEY" job-probe \
  --service-type whisper --escrow-job-id coord_probe_1 \
  --buyer-address "$BUYER" --no-signature --output json
```

**Expected:** `"http_status": 403` — `alias escrow claims require a buyer
wallet signature`. Pre-fix this returned `200` and minted a claim on the
named escrow key.

### Step 2: Signature bound to a different escrow key is refused

Sign the canonical message for `coord_probe_1` but claim `coord_probe_2` —
`--sign-escrow-job-id` selects the binding the signature covers while
`--escrow-job-id` selects the claimed alias:

```bash
aitbc market --api-key "$API_KEY" job-probe \
  --service-type whisper --escrow-job-id coord_probe_2 \
  --sign-escrow-job-id coord_probe_1 \
  --buyer-address "$BUYER" --output json
```

**Expected:** `403` — signature/binding mismatch. A captured signature
cannot be re-pointed at another escrow.

### Step 3: Self-bound job needs no signature (regression)

```bash
aitbc market --api-key "$API_KEY" job-probe \
  --service-type whisper --buyer-address "$BUYER" \
  --provider-address 0x<provider> --output json
```

**Expected:** `"http_status": 200` — no `--escrow-job-id` means no alias,
no signature required. The ordinary `market run`/self-bound shape is
unchanged.

### Step 4: Bound `ai submit` path still verifies (paid leg — gated)

Run a minimal paid transcribe submit on the customer node:

```bash
aitbc ai submit --type transcribe --input <url> --payment 0.01 --wallet <buyer> --coordinator-url <hub>
```

**Expected:** submit succeeds; the deferred market job registration
carries the buyer signature (visible in market logs as a normal create);
the gated shop call with the minted `X-Access-Key`/`X-Access-Secret`
authenticates — the lock tx sealed with `payload.market_job_id` equal to
the `ai_job_*` market job id (`aitbc transactions status <lock-tx>` shows
the payload field).

---

## Validation

```bash
# The refused Step-1 job must not exist:
curl -sS "$MARKET/jobs?buyer_address=$BUYER" -H "X-Api-Key: $API_KEY" | jq '.[] | select(.payload.escrow_job_id == "coord_probe_1")'
# Expected: no rows (or empty)

# Step-4 lock tx carries the binding:
aitbc transactions status --tx-hash <escrow-lock-tx-hash>
# Expected: sealed tx whose payload carries market_job_id = the ai_job_* market job id
```

---

## Related Resources

- Issue: #2326 (MARKET-ESCROW-SQUAT-1), #2325 (alias uniqueness), #2322 (escrow binding),
  #2454 (`market job-probe` CLI verb + group `--api-key`)
- Code: `apps/market/src/market_service/gates.py` (`_alias_claim_signature_gate`),
  `services/market_service/job_settlement.py` (`_alias_lock_binds_market_job`),
  `cli/aitbc_cli/commands/ai/submit.py`, `cli/aitbc_cli/utils/escrow.py`
- Tests: `apps/market/tests/test_alias_claim_signature_2326.py`,
  `test_escrow_squat_2326.py`, `test_access_token_escrow_alias_2325.py`

---

*Last updated: 2026-11-21*
*Version: 1.1*
