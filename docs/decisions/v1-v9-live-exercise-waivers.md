# V-1 — v9-era live-exercise waivers (2026-10-08)

**Decision (operator, 2026-10-08):** live exercise is **waived** for every
transaction type that can be exercised on a fixture chain — all 22 types
that have never sealed under v9 (state-transition v9, active since block
30400). The single exception is one live `BRIDGE_RELEASE` exercise, which
stays unbuilt and requires the operator's approval at that time.

**Why this is safe:** a sealed transaction proves two things — admission
and deterministic apply — and a fixture-chain replay proves the same two
things without a chain write. The replay harness
(`tests/unit/test_v9_type_coverage_replay.py` — built; see the V-1
close-out below) constructs synthetic blocks at v9 rules,
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
[v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution--option-1-implemented-staking--bounty);
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

**Supplementary evidence — Coder C live sweep on `bc-2` (final report,
head ~8736).** Coder C ran a live exercise sweep of the remaining
user-submitted types on `bc-2`. These observations are supplementary —
they are not part of the close condition above and V-1 does not wait on
them:

| type | sealed? | height | tx hash / note |
|---|---|---|---|
| MESSAGE | ✅ sealed | 8701 | `0x22dc0dcc…c0a76b` — `aitbc messaging send`, node0 `default` |
| AI_JOB | ✅ sealed | 8720 | `0xcaeb41d4…324bd68` — node0 `POST /ai/submit`, relayed to hub mempool |
| GPU_ALLOCATE | ✅ sealed | 8704 | `0x6703780c…e22fc5b` — node0 `coin-grant-test-2026-10-27`; fresh `GPU_REGISTER` @8702 `0xf356e94e…2fe35d91` as prep |
| GOVERNANCE_PROPOSE / VOTE | ✅ sealed | 8708 / 8716 | `0xee997ce3…ffda282c` (`prop_76855f71`) / `0xdfe148c9…339edcd6` — custom signer; the CLI cannot emit v13 `execution_payload` and the vote field is `vote_type`, not `vote` |
| GOVERNANCE_EXECUTE | ✅ sealed | 9278 | previously marked authority-gated (recon found no executor key in fleet stores) — **sealed @9278**: executor `0xD9CC189c` executed `governance_sweep_marker=bc-2-live-exercise`; evidence in #issuecomment-5226. The earlier `prop_76855f71` + one vote remain sealed; custody gate `d2095d800` stands for the post-reset chain |
| LIQUIDITY_* | ✅ retracted at v18 | 9600 | DEPOSIT **poisoned the chain**: `liq_<random>` stake_id + wall-clock `locked_until` are committed columns → every node computed a different v14 aux-root → 3-vs-2 liveness deadlock at 8705/8706; recovered via delta-journal `revert_losing_segment` (poison dropped, not requeued) + rejoin runbook, clean quorum at 8706 `0x14b9461e…`. WITHDRAW/CLAIM unreachable pre-9600 — exercisable at v18; seal heights append as C's plays land |
| BOND_* | ✅ retracted at v18 | 9600 | LOCK deliberately not fired — same nondeterminism class (`locked_until = datetime.now(UTC)` committed on the `bond` row); RELEASE unreachable; SLASH doubly blocked — needs both a sealed bond (impossible at v16) and `bond_slash_authority` (key absent fleet-wide). On-chain `BOND_SLASH` emission lives in `BondSlashingService.slash()` (`contexts/market/services/bond_slashing.py`, signs via `BOND_SLASH_PRIVATE_KEY`/`BOND_SLASH_AUTHORITY_ADDRESS`), invoked by job-scoped emitters — `infrastructure/routers/miner.py:379` on TEE/ZK verification failure, `infrastructure/routers/admin.py:334,413` on dispute rulings — not by the domain-status-only bonds endpoint |
| BRIDGE_LOCK | ⬛ config-blocked — resolved | — | `initiate_transfer` requires distinct source/target chains; every fleet node supports only `bc-2` — no valid lock target existed. **Decided:** companion island `bc-2-island-1` (option B — hub1+node1, 2-of-2 PBFT) is the target; deploy in Coder B's lane (`docs/ops/companion-island-deploy.md`), first live lock per [bridge-release-exercise](../ops/bridge-release-exercise.md) + [scenario 88](../scenarios/88_bridge_island_lock_release.md) |
| BRIDGE_WITHDRAW | ✅ sealed (chain side) | 8723 | `0x74301648…c2a3656` — 360000 units → `0xF1C83cd9…` on sepolia; **anomaly**: the monitor recorded it as "outbound refund" `aec7a816…` with no ledger row and no ETH payout — chain-side type proven. **Root cause found (Refs #652):** a hex-prefix join bug in the monitor's classification — the payout DID execute, 1.17µETH → `0xF1C83c…`; the "no payout" reading was the mislabeled ledger view, not a failed leg. **Fixed:** `e8bb7b749` (hex-prefix normalization); verified by C's live rerun (#issuecomment-5055) |
| ESCROW_FEE_SWEEP | ✅ sealed ×5 | 8744–8749 | root cause found: the sweep pass runs inside `aitbc-blockchain-rpc`, but `ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT=1` was pinned only in `aitbc-blockchain-node.env` → the rpc unit's default floor `35400` excluded every bc-2 leg → tick-only metrics. **Resolved:** pin moved into the shared `blockchain.env` ×5 + rpc restart (Coder A) → the full eligible backlog drained in five seals: `83631ce6` @8744 `0xdbbb515d…dc2c8d4` (900u), `sw_job_20261026000334` @8745 `0x26dc8e2c…a238e`, `sw_job_20261026012257` @8746 `0x3af28f3d…539c7` (1500u), `sw_job_20261026003141` @8747 `0x3d306611…ebe49`, `sw_job_20261026095528` @8749 `0xc92a5a26…0febb` — both of C's predicted candidates included |
| `STAKE_LOCK`/`STAKE_RELEASE` via `/v1/staking/*` | ✅ retracted at v18 | 9600 | unsealable — single-node committed-row defect: `stake` is a committed table (`COMMITTED_TABLES`) but the `/v1/staking/*` handlers write the row at queue time on the serving node only → the submitter's aux fingerprint diverges → it rejects the very block that sealed its lock; single-node fork-out (4/5 quorum holds; recovery = delete the row + rejoin). Fixed: `stake` exited `COMMITTED_TABLES_V18` at 9600 — Refs #649; per-type seal heights append as C's plays land; see [v14-aux-root-nondeterminism](../design/v14-aux-root-nondeterminism.md) |
| `STAKE_*` via `/v1/agent-staking/*` / `BOUNTY_*` | ✅ sealed ×5 at v17 | 8904–8912 | full revived-type cycle exercised post-activation — all five carry `payload.auth` signed by `0xAbD0D01ae6976F1D8E35b9D5CaF0dF66fAA009FA`, 3 attestations, v17 blocks, state+aux roots verified identical: `BOUNTY_LOCK` @8904 `0x49dc1b37`, `BOUNTY_PAYOUT` @8908 `0x693ef99a`, `BOUNTY_LOCK` #2 @8908 `0xa3a804f3`, `BOUNTY_REFUND` @8912 `0xf8c98983`, agent `STAKE_LOCK` @8912 `0x4a18e3f3`. `agent_stake`/`bounty_contract` uncommitted — the plays for [scenario 86](../scenarios/86_bounty_lifecycle.md) and [87](../scenarios/87_agent_staking.md) are exercised |
| `HTLC_*` / `AUTO_STAKE` | ⬛ dead | — | stay retired — no `payload.auth` to verify under the v17 rule (option 3 above) |
| BRIDGE_RELEASE / BRIDGE_REFUND | ⬛ not attempted | — | authority issuance; reserved for a separate approved exercise |

The sweep's headline finding: `apply_liquidity_deposit` and `apply_bond`
stamp nondeterministic values (random ids, wall-clock `locked_until`)
into committed side-table columns under the v14 aux-root rule, so any
proposed instance is guaranteed to fork the fleet. Fixing it needs
apply-time determinism (block time, deterministic ids) plus version
gating — a code change, not an ops one. **Decided (Card 6 = A):** the
fix is specced in `docs/design/v18-deterministic-committed-apply.md`
(Refs #649) — deterministic ids + block-header time + a v18 committed-set
re-scope (`stake` exits `COMMITTED_TABLES_V18`).

**The BRIDGE_RELEASE reservation stands.** The single live
`BRIDGE_RELEASE` exercise stays unbuilt and gated on the operator's
explicit approval; the draft runbook lives at
`docs/ops/bridge-release-exercise.md`.
