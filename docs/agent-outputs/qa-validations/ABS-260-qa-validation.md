# QA Validation — ABS-260

**Ticket**: De-Fork 3/3: consumer-feedback channel formalized in migration SOP (CSV export duty + upstream intake)  
**Branch**: `ABS-260-auto`  
**Commit**: `ddf1674`  
**Validator**: QAS  
**Date**: 2026-07-13  
**Verdict**: ✅ APPROVED

---

## What was reviewed

7 files, +190/−19 on `ABS-260-auto` (docs and templates only; no runtime code):

- `.agentic/templates/consumer-feedback-item.md` — new CSV item format template (AC1)
- `harness/claude/agents/boilerplate-migration.md` — export duty added (AC2)
- `harness/claude/agents/self-improvement.md` — export duty added (AC2)
- `agent_providers/claude_code/prompts/boilerplate-migration.md` — provider mirror (AC2)
- `agent_providers/claude_code/prompts/self-improvement.md` — provider mirror (AC2)
- `docs/sop/BOILERPLATE_MIGRATION_SOP.md` — §6 consumer-feedback channel added (AC3)
- `docs/sop/SELF_IMPROVEMENT_SOP.md` — §5 export duty added, consistent with agent defs (AC3)

---

## AC Verification

### AC1 — CSV/item format specified (template)

`.agentic/templates/consumer-feedback-item.md` exists and contains:
- **Header row verbatim**: `Summary,Type,Priority,Labels,Description` ✅
- **Type values**: `Bug | Improvement | Feature` ✅
- **Priority values**: `Highest | High | Medium | Low` ✅
- **Labels**: must contain `consumer-feedback`; add project slug ✅
- **Description = four mandatory blocks**: Finding / Repro / Fix / Fork ✅
- **RFC-4180 quoting rules**: documented (comma-in-field, embedded-quote doubling, multi-line inside single quoted field) ✅
- **Copy-paste skeleton** present ✅
- **Worked example** from the 2026-07-13 precedent batch (2 rows, 5 fields each) ✅

**Placement check**: `.agentic/templates/` is boilerplate-owned wholesale (`.agentic/upgrade/ownership.yaml` maps `.agentic/` with `config.yaml` and `overrides/` as the only exceptions). The ticket suggested `docs/sop/` or `specs_templates/`; neither is in the ownership map — a template there would never reach a consuming project. Placement under `.agentic/` is the correct call. Confirmed live by the implementer's 2.24.1→2.25.0 sandbox migration (`added` in the report).

`ls .agentic/templates/`: only `consumer-feedback-item.md` — directory contains the new file and nothing else.

**PASS.**

### AC2 — Export duty in boilerplate-migration.md + self-improvement.md (+ provider mirrors)

`harness/claude/agents/boilerplate-migration.md` diff (confirmed independently):
- Step 3 added: "Export the consumer-feedback items (ABS-260, MANDATORY)" with exact format reference, file path pattern, and the warning-not-failure rule for unexportable forks ✅
- Step 5 (formerly 4): commit amended to include the feedback CSV ✅
- `Write/Edit` tools scope updated to include `work/consumer-feedback/` ✅
- Key Principles: "Every Kept Fork Ships an Item" added ✅
- Phantom `feature-request.md` reference removed (replaced by the real template path) ✅

`harness/claude/agents/self-improvement.md` diff (confirmed independently):
- Export duty block added after the proposal fields section: one CSV row per boilerplate-owned finding, format per `.agentic/templates/consumer-feedback-item.md` ✅
- Report line added: "Consumer-feedback items exported: …" ✅
- `Write` scope extended to `work/consumer-feedback/` ✅

Provider mirrors match harness exactly:
```
diff harness/claude/agents/boilerplate-migration.md \
     agent_providers/claude_code/prompts/boilerplate-migration.md
→ MATCH

diff harness/claude/agents/self-improvement.md \
     agent_providers/claude_code/prompts/self-improvement.md
→ MATCH
```

`scripts/generate-governor.sh --providers --check` → **OK** (agent_providers/claude_code == generated(harness/claude))

No remaining references to phantom `.agentic/templates/feature-request.md` in any of the seven changed files.

**PASS.**

### AC3 — Intake section in BOILERPLATE_MIGRATION_SOP (upstream verdict response)

`docs/sop/BOILERPLATE_MIGRATION_SOP.md` bumped to v1.5, §6 added:

**§6.1 Consumer Side — Export Duty**:
- Format: 5-column CSV, `.agentic/templates/consumer-feedback-item.md` ✅
- Location: `work/consumer-feedback/YYYY-MM-DD-<project-slug>.csv`, committed on migration branch ✅
- Writer: boilerplate-migration agent (per conflict kept) + self-improvement agent (per boilerplate-level finding) ✅
- Warning-not-failure, driver-side check deferred to ABS-259 (honest about today's state) ✅
- Forwarding is human-only (ADR-A-0004 cited) ✅

**§6.2 Upstream Side — Intake**:
- Gate 1: dedup check via `duplicate-detection` skill before any ticket creation ✅
- Gate 2: verification against **HEAD** (not the consumer's installed version) ✅
- Gate 3: one verdict per item — `integrate` / `already-fixed` / `works-as-designed` — with defined meaning and upstream action per verdict ✅
- Verdict returned to consumer: ticket key / fixing version / rationale ✅
- Consumer records returned ticket key as `upstream_ref` (feeding ABS-259) ✅
- "No item is silently dropped" — every row ends in a verdict ✅

`docs/sop/SELF_IMPROVEMENT_SOP.md` §5 bumped to v1.1, consistent with agent def: references the template and the intake section, preserves human-gate rule. ✅

**PASS.**

---

## Test Results (re-run independently)

| Test | Result |
| ---- | ------ |
| `bash tests/test-migrate-project.sh` | **53/53 PASS** |
| `bash tests/test-harness-parity.sh` | **6/6 PASS** (governor drift guard: live `.claude/` == generated(v2.25.0)) |
| `scripts/generate-governor.sh --providers --check` | **OK** |

---

## Spot Checks

- `git check-ignore -v work/consumer-feedback/test.csv` → **NOT IGNORED** — the CSV output path is committable; the feedback artifact lands in the human-reviewed diff, not a gitignored scratch area.
- Frontmatter `tools:` field in both agent defs grants `Write`, so the mandated export step is executable (not just declared).
- All seven changed files: zero references to phantom `.agentic/templates/feature-request.md`.

---

## Follow-up (not a blocker, out of AC scope)

`adrs/agentic/ADR-A-0008:24` still references `.agentic/templates/feature-request.md` — a path that has never existed. The agent def and SOP references were corrected to point at the new template; the ADR's dangling pointer remains. Worth a small follow-up ticket. (Intentionally not fixed here per ADR-A-0010.)

---

## Verdict

All three ACs met. Tests green. Provider mirrors in sync. Output path committable. Export duty is executable, not merely declared (Write in frontmatter `tools:`). Honest about today's state (driver-side warning deferred to ABS-259).

**APPROVED → Story Acceptance.**
