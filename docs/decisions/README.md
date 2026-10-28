# Decision log

One line per decision, newest first. The reason is the point — decisions get
revisited, and a reversal without the recorded reason is how a wrong call
gets re-made. Register items (O-*/K-*/BR-*/V-*/SD-*) reference the live task
register; this page keeps the decision itself when the register moves on.

| Date | Ref | Decision | Reason |
|------|-----|----------|--------|
| 2026-10-28 | BNT-1 | Decided — option 1A: a new state-transition height (`STATE_TRANSITION_V17_HEIGHT`, unset = unarmed) admits unsigned protocol transfers carrying a well-formed `payload.auth` — `STAKE_LOCK`, `STAKE_RELEASE`, `BOUNTY_LOCK`, `BOUNTY_PAYOUT`, `BOUNTY_REFUND` ([v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution--option-1-implemented-staking--bounty); commit `7f88f7381`). HTLC emissions and unsigned `AUTO_STAKE` stay retired (option 3). | The auth is re-verified at apply in both apply paths and at remote attestation, so the keyless-escrow design stays intact and the v9 signature rule is untouched — the strict-xfail pins keep recording the historical defect. The retired RPC surfaces return behind an activation gate (HTTP 410 below v17). |
| 2026-10-28 | card-10 | **A** — the consensus `/v1/staking/*` `STAKE_*` pin is waived at v17 (unsealable — a single-node committed-row defect), fixed by the same v18 gate as card 6 (Refs #649, [v14-aux-root-nondeterminism](../design/v14-aux-root-nondeterminism.md)). | The defect is deterministic-apply, not admission: one waiver covers the pin and the v18 fix covers the class — pinning a known-broken seal adds noise, not signal. |
| 2026-10-28 | card-9 | **B** — dead coordinator bounty router removed (commit `a072d8034`) — Refs #654. | Dead route surface only confused audits; removal is the fix, not a deferral. |
| 2026-10-28 | card-8 | **B** — REST is the canonical surface for the revived routes (no CLI wrappers); typed MCP tools spec in [docs/ops/mcp-agent-economics-tools.md](../ops/mcp-agent-economics-tools.md) — Refs #657. | One canonical surface keeps semantics single-sourced; MCP tools wrap REST rather than re-implementing it. |
| 2026-10-28 | card-7 | **B** — bridge payout-leg: investigate the "outbound refund" classification and re-run the withdraw — the `aec7a816…` anomaly. | A misclassified leg can hide a real payout failure; the classification must be understood before the next live withdraw. |
| 2026-10-28 | card-6 | **A** — v18 deterministic-apply bundle (fix, not waive): deterministic ids + block-time `locked_until` + `stake` exits `COMMITTED_TABLES_V18` ([design](../design/v18-deterministic-committed-apply.md), Refs #649). | Nondeterministic committed rows break replay across nodes; fixing at a version height is the consensus apply-time rule. |
| 2026-10-28 | card-5 | **B** — `GOVERNANCE_EXECUTE` marked authority-gated/unexercised on bc-2 (keys absent fleet-wide; custody lands post-reset, `d2095d800`) — waiver doc. | The capability cannot be exercised without keys that do not exist yet; a waiver records the gate honestly instead of faking a pass. |
| 2026-10-28 | card-11 | **B** — resize Lock B to 30,000,000u (sender `0x08aB80…` holds 34.78M; 36M+fees was ~1.26M short). Tier semantics preserved — boundary is `>10,000u` — with zero fund movement needed; [bridge-release-exercise](../ops/bridge-release-exercise.md) + scenario 88 updated. | |
| 2026-10-28 | card-4 | **A — executed** — the v17 pin became a code literal post-proof (env → literal, the v15 pattern): `13f72546f` defaults `state_transition_v17_height` to `8900`; bc-2 env pins removed fleet-wide (env now override-only; islands/new chains still pin); [v17 activation runbook](../ops/v17-activation-runbook.md) now EXECUTED. | Once proven, a pinned env value is a config knob that can drift; a literal in code makes the activation immutable. |
| 2026-10-28 | card-3 | **Moot** — `BRIDGE_LOCKS_PAUSED=false` is already fleet-wide; the exercise IS the first live lock — no unpause step exists. | The card assumed a pause that was never in force; recording it as moot keeps the log truthful. |
| 2026-10-28 | card-2 | Two-tier locks — 5,000 units (3-conf) + 36,000,000 units = 1 AIT (6-conf); sender node0 `default` → fresh island recipient (`0xc1B940CE…5E40`, 10 AIT genesis alloc) — [bridge release exercise](../ops/bridge-release-exercise.md). | Two tiers exercise both confirmation depths; a fresh recipient with genesis alloc isolates the payout leg from existing balances. |
| 2026-10-28 | card-1 | **B** — companion island subset: `bc-2-island-1` produced by hub1+node1 (2-of-2 PBFT) with dedicated units/env — deploy spec [docs/ops/companion-island-deploy.md](../ops/companion-island-deploy.md), Refs #659. | A two-node island gives PBFT coverage on real hardware without touching the production island; dedicated units keep env isolation clean. |
| 2026-10-12 | all | [Full decision table for 12 October](2026-10-12-operator-decisions.md) — every operator call of that day verbatim from the task register. | One dated page keeps the batch readable when the register moves on. |
| 2026-10-12 | V-3 | Committed set = all 13 apply-written tables; shadow compute first, compare-only | Canonicalization rules spec'd ([design doc](../design/v3-side-table-root-shadow.md)); a table that drifts in the soak is dropped, never repaired; activation height shared with V-2/V-4/BNT-1. |
| 2026-10-12 | BNT-1 | Open — every `queue_protocol_transfer` emission (stake, agent-stake, auto-stake, bounty, HTLC; 12 call sites) is unsigned at the top level and rejected by the v9 signature rule; zero sealed since 30400 ([audit + options](../design/v9-unsigned-protocol-transfers.md)). | The emitter never signs (keyless escrow); v9 exempts only BRIDGE_*. Options: admit `payload.auth` at a new version height, sign lock legs at emission, or retire the dead surfaces. Decided 2026-10-28 — see the row above. |
| 2026-10-08 | V-4 | Grandfathering activation boundary set to height 30000 ([design](../design/bridge-state-root-grandfathering.md)); audit tool default and fixtures pin it. | All 4 underivable legacy locks sit below it (≈2.4k–8.3k) and the boundary is inside sealed history, so no existing seal can ever flip class; underivable locks sealed after activation are defects the seal-path guard rejects. |
| 2026-10-08 | V-1 | Live exercise waived for all 22 fixture-replayable types never sealed under v9 ([waiver list](v1-v9-live-exercise-waivers.md)); one live BRIDGE_RELEASE stays reserved pending operator approval. | A fixture-chain replay proves admission + deterministic apply — the same two things a sealed tx proves — without a chain write. Nothing is un-replayable, so per-type live txs add cost, not assurance. |
| 2026-10-01 | SD-1 | Escrow rows are rebuildable from sealed ESCROW_LOCK/RELEASE/REFUND history; the rebuild tool proves per-job and global invariants before any write ([design](../design/escrow-rebuild-from-chain.md)). | The sealed transaction table is the only record guaranteed on every node; RPC-written rows are lossy bookkeeping. Writing a row the chain contradicts is worse than leaving the gap. |
| 2026-09-30 | V-7 | Governance votes are advisory tallies, not on-chain state — a vote row is written only on the node that received the RPC. | Apply never reads tallies; execution is gated on the executor signature. Recording them as chain state implied consensus they never had. |
| 2026-09-30 | O-7 | `BRIDGE_FUNDING_SOURCES` set to the treasury address now; move to a separate wallet before mainnet — migration plan in [docs/ops/bridge-funding-source-migration.md](../ops/bridge-funding-source-migration.md). Testnet cutover done 16 Oct: F=rehearsal signer3 `0x7bD5…91D2`, overlap `F,0x02b8…` on hub; shrink + mainnet pass still open. | The knob matches the Ethereum-side sender of an ETH inflow — independent of the AITBC-side key split (K-1). Recording funding inflows as `FUNDING` beats deposit-path failures. The treasury key is hot on the hub, so it must not carry mainnet ETH. |
| 2026-09-30 | O-8 | The new bridge contract's owner is a 2-of-3 Safe; signers are three separate people on separate devices, addresses only (never keys/seeds in chat or repo). | A single hot key already cost one contract (lost deployer). Three people survive one unreachable signer and no more. |
| 2026-09-30 | BR-7 | Payout amount is locked at first pricing; per-deposit caps are fraction-of-float plus an absolute ceiling; float alerts count committed rows. | Oracle drift between pricing and payout must not change what a deposit pays; one outsized deposit must not drain the float; queued payouts already own part of the balance. |
| 2026-09-30 | SD-2 | Alertmanager delivery deferred — alerts stay as log lines plus fleet-check counts. | Lower priority than the v9 pin; the interim channel is adequate while deposits are canary-scale. |
| 2026-09-29 | K-1 | Authority move order: governance executor first (it can reassign the rest), then bridge release, escrow settlement, bond slash — each a `parameter_change` gov action to a new offline address. | The executor is the only authority that can move the others; moving it last would strand the rest under the old key. |

Related design documents:

- [key-custody-proposal.md](../design/key-custody-proposal.md) — plaintext key
  inventory, custody tiers and the encrypted-copy procedure (K-4).
- [eth7-escrowed-sell-flow.md](../design/eth7-escrowed-sell-flow.md) — hub-escrowed
  AIT→ETH sell flow: keyed escrow lock now, keyless protocol escrow post-settle
  (ETH-7 design, Sepolia only).
- [eth8-exchange-page.md](../design/eth8-exchange-page.md) — hub trade exchange
  page: read-only book/tape first, then signed orders, then ETH-7-funded
  settlement (ETH-8 design, Sepolia only).
- [node-held-wallet-access.md](../design/node-held-wallet-access.md) — bounded,
  allow-listed, operator-approved agent spends from a node-held ops wallet (SEC-1).
- [TOPOLOGY/2026-10-16-wallet-custody-inventory.md](../../TOPOLOGY/2026-10-16-wallet-custody-inventory.md) —
  read-only fleet wallet custody inventory (WALLET-CUSTODY-1); operator decision
  16 Oct: accept plaintext.
- [TOPOLOGY/2026-10-16-keytrace.md](../../TOPOLOGY/2026-10-16-keytrace.md) —
  KEYTRACE-1: fleet backup-file inventory (5 key-bearing env backups named) and
  the 0x02B8 treasury signing trace — verdict historical, last send 7 Oct.
- [TOPOLOGY/2026-10-17-env-var-crosscheck.md](../../TOPOLOGY/2026-10-17-env-var-crosscheck.md) —
  ENV-XCHECK-1: names-only fleet env census (307 names, 115 service records) —
  20 fictional/stale keys removed from `/etc/aitbc/*.env` on 17 Oct; scanner
  pitfalls + node0 orphan-fragment note for re-runs.
