# QA Validation Report: PILOT-67

**Story**: PILOT-67 — Merge-Erkennung: parentless Story in einen Epic-Branch + origin-Fallback verbieten
**Epic**: PILOT-58
**Date**: 2026-07-26
**Validator**: QAS (automated)
**Commit under test**: `9352fb42` on `PILOT-67-auto`

---

## 1. Acceptance Criteria Verification

| AC | Description | Verdict | Evidence |
|----|-------------|---------|----------|
| AC1 | Merge detection probes ALL targets (main + every epic branch), regardless of parent field | **PASS** | `story_merge_target_branches` emits main + all `epic/*` refs; `story_git_merge_state` iterates the full set. Test: "AC1: parentless story merged into epic/* → MERGED" PASS |
| AC2 | Epic ref is fetched before resolution — no silent fallback to main on stale/absent tracking ref | **PASS** | `story_merge_target_branches` fetches `refs/heads/epic/*:refs/remotes/$remote/epic/*` before listing. Test: tracking ref deleted → still listed and resolved PASS |
| AC3 | Hardcoded `origin` fallback locked: active push remote is the only source | **PASS** | `resolve_active_main_ref` now uses `remote.pushDefault` else sole remote, never unconditional `origin`. Tests: `pushDefault=gitlab` → `gitlab/main`, sole remote `bitbucket` → `bitbucket/main` — both PASS |
| AC4 | Manual operator release not silently re-parked; probe-vs-operator conflict is visible | **PASS** | `docs_pr_gate` calls `operator_released_from_merge_gate`; on disagreement emits `MERGE-WAIT-CONFLICT` intent + gate comment + notify, returns 1 (Docs proceeds). Tests: no re-park, conflict logged, comment posted — all PASS |
| AC5 | Falsification: parentless story merged into epic branch ⇒ MERGE-WAIT-RELEASE fires | **PASS** | Fixture: PILOT-34 (no parent), merged into `epic/PILOT-28-poll-to-push`. `story_git_merge_state` → `MERGED`. `merge_wait_release` → `TRANSITION PILOT-34 Docs`. |

---

## 2. Test Suite Results

### PILOT-67 Target Suite

| Suite | Run at | Total | Passed | Failed |
|-------|--------|-------|--------|--------|
| `test-merge-wait-target.sh` | `9352fb42` | 31 | **31** | 0 |

Breakdown: 16 pre-existing assertions (AC regression guard) + 15 new PILOT-67 AC1–AC5 assertions. All PASS.

### Full Staged Suite

| Stage | Total | Passed | Failed | Notes |
|-------|-------|--------|--------|-------|
| `orch-core` (test-orchestrator.sh, 4 shards) | 726 | **726** | 0 | |
| `stories` (orchestrator.d/*.sh, 51 files) | 51 files | **51** | 0 | |
| `pool` (remaining test-*.sh) | 19 files | 18 | **1** | Pre-existing; see §3 |

### Sibling Merge-Gate Suites

| Suite | Passed | Status |
|-------|--------|--------|
| `test-merge-wait.sh` | 70/70 | PASS |
| `test-docs-merge-wait-pilot.sh` | 28/28 | PASS |
| `test-merge-conflict-redirect.sh` | 43/43 | PASS |
| `test-stacked-mr-guard.sh` | 21/21 | PASS |

### Static Analysis

| Check | Result |
|-------|--------|
| `bash -n scripts/orchestrator.sh` | **PASS** (syntax clean) |

---

## 3. Pre-Existing Failure (Not a Regression)

`test-rule-ledger.sh`: 1 failure — "repo docs/rule-ledger.yaml passes the checker (expected exit 0, got 1)".

Confirmed pre-existing: identical failure on `main` (cc1ea37e) baseline before PILOT-67 changes. The PILOT-67 commit touches only `scripts/orchestrator.sh` and `tests/test-merge-wait-target.sh`; no rule-ledger files changed.

---

## 4. Code Review Alignment

The System Architect approved the same commit at the `In Review` gate (see handoff comment 2026-07-26T14:56:12Z). Noted items carried forward: `story_merge_target_branches` now incurs one bounded fetch per call (bounded by `ORCH_REMOTE_PROBE_TIMEOUT`), which is correct behavior, not a defect.

---

## Verdict

**QAS APPROVED**

All 5 acceptance criteria met. `test-merge-wait-target.sh` 31/31 PASS. Full staged suite green (pre-existing pool/1 failure confirmed on main baseline; no PILOT-67 regressions). Sibling merge-gate suites green. Syntax clean.
