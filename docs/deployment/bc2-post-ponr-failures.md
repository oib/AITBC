# bc-2 Post-PONR Failure Modes

Reset planning only — nothing here is authorized. This doc picks up where
the runbook's §D abort table ends: once the first block is sealed on
bc-2 (**PONR**), no abort row exists, and failure handling becomes the
modes and decision tree below.

## Mechanics primer

Every multi-validator block needs its proposer plus **2 remote
attestations** — production stalls below 3-of-4 reachable validators.
Symmetric loss **stalls, never forks**; a fork needs an *asymmetric*
partition where attestation gossip flows but block gossip/pull does not.
Attester lock, deterministic fork choice, freshness checks, and the delta
journal are the auto-heal layers. The two rules the branches below lean
on: a validator's `P2P_BIND_HOST` must be a fleet-reachable address —
`127.0.0.1` silences its gossip without stopping the unit — and node
units run `GOSSIP_BACKEND=mesh`; a rejoin is an env drop-in restart,
never a bare `Environment=` edit.

## Failure modes

| mode | how it shows | still intact | lost | rehearsal status |
|---|---|---|---|---|
| **M1 one validator down** (crash, env typo, key) | `ServiceDown`/`AitbcSystemdUnitFailed`; `SELECT DISTINCT proposer` misses one; heads still advance (~1 extra round at its slot) | everything — chain produces on 3-of-4 | nothing but cadence | **rehearsed** — `rejoin` + `skip` |
| **M2 ≥2 validators down → stall** | heads equal + frozen fleet-wide; `ChainHeadStalled`; journal `got 0 attestation(s), need 2` | everything sealed; **no fork forms** | liveness only — time | **rehearsed** — `stall` (#351) |
| **M3 fork** (asymmetric partition) | `ChainDiverged`; same height, different hashes; `sync_fork_*` counters; `ForkOrphanedTxLost` if a user's tx is on the loser | majority branch; journal covers non-empty losers | orphaned txs on losing segment (requeue under full admission; rejected ones gone — by-hand reconcile) | **rehearsed** — `fork` (#351) |
| **M4 bad allocation found post-seal** | user report; `/rpc/state/snapshot` figure wrong vs alloc file; verifier `alloc-classes` FAIL | the chain itself — blocks stay valid | nothing yet — depth compounds it | **rehearsed** — `alloc-fix` (#351) |
| **M5 wrong env on one host** (`CHAIN_ID`/`TRUSTED_PROPOSERS` slip) | `env-pins` FAIL in verifier; that host refuses blocks | the other 4 | that host's participation until fixed | **rehearsed** — `untrusted` |
| **M6 quorum loss without death** (gossip degradation — incl. hub's `P2P_BIND_HOST=127.0.0.1` restart trap) | attestation count <2 trending; the victim's attestation absent from `block_metadata.attestations` + the refusal mark at its slot. **No loaded alert fires today** — `AttestationValidatorSilent`/`AttestationArrivalDegraded` are committed in `aitbc_rules.yml`, but the `attestation-arrival` exporter has no systemd timer anywhere, so no `aitbc_attestation_*` series exists for the loaded rules to evaluate; the verifier's `quorum-sweep` (≥2 attestations per block) and `proposer-rotation` both stay green under one silent validator. Detection today is the verifier sweep and journal marks | sealed history | liveness drift toward M2 | **rehearsed** — `gossip` (#351): on scratch no alert tier fires (no prometheus there); the evidence is the refusal mark, the fallback-covered victim slot, the victim's attestation absent from new seals, and recovery on restore |
| **M7 corrupt store on one host** | unit crash-loop; sqlite/journal errors; `ActiveEnterTimestamp` churn | other hosts' copies; `.pre-reset` is the **old** chain — cannot restore bc-2 | that host's bc-2 db (recoverable via resync) | **rehearsed** — `resync` (#351) |
| **M8 second reset** (last resort, not an abort) | operator decision after M4-class finding or unrecoverable fleet | allocation file + confirmations carry verbatim; harness + runbook procedure re-proven | all sealed bc-2 history; every post-seal artifact (F4, TOPOLOGY record, consumer flips) redone | n/a — decision class; the runbook procedure itself is the evidence |
| **M9 bridge/EVM side** (Sepolia contract, Safe, signer keys) | not a bc-2 failure: `BRIDGE_LOCKS_PAUSED` stays `true` until `SEPOLIA-REDEPLOY-1`; any contract/Safe finding surfaces in that parked row's prep | bc-2 unaffected — the deposit path is the watched EOA + payout wallet | nothing on-chain | n/a — parked row `SEPOLIA-REDEPLOY-1` |

> Sepolia EVM signer rotation is a **separate operator-owned action** tied
> to `SEPOLIA-REDEPLOY-1`: **no key rotation happens in this reset**, locks
> stay paused until then, and no coder touches those keys.

## Options per mode

Risk order. **Bold** = the operator's own named line.

| mode | options |
|---|---|
| M1 | fix env + **restart unit** (rejoin procedure — the drop-in form, *not* bare `Environment=`); catch up via sync; if store corrupt → resync from peer |
| M2 | **restore one validator** (rejoin procedure); heads stay equal — no resync; if a host is unrecoverable → operator decides degraded-3 vs M8 |
| M3 | **wait one round window first** — fork choice + attester lock settle it; escalate only if loser predates journal or revert root-check fails → **manual**: delete diverged rows + `sync_cli --source https://<peer>` |
| M4 | (a) **corrective treasury transfer** — the corrective write is a chain transaction from the treasury key, the operator's own action and line; no coder signs it — it can create a missing account row; (b) M8 if the error invalidates the chain's purpose |
| M5 | env fix + **restart** + rejoin; verifier `env-pins` re-run proves it |
| M6 | restore gossip: check `P2P_BIND_HOST`/`GOSSIP_BACKEND=mesh` (the rules in the primer above); **restart** |
| M7 | **delete `data/bc-2` on that host + re-init from genesis.json + resync** (deletion + restart — operator line) |
| M8 | rerun the whole runbook at a new chain id, chosen then; `.pre-reset` procedure applies to `data/bc-2` the same way; **never** part of §D |
| M9 | `SEPOLIA-REDEPLOY-1` scope — the unpause itself is `BC2-UNPAUSE-1`'s gated sequence; signer rotation is the operator's own action inside the redeploy step |

## Two-minute decision tree

```
read: post-cut-verify head-equality + /rpc/head ×5          (~30 s)
├─ heads equal + advancing → not consensus. Check env-pins,
│   proposer-rotation row (missing validator → M1), unit rows.
├─ heads equal + FROZEN → M2 stall.
│   read: journal "got N attestation(s)" + is-active ×4 validators
│   → <3 alive → restore one via rejoin procedure (operator line)
│   → all alive → M6 gossip: P2P_BIND_HOST on hub, GOSSIP_BACKEND=mesh
├─ same height, DIFFERENT hashes → M3 fork.
│   read: which hosts share which hash → wait ONE round window (60 s)
│   → heals via fork choice → done; check ForkOrphanedTxLost alert
│   → unsettled → manual resync path (journal-predating segments only)
└─ one host behind/different → M1/M5 on that host only.
    read: is-active + journal + env-pins diff on that host

STOP — call the operator, never improvise:
  • two validators unrecoverable inside the window
  • fork loser predates the delta journal / revert root mismatch
  • any bad-allocation suspicion (M4) • anything pointing at M8
```

## Rehearsal coverage

Exercised on scratch: `rejoin` (M1 catch-up + slot resume) · `skip` (M1
one-down cadence) · `untrusted` (M5 membership refusal) · `golden`
(genesis determinism) · `rollback.py` (pre-PONR aborts — 130 s, 13 polls).
Rehearsed under `RESET-REHEARSAL-FAULTS-1` (#351 — each phase proven once
on the node2 scratch harness; the full ordered pass is REHEARSAL-4's):
`stall` (M2 — 2-of-4 freeze with the refusal mark, resume on restart),
`fork` (M3 — same-height rival seals, convergence on restore), `resync`
(M7 — corrupt store → repair → hash-exact catch-up), `alloc-fix` (M4 —
treasury-signed corrective seals; the first run caught a real
payload-signing defect), `gossip` (M6 — attestation-plane degradation,
filter and bind variants). M8 is a decision class — the runbook
procedure re-run is its own rehearsal.

Proposed register row — real gap, not built: wire
`scripts/monitoring/attestation-arrival-textfile.py` (systemd timer +
textfile dir) so the already-loaded `aitbc-attestation-arrival` group gets
its `aitbc_attestation_*` series — until then nothing on production alerts
a single silently-degraded validator (M6).

## Stop conditions

Never improvise past these — call the operator: two validators
unrecoverable inside the window; a fork loser predating the delta
journal or failing a revert root-check; any bad-allocation suspicion
(M4); anything pointing at M8.
