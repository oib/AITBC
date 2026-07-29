# QA Validation — ABS-258 (post-rebase re-verification)

**Date**: 2026-07-13
**Branch**: ABS-258-auto
**Commits reviewed**: 1d9d57f (ADR), 4bc6236 (implementation), 53cf4e2 (SOP), 01fefb3 (prior QA report)
**Rebased onto**: origin/epic/ABS-245-consumer-feedback-defork @ 3908ae8
**Run by**: qas (independent, clean env — ORCH_TOOLS/ORCH_MODEL/ORCH_SPAWN_CWD/ORCH_TARGET_REPO/ORCH_HARNESS_HOME/ORCH_OVERRIDES_DIR all unset)
**Verdict**: APPROVED

---

## Context

The RTE bounce at the Merging station (rebase conflict on ADR-A-0008 against the epic tip carrying ABS-259 and ABS-264 amendments) was resolved by the implementer. The system-architect re-reviewed and approved to In Test. This is the QAS re-verification of the rebased result.

Rebase conflict resolutions (three files, verified below):
- `adrs/agentic/ADR-A-0008-*`: epic amendments (ABS-259 §114, ABS-264 §234) preserved; bidirectional ADR-A-0022 link preserved.
- `tests/test-migrate-project.sh`: ABS-249 + ABS-258 fixtures unioned; total 108 (up from 57 pre-rebase).
- `docs/sop/BOILERPLATE_MIGRATION_SOP.md`: §3.1.1 kept; §3.3 appended; drift cross-reference present.

---

## Acceptance Criteria

### AC1 — ADR: overlay semantics, materialization point, frontmatter/tools boundary

**File**: `adrs/agentic/ADR-A-0022-agent-def-overlays.md`

- `status: proposed` (accepted on human merge, ADR-A-0004). ✓
- D1: spawn seam, not write-time edit; rejected alternative (write-time) documented with reason (CONFLICT resurrection). ✓
- D2: append-only, body-only; overlay frontmatter stripped + NOTICEd; `tools` not additive. ✓
- D3: resolves against work target, not harness home; `ORCH_OVERRIDES_DIR` override; fail-open. ✓
- D4: scope shrinks to spawn seam only; sync-claude-harness / migrate-project untouched. ✓
- Bidirectional link: ADR-A-0008 references ADR-A-0022 (confirmed present post-rebase); ADR-A-0022 "Related decisions" references ADR-A-0008. ✓

**Result**: PASS

---

### AC2 — Implementation in the materialization path; base-update + overlay → both present, no conflict

**Files**: `scripts/orchestrator-spawn-claude.sh`, `tests/test-agent-def-overlay.sh`, `tests/test-migrate-project.sh`

**Implementation** (`build_agents_json()`): three-bucket composition — commons + role + overlay. `ridx` keys frontmatter source to the role def only; overlay frontmatter stripped + NOTICEd; resolved against target with `ORCH_OVERRIDES_DIR` fallback; fail-open.

**Test run** (clean env, independently executed by this QAS seat):

```
tests/test-agent-def-overlay.sh  → 24/24 PASS
tests/test-migrate-project.sh    → 108/108 PASS  (57 pre-rebase + ABS-249/ABS-264 fixtures merged)
bash -n scripts/orchestrator-spawn-claude.sh     → OK
shellcheck -S error scripts/orchestrator-spawn-claude.sh → OK
```

Test coverage confirmed:
- Fail-open parity: no overlay → byte-identical emission (3 tests)
- Both bodies present, overlay last (8 tests including ordering assertion)
- On-disk def byte-unchanged after spawn
- Overlay `tools:` does not widen the seat grant (D2) — 3 tool-widening tests
- Overlay resolves against target not harness (D3) — per-role isolation confirmed
- End-to-end (migrate test): overlaid def REPLACED with upstream v2, overlay untouched, no CONFLICT

**Result**: PASS

---

### AC3 — BOILERPLATE_MIGRATION_SOP documents overlay as the standard def-customization path

**File**: `docs/sop/BOILERPLATE_MIGRATION_SOP.md §3.3`

- §3.3 "Customizing an agent def: use an OVERLAY, not a fork (ADR-A-0022, ABS-258)" present. ✓
- Decision table: additive → overlay (no conflict, keeps upstream updates); wholesale → `project_owned_exceptions` (stops receiving updates). ✓
- Drift paragraph (line 158) cross-references §3.3 before a reader edits a def. ✓
- Limits stated: append-only, body-only, frontmatter stripped, interactive Task-tool use bypasses overlay (D5). ✓
- Rebase preserved §3.1.1 (ABS-249 content) alongside §3.3. ✓

**Result**: PASS

---

## Rebase resolution verification

| File | Epic-tip changes preserved | ABS-258 changes preserved |
|------|---------------------------|--------------------------|
| ADR-A-0008 | ABS-259 §114 + ABS-264 §234 amendments ✓ | ADR-A-0022 bidirectional link ✓ |
| test-migrate-project.sh | ABS-249 fixtures (→ 108 total) ✓ | Overlay test section coherent ✓ |
| BOILERPLATE_MIGRATION_SOP.md | §3.1.1 intact ✓ | §3.3 + drift cross-ref ✓ |

---

## Non-blocking observation (carried forward, not a bounce)

The overlay test reports 5 false failures when run inside a live orchestrator seat — inherited `ORCH_TOOLS` leaks into the awk `tools_override`. No AC requires a fix; CI runs in a clean env (24/24 there). Future test-hygiene pass: add `env -u ORCH_TOOLS …` guard inside the test script.

---

## Summary

| Criterion | Result |
|-----------|--------|
| AC1 — ADR-A-0022 (semantics, point, boundary, bidirectional link) | PASS |
| AC2 — spawn seam implementation + overlay test 24/24 + migrate 108/108 | PASS |
| AC3 — SOP §3.3 overlay-vs-fork decision table | PASS |
| bash -n + shellcheck -S error on spawn script | PASS |
| Rebase conflict resolutions coherent | PASS |

**Verdict: APPROVED** — all three ACs met on the rebased branch; all tests green in an independently run clean env; rebase resolutions preserve both sides.
