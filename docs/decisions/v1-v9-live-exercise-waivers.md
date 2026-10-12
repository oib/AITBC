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
