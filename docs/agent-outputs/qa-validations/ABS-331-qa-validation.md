# QA Validation Report — ABS-331

**Ticket**: ABS-331 — jira-tracker search: emit canonical priority column + ORDER BY created ASC  
**QA Actor**: qas  
**Date**: 2026-07-17  
**Commit reviewed**: `71e369c` on branch `ABS-331-auto`  
**Verdict**: ✅ **APPROVED**

---

## AC Verification Summary

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | `jira-tracker search` (and `mock-tracker.sh search`) emits a `priority` column; absent/unmapped ⇒ `normal` | ✅ PASS | `ABS-331 AC1` assertions (3/3); `test-jira-tracker.sh` 159/159; `test-mock-tracker.sh` 180/180 |
| AC2 | Search JQL carries `ORDER BY created ASC`; age-ASC results within fence; equal-timestamp stable tiebreak | ✅ PASS | `ABS-331 AC2` assertions (2/2); line 900 of `jira-tracker.sh`; mock `sort -k1,1 -s` |
| AC3 | `prioritize_rows` reads priority from search column → 0 per-row `tracker get`; falls back only on legacy 4-field rows; no false-positive on legacy `title="high"` | ✅ PASS | `test-abs331-prioritize-rows.sh` 10/10 (call-logging stub proves zero gets) |
| AC4 | Full backward compat; no-priority tree dispatches byte-identically feature-on vs off; full orchestrator suite stays green | ✅ PASS | orchestrator suite 1106/1106 PASS (scrubbed env); `ABS-331 AC4` (3/3) |
| AC5 | `bash -n` clean on all 3 scripts; `generate-governor.sh --providers --check` OK | ✅ PASS | All `bash -n` OK; generate-governor check: `agent_providers/claude_code == generated(harness/claude)` |

---

## Test Suite Results

| Suite | Run | Result |
|-------|-----|--------|
| `tests/test-abs331-prioritize-rows.sh` | `bash tests/test-abs331-prioritize-rows.sh` | **10/10 PASS** |
| `tests/test-jira-tracker.sh` | `bash tests/test-jira-tracker.sh` | **159/159 PASS** (1 skipped: live-smoke) |
| `tests/test-mock-tracker.sh` | `bash tests/test-mock-tracker.sh` | **180/180 PASS** |
| `tests/test-orchestrator.sh` (full suite, scrubbed env) | `env -i … bash tests/test-orchestrator.sh` | **1106/1106 PASS** |
| `ABS-331-search-priority.sh` (in orchestrator suite) | included above | **8/8 PASS** |

**Total assertions verified: 1465/1465 PASS (0 failures)**

---

## AC1 Deep-Dive

`jira-tracker.sh` `jql_search()` already requests `labels` in its fields list (line 548). `cmd_search()` extracts priority via `row_priority(labels)` (lines 933-942): iterates labels for `priority:<value>`, validates against `{hotfix,high,normal,low}`, defaults to `normal`. Emits 5-column row: `id\ttype\tstatus\tpriority\ttitle`. `mock-tracker.sh` mirrors via `fm_get priority; priority="${priority:-normal}"`.

## AC2 Deep-Dive

`jira-tracker.sh` `cmd_search()` line 900: `jql="$jql ORDER BY created ASC"` — appended after all `AND` filters (ORDER BY must be final element). `mock-tracker.sh` prepends `created` timestamp to sort key, stable-sorts (`-s`), then strips it with `cut -f2-`.

## AC3 Deep-Dive

`prioritize_rows` in `orchestrator.sh`: peels first 3 tab fields to expose field 4; detects a 5th field via `[ "$rest" != "${rest#*"$tab"}" ]`. If present → reads `f4` (hotfix|high|normal|low), defaults to `normal` for unmapped values, **zero `ticket_priority` calls**. If absent (4-field legacy row) → falls back to `ticket_priority "$id"`. Lines preserved verbatim via `printf '%s\t%010d\t%s\n' "$rank" "$i" "$line"`. The call-logging stub in `test-abs331-prioritize-rows.sh` writes to a file per call (pipeline-safe) and counts prove 0 gets for 5-field rows, 2 gets for 2 legacy 4-field rows.

## AC4 Deep-Dive

Orchestrator suite run in `env -i HOME=… PATH=… TMPDIR=…` (same scrubbed-env technique as architect's review). 1106/1106 PASS — 88 more than the architect's 1018 because ABS-336 assertions were added post-architect-review. All sweep loops (`read -r id type status _title` with underscore catch-all) absorb the new column harmlessly. `cut -f1` (L1309) likewise unaffected.

## AC5 Deep-Dive

```
bash -n scripts/jira-tracker.sh  → OK
bash -n scripts/mock-tracker.sh  → OK
bash -n scripts/orchestrator.sh  → OK
generate-governor.sh --providers --check → OK (agent_providers/claude_code == generated(harness/claude))
```

---

## Scope "Out" Adherence

Verified via `git diff gitlab/main..71e369c`:
- ✅ No changes to ABS-261 dispatch/cap/preemption logic
- ✅ No changes to ABS-242 canonical mapping (only consumes it via `priority:<value>` label)
- ✅ No changes to `ORCH_PRIORITY_DISPATCH` or `ORCH_HOTFIX_CAP_BONUS` knobs

---

## Final Verdict

**APPROVED** — All 5 ACs met, 1465/1465 test assertions PASS, bash-n clean, governor check OK, scope "Out" honoured.  
No `design` flag → transitioning to **Story Acceptance**.
