# v14 aux-root nondeterminism — apply-time volatile columns fork the committed fingerprint

**Status:** Open — confirmed live consensus defect (bc-2, 28 Oct 2026);
remediation pending operator decision — fix apply-time determinism behind a
new version height (candidate v18), vs formally waive LIQUIDITY_\*/BOND_\*
at the current versions. A second live-verified surface — single-node
committed rows (§ "Mechanism 3") — additionally makes
`STAKE_LOCK`/`STAKE_RELEASE` via `/v1/staking/*` unsealable at
**v16/v17 — retracted at v18 (9600)**. The interim rule below is in force until decided:
the six LIQUIDITY_\*/BOND_\* types plus consensus-path `STAKE_*` are
unsealable — do not submit. The incident is recorded in
the sweep table of
[v1-v9-live-exercise-waivers.md](../decisions/v1-v9-live-exercise-waivers.md).

## The mechanism — what the aux-root commits

v14 (V-3) made the side tables consensus-critical. At `block_version >= 14`
the proposer flushes the post-apply session and digests the committed set —
`COMMITTED_TABLES` (13 tables at v14) / `COMMITTED_TABLES_V15` (12 tables
from the v15 height), `state/side_root_shadow.py:62-88` — into
`aux_state_root` on the header (`consensus/poa.py:1271-1277`, bound into the
block hash at `:1280-1281`). Every importer recomputes the same fingerprint
over its own committed tables and **rejects** the block on mismatch
(`sync_block_import.py:807-828` — `sync_aux_root_rejected_total`,
"BLOCK REJECTED").

The fingerprint is a sha256 over `table=digest;` pairs
(`committed_fingerprint`, `side_root_shadow.py:183-202`); each per-table
digest hashes row content over all columns minus two exclusion rules:

- every column ending in ``_at`` — locally stamped wall-clock values
  (`_is_local_stamp`, `:110-113`);
- `CANONICAL_EXCLUDED_COLUMNS` — today only `gpu_allocation.allocation_id`
  (`:118-121`, "Live fact: gpu_allocation.allocation_id differs on every
  host").

So a stored value escapes the block commitment **only** if it is an `*_at`
timestamp or explicitly excluded. `locked_until` and `stake_id` satisfy
neither rule — every apply-time value they hold is consensus bytes. The
codebase already names this class in the fleet-digest spec
(`state/block_deltas.py:276-317`):

>   * apply-time nondeterministic fields: ``locked_until`` (bond and
>     liquidity stakes set it from apply-time ``now()``), ``stake_id`` and
>     ``allocation_id`` (random tokens generated per apply when the payload
>     omits one — ``secrets.token_hex``/``uuid4``), ``unbonding_at`` —
>     identical inputs still produce different stored values on each node.

That carve-out (`VOLATILE_DIGEST_COLUMNS`) protects only the *fleet digest
tooling*; the committed aux-root has no equivalent — which is exactly the
gap that fired on bc-2.

## Which apply paths stamp what

| tx type | apply entry | apply-time nondeterminism | committed column(s) |
|---|---|---|---|
| LIQUIDITY_DEPOSIT | `apply_liquidity_deposit`, `state/liquidity_transition.py:53` (dispatch `:1859-1863`) | `stake_id=_generate_stake_id()` (`:88`) → `liq_<secrets.token_hex(8)>` (`state/liquidity.py:202-203`); `locked_until=datetime.now(UTC)+timedelta(lock_days)` (`:94`) | `liquidity_stake.stake_id` (PK) **and** `locked_until` — both hashed |
| LIQUIDITY_WITHDRAW / CLAIM | `liquidity_transition.py:186` / `:111` (dispatch `:1864-1873`) | verdict gated on wall clock — `datetime.now(UTC) < stake.locked_until` (`:209`); `_realize_fixed_apy` accrues over `now() - created` (`liquidity.py:163`) → per-host reward amounts | divergent `liquidity_stake` / `liquidity_pool.reward_per_share` / `liquidity_distribution` rows — plus `account` balances, i.e. the state root too |
| BOND_LOCK (+ top-up) | `_handle_bond_transaction`, `state/state_transition.py:2358` (dispatch `:2085-2088`) | `now = datetime.now(UTC)` (`:2390`), `locked_until = now + lock_days` (`:2397`), stored at `:2402` / `:2414` | `bond.locked_until` — hashed |
| BOND_RELEASE / SLASH | same | verdict gated on `now < bond.locked_until` (`:2434-2439`) — accept/reject can split across hosts | `bond` row state |
| GPU_ALLOCATE (pre-v16) | `state_transition.py:2628-2638` | `alloc_<uuid4>` fallback when the payload omits the id | `gpu_allocation.allocation_id` — **already remediated**: digest-excluded (`side_root_shadow.py:118-121`) and payload-mandatory at v16 (`state_transition.py:1783-1785`, `gpu_resources.py:157-165`) — the proof this class is fixable |

Wall-clock stamps that do end in `_at` (`pool.updated_at`,
`pool.last_distribution_at` at `liquidity.py:128-129`, `created_at`
defaults) are excluded by rule 1 and harmless to the commitment. The two
verdict gates are the sharpest edge of the defect: they are not only "same
tx, different stored bytes" but potentially "different verdict on different
hosts" — a withdraw or release that passes on the proposer can fail on an
importer a few seconds later.

## Mechanism 3 — single-node committed rows (queue-time RPC writes)

The apply-time class above needs a *proposed* transaction to fork. A
sharper variant needs none at all: **`stake` is a committed table whose
only writers are node-local RPC handlers.** At queue time — outside block
apply — the revived staking handlers write their domain row on the
serving node only:

```python
# rpc/staking.py:244-247 (the /v1/staking/stake queue path)
locked_until = datetime.now(UTC) + timedelta(days=lock_days)
stake = Stake(chain_id=chain_id, address=address, amount=amount,
              locked_until=locked_until, status="active")
session.add(stake); session.commit()
```

`block_deltas.py:1079-1087` states the class verbatim: ``stake``,
``agent_stake`` and ``bounty_contract`` rows "are written by the RPC
handlers at queue time — outside block apply, so the delta journal can
never capture them." `table_digest` (`side_root_shadow.py:156+`) hashes
the table's full contents into the committed fingerprint — and `stake`
sits in `COMMITTED_TABLES` (`:75`) while `agent_stake` and
`bounty_contract` do not. The handler's own comment marks the defect's
age: "The stake row is not part of the state root, so writing it here
is safe" (`rpc/staking.py:238-243`) — true for the v9 state root, but
expired the moment v14 started committing the side tables.

**Consequence (verified end-to-end by Coder A):** any sealed
`STAKE_LOCK` via `/v1/staking/stake` leaves the *submitter's*
fingerprint divergent — the serving node hashed a row nobody else has —
so it rejects the very block that sealed its own lock. A single-node
fork-out: 4/5 quorum holds, no liveness deadlock, but the submitter
stalls until the row is deleted and the node rejoins (the exact 21 Oct
12:14 `edge_node_registration` recovery). `STAKE_RELEASE` via
`/v1/staking/unstake` mutates the same committed row → same outcome.

**Precedent:** this is the misclassification v15 already fixed for
`edge_node_registration` — `COMMITTED_TABLES_V15` drops it
(`side_root_shadow.py:77-88`, comment: "Its committed membership was a
misclassification: any successful register call diverged the
fingerprint on exactly one node — 21 Oct 12:14 incident — node2 stalled
at 118 until the row was deleted"). `stake` is the identical case:
node-local queue-time writer, no apply-path reader or writer.

## The incident — bc-2, 28 Oct 2026

- A `LIQUIDITY_DEPOSIT` submitted during the live type-coverage sweep
  reached every mempool and was proposed at ~height 8705.
- Each validator applied it and recomputed the committed fingerprint:
  `liquidity_stake.stake_id` drew a fresh `liq_<16 hex>` per host and
  `locked_until` stamped each host's wall clock → every node computed a
  different `aux_state_root`.
- Attestation/import verification rejected the candidate on aux-root
  mismatch (`sync_block_import.py:813-828`) → the fleet split 3-vs-2 →
  liveness deadlock at 8705/8706: no candidate block could carry a quorum.
- Recovery: delta-journal `revert_losing_segment`
  (`state/block_deltas.py:935`) on node1+node2 — the poison tx was dropped,
  **not** requeued (requeueing would re-poison the next proposal) — plus
  the validator rejoin runbook → clean quorum at 8706 (`0x14b9461e…`).
- Fleet verified healthy at ~8736.

## Why the replay suite did not catch it

`tests/unit/test_v9_type_coverage_replay.py` replays every waived type —
including `LIQUIDITY_DEPOSIT` and all three `BOND_*` — through the real
`apply_transaction`, twice, on two identically-seeded sqlite databases
(`_replay_twice`, `:539-567`). It is green today because the compared
surface is narrower than the committed surface:

1. The assertions are the verdict, the `account` rows (`:618-620`) and
   `compute_state_root_full` (`:621-622`) — which reads only
   `SELECT address, balance, nonce FROM account`
   (`state/state_root_utils.py:31-34`). `liquidity_stake`, `bond`,
   `liquidity_pool` rows are never compared; `committed_fingerprint` is
   never called.
2. The replay pins `block_version=9` — five versions below the v14
   aux-root era, so a side-table diff would have no committed consumer in
   the test even if it were visible.
3. Fundamentally, divergence needs **>1 node** each independently applying
   the same transaction and then committing to a shared value. Wall-clock
   and `secrets.token_hex` writes are deterministic *within* one node —
   each host's own state is coherent and self-consistent; the hosts only
   disagree with each other. A single-process double-apply can only ever
   show a node agreeing with itself.

Cheap coverage fix: the two-database harness is exactly the right
substrate — asserting `committed_fingerprint` equality across the two
databases (`side_root_shadow.py:183-202`) closes the class, not just these
types.

## Remediation sketch — candidate v18

The fix changes committed state (stored values, therefore the aux-root
preimage), so it needs a version gate, same shape as v14–v17:

- **Deterministic ids** — `stake_id = f"liq_{tx_hash[:16]}"`: `tx_hash` is
  already an apply argument (`liquidity_transition.py:57`) and unique per
  tx. `bond_id` already arrives via payload (deterministic) — leave as-is.
  v16 making `allocation_id` payload-mandatory is the proven pattern.
- **Block-header time, not wall clock** — plumb the block timestamp into
  apply (`block_height` is already threaded — `_handle_bond_transaction`
  `:2368`); `locked_until = block_time + timedelta(days=lock_days)`;
  `_realize_fixed_apy` measures elapsed to `block_time`; the withdraw /
  release verdict gates compare against `block_time`. Headers already carry
  `timestamp` (`poa.py:1281-1290`), so every node recomputes against the
  same value.
- **Version gate** — `STATE_TRANSITION_V18_HEIGHT` alongside
  `state_transition_v17_height` (`config.py:918`) plus the
  `get_block_version_for_height` chain (`state_transition.py:959-988`).
  Below the gate behavior is unchanged — no LIQUIDITY_\*/BOND_\* tx has
  ever sealed at v14+, so nothing historical depends on the volatile path;
  the gate exists so a mixed-version fleet never disagrees. Fleet pin and
  `fleet-config-check.sh` watch per the v17 rollout
  ([v17-activation-runbook.md](../ops/v17-activation-runbook.md)).
- **Regression pin** — the cross-DB `committed_fingerprint` assertion above.

### And the committed-set re-scope (mechanism 3)

`stake` exits the committed set behind the same v18 gate —
`COMMITTED_TABLES_V18 = COMMITTED_TABLES_V15` minus `"stake"`. The set
selection is already version-keyed (`committed_tables_for_version`,
`side_root_shadow.py:91-97`), so pre-v18 blocks keep replaying over the
old set byte-for-byte — the same shape as the v15
`edge_node_registration` re-scope. No apply-path code reads or writes
`stake`, so nothing else gates on it.

The deeper question the fix should pose: if `stake`'s committed
membership was a misclassification from the start (its only writer is
node-local and its only readers are local status queries), is the table
needed in consensus at all — or is the v18 change less a *fix* than a
*re-scope* admitting the membership was wrong? The same audit applies
to every remaining committed table's writer set: `liquidity_*`, `bond`,
`receipt`, `ipfs_subscription` each deserve a "who writes this, and
where" pass before v18 freezes the next set.

## Interim rule — unsealable types (RETRACTED at v18)

> **29 Oct:** all entries below lifted — the v18 deterministic-apply
> bundle activated cleanly at 9600 (zero divergence); see
> [v18-activation-runbook](../ops/v18-activation-runbook.md). The
> history stays for the record; per-type seals are tracked in the
> waiver table and coverage ledger.

`LIQUIDITY_DEPOSIT`, `LIQUIDITY_WITHDRAW`, `LIQUIDITY_CLAIM`,
`BOND_LOCK`, `BOND_RELEASE`, `BOND_SLASH` were **unsealable** at current
state-transition versions, and `STAKE_LOCK`/`STAKE_RELEASE` via
`/v1/staking/*` were **unsealable at v16/v17**
(mechanism 3): do not submit them. Admission validates payload
shape only (`state_transition.py:1358-1367`) — nothing stops a submitted tx
reaching a proposer, and any proposed instance computes a different
aux-root on every host and forks the fleet; the staking variant does
not even need a proposal — the queue-time write alone diverges the
submitter.

- WITHDRAW/CLAIM additionally need a sealed deposit position — none can
  exist.
- BOND_RELEASE/SLASH need a sealed active bond — none can exist.
- BOND_SLASH is doubly blocked: `_bond_slash_authority`
  (`state_transition.py:162-195`) resolves the `bond_slash_authority` chain
  parameter height-scoped, and the key is absent fleet-wide on bc-2 → apply
  returns "no slash authority configured" (`:2459-2461`) before the bond
  lookup is even reached.
- **`/v1/agent-staking/*` STAKE_* remains exercisable** — `agent_stake`
  is not a committed table, so its queue-time rows stay node-local by
  design (same for `bounty_contract`). Only the `/v1/staking/*`
  consensus-path plays are blocked.

## Related

- [v1-v9-live-exercise-waivers.md](../decisions/v1-v9-live-exercise-waivers.md) —
  sweep table; the LIQUIDITY_\* and BOND_\* rows record the incident.
- [v3-side-table-root-shadow.md](v3-side-table-root-shadow.md) — the V-3
  design the aux-root committed.
- [v9-unsigned-protocol-transfers.md](v9-unsigned-protocol-transfers.md) —
  BNT-1 → v17, the precedent for a version-gated consensus fix.
- [chain-reset-runbook.md](../ops/chain-reset-runbook.md) — fork/liveness
  recovery mechanics.
- [v17-activation-runbook.md](../ops/v17-activation-runbook.md) — the
  version-gate rollout procedure a v18 activation would follow.
