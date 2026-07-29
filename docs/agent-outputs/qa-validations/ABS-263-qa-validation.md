# QAS Validation Report — ABS-263

**Ticket**: ABS-263 — Windows/MSYS: tracker adapter request/write path over argv limit  
**Branch**: ABS-263-auto @ 3ca1c9e  
**QAS run date**: 2026-07-13  
**Verdict**: APPROVED

---

## AC Verification

### AC1 — http_call request body via @file, temp file cleaned on all paths

`grep -n 'data-binary' scripts/jira-tracker.sh` returns:
```
321:    # Deliver the request body to curl through a temp FILE (--data-binary "@file"),
333:            -X "$method" --data-binary "@$bodyfile" "$url" 2>"$err")"
```

Line 341: `[ -z "$bodyfile" ] || rm -f "$bodyfile"` — runs unconditionally before the error-exit `die` at line 348. Temp file freed on success and every error path.  
**PASS**

### AC2 — No adapter request payload on argv

```
grep -c 'json.loads(sys.argv' scripts/jira-tracker.sh
0
```

`post_structured_comment` (ADF) and `cmd_create` (description) both pipe via `printf | py` and read with `sys.stdin.read()`. No request payload crosses argv.  
**PASS**

### AC3 — Both curl shims resolve --data-binary @file

`jira-curl-shim.sh:59-60`:
```bash
--data-binary)
    if [ "${2#@}" != "$2" ]; then reqbody="$(cat "${2#@}")"; else reqbody="$2"; fi
```

`jira-version-curl-shim.sh:27-28`:
```bash
--data-binary)
    if [ "${2#@}" != "$2" ]; then body="$(cat "${2#@}")"; else body="$2"; fi
```

Both shims exercise the real write path in tests.  
**PASS**

### AC4 — Oversized write-path regression test (Test 9h)

Test 9h posts a ~2 MB comment body (past this host's ARG_MAX) via `--body-file` and asserts:
- exit 0 (no E2BIG)
- `WRITE-PATH-MARKER` end marker present in the captured request body (full payload, not truncated)

Run result (this QAS session):
```
PASS  comment with a ~2MB body exits 0
PASS  no E2BIG: request body never crosses the argv boundary
PASS  oversized comment reports success
PASS  the full oversized body reached the request (posted, not dropped)
```
**PASS**

### AC5 — Lint guard in test-tracker-adapter-lint.sh

Guard asserts no `json.loads(sys.argv` in `jira-tracker.sh`. Run result:
```
PASS  no adapter payload on argv (no 'json.loads(sys.argv' in jira-tracker.sh)
```
Total lint suite: 3/3 passed, 0 failed.  
**PASS**

### AC6 — cmd_get page loop: no temp dir leak on malformed page

Line 561 takes the parse exit code by hand:
```bash
... || { rm -rf "$cdir"; die "get: malformed comment page from Jira ($id, page $page)"; }
```
Line 751 cleans up on the success path: `rm -rf "$cdir"`.

Test 9i result:
```
PASS  get on a malformed comment page fails cleanly (non-zero exit)
PASS  malformed comment page leaks no jira-comments mktemp dir
```
**PASS**

---

## Test Suite Results (this QAS session — independently re-run)

| Suite | Passed | Skipped | Failed |
|---|---|---|---|
| tests/test-jira-tracker.sh | 128 | 1 (live tier) | 0 |
| tests/test-tracker-adapter-lint.sh | 3 | 0 | 0 |
| tests/test-mock-tracker.sh | 147 | 0 | 0 |
| tests/test-release-notes.sh | 25 | 0 | 0 |

All suites green. The live-tier skip is expected (requires `JIRA_LIVE_TOKEN`).

---

## Merge-ordering note (not a defect)

`ABS-263-auto` @ 3ca1c9e is stacked on `ABS-250-auto` commits. AC2's count-of-0 holds only atop ABS-250. RTE/TDM must rebase ABS-263 onto `main` once ABS-250 lands. Code is correct on its intended base.

---

## Final Verdict

**APPROVED for Story Acceptance.**  
All AC1–AC6 verified. Four test suites green (303 pass, 1 expected skip, 0 fail). Write-path argv-limit is closed; lint guard makes the defect class permanently unrepeatable.
