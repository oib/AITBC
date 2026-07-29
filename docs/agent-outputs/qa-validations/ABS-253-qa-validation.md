# QA Validation — ABS-253

**Branch**: ABS-253-auto  
**Commits under review**: `2b31d2b` + `5aaa610` (rebased from `4e1aff5` + `f10c7f3`)  
**Validator**: qas  
**Date**: 2026-07-13  
**Verdict**: ✅ APPROVED

---

## AC1 — Explicit exit-transition block in be/fe/data-engineer; SOP corrected

**Result**: PASS

Verified independently on `5aaa610`:

| Def | Exit protocol present | Canonical `In Review` target | `work/scratch/` draft path | `--reason-file` | `--expect-from` | Positional status arg |
|-----|----------------------|-----------------------------|-----------------------------|-----------------|-----------------|----------------------|
| `harness/claude/agents/be-developer.md` | ✓ (line 235) | ✓ | ✓ (line 248–249) | ✓ | ✓ | ✓ |
| `harness/claude/agents/fe-developer.md` | ✓ (line 206) | ✓ | ✓ (line 219–220) | ✓ | ✓ | ✓ |
| `harness/claude/agents/data-engineer.md` | ✓ (line 287) | ✓ | ✓ (line 301–302) | ✓ | ✓ | ✓ |

Provider mirror parity: `diff` on be/fe/data-engineer between `harness/claude/agents/` and `agent_providers/claude_code/prompts/` → all IDENTICAL.

`/tmp` draft path check: `git grep '/tmp/'` over all 6 files returns only the prose warning against it — zero recipe sites.

SOP (`docs/sop/AGENT_WORKFLOW_SOP.md`): `Exit States` table split into `Exit status (transition target)` + `Handoff label` columns. BE/FE/DE row = `In Review` / `"Ready for QAS"`. All nine statuses asserted in the table confirmed present in `profiles/neutral/adapters/statuses.yaml`.

`Ready for QAS` absent from `statuses.yaml`; `In Review` edge present.

---

## AC2 — issue-enrichment.md names sanctioned default path; settings.template.json allowlisted

**Result**: PASS (one minor follow-up observation below)

`harness/claude/agents/issue-enrichment.md`:

- `create` flow: `work/scratch/enrichment-body-$$.md` with `mkdir -p work/scratch` (line 77–78)
- `append` flow: `work/scratch/match-current.md` (line 98)
- Normative note (lines 85–92): explicitly names `work/scratch/**` as the sole sanctioned path; names bare `$(mktemp)` as denied under `--permission-mode dontAsk`

Settings templates:

| File | `Write(work/scratch/**)` | `Edit(work/scratch/**)` | Valid JSON |
|------|--------------------------|--------------------------|-----------|
| `harness/claude/settings.template.json` | ✓ | ✓ | ✓ |
| `agent_providers/claude_code/permissions/settings.template.json` | ✓ | ✓ | ✓ |

`.gitignore` line 164: `work/scratch/` gitignored. `git check-ignore -v work/scratch/test.md` confirms.

**Minor observation** (not blocking): `harness/claude/skills/issue-enrichment/SKILL.md` lines 225–226 (the `append` example block) still contain `> /tmp/match-current.md` and `BODY_FILE="$(mktemp)"`. The normative text two lines above explicitly prohibits both patterns. The DEF itself is correct; this is a self-contradictory example in a supplementary skill doc. The SA flagged `qas-design.md:98` as a follow-up candidate under ABS-245 using the same standard. This item qualifies for the same treatment. The SKILL.md's `create` examples (the common path) are fixed; only the `append` example has the residual pattern.

---

## AC3 — Parity test green

**Result**: PASS

```
tests/test-harness-parity.sh (run on ABS-253-auto, 2026-07-13):

  Total:  6
  Passed: 6
  Failed: 0

  ALL TESTS PASSED
```

Tests include: governor drift guard, LOCAL-RUNTIME exclusion, generator exclusion, wrong-entry-guard registration, `--providers --check` byte-parity, `--providers` mirror mode.

---

## Summary

| Criterion | Result | Notes |
|-----------|--------|-------|
| AC1: be/fe/data-engineer exit blocks | PASS | All 3 defs + mirror verified; SOP fixed |
| AC2: issue-enrichment sanctioned path + allowlist | PASS | DEF correct; minor SKILL.md append example follow-up (ABS-245) |
| AC3: parity test | PASS | 6/6 |

**Verdict: APPROVED — advancing to Story Acceptance.**

Follow-up candidate (ABS-245): `harness/claude/skills/issue-enrichment/SKILL.md` lines 225–226 append example still uses `/tmp/` and `$(mktemp)`. Same pattern as `qas-design.md:98`; same resolution (separate ticket).
