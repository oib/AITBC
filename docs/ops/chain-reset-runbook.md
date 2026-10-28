# Chain reset runbook — DRAFT FOR APPROVAL

> **Status: DRAFT — authorizes nothing.** This is the generalized reset
> playbook for the **next** chain cut (`<new-chain>` = chain id TBD). The
> executed instance it is distilled from is
> [bc2-reset-runbook.md](../deployment/bc2-reset-runbook.md) (bc-2 cut,
> 21 Oct 2026) — that document carries the bc-2-specific values, the
> ledger format, and the window findings this template inherits. This
> document ends at an **APPROVED / NOT APPROVED** decision, not at
> execution; every fleet-affecting step keeps the gate classes the bc-2
> runbook defines (operator-named / standing / per-item word / ungated).

## 1. Evidence preconditions — close these first

The reset is the destination of the current evidence program. These
rows must be closed **before** the freeze; each has a written home, and
the cut does not wait on unwritten outcomes.

| # | gap | evidence home | state |
|---|---|---|---|
| P1 | **v17 activation + revived-type seals** — `STATE_TRANSITION_V17_HEIGHT` armed at 8900 on all five hosts (Coder A wave, 28 Oct); activation + the first `payload.auth` seals (staking/bounty exercises) are the live proof of the BNT-1 revival | `docs/ops/v17-activation-runbook.md` §4 checks; A's exercise records | armed, in flight |
| P2 | **Coder C live sweep** — MESSAGE, AI_JOB, GPU_ALLOCATE, GOVERNANCE_*, LIQUIDITY_*, BOND_*, BRIDGE_LOCK/WITHDRAW on bc-2 | placeholder table in `docs/decisions/v1-v9-live-exercise-waivers.md` §Close-out | in flight |
| P3 | **ESCROW_FEE_SWEEP observation** — first sealed sweep on bc-2 | `docs/ops/first-sweep-observation.md` checker + the same table row | in flight |
| P4 | **BRIDGE_RELEASE exercise** — the one V-1-reserved live proof; runs only if approved | `docs/ops/bridge-release-exercise.md` (DRAFT) | awaiting approval |
| P5 | **Waiver-doc close** — V-1 record final once P1–P4 land | same file | in flight |

GOVERNANCE_EXECUTE is the known exception in P2: the bc-2 genesis
`governance_executors` keys exist nowhere in the fleet — see §2. If it
lands unexercised, the waiver table records it as authority-gated, not
green.

## 2. Authority-key custody gate — load-bearing, before height 1

**The failure this gate exists to prevent:** bc-2's genesis baked
`governance_executors` = `0xFa80…`, `0xD9CC…` — addresses whose private
keys exist in no env file, wallet, or keystore on the fleet (Coder A
recon, 28 Oct). GOVERNANCE_EXECUTE is therefore unexercisable on bc-2,
and — worse — every other authority address is only re-seat-able through
a `parameter_change` governance action that *itself needs an executor
signature*. Lost executor keys on a produced chain mean the authority
set can never be moved again.

**Rule for `<new-chain>`:** every genesis-baked authority value is
backed by a recorded key **or** a signed possession proof **or** an
explicit dead-key decision — verified *before* the genesis build
consumes the values (the treasury `personal_sign` proof pattern from
bc-2's A8/C4 is the shape: `check-alloc-file.py --treasury-proof`).

Genesis parameters on bc-2 (rehearsal `_parameters`, same set expected
next reset):

| parameter | signs for | if the key is lost |
|---|---|---|
| `governance_executors` (list) | GOVERNANCE_EXECUTE — every `parameter_change`, i.e. the only path that re-seats the rest | the authority set freezes permanently; governance is cosmetic |
| `bond_slash_authority` | BOND_SLASH emissions (coordinator-api `BOND_SLASH_PRIVATE_KEY` must match) | slashing dead; bonds never releasable by penalty |
| `bridge_release_authority` | every `BRIDGE_RELEASE`/`BRIDGE_REFUND` credit | cross-chain releases dead |
| `escrow_settlement_authority` | ESCROW_RELEASE / ESCROW_REFUND | escrow settlement dead |
| `escrow_fee_recipient` | receives swept fees | spendable-only loss — funds land unspendable until re-seated |
| `bridge_validators` rows | multisig proof set for releases | release confirm can't reach threshold |

Custody checklist per row (fill before genesis build): **key location**
(env name + host, wallet name, or "off-fleet operator custody") and
**proof method** (signed challenge / import check). A value marked
"dead key" is a named operator decision recorded in this runbook's §8 —
never an accident discovered post-seal.

## 3. Rehearsal machinery — what already exists and what it proves

All scratch-only: keys minted fresh under `--scratch`, deleted with
teardown, never derived from fleet material; nothing touches live
units, env files, ports, data dirs, wallets or keystores.

- **`scripts/reset-harness/rehearsal.py`** — five scratch node processes
  (`systemd-run` transient units, per-instance data dirs, loopback ports,
  cgroup caps): 4 proposers + 1 follower. Builds genesis via
  `scripts/ops/build-genesis.py` + `verify-genesis-root.py`, then runs
  acceptance phases: identical block-0 hash, proposer rotation,
  attestation quorum ≥2 (fleet runs `PBFT_CONSENSUS_ENABLED=false`),
  restart/rejoin, stopped-proposer skip, fresh service stores,
  gates1 golden replay, plus fault phases — `stall` (2 validators down:
  freeze, no fork, resume), `resync` (corrupt store → wipe → re-init →
  resync), `alloc-fix` (post-seal corrective treasury transfer), `fork`
  (asymmetric partition → deterministic heal), `gossip` (attestation
  plane degradation), `untrusted` (TRUSTED_PROPOSERS refusal).
  Live-host protection: refuses on load/memory budget breach and on a
  second concurrent run.
- **`scripts/reset-harness/rollback.py`** — the pre-PONR rollback
  rehearsal: every cut step reverted in order; byte-equal restore from
  both the `.pre-reset` copies and a separate backup; the bare-restart
  trap documented (old code stalls head −1 without a hub; current code
  refuses at `consensus/poa.py` — "Genesis file required"); fresh-start
  detection (`ActiveEnterTimestamp`/`ExecMainStartTimestamp`/`MainPID`);
  frozen-head resume; the partial-start proof (one validator up →
  `max(height)=0`, the point cannot be crossed early).
- **`scripts/ops/post-cut-verify.py`** — one read-only post-cut sweep,
  manifest-driven so the same code runs against the rehearsal harness
  and the live fleet: genesis sha256 ×5, heads equal and moving, env-set
  landed on every carrier, bridge pause at the admission gate, balances
  match allocations, units fresh, no old-chain stores under `data/`,
  alerts/pages/mempool checks. The only write-shaped probe
  (bridge-lock POST) is off by default and runs under `--probe` on the
  operator's line.

## 4. The cut — sequence (generalized from bc-2 §B–§D)

Window order. Every row carries its gate class from the bc-2 gate table.

1. **FF — code convergence**: the reset release deploys *with* the cut —
   first window action, not ahead of it (operator ruling on bc-2; re-decide per reset).
2. **Freeze** (stop accepting writes): timers suspended → faucet /
   coin-request intake parked → market + exchange stopped →
   `BRIDGE_LOCKS_PAUSED=true` on every carrier → coordinator-api stopped
   → head + `state_root` recorded ×5 **and drain zero-checks re-run**
   (a new row since the drain is a new drain item — stops the cut).
3. **C1 stops**: services in dependency order per the host-inventory doc.
4. **C2 `.pre-reset`**: every chain + service store moved to
   `/var/lib/aitbc/.pre-reset-<date>/` — sibling of `data/`, never inside
   it; no deletion.
5. **C3 env apply**: the reset env-set doc applied to **every file
   holding each name** (names repeat across files), plus the `Environment=`
   sweep of unit drop-ins and the *absence* sweep for the old chain id —
   both 21-Oct findings.
6. **C4 genesis**: scratch build → `verify-genesis-root.py` → per-host
   `sha256sum` → distribute `genesis.json` into `data/<new-chain>/` ×5.
   Custody proofs (§2) consumed on the build host, `0600`, deleted after.
7. **C5 validators up**: all validator node units up in one short window
   (nothing seals before a second validator joins — rehearsed), followers
   after, customer node last; rpc units with or right after the node leg
   (mesh-mode validators need rpc for attestation topics).
8. **C6 service stores fresh**; **C7 checks**: heads advancing, proposer
   rotation, per-block quorum ≥2, read paths answering for the new chain,
   `data/` holds no old-chain store, alerts quiet.
9. **PONR**: first block above 0 sealed with attestations — after it, the
   abort table no longer applies; abandoning is a second reset-class event.

## 5. Abort / rollback

| reached | action |
|---|---|
| freeze only | unpause every intake — downtime only |
| C1 stopped | restart old units/env — downtime only |
| C2 moved | **explicit `.pre-reset` move-back first** — a bare restart on empty dirs restores nothing (the rehearsed trap) |
| C3 env applied | revert env edits + restarts |
| C4 distributed | delete `data/<new-chain>/` files — old chain untouched |
| C5 started, nothing sealed (`max(height)=0` ×all) | stop units → delete files → revert env → move stores back |
| first seal | **point of no return** — no abort |

Post-PONR: deliberate-halt posture for fleet-wide rejection (capture
evidence, don't restart to unstick); a single straggler is rebuilt, not
matched.

## 6. Post-cut

- Soak window before anything is deleted (bc-2: 3 days); `.pre-reset`
  and offline backups retire on a per-item operator word after it.
- `post-cut-verify.py` green; owed-items sheet (bc-2: `bc2-post-cut-owed.md`)
  holds the consumer flips, timer restores, funding writes, bridge
  unpause — each its own gated step.
- `TRUSTED_PROPOSERS` operating rule: any later validator-set change
  updates the list on every host in the same change.
- No write to a committed side-table outside block apply (21 Oct
  `EDGE-REG-CONSENSUS-1` rule — CI guard `test_rpc_committed_writes.py`).

## 7. What rehearsal cannot prove (carried forward from bc-2 §G)

Real systemd units vs transient scopes; real store sizes; live-path
writes under `/var/lib/aitbc`; the five-host serial spread; offline
backups; drain writes; the website render. The final rehearsal at the
release-candidate commit (`RESET-REHEARSAL-N`) re-proves the same scope
on the exact reset code — it does not shrink this list.

## 8. Open decisions — operator

- `<new-chain>` chain id, block-0 parameters, and whether this reset is
  the v1 cut or another testnet-era one (changes the rotation answer:
  bc-2 was "no rotation — not a v1 bc reset").
- Genesis allocation set + treasury custody (same proof pattern or new).
- **Custody answers per §2 row** — who records/holds each authority key;
  whether `governance_executors` get freshly generated, recorded keys
  this time.
- Validator set: keep the current four, or rotate (the deferred
  fleet-wide rotation is scheduled "for release v1").
- Rehearsal scope + count; whether `RESET-GENESIS-LIVE-1` (a `--live`
  genesis write path) stays parked.
- Soak length; window date; maintenance-notice lead.

## 9. Operator sign-off

- [ ] §1 evidence rows closed (or explicitly waived for this cut)
- [ ] §2 custody checklist complete — every genesis authority has a
      recorded key, a proof, or a named dead-key decision
- [ ] Rehearsal + rollback rehearsal green at the release-candidate commit
- [ ] **Decision: APPROVED / NOT APPROVED**

    Operator: ______________  Date: __________  Notes: ______________
