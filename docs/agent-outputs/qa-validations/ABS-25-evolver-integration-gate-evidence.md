# ABS-25d Gate Evidence — Evolver Integration

**Date**: 2026-07-03  
**Ticket**: ABS-25 (subtask ABS-25d)  
**PR**: [PR #11](https://bitbucket.org/lovebytecodes/agentic-development-boilerplate/pull-requests/11)  
**Branch**: `ABS-25-evolver-integration`

---

## 1. Hook non-regression

**Command:**

```bash
bash tests/test-hooks-config.sh
bash tests/test-iteration-guard.sh
```

**Result:** PASS

| Check | Status |
| ----- | ------ |
| `hooks-config.json` valid JSON | PASS |
| iteration-guard entry present | PASS |
| push-to-main block present | PASS |
| session-start banner present | PASS |
| evolver lifecycle hooks (session-start, post-edit, stop) | PASS (8/8) |
| iteration-guard script tests | PASS (12/12) |

Pre-existing harness hooks were not removed or rewritten. Evolver entries are additive per ADR-A-0010.

---

## 2. Evolver smoke (CLI available)

**Environment:**

- `npm i -g @evomap/evolver` (Node v26.3.1)
- `EVOLVER_AUTO_ISSUE=false`, `EVOLVER_VALIDATOR_ENABLED=0`
- No `A2A_HUB_URL` set (Hub search reported `no_hub_url`)

### 2a. Lifecycle hook — neutral profile (skip path)

```bash
bash scripts/hooks/evolver-lifecycle.sh session-start
# evolver-lifecycle: SKIP evolution provider none
# exit=0
```

### 2b. Lifecycle hook — evolver profile

```bash
ACTIVE_PROFILE=evolver bash scripts/hooks/evolver-lifecycle.sh stop
# evolver-lifecycle: RUN evolver --review phase=stop provider=evolver
# [Review] No pending evolution run to review.  (expected before first run)
# exit=0
```

### 2c. Full cycle — `evolver run` + `evolver --review`

```bash
cd <repo-root>
export EVOLVER_AUTO_ISSUE=false EVOLVER_VALIDATOR_ENABLED=0
evolver run          # GEP prompt emitted to stdout; .evolver/gep/ seeded
evolver --review     # Pending run summary printed (gene_gep_repair_from_errors)
```

**Observed:**

- GEP protocol prompt printed (Cycle #0001, gene selection, signals from session logs).
- Asset store created at `.evolver/gep/` (`genes.json`, `candidates.jsonl`, `events.jsonl`).
- `events.jsonl` empty until `solidify` completes a cycle — expected Evolver behavior; review mode surfaces pending run without auto-applying patches.
- No Hub connection attempted (`SearchFirst] No hub match (reason: no_hub_url)`).
- Runtime dirs `.evolver/` and `memory/` are gitignored.

**Verdict:** Smoke PASS — CLI integration works offline; human review path (`--review`) is the default exit, not autonomous patching.

---

## 3. Self-Improvement E2E (fixture walkthrough)

**Scope:** Apply Step 2 procedure from `.claude/agents/self-improvement.md` to fixture
`work/fixtures/evolver/sample-events.jsonl` (no live Evolver required).

### 3a. Input event

```json
{"id":"evt-fixture-001","timestamp":"2026-07-03T12:00:00Z","gene_id":"gene-hook-friction","signals":["commit-format-reminder","iteration-guard-block"],"outcome":"prompt_emitted","review_mode":true}
```

### 3b. Step 2 mapping

| Field | Friction signal |
| ----- | --------------- |
| `signals[0]` | `commit-format-reminder` → SAFe commit format friction |
| `signals[1]` | `iteration-guard-block` → gate bounce without correct `Iteration N of M` marker |
| `gene_id` | `gene-hook-friction` → hook/governance cluster |

**Recurrence:** 2 signals on one event + alignment with retro friction on commit format and iteration-guard → meets Evolver recurrence rule (retro + 1 EvolutionEvent).

### 3c. Skill proposal (matches fixture structure)

## Skill Proposal: commit-format-guard

- **Recurring task**: Agents repeatedly hit the commit-format reminder hook and iteration-guard block when bouncing gate comments without the correct `Iteration N of M` marker shape.
- **Occurrences**: 2+ — EvolutionEvent `evt-fixture-001` signals `commit-format-reminder` and `iteration-guard-block`; matches retro friction on SAFe commit format.
- **Belongs at**: extend `.claude/skills/safe-workflow/SKILL.md` (Pre-commit section), not a new skill directory.
- **Evidence**: `.evolver/gep/events.jsonl` line `evt-fixture-001`; gene `gene-hook-friction`.

### 3d. Self-Improvement Report (abbreviated)

```markdown
## Self-Improvement Report

- **Trigger**: human — ABS-25d fixture walkthrough
- **Context**: work/fixtures/evolver/sample-events.jsonl
- **Retro**: N/A (fixture-only scope)
- **Skills proposed**: commit-format-guard → extend `.claude/skills/safe-workflow/SKILL.md`
- **Improvement proposals filed**: none (friction is project harness, not boilerplate-owned)
- **Patterns observed**: hook friction cluster (commit format + iteration guard) — informational
- **Human actions needed**: route skill extension via BSA → Issue Enrichment if accepted
```

**Verdict:** PASS — fixture → skill proposal mapping conforms to Step 2 contract and `sample-skill-proposal.md`.

---

## 4. System Architect — Stage 1 Review

**Reviewer**: System Architect (Stage 1)  
**Scope**: PR #11 / `ABS-25-evolver-integration` vs `main`

### 4.1 Pattern compliance

| Check | Result | Notes |
| ----- | ------ | ----- |
| Capability adapter pattern (ADR-A-0007) | PASS | `evolution.md` mirrors `task-tracking.md` structure; `profiles/evolver/profile.yaml` follows `jira-github-postgres` binding style |
| Harness upgrade-clean (ADR-A-0008) | PASS | No fork of harness-owned core; binding is profile + additive hook config only |
| Additive hooks (ADR-A-0010) | PASS | iteration-guard, push block, session banner unchanged; evolver hooks appended |
| Human-approval boundaries (ADR-A-0004) | PASS | `EVOLVER_AUTO_ISSUE=false`, no Hub env in template, `autonomous_merge` unchanged, no outward writes |
| Self-Improvement integration thesis | PASS | Feeds existing loop; no parallel `evolver-sop` skill |

### 4.2 Governance / security

| Check | Result |
| ----- | ------ |
| `#EXPORT_CRITICAL` defaults documented | PASS |
| `.evolver/`, `memory/` gitignored | PASS |
| `evolver setup-hooks` prohibited in docs | PASS |
| Hook script fail-open on missing CLI / provider none | PASS |
| Rate limit (300s) on lifecycle hook | PASS |

### 4.3 Findings

**Non-blocking observations:**

1. `events.jsonl` stays empty until Evolver `solidify` — document in onboarding (operators should not expect events on `run` alone).
2. The evolver hook is registered on `Stop` only (not `SessionEnd`) — intentional per spec §5.2 and enforced by `tests/test-hooks-config.sh`. `SessionEnd` keeps only the pre-existing uncommitted-changes check.

**Blocking issues:** None.

### 4.4 Decision

**APPROVED — Stage 1 Approved - Ready for ARCHitect**

Profile/adapter approach is sound. Governance boundaries preserved. Proceed to Stage 2 (ARCHitect-in-CLI) and HITL merge gate.

---

## 5. Summary

| Gate item | Owner | Status |
| --------- | ----- | ------ |
| Hook non-regression | Implementer / QAS | PASS |
| Evolver smoke (`run` + `--review`) | Human / Opus | PASS |
| Self-Improvement fixture E2E | Opus | PASS |
| System Architect Stage 1 | System Architect | APPROVED |

**ABS-25d complete.**
