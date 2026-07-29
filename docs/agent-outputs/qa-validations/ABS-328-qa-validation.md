# QA Validation Report — ABS-328

**Ticket**: ABS-328 — Koexistenz S2: Divergenz-Reporter `tracker-divergence.sh`  
**Branch**: `ABS-326-koexistenz` (commit 46af22e + HEAD)  
**QAS actor**: qas  
**Date**: 2026-07-16  
**Verdict**: ✅ **APPROVED**

---

## Validation Summary

| Check | Result |
|---|---|
| `bash -n` syntax clean — tracker-divergence.sh | ✅ PASS |
| `bash -n` syntax clean — test-tracker-divergence.sh | ✅ PASS |
| Full test suite (18 assertions) | ✅ 18/18 PASS |
| AC1: field divergences with both values; explained entries non-gating | ✅ PASS |
| AC2: injected status drift detected on next run | ✅ PASS |
| AC3: read-only — no mutating verbs to any adapter | ✅ PASS |
| Source audit: only `search`/`get` passed to adapters | ✅ PASS |
| Secret hygiene: token via `--config`, never argv | ✅ PASS |
| Exit codes: 0=clean, 1=unexplained, 2=error | ✅ PASS |

---

## Test Run Output

```
=== tracker-divergence.sh — divergence reporter (ABS-328) ===

[1] identical trackers -> exit 0, clean report
  PASS exit 0 on identical trackers
  PASS report.json: unexplained_count 0
  PASS report.json: both fenced tickets compared
  PASS history line appended with unexplained=0

[2] injected status drift is detected on the next run
  PASS exit 1 (unexplained divergence gates)
  PASS exactly the drifted field reported
  PASS report carries BOTH values (AC 1)
  PASS markdown report lists both values

[3] whitelisted divergence: listed but not gating
  PASS exit 0 when every divergence is explained
  PASS entry still listed, marked explained
  PASS markdown report shows the whitelist reason

[4] ticket missing on the mirror -> presence divergence
  PASS exit 1 on missing mirror ticket
  PASS presence divergence names the missing side

[5] comment-count drift detected
  PASS exit 1 on comment-count drift
  PASS comment counts reported from both sides

[6] read-only: only search/get ever reach an adapter
  PASS recorded adapter calls across ALL runs are search/get only
  PASS script source invokes no mutating adapter verb
  PASS the only HTTP call in the source is the read-only search/jql query

All 18 assertions passed
```

---

## AC Verification Detail

### AC1 — Report lists every field divergence with both values; explained entries marked and non-gating

- **Test [2]**: `write_ticket back-b ABS-101 Blocked` (drift: Doing→Blocked). Report carries both values: `primary=Doing / mirror=Blocked`. ✅  
- **Test [3]**: Whitelist rule `ABS-10*|status|migration backfill pending (test)` → `explained_count=1`, `exit 0`, reason shown in markdown. ✅  
- **Source**: Python block emits `{key, field, primary, mirror, explained}` for every divergence entry; `unexplained` list drives exit code only. ✅

### AC2 — Artificially created status drift detected on next run

- **Test [2]**: `write_ticket "$TEST_DIR/back-b" ABS-101 Blocked 2` injects status drift. Reporter detects `field=status`, `primary=Doing`, `mirror=Blocked`, `exit=1`. ✅  
- Exactly the drifted field is reported (`['status']`), no spurious fields. ✅

### AC3 — Read-only: no writes on Jira or Backend, provable per audit

- **Source audit** (test [6]): `grep -E '(PRIMARY|MIRROR)_CMD" (create|update|comment|transition|link|assign)'` → **0 matches**. ✅  
- **Adapter call recording**: all calls across all test runs recorded to `calls.txt`; `grep -cv '^(search$|get )' calls.txt` → **0** (only `search` and `get` ever reached an adapter). ✅  
- **Only HTTP call**: `POST /rest/api/3/search/jql` — the same read-only query endpoint the Jira adapter uses for every search. Not a write. ✅  
- **Token hygiene**: `printf 'user = "%s:%s"\n' "$JIRA_EMAIL" "$JIRA_API_TOKEN" > "$curlcfg"` then `curl --config "$curlcfg"` — never exposed in argv. ✅

---

## Architecture Review Follow-Ups (advisory, non-blocking)

Per the architect's Stage 1 review:

1. **Python heredoc crash → exit 1 vs exit 2** (MEDIUM): A python uncaught exception exits the heredoc with 1, reported as "unexplained divergence" rather than error. Gate stays red (safe fail-closed). Advisory: consider `trap` to exit 2. **Does not block this story.**
2. **fixVersion sweep `maxResults=100` single-page** (MEDIUM): Fine for the current small shadow fence; pagination warranted before the fence grows. **Does not block this story.**

---

## Exit Routing

- `flags` line: **none** → no `design` flag  
- Exit target: **Story Acceptance**

---

## Verdict

**APPROVED** — All 3 acceptance criteria satisfied, 18/18 test assertions PASS, read-only guarantee proven by source audit + runtime adapter-call recording. Releasing to Story Acceptance.
