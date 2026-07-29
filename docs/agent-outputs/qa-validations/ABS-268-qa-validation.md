# QA Validation Report — ABS-268

**Ticket**: ABS-268 — Agent-Def-Hygiene: residualer /tmp + inline-`--body` Draft-Path-Sweep + mechanischer Lint-Guard  
**Branch**: ABS-268-auto  
**Commits validated**: 929db19, d592680, 11d5edf  
**QAS actor**: qas  
**Date**: 2026-07-14  
**Verdict**: ✅ APPROVED

---

## AC Verification (independently re-run)

### AC1 — No inline `--body`/`--reason` tracker calls in harness

**Command run:**
```
git grep -nE '\-\-(body|reason) "' -- harness/claude/agents/ harness/claude/skills/
```

**Result**: 1 hit — `harness/claude/skills/release-patterns/SKILL.md:81`  
**Assessment**: `gh pr create --body "$(cat <<'EOF' …)"` — a GitHub PR creation command,  
NOT a tracker adapter call. Correctly out of scope.  
**Verdict**: ✅ PASS

---

### AC2 — No `/tmp` redirects or `BODY_FILE="$(mktemp)"` in named files

**Command run:**
```
git grep -nE '(> ?/tmp/|BODY_FILE="\$\(mktemp\)")' \
  -- harness/claude/agents/qas-design.md \
     harness/claude/agents/bsa.md \
     harness/claude/skills/issue-enrichment/SKILL.md
```

**Result**: 0 hits  
**Spot-verified**: All three files carry `mkdir -p work/scratch` in every recipe block  
and route body/reason through `work/scratch/`.  
**Verdict**: ✅ PASS

---

### AC3 — `tracker-ops/SKILL.md` draws Write/Edit vs Bash tool distinction

**Checked**: `harness/claude/skills/tracker-ops/SKILL.md` lines 122–134  
**Key text present**:  
- "where you draft it depends on the TOOL you draft it with (ABS-253)"  
- "Write/Edit tool → `work/scratch/` only … denied … silently never lands"  
- "Bash redirection (`printf … > path`) → `/tmp/…` works, because it is the Bash tool, not the Write grant"  
- "Default: `mkdir -p work/scratch` and draft into `work/scratch/<ticket>-<what>.md`"  

**Old sentence confirmed absent**: grep for `sandbox is fine` → 0 hits in harness  
**Examples (lines 64–65, 81–82, 153–154)**: all draft to `work/scratch/`  
**Verdict**: ✅ PASS

---

### AC4 — `tests/test-agent-def-lint.sh` exists, executable, proves pre-fix failure, green on post-fix

**Test run output:**
```
=== agent-def lint: draft-path + inline-body guard (ABS-268) ===
  PASS guard FAILS on the pre-fix content (regression proof)
  PASS   detects RULE-A: inline --body on a tracker call
  PASS   detects RULE-B: draft redirected into /tmp
  PASS   detects RULE-B: body draft in a bare $(mktemp)
  PASS   detects an inline flag on a backslash-CONTINUED tracker call
  PASS no false positives on the sanctioned forms
  PASS harness/claude agents + skills are clean
Results: Total: 7  Passed: 7  Failed: 0
```

**File**: `-rwxr-xr-x tests/test-agent-def-lint.sh`  
**Regression proof**: Guard uses verbatim defective fixture lines and runs against  
the live harness tree — regression proof is real, not synthetic-only.  
**spec-creation exemption**: Correctly embedded in test with the ticket's own justification.  
**Verdict**: ✅ PASS

---

### AC5 — `test-harness-parity.sh` green (corrected premise: `.claude/` is generated(pin))

**Test run output:**
```
=== governor drift guard (live .claude == generated(pin)) ===
  PASS generate-governor.sh --check passes (live .claude == generated(v2.25.1) + banner stamped)
  PASS no LOCAL-RUNTIME item is part of the generated shipped set
  PASS generator explicitly excludes LOCAL-RUNTIME items from generation
  PASS live settings.template.json wrong-entry-guard registration matches generated(v2.25.1)
  PASS generate-governor.sh --providers --check passes (agent_providers/claude_code == generated(harness/claude))
  PASS generator implements the --providers mirror mode
Results: Total: 6  Passed: 6  Failed: 0
```

**Premise correction (ACKed by system-architect)**: AC5 as written asks `.claude/**` to carry the  
fix AND `test-harness-parity.sh` to be green — those two requirements exclude each other.  
Under ABS-94, `.claude/` is `generated(pin)` from `.governor-tag` (v2.25.1), and  
`test-harness-parity.sh` asserts `.claude == generated(v2.25.1)`. Hand-editing `.claude/`  
would turn that test RED. The fix lives in `harness/claude/**` (the source) and  
`agent_providers/` (regenerated via sanctioned `--providers` path). `.claude/` picks  
up the fix at the next promotion (ABS-95). ABS-253 precedent (PR #173) confirms: it  
touched harness + agent_providers, never `.claude/`.  
**`.gemini/` + `.agents/` mirrors**: carry the in-scope defects fix (lines 225-226 area  
→ `work/scratch/`). Line 87 retains `$(mktemp)` in the simulation snippet — same class  
as spec-creation:194 (Bash redirection, not Write/Edit tool; within guard exemption).  
**Verdict**: ✅ PASS (on corrected premise, consistent with SA's ack and ABS-94)

---

### AC6 — `spec-creation/SKILL.md:194` is unchanged (anti-overreach)

**Command run:**
```
git diff main -- harness/claude/skills/spec-creation/SKILL.md
```

**Result**: empty diff (byte-identical to main)  
**Line 193-194 content confirmed**: `BODY_FILE="$(mktemp)"` still present — correctly untouched.  
**Verdict**: ✅ PASS

---

## Bonus Observation

`tests/test-agent-def-overlay.sh` — the SA noted 5/24 failures "identically on main" and filed  
a follow-up. On ABS-268-auto this test runs **24/24 PASS** (this diff does not touch the overlay  
path; the improvement is either pre-existing test rot that cleared, or the SA's main checkout  
was stale at review time). In either case: **not a regression from this diff**.

---

## Test Suite Summary

| Test | Result |
|------|--------|
| `test-agent-def-lint.sh` | ✅ 7/7 PASS |
| `test-harness-parity.sh` | ✅ 6/6 PASS |
| `test-agent-def-overlay.sh` | ✅ 24/24 PASS |
| `test-preflight.sh` | ✅ 45/45 PASS |

---

## Scope Ack (14 files vs 5 named)

The sweep touched 14 agent-def/skill files rather than the 5 in the ticket's scope section.  
This is **not overreach** — AC1's grep is repo-wide over `harness/claude/{agents,skills}` and  
AC4 demands a guard over that same tree. Fixing only the 5 named files would have left the  
guard red or forced it to be hollowed. The expansion is the identical mechanical transformation,  
no new abstraction, and several unnamed files carried literal `<`/`>` in inline values  
(live ABS-163 denials). Independently ACKed by system-architect.

---

## Final Verdict

| AC | Verdict |
|----|---------|
| AC1 — No inline `--body`/`--reason` tracker calls | ✅ PASS |
| AC2 — No `/tmp` or `mktemp` in named files | ✅ PASS |
| AC3 — tracker-ops tool distinction, examples corrected | ✅ PASS |
| AC4 — lint guard 7/7, regression-proven | ✅ PASS |
| AC5 — parity green on corrected premise | ✅ PASS |
| AC6 — spec-creation unchanged | ✅ PASS |

**ALL CRITERIA MET. Approved for Story Acceptance.**  
**Flags**: none → exit to `Story Acceptance` (no design gate).
