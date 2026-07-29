# QA Validation — PILOT-66
**Worktree-Provisionierung: Fehlversuche zaehlen, backoff, eskalieren**

- Branch: `PILOT-66-auto`
- HEAD at re-validation: `8479fef8` (forward-fix commit)
- Prior QAS pass HEAD: `8c27e49b`
- Re-validated: 2026-07-26
- Verdict: **APPROVED**

---

## Re-validation Scope

After the prior QAS pass, the system-architect routed a forward-fix commit (`8479fef8`) to resolve a worktree leak in `tests/test-claim-assign.sh`. The fix stubs `ensure_worktree` as a no-op (same class as the existing `live_spawn`/`resolve_spawn_model` stubs), making the suite hermetic across back-to-back runs. Re-validation confirms: (1) the forward-fix passes, (2) all four AC tests remain green at the new HEAD.

---

## Acceptance Criteria

### AC1 — per-ticket counter + backoff + escalation after N attempts

**PASS.**

`record_worktree_provision_failure` writes `$ORCH_STATE_DIR/wtfail-<ticket>`, increments the counter each call, calls `record_backoff` (so the sweep skips the ticket for free during the delay), and calls `escalate_worktree_provision` when the counter reaches `ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS`.

`escalate_worktree_provision` posts a `gate-results` comment to the tracker, transitions the ticket to `Blocked`, and fires `NOTIFY` (the Attention-Event).

Fixture `tests/orchestrator.d/PILOT-66-worktree-provision-guard.sh` (11/11 at HEAD `8479fef8`):
- Attempt 1: `INTENT SKIP-NOWORKTREE … attempt=1/3`; no `WORKTREE-PROVISION-ESCALATE`.
- Attempt 2: `attempt=2/3`; no escalation.
- Attempt 3: `INTENT WORKTREE-PROVISION-ESCALATE … to=Blocked` + `INTENT NOTIFY`; tracker comment "Worktree provisioning failed 3 consecutive times" confirmed via `tracker get`.

### AC2 — git's own stderr surfaced in the runlog

**PASS.**

`_worktree_add` captures stderr into `ENSURE_WORKTREE_STDERR` on non-zero exit; the failure log now prints `worktree provisioning failed for <ticket> (git worktree add): <git error text>` instead of the bare `(git worktree add)`.

Fixture asserts `already` appears in attempt-1 output (real git error: "is already checked out at …"). Green at current HEAD.

### AC3 — mechanical guard: seats in the main checkout cannot move its HEAD

**PASS.**

`scripts/hooks/post-checkout-main-head-guard.sh` is the mechanical backstop. `provision_main_head_guard` (orchestrator startup) installs it into `<git-common-dir>/hooks/post-checkout`. On a branch checkout by a seat in the main checkout, the hook snaps HEAD back to the protected branch — only when safe (clean tree, new branch at same commit as protected branch). An unsafe move (diverged branch, dirty tree) warns but does not restore. Human checkouts and linked-worktree checkouts are never touched.

`tests/test-main-head-guard.sh` — 12/12 at HEAD `8479fef8`:
- Seat `git checkout -b feature-x` → HEAD restored to `main`; branch ref kept; `git worktree add feature-x` succeeds.
- Human checkout → HEAD untouched.
- Unsafe move (diverged branch) → warn-only, no restore.
- Linked-worktree seat checkout → untouched (git-dir ≠ common-dir).
- Kill switch (`ORCH_PROTECT_LOCAL_MAIN=0`) removes the hook; post-kill seat checkout moves freely.
- Foreign hook untouched (fail-open install).

### AC4 — budget unchanged across N failed provisioning attempts

**PASS.**

Fixture: after 2 failed provisioning attempts, `STUB_RECORD_FILE` (spawn-seam call counter) = 0 lines; `spawn-ledger-*` = 0 lines. The provisioning check returns before the budget/lock/seam path is touched.

---

## Forward-Fix: `8479fef8`

`tests/test-claim-assign.sh` — 20/20 at HEAD `8479fef8`:

The fix adds `ensure_worktree() { :; }` (8 lines with comment) to the claim-assign suite. The ABS-186 suite drives `spawn_dispatch` in MODE=live with `ORCH_WORKTREE_SPAWNS=1`, reaching the PILOT-66 provisioning gate. Without the stub, `git worktree add -b <ticket>-auto` ran in the shared `.git`, leaking branches (`T-won-auto`, `T-role-auto`, etc.) with no teardown; a second run then collided. The stub is the same class as `live_spawn` and `resolve_spawn_model` (existing stubs in the same suite) — the assign layer only needs provisioning to succeed, never inspects the worktree.

Verified hermetic: 20/20 on this run.

---

## Full Test Evidence (HEAD `8479fef8`)

| Test | Result | Notes |
|---|---|---|
| `PILOT-66-worktree-provision-guard.sh` (via `SUITE_INCLUDE_ONLY`) | **11/11 PASS** | AC1/AC2/AC4 |
| `tests/test-main-head-guard.sh` | **12/12 PASS** | AC3 |
| `tests/test-claim-assign.sh` | **20/20 PASS** | forward-fix |
| `tests/test-orch-knob-drift.sh` | **4/4 PASS** | knob hygiene |
| `tests/test-orchestrator-marker-allowlist.sh` | **3/3 PASS** | marker hygiene |
| `tests/test-rule-ledger.sh` | **18/19** | pre-existing on `main` (`.claude/agents/tdm.md` drift); routed ABS-558 |

### Pre-existing failure baseline

`test-rule-ledger.sh` 18/19 is the same failure present on `main` at `cc1ea37e`. Not a PILOT-66 regression.

---

## Knob and Marker Hygiene

- `ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS` documented in `ORCHESTRATOR_SOP.md` → knob-drift 4/4.
- `ORCH_GUARD_MAIN_BRANCH`, `ORCH_HEAD_GUARD_ACTIVE` documented in the ops-knob table.
- `wtfail-` marker class documented in `ORCHESTRATOR_STATE_MARKERS.md` → marker-allowlist 3/3.

---

## Commits on branch

| SHA | Subject |
|---|---|
| `e7f0187b` | `fix(orchestrator): bound worktree-provisioning failures + main-HEAD guard [PILOT-66]` |
| `712bc069` | `docs(sop): document PILOT-66 knobs + wtfail- marker class [PILOT-66]` |
| `06a00409` | `docs(qa): QA validation report for PILOT-66 — APPROVED [PILOT-66]` |
| `8479fef8` | `fix(test): stub ensure_worktree in claim-assign suite to stop worktree leak [PILOT-66]` |

---

**Verdict: APPROVED — all 4 ACs pass at HEAD `8479fef8`, forward-fix hermetic (20/20), no new regressions vs main.**
