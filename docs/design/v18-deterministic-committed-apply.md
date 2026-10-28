# v18 — deterministic committed apply: version gate, `stake` leaves the committed set

**Status:** Decided by operator (Card 6 = A — fix, not waive). This document
is the **remediation spec** the implementation lane (Coder A) builds from;
activation is **not yet scheduled**. Refs #649; the confirmed-defect
finding it remediates is
[v14-aux-root-nondeterminism.md](v14-aux-root-nondeterminism.md) (commit
`1af148b18`, bc-2 incident 28 Oct 2026). Until
`STATE_TRANSITION_V18_HEIGHT` activates, the interim rule from the finding
stays in force: `LIQUIDITY_DEPOSIT`/`WITHDRAW`/`CLAIM`,
`BOND_LOCK`/`RELEASE`/`SLASH`, and consensus-path `STAKE_LOCK`/`STAKE_RELEASE`
via `/v1/staking/*` are **unsealable — do not submit**.

v18 changes committed state — stored values, therefore the aux-root
preimage — so it rides a version gate of the same shape as v14–v17. The
rule it installs, stated plainly:

> **At `block_version >= 18` the apply output is a pure function of
> (transaction, prior state, block header).** No `datetime.now(UTC)`, no
> `secrets.token_hex`/`uuid4`, no per-host value may reach a committed
> column — or any column — from the apply path.

## 1. The gate — `STATE_TRANSITION_V18_HEIGHT`

Same env→literal pattern v15/v17 followed:

- **Ship unarmed.** Add `state_transition_v18_height: int | None = None`
  beside `state_transition_v17_height`
  (`apps/blockchain-node/src/aitbc_chain/config.py:918`); `None` keeps the
  rule unarmed until the activation height is pinned fleet-wide. Prepend
  the `v18_threshold` branch at the top of the descending chain in
  `get_block_version_for_height`
  (`state/state_transition.py:959-988`; the v17 entry sits at
  `:966-968`). Both the proposer stamp (`consensus/poa.py:1272`) and
  every importer's replay version resolve through this one function, so
  the gate needs nothing else to bind.
- **Pin at activation.** The operator sets `STATE_TRANSITION_V18_HEIGHT`
  in the env files on every host together with the validator restart
  wave — a mid-rollout mixed version set rejects blocks as
  `aux_state_root` mismatches (the pin-warning comment the v15/v16/v17
  fields carry, `config.py:895-918`, applies verbatim).
- **Commit as a literal once proven.** After the activation height has
  held on main, the env value becomes a code literal default — the
  end-state `state_transition_v9_height = 30400` already shows
  (`config.py:835`). Until then the env pin is the contract.
- **Fleet watch.** `scripts/monitoring/fleet-config-check.sh` carries the
  pinned-height list at `:155-160` (last entry
  `STATE_TRANSITION_V17_HEIGHT`, `:160`); it gains
  `STATE_TRANSITION_V18_HEIGHT` in the same change so a host missing the
  pin alerts before it diverges.

## 2. Committed-set change — `stake` exits

```python
COMMITTED_TABLES_V18: tuple[str, ...] = tuple(t for t in COMMITTED_TABLES_V15 if t != "stake")
```

- The set selection is already version-keyed:
  `committed_tables_for_version` (`state/side_root_shadow.py:91-97`)
  returns `COMMITTED_TABLES_V15` (`:88`, which dropped
  `edge_node_registration` from the frozen 13-table v14 set at `:62-76`,
  `stake` at `:75`) for `block_version >= 15`. v18 adds the `>= 18`
  branch returning the 11-table set.
- **Replay safety:** sealed pre-v18 blocks keep replaying over the V15
  set byte-for-byte — the fingerprint recomputed at import
  (`sync_block_import.py:807-813`) and the `committed_fingerprint` it
  calls (`side_root_shadow.py:183-202`) both take the sealed
  `block_version`, so the change binds only new seals. This is the same
  re-scope shape v15 proved for `edge_node_registration`.
- Nothing else needs gating: no apply-path code reads or writes `stake`.
  Its only writers are the node-local queue-time RPC handlers
  (`rpc/staking.py:244-247`, wall-clock `locked_until` at `:244`) —
  `block_deltas.py:1080-1086` names the class verbatim ("written by the
  RPC handlers at queue time — outside block apply"). Those handlers stay
  as-is; at v18 their rows are service state again, so a single-node
  write can no longer fork the submitter off the fleet.

### Open question — for the operator, not decided here

Was `stake`'s committed membership ever intentional? Its only writer is
node-local and its only readers local status queries — the identical
profile to `edge_node_registration`, which v15 re-scoped as a
misclassification. If `stake` was never meant to be consensus state, v18
is a **re-scope** (correcting the V-3 table list), not a **fix**. The
same audit is owed to every remaining committed table's writer set —
`liquidity_*`, `bond`, `receipt`, `ipfs_subscription` — before the v18
set freezes. Flagged per the finding's remediation section; the
implementation lane does not answer it.

## 3. Deterministic apply rules

Every volatile write below is gated `block_version >= 18`; below the gate
the volatile path stays for replay of the (empty) v14–v17 era of these
types. Precedent for the whole class: v16 made `allocation_id`
payload-mandatory rather than minting `alloc_<uuid4>` at apply
(`state_transition.py:1782-1788`, `gpu_resources.py:150-165`) — the proof
this defect shape is fixable — and `bond_id` already arrives
payload-mandatory (`state_transition.py:2383-2385`).

### `apply_liquidity_deposit` — `state/liquidity_transition.py:53`

| today (committed bytes, per-host) | at v18 |
|---|---|
| `stake_id=_generate_stake_id()` (`:88`) → `liq_<secrets.token_hex(8)>` (`state/liquidity.py:202-203`) | `stake_id = f"liq_{tx_hash[:16]}"` — `tx_hash` is already an apply argument (`:57`) and unique per tx |
| `locked_until=datetime.now(UTC)+timedelta(days=lock_days)` (`:94`) | `locked_until = block_time + timedelta(days=lock_days)` — `block_time` is the sealed header timestamp |
| verdict gate `datetime.now(UTC) < stake.locked_until` (`:209`, withdraw) | compares against `block_time` |
| `_realize_fixed_apy` accrues over `datetime.now(UTC) - created` (`state/liquidity.py:163`) | elapsed measured to `block_time` → identical reward amounts on every host |

The handler signature (`:53-59`) carries neither `block_version` nor a
time — the dispatch (`state_transition.py:1859-1873`) passes both at v18,
the same way `block_height` already reaches the bond handler.

### `_handle_bond_transaction` — `state/state_transition.py:2358`

| today (committed bytes, per-host) | at v18 |
|---|---|
| `now = datetime.now(UTC)` (`:2390`) | `now` replaced by `block_time` for all state writes |
| `locked_until = now + timedelta(days=lock_days)` (`:2397`), stored at `:2402` (top-up) / `:2414` (new bond) | `locked_until = block_time + timedelta(days=lock_days)` |
| verdict gate `now < bond.locked_until` → release rejected (`:2434-2439`) | compares `block_time < bond.locked_until` — same verdict on every host |

`created_at`/`updated_at` (`:2403`, `:2417-2418`) may take `block_time`
too, but are already digest-excluded (`*_at` rule,
`side_root_shadow.py:110-113`) — either choice is consensus-safe; take
`block_time` for uniformity.

### Plumbing `block_time` into apply

`apply_transaction` today takes `block_version` and `block_height` but no
time (`state_transition.py:1809-1819`). Add a `block_time` parameter and
thread it from both callers:

- **Proposer:** the timestamp already reaches
  `_process_txs_sequential(session, …, next_height, timestamp)`
  (`consensus/poa.py:1964-1971`, invoked `:1220`) and is stamped into the
  header (`:1290`) — the same `datetime` object every importer will
  re-derive.
- **Importer:** `block_data["timestamp"]` is already parsed at
  `sync_block_import.py:390-394`; pass it into the
  `apply_transaction(..., block_version=…, block_height=…)` call at
  `:684-691`.
- **Remote attestation** and `compute_state_delta` replay must receive
  the same header timestamp — an attester never attests a block its own
  apply would reproduce differently (the v17 attester-parity rule).

Below v18, callers may pass `block_time=None` and the volatile paths stay
— pre-v18 history has no sealed instances of these types, so the None
branch is unreachable on replay but must exist for safety.

## 4. Acceptance checklist

- [ ] **v14–v17 replay byte-identical.** Replaying sealed history
  produces identical `committed_fingerprint` values
  (`side_root_shadow.py:183-202`) at every version below 18 — the V15
  committed set and the volatile apply paths are untouched below the
  gate.
- [ ] **v18 LIQUIDITY_DEPOSIT seals on ≥2 nodes.** The same tx applied on
  two independent nodes produces identical `liquidity_stake` rows
  (`stake_id`, `locked_until`) and identical `aux_state_root` — verified
  end-to-end, the exact test the bc-2 incident failed.
- [ ] **v18 STAKE_LOCK seals without single-node divergence.** A
  `/v1/staking/stake` lock seals and the submitter keeps importing
  subsequent blocks — the queue-time row is no longer hashed, so the
  21-Oct-`edge_node_registration`-style stall cannot recur.
- [ ] **Withdraw/release verdict parity.** A `LIQUIDITY_WITHDRAW` /
  `BOND_RELEASE` at the lock boundary returns the same verdict on every
  host (both compare `block_time`, not wall clock).
- [ ] **`fleet-config-check.sh` gains `STATE_TRANSITION_V18_HEIGHT`** in
  its pinned list (`scripts/monitoring/fleet-config-check.sh:155-160`).
- [ ] **Cross-DB `committed_fingerprint` regression pin.** The two-
  database replay harness (`tests/unit/test_v9_type_coverage_replay.py`,
  `_replay_twice` `:539-567`) gains an assertion comparing
  `committed_fingerprint` across both databases at v18 — closing the
  coverage gap the finding identified (the suite compared only verdicts,
  `account` rows and `compute_state_root_full`, never the committed
  surface, and pinned `block_version=9`).
- [ ] Activation runbook drafted following
  [v17-activation-runbook.md](../ops/v17-activation-runbook.md) before the
  height is scheduled.

## Related

- [v14-aux-root-nondeterminism.md](v14-aux-root-nondeterminism.md) — the
  confirmed finding this remediates (commit `1af148b18`); incident,
  mechanism and interim unsealable rule.
- [v9-unsigned-protocol-transfers.md](v9-unsigned-protocol-transfers.md) —
  BNT-1 → v17, the precedent for a version-gated consensus fix shipping
  unarmed then pinned.
- [v3-side-table-root-shadow.md](v3-side-table-root-shadow.md) — the V-3
  design whose committed set v18 re-scopes.
- [v1-v9-live-exercise-waivers.md](../decisions/v1-v9-live-exercise-waivers.md) —
  sweep table recording the bc-2 incident.
- [v17-activation-runbook.md](../ops/v17-activation-runbook.md) — the
  rollout procedure the v18 activation will follow.
