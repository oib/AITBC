# reset-2 (testnet) Reset Runbook — DRAFT

Status: **plan only. Nothing here is authorized, scheduled, or run.** The
window is an operator field; every fleet-affecting step keeps the gate
classes defined by
[bc2-reset-runbook.md](bc2-reset-runbook.md) §"Gate wording" (operator-named /
standing / per-item word / ungated) — restated, not relaxed.

Companion documents (values live there, not restated here):

- [chain-reset-runbook.md](../ops/chain-reset-runbook.md) — the generalized
  template this is the **instance of** (distilled from the bc-2 cut,
  21 Oct 2026); §1 evidence-precondition table and §2 custody gate apply
  verbatim to reset-2.
- [bc2-reset-runbook.md](bc2-reset-runbook.md) — the executed instance;
  its timings key, ledger format, and gate table are the shapes reset-2
  inherits.
- `AGENTS/validator-operations.md` — validator gossip topology, key layout,
  attestation lock, fork healing, rejoin runbook (canonical for §C/§F).
- `apps/blockchain-node/tests/golden/GATES.md` — why every gate height is
  `1` on the new chain.
- #410 (BC-RESET-2-PLAN-1) — the R1–R7 decision set; unresolved items are
  mirrored in §9 before they block a step.

## What reset-2 is

A second testnet genesis (new chain id TBD by the operator — `bc-3`
throughout this draft) executed before the v1 mainnet switch. Unlike
bc-2's emergency reset, this is a **planned** cut: bc-2 keeps running
until the freeze, and the rehearsal machinery from §3 already proved the
mechanics once.

## New lessons folded in (post-bc-2 findings)

Each lesson below changes a specific step — marked `[reset-2]` where it
applies.

1. **Multi-worker rpc is the default** (`--workers 2` fleet since
   `1c79d237b`). Two consequences for the runbook:
   - Admission-time dedupe is pg-authoritative (`pg_advisory_xact_lock` —
     the #743 fix shape, `8c0033cbe`). Post-reset verification includes
     the storm check (below), not just "a send seals".
   - Per-worker semantics are documented, not bugs: rate-limit counters
     (1000 req/60s **per worker**, fleet-effective 2000 — #745 Option A),
     `BlockHeaderCache` staleness, ws dedupe. The deploy checklist must
     NOT report these as defects.
2. **Deploy/verify pattern proven on #743**: single-host first (node0,
   non-validator) → restart → verify → fleet order
   `node0 → node2 → node1 → hub → hub1`, one restart each with a
   spot-check after. Reuse this order for any post-genesis code wave.
3. **Storm sizing is host-scaled** (stress-3 hub saturation): `STORM_N=150`
   = ~150 concurrent CLI processes saturated the small hub VPS
   (load ~90, sshd down ~15 min, chain paused while hub held the
   proposer slot). Cap small-host storm concurrency at 20–40.
   `scripts/stress/KNOWN.md` carries the convention.
4. **Watcher discipline** (#741, stress-2/3): timers arm from
   `locked_until`, never from wall-clock estimates; a watcher failure
   must fail loud, not swallow. The stress-2 maturity watcher fired
   ~22h early off a clock assumption — reset-2's own watchers (drain
   monitors, seal observers) use the sealed-height/timestamp source of
   record only.
5. **Admitted-then-vanished txs** have a known shape now: per-host
   arbitration (pre-#743) is fixed fleet-wide; the residual fanout
   sub-case is observable (`_queue_peer_fanout` now logs). A send that
   vanishes post-reset is a finding, not noise — the runbook treats any
   "submitted, never sealed, no reject" as a stop-and-report.
6. **Fresh-chain-db path is covered** (`91f5b5b26`): import/admission on
   an uninitialized chain db no longer 500s — the exact path a new
   genesis exercises on first boot.

## 1. Evidence preconditions — before the freeze

Adapted from the template's §1 table; each row needs a written home
before the freeze step runs.

| # | gap | evidence home | state |
|---|---|---|---|
| E1 | R1–R7 decisions final (chain id, genesis values, validator set, treasury, timing) | #410 operator card | open |
| E2 | authority custody: every genesis-baked authority backed by recorded key or signed possession proof | template §2 table; `scripts/ops/key-audit.py --find-address` | **load-bearing — must not repeat bc-2's lost `governance_executors`** |
| E3 | committed-table membership audit closed (#649) — no committed-fingerprint table whose only writer is node-local RPC | design review vs `COMMITTED_TABLES` | pending |
| E4 | env enumeration: every new var inside the fleet checker's enumerated set; no operator-pair split violated (signing/verifying env separation by design, template §9.4) | `fleet-config-check` list | pending |
| E5 | rehearsal N complete on scratch (genesis build → produce → replay → rejoin) — the stress-3 wave already proved the runtime paths that bc-2 rehearsal couldn't | scratch harness log | pending |
| E6 | drain/waive table for bc-2 consumers (who must migrate vs who is archived) | `bc2-drain-checklist.md` shape | pending |

## 2. Authority custody gate (carried, load-bearing)

Unchanged from the template §2 — restated here because it is the single
highest-impact finding of the bc-2 program: **every** genesis-baked
authority value needs a recorded key or a signed possession proof
verified *before* the genesis build consumes the values. bc-2's
`governance_executors` keys exist nowhere — the reset-2 build must not
repeat that. `key-audit.py --find-address <addr>` walks every env /
keystore / wallet file without printing the key.

## 3. Rehearsal machinery — what exists and what it proves

- bc-2 rehearsal path (scratch genesis → produce → replay) — proven once
  already; reset-2 reuses it with bc-3 values.
- **New since bc-2**: the stress-3 volume/storm plays under
  `scripts/stress/plays/` are a live admission/seal harness — reuse as
  the post-genesis smoke set (transfers, escrow lock/release/refund,
  AI job, GPU register, exchange, IPFS subscription, RECEIPT_CLAIM).
- The `STORM_N` nonce-storm (play 16) is now a **verification tool**,
  not just a stress play: post-reset, one storm pass per host must show
  exactly 1 pending row per contested nonce (the #743 invariant) — the
  same check the #743 verification wave ran.
- What rehearsal still cannot prove (carried from template §7):
  proposer-failover mid-cut, a re-org across the cut boundary, gossip
  mesh behavior under real peer latency — these stay live-window risks
  with abort paths in §5.

## 4. The cut — sequence (adapted from bc-2 §B–§D)

Phases preserve the bc-2 names; `[reset-2]` marks the deltas.

**B. Freeze** — stop accepting writes on bc-2, in order:
1. Announce the window (public notice — operator names it).
2. Freeze intake: customer traffic pause + bridge locks paused
   (`BRIDGE_LOCKS_PAUSED` — bc-2 pattern; decide whether it carries
   through genesis or launches armed per R-item).
3. Final drain check vs the §E6 table.
4. Record the freeze ledger entry (operator line verbatim + height).

**C. Cut** — per host class, in order:
1. Genesis build on scratch path (decided shape: scratch path is
   enough — bc-2 A6/C4 precedent unless R-item overrides).
2. `[reset-2]` Rolling deploy pattern is the #743 order:
   node0 (non-validator, first) → node2 → node1 → hub → hub1.
   Validator units restart in the operator-named window; the
   **validator rejoin runbook** (`AGENTS/validator-operations.md`) is
   the authority for the rejoin sequence — attestation lock handling,
   fork-healing checks, `VALIDATOR_SET` verification per host before
   the node unit starts.
3. Each host's spot-check after restart: rpc active, 2 workers, head
   advancing, one normal send admitted AND sealed (watch for the
   vanish shape — stop-and-report if it drops).
4. Point of no return = first sealed block on bc-3 (bc-2 §D rule
   carries verbatim).

**D. Post-cut spot set** — the stress-3 smoke set trimmed:
transfers, escrow lock+release, one AI job leg, GPU register, mempool
invariant check (`STORM_N` capped 20–40 on hub/hub1-class hosts).

## 5. Abort / rollback

Carried from bc-2 §E and template §5:
- Any anomaly before the first bc-3 seal → freeze holds, rollback = keep
  bc-2 (the cut is additive until genesis seals — bc-2 services stay
  paused, not destroyed).
- After the first seal → forward-only; defects are fixed forward.
- `[reset-2]` The deploy wave itself is reversible until the first seal:
  a host can re-join bc-2's mesh (rejoin runbook) if genesis fails to
  produce — this is the one rollback leg bc-2 didn't have.

## 6. Post-cut

- bc-2 consumer migration per the E6 drain table; `.pre-reset` /
  scratch-artifact deletion stays per-item-word gated.
- Watchers armed from sealed-height/locked_until sources only (#741
  rule) — never wall-clock estimates.
- Journal sweep ×5 hosts (the stress-3 per-batch discipline): any new
  error line class is a finding.

## 7. Findings this runbook answers

- Lost executor keys (template §2) → §2 custody gate, pre-genesis.
- Multi-worker per-process state (#743/#745/#747 class) → §B.3 spot
  checks + §4 deploy order + "not-a-defect" list for per-worker
  semantics.
- Small-host saturation → storm cap convention.
- Fresh-chain-db 500 → covered by `91f5b5b26` (already fleet-wide).
- #742 deferred-scope items stay deferred — reset-2 does not absorb
  them.

## 8. Gate table (proposed, mirrors bc-2 §H)

| step | class |
|---|---|
| window announce | operator-named |
| freeze intake / bridge pause | operator-named |
| genesis build + values | operator-named (values pinned in the genesis doc) |
| per-host service restarts | standing (rolling, order fixed §4) |
| validator rejoin sequence | operator-named per host |
| first-seal acceptance | operator-named |
| artifact deletions | per-item word |
| all reads | ungated |

## 9. Open items — blocked on #410 R-decisions

The steps that cannot be fully scripted until #410's R1–R7 resolve:

- **chain id + genesis values** (chain id `bc-3` assumed throughout;
  allocations/validators/parameter set pin the genesis build)
- **treasury + authority set** — feeds §2 custody table
- **bridge pause carry-through** — `BRIDGE_LOCKS_PAUSED` at genesis vs
  armed-after (operator decides; bc-2 precedent was paused→redeploy)
- **bc-2 fate** — keep running as parallel testnet vs decommission
  post-cut (affects the E6 drain table's "migrate vs archive" split)
- **window date** — blank until operator names it

Nothing else in this draft is contingent — the mechanics, order,
watcher discipline, and verification shape are all proven or
documented.

## 10. Sign-off checklist

- [ ] §1 evidence rows closed (or waived for this cut)
- [ ] §2 custody checklist complete — every genesis authority has a
      recorded key or signed proof
- [ ] §4 deploy order + rejoin runbook acked per host
- [ ] §9 R-decisions landed and mirrored into the genesis doc
- [ ] window + notice named by the operator
