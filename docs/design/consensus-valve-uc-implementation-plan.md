# UC barrier — implementation plan (PROPOSE-ONLY)

Status: **draft for AD review** — companion to
[consensus-valve-justification-barrier.md](consensus-valve-justification-barrier.md)
(spec `c54a68fcd`, fully ruled). This document plans the implementation;
it authorizes nothing. No code exists; every change below is gated
dormant/off until separately approved.

**Operator ruling (addendum)**: the Phase-2 **evidence-valve substrate**
from #1279 c20248 (Coder A's per-(height,hash) gossip-observation index)
is folded into this proposal — the UC barrier and the evidence valve
are the same mechanism family and are designed here as **one coherent
mechanism**, not two rows. A's analysis and the director ruling are at
#1279 c20248/c20256/c20258; Phase-1.5 (three-way `locate_voted_block`
verdict) was minted separately as #1280 (owner/A) and is a prerequisite,
not part of this plan.

AD rulings folded in: threshold = 2 (= `MIN_ATTESTATIONS`); justified
unlocks get a **distinct evidence class** (not advisory-downgrade, not
unjustified); `block_metadata.unlock_justification` is an accepted
additive field; `query_epoch` binding is epoch-based (not round-bound).

## 1. Component changes

### 1.1 Wire types — `consensus/unavail.py` (new module)

- `UNAVAIL_QUERY` / `UNAVAIL_RESP` payloads, canonical encoding,
  domain-separated signature tag (`"unavail-v1"` — an attestation
  signature must not verify as an absence statement).
- `UnavailabilityCertificate` dataclass + `verify_unavailability_cert(cert,
  validator_set, chain_id, height, block_hash, now)` → `Verdict`
  (`VALID | INVALID(reason)`). Checks: chain/height/hash/epoch match,
  each signature recovers to a `VALIDATOR_SET` member, distinct signers,
  count ≥ `MIN_ATTESTATIONS`, freshness window
  (`unavail_cert_max_age_seconds`, proposed 120 s — one collect window +
  gossip slack).
- UC assembly helper: given collected responses, build + self-verify
  before use (a node never emits a UC it cannot verify).

### 1.2 Evidence substrate — gossip-observation index (#1279 c20248, folded)

The UC proves validators *declare* unavailability; A's substrate proves
the voted hash *cannot be joining a quorum*. Both are required for the
"can never join quorum" justification, and they share the same wire
traffic.

- **`GossipObservationIndex`** (new, in-memory per `(chain_id, height,
  block_hash)`): `{requests_seen, attestations: {signer -> count},
  first_seen, last_seen}`. Fed by:
  - `attest_request.<chain>` — already subscribed persistently by every
    validator (`remote_attestation.py:261`); index taps the existing
    handler.
  - `attest_response.<chain>` — **the one real gap**: today only the
    collecting proposer subscribes, transiently (line ~1467). Add a
    persistent follower-side subscriber that feeds the index and drops
    payloads after recording (no attestation state change for
    non-collectors — observation only).
- **Clean-window verdict** `index_clean(index, now)`: true iff
  `now − last_seen ≥ T_evidence` AND `distinct attestations < quorum`
  AND no request re-broadcast seen in the window. `T_evidence`
  proposed **90 s** — sized above worst observed gossip propagation
  (~33 s in the drills) per A's residual analysis, not the 300 s timer.
- **"Zero observed ≠ zero cast" residual** (A's honest caveat,
  adopted): attestation gossip is ephemeral with no store-and-forward,
  so a sealed block's responses can be permanently lost in partition.
  The rule stays sound because (a) a seal requires the proposer to have
  *received* quorum pre-isolation, and (b) the sealed block itself
  re-propagates post-heal → `locate_voted_block` hits → the fetch path
  catches it before the clean window can complete. T_evidence covers
  convergence; it is not claimed to prove non-existence.
- **Responder-side tightening**: a validator asked for
  `UNAVAIL_RESP` signs only if it also does not possess the block —
  signing while holding it is a self-contradiction (already priced in
  the spec). Whether responders additionally consult their own index
  before signing is left as an implementation detail; the *verifier*
  does not depend on it.

### 1.3 UC collection — gossip path

- On valve-timer expiry in either consumer (§1.4), node publishes
  `UNAVAIL_QUERY`, collects `UNAVAIL_RESP`s for
  `unavail_collect_seconds` (proposed 15 s), assembles the UC, caches it
  keyed `(chain_id, height, block_hash)` for reuse by both gates within
  the freshness window.
- Responders: a validator holding the voted block MUST NOT sign a
  response — it should serve the block instead (existing
  `locate_voted_block`/pull path stays authoritative). Non-validator
  peers cannot sign; their reachability is already covered by the
  fetch-before-unlock leg.
- Transport: reuse the existing gossip broker topics used by
  attestation requests (no new port/mesh topology); RPC fallback via the
  same `pull_hook`-style peer base-URL plumbing if gossip is the only
  configured path is unavailable — decide in review whether gossip-only
  suffices for v1.

### 1.4 Journal interaction

- `vote_journal.VoteRecord` gains optional `justification: str | None`
  (serialized; absent = unjustified, preserving all Phase-1 journals).
- `journal.record(...)` accepts the justification bundle — embedded UC
  plus an observation-index verdict summary `{clean_since, attestations_
  seen, requests_seen}` (embedding preferred: the journal is the durable
  artifact an auditor/verifier reads after restart; size is bounded,
  ~2 signatures + small counters).
- `valve_open` semantics **unchanged** — it remains the flag-off time
  rule; under the armed flag the release predicate at the consumers
  changes (below), not inside the journal. Keeps Phase-1 pins intact.

### 1.5 Gate consumers (three call sites)

Armed-mode release predicate (replaces `valve_open` as the unlock
gate — this is where the ~300 s stall collapses to ~T_evidence):

```
unlock_permitted = unfetchable_persists(T_evidence)
                AND index_clean(index_for(old_hash), T_evidence)
                AND uc_valid(UC_for(old_hash))
```

- `unfetchable_persists`: `locate_voted_block` keeps returning no
  serving peer across the whole window (today's check, now held for
  T_evidence rather than evaluated once after 300 s).
- `index_clean`: §1.2 verdict — no foreign attestations for `old_hash`,
  no request re-broadcasts, quiet window ≥ T_evidence.

> **Respin amendment (h35 deadlock, #1281):** evaluation order is
> quiet-hash → UC probe → full verdict re-check. Mesh visibility inside
> `index_clean` is established by *authenticated UC probe responses*
> (`note_actor` on verified responders), not solely by passive attest
> traffic — the hold itself suppresses that traffic, so a passive-only
> reading deadlocks on any total proposal-silence event. The quiet leg
> stays passive and cheap: a hash with live attest traffic is never
> probed. Post-probe the FULL predicate is re-evaluated — cert quorum
> is not mesh visibility, and acquisition is not authorization.
- `uc_valid`: ≥2 validator-signed unavailability responses for
  `(chain_id, height, old_hash, query_epoch)`.

Deliberate consequence: **no time-only escape remains when armed.** A
permanent partition holds the height indefinitely — same safety
posture as today minus the 300 s valve, and identical in outcome to a
sub-quorum partition (no seal possible anyway). Liveness returns on
heal; this is the trade A's c20248 analysis priced and the director
accepted (c20258). The 300 s `vote_journal_unlock_seconds` stays as the
flag-off path and as a *collection trigger* — the UC/index machinery
engages once the timer expires, then releases on evidence, not time.

Consumers:

1. `remote_attestation._journal_refuses` — rival attestation permitted
   iff `unlock_permitted`. The attestation request payload gains
   optional `unlock_justification` (UC + index verdict); peers
   re-verify before signing. Missing/invalid justification under the
   flag → refusal continues.
2. `poa._honor_vote_journal` — rival proposal permitted iff
   `unlock_permitted`. `block_metadata` gains `unlock_justification`
   (additive, per ruling); the sealed block carries the artifact so
   late validators/auditors can verify post-hoc.
3. Evidence classifier — `slashing`/`deactivation_evidence` path:
   equivocation events recorded while the flag is armed are tagged
   `justification="unavailability_cert"` (valid UC presented) or
   `justification="unjustified"` (none/invalid). Per ruling this is a
   **distinct class** — the event still reaches the evidence bundle
   (deterrence retained); classification only changes how #1274's
   policy treats the pair.

### 1.6 Flag gating (Phase-1 conventions)

- `VOTE_JOURNAL_JUSTIFICATION_ENABLED: bool = False` in `config.py`,
  same dormant pattern as `vote_journal_enabled` /
  `attestation_round_lock_enabled`: read once, default off, no behavior
  change when off (all UC/index code paths short-circuit before
  collection; the persistent `attest_response` subscriber is the only
  always-cheap addition and is itself flag-gated).
- Sub-knobs: `unavail_collect_seconds` (15 s),
  `unavail_cert_max_age_seconds` (120 s), `unavail_min_responses`
  (default = `MIN_ATTESTATIONS`), `unavail_evidence_seconds`
  (`T_evidence`, proposed 90 s).
- Independent of `ATTESTATION_ROUND_LOCK_ENABLED` — the barrier is
  round-agnostic; both lock modes use the same release predicate.
- Depends on #1280 Phase-1.5 (three-way `locate_voted_block` verdict):
  "peer serves rival Y at h" is positive contention evidence and must
  suppress the clean-window, not count as neutral.

## 2. Test plan

Unit (`apps/blockchain-node/tests/`):

- `verify_unavailability_cert`: valid cert; each single-field corruption
  (chain/height/hash/epoch/signer-set/duplicate signer/stale); signature
  replay across message tags; threshold boundary (1 vs 2 signers).
- Gate wiring: flag off → byte-identical Phase-1 behavior (journal pins
  stay green); flag on + timer expired + no UC → refusal; + valid UC +
  clean index → permitted and justification embedded in
  request/metadata/journal.
- Observation index: request/response feed correctness; distinct-signer
  counting; clean-window boundary at T_evidence; "zero observed ≠ zero
  cast" case — sealed block whose responses were partitioned away must
  still be caught by the post-heal fetch path (assert hold, not unlock).
- Partition matrix: (a) 4/4 reachable → UC assembles + index clean →
  unlock at ~T_evidence (assert ≪300 s collapse); (b) proposer-side
  partition (D9b shape) → peer-visibility fails → hold persists
  (indefinite-hold posture, no time escape); (c) sub-quorum partition →
  no UC possible, but no seal possible either (assert the equivalence);
  (d) heal-race — foreign attestation for `old_hash` observed inside
  the window → `index_clean` false → hold continues.
- Round-bound mode (`ATTESTATION_ROUND_LOCK_ENABLED` on): same matrix —
  barrier is round-agnostic, cross-round pair still classifies
  justified.
- Legacy mode: `round=None` records accept/propagate justification
  identically.

Drill (A2, `aitbc-drill-*` mesh — after implementation lands, not now):

- Re-run D9b and D9c scenarios with the flag armed; expected: unlock
  collapses from ~300 s to ~T_evidence + collect (~105 s) on the honest
  path; dual seal only via ≥2 validators signing unavailability then
  re-attesting — with self-incriminating evidence attached; partition
  cases hold indefinitely (no time escape) until heal.
- Restart mid-collect: UC cache is volatile by design; journal-persisted
  justification survives restart for evidence, gate re-collects.
- Evidence durable under `~/aitbc-test/evidence/`.

## 3. Rollout / flag strategy

1. Land dormant behind `VOTE_JOURNAL_JUSTIFICATION_ENABLED` (requires
   `VOTE_JOURNAL_ENABLED` — document the dependency: UC without the
   journal has no valve to justify).
2. A2 drills produce the pass/fail evidence above; ledger on #1268.
3. Per-chain arm height only after drill evidence + AD/operator read-out;
   hub last, matching prior consensus-flag pattern. Mixed-version fleet
   is safe by construction: UC fields are additive/optional; old nodes
   ignore them and keep time-valve behavior (documented downgrade, not
   a safety regression vs today).

## 4. Composition with #1278

#1278's gap: the proposer-side valve path logs the rival seal but
records no equivocation evidence for the proposer itself. With the UC:

- `_honor_vote_journal` valve-open now produces a UC artifact at the
  exact point #1278 identified — the plan routes that artifact into the
  same journal/evidence record the attester path uses, giving the
  proposer-side event the signature material the bundle filter
  (`multi_validator_poa.py:444`) requires.
- Whether #1278's remaining scope (proposer recording its *own*
  equivocation unconditionally, UC or not) is fully closed here or
  stays a separate row is an AD call — flagged, not assumed.

## 5. Estimated size

~900–1300 LOC + tests: new `unavail.py` incl. observation index (~450),
gossip handlers + persistent `attest_response` subscriber (~200),
gate wiring in `remote_attestation`/`poa` (~180), classifier tag
(~50), config (~40), tests (~400+). No consensus-format or block-schema
change beyond the approved additive metadata field; the index is
in-memory/volatile by design (observation window ≪ journal retention).
