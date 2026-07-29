# QA Validation — ABS-597

**Ticket**: JOIN-SPLIT-Fehlalarm: Detektor zaehlt lokale Branches und prueft keine Ahnenschaft  
**Commit**: `6b38620b`  
**Branch**: `ABS-597-auto` → `refs/remotes/gitlab/ABS-597-auto` (pushed)  
**Validator**: QAS  
**Date**: 2026-07-27  
**Verdict**: **APPROVED**

---

## Files Changed

| File | Purpose |
|------|---------|
| `scripts/orchestrator.sh` | AC1–AC3: remote-only fetch + `epic_branch_split_class` |
| `tests/orchestrator.d/ABS-316-epic-branch-split.sh` | AC4: 3 regression cases |
| `harness/claude/agents/tech-writer.md` | AC5: bar `epic/` namespace for fallback branches |
| `agent_providers/claude_code/prompts/tech-writer.md` | AC5 mirror (parity OK) |

---

## AC Verification

### AC1 — Split detector evaluates only branches on the active push remote

`epic_branch_names()` queries `refs/remotes/<remote>/epic/<epic>-*` via `active_remote_name` (ADR-A-0030 pin). It runs a bounded best-effort fetch first (`_bounded_git "${ORCH_REMOTE_PROBE_TIMEOUT:-12}"`) then reads only tracking refs. Local `refs/heads/` are never counted.

Test: `localonly` scenario — one remote branch + a local-only second branch.

```
PASS ABS-597 AC1: local-only second branch does NOT inflate the remote count
PASS ABS-597 AC1: local-only branch -> SINGLE (no split)
PASS ABS-597 AC1: local-only trace -> JOIN fires (the frozen-PILOT-71 fix)
PASS ABS-597 AC1: local-only trace -> no false escalation
```

**Result: PASS**

### AC2 — Ancestor relationship auto-resolves, no escalation

New function `epic_branch_split_class()` returns `ANCESTRY<TAB>winner<TAB>names` when every candidate is `merge-base --is-ancestor` of another. `join_check_epic` logs `INTENT JOIN-SPLIT-RESOLVED` with `descendant:<winner>` and then fires the ordinary JOIN — no escalation to `Needs PO Decision`.

Test: `ancestry` scenario — slug1 is ancestor of slug2.

```
PASS ABS-597 AC2: two remote branches present
PASS ABS-597 AC2: one contains the other -> ANCESTRY
PASS ABS-597 AC2: ancestry auto-resolved (logged), not escalated
PASS ABS-597 AC2: the descendant wins
PASS ABS-597 AC2: JOIN still fires after auto-resolve
PASS ABS-597 AC2: ancestry does NOT escalate to Needs PO Decision
```

**Result: PASS**

### AC3 — Real divergence escalates naming the diverging commits

`epic_branch_split_class()` returns `SPLIT<TAB>names<TAB>detail` when commits exist on both sides of the merge base. The `join_check_epic` body message now carries `diverging:<branch>[<sha1>,<sha2>,...] <branch>[<sha>...]` (the `$ebdetail` variable), not just branch names.

Test: `divergence` scenario — slug1 and slug2 each carry a unique commit off base.

```
PASS ABS-597 AC3: two divergent remote branches
PASS ABS-597 AC3: divergent commits both sides -> SPLIT
PASS ABS-597 AC3: real split -> Needs PO Decision
PASS ABS-597 AC3: split intent names both branches
PASS ABS-597 AC3: split intent names the diverging commits, not only branch names
PASS ABS-597 AC3: split does NOT fire the ordinary JOIN
```

**Result: PASS**

### AC4 — Regression tests for all three cases

Command run:
```bash
SUITE_INCLUDE_ONLY=ABS-316-epic-branch-split.sh bash tests/test-orchestrator.sh
```

Commit tested: `6b38620b` on `ABS-597-auto`.

```
=== ABS-316/ABS-597 epic-branch-split guard ===

  PASS ABS-597: one remote epic branch -> distinct count 1
  PASS ABS-597: one branch -> SINGLE
  PASS ABS-597: single branch -> ordinary JOIN fires
  PASS ABS-597: single branch -> no split escalation
  PASS ABS-597: zero epic branches -> distinct count 0
  PASS ABS-597: zero branches -> guard no-ops, JOIN fires
  PASS ABS-597 AC1: local-only second branch does NOT inflate the remote count
  PASS ABS-597 AC1: local-only branch -> SINGLE (no split)
  PASS ABS-597 AC1: local-only trace -> JOIN fires (the frozen-PILOT-71 fix)
  PASS ABS-597 AC1: local-only trace -> no false escalation
  PASS ABS-597 AC2: two remote branches present
  PASS ABS-597 AC2: one contains the other -> ANCESTRY
  PASS ABS-597 AC2: ancestry auto-resolved (logged), not escalated
  PASS ABS-597 AC2: the descendant wins
  PASS ABS-597 AC2: JOIN still fires after auto-resolve
  PASS ABS-597 AC2: ancestry does NOT escalate to Needs PO Decision
  PASS ABS-597 AC3: two divergent remote branches
  PASS ABS-597 AC3: divergent commits both sides -> SPLIT
  PASS ABS-597 AC3: real split -> Needs PO Decision
  PASS ABS-597 AC3: split intent names both branches
  PASS ABS-597 AC3: split intent names the diverging commits, not only branch names
  PASS ABS-597 AC3: split does NOT fire the ordinary JOIN
  PASS ABS-597: ORCH_EPIC_SPLIT_GUARD=0 restores JOIN even with a real split
  PASS ABS-597: kill switch suppresses the split escalation

  Total: 24  Passed: 24  Failed: 0
```

Companion tests (no regressions):
- `test-epic-join-resting.sh`: **25/25 PASS**
- `test-epic-end-scenario.sh`: **29/29 PASS**

**Result: PASS**

### AC5 — tech-writer fallback branches outside `epic/` namespace

Both `harness/claude/agents/tech-writer.md` and `agent_providers/claude_code/prompts/tech-writer.md` carry the new **Branch namespace (ABS-597)** block:

> "If a push conflict ever forces you to create a fallback/scratch branch, name it OUTSIDE the `epic/` namespace (e.g. `docs/<ticket>-<slug>`), NEVER `epic/<epic>-…-tw-docs-<n>`."

Mirror parity:
```
generate-governor.sh --providers --check: OK (agent_providers/claude_code == generated(harness/claude)).
```

**Result: PASS**

---

## Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | Remote-only branch evaluation | **PASS** |
| AC2 | Ancestry auto-resolves, no escalation | **PASS** |
| AC3 | Real split escalates with commit names | **PASS** |
| AC4 | 24/24 regression tests green | **PASS** |
| AC5 | tech-writer barred from `epic/` namespace | **PASS** |

**Verdict: APPROVED — advancing to Story Acceptance.**
