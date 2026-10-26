# Escrow relays — who calls what

The blockchain node's `/rpc/escrow/*` routes are **IP-allowlisted and
API-key-gated** (security matrix: `X-API-Key`, Level 2). A customer node
has neither, so customer-facing escrow traffic goes through two JWT
relays on the coordinator API instead.

## The `to` address rule

Every escrow lock pays the **node wallet** of the settlement node —
`node_wallet` on `/health` — not the caller's own node wallet and not a
proposer id. On the current fleet hub and node0 share one node wallet;
node1, node2 and hub1 share another. A lock signed `to` anything else is
rejected with `400 "lock_tx to must be the node wallet"`.

## Create — `POST /v1/escrow/relay`

Accepts the raw `/rpc/escrow/create` payload (extra fields such as
`lock_signature`, `energy_quote`, `energy_quote_digest` pass through
verbatim) and relays it to the settlement node's `POST /rpc/escrow/create`
with the service-to-service key.

- **Buyer binding**: the `buyer` in the payload must equal the wallet
  row bound to the JWT `sub` (403 otherwise; admins exempt).
- **Cap**: non-admin calls are capped at 360,000,000 units (10 AIT).
- **Dedup/replay**: keyed on `sha256(lock_tx)` then `(client_id, job_id)`
  — a replay returns the stored `contract_id`; a different lock on the
  same `job_id` returns 409.
- **Errors**: chain 4xx passes through at the same status; a timeout or
  chain 5xx returns 502. Rate-limited 30/min per client credential.

## Release — `POST /v1/escrow/release`

Releases an escrow from a customer node that cannot reach the rpc.
Buyer-bound the same way: the caller must be the buyer of the named
escrow. A relay refusal (buyer mismatch, amount over the lock, unknown
job) is final — the CLI must not fall back to the rpc on a 4xx, only on
an unreachable relay or a missing credential.

- **425 "lock not yet sealed" is retryable, not a refusal**: the chain's
  `_ensure_lock_sealed` gate answers 425 (`Retry-After: 5`) while the
  ESCROW_LOCK is still in mempool, and the relay passes the 425 through
  (dropping the header). The CLI waits and reposts the same body —
  `Retry-After`-paced, default 5 s, 10 s per-wait cap, ~24 s total —
  which is safe because the relay dedups on `job_id`. If the bound is
  exhausted the failure is reported as a named retryable condition and
  the rpc fallback still does not fire (it would 425 identically);
  rerun `market escrow release` once the lock seals.
- **`amount` is currently required** by the request schema (422 when
  omitted); the bare-release CLI sites read the escrow's locked amount
  over the local→hub GET to fill it. Making `amount` optional so the
  chain releases the full lock server-side is proposed under
  ESCROW-RELEASE-3 (#469) pending the director's comment.

## Metrics and alerts (ESCROW-RELAY-OBS-1)

The relays count each request once on the Prometheus counter

```
aitbc_escrow_relay_requests_total{relay, result}
```

exported on the coordinator's `/prometheus` scrape endpoint (the generic
`http_requests_total` middleware labels cannot split these classes:
replay vs ok are both 200, and a chain timeout vs a chain 5xx both
surface as 502 — classification happens at the relay's result boundary).

- `relay` ∈ `create` | `release` | `refund`
- `result` ∈
  - `ok` — relayed and settled (200, `duplicate=false`)
  - `replay` — dedup/idempotency hit, stored result returned
  - `business_4xx` — fixable refusal (binding mismatch, over-cap, unknown
    job, conflicting lock, other chain 4xx pass-throughs)
  - `too_early_425` — "lock not yet sealed"; normal retryable traffic
  - `upstream_5xx` — chain 5xx, malformed upstream payload, or an
    internal error surfaced as 5xx
  - `chain_timeout` — no HTTP response from the settlement node
    (timeout, DNS, refused connection)

**Refund**: the counter and call site are already defined; the refund
relay router is mid-review, so the mount in `main.py` is guarded — the
`relay="refund"` series simply stays silent until that router lands.

**Scrape requirement**: the live `/etc/prometheus/prometheus.yml` on hub
needs a `coordinator-api` job with `metrics_path: /prometheus` (port
8203) before these series reach the rules — flagged on #474 as a
deployment follow-up; the alerts below are inert without it.

Alert rules in `scripts/monitoring/aitbc_rules.yml` (promtool-tested in
`aitbc_rules_test.yml`):

- **`EscrowRelayErrorRatio`** (warning) — `upstream_5xx` +
  `chain_timeout` share of a relay's requests over 15m > 20%, behind a
  ≥5-request floor so a single failure on an idle relay cannot trip it.
- **`EscrowRelay425Storm`** (warning) — more than 20 `too_early_425`
  answers in 15m on one relay. 425s are expected Retry-After traffic
  while an ESCROW_LOCK sits in mempool; a storm means releases are
  racing unsealed locks at volume or the chain stopped sealing them.

## Refund — stays on the settlement node

`/rpc/escrow/{job_id}/refund` has **no relay**: the settlement chain
refuses settlement operations from non-settlement nodes, and the relay
deliberately covers create+release only. `aitbc market escrow refund`
must reach a settlement node's rpc directly (allowlisted + API key).

## Named errors

- `403 "Forbidden: missing or invalid API key"` — direct `/rpc/escrow/*`
  from a customer node (this is the relay's reason for existing).
- `400 "lock_tx to must be the node wallet"` — wrong `to` on the lock.
- `403 Forbidden` — relay buyer-binding mismatch or a route missing
  from the security matrix (deny-by-default).
- `409` — a different lock already exists for the same `job_id`.
- `502` — chain timeout/5xx through the relay (safe to retry: dedup
  returns the stored row).

## Stuck-lock monitor — `scripts/ops/escrow-stuck-sweep.py`

A lock can outlive its job: a job that completes, fails, or is canceled
while its escrow row stays `locked` strands the money with no automatic
settler (SEC-20b, the #455 fast-job run). The sweep is the read-only
monitor for that condition: it opens the chain DB `escrow` and
`transaction` tables plus the coordinator `job`/`job_payments` tables
(and `marketplace_jobs` when present) through SQLite `mode=ro` +
`PRAGMA query_only=ON`, lists every lock whose job is terminal
(`COMPLETED`/`FAILED`/`CANCELED`/`EXPIRED`, terminal `job_payments.status`,
or a sealed `ESCROW_RELEASE`/`ESCROW_REFUND` leg) and older than
`--max-age` (default 1 h), and exits 1 when any exist. `--host hub`
runs the same read-only queries over ssh; `--textfile` emits
node_exporter metrics. Run by hand or from the gate — deliberately no
systemd unit; refunding a listed lock stays a settlement-node operator
action per the refund section above.
