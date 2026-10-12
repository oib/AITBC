# Decision log

One line per decision, newest first. The reason is the point — decisions get
revisited, and a reversal without the recorded reason is how a wrong call
gets re-made. Register items (O-*/K-*/BR-*/V-*/SD-*) reference the live task
register; this page keeps the decision itself when the register moves on.

| Date | Ref | Decision | Reason |
|------|-----|----------|--------|
| 2026-10-12 | all | [Full decision table for 12 October](2026-10-12-operator-decisions.md) — every operator call of that day verbatim from the task register. | One dated page keeps the batch readable when the register moves on. |
| 2026-10-12 | V-3 | Committed set = all 13 apply-written tables; shadow compute first, compare-only | Canonicalization rules spec'd ([design doc](../design/v3-side-table-root-shadow.md)); a table that drifts in the soak is dropped, never repaired; activation height shared with V-2/V-4/BNT-1. |
| 2026-10-12 | BNT-1 | Open — every `queue_protocol_transfer` emission (stake, agent-stake, auto-stake, bounty, HTLC; 12 call sites) is unsigned at the top level and rejected by the v9 signature rule; zero sealed since 30400 ([audit + options](../design/v9-unsigned-protocol-transfers.md)). | The emitter never signs (keyless escrow); v9 exempts only BRIDGE_*. Options: admit `payload.auth` at a new version height, sign lock legs at emission, or retire the dead surfaces. Operator decision pending. |
| 2026-10-08 | V-4 | Grandfathering activation boundary set to height 30000 ([design](../design/bridge-state-root-grandfathering.md)); audit tool default and fixtures pin it. | All 4 underivable legacy locks sit below it (≈2.4k–8.3k) and the boundary is inside sealed history, so no existing seal can ever flip class; underivable locks sealed after activation are defects the seal-path guard rejects. |
| 2026-10-08 | V-1 | Live exercise waived for all 22 fixture-replayable types never sealed under v9 ([waiver list](v1-v9-live-exercise-waivers.md)); one live BRIDGE_RELEASE stays reserved pending operator approval. | A fixture-chain replay proves admission + deterministic apply — the same two things a sealed tx proves — without a chain write. Nothing is un-replayable, so per-type live txs add cost, not assurance. |
| 2026-10-01 | SD-1 | Escrow rows are rebuildable from sealed ESCROW_LOCK/RELEASE/REFUND history; the rebuild tool proves per-job and global invariants before any write ([design](../design/escrow-rebuild-from-chain.md)). | The sealed transaction table is the only record guaranteed on every node; RPC-written rows are lossy bookkeeping. Writing a row the chain contradicts is worse than leaving the gap. |
| 2026-09-30 | V-7 | Governance votes are advisory tallies, not on-chain state — a vote row is written only on the node that received the RPC. | Apply never reads tallies; execution is gated on the executor signature. Recording them as chain state implied consensus they never had. |
| 2026-09-30 | O-7 | `BRIDGE_FUNDING_SOURCES` set to the treasury address now; move to a separate wallet before mainnet. | The knob matches the Ethereum-side sender of an ETH inflow — independent of the AITBC-side key split (K-1). Recording funding inflows as `FUNDING` beats deposit-path failures. The treasury key is hot on the hub, so it must not carry mainnet ETH. |
| 2026-09-30 | O-8 | The new bridge contract's owner is a 2-of-3 Safe; signers are three separate people on separate devices, addresses only (never keys/seeds in chat or repo). | A single hot key already cost one contract (lost deployer). Three people survive one unreachable signer and no more. |
| 2026-09-30 | BR-7 | Payout amount is locked at first pricing; per-deposit caps are fraction-of-float plus an absolute ceiling; float alerts count committed rows. | Oracle drift between pricing and payout must not change what a deposit pays; one outsized deposit must not drain the float; queued payouts already own part of the balance. |
| 2026-09-30 | SD-2 | Alertmanager delivery deferred — alerts stay as log lines plus fleet-check counts. | Lower priority than the v9 pin; the interim channel is adequate while deposits are canary-scale. |
| 2026-09-29 | K-1 | Authority move order: governance executor first (it can reassign the rest), then bridge release, escrow settlement, bond slash — each a `parameter_change` gov action to a new offline address. | The executor is the only authority that can move the others; moving it last would strand the rest under the old key. |

Related design document: [key-custody-proposal.md](../design/key-custody-proposal.md)
— plaintext key inventory, custody tiers and the encrypted-copy procedure (K-4).
