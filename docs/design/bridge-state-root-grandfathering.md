# V-4 — bridge_state_root activation: legacy-lock grandfathering

**Status:** design + audit tooling on main; no consensus code.
**Operator decision (2026-10-08):** activation boundary height **30000**.

## Problem

`block.bridge_state_root` is a per-block commitment over sealed
`BRIDGE_LOCK`s. The audit tool (`scripts/ops/bridge-leaf-audit.py`)
rebuilds each leaf two ways:

- **current leaf** — from the local `cross_chain_transfer` row (the data
  the seal path actually committed);
- **derived leaf** — re-deriving `lock:<transfer_id>:<amount>:<target_chain>`
  from the sealed transaction's payload, or — for GAP-47 block-scoped
  locks with an empty payload — from the signed `envelope` body.

Fleet audit (2026-10-08): every derivable leaf agrees with its sealed
header root wherever local rows exist — the commitment scheme is sound.
But **4 of 5 legacy locks carry neither payload fields nor an envelope
body** (heights ≈ 2.4k–8.3k, before the seal path recorded them), so
their leaves cannot be re-derived deterministically.

## The boundary rule

Activation must not recompute history — headers are sealed. The
operator-chosen activation height splits underivable locks into two
classes (`lock_class` in the audit tool):

- **below 30000 → `grandfathered`**: the sealed root stands as-is. The
  leaf is asserted from the sealed header, never recomputed — the legacy
  rows are unrecoverable by construction, not by corruption.
- **at/above 30000 → `missing_data` defect**: an underivable lock sealed
  after activation is an activation-blocking bug — the seal path dropped
  both payload fields and the envelope, which the activation guard must
  make impossible (write both, or fail the seal).

Boundary 30000 sits comfortably above the last underivable lock
(≈ height 8.3k) and well inside already-sealed history (head ≈ 44k), so
**no historical lock can ever flip class**: the classification of every
existing seal is frozen the moment the boundary is pinned.

## Activation path (design only — nothing of this is built)

1. Seal-path guard (consensus change, gated at the boundary): a
   `BRIDGE_LOCK` reaching the seal path at height ≥ 30000 without
   derivable payload/envelope data is rejected, not sealed.
2. The audit tool reports `missing_data` count per host; activation
   requires `missing_data = 0` fleet-wide at the boundary block.
3. The committed root continues from sealed headers — grandfathered
   leaves contribute their header value verbatim.

## Verifying today

```bash
venv/bin/python scripts/ops/bridge-leaf-audit.py --db <chain.db>
# default --boundary 30000 prints:
#   boundary 30000: derivable=1 grandfathered=4 missing_data=0
```

`--boundary 0` disables grandfathering (everything underivable becomes
`missing_data`); `--boundary <H>` evaluates an alternative height.

Fixtures: `tests/unit/test_bridge_leaf_audit.py` —
`test_lock_class_boundary_split` (the boundary edge, inclusive-above),
`test_audit_boundary_counts` (same lock shape lands grandfathered below,
defect above), `test_cli_default_boundary_is_operator_choice` (the
chosen 30000 is the CLI default).
