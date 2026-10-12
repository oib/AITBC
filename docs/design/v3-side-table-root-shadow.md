# V-3 — committed side-table root: 13-table set and per-block shadow compute

**Status:** design only; no consensus code. Operator decision 2026-10-12:
the committed set is all 13 apply-written tables; shadow computation runs
in compare-only mode first. Executable reference: `scripts/ops/side-root-probe.py
--canonical` (identical rules).

## Committed set

All 13 tables written by `StateTransition.apply_transaction` and its
`state/*` helpers:

```text
account  bond  chain_parameter  chain_parameter_history
edge_node_registration  gpu_allocation  gpu_registration
ipfs_subscription  liquidity_distribution  liquidity_pool
liquidity_stake  receipt  stake
```

`account` is the canary — already committed via `state_root`, so it must
always agree. Verified fleet-wide at height 44672: every table's
canonical digest is identical on all five hosts; set fingerprint
`49da49df` everywhere.

Excluded by design: node-local bookkeeping (escrow, governance_*,
mempool, cross_chain_transfer, bridge_*, consensus_state) and history
tables (block, transaction).

## Canonicalization rules (the spec)

A committed table digest is defined over rows and columns as follows —
same rules the probe applies under `--canonical`:

1. **Column exclusion — `*_at` stamps.** Every column whose name ends in
   `_at` is a locally stamped wall-clock value (registered_at,
   allocated_at, completed_at, created_at, updated_at) and is excluded.
   A table's committed columns are therefore its schema columns minus the
   `*_at` ones.
2. **Column exclusion — node-local handles.** Per-table named columns
   that carry RPC-generated, non-derivable identifiers are excluded:
   `gpu_allocation.allocation_id`.
3. **Address canonicalization.** Any `0x`-prefixed text value is
   lowercased before hashing (checksummed vs lowercase storage is an
   encoding artifact; live fact: stake.address on hub vs followers).
4. **Timestamp-text normalization.** ISO-8601 text with an all-zero
   fractional second part is normalized by dropping the fraction
   (`…:00.000000` ≡ `…:00`; live fact: stake.locked_until, node0 vs
   node2/hub). Non-zero fractions are kept — a real sub-second difference
   is real divergence.
5. **Row ordering.** Rows are serialized per cell with type tags
   (None/int/float/str/bytes, so `1 != '1' != b'\x01'`) and sorted by
   their canonical byte form — digest is order-independent by
   construction.
6. **Digest.** `sha256(table_name ‖ column list ‖ sorted canonical
   rows)`, truncated to 8 hex chars in reports.

## Shadow computation (soak phase)

A per-block hook computes the committed digests after each block's apply
batch and compares them against the previous shadow state — **compute
and compare, never reject**:

- After block `h` is applied, for each committed table compute the
  canonical digest from the live tables.
- Store the 13 digests + set fingerprint in a node-local shadow table
  (`shadow_side_root(block_height, fingerprint)` is enough — the per-table
  digests are recomputed on demand for forensics).
- Compare with the local previous value to detect churn, and across the
  fleet via the existing digest-compare ops runs (or a gossip field —
  see below).
- **A mismatch never affects block production, validation, or apply.**
  The shadow value is observational only until the activation height.

### Divergence counter

One monotonically increasing counter per table per node
(`side_root_divergence_total{table}`) incremented whenever the per-block
delta check detects a change pattern that the rules cannot explain —
concretely: recompute both halves of the delta and increment when two
nodes report different fingerprints for the same height. A companion
gauge exposes the last divergent height. Alert rule: any increase of the
counter pages as a consensus-risk signal even though consensus is
unaffected — the shadow is what it measures.

### Drift rule

**A table that diverges during the soak is dropped from the committed
set, never repaired.** Divergence means the canonicalization rules are
incomplete for that table's writers — adding more rules on the fly would
hide the evidence. The soak reports the dropped set; the activation
design proceeds with whatever survived. `account` can never drift (it is
already committed via `state_root`) — a divergence there is a replay
bug, not a soak result.

## Activation (consensus code — separate, gated)

After the soak shows zero unexplained divergence for the agreed window,
the shadow fingerprint becomes a committed `aux_state_root` field in the
block header at a single activation height shared with the other pending
consensus items — **V-2 (v13 governance binding), V-4 (grandfathering
guard) and BNT-1 (payload.auth admission)** — so one version bump
carries all four. Height selection is the operator's decision once the
soak data exists; the design constraint is only that all four land
behind the same `STATE_VERSION` gate.

## What this round changed

- `side-root-probe.py --canonical` now reports one `committed_set` of all
  13 tables (with `requires_rules` naming the 3 canonicalized members)
  and the fingerprint covers all 13.
- This document is the spec for the shadow hook and the activation.
