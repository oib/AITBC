# QA Validation Report — PILOT-55

**Ticket**: PILOT-55 — Prompt-Größenbudget + Sensor + plattformabhängiges Argv-Gate  
**Validator**: qas  
**Date**: 2026-07-26  
**Branch**: PILOT-55-auto  
**Commits reviewed**: 7b0738db, 72e3a3d2  
**Verdict**: ✅ **APPROVED**

---

## Summary

All 4 Acceptance Criteria (AC1–AC4) are satisfied. Scope guardrails clean (no out-of-scope files touched). Test suite 19/19 PASS. E2E platform gate validated interactively.

---

## AC Verification

### AC1 — Declared Prompt-Size Budget per Seat + Sensor

**Requirement**: A declared budget (Commons + Role + Overlay) per seat; a role over budget is a **defect**, not an operating mode.

| Check | Result |
|---|---|
| Budget declared in `docs/sop/AGENT_CONFIGURATION_SOP.md` § "Prompt Size Budget" | ✅ PASS |
| Sensor `scripts/agent-prompt-size.sh` exists and is executable | ✅ PASS |
| Sensor measures IST sizes matching ticket figures (qas 37418, rte 36738, commons 13760) | ✅ PASS |
| `--check` exits 1 when any role is over budget (defect, not a mode) | ✅ PASS |
| Report mode exits 0 even with over-budget roles (pure measurement) | ✅ PASS |
| Test suite `tests/test-agent-prompt-size-budget.sh` | ✅ **19/19 PASS** |
| Ratchet set to 13 (today's known-debt ceiling, prevents new bloat) | ✅ PASS |

**Sensor output (run on 2026-07-26)**:
```
ROLE                     COMPOSED     ROLE  OVERLAY  STATUS
qas                         37418    23658        0  OVER
rte                         36738    22978        0  OVER
issue-enrichment            36255    22495        0  OVER
system-architect            31470    17710        0  OVER
qas-design                  30783    17023        0  OVER
po-agent                    29898    16138        0  OVER
data-engineer               29698    15938        0  OVER
self-improvement            29489    15729        0  OVER
tdm                         29102    15342        0  OVER
bsa                         27533    13773        0  OVER
be-developer                27452    13692        0  OVER
fe-developer                25468    11708        0  OVER
tech-writer                 24407    10647        0  OVER
security-engineer           23727     9967        0  ok
boilerplate-migration       22950     9190        0  ok
ui-ux-design                22648     8888        0  ok
data-provisioning-eng       19576     5816        0  ok
SUMMARY: 13/17 roles OVER budget (24000 B); commons=13760 B
```

Figures match ticket exactly: qas 37418 B ✓, rte 36738 B ✓, issue-enrichment 36255 B ✓, system-architect 31470 B ✓, be-developer 27452 B ✓, commons 13760 B ✓.

---

### AC2 — Platform-Dependent Gate (POSIX restores inline as normal case)

**Requirement**: Gate set platform-dependently; POSIX should not force the 24000 B fallback.

| Check | Result |
|---|---|
| `scripts/orchestrator-spawn-claude.sh` uses `uname -s` to detect Windows vs POSIX | ✅ PASS |
| POSIX default: `getconf ARG_MAX - 32768` (floor 24000) | ✅ PASS |
| Windows (MINGW/MSYS/CYGWIN/Windows_NT): keeps 24000 | ✅ PASS |
| `ORCH_AGENTS_ARG_MAX` still overrides both (operator lever unchanged) | ✅ PASS |
| ABS-251 test pins explicit 24000 to test mechanism at fixed threshold | ✅ PASS |
| E2E: POSIX with no override → smallrole goes **INLINE** (`--agents` JSON) | ✅ PASS |
| E2E: Forced `ORCH_AGENTS_ARG_MAX=24000` + ~29 KB role → **FALLBACK** (`--plugin-dir`) | ✅ PASS |

POSIX `ARG_MAX` on this machine: 1048576 B → AGENTS_ARG_MAX default = 1015808 B (>> 37418 B for the largest role: inline path restored as normal case).

---

### AC3 — ADR-A-0022 supplemented with D6 (non-null case)

**Requirement**: Overage switches the LOAD PATH, not just the transfer form. ONLY the ADR file, not role defs.

| Check | Result |
|---|---|
| D6 section exists in `adrs/agentic/ADR-A-0022-agent-def-overlays.md` | ✅ PASS |
| D6 explains: overage → switches load path (inline `--agents` → plugin-dir `--agent`) | ✅ PASS |
| ADR `status: proposed` (awaits human acceptance — correct for ADR-only work) | ✅ PASS |
| No role definitions modified | ✅ PASS |
| `_common-rules.md` not touched | ✅ PASS |

---

### AC4 — Link to Prefix-Amplification Analysis

**Requirement**: Budget and token-efficiency are the same problem; cross-referenced.

| Check | Result |
|---|---|
| `work/improvement-proposals/2026-07-25-token-efficiency-prefix-amplification.md` exists | ✅ PASS |
| Referenced in `scripts/agent-prompt-size.sh` (header comment, lines 8-9) | ✅ PASS |
| Referenced in `adrs/agentic/ADR-A-0022-agent-def-overlays.md` D6 (lines 82-83) | ✅ PASS |
| Referenced in `docs/sop/AGENT_CONFIGURATION_SOP.md` (lines 340-341) | ✅ PASS |
| 22–60% paid-input cost claim cited in all three places | ✅ PASS |

---

## Scope Guardrail Verification

| Out-of-scope file | Status |
|---|---|
| `harness/claude/agents/_common-rules.md` | Not touched ✅ |
| Any role definition file | Not touched ✅ |
| `scripts/orchestrator.sh` (main orchestrator) | Not touched ✅ |
| Spawn-seam behavior (other than platform threshold) | Not touched ✅ |

Files changed — Commit 7b0738db (sensor):
- `docs/sop/AGENT_CONFIGURATION_SOP.md` (+27 lines)
- `scripts/agent-prompt-size.sh` (new, 99 lines)
- `tests/test-agent-prompt-size-budget.sh` (new, 139 lines)

Files changed — Commit 72e3a3d2 (platform gate + ADR):
- `adrs/agentic/ADR-A-0022-agent-def-overlays.md` (+21 lines)
- `scripts/orchestrator-spawn-claude.sh` (+24/-4 lines — platform threshold only)
- `tests/test-orchestrator.sh` (+12/-3 lines — pin ABS-251 to explicit 24000)

---

## Shell Quality

| Check | Result |
|---|---|
| `bash -n scripts/agent-prompt-size.sh` | ✅ OK |
| `shellcheck -S warning scripts/agent-prompt-size.sh` | ✅ OK (no warnings) |
| `bash -n scripts/orchestrator-spawn-claude.sh` | ✅ OK |
| `shellcheck -S warning scripts/orchestrator-spawn-claude.sh` | ✅ OK (SC2034 is pre-existing, not PILOT-55) |
| `bash -n tests/test-agent-prompt-size-budget.sh` | ✅ OK |

---

## Test Evidence

```
=== prompt-size budget sensor (PILOT-55 / ABS-566) ===

  PASS composed size = commons + role (small = 150, under budget → ok)
  PASS composed size flags over-budget (big = 1100 > 500 → OVER)
  PASS README.md is excluded (not a spawnable role)
  PASS _common-rules.md is excluded (shared fragment)
  PASS overlay bytes are added to the composed size (small = 100+50+40 = 190)
  PASS --check EXITS NON-ZERO when a role is over budget (defect, not a mode)
  PASS report mode exits 0 even with an over-budget role (pure measurement)
  PASS --check PASSES when every role is under budget
  PASS budget is configurable via ORCH_PROMPT_SIZE_BUDGET
  PASS a non-numeric budget is rejected (exit 2)
  PASS real-harness report runs cleanly (exit 0)
  PASS real be-developer composed size == role + commons bytes (methodology matches ABS-566)
  PASS   real report includes role: qas
  PASS   real report includes role: rte
  PASS   real report includes role: issue-enrichment
  PASS   real report includes role: system-architect
  PASS   real report includes role: be-developer
  PASS real report emits a parseable SUMMARY line
  PASS over-budget count (13) within ratchet ceiling (13) — no new prompt-size defect

=== Results ===
  Total:  19
  Passed: 19
  Failed: 0

Prompt-size budget sensor: all checks passed.
```

---

## Verdict

**✅ APPROVED** — All 4 ACs satisfied, scope guardrails clean, test suite 19/19 PASS, e2e platform gate verified. Transitioning to Story Acceptance.

**Follow-up (ABS-566 remainder, out of scope here)**: Shorten the 13 over-budget roles below 24000 B, lower the ratchet as they drop. ADR-A-0022 D6 needs human acceptance via PR merge.
