# Manual escrow refund runbook

How to refund a job payment whose escrow is still held on-chain. There is
**no automatic refund sweeper** — refunds are deliberate operator or client
actions. Mechanisms verified against the code on `main`; cite points are
file:line.

Companion docs: `docs/ops/escrow-settlement-ops.md` (the full pipeline and
alerts), `docs/ops/escrow-routing.md` (escrow rows exist only on the node
that accepted the create call — run everything below against **that** node's
coordinator API and the hub's RPC).

## 1. Which payments are refundable

`REFUNDABLE_STATES`
(`apps/coordinator-api/src/coordinator_api/contexts/payments/acceptance.py:46`)
= `HELD_STATES` (`escrowed`, `pending_acceptance`, `disputed`, :43) plus
`settlement_failed` (:35). In words: any payment whose escrow is still
funded on-chain, including one whose release went terminally blocked.

Two additional gates in `refund_payment`
(`contexts/payments/services/payments.py`, ~L1722-1740):

- `escrowed_at` must be set — a row that never reached the escrowed state
  has no on-chain money to return (:1722).
- **Client vs operator scope**: a client JWT may only refund a plain
  `escrowed` payment whose result was never delivered. Once output exists,
  or the state is `pending_acceptance`/`disputed`/`settlement_failed`, the
  API answers 403 "refunds at this stage need an operator" (:1731-1738) —
  those are always arbiter calls.

## 2. The operator-facing call

`POST /payments/{payment_id}/refund`
(`contexts/payments/routers/payments.py:140`) authenticated with an
**admin** JWT (`AdminOrClientDep`; `is_admin` = `user["role"] == "admin"`,
:159). Body: `{"job_id": "<job_id>", "reason": "<free text>"}`.

- Admin path: the payment row is fetched directly, no ownership check;
  `refund_payment(..., is_admin=True)` bypasses the delivered-gate but still
  requires `REFUNDABLE_STATES` + `escrowed_at`.
- The route first **reconciles against the on-chain escrow**
  (`_reconcile_refund_state`, `payments.py:1612`): if the chain says the
  escrow is already `refunded`, the row is repaired locally and the call
  returns success without a new transaction; if the chain says it is
  **settled**, the call refuses — a settled escrow cannot be refunded.

Related operator tool (do not confuse the two):
`POST /payments/{job_id}/retry-release`
(`contexts/infrastructure/routers/admin.py:450`, `AdminDep`) clears the
`release_attempts` counter, moves `settlement_failed` back to `escrowed`,
and retries the release once — the choice when the provider should be paid,
not when the customer should be refunded.

## 3. Precondition: trust only the receipt of record

Before deciding *whether* a held payment deserves a refund, judge the job
from the canonical receipt, not from what either party mails you.
`get_receipt_of_record` (`payments.py:279-292`) resolves it: the
`JobReceipt` row indexed by `job.receipt_id` (the authoritative signed
record), falling back to the denormalised `job.receipt` JSON. A
client-provided receipt, screenshot, or log dump is not evidence — and for
`disputed`/`pending_acceptance` rows the release sweepers use the same
source (`_computation_is_correct`, :267-276), so an operator judgment made
from anything else can diverge from what the pipeline believes.

## 4. Pre-check list (all must hold before calling refund)

1. `job_payments.status` ∈ REFUNDABLE_STATES and `escrowed_at` is not NULL.
   (Anything else — `released`, `refunded`, `pending`, `failed` — is
   already final or never backed.)
2. Release attempts: read `meta_data["release_attempts"]`
   (`META_RELEASE_ATTEMPTS`, `acceptance.py:70`). The automatic bound is
   `DEFAULT_MAX_RELEASE_ATTEMPTS = 20` (:57; env override
   `COORDINATOR_RELEASE_MAX_ATTEMPTS`, :156). If the counter is below the
   bound and the row is still in a HELD state, the sweepers may still be
   retrying — prefer fixing the blocker, or understand you are refunding a
   payment mid-retry.
3. On-chain escrow state: query the escrow through the node's own RPC and
   confirm it is still locked (not `released`, not already `refunded`).
   The route re-checks this itself (§2), but deciding *before* the call is
   cheaper than handling a refusal.
4. No release already sealed: `released_at` NULL locally **and** no
   `ESCROW_RELEASE` receipt on-chain for this `job_id`. If a sealed release
   exists, the money is gone — see §6.
5. For `settlement_failed`: confirm the blocker is permanent enough that a
   release is the wrong outcome (otherwise use `retry-release`, §2).

## 5. Verification after the call

- Response `{"status": "refunded", "payment_id": …}` — the route only
  returns this after `_submit_refund` submitted the `ESCROW_REFUND` tx and
  the chain accepted it.
- `job_payments.status = refunded`, `refund_transaction_hash` set,
  `refunded_at` set; `job.payment_status = refunded`
  (the B-residue repair path also reconciles stale local hashes).
- On-chain: the custody address (`keccak("aitbc.escrow.<job_id>")[:20]`,
  keyless — `escrow-settlement-ops.md` §1.1) shows the escrow `refunded`
  and the funds back at the customer's address.

## 6. If the escrow shows a double settlement

If the chain says the escrow is `released`/`settled` **while** the local
row still looks refundable (or vice versa with money already moved): **stop
and escalate — do not refund.** The reconcile path (`_reconcile_refund_state`)
returns "cannot refund" for a settled escrow, so the API will refuse anyway;
forcing anything past that (manual txs, row edits) risks paying twice.
Capture the on-chain state, the `job_payments` row, and the job row, and
hand off — this is an accounting-divergence incident, not an ops action.

## 7. Live fleet posture (2026-10-08)

Read-only count on hub's coordinator.db (`mode=ro`, single aggregate):
zero `job_payments` rows currently sit in any refundable state —
`escrowed`, `pending_acceptance`, `disputed`, `settlement_failed` all
returned 0. This runbook currently has no live queue to serve; keep it for
the next held-escrow incident.
