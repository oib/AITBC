# QA Validation — ABS-243

**Ticket**: Harness-Guard: Seat darf nur eigene PIDs/Prozessgruppe killen, nie per Namens-Pattern  
**Branch**: `ABS-243-auto`  
**Commit**: `1b64ce3` (provider mirror) ← re-validated; prior commits `4a2120e` (AC1 fix) + `74b41cc` (initial impl)  
**Validator**: QAS  
**Date**: 2026-07-12  
**Verdict**: ✅ APPROVED

---

## What was reviewed

10 files, 631 net insertions on `ABS-243-auto` (`git diff main...HEAD --stat`):

**Guard and wiring (unchanged since `4a2120e`, SA-approved):**
- `harness/claude/hooks/pre-bash-kill-guard.sh` — PreToolUse Bash hook (155 lines)
- `tests/test-kill-guard.sh` — 31-assertion test suite
- `harness/claude/settings.template.json` + `harness/claude/hooks-config.json` — hook wiring
- `scripts/orchestrator-spawn-claude.sh` — `ORCH_KILL_GUARD` export (default 1)
- `scripts/orchestrator.sh` — header hard-rule block (lines 360–368)
- `harness/claude/agents/_common-rules.md` — §8 Kill-Scope rule

**Provider mirror (added in `1b64ce3`, CI parity fix):**
- `agent_providers/claude_code/hooks/pre-bash-kill-guard.sh` — byte-identical to harness (`diff -r` empty)
- `agent_providers/claude_code/permissions/settings.template.json` — +5 lines, kill-guard PreToolUse registration mirrored

**Guard logic unchanged from `4a2120e`:** `git diff 4a2120e..HEAD -- harness/claude/hooks/pre-bash-kill-guard.sh` → empty.

---

## AC Verification

### AC1 — Name-pattern kills blocked; decoy survives

`bash tests/test-kill-guard.sh` run at `1b64ce3`. Guard behavior per AC1 confirmed via `run_guard()` which passes env vars directly to the hook (`ORCH_SEAT=... ORCH_KILL_GUARD=... bash "$HOOK" <<<"$payload"`).

Blocked (exit 2):
- `pkill -9 -f "scripts/orchestrator.sh --live"` — the exact incident command
- `kill -s KILL $(pgrep -f "scripts/orchestrator.sh --live")` — incident, signal-flag variant
- `pgrep -f orchestrator | xargs kill -s KILL` — pipe form with signal flag
- `pkill -f orchestrator && kill -s 0 $$` — compound clause
- `pkill -f orchestrator -s` — `-f` mode never scoped even with trailing `-s`
- `killall orchestrator.sh`

End-to-end decoy test: a subprocess running `abs243-decoy-orchestrator.sh --live` was started; the guard blocked the `pkill -9 -f` against it; `kill -0 "$DECOY_PID"` confirmed it alive; cleanup by explicit PID. Decoy survived. **PASS.**

SA Stage-1 Iteration 1 fix verified: `split_segments()` splits at shell boundaries (`| & ; \`()`) so `seg_is_scoped()` counts `-P/-g/-s` only within the pkill/pgrep invocation's own segment. Signal-flag/compound-clause variants all block. **PASS.**

### AC2 — PID/group/session-scoped kills pass; no false positives

11 allow-path assertions, all exit 0:
- `kill "$pid"`, `kill -TERM 12345`, `kill -0 12345`
- `pkill -TERM -P "$spawn_pid"`, `pkill -KILL -P 12345`
- `pkill -g 4242`, `pkill -s 4242`
- `pgrep -P 12345 | xargs kill`
- `kill -s TERM 12345`, `kill -s KILL "$pid"` (signal flag with explicit PID)
- `ps aux | grep orchestrator` (non-kill inspection)

Existing `pkill -TERM -P "$spawn_pid"` / `pkill -KILL -P "$spawn_pid"` in `orchestrator.sh` line 4748/4751 remain ALLOWED by the guard. **PASS.**

### AC3 — Kill switch + human shell

- `ORCH_KILL_GUARD=0`: a name-pattern kill passed through (exit 0). **PASS.**
- Human shell (seat marker empty — `ORCH_SEAT=""` in `run_guard`): guard exited 0. The check at guard line 67 (`-z "${ORCH_SEAT:-}${ORCH_TICKET:-}${ORCH_ROLE:-}"`) gates on the compound of all three markers. **PASS.**

### AC4 — Blocked kills logged

`ORCH_KILL_GUARD_LOG` receives one line per block:  
`2026-07-12T... BLOCKED seat=... role=... ticket=... matched=pkill reason=... cmd=...`

Log confirmed: `BLOCKED`, `matched=pkill`, offending command string, UTC timestamp matching `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z `. Stderr shows `❌ BLOCKED (ABS-243 kill-guard)` banner with match detail. **PASS.**

### AC5 — Hard rule documented

- `harness/claude/agents/_common-rules.md` §8 (line 94): "Kill-Scope (never kill by name/pattern, ABS-243)" — ALLOWED and FORBIDDEN examples present, mechanical guard mentioned.
- `scripts/orchestrator.sh` lines 360–368: hard rule block documenting the incident, `ORCH_KILL_GUARD` knob, `ORCH_KILL_GUARD_LOG` observability. Existing PID-scoped examples (`pkill -P`) at lines 4748/4751 valid and ALLOWED. **PASS.**

---

## Static analysis

| Check | Result |
|-------|--------|
| `bash -n harness/claude/hooks/pre-bash-kill-guard.sh` | CLEAN |
| `bash -n tests/test-kill-guard.sh` | CLEAN |
| `shellcheck -S warning harness/claude/hooks/pre-bash-kill-guard.sh` | CLEAN |
| `shellcheck -S warning tests/test-kill-guard.sh` | CLEAN |
| `jq empty harness/claude/settings.template.json` | VALID |
| `jq empty harness/claude/hooks-config.json` | VALID |
| `jq empty agent_providers/claude_code/permissions/settings.template.json` | VALID |

---

## Test runs

```
bash tests/test-kill-guard.sh          →  31 passed, 0 failed
bash tests/test-local-main-guard.sh   →  24 passed, 0 failed (regression)
bash tests/test-harness-parity.sh     →   6 passed, 0 failed (CI parity — was 5/6 before provider mirror)
```

---

## Deferred items (security flag, not QAS scope)

Two items accepted at SA Stage-1 remain for downstream SecEng review:

1. **Adversarial bypassability** — base64/eval obfuscation of the command string passes through the heuristic textual gate. Documented in guard header.
2. **`setsid` omission** — absent on macOS/BSD, no AC requires it; accepted per YAGNI.

Neither item affects AC1–AC5 coverage.

---

## Validation guardrail

No real name-pattern `pkill`/`pgrep`/`killall` against `orchestrator.sh` was executed. All probes used the guard's stdin contract and a decoy with a distinct `abs243-decoy-orchestrator.sh` tag killed only by explicit PID.

---

## Verdict

All five acceptance criteria met at `1b64ce3`. Guard logic byte-identical to SA-approved `4a2120e`. Provider mirror byte-identical to harness. Static analysis clean. All three test suites green.

**✅ APPROVED — forwarding to Story Acceptance.**
