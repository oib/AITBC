# QA Validation Report — ABS-244

**Ticket:** ABS-244 — SecEng bypassability review + defense-in-depth hardening of the ABS-243 seat kill-guard  
**Branch:** `ABS-244-auto`  
**Commits:** `d7d5968` (hook hardening), `bbb8630` (review artifact)  
**QAS:** qas  
**Date:** 2026-07-14  
**Verdict:** ✅ **APPROVED**

---

## Scope recap (PO amendment 2026-07-14T08:00:56Z, review-first)

The PO amended the scope: AC1 must include guard self-modification, indirect execution and
kill-switch abuse; AC2 accepted-risk is a fully legitimate outcome; AC3 setsid deferral
pre-answered; any real enforcement layer capped to a follow-up. This report validates against
the amended AC, not the original body alone.

---

## Acceptance Criteria — Pass/Fail per criterion

### AC1 — Bypassability review artifact in `docs/security/`
**✅ PASS**

Artifact: `docs/security/ABS-244-kill-guard-bypassability-review.md` (committed at `bbb8630`).

Vector matrix covers all required vectors with exploitable/not verdicts and probe evidence:

| Vector | Required by | Covered | Verdict |
|--------|------------|---------|---------|
| base64/eval | Original AC1 | ✅ V1 | Exploitable — accepted risk A1 |
| Variable indirection | Original AC1 | ✅ V2a | Exploitable — accepted risk A1 |
| Wrapper/alias script | Original AC1 | ✅ V3 | Exploitable — accepted risk A2 |
| `exec` | Original AC1 | ✅ V4 | **Not exploitable** (kill word on line) |
| Alternate kill utility | Original AC1 | ✅ V5a | Exploitable — accepted risk A1/A2 |
| Guard self-modification | PO amendment | ✅ V6 | Exploitable — accepted risk A3 (dominant) |
| Indirect execution (wrapper file) | PO amendment | ✅ V3/V5a | Exploitable — accepted risk A2 |
| Kill-switch abuse | PO amendment | ✅ V7 | **Not exploitable** — inline env prefix hits command, not hook |
| Quote splicing | Peer of V2 | ✅ V2b | Exploitable — accepted risk A1 |
| V0 — guard never wired | PO amendment (implicit) | ✅ | Dominant finding, escalated to operator |

All verdicts reproducible: `bash tests/probe-kill-guard-bypass.sh`.
Method: PreToolUse stdin JSON contract with decoy PIDs only; no name-pattern kill against `orchestrator.sh` was executed.

### AC2 — Exploitable vectors mitigated or accepted-risk documented
**✅ PASS**

Two vectors mitigated with tests (M1, M2); all remaining exploitable vectors carry explicit accepted-risk reasoning:

**Mitigated:**
- M1 — `ps … | grep … | kill` (V5b): blocked; tested in `test-kill-guard.sh` including end-to-end decoy survival.
- M2 — broadcast `kill -9 -1` (V8): blocked; tested with positional logic (`kill -1 <pid>` still allowed).

**Accepted risk (with reasoning):**
- A1 (V1/V2a/V2b/V5a): Command-line obfuscation. Structurally unfixable at PreToolUse layer (guard reads before shell expansion). Hardening buys false assurance + raises FP rate.
- A2 (V3/V5a): Indirect execution. Guard sees `bash script.sh`, not contents. Closing would require static analysis of all executed files.
- A3 (V6): Guard self-modification. Dominant bypass: seats hold `Write`/`Edit` on the guard file by explicit grant, running as operator's UID. A hook cannot protect its own file.

Governance declarative rule: `_common-rules.md §8` now explicitly states guard evasion is a governance violation, with reference to the review artifact. ✅

### AC3 — `setsid` evaluation with `#PATH_DECISION`
**✅ PASS**

`#PATH_DECISION` present in review artifact (confirmed: `grep "PATH_DECISION"` → 1 hit).

Rationale recorded:
- `command -v setsid` → not found on macOS/BSD (verified by the seat; confirmed by QAS: `command -v setsid` → empty on this host)
- Even where available, `setsid` scopes own-group cleanup; it does not prevent signalling processes of the same UID. Not an outward-kill barrier.
- Alternatives (setsid behind platform check, nohup/disown, privilege separation) all documented with rejection rationale.

### AC4 — Kill-switch + observability parity for new layers
**✅ PASS**

Both new rules (M1 and M2) honor `ORCH_KILL_GUARD=0` and the human-shell exemption. Both emit observability logs with UTC ts, seat identity, matched form, and command. Tested explicitly in the `ORCH_KILL_GUARD=0 allows broadcast kill (legacy)`, `ORCH_KILL_GUARD=0 allows ps|grep|kill (legacy)`, `human shell never guarded (broadcast)`, `log records the broadcast-kill form`, `log records the ps-name-lookup form` assertions — all pass.

### AC5 — No regression; all test suites green; lint clean
**✅ PASS**

**`tests/test-kill-guard.sh`:** 48 passed / 0 failed (up from 31 ABS-243 assertions; all prior assertions unchanged, 17 new ABS-244 assertions added).

**`tests/test-local-main-guard.sh`:** 13 failures — identical failures on `main` (pre-existing environment issue: exit 127, command not found for a script dependency). ABS-244 introduced **zero regressions** here.

**Hook parity:** `harness/claude/hooks/pre-bash-kill-guard.sh` and `agent_providers/claude_code/hooks/pre-bash-kill-guard.sh` byte-identical (`md5sum` both = `c03b7e519c0a7111891ba4428a4a4a3a`).

**Lint:**
- `bash -n harness/claude/hooks/pre-bash-kill-guard.sh` → OK ✅
- `shellcheck -S warning harness/claude/hooks/pre-bash-kill-guard.sh` → OK ✅
- `bash -n tests/probe-kill-guard-bypass.sh` → OK ✅
- `bash -n tests/test-kill-guard.sh` → OK ✅
- `shellcheck -S warning tests/probe-kill-guard-bypass.sh tests/test-kill-guard.sh` → OK ✅
- `jq empty harness/claude/hooks-config.json` → OK ✅
- `jq empty harness/claude/settings.template.json` → OK ✅

---

## Security Reviewer Findings (non-blocking, filed as follow-ups)

The SecEng seat (security-engineer) identified two additional findings, both filed as
follow-ups and explicitly NOT blocking this ticket per the review-first scope cap:

1. **M1 narrower than claimed** — `ps ax | awk '/orchestrator/' | xargs kill` bypasses M1 (keys on `grep` token, not `ps` + non-grep lookup). Filed as follow-up; open before ABS-244, narrower after, fix is a matcher-widening the PO capped out.
2. **Audit log injection** — the blocked command is logged unescaped, so a newline in a command injects arbitrary log lines. Pre-existing from ABS-243; no privilege gain; follow-up filed.

QAS assessment: Both are honestly disclosed limitations, not defects in the ABS-244 deliverable. The PO decision explicitly caps enforcement layers to a follow-up. These findings are correctly scoped out.

---

## V0 Finding — Escalation Confirmed Out of Scope

**V0: `.claude/settings.json` does not exist** — no settings file loads the kill-guard, so it never fires in this checkout. Reproduced independently:

```
bash tests/probe-kill-guard-bypass.sh
→ NOT WIRED | V0 | *** no settings.json loads this hook -> THE GUARD NEVER FIRES ***
```

This is correctly escalated to the operator by the be-developer (deliberately not remediated mid-flight, per the governor-pin model). The Security Reviewer confirmed it for a 4th time independently. It is a **V0 finding, not a defect in ABS-244** — the deliverable is the review artifact, not the wiring.

This does not block the ABS-244 verdict. A follow-up (orchestrator preflight self-check) is recommended but is outside this ticket's scope.

---

## Summary

| AC | Criterion | Result |
|----|-----------|--------|
| AC1 | Review artifact committed in `docs/security/`, all vectors covered including PO amendment additions | ✅ PASS |
| AC2 | All exploitable vectors mitigated (M1/M2) or explicitly accepted-risk with reasoning; governance rule in §8 | ✅ PASS |
| AC3 | setsid deferred with platform rationale and `#PATH_DECISION` recorded | ✅ PASS |
| AC4 | Kill-switch + observability parity for both new rules, tested | ✅ PASS |
| AC5 | 48/48 test-kill-guard.sh; local-main-guard regressions are pre-existing (identical on main); hook parity byte-identical; bash-n/shellcheck/jq-empty all clean | ✅ PASS |

**Verdict: APPROVED** — All five acceptance criteria met under the PO review-first scope amendment.

**Exit:** ABS-244 carries `security` flag but no `design` flag → transition to `Story Acceptance`.
