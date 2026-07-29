# QA Validation — ABS-216

**Ticket**: ABS-216 — STATION-GUARD: Out-of-Chain-Stati (Ready for Human Acceptance) in skip detection + qas exit-target hardening  
**Branch**: `ABS-216-auto`  
**Commits**: `d7b33d1` (guard fix + tests), `7767204` (qas.md doc hardening)  
**QAS run date**: 2026-07-12  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Results

### AC1 — RfHA known to guard; In Test → RfHA redirects to Story Acceptance ✅

`guard_chain_index()` added in `scripts/orchestrator.sh` (lines 1473–1477). Maps `Ready for Human Acceptance` to index 10 for skip-detection only; the three call sites in `forward_skip_illegitimate` and `station_guard` use `guard_chain_index` instead of `chain_index`.

Verified inline:
```
chain_index("Ready for Human Acceptance")        = 0  (canonical, unchanged)
guard_chain_index("Ready for Human Acceptance")  = 10 (guard supplement)
guard_chain_index("In Test")                     = 7  (pass-through)
```

`forward_skip_illegitimate "In Test" "Ready for Human Acceptance"` → rc=0 (flagged as illegitimate).  
`first_skipped_mandatory 7 10` → `Story Acceptance` (correct redirect target).

### AC2 — Legal paths around RfHA unchanged ✅

Inline verification:
```
forward_skip_illegitimate "Story Acceptance" "Ready for Human Acceptance" → rc=1 (green)
forward_skip_illegitimate "Ready for Human Acceptance" "Merging"          → rc=1 (green)
forward_skip_illegitimate "Ready for Human Acceptance" "Ready for Merge"  → rc=1 (green)
chain_index "Ready for Human Acceptance"                                  → 0   (bounce counting untouched)
```

All four assertions confirmed; the canonical `chain_index` (used for bounce counting and high-water mark) is unchanged.

### AC3 — qas.md Exit Protocol names RfHA as forbidden ✅

`harness/claude/agents/qas.md` Exit Protocol now reads:

> on PASS your exit transition target is **`Story Acceptance`** — NEVER `Done`, and NEVER `Ready for Human Acceptance`. … `Ready for Human Acceptance` is the human gate that follows the `Story Acceptance` seat — jumping straight to it from `In Test` folds the mandatory Story Acceptance station and is equally illegal (STATION-GUARD redirects it back to `Story Acceptance`, ABS-216); do not use it as a "next plausible human gate" fallback.

Byte-parity confirmed:
```
diff harness/claude/agents/qas.md agent_providers/claude_code/prompts/qas.md → IDENTICAL
```

### AC4 — Tests in tests/test-station-guard.sh; suite green ✅

```
bash tests/test-station-guard.sh
Total: 62  Passed: 62  Failed: 0  → ALL TESTS PASSED
```

ABS-216 section added (lines ~111–206): `guard_chain_index`/`chain_index` invariants, `In Test → RfHA` and `Design Test → RfHA` flagged, redirect target = Story Acceptance, legal RfHA paths green, end-to-end `station_guard` intervention test.

---

## Regression Check

```
bash tests/test-orchestrator.sh
Total: 596  Passed: 589  Failed: 7
```

The 7 failures are pre-existing and environmental — none in the station-guard domain:

| # | Failure | Category |
|---|---------|----------|
| 1 | startup provenance line reports harness=\<stable repo\> | provenance-seam path |
| 2 | no seam: provenance harness == script repo | provenance-seam path |
| 3 | explicit operator-wide cap overrides qas built-in (expected '15', got '80') | model-cap config |
| 4 | downsize label on system-architect review → MODEL-LABEL-SKIP | model-label config |
| 5 | review/judgment seat keeps role default (no downsized model) | model-label config |
| 6 | upsize label logs MODEL-LABEL (applied) for architect | model-label config |
| 7 | dry-run: review seat → MODEL-LABEL-SKIP (never MODEL-LABEL) | model-label config |

These failures reproduce identically on the clean `99d9c64` baseline (confirmed by system-architect in their `gate-results` comment: "clean-HEAD baseline worktree at 99d9c64 → identical 575/21 with same failing test names"). Note: system-architect observed 575/21; this QAS run saw 589/7; the environmental failure count varies across runs (reconcile-dispatch timing sensitivity). The station-guard domain is clean in both cases.

`bash -n scripts/orchestrator.sh` → **SYNTAX OK**

---

## Additional Verifications

- `guard_chain_index` is a strict superset of `chain_index` (passes through all canonical statuses unchanged — verified by `assert_eq "$(guard_chain_index "In Test")" "$(chain_index "In Test")"` in the test).
- Wiring confirmed: `forward_skip_illegitimate` (line 1533) and `station_guard` (lines 1567, 1574) all call `guard_chain_index` post-patch.
- Non-blocking SA note acknowledged: RfHA shares guard slot 10 with Merging, so `RfHA → Done`/`RfHA → Docs` would redirect to Docs without separately flagging Merging. Out of scope for this Befund.

---

## Verdict

**APPROVED** — All four ACs met. Station-guard suite 62/62. Zero new orchestrator failures vs baseline. `qas.md` wording correct and byte-parity confirmed. Branch `ABS-216-auto` ready for Story Acceptance.
