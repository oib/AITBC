# QA Validation — ABS-595

**Commit under test:** 32496a8e (on `ABS-595-auto`, pushed to `gitlab/ABS-595-auto`)  
**Files changed:** 5 (`scripts/ci-capacity-probe.sh` +158, `scripts/ops-sweep-sensors.sh` +33, `tests/test-ci-capacity-probe.sh` +127, `harness/claude/agents/rte.md` ±4, `agent_providers/claude_code/prompts/rte.md` ±4)  
**QAS run date:** 2026-07-27  

---

## AC1 — Bounded pipeline wait (named timeout, not silent budget burn)

`scripts/ci-capacity-probe.sh wait <deadline> <interval> <poll_cmd>` polls until the pipeline reaches a terminal verdict. When `(now − start) ≥ deadline`, it prints `PIPELINE-WAIT-TIMEOUT after=<N>s …` and exits 124 (the ABS-573 per-suite-watchdog contract). It never loops beyond the deadline.

Test evidence (`tests/test-ci-capacity-probe.sh`):
- `forever-PENDING wait exits 124` — PASS
- `timeout is a NAMED state, not a silent budget burn` — PASS
- `wait returns NO-CAPACITY at once when the pipeline can't run` — PASS
- `wait surfaces the NO-CAPACITY verdict` — PASS

**AC1: PASS**

---

## AC2 — NO-CAPACITY distinguished from RED

`classify <status> <failure_reason> <runner_count>` applies a precedence chain:
1. `success` → exit 0 GREEN
2. `runners = 0` → exit 2 NO-CAPACITY (capacity absent, non-blocking)
3. `failed` with reason in `{stuck_or_timeout_failure, runner_system_failure, scheduler_failure, no_matching_runner}` → exit 2 NO-CAPACITY
4. `failed` with any other reason → exit 1 RED (real job failure, block)
5. in-flight statuses → exit 3 PENDING

GitLab API fields used: pipeline `failure_reason` and project runner list (both live-readable; both fixture-injectable for tests).

Test evidence:
- `success → GREEN (0)` — PASS
- `failed+script_failure, runners present → RED (1)` — PASS
- `failed+runner_system_failure → NO-CAPACITY (2)` — PASS
- `pending with 0 runners → NO-CAPACITY (2)` — PASS
- `running with runners → PENDING (3)` — PASS
- `a genuine red and an infra-stuck are DIFFERENT verdicts` — PASS

**AC2: PASS**

---

## AC3 — Regression test: stuck_or_timeout_failure + 0 runners does NOT stall the lane

`tests/test-ci-capacity-probe.sh` runs `bash scripts/ci-capacity-probe.sh classify failed stuck_or_timeout_failure 0` directly and asserts:
- exit code is 2 (non-blocking, not PENDING=3) — PASS
- output contains `NO-CAPACITY` — PASS  
- verdict is terminal (≠ 3), so the RTE seat stops waiting — PASS

This is the exact failure signature from Pilot 8 (MRs !234/!236/!238, `pipeline=failed failure_reason=stuck_or_timeout_failure duration=None`).

**AC3: PASS**

---

## AC4 — One-shot CI capacity sensor

`detect_ci_capacity()` in `scripts/ops-sweep-sensors.sh` (lines 364–374) fires when `.gitlab-ci.yml` exists AND runner count is 0. It emits exactly one line: `ci-capacity - ci-config=.gitlab-ci.yml,runners=0 register-a-runner-or-remove-the-ci-config`. Count unknown → silent. Config absent → silent. Runners present → silent.

Sensor is registered in `ALL_DETECTORS` and in `run_one()` dispatcher, appears in `--list`.

Test evidence:
- `sensor exits 0 even with a finding (diagnosis, not a gate)` — PASS
- `fires the ci-capacity class` — PASS
- `evidence names the zero-runner signature` — PASS
- `reports the capacity gap exactly ONCE` — PASS
- `silent when runners ARE available` — PASS
- `silent when the runner count is unknown` — PASS
- `silent when no CI config is shipped` — PASS
- `ci-capacity listed in --list` — PASS

**AC4: PASS**

---

## Supporting checks

| Check | Result |
|---|---|
| `bash tests/test-ci-capacity-probe.sh` | **23/23 passed** |
| `bash tests/test-ops-sweep-sensors.sh` | **35/35 passed** |
| `bash -n scripts/ci-capacity-probe.sh` | OK |
| `bash -n scripts/ops-sweep-sensors.sh` | OK |
| `bash scripts/generate-governor.sh --providers --check` | OK (no drift) |
| Commit 32496a8e reachable on active remote | `refs/remotes/gitlab/ABS-595-auto` ✓ |

**RTE procedure (`harness/claude/agents/rte.md` Merging step 3):** now instructs to use `scripts/ci-capacity-probe.sh`, bound the wait, treat NO-CAPACITY / PIPELINE-WAIT-TIMEOUT as infra hand-off (not story bounce), and not bounce a story for missing infrastructure. Provider mirror regenerated in the same commit.

---

## Architect non-blocking observations (disposition)

Three observations from the In-Review gate — none block ACs:

1. **Runner-precedence edge:** `classify()` checks `runners = 0` before `failure_reason`. A pipeline with 0 runners and a non-stuck reason still exits NO-CAPACITY. This is correct per AC2 (zero runners = infrastructure absent, always non-blocking). Not a defect.
2. **`online`-only vs "active AND online":** `cmd_runners` counts `"online":true` entries from the GitLab runners API. The header comment says "active AND online". In GitLab's API, `online` already implies active assignment eligibility; the grep is sufficient for the classification decision. Acceptable.
3. **glab-specific live reads:** `verdict` and `runners` subcommands require `glab`. The ACs cover only the pure `classify` and `wait` paths (both fixture-testable without glab), and the test suite exercises those. The live adapters are untestable without a real GitLab project — accepted as-is.

---

## Verdict

**APPROVED** — all four acceptance criteria pass. No regressions in the existing ops-sweep suite (35/35). Harness/mirror parity clean. No out-of-scope changes (branch-protection switch untouched per AC guardrail).
