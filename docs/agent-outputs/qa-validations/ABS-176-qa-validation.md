# QA Validation — ABS-176

**Ticket**: ABS-176 — Kontext-Packet byte-stabil cachen fuer Prompt-Cache-Hits bei Re-Spawns
**Branch**: `ABS-176-auto`
**Commit**: `0d9a835`
**Changed files**: `scripts/orchestrator.sh` (+36/-5), `tests/test-packet-cache.sh` (+130)
**Date**: 2026-07-10
**Validator**: QAS

---

## Acceptance Criteria Results

| AC | Description | Verdict | Evidence |
|----|-------------|---------|----------|
| AC1 | Two consecutive builds of same unchanged ticket are byte-identical | **PASS** | `test-packet-cache.sh` `cmp -s` assertion green |
| AC2 | Changed `updated` invalidates cache; next packet carries new state | **PASS** | 5 assertions: new-body present, old gone, packets differ, meta key updated, unchanged `updated` reuses verbatim |
| AC3 | Packet carries no content verbatim from role-def/commons | **PASS** | `skills:` header line confirmed removed (present in HEAD~1); 6 role-def files each retain their own skills guidance (grep verified); `tracker_cmd` + duty-note kept per ABS-180 |
| AC4 | Smoke: run.log shows `cache_read` at rework bounce | **EXTERNAL-DEPENDENCY** | Requires live provider API credentials + authorized spend (ADR-A-0004). Orchestrator precondition proven by AC1. Escalating to TDM. |
| AC5 | Existing packet tests unchanged green | **PASS** | ABS-135 from_status (2 tests), ABS-180 tracker_cmd/duty-note (3 tests), placement — all green in `test-orchestrator.sh` 448/455 |

---

## Test Runs (QAS-independent execution)

### tests/test-packet-cache.sh
```
Total: 12  Passed: 12  Failed: 0  — ALL TESTS PASSED
```
Covers: AC1 byte-identical rebuild, AC2 cache invalidation + cache-hit on unchanged `updated`, header-coordinate isolation (no stale from_status across seats), AC3 skills-line drop + duty-note retention.

### tests/test-orchestrator.sh
```
Total: 455  Passed: 448  Failed: 7
```
The 7 failures are pre-existing environmental (provenance `harness=` path, model-label/max-turns config resolved from the stable checkout, not this tmp worktree). The system-architect ran a controlled comparison (HEAD vs HEAD~1) confirming zero new failures attributable to ABS-176. The ABS-135, ABS-180, and ABS-163 groups are all green.

### tests/test-station-guard.sh
```
Total: 45  Passed: 45  Failed: 0  — ALL TESTS PASSED
```

### tests/test-intake-classification.sh
```
Total: 21  Passed: 21  Failed: 0  — ALL TESTS PASSED
```

### bash -n scripts/orchestrator.sh
```
SYNTAX OK
```

---

## AC3 Code Review Evidence

**Removed from header** (confirmed in `git diff HEAD~1..HEAD`):
```
skills: your role definition maps built-in/repo skills to this seat — invoke them via the Skill tool instead of rebuilding their content (ABS-123)
```

**Still present per role-def** (grep `.claude/agents/*.md`):
- `be-developer.md:309` — role-specific skills guidance
- `qas.md:458` — role-specific skills guidance
- `system-architect.md`, `fe-developer.md`, `rte.md`, `data-engineer.md` — each has equivalent guidance

**Kept in packet** (runtime-specific, per ABS-180):
- `tracker_cmd: <resolved-path>`
- `note: use tracker_cmd above...`

---

## AC4 Classification

**Type**: `external-dependency`
**Reason**: Live provider API credentials + authorized spend required. No agent can provision these (ADR-A-0004). The orchestrator-side precondition — a byte-stable packet — is provably implemented and verified by AC1. AC4 only observes the resulting cache-hit in a live run (`cache_read_input_tokens` in run.log).

**Action**: Escalating to TDM for live-env verification. Do NOT route to implementer.

---

## Non-Blocking Observations (from System Architect Stage 1)

The cache signature omits `TRACKER_CMD` and `ORCH_PACKET_MAX_BYTES`. Within a run these are constant; across runs a changed adapter path or cap could serve a stale packet. The architect flagged this as a cheap follow-up hardening (fold both into `sig`). Not gating this ticket.

---

## Verdict

**APPROVED for Story Acceptance**

AC1, AC2, AC3, AC5: all PASS. Implementation is correct and minimal (reuses `PACKETS_DIR`, `fm_field` helper, existing packet format). Zero new test failures.

AC4 is an `external-dependency` (live provider credentials + spend). The orchestrator-side condition is proven. Escalating to TDM for live-env verification — this does not block the implementation, which is sound.
