# v9 pre-pin checklist (transaction authorization)

> Tracked copy of the operator checklist (sanitized; TOPOLOGY keeps the
> scratch original). Gate for pinning `state_transition_v9_height`.

Gate for pinning `state_transition_v9_height`. Every line must be green
before the pin commit is made; the order below is the order to run it.

## 1. Shadow-window pass condition (scripted)

`fleet-config-check.sh` section "v9 shadow window (pin gate)" computes
the window automatically: latest validator `ActiveEnterTimestamp`
bounds the fleet window; per-process counters are `increase()` since
restart by construction. PASS requires all of:

- [ ] ≥ `V9_WINDOW_MIN_HOURS` (24) elapsed since the latest validator
      restart, on every active node.
- [ ] `v9_shadow_checked_total > 0` on every validator — positive
      control, proves the policy ran on live traffic.

      **Rollout record (2026-09-29):** the positive-control code shipped
      early via commit `091ca4cb` and a rolling validator restart —
      hub1 → node1 → node2 → hub, then follower node0 — each via the
      rejoin runbook (no-production drop-in → restart → height+hash
      parity → restore). Latest validator restart = hub at
      **21:35:32 CEST**; earliest pin-ready window close =
      **2026-09-30 21:35:32 CEST**. node0's later restart (21:35:54)
      correctly does not move the validator-only bound. The K-3
      ETH-key clear rode the same restarts — `ETH_WALLET_PRIVATE_KEY`
      is now absent from all `aitbc-blockchain-node` processes.
      `checked` counts *evaluations* (proposer + importers +
      attesters), not unique transactions — ">0" is the gate, never a
      traffic-volume claim.

      **Pinned-code delta:** the window runs `091ca4cb`; the pin will
      ship `7fdf202` on top plus the pin height. The delta so far is
      metric-surface only — `IPFS_SUBSCRIPTION` added to
      `V9_METRIC_KNOWN_TX_TYPES` (it was silently landing in `_other`)
      plus a completeness parity test; verdict semantics unchanged.
      This claim is a gate, not an assertion — see the re-window check
      in section 4. Completeness is now enforced mechanically:
      `test_known_metric_types_cover_apply_path` fails if any type the
      apply path recognizes is missing from the allowlist — a new type
      can no longer hide in `other`.
- [ ] `v9_would_reject_total == 0` (and no `v9_would_reject_*` detail
      series) on every validator.
- [ ] `v9_shadow_checked_total > 0` is not automatic: empty blocks run
      no verdicts, so a quiet fleet shows `checked 0` even on correct
      code. **2026-09-30 ~12:10 CEST**: probe tx sent inside the window
      (hub `default` → `ipfsbuyer`, 0.001 AIT, signed TRANSFER, sealed
      at treasury nonce 80). All five hosts then showed
      `v9_shadow_checked_total 1.0` + `..._transfer_total 1.0` — the
      wiring is proven live. If the window otherwise stays quiet, one
      such probe inside the window is enough to satisfy `checked > 0`.
      (Exactly 1 per host is consistent: the imported-head shortcut
      signs without re-evaluating when attestation arrives post-import.)
- [ ] `v9_shadow_checked_other_total == 0` on every validator —
      non-zero means real evaluations landed outside the known-type
      set (most likely a peer probing with made-up type names, but
      possibly a real type the allowlist missed). Explain it on record
      before the pin; the fleet check prints and flags it.
- [ ] Traffic-mix review: per-type `v9_shadow_checked_<type>_total`
      series show the window actually covered traffic — rare types
      (governance, staking, escrow, GPU, BRIDGE_*) either appear in
      `checked` during the window or are exercised by the canary.

## 2. Window discipline (while it runs)

- [ ] No validator restarts — any restart resets that node's counters
      AND the fleet window start. The K-3 restart that clears
      `ETH_WALLET_PRIVATE_KEY` from `aitbc-blockchain-node` memory rides
      the pin deploy itself, not before.
- [ ] No chain-code deploys (blockchain-node/rpc/p2p sources).
- [ ] Bridge-monitor work is safe inside the window (no validator
      restart) — but keep it below pin prep in priority.

## 3. Canary ordering

- [ ] Record the window verdict FIRST (fleet-check output above).
- [ ] Then run the canary. Any negative canary case (unsigned tx, wrong
      signer) increments `v9_would_reject_*` by design — list expected
      counter deltas per canary case so a non-zero counter afterwards
      is explained, not alarming.

## 4. Pin mechanics

- [ ] **Re-window gate** — "the window measured the pinned code" as a
      command. The validator's import surface is wider than the app:
      `aitbc-blockchain-node` runs with
      `PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/blockchain-node/src`, so
      consensus behavior also depends on the repo-root `aitbc/`
      package (e.g. `crypto/signature_recovery.py`), `packages/`, and
      the dependency inputs. From a checkout containing the pin commit:

      ```bash
      git diff --stat 091ca4cb00..<pin-commit> -- \
          apps/blockchain-node/src aitbc packages \
          requirements.txt requirements-minimal.txt requirements-test.txt \
          poetry.lock pyproject.toml
      ```

      The changed-file set must be exactly
      `apps/blockchain-node/src/aitbc_chain/config.py` (the pinned
      height) and
      `apps/blockchain-node/src/aitbc_chain/state/v9_policy.py` (the
      metric allowlist) — and `git diff` hunks must show only the
      height line and allowlist entries. Any other change inside the
      import surface means the window ran on different code than the
      pin: re-window.
- [ ] **Documentation gate** — both must hold before the pin commit:
      the v9 authorization policy is described in a tracked doc (the
      "v9 transaction authorization" section of
      `docs/releases/v0.25/v0.25.8_change.log` plus
      `state/v9_policy.py`); and the changelog carries an entry for every
      commit in the pin range — mechanically verified by the fleet check's
      "changelog coverage" section, which must report zero uncovered
      commits.
- [ ] **One source of truth for the height** — `config.py` carries the
      pin. Documented convention (v0.25.8 changelog): v2=0/v3=5470 are
      env-set on all five nodes by design; v4+ are code-pinned literals
      ("V7/V8 env lines dropped"). V9 follows the code-pin convention:
      no `STATE_TRANSITION_V9_HEIGHT` in any env file, systemd
      `Environment=` line, or drop-in.
      Enforced by the fleet check's "effective transition heights"
      section, which reads the **running process environment**
      (`/proc/<pid>/environ` — catches env files, systemd lines and
      leftover drop-ins in one pass) and falls back to each host's own
      checkout default; effective = env-if-present else code. It flags
      any V4..V9 env shadow and any cross-host effective difference.
      Baseline verified 2026-09-29: all five hosts identical at
      `V2=0(env) V3=5470(env) V4=11000 V5=24000 V6=0 V7=24650 V8=24800
      V9=None`.
      **V-5 replay caveat:** a node replaying/bootstrap-checking
      *without* the env pins sees code default v3=0, not the live 5470
      — replay tooling must load the production env or pass the heights
      explicitly (`--env-file` takes one file; merge node.env + %N.env +
      blockchain.env first-wins). `/rpc/status` does not expose
      effective heights, so process-env + checkout is the authoritative
      read. **Known divergence (2026-09-30, inventory in
      `v5-replay-inventory.md`):** genesis replay of real
      history fails at height 11 — the v1 model wrongly assumes the
      recording era did not auto-create recipient accounts at import.
      Blocks 1–10 verify hash+root identical; the 16-allocation genesis
      on hub1 is the correct input. This is replay-fidelity work for
      V-5, not a v9 pin blocker — v9 evaluates new blocks identically
      either way.
- [ ] Identical validator commits: `git rev-parse HEAD` equal on all
      four validators before the restart wave begins — the tag section
      of the fleet check only verifies each host *contains* the latest
      tag; different commits can both pass it. The check prints a
      heads-identical/differ line per run. **Read together with the
      effective-heights section**: its fallback reads each host's own
      checkout default, which is only correct when the checkouts are
      identical — this gate is what makes that derivation trustworthy.
- [ ] Pin height ≥ 500 blocks past the last validator restart.
- [ ] Historical fixture (`test_historical_replay.py`) and parity
      matrix pass on the pinning commit.
- [ ] Deploy via the rejoin runbook; confirm every validator reports
      the same effective height before the arrival block.

## 5. Post-pin watch

- [ ] `v9_would_reject_total` now counts REAL rejections — first
      several hundred blocks watched for `[PROPOSE]` success and zero
      unexpected rejections (per changelog Phase 2).

## 6. Rollback line

- [ ] If real rejections rise after the pin: the decision is the
      operator's. Unpinning requires **another version height** (the
      pin is consensus state — a revert is itself a versioned
      transition); the alternative is fix-forward. Decide BEFORE
      pinning which failure modes justify which response, so the
      middle of an incident isn't where the policy gets written.

## Reference

- Shadow machinery: `apps/blockchain-node/src/aitbc_chain/state/v9_policy.py`
- Window check: `scripts/monitoring/fleet-config-check.sh` "v9 shadow
  window (pin gate)"
- Alert rules tested: `scripts/monitoring/aitbc_rules_test.yml`
  (`promtool test rules`) — V9ShadowRejection, V9AttestationRefusal
- Phase-2 description: `docs/releases/v0.25/v0.25.8_change.log`
  "v9 transaction authorization" section
