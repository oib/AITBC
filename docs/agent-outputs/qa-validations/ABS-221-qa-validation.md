# QA Validation — ABS-221 (merge-status skill)

**Date:** 2026-07-12  
**Seat:** QAS  
**Branch:** `ABS-221-auto`  
**Commit:** `0f826ba` — `feat(skills): add merge-status skill for rte polling [ABS-221]`  
**Verdict:** **APPROVED**

---

## Verified Repo State

```
branch: ABS-221-auto
HEAD:   0f826ba feat(skills): add merge-status skill for rte polling [ABS-221]
tree:   clean (working tree matches HEAD on main; ABS-221-auto is 1 commit ahead)
```

Files in diff vs `main`:
- `harness/claude/skills/merge-status/SKILL.md`
- `harness/claude/skills/merge-status/merge-status.sh`
- `harness/claude/agents/rte.md`
- `agent_providers/claude_code/prompts/rte.md`
- `docs/agent-outputs/ABS-221-merge-status-metric.md`

---

## AC Validation

### AC1 — Skill under `harness/claude/skills/merge-status/` + apply-copy + architect micro-decision

**PASS.**

- `harness/claude/skills/merge-status/SKILL.md` — present; complete content (subcommands, exit-code contract table, raw `bb` recipes, "When NOT to poll" section, gotchas from PR #153 execution).
- `harness/claude/skills/merge-status/merge-status.sh` — present; exec bit `100755` confirmed in git index (`git ls-tree ABS-221-auto`).
- Apply-copy `.claude/skills/merge-status/` correctly NOT hand-committed. Per ADR-A-0016, the live `.claude/` tree is generated from the pinned governor tag (`v2.24.1`), not a hand-maintained copy. Hand-committing the apply-copy would diverge from `generated(v2.24.1)` and break `generate-governor.sh --check`. The copy materializes at the next `/release`. Architect confirmed this in Stage-1 review (gate-results 2026-07-12T09:14:31Z).
- Micro-decision (new skill, NOT a `release-patterns` extension) documented in `docs/agent-outputs/ABS-221-merge-status-metric.md` §Architekten-Kurzentscheid. Rationale: `release-patterns` covers the doing workflow (create/validate/merge); `merge-status` covers read-only status questions. Single-responsibility, separate trigger. Architect concurred.

### AC2 — All recipes executed against PR #153

**PASS.**

Evidence in `docs/agent-outputs/ABS-221-merge-status-metric.md` §AC2-Beleg. PR #153 = MERGED, merge_commit `8c67ef297ac0`.

| Command | Output | Exit |
|---|---|---|
| `pr-state 153` | `PR 153: MERGED` | 0 |
| `pr-ci 153` | `PR 153 CI: successful=0 failed=0 pending=0` | 2 (no checks) |
| `on-target 8c67ef297ac0` | `ON-TARGET: … is on origin/main` | 0 |
| `on-target <unmerged-sha>` | `NOT-ON-TARGET: …` | 1 |
| `drift 8c67ef297ac0 main` | `DRIFT: … is 8 commit(s) behind origin/main` | 1 |

Raw `bb --json --jq` recipes (`.state`, `.merge_commit.hash`, `.summary`, `pr list .pullRequests[] | .id`) also verified for real per the metric doc.

### AC3 — rte role definition references the skill

**PASS.**

`harness/claude/agents/rte.md` — 3 references verified by line number:
- L62: Available Skills entry (trigger description, when to use)
- L78: Monitor-CI procedure step 5 (explicit subcommand list: `pr-ci`, `on-target`, `drift`)
- L230: Built-in skills line (Skill-tool invocation note)

`agent_providers/claude_code/prompts/rte.md` provider mirror — 3 matching references (same lines); parity confirmed.

### AC4 — Before/after metric via Miner-Report

**PASS (with sanctioned open dependency on ABS-218).**

BEFORE baseline measured and documented in `docs/agent-outputs/ABS-221-merge-status-metric.md`:
- `git log` 25×, `git fetch` 7×, `git ls-remote` 4×, `bb pr view` 4×, `bb pr list` 3× = **43 status calls** across a handful of RTE sessions. Launcher comment: "CI-Polling frisst Turns" (Turn-Ceiling set at RTE=60).

Measurement method for the AFTER number is specified and reproducible. The AFTER count is legitimately deferred — `scripts/skill-mining.sh` (ABS-218) was `Ready for Development` when this story ran. PO ruling on ABS-217 explicitly authorized skill stories to proceed in parallel; only AC4 verification awaits ABS-218. The AFTER number is not fabricated (evidence-discipline respected per ABS-137). This is a tracked open dependency, not a gap.

---

## Quality Gates

| Gate | Result |
|---|---|
| `shellcheck merge-status.sh` | CLEAN |
| `bash -n merge-status.sh` | OK |
| exec bit `100755` in git index | CONFIRMED |
| `--help` exit code | 0 |
| Unknown subcommand exit code | 64 |
| `harness/claude/agents/rte.md` refs | 3 (L62, L78, L230) |
| `agent_providers/claude_code/prompts/rte.md` refs | 3 (parity confirmed) |

No `yarn test:unit / test:integration / test:e2e` applies — this is a shell+markdown skill with no JS/TS surface.

---

## Advisory (non-blocking, inherited from Stage-1)

`drift <branch> [target]` defaults `target=main`, but the rte story-push step rebases onto `origin/dev`. The target is parameterized and documented; the rte should pass the explicit base when checking story-branch drift. Not a defect — an operational reminder for the rte.

---

## Verdict

**APPROVED.** AC1–AC3 fully met. AC4 baseline + measurement method documented with a sanctioned open dependency on ABS-218; not fabricated. All shell quality gates green. Transitioning to Story Acceptance.
