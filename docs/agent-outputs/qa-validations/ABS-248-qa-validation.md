# QA Validation Report — ABS-248

**Ticket**: ABS-248 — Migration-Treiber: Harness-Surface fehlt in ownership.yaml  
**Branch**: `ABS-248-auto` (commits `1ff6ab3` + `e5ced3a`)  
**Validated against**: ADR-A-0008 Amendment 2026-07-14 (supersedes ticket AC1–AC3 per system-architect; BSA re-spec waived)  
**Date**: 2026-07-14  
**QAS actor**: qas  
**Verdict**: ✅ **APPROVED**

---

## Validation Scope

The system-architect (design-first seat) waived the BSA re-spec and declared the ADR's five
implementation notes authoritative over the ticket's original AC1–AC3. QAS validates against
those notes, not the ticket body.

### ADR ACs verified (from ADR-A-0008 Amendment § Implementation notes)

| # | Description | Result |
|---|-------------|--------|
| (a) | Harness census is non-empty: driver now enumerates 104 `.claude/` paths | ✅ PASS |
| (b) | Token-substituted harness file classifies **REPLACE, not CONFLICT** (ABS-249 regression guard) | ✅ PASS |
| (c) | `team-config.json` / `hooks-config.json` byte-unchanged after migration (upstream rewrote both) | ✅ PASS |
| (d) | `sync_scope` gate: a Claude-only target receives **zero** `.gemini/` ADDs | ✅ PASS |
| (e) | No delegation invoked — the dead DELEGATE_CLAUDE block is gone | ✅ PASS |

---

## Test Evidence

### test-migrate-project.sh — 120/120 PASSED

Run from: `tmp/ABS-248-work` (worktree for `ABS-248-auto`)

```
Total:  120
Passed: 120
Failed: 0
ALL TESTS PASSED
```

**ABS-248-specific assertions (all PASS):**

| Assertion | Result |
|-----------|--------|
| AC1: driver exits 0 with the harness surface mapped | ✅ PASS |
| AC1: a pristine harness agent-def is REPLACED with upstream v2 (census non-empty) | ✅ PASS |
| AC1: a brand-new upstream harness file is ADDed | ✅ PASS |
| AC2: a token-substituted harness file is REPLACED and re-instantiated (BUSCH), not left at v1 | ✅ PASS |
| AC2 (ABS-249 regression guard): instantiated harness classifies REPLACE, NOT phantom CONFLICT | ✅ PASS |
| AC3: .claude/team-config.json byte-unchanged (identity never clobbered) | ✅ PASS |
| AC3: .claude/hooks-config.json byte-unchanged | ✅ PASS |
| AC3: an identity exception is never reported as a CONFLICT | ✅ PASS |
| AC4: Claude-only target (default sync_scope) receives ZERO .gemini/ ADDs | ✅ PASS |
| AC5: driver never delegates to sync-claude-harness.sh | ✅ PASS |
| AC4: a target that ADOPTS .gemini in sync_scope DOES receive the .gemini harness | ✅ PASS |
| AC3: manifest `protected:` harness file honored (v1.0 scope-relative path normalized) | ✅ PASS |

### test-adr-status.sh — 31/31 PASSED

```
ADR status guard: 31 passed, 0 failed
```

ADR-A-0008 (status: accepted, base + ABS-228 amendment) passes. The ABS-248 amendment is
correctly `status: proposed` (human acceptance required, ADR-A-0004).

### test-harness-parity.sh — 6/6 PASSED

```
Total:  6
Passed: 6
Failed: 0
ALL TESTS PASSED
```

No harness-parity regression.

### shellcheck — CLEAN (error-level)

```
shellcheck -S error scripts/migrate-project.sh
exit code: 0
```

Only pre-existing `info`-level hints (SC2012, SC2015, SC2295) — none introduced by ABS-248.

---

## Independent Verification Claims

### Census: 0 → 104

Before ABS-248, `ownership.yaml` had no harness domain → `git ls-files -- '.claude/'` yielded
0 paths in the driver → the harness never migrated. After:

```
git ls-files --with-tree=ABS-248-auto -- '.claude/' | wc -l
104
```

### Six harness domains in ownership.yaml

`boilerplate_owned:` now contains: `.claude/`, `.gemini/`, `.codex/`, `.cursor/`, `.agents/`,
`dark-factory/`. `project_owned_exceptions:` now contains `.claude/team-config.json` (structural)
and `.claude/hooks-config.json` (structural).

### DELEGATE_CLAUDE block retired

```bash
grep "DELEGATE_CLAUDE" scripts/migrate-project.sh
# Result: only in comments explaining the removal — no executable block
```

`sync-claude-harness.sh` is untouched (standalone consumer tool contract unchanged).

### Q1 premise verified at tag (architect claim upheld)

`git ls-files --with-tree=ABS-248-auto -- '.claude/' | wc -l` = 104 (same as on main/ABS-248-auto
since `.claude/` is the promoted artifact at the tag, consistent with ADR-A-0016).

---

## Non-Blocking Follow-ups (architect-named, not blocking approval)

1. **MEDIUM** — `protected:` entries are matched literally, but the schema documents them as globs. A glob covering an upstream path wouldn't be honored. Bounded (clean-tree precondition, real manifests use literal paths).
2. **LOW** — `MIGRATE_EXCEPTIONS` is now orphaned in `sync-claude-harness.sh` (newly-dead code, same defect class ABS-248 fixes). The ADR ring-fences that script; someone should file a follow-up.

Neither is blocking. Both were named by the architect and accepted into the handoff without bounce.

---

## Human Action Required ⚠️

**ADR-A-0008 Amendment 2026-07-14 stays `status: proposed`.**  
Human acceptance (ADR-A-0004) is required before/at epic merge.  
The code is on the branch and the tests prove it correct — but the decision is not ratified until the operator accepts the ADR.

---

## Summary

All ADR-mandated gates pass. The implementation:
- adds the six harness domains to ownership.yaml (Q1)
- gates non-`.claude` domains on `sync_scope` (Q2)
- retires the broken DELEGATE_CLAUDE block (Q3)
- protects identity files via `project_owned_exceptions` + manifest `protected:` fold (Q4)
- explicitly out-of-scopes renames (Q5)

The three-release consumer pain ("`.claude` delta manuell") is resolved for the next upgrade cycle.

**Verdict: APPROVED** — transition to Design Test (design-first flag present).
