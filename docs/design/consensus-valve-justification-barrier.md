# Verifiable-justification barrier for the vote-journal valve route

Status: **draft for AD review** — Phase-2 spec for #1268 residual (c),
released after the #1274 AD policy ruling (comment 20233). Propose-only;
no code, no flags, no implementation authorization implied.

Refs: #1268 (residual ledger c20211, AD acceptance c20235), #1274 (AD final
policy ruling c20233), #1278 (proposer-side recorder gap), #1242 (round-lock
machinery this extends), D9b/D9c drill evidence
(`~/aitbc-test/evidence/1268-20261108-133523/`).

## 1. The gap being closed

Phase 1 (#1268, `6c601ef68` + pin `1883d6da4`) made every vote durable and
restart-safe, added fetch-before-unlock, and added the liveness valve:

- attester side — `remote_attestation._journal_refuses`: a live journal
  vote for a different hash refuses the rival while (a) a peer serves the
  voted block (then pull), or (b) the vote is younger than
  `vote_journal_unlock_seconds` (default 300 s).
- proposer side — `poa._honor_vote_journal`: same rule for proposals.

Both valves open on **local evidence only**: `valve_open(record, 300)`
(wall clock) plus `locate_voted_block` (a private peer query whose
outcome is never published). D9b (round-lock OFF) and D9c (round-lock ON)
both produced the predicted dual seal: n3 sealed A with its publish
dropped, the mesh attested A, the 300 s valve opened, and the mesh sealed
rival B — two confirmed blocks at one height, fork-resolved only after
heal, with the tx surviving exactly once by luck of fork choice.

The AD ruling (c20233) is explicit: a cross-round/cross-hash transition
is justified **only** with independently verifiable protocol evidence;
a time-based unlock alone is NOT proof. This document specifies that
proof.

## 2. What "verifiable" must mean here

An unlock at `(chain_id, height, voter, old_hash → new_hash)` is
*justified* iff a third party — another validator, the sync path, the
equivocation verifier, an auditor — can confirm the permission **without
trusting the unlocking node's word and without access to its local
state**. Concretely the artifact must be:

1. **Self-contained**: signatures + parameters sufficient to re-derive
   the decision; no "ask the node" step.
2. **Quorum-grounded**: its force comes from validator-set signatures,
   not from peer claims or timestamps alone.
3. **Fresh and bound**: tied to `(chain_id, height, old_hash)` and a
   bounded time window, so it cannot be replayed for a different height,
   hash, or era.
4. **Checkable by one pure function**: `verify_justification(...) ->
   Verdict` usable identically in the attestation gate, the proposal
   gate, block validation, and the #1274 evidence classifier.

A wall-clock timeout fails (2) and (4): it is a local assertion. An
operator assertion fails (1) and (2). Both are already ruled out.

## 3. Proposal: the Unavailability Certificate (UC)

The valve exists for exactly one situation: the voted block cannot be
fetched, so the height cannot advance honestly. The permission to unlock
is therefore a claim about **unavailability of `old_hash` at `height`**.
We make that claim a signed, quorum-intersection artifact.

### 3.1 Messages

Two new gossip/RPC message types (names provisional):

- `UNAVAIL_QUERY {chain_id, height, block_hash, query_epoch, requester}`
  — broadcast when a node's valve timer expires for `(height, block_hash)`.
- `UNAVAIL_RESP {chain_id, height, block_hash, query_epoch, signer,
  signature}` — a validator's signed statement: *"as of `query_epoch`, I
  do not possess and cannot serve `block_hash` at `height`."*

The response signs the canonical tuple
`(chain_id, height, block_hash, query_epoch)` with the validator key —
the same key that signs attestations, so `VALIDATOR_SET` membership is
the authorization check and no new key hierarchy is introduced.

### 3.2 Certificate assembly

`UnavailabilityCertificate` (UC):

```
{ chain_id, height, block_hash, query_epoch,
  responses: [ {signer, signature} ... ],
  assembled_by, assembled_at }
```

- A node whose valve expires broadcasts `UNAVAIL_QUERY`, collects
  `UNAVAIL_RESP`s for `unlock_collect_seconds` (proposed: 15 s, one
  gossip round), and assembles the UC locally. No leader, no new service.
- **Threshold**: the UC is valid iff responses verify under
  `VALIDATOR_SET` and the signer set has size ≥ `MIN_ATTESTATIONS`
  (today 2). Rationale: a seal needs the proposer + 2 attestations; if 2
  validators have signed *unavailability* for `old_hash`, any future
  quorum for `old_hash` must include at least one of them re-attesting —
  which is itself recorded equivocation evidence. The certificate
  therefore does not merely justify the unlock; it **prices the residual
  risk**: resurrecting `old_hash` now requires a validator to sign
  against its own signed statement.
- Signers that possess the block MUST NOT sign a response (they should
  serve it instead — the existing fetch-before-unlock path). A signer
  that lies (signs unavailability while holding the block) gains nothing:
  it cannot help `old_hash` seal without contradicting its signature,
  and that contradiction is slashable evidence.

### 3.3 Gate changes (proposal, flag-gated)

Replace the valve predicate `valve_open(record, unlock)` AND-ed with a
second condition in both call sites:

- `remote_attestation._journal_refuses`: rival attestation allowed iff
  `valve_open(...) AND uc_valid(UC_for(old_hash))`. The signed
  attestation request carries `justification: UC` so peers can verify
  before signing.
- `poa._honor_vote_journal`: rival proposal allowed iff
  `valve_open(...) AND uc_valid(...)`. The sealed block's
  `block_metadata` gains `unlock_justification` (additive field;
  absent = unjustified).

`uc_valid` is the single pure verifier described in §2(4). While the
barrier flag is off, behavior is byte-identical to today.

### 3.4 Interaction with round-lock

Under `ATTESTATION_ROUND_LOCK_ENABLED` the same valve route produced
D9c's cross-round pair (A round 0 → B round 5). The UC is
round-agnostic on purpose: unavailability is a statement about the
*block*, not the round. A round-bound variant (`query_epoch` → round
number) is a one-line payload change if AD prefers tighter binding;
recommend keeping it epoch-based since the certificate's force is
quorum-intersection, not round semantics.

### 3.5 Evidence classification (#1274 hookup)

The equivocation recorder (`slashing.record_attestation_equivocation`)
currently emits `double_sign` for any two hashes at a height. With the
barrier armed:

- a re-vote carrying a **valid UC** is recorded with
  `justification="unavailability_cert"` — the AD ruling's "justified
  unlock" class. Policy treatment (advisory vs deterrent) is #1274's
  call; the artifact gives it ground truth instead of inference.
- a re-vote with **no/invalid UC** while the barrier is armed is
  `justification="unjustified"` — the time-unlock path is closed, so
  this is a real protocol violation, not a liveness artifact.
- `verify_unavailability_cert` is also exposed to
  `state/deactivation_evidence._verify_attestation_equivocation` so the
  on-chain/off-chain verifier can classify pairs without trusting node
  logs.

This also gives #1278 a natural home: the proposer-side valve path
(`poa.py:1254`) must emit the same UC into its journal/evidence record —
the barrier forces the justification artifact into existence at exactly
the point the recorder gap lives.

## 4. Why not the alternatives

- **Pure 2-phase QC barrier (E's option a, c19769 §2)**: prevote/precommit
  QCs bound to round+hash. Stronger in the abstract but does not address
  the valve scenario directly — the rival does not exist until after the
  unlock, so there is no QC to present *at unlock time*. It is the
  correct end-state if the fleet ever wants Tendermint-grade locking;
  it is a consensus-format change (new message types, block_metadata
  field, arm height, mixed-version fleet hazard) and should be a
  separate, later phase. The UC proposed here is deliberately the
  *minimal* artifact that satisfies the AD ruling for the valve route.
- **Confirmation depth (option b)**: bounds exposure of tip state but
  says nothing about whether an unlock was permitted; complementary,
  not a substitute. Unchanged recommendation: ship `finalized_height`
  work independently.
- **Keep time-unlock, mark evidence advisory**: rejected by c20233 —
  time alone is not proof.

## 5. Costs and risks

- **Liveness**: valve path gains one gossip round-trip (~seconds) and
  requires reaching ≥2 validators. If the mesh is partitioned below
  quorum, no seal is possible anyway, so the UC requirement adds no
  *new* stall class — only latency on an already-degraded path. The
  300 s timer still bounds how long a node waits before even attempting
  assembly.
- **Byzantine signer**: a validator signing unavailability then
  re-attesting `old_hash` produces a verifiable self-contradiction —
  strictly better evidence than today (today the same behavior is
  invisible or ambiguous).
- **UC replay**: bound by `(chain_id, height, block_hash, query_epoch)`
  + freshness window; signatures are domain-separated from attestation
  payloads (different message tag) so an attestation signature cannot be
  recycled as an absence statement.
- **Journal amnesia residual (unchanged)**: a wiped `vote_journal.json`
  still fails open; the UC does not fix that — it is orthogonal and
  remains the stated Phase-1 residual.
- **Size**: ~600–900 LOC estimate (two message types, UC assembly,
  `uc_valid`, gate wiring, evidence classifier hook, metrics) plus
  tests — smaller than the full QC barrier because no consensus-format
  or block-schema change is required for the attester path; the
  `block_metadata.unlock_justification` field is additive and
  ignorable by old readers.

## 6. Rollout sketch (for AD approval, not authorization)

1. Land `UNAVAIL_*` messages + `uc_valid` + metrics behind
   `VOTE_JOURNAL_JUSTIFICATION_ENABLED` (default off) — dormant.
2. A2 drills on the retained `aitbc-drill-*` mesh: re-run D9b/D9c with
   the barrier armed. Expected outcomes to pin in advance: (a) dual seal
   still possible only if ≥2 validators sign unavailability then
   re-attest (now with self-incriminating evidence); (b) honest-path
   re-votes carry valid UCs and classify as justified; (c) no new stall
   beyond the collect window.
3. Only after drill evidence + operator read-out: arm per-chain, hub
   last (same pattern as prior consensus flags).

## 7. Questions for AD

1. Threshold: `MIN_ATTESTATIONS` (2) signer sets, or stricter
   (`VALIDATOR_SET − 1`)? 2 gives the quorum-intersection argument;
   larger sets raise the bar but also the partition sensitivity.
2. Should a *valid* UC downgrade the evidence pair to advisory, or does
   c20233's "deterrence retained" mean justified unlocks stay
   consensus-visible with a distinct class? (Policy detail belongs to
   #1274 implementation; this spec only guarantees the artifact exists.)
3. Is `block_metadata.unlock_justification` acceptable as an additive
   field, or should justification live only in gossip/evidence (keeps
   block schema untouched but loses the artifact for late-joining
   validators validating old seals)?
4. Confirm epoch-based `query_epoch` binding vs round-bound variant
   under round-lock ON.
