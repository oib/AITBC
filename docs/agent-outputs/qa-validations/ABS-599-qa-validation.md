# QA Validation — ABS-599

**Ticket**: RTE resolves tests/staged-suite.sh against the harness checkout instead of the target repo  
**Branch**: ABS-599-auto  
**Commit under review**: `a855fb2d`  
**QAS run date**: 2026-07-27  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Results

### AC1 — Source corrected, paths anchor to the target repo

**PASS**

- Source identified: rte seat generalized the harness prefix (injected by ABS-535 skill-path rewrites) onto `tests/staged-suite.sh`, a repo-relative test tool.
- Fix: `harness/claude/agents/rte.md` and `harness/claude/agents/qas.md` each carry an explicit PATH anchor at their `staged-suite` blocks. The anchor names the root cause, states that `tests/staged-suite.sh` resolves against the seat cwd (target repo), and forbids any harness/governing-checkout absolute prefix.
- Provider mirror regenerated per ABS-317: `agent_providers/claude_code/prompts/rte.md` and `qas.md` contain the same anchor.
- No other seat text was changed; scoped to the two gate seats that invoke repo-relative test tools (commons prompt-size ratchet blocks adding it there).

### AC2 — Test confirms target-repo resolution with differing checkouts

**PASS — 9/9 assertions**

```
bash tests/test-seat-repo-path.sh
```

Run against commit `a855fb2d`:

```
=== ABS-599: repo-relative tool paths resolve against the target repo ===

AC2 — a gate seat is cd'd into the target repo and finds tests/staged-suite.sh there
  PASS harness and target checkout are different directories (self-hosting split)
  PASS seat cwd is the target repo (.../tmp/seat-repo-path-test.WBdBod/project)
  PASS seat cwd is NOT the harness checkout
  PASS tests/staged-suite.sh is findable from the seat cwd (the target repo)
  PASS rte prompt keeps the repo-relative staged-suite invocation
  PASS rte staged-suite block carries the path-resolution anchor (ABS-599)
  PASS no harness-absolute path to staged-suite in the seat prompt

AC3 — no seat SOURCE text names a machine-absolute checkout path
  PASS no agent-def / skill source names a machine-absolute checkout path (/Users|/home)
  PASS guard catches an injected machine-absolute harness path

=== Results: 9/9 passed ===
All tests passed
```

Test drives the real spawn seam (`scripts/orchestrator-spawn-claude.sh`) with `ORCH_HARNESS_HOME` pointing at the actual repo root and `ORCH_SPAWN_CWD` pointing at a separate ephemeral directory. ABS-285 env scrub applied (`unset "${!ORCH_@}"`).

### AC3 — Grep-assert blocks harness-absolute paths in seat source

**PASS** (covered within `test-seat-repo-path.sh` above)

- Guard scans `harness/claude/agents` and `harness/claude/skills` for `/Users/…` and `/home/<user>/…` patterns — zero hits.
- Positive control: an injected file containing `/Users/someone/boilerplate-stable/…` is caught by the same grep. Confirms the guard is live, not vacuously passing.

---

## Supporting Validation

| Test | Result | Command |
|------|--------|---------|
| Harness parity (`test-harness-parity.sh`) | 6/6 PASS | `bash tests/test-harness-parity.sh` |
| Agent-def lint (`test-agent-def-lint.sh`) | 7/7 PASS | `bash tests/test-agent-def-lint.sh` |
| Agent-def exit lint (`test-agent-def-exit-lint.sh`) | 9/9 PASS | `bash tests/test-agent-def-exit-lint.sh` |
| Prompt-size budget (`test-agent-prompt-size-budget.sh`) | 19/19 PASS | `bash tests/test-agent-prompt-size-budget.sh` |
| Spawn-skill-path (`test-spawn-skill-path.sh`) | 32/32 PASS | `bash tests/test-spawn-skill-path.sh` |
| Provider mirror parity (`--providers --check`) | OK | `bash scripts/generate-governor.sh --providers --check` |

No regressions introduced. The rte-path fix is additive (text-only addition to two seat prompts + new test file).

---

## Commit Verification

- Commit `a855fb2d` exists: confirmed via `git cat-file -e`
- Pushed: confirmed via `git for-each-ref --contains a855fb2d refs/remotes/` → `refs/remotes/gitlab/ABS-599-auto`
- Branch: `ABS-599-auto` (ticket story branch)

**Final Verdict: APPROVED — transition to Story Acceptance.**
