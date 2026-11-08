# UC barrier — implementation plan (PROPOSE-ONLY)

Status: **draft for AD review** — companion to
[consensus-valve-justification-barrier.md](consensus-valve-justification-barrier.md)
(spec `c54a68fcd`, fully ruled). This document plans the implementation;
it authorizes nothing. No code exists; every change below is gated
dormant/off until separately approved.

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

### 1.2 UC collection — gossip path

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

### 1.3 Journal interaction

- `vote_journal.VoteRecord` gains optional `justification: str | None`
  (serialized; absent = unjustified, preserving all Phase-1 journals).
- `journal.record(...)` accepts the UC reference (cert hash or embedded
  cert — embedding preferred: the journal is the durable artifact an
  auditor/verifier reads after restart; size is bounded, ~2 signatures).
- `valve_open` semantics **unchanged** — it remains the time rule; the
  UC requirement is a second predicate AND-ed at the consumers, not a
  journal-internal change. Keeps Phase-1 pins intact.

### 1.4 Gate consumers (three call sites)

1. `remote_attestation._journal_refuses` — rival attestation permitted
   iff `valve_open(...) AND uc_valid`. The attestation request payload
   gains optional `unlock_justification` (UC); peers re-verify before
   signing. Invalid/missing UC under the flag → refusal continues
   (today's pre-valve behavior, now without time escape).
2. `poa._honor_vote_journal` — rival proposal permitted iff
   `valve_open(...) AND uc_valid`. The proposal's `block_metadata`
   gains `unlock_justification` (additive, per ruling); the sealed
   block carries the artifact so late validators/auditors can verify
   post-hoc.
3. Evidence classifier — `slashing`/`deactivation_evidence` path:
   equivocation events recorded while the flag is armed are tagged
   `justification="unavailability_cert"` (valid UC presented) or
   `justification="unjustified"` (none/invalid). Per ruling this is a
   **distinct class** — the event still reaches the evidence bundle
   (deterrence retained); classification only changes how #1274's
   policy treats the pair.

### 1.5 Flag gating (Phase-1 conventions)

- `VOTE_JOURNAL_JUSTIFICATION_ENABLED: bool = False` in `config.py`,
  same dormant pattern as `vote_journal_enabled` /
  `attestation_round_lock_enabled`: read once, default off, no behavior
  change when off (all UC code paths short-circuit before collection).
- Sub-knobs: `unavail_collect_seconds`, `unavail_cert_max_age_seconds`,
  `unavail_min_responses` (default = `MIN_ATTESTATIONS`).
- Independent of `ATTESTATION_ROUND_LOCK_ENABLED` — the UC is
  round-agnostic; both lock modes use the same barrier.

## 2. Test plan

Unit (`apps/blockchain-node/tests/`):

- `verify_unavailability_cert`: valid cert; each single-field corruption
  (chain/height/hash/epoch/signer-set/duplicate signer/stale); signature
  replay across message tags; threshold boundary (1 vs 2 signers).
- Gate wiring: flag off → byte-identical Phase-1 behavior (journal pins
  stay green); flag on + valve expired + no UC → refusal; + valid UC →
  permitted and UC embedded in request/metadata/journal.
- Partition matrix: (a) 4/4 reachable → UC assembles, unlock proceeds;
  (b) only proposer-side partition (D9b shape) → collect times out,
  unlock stays closed, liveness stall bounded by timer not forever;
  (c) sub-quorum partition → no UC possible, but no seal possible either
  (assert the equivalence, not just the stall).
- Round-bound mode (`ATTESTATION_ROUND_LOCK_ENABLED` on): same matrix —
  UC is round-agnostic, cross-round pair still classifies justified.
- Legacy mode: `round=None` records accept/propagate justification
  identically.

Drill (A2, `aitbc-drill-*` mesh — after implementation lands, not now):

- Re-run D9b and D9c scenarios with the flag armed; expected: dual seal
  only via ≥2 validators signing unavailability then re-attesting —
  with self-incriminating evidence attached; honest-path re-votes carry
  valid UCs.
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

~700–1000 LOC + tests: new `unavail.py` (~300), gossip handlers (~150),
gate wiring in `remote_attestation`/`poa` (~150), classifier tag (~50),
config (~30), tests (~300+). No consensus-format or block-schema
change beyond the approved additive metadata field.
