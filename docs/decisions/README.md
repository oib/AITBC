# Decision log

One line per decision, newest first. The reason is the point — decisions get
revisited, and a reversal without the recorded reason is how a wrong call
gets re-made. Register items (O-*/K-*/BR-*/V-*/SD-*) reference the live task
register; this page keeps the decision itself when the register moves on.

| Date | Ref | Decision | Reason |
|------|-----|----------|--------|
| 2026-09-30 | V-7 | Governance votes are advisory tallies, not on-chain state — a vote row is written only on the node that received the RPC. | Apply never reads tallies; execution is gated on the executor signature. Recording them as chain state implied consensus they never had. |
| 2026-09-30 | O-7 | `BRIDGE_FUNDING_SOURCES` set to the treasury address now; move to a separate wallet before mainnet. | The knob matches the Ethereum-side sender of an ETH inflow — independent of the AITBC-side key split (K-1). Recording funding inflows as `FUNDING` beats deposit-path failures. The treasury key is hot on the hub, so it must not carry mainnet ETH. |
| 2026-09-30 | O-8 | The new bridge contract's owner is a 2-of-3 Safe; signers are three separate people on separate devices, addresses only (never keys/seeds in chat or repo). | A single hot key already cost one contract (lost deployer). Three people survive one unreachable signer and no more. |
| 2026-09-30 | BR-7 | Payout amount is locked at first pricing; per-deposit caps are fraction-of-float plus an absolute ceiling; float alerts count committed rows. | Oracle drift between pricing and payout must not change what a deposit pays; one outsized deposit must not drain the float; queued payouts already own part of the balance. |
| 2026-09-30 | SD-2 | Alertmanager delivery deferred — alerts stay as log lines plus fleet-check counts. | Lower priority than the v9 pin; the interim channel is adequate while deposits are canary-scale. |
| 2026-09-29 | K-1 | Authority move order: governance executor first (it can reassign the rest), then bridge release, escrow settlement, bond slash — each a `parameter_change` gov action to a new offline address. | The executor is the only authority that can move the others; moving it last would strand the rest under the old key. |
