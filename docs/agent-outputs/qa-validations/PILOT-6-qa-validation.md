# QA Validation Report — PILOT-6

**Ticket**: PILOT-6 — v3-Parität: lane als First-Class-Spalte im Agentic Backend + backend-tracker.sh --lane  
**Branch**: PILOT-6-auto  
**Commit under test**: `c4ce39caeb23255555e72fdcfb5228d9f7c060f4`  
**QAS actor**: qas  
**Date**: 2026-07-22 (cycle 3 — re-validation after second RTE rebase-forward; migration renumbered 015→016→018 following PILOT-8 `relates` merge)  
**Verdict**: ✅ APPROVED

---

## AC Verification Matrix

| # | Acceptance Criterion | Evidence | Result |
|---|---------------------|----------|--------|
| AC1 | `create --lane fastlane` → `get` shows `lane: fastlane`; without `--lane` shows `lane: normal` (ABS-374: never port 8420) | Conformance Test 23 (ephemeral Docker :56014, ABS-374-compliant): "create without --lane yields lane: normal" ✔, "create --lane fastlane surfaces via get" ✔ — run live by QAS at `c4ce39ca` | ✅ PASS |
| AC2 | `update <id> lane fastlane` flips field; invalid values → Exit ≠ 0, wording mock-identical | Conformance Test 23: "update lane prints the canonical success line" ✔, "update lane fastlane flips the field" ✔, "update lane normal flips it back" ✔, "create/update --lane with invalid value is rejected" ✔ (nonzero exit). Wording: `create: invalid lane '…' (normal\|fastlane)` / `update: lane must be 'normal' or 'fastlane'` — byte-identical to mock-tracker.sh lines 316/484 | ✅ PASS |
| AC3 | `search --lane fastlane` returns exactly fastlane tickets (2 tickets, one per lane, filtered list) | Conformance Test 23: "search --lane fastlane includes the fastlane ticket" ✔, "search --lane fastlane excludes a normal-lane ticket" ✔ | ✅ PASS |
| AC4 | Frontmatter render byte-identical to `mock-tracker.sh get` (ADR-A-0021) | render.ts line 110: `lines.push(\`lane: \${fm.lane \|\| "normal"}\`)` immediately after `parent:` at line 106. mock-tracker.sh line 407: `echo "lane: $lane"` immediately after `parent:` at line 403. Ordering and field-not-label contract confirmed. 14/14 Test-23 byte-parity assertions PASS. ADR-A-0026: `lane:` is a frontmatter field, not a `lane:<x>` label token (asserted and passing). | ✅ PASS |
| AC5 | Migration `018_work_item_lane.sql` additive; git diff over pre-PILOT-6 migrations is empty; idempotent at second boot | `git diff remotes/gitlab/epic/PILOT-5-backend-jira-parity..PILOT-6-auto -- backend/packages/core/src/migrations/` shows ONLY `018_work_item_lane.sql` added (+19 lines). All 001–017 migrations zero diff. Migration: `ALTER TABLE work_item ADD COLUMN lane text NOT NULL DEFAULT 'normal' CHECK (lane IN ('normal', 'fastlane'))` + index — additive/idempotent (migrate.ts uses `schema_migrations` table to skip already-applied files; second boot is a no-op). Note: AC text says "001..013" — written pre-PILOT-8 merge; material criterion (all pre-lane migrations untouched, only one lane migration added) holds. | ✅ PASS |
| AC6 | `items-routes.test.ts` covers lane in create/update/search | items-routes.test.ts: 19 lane references; test covers create (default normal + fastlane opt-in), invalid create (400 + mock wording), update flip + invalid (400 + mock wording), search filter (include/exclude). DB-gated SKIP without DATABASE_URL (`{ skip: !BASE_URL }`; same gate as 217 other server tests). Equivalent live-backend coverage via conformance Test 23 (ephemeral Docker, self-provisioned). | ✅ PASS |

---

## Test Run Evidence (QAS-independent, cycle 3)

### Conformance Suite (tests/test-backend-tracker.sh) — PRIMARY LIVE-BACKEND PROOF

```
Command: bash tests/test-backend-tracker.sh
Commit:  c4ce39caeb23255555e72fdcfb5228d9f7c060f4  (PILOT-6-auto HEAD)
Backend: ephemeral Docker port :56014 (never :8420 — ABS-374 compliant)
Project: betrack54514 (throwaway, torn down on exit)

Total:  208
Passed: 208
Failed: 0

ALL CONFORMANCE ASSERTIONS PASSED

Test 23 — lane (PILOT-6/ABS-319) — 14/14 PASS:
  ✔ create without --lane yields lane: normal
  ✔ create --lane fastlane surfaces via get
  ✔ lane fastlane ticket carries no labels list
  ✔ lane is a field, not a lane:<x> label token
  ✔ update lane prints the canonical success line
  ✔ update lane fastlane flips the field
  ✔ update lane normal flips it back
  ✔ search --lane fastlane includes the fastlane ticket
  ✔ search --lane fastlane excludes a normal-lane ticket
  ✔ lane survives alongside role/flags/labels
  ✔ flags survive alongside lane
  ✔ labels survive alongside lane
  ✔ create --lane with an invalid value is rejected
  ✔ update lane with an invalid value is rejected

Note: "ABS-426 bite proof: induced mint failure" shows FAIL intentionally —
this is an anti-silent-pass assertion that verifies the suite itself cannot
auto-pass a real failure. The immediately following PASS assertion confirms
the bite-proof check works. This is not a product failure.
```

### Backend pnpm Tests (pnpm -r test)

```
Command: pnpm -r test  (run in backend/ at c4ce39ca)

apps/web:          pass 75,  fail 0,  skip 0
packages/core:     pass 142, fail 0,  skip 106  (DB-gated)
packages/webhooks: pass 6,   fail 0,  skip 10   (DB-gated)
packages/forge:    pass 18,  fail 0,  skip 7    (DB-gated)
apps/server:       pass 7,   fail 0,  skip 217  (DB-gated, incl. lane HTTP test)

Total active (non-skip): 248 PASS, 0 FAIL
```

### Migration Additivity Verification

```
git diff remotes/gitlab/epic/PILOT-5-backend-jira-parity..PILOT-6-auto \
  -- backend/packages/core/src/migrations/ | grep "^diff"

→  diff --git a/backend/packages/core/src/migrations/018_work_item_lane.sql \
              b/backend/packages/core/src/migrations/018_work_item_lane.sql

Only ONE file appears (the new 018 lane migration). 001–017 zero diff.
```

### Implementation Spot-Check

```
render.ts:106  lines.push(fm.parent ? `parent: ${fm.parent}` : "parent:");
render.ts:110  lines.push(`lane: ${fm.lane || "normal"}`);   ← after parent:

mock-tracker.sh:403  if [ -n "$parent" ]; then echo "parent: $parent"; … fi
mock-tracker.sh:407  echo "lane: $lane"                                ← after parent:

items.ts:83    const LANES = new Set(["normal", "fastlane"]);
items.ts:388   if (!LANES.has(lane)) throw new OpError(400, `create: invalid lane '${lane}' (normal|fastlane)`);
items.ts:561   if (value !== "normal" && value !== "fastlane") throw new OpError(400, "update: lane must be 'normal' or 'fastlane'");

backend-tracker.sh:179  --lane) ... q+=( --data-urlencode "lane=$2" );  (search)
backend-tracker.sh:200  --lane) ... lane="$2";                           (create)
```

---

## Guardrail Checks

| Guardrail | Status |
|-----------|--------|
| ABS-374 (no port 8420) | ✅ Conformance suite on :56014 (ephemeral, never :8420) |
| ADR-A-0021 (byte parity) | ✅ render.ts line 110 matches mock-tracker.sh line 407 — same field, same position after parent: |
| ADR-A-0026 (field not label) | ✅ `lane:` frontmatter field; Test 23 asserts no labels list and no `lane:fastlane` label token |
| Migration additivity (001–017 untouched) | ✅ Zero diff on pre-PILOT-6 migrations confirmed |
| No render-path changes beyond lane line | ✅ Only `lane:` emit added; no restructuring of existing render paths |
| Error wording mock-identical | ✅ Verified by source code inspection and conformance Test 23 nonzero-exit assertions |

---

## Cycle History

| Cycle | Commit | Conformance | Notes |
|-------|--------|-------------|-------|
| 1 | `2b45dbf8` | 205/205 PASS | Initial; migration `015_work_item_lane.sql` |
| 2 | `cd8fb893` | 208/208 PASS | After PILOT-8 rebase; renumbered to `016` |
| 3 (this run) | `c4ce39ca` | 208/208 PASS | After second rebase; renumbered to `018` (PILOT-8 `relates`=015, `016`=project-version, `017`=attachment) |

All three cycles PASS; zero regressions introduced across rebases.

---

## Flags Check

`flags: [data]` — no `design` flag.  
**Exit target**: Story Acceptance (not Design Test).

---

**QAS Verdict: APPROVED** — All 6 ACs independently verified against live backend evidence at `c4ce39ca`. 208/208 conformance assertions PASS (14/14 lane). 248 active pnpm tests PASS, 0 FAIL. Migration `018_work_item_lane.sql` additive, 001–017 byte-unchanged.
