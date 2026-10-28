# V-1 — v9-era live-exercise waivers (2026-10-08)

**Decision (operator, 2026-10-08):** live exercise is **waived** for every
transaction type that can be exercised on a fixture chain — all 22 types
that have never sealed under v9 (state-transition v9, active since block
30400). The single exception is one live `BRIDGE_RELEASE` exercise, which
stays unbuilt and requires the operator's approval at that time.

**Why this is safe:** a sealed transaction proves two things — admission
and deterministic apply — and a fixture-chain replay proves the same two
things without a chain write. The replay harness
(`tests/apps/blockchain-node/test_v9_type_coverage_replay.py`, to be
built per the round-8 design) constructs synthetic blocks at v9 rules,
signs them with fixture keys, mints prerequisite rows, and replays the
block twice asserting identical final state — the same determinism check
the V-2 adversarial replay test uses.

## The 22 waived types

Each row names the parametrized replay test that will exercise the type
(`test_v9_type_coverage_replay.py::test_v9_type_replayed[<TYPE>]`), the
chain-state prerequisite the fixture must mint, and the existing
apply-path test file that already touches the type.

| type | fixture prerequisite | replay test | existing apply-path coverage |
|---|---|---|---|
| AI_JOB | none | `test_v9_type_replayed[AI_JOB]` | test_apply_parity, test_gossip_tx_admission |
| MESSAGE | none | `test_v9_type_replayed[MESSAGE]` | test_mempool_admission, message-type tests |
| BOND_LOCK | none | `test_v9_type_replayed[BOND_LOCK]` | test_bond_* |
| BOND_RELEASE | BOND_LOCK sealed | `test_v9_type_replayed[BOND_RELEASE]` | test_bond_* |
| BOND_SLASH | BOND_LOCK sealed + authority sender | `test_v9_type_replayed[BOND_SLASH]` | test_bond_*, authority tests |
| BOUNTY_LOCK | none | `test_v9_type_replayed[BOUNTY_LOCK]` | test_bounty_* |
| BOUNTY_PAYOUT | BOUNTY_LOCK sealed | `test_v9_type_replayed[BOUNTY_PAYOUT]` | test_bounty_* |
| BOUNTY_REFUND | BOUNTY_LOCK sealed | `test_v9_type_replayed[BOUNTY_REFUND]` | test_bounty_* |
| BRIDGE_LOCK | none | `test_v9_type_replayed[BRIDGE_LOCK]` | test_bridge_* suites |
| BRIDGE_RELEASE | BRIDGE_LOCK sealed + signed-envelope fixture (validator signatures minted by fixture keys; live lock @27251 provides the envelope shape) | `test_v9_type_replayed[BRIDGE_RELEASE]` | test_bridge_* suites — **live exercise also reserved, see below** |
| BRIDGE_REFUND | BRIDGE_LOCK sealed + signed-envelope fixture | `test_v9_type_replayed[BRIDGE_REFUND]` | test_bridge_* suites |
| BRIDGE_WITHDRAW | bridge credit state | `test_v9_type_replayed[BRIDGE_WITHDRAW]` | test_bridge_withdraw_state |
| GOVERNANCE_PROPOSE | none | `test_v9_type_replayed[GOVERNANCE_PROPOSE]` | test_governance_* |
| GOVERNANCE_VOTE | GOVERNANCE_PROPOSE sealed | `test_v9_type_replayed[GOVERNANCE_VOTE]` | test_governance_* |
| GPU_ALLOCATE | GPU_REGISTER sealed | `test_v9_type_replayed[GPU_ALLOCATE]` | test_gpu_* |
| IPFS_SUBSCRIPTION | none | `test_v9_type_replayed[IPFS_SUBSCRIPTION]` | test_apply_parity |
| LIQUIDITY_DEPOSIT | none | `test_v9_type_replayed[LIQUIDITY_DEPOSIT]` | test_liquidity |
| LIQUIDITY_WITHDRAW | LIQUIDITY_DEPOSIT sealed | `test_v9_type_replayed[LIQUIDITY_WITHDRAW]` | test_liquidity |
| LIQUIDITY_CLAIM | liquidity position | `test_v9_type_replayed[LIQUIDITY_CLAIM]` | test_liquidity |
| RECEIPT_CLAIM | receipt issued | `test_v9_type_replayed[RECEIPT_CLAIM]` | receipt tests |
| STAKE_LOCK | none | `test_v9_type_replayed[STAKE_LOCK]` | test_staking, test_nonce_* |
| STAKE_RELEASE | STAKE_LOCK sealed | `test_v9_type_replayed[STAKE_RELEASE]` | test_staking |

## Finding surfaced by the replay suite (2026-10-12)

`BOUNTY_PAYOUT` and `BOUNTY_REFUND` are replayable **in the apply code**
but **unsealable in the production shape**: `queue_protocol_transfer`
emits them unsigned (the bounty escrow is keyless — no sender signature
can exist), and the v9 signature rule exempts only `BRIDGE_*`. Their
`payload.auth` operator signature does not satisfy the top-level
presence check. Both cases are strict-xfail in the suite; making them
sealable needs a consensus change (admit `payload.auth` at v9, or sign
the envelope) — an operator decision, flagged here rather than waived.

**Resolved (2026-10-28) — BNT-1 decided, option 1A.** The operator chose
the consensus change, delivered as a new state-transition height rather
than a v9 amendment: `STATE_TRANSITION_V17_HEIGHT` (unset = unarmed)
admits unsigned protocol transfers carrying a well-formed
`payload.auth` — `STAKE_LOCK`, `STAKE_RELEASE`, `BOUNTY_LOCK`,
`BOUNTY_PAYOUT`, `BOUNTY_REFUND` — with the auth re-verified at apply in
both apply paths and at remote attestation. HTLC emissions and unsigned
`AUTO_STAKE` carry no auth and stay retired (option 3). The mechanism is
documented in
[v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution);
implementation commit `7f88f7381`. The strict-xfail pins stay — they
record the historical v9 defect this decision repaired, replayed at v9
rules on purpose.

## What is NOT waived

- The **live `BRIDGE_RELEASE` exercise**: kept because only a live release
  exercises the full monitor → envelope → seal path end-to-end. It is
  unbuilt today and needs the operator's explicit approval when proposed.
- Any type a fixture *cannot* replay honestly would need live exercise —
  currently zero such types; the waiver is conditional on the replay
  suite landing green on main.

## Close condition for V-1

`test_v9_type_coverage_replay.py` lands on main, all 22 parametrized cases
green, and the fleet keeps agreeing on every block (already verified:
8584 v9-era blocks identical across all five hosts at head 39089).

## Close-out (2026-10-28)

**Condition met.** All three legs of the close condition hold on `main`:

1. **The replay suite landed and is green.** The harness lives at
   `tests/unit/test_v9_type_coverage_replay.py` — the suite in `2c6707d8d`,
   the production-shape xfail pins in `f54decccc`, the v17 section in
   `7f88f7381`. A full run reports **44 passed + 13 strict xfailed** (57
   cases). All 22 parametrized `test_v9_type_replayed` cases are green:
   20 pass, and `BOUNTY_PAYOUT`/`BOUNTY_REFUND` are strict-xfail **by
   design** — they pin the historical v9 defect (the unsigned production
   shape was unsealable after block 30400), replay deliberately at v9
   rules, and would flip to XPASS the day v9 admitted them. The other 11
   xfails are the same pin on the production-emission cases.
2. **The v17 section proves the BNT-1 revival deterministically.** The
   seven emissions carrying a well-formed `payload.auth` — the
   `STAKE_LOCK`/`STAKE_RELEASE` shapes emitted by staking and
   agent-staking plus `BOUNTY_LOCK`/`BOUNTY_PAYOUT`/`BOUNTY_REFUND` —
   seal on two independent databases with identical accounts and state
   root. The four no-auth emissions (`AUTO_STAKE`, the HTLC shapes) keep
   the exact v9 `missing_signature` rejection at v17.
3. **Fleet agreement already held at waiver time** — 8584 v9-era blocks
   identical across all five hosts at head 39089, as recorded above.
   (The fleet has since cut to `bc-2`; the replayed v9-era blocks are
   historical and identical on every host.)

**Supplementary evidence — Coder C live sweep on `bc-2` (in flight).**
Coder C is running a live exercise sweep of the remaining user-submitted
types on `bc-2`. These observations are supplementary — they are not part
of the close condition above and V-1 does not wait on them. Results to be
filled in from C's report; do not write outcomes here ahead of it:

| type | sealed? | height | tx hash / note |
|---|---|---|---|
| MESSAGE | ⬜ pending | — | Coder C sweep |
| AI_JOB | ⬜ pending | — | Coder C sweep |
| GPU_ALLOCATE | ⬜ pending | — | Coder C sweep |
| GOVERNANCE_* | ⬜ pending | — | Coder C sweep |
| LIQUIDITY_* | ⬜ pending | — | Coder C sweep |
| BOND_* | ⬜ pending | — | Coder C sweep |
| BRIDGE_LOCK | ⬜ pending | — | Coder C sweep |
| BRIDGE_WITHDRAW | ⬜ pending | — | Coder C sweep |
| ESCROW_FEE_SWEEP | ⬜ pending | — | observation only — Coder C sweep |

**The BRIDGE_RELEASE reservation stands.** The single live
`BRIDGE_RELEASE` exercise stays unbuilt and gated on the operator's
explicit approval; the draft runbook lives at
`docs/ops/bridge-release-exercise.md`.
