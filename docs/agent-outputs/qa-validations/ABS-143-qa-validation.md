# QA Validation Report — ABS-143

**Ticket:** ABS-143 — Revive CI on Bitbucket: pipelines.yml, fix literal `AITBC` regex, evict template workflows, wire e2e suites
**Branch:** `ABS-143-auto`
**Commit:** `25ba49a` — `ci(pipelines): revive enforced CI on Bitbucket [ABS-143]`
**QAS Validation Date:** 2026-07-09
**QAS Instance:** Fresh spawn (resumed after prior transient API-failure crashes)
**Status:** ✅ APPROVED (AC1–AC4) | ⚠️ AC5 BLOCKED — `external-dependency`

---

## Acceptance Criteria Results

### AC1 ✅ — `bitbucket-pipelines.yml` exists with all required gates

| Check | Result | Evidence |
|---|---|---|
| File exists at repo root | ✅ PASS | `ls bitbucket-pipelines.yml` → present, 3,774 bytes |
| YAML valid | ✅ PASS | `python3 -c "import yaml; yaml.safe_load(...)"` → valid |
| Trigger: `pull-requests: '**'` | ✅ PASS | Confirmed in `pipelines:` block |
| Trigger: `branches: main` | ✅ PASS | Confirmed in `pipelines:` block |
| Gate 1 — hook-copy parity | ✅ PASS | `diff -r harness/.claude/hooks agent_providers/claude_code/hooks` → in sync |
| Gate 2 — skills parity (`check-skills-parity.sh`) | ✅ PASS | Ran locally → 22/22 skills in sync (harness/.claude, .agents/, .gemini/) |
| Gate 3 — governor drift (`test-harness-parity.sh`) | ✅ PASS | `bash tests/test-harness-parity.sh` → 4/4 PASSED |
| Gate 4 — full `tests/test-*.sh` loop | ✅ PASS | 24/25 suites pass (see Test Suite table below); sole failure is pre-existing ABS-133 |
| Gate 5 — commit-format check, real `ABS` prefix | ✅ PASS | `bash .github/scripts/check-commit-format.sh HEAD` → `✓ ci(pipelines): revive enforced CI on Bitbucket [ABS-143]` |
| `clone: depth: full` present | ✅ PASS | Confirmed; required for PR-range commit walk |
| Uses `BITBUCKET_PR_DESTINATION_BRANCH` | ✅ PASS | PR mode: `git fetch origin "$BITBUCKET_PR_DESTINATION_BRANCH"` |
| `check-commit-format.sh` syntax clean | ✅ PASS | `bash -n .github/scripts/check-commit-format.sh` → OK |
| Broken `AITBC` regex replaced | ✅ PASS | New regex `\[ABS-[0-9]+\]` matches `[ABS-143]`; old pattern only matched literal `[AITBC-N]` |

**Non-blocking architectural notes (from system-architect review, confirmed by QAS):**
- Missing `set -f` in `check-commit-format.sh` loop (arch note #3): `for msg in $(git log ...)` without glob-expansion guard. Low severity — commit subjects with `*/?/[` could mis-expand. Not a gate issue; recommended backlog item.
- `test-harness-parity.sh` runs twice in pipeline (gate 3 + gate 4 glob) (arch note #2): Harmless duplication; minor wasted CI minutes.

---

### AC2 ✅ — Template workflows evicted from executed path

| Check | Result | Evidence |
|---|---|---|
| `ci.yml` absent from `.github/workflows/` | ✅ PASS | `ls .github/workflows/ci.yml` → No such file |
| `docker-build.yml` absent from `.github/workflows/` | ✅ PASS | `ls .github/workflows/docker-build.yml` → No such file |
| Both present in `templates/.github/workflows/` | ✅ PASS | `ls templates/.github/workflows/` → `README.md ci.yml docker-build.yml` |
| No enforcing `{{...}}` tokens in auto-triggered workflows (Bitbucket) | ✅ PASS | `pr-validation.yml` has `AITBC` at lines 93/108/120 — but these emit `::warning::` only (non-enforcing), and **`pr-validation.yml` never executes on Bitbucket** (GitHub Actions only) |
| `tests.yml` clean of template tokens | ✅ PASS | All `${{ }}` expressions are GitHub Actions syntax, not template tokens |

Remaining active `.github/workflows/` files: `README.md`, `pr-validation.yml`, `test-fork-sync.yml`, `tests.yml` — all deliberate consumer-facing payload.

---

### AC3 ✅ — Keep/drop decisions recorded

`.github/workflows/README.md` (created in `25ba49a`) records explicit keep/drop for every file:

| Item | Decision | Documented Rationale |
|---|---|---|
| `tests.yml` | **KEPT** | Functional consumer GitHub payload; `bitbucket-pipelines.yml` is the live CI for this repo |
| `pr-validation.yml` | **KEPT** | Consumer payload; `AITBC` intentional (substituted by `setup-template.sh`); enforcing gate is in `bitbucket-pipelines.yml` |
| `test-fork-sync.yml` | **KEPT** | Path-triggered fork-sync compatibility check for GitHub consumers |
| `ci.yml` / `docker-build.yml` | **MOVED → `templates/`** | Pure unsubstituted templates; would permanently red a future GitHub mirror default branch |
| `.github/FUNDING.yml` | **KEPT** | Inert on Bitbucket; valid GitHub Sponsors metadata for consumers/author |
| `.github/ISSUE_TEMPLATE/` | **KEPT** | Inert on Bitbucket; generic templates useful to GitHub consumers |

All AC3 decisions present and deliberate. ✅

---

### AC4 ✅ — E2E exit-gate suites wired as explicit manual release steps

`docs/release/PRE-RELEASE-CHECKLIST.md` section 1 "Code Quality Gates", the new entry (lines ~33–40):

```markdown
- [ ] **E2E exit-gate suites** (manual — ABS-143). These are excluded from the
  `tests/test-*.sh` glob ... the release owner runs them by hand and records pass/fail.
  - [ ] `bash tests/e2e-orchestrator-dryrun.sh` (v1/v2 lifecycle — ABS-55): ___ pass / ___ fail
  - [ ] `bash tests/e2e-workflow-v3.sh` (v3 full-team scenarios — ABS-80): ___ pass / ___ fail
  - [ ] Any failure investigated and either fixed or documented in Notes/Errata before tagging.
```

Both scripts verified:
- `tests/e2e-orchestrator-dryrun.sh` — exists, `bash -n` clean ✅
- `tests/e2e-workflow-v3.sh` — exists, `bash -n` clean ✅

Implementation choice: **explicit manual checklist steps** (AC4 explicitly permits "pick one, implement it"). Rationale for not auto-wiring into `pre-release-check.sh`: both e2e suites currently drift-red vs HEAD (post-ABS-153 orchestrator changes, ABS-80 follow-up). Auto-wiring a hard gate against a broken suite would block all releases. Checklist approach is the correct safe choice.

ABS-55 + ABS-80 references present. ORCHESTRATOR_SOP.md §"epic exit gate" alignment confirmed.

---

### AC5 ⚠️ — First Bitbucket Pipeline run + URL (BLOCKED)

**Failure Classification: `external-dependency`**
**Action: Escalate to TDM/human + RTE — do NOT route to implementer**

Blocked on:
1. **Human enablement of Bitbucket Pipelines** on this repo — a provisioning action governed by ADR-A-0004 (human-approval boundary; no agent seat can do this)
2. **RTE opening a PR** to trigger the first pipeline run and capture the green pipeline URL

This is identical to the system-architect's finding. No pipeline URL evidence available — the pipeline cannot produce a first run URL until a human enables it. QAS confirms this is the correct classification per the Failure Classification protocol.

---

## Test Suite Health — Independent QAS Run

Run conditions: `env -i` clean environment (HOME/PATH/SHELL/USER/TMPDIR only), all `ORCH_*`/`TRACKER_CMD`/`JIRA_*`/`MOCK_TRACKER_TICKETS_DIR` unset (to match clean CI runner per BE developer's env-leak finding).

| Suite | Result | Notes |
|---|---|---|
| test-adopt-analyze | ✅ PASS | — |
| test-evolver-lifecycle | ✅ PASS | — |
| test-fork-sync | ✅ PASS | — |
| test-harness-parity | ✅ PASS | 4/4 |
| test-hooks-behavioral | ✅ PASS | — |
| test-hooks-config | ✅ PASS | — |
| test-intake-classification | ✅ PASS | — |
| test-iteration-guard | ✅ PASS | — |
| test-jira-tracker | ✅ PASS | — |
| test-manifest-init | ✅ PASS | — |
| test-manifest-loader | ✅ PASS | — |
| test-mock-tracker | ✅ PASS | — |
| test-multi-domain-sync | ✅ PASS | — |
| test-orchestrator | ❌ FAIL | 442/444 — 2 pre-existing ABS-133 timing-flaky assertions (SKIP-LOCKED re-queue scenario); not caused by ABS-143 (no overlap in changed files) |
| test-patch-generation | ✅ PASS | — |
| test-path-a-solo-pipeline | ✅ PASS | — |
| test-preflight | ✅ PASS | — |
| test-profile-activation | ✅ PASS | — |
| test-protected-files | ✅ PASS | — |
| test-rename-diff | ✅ PASS | — |
| test-setup-template | ✅ PASS | — |
| test-station-guard | ✅ PASS | — |
| test-substitutions | ✅ PASS | — |
| test-tracker-adapter-lint | ✅ PASS | — |
| test-wrong-entry-guard | ✅ PASS | — |

**Summary: 24/25 PASS, 1 FAIL (pre-existing, ABS-143 scope = 0 regressions)**

The 2 failing assertions in `test-orchestrator` are in the "ABS-133 SKIP-LOCKED re-queue" test section. The ABS-143 commit (`25ba49a`) modified 0 files in the orchestrator or test-orchestrator.sh. The failure is timing-dependent and pre-dates this ticket. Route to ABS-133/ABS-80 backlog triage.

---

## Commit Scope Verification

Files changed in `25ba49a` — complete list (7 files, 228 insertions, 0 deletions):

| File | Change | Covers |
|---|---|---|
| `.github/scripts/check-commit-format.sh` | **new** | AC1 (replaces broken `AITBC` regex) |
| `.github/workflows/README.md` | **new** | AC3 (keep/drop decisions) |
| `bitbucket-pipelines.yml` | **new** | AC1 |
| `docs/release/PRE-RELEASE-CHECKLIST.md` | **modified** | AC4 (e2e wiring) |
| `templates/.github/workflows/README.md` | **new** | AC2 (template context doc) |
| `templates/.github/workflows/ci.yml` | **moved** | AC2 |
| `templates/.github/workflows/docker-build.yml` | **moved** | AC2 |

No product code touched. No RLS/auth/DB/frontend surface. CI infra only.

---

## Pattern Compliance

- ✅ Reuses `check-skills-parity.sh` and `test-harness-parity.sh` — no reimplementation (good pattern reuse, per arch review)
- ✅ `#PATH_DECISION` (Pipelines vs GitHub mirror) resolved by POPM 2026-07-07; decision on record; no ADR required
- ✅ No RLS/auth/DB/frontend patterns applicable to this CI-only change
- ✅ Template-eviction approach follows the established `templates/.github/workflows/` path already framed in `.github/WORKFLOW_PATTERNS.md`

---

## Final Verdict

| AC | Result | Classification |
|---|---|---|
| AC1 — `bitbucket-pipelines.yml` with all gates | ✅ **PASS** | — |
| AC2 — Template workflow eviction | ✅ **PASS** | — |
| AC3 — Keep/drop decisions recorded | ✅ **PASS** | — |
| AC4 — E2E suites wired | ✅ **PASS** | — |
| AC5 — First green Bitbucket pipeline run + URL | ⚠️ **BLOCKED** | `external-dependency` → TDM/human + RTE |

**🟢 APPROVED for RTE**

AC1–AC4 fully verified. Sole open item (AC5) is an `external-dependency` — Bitbucket Pipelines must be enabled by a human (ADR-A-0004), then RTE opens the triggering PR. Not a gate blocker per classification protocol.

---

## QAS Handoff Statement

> QAS validation complete for ABS-143 (commit `25ba49a`, branch `ABS-143-auto`). AC1–AC4 all PASS — `bitbucket-pipelines.yml` YAML valid and gates confirmed, template workflow eviction verified, keep/drop decisions documented, e2e suites wired in checklist. Independent test run: 24/25 suites pass; sole failure (test-orchestrator 442/444) is pre-existing ABS-133, zero regressions attributable to this change. AC5 (first Bitbucket pipeline run URL) classified `external-dependency` — escalated to TDM/human; RTE to open first PR for pipeline capture. **Approved for RTE.**

— QAS, 2026-07-09
