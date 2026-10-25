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
