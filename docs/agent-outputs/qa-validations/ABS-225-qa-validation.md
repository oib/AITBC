# QA Validation — ABS-225 Progress-Based Idle Watchdog

**Verdict:** APPROVED  
**Date:** 2026-07-12  
**Commit:** `14c3a49` (branch `ABS-225-auto`)  
**Runs:** 3 independent test-suite executions (all exit 0)

---

## Acceptance Criteria

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | Active seat survives past old wall-time | **PASS** | `watchdog_verdict(3000,5,900,7200)=continue` + E2E: seat hands off, `extended:` logged, zero idle-kill or lifetime-kill events |
| AC2 | Hung seat idle-killed earlier than legacy wall-time | **PASS** | `watchdog_verdict(950,950,900,7200)=idle-kill` + E2E: killed at 6–7s, far under 30s MAX_LIFETIME; `idle-kill` in run.log |
| AC3 | Endless-loop seat hard-killed at MAX_LIFETIME | **PASS** | `watchdog_verdict(7200,1,900,7200)=lifetime-kill` + E2E: reaped at 3s MAX_LIFETIME; `lifetime-kill` logged, never `idle-kill` |
| AC4 | Single long Bash call survives via process-check | **PASS** | `seat_has_live_descendant` returns active while a child is alive; E2E: 4s child call survives IDLE_TIMEOUT=2s; design decision documented in code + SOP |
| AC5 | Watchdog decisions visible in run.log | **PASS** | `idle-kill`, `lifetime-kill`, and `extended:` events asserted in Part C; every decision includes the WHY (idle N s vs threshold, or lifetime N s vs cap) |
| AC6 | Kill-switch + knobs documented; legacy envs still effective | **PASS** | `ORCH_WATCHDOG_IDLE=0` legacy path tested E2E; 4 new knobs in orchestrator.sh header + ORCHESTRATOR_SOP env table; `ORCH_AGENT_TIMEOUT[_<ROLE>]` feeds derived `MAX_LIFETIME` (2×) — no existing launcher breaks |

---

## Test Suite Results

```
Total:  645   Passed: 638   Failed: 7
```

**All 27 ABS-225 assertions: PASS** (Part A verdict logic: 7; Part B activity helpers: 5; Part C E2E: 15)

**7 pre-existing failures (none in ABS-225 scope):**
- 2 harness-path provenance checks — expect the stable checkout path; this worktree lives under `tmp/ABS-225-work`
- 5 MODEL-LABEL/turn-cap checks — require agent frontmatter absent in this worktree (DEMO-1, DEMO-3, DEMO-7 tickets)

Pre-existing status confirmed: System Architect baseline run at `916e05b` (ABS-225 absent) produced an identical failing set. Zero regressions introduced by commit `14c3a49`.

---

## Operator Pattern-Kill Gate (Operator mandate: both Review AND QAS verify)

**Gate: PASS**

Files audited from the commit (`scripts/orchestrator.sh`, `tests/orchestrator.d/ABS-225-watchdog-idle.sh`, `tests/fixtures/stub-spawn.sh`):

| Check | Result |
|-------|--------|
| `pkill -f` (name-pattern kill) anywhere | NONE — zero occurrences |
| Bare `pkill` without `-P <pid>` | NONE — every pkill uses `-P "$spawn_pid"` |
| Watchdog kills only the runner-started seat | CONFIRMED — `kill -TERM/-KILL "$spawn_pid"` + `pkill -TERM/-KILL -P "$spawn_pid"` (direct children only) |
| Test cleanup kills | CONFIRMED PID-scoped — `kill "$cp"` / `pkill -P "$cp"` / `kill "$sp"` ($!-remembered) |
| stub-spawn.sh | No kill/pkill/pgrep at all |

The 15:38Z/15:41Z live-orchestrator kills came from the seat's interactive ad-hoc `pkill -9 -f "scripts/orchestrator.sh --live"` session commands — not from the committed deliverable. The committed code cannot reap a foreign runner.

**Validation note:** All QAS test commands used `orch --live --once` with tracker-created tickets; no name-pattern pkill was used during validation.

---

## Code Review Observations

- `watchdog_verdict()` checks MAX_LIFETIME before idle — a looping "active" seat (ABS-132/151) dies correctly at the cap before idle-kill could fire.
- `seat_has_live_descendant` uses `pgrep -P "$1"` (by PPID, not name) — correct.
- `seat_last_transcript_write` uses `find -newer "$marker"` (POSIX-portable) — correctly excludes transcripts from before the spawn.
- `seat_activity_epoch` uses `date -u +%s` as "now" when a child is alive — returns current epoch rather than a stale floor value.
- `ORCH_WATCHDOG_POLL` throttles the heavier activity probe; MAX_LIFETIME still checked per 1s tick — correct architecture for keeping the absolute cap responsive.
- `bash -n` and `shellcheck -S warning` clean across the new code range (verified by SA; no new findings in watchdog section).

---

## Documentation (AC6)

- `scripts/orchestrator.sh` header: `ORCH_WATCHDOG_IDLE`, `ORCH_AGENT_IDLE_TIMEOUT`, `ORCH_AGENT_MAX_LIFETIME`, `ORCH_WATCHDOG_POLL` documented with defaults and semantics.
- `docs/sop/ORCHESTRATOR_SOP.md`: env table updated with all 4 knobs; `ORCH_AGENT_TIMEOUT[_<ROLE>]` re-documented as the MAX_LIFETIME source.
- `docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md`: changelog entry added.
- AC4 process-check decision documented in code comments and SOP.

---

## Final Verdict

**APPROVED for Story Acceptance.**

All 6 ACs met. Operator pattern-kill gate passed independently. 27/27 ABS-225 test assertions pass across 3 runs. Zero regressions. Committed documentation complete.

