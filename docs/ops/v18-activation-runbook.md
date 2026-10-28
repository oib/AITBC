# v18 activation runbook — `STATE_TRANSITION_V18_HEIGHT` (DRAFT)

> **Status: DRAFT — written ahead of implementation.** The v18
> remediation is specced in
> [v18-deterministic-committed-apply](../design/v18-deterministic-committed-apply.md)
> (Refs #649) and decided by operator Card 6 = A. The implementation
> is shipped and the pin wave is done: `STATE_TRANSITION_V18_HEIGHT=9600`
> armed fleet-wide; activation pending at head 9600 — §4 post-checks
> apply then.
>
> **WARNING — sharper than v17:** v18 changes the *committed set*
> (`stake` exits `COMMITTED_TABLES_V18`). A mixed fleet at a ≥v18 block
> does not just disagree on apply rules — it digests **different table
> sets** for the same block → guaranteed `aux_state_root` mismatch.
> The identical-pin-across-all-validators requirement is absolute here;
> there is no graceful mixed window.

Fleet: node0, node1, node2, hub1, hub — chain `bc-2`, RPC on
`127.0.0.1:8202`, chain DB at `/var/lib/aitbc/data/bc-2/chain.db`. The
island `bc-2-island-1` runs transitions=1 and is out of scope for this
pin (it already applies v18-equivalent rules from genesis — **DRAFT-impl**,
confirm its heights once the fix lands).

## 1. What activates at 9600

- Apply becomes deterministic for `LIQUIDITY_*`/`BOND_*`:
  `liq_<tx_hash[:16]>`-style ids, `locked_until` derived from the block
  timestamp — apply output = f(tx, prior state, block header).
- `stake` exits the committed set (`COMMITTED_TABLES_V18`) — the
  `/v1/staking/*` queue-time writes stop forking the submitter.
- The unsealable list from
  [v14-aux-root-nondeterminism](../design/v14-aux-root-nondeterminism.md)
  lifts: LIQUIDITY_*/BOND_* and consensus-path STAKE_* become
  exercisable again.
- Nothing user-visible flips: no RPC surfaces change, no 410 gates.

## 2. Pre-checks (before setting anything)

- `git log --oneline -1` ≥ the implementation commit on **all five**
  hosts — the apply changes and `STATE_TRANSITION_V18_HEIGHT` plumbing
  must be identical everywhere before any pin is set.
- `fleet-config-check.sh` run — env drift clean; the checker already
  enumerates the pin name (spec checklist; B adds it in the impl
  commit).
- All five nodes producing/attesting normally — no open seal gaps.
- Replay gate green on the impl branch: the cross-DB
  `committed_fingerprint` assertion + v14–v17 replay byte-identical
  (the impl's acceptance checklist items).
- 9600 was chosen with headroom — the restart wave (§3) plus slack; the
  wave completed before 9600 seals.

## 3. Set + restart wave

1. Write `STATE_TRANSITION_V18_HEIGHT=9600` into
   `/etc/aitbc/blockchain.env` on all five hosts (own line; no inline
   comment on the assignment). Verify the file parses identically ×5
   via the drift check's env section.
2. Confirm `STATE_TRANSITION_V18_HEIGHT` reads back identical on all
   hosts before restarting **anything** — §5(a) is why.
3. Serial restart, one host at a time — the v17 wave order works:
   **node0 → hub1 → node1 → node2 → hub** (the completed 8900 order),
   restarting `aitbc-blockchain-node` **and** `aitbc-blockchain-rpc`
   on each.
   - Per host: service up + head advancing + attestations flowing
     before the next host. Never two validators in one window.
4. After the wave: every node's process env shows the pin and the
   drift check's env-diff line is `9600` ×5.

## 4. Post-checks (at/after 9600)

- **Version stamps:** blocks from 9600 carry `block_version=18` on
  every host (sqlite `block`/`block_metadata` on any two nodes must
  agree — the proposer stamps, importers accept).
- **Aux-root divergence watch — the canary:** watch
  `block_version_stamp_mismatch_total` and the sync reject metric
  (`sync_aux_root_rejected_total`) across the first ~20 blocks post-9600.
  Any nonzero reject counter means a host resolved a different
  committed set — find which host's fingerprint diverged and pull it
  from the set before it poisons attestations. (This is the check the
  v17 window ran for `payload.auth`; here it is THE check.)
- **Determinism proof seals — the first post-v18 exercises:** a
  `LIQUIDITY_DEPOSIT` + a `BOND_LOCK` submitted post-9600 must seal
  with **identical aux roots on ≥2 hosts** (the defect's exact inverse
  — verify `aux_state_root` equality across hub/node1/node2 rather
  than trusting the seal).
- **Consensus-stake proof:** a `/v1/staking/stake` call post-9600 must
  NOT fork the submitter — the node's head keeps advancing (the
  single-node committed-row inverse).
- Fleet: all five producing/attesting; heads advancing past 9600+n.

## 5. Failure modes

### (a) Heads stop on ALL hosts at 9600

A validator's pin is missing/different → it resolves the V15 committed
set against a V18 block (or vice versa) → aux-root mismatch → the
candidate dies at attest. Fix the pin on the wrong host and restart —
the wave rule exists for exactly this.

### (b) ONE host diverges/rejects at 9600

Same class as v17's stamp mismatch, but committed-set-shaped: the
host's fingerprint covers a different table set. `sqlite … chain.db`
its aux computation vs a known-good host; pull it from attestation
until re-pinned + restarted + resynced.

### (c) A pre-v18 `LIQUIDITY_*`/`BOND_*` tx lands post-9600

Harmless to the ledger — admission still accepts the shapes; the v18
apply just handles them deterministically. The old volatile path is
version-gated, not deleted.

### (d) A revived-stake play submitted *before* 9600

Any `/v1/staking/*` queue-time write before 9600 still hits the old
committed `stake` table — same single-node fork-out as v17. Keep the
unsealable rule in force until 9600 + a few sealed blocks.

### (e) Pin drift discovered mid-wave

Stop the wave immediately (before the next validator), restore the
earlier env value on touched hosts, restart them back, re-run the
pre-check. v18 has no soft-divergence margin — a partial fleet is a
split fleet.

## 6. Rollback — what can and cannot be undone

- **Before 9600:** full rollback — remove the pin ×5 + the same
  serial restart wave; nothing has activated.
- **After 9600:** the pin is permanent for replay — removing it
  breaks replay of the v18-stamped blocks (same shape as v17). The
  only post-activation rollback is a chain reset or a new version
  that re-includes `stake` — neither is a routine op.

## 7. Literal-pin follow-up

After the activation height holds on main, commit
`state_transition_v18_height` as a code literal (the
`13f72546f`/v17 pattern — env → literal once proven) and remove the
bc-2 env pins; islands and new chains keep env pins (`=1`).

## 8. Operator sign-off

- [ ] Impl commit recorded in §2 and identical on all five hosts
- [ ] 9600 set and verified identical ×5 before any restart
- [ ] Wave order agreed; quorum held between hosts
- [ ] v18 stamps land from 9600; aux-reject canary clean
- [ ] LIQUIDITY_DEPOSIT + BOND_LOCK seals with identical aux roots
- [ ] `/v1/staking/stake` play post-9600 does not fork the submitter
- [ ] Unsealable-list retraction folded into the finding doc +
  waiver table + scenarios README
- [ ] Literal-pin follow-up scheduled

**Decision:** APPROVED / NOT APPROVED — ________ (date, initials)

*Last updated: 2026-10-28 — DRAFT pending v18 implementation landing*
