# Consensus domain-separation activation runbook (#1298)

> Covers arming `consensus_domain_separation_height` (H) — and, if the
> dual-accept slice is approved, `consensus_legacy_attestation_until_height`
> (S) — on the live fleet. Same one-way activation discipline as the
> v14–v24 state-transition runbooks (`version-gated-activation-runbook.md`,
> `fleet-wave-runbook.md`): **height-gated, fleet-pinned, fix-forward only
> once crossed.**

## What the gate does

At/above H, block-proposal and block-attestation signatures use
domain-separated preimages (`aitbc-consensus-v1:block_proposal` /
`:block_attestation`, `aitbc/crypto/consensus_signing.py`), so a signature
minted for one purpose can never verify for the other. Below H every
sign/verify path is byte-identical to pre-activation — sealed-history
replay cannot diverge.

| Setting (env) | Meaning |
|---|---|
| `CONSENSUS_DOMAIN_SEPARATION_HEIGHT` (`consensus_domain_separation_height`) | H. `None`/unset = unarmed (default). Per-height gate, never wall-clock. |
| `CONSENSUS_LEGACY_ATTESTATION_UNTIL_HEIGHT` (`consensus_legacy_attestation_until_height`) | S. Optional bounded dual-accept window `[H, S)` for **attestation-channel verification only**. Unset = hard cutover at H. S ≤ H is an empty window ≡ unset. Proposal signatures NEVER dual-accept. |

Domain labels are also stamped on evidence records (`signature_domain` in
`attestation_signed.json`) and the attestation-lock journal
(`attestation_round_locks.json`, `kind="attestation"` records) so on-chain
equivocation verification rebuilds the exact preimage and old builds skip
the new record kinds cleanly (additive-tolerant).

## Pre-activation checklist (all five hosts: hub, hub1, node0, node1, node2)

1. **Code live, gate unset (Phase 1 soak).** The impl-1298 build is on
   `origin/main` and ff'd fleet-wide — `git log --oneline -1` identical on
   every host. With H unset, behavior is byte-identical legacy; soak
   indefinitely before pinning.
2. **Fleet compatibility (hard requirement, Phase 2).** EVERY validator AND
   follower runs the domain-aware build before H is pinned. A node still on
   a pre-#1298 build after the pin produces legacy signatures that upgraded
   verifiers reject at ≥H: its votes stop counting and, as proposer, its
   blocks fail proposal verification → round-stall until rotation or
   upgrade. On the 4-validator/3-of-4 set, ONE missed node ≈ 25% round-stall
   (quorum survives); TWO = halt. Followers matter too — they verify
   imported blocks' proposal signatures.
3. **Fleet-config parity.** `fleet-config-check` clean; add
   `CONSENSUS_DOMAIN_SEPARATION_HEIGHT` (and
   `CONSENSUS_LEGACY_ATTESTATION_UNTIL_HEIGHT` if used) to its `VARS` list.
   `consensus_proposer_round_seconds` must already be fleet-identical —
   round derivation depends on it (O6).
4. **Height comfortably ahead.** H several hours of blocks beyond current
   head so the env edit + serial restart wave completes before activation
   (same rule as the version-gated runbook).
5. **Pre-activation snapshot.** Latest `aitbc-backup.timer` generation < 26 h
   old on every host.
6. **Optional L4 mixed-version leg (CARD6, E-run, sandbox-only).** If run,
   record exact per-node versions + flags; exercises signature-domain AND
   round handling, mixed-version reject/accept, raw journals + hashes
   preserved. No production rollout/window activation is authorized by it.
7. **Open-flags resolved before pinning (AD):** pin-expiry/abandon-height
   ruling (T12), dual-accept window W value (T13 — or hard cutover),
   same-key r+4 proposal edge (T19), #1301 abandon-statement domain decision
   (c24412 caveat — `abandon.py` still signs legacy
   `sign_consensus_message`; decide migrate-to-domain vs deliberate
   exclusion BEFORE arming).

## Activation — height pinning order

1. **Pin H first.** Add `CONSENSUS_DOMAIN_SEPARATION_HEIGHT=<H>` to
   `/etc/aitbc/blockchain.env` on all five hosts, identical value, and run
   the serial restart wave per `fleet-wave-runbook.md` (hold-check, serial
   restarts, `ExecMainStartTimestamp`/`MainPID` readback, head-equality
   between hosts).
2. **Pin S second, only if dual-accept is approved.** Add
   `CONSENSUS_LEGACY_ATTESTATION_UNTIL_HEIGHT=<S>` (S = H + W) in a second
   env wave — it may be pinned any time before the tip reaches S, since the
   gate is height-derived. Never pin S without H (S ≤ H is an empty window,
   equivalent to unset). If hard cutover is chosen, leave S unset forever.
3. **Emit rule inside `[H, S)`:** upgraded signers emit ONLY the new domain
   preimage — the window exists solely so stragglers' legacy attestations
   still count. This is why Phase 2 (fleet convergence) is a hard
   precondition: upgrade-first is what makes the window safe.

## At/after activation — watch points

- Head crosses H: block production continues, no stall, no fork — compare
  block hashes across hosts at H and H+5.
- Signature-failure signal: `signature_metrics` `record_failure("block", …)`
  / `invalid_signature` rate at ≥H — a spike means a node missed the
  upgrade (see fleet precondition).
- Dual-accept (only if S armed): `consensus_legacy_attestation_accepted_total`
  counts every legacy attestation accepted inside `[H, S)` — it must go to
  zero as the window closes; any increment at ≥S is a bug.
- Journal health: `attestation_lock_persist_failure_total` must stay 0 —
  each increment is a refused (fail-closed) attestation.
- `attestation_refused_resign_after_expiry_total` — replay-resistance
  refusals; expected rare, investigate clusters.

## Rollback boundary

- **Before H is sealed (H unset, or H still ahead of tip):** remove the env
  pin(s) and re-wave — fully reverts; no domain-signed blocks exist. Safe.
  A partial-rollout abort before pinning: redeploy the previous build
  fleet-wide; gate unset → zero consensus impact.
- **After any block ≥ H is sealed: NO rollback.** Domain-signed blocks are
  in chain history; unpinning makes verifiers take the legacy path and
  every ≥H block fails verification → fork. Fix-forward only — same
  one-way property as v22/v23 activations. Never attempt env rollback
  post-activation.
- **Post-H code downgrade** (running an old build with H still pinned):
  fail-closed liveness degradation, NOT a safety violation — old builds
  reject domain signatures → quorum-stall risk (arithmetic above). Old
  builds ignore domain-tagged journal/evidence records (additive-tolerant).
  Fix forward; do not unpin.

## Verification legs per T-case

| Leg | Where | T-cases | Pass criteria |
|---|---|---|---|
| L0 unit | node2 worktree | T1–T22 matrix | `apps/blockchain-node/tests/consensus/test_domain_separation_matrix_1298.py` green; skipped rows name their slice dependency and are never fake-passed. c901/ruff/mypy hooks clean. |
| L1 golden/replay | node2 | T5 (boundary), #1245 preservation | Historical replay below H byte-identical; golden engine session-config parity at the tested SHA. |
| L2 mesh boundary | mesh @ impl SHA | T4, T6, T7b, T10, T16, T17, T18(reject), T21, T22 | 4-node rebuild; pin H mid-run; H−1 legacy → H domain transition observed; same-hash retry accepted; no stall; seal→import parity across boundary. |
| L3 equivocation | mesh @ impl SHA | T3, T8, T9 | Forced rival at ≥H → domain-labeled equivocation evidence persisted; on-chain verifier accepts same-domain pairs, rejects cross-domain pairing. |
| L4 mixed-version | mesh, sandbox-only (E, CARD6) | T20, T13 (if armed) | One node on pre-impl build, pin H → bounded liveness degradation, no safety violation; per-node SHA+flags+raw journals recorded. |
| Activation soak | fleet | all | Post-pin watch points above clean through H and window close. |

Skipped-matrix dependencies (must land before their legs can run):
T7a/T14 unconditional round auth; T11/T12 proposer emission gate +
pin-expiry ruling; T13/T18w dual-accept window; T15 130 s shared lapse
constant; T19 AD disposition; T20 mesh leg.

## Evidence capture format

Per leg, ledger one record containing:

- **SHA + config:** exact impl SHA tested; per-host `git log --oneline -1`;
  the env pins (`CONSENSUS_DOMAIN_SEPARATION_HEIGHT`,
  `CONSENSUS_LEGACY_ATTESTATION_UNTIL_HEIGHT` or "unset"),
  `consensus_proposer_round_seconds`, round-lock / vote-journal / UC flags
  per node.
- **Timestamps:** pin time (wall), H, current tip at pin, observed crossing
  time of H and S.
- **Chain evidence:** block hashes on ≥2 hosts at H−1, H, H+5 (fork check);
  signature records extracted for I3b re-verification.
- **Node journals (raw, hashed):** `attestation_round_locks.json`
  (kind="attestation" + round-lock records incl. `signature_domain`,
  `derived_round`, `signed_wall`), `attestation_signed.json`
  (`signature_domain`-stamped records), vote journal where armed.
- **Metrics snapshot:** `consensus_legacy_attestation_accepted_total`,
  `attestation_lock_persist_failure_total`,
  `attestation_refused_resign_after_expiry_total`, signature-failure
  counters (`record_failure("block", …)`).
- **Equivocation legs:** the persisted slashing events + assembled
  `verify_deactivation_evidence` payloads and verdicts.
