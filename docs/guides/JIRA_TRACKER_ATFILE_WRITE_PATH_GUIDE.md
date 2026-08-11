# Feature Guide: `jira-tracker.sh` — Request bodies via `@file` (ABS-263)

**Story**: ABS-263 — Windows/MSYS: tracker adapter request/write path over argv limit
**Adapter affected**: `scripts/jira-tracker.sh`
**Tests updated**: `tests/tooling/test-jira-tracker.sh`, `tests/tooling/test-tracker-adapter-lint.sh`,
`tests/fixtures/jira-curl-shim.sh`, `tests/fixtures/jira-version-curl-shim.sh`

---

## Overview

ABS-250 fixed the **read path** — responses from Jira no longer cross argv. ABS-263
fixes the **write path** — request bodies (comments, issue descriptions) no longer
cross argv either.

Before this fix, `http_call` delivered every request body to curl as
`--data-binary "$body"` (an argv string). On Windows/MSYS, where ARG_MAX is roughly
32 KB, a gate-results or handoff comment large enough to carry real evidence hits:

```
Argument list too long
```

before curl runs. The comment is not posted. The evidence trail that this methodology
rests on silently drops. Windows seats could read tickets (ABS-250) but could not
post to them.

ABS-263 completes the pair:

- `http_call` writes the body to a temp file and passes `--data-binary "@$bodyfile"`.
- `post_structured_comment` (comment ADF) and `cmd_create` (issue description ADF)
  pipe their payload via `printf | py` and read it with `sys.stdin.read()`.
- Both curl shims resolve the `@file` form so tests exercise the real code path.
- A lint guard in `test-tracker-adapter-lint.sh` makes the argv-payload defect class
  permanently unrepeatable.
- A folded-in fix cleans up `cmd_get`'s page-loop mktemp dir on malformed pages.

**External API unchanged.** Callers use `--body-file` exactly as before.

---

## What changed

### `http_call` — request body via temp file

Before (argv path, dies on Windows/MSYS):

```bash
code="$("$CURL_BIN" ... --data-binary "$body" "$url")"
```

After (`scripts/jira-tracker.sh:327–341`):

```bash
local bodyfile=""
set +e
if [ -n "$body" ]; then
    bodyfile="$(mktemp "${TMPDIR:-/tmp}/jira-body.XXXXXX")"
    printf '%s' "$body" > "$bodyfile"
    code="$("$CURL_BIN" ... --data-binary "@$bodyfile" "$url" 2>"$err")"
else
    code="$("$CURL_BIN" ... -X "$method" "$url" 2>"$err")"
fi
local rc=$?
set -e

[ -z "$bodyfile" ] || rm -f "$bodyfile"
```

The temp file is removed unconditionally at line 341 — before the `die` at line 348 —
so it is freed on success and on every error path. Pattern reused from
`scripts/release-notes.sh:258`.

### `post_structured_comment` — ADF payload via stdin

Before (argv path):

```python
node = json.loads(sys.argv[1])  # dies E2BIG on large comment ADF
```

After (`scripts/jira-tracker.sh:1170`):

```bash
reqbody="$(printf '%s' "$adf" | py 'import sys,json; sys.stdout.write(json.dumps({"body": json.loads(sys.stdin.read())}))')"
```

The ADF blob travels via shell pipe; Python reads it from `sys.stdin.read()`. Only
small control values (issue id, kind, actor) stay in argv.

### `cmd_create` — description ADF via stdin

Before (argv path):

```python
desc = json.loads(sys.argv[1])  # dies E2BIG on long description
```

After (`scripts/jira-tracker.sh:916–928`):

```bash
body="$(printf '%s' "$desc_adf" | py '
import sys, json
project, itype, summary, parent, role, flags, ac_blocking = sys.argv[1:8]
desc = sys.stdin.read()          # ADF blob from pipe; not argv
...
"description": json.loads(desc),
')"
```

Only structural fields (project key, issue type, summary, parent, role, flags) remain
in argv — none can grow beyond a short string.

### `cmd_get` — page-loop temp-dir cleanup

The comment-page loop in `cmd_get` previously leaked its mktemp directory when a page
returned malformed JSON and `set -e` triggered mid-loop. The fix takes the parse exit
code by hand (`scripts/jira-tracker.sh:561`):

```bash
... || { rm -rf "$cdir"; die "get: malformed comment page from Jira ($id, page $page)"; }
```

Line 751 frees the directory on the success path. No dirs leak on either path.

### Curl shims — `@file` form support

Both test shims now resolve `--data-binary "@file"`:

`tests/fixtures/jira-curl-shim.sh:59–60`:

```bash
--data-binary)
    if [ "${2#@}" != "$2" ]; then reqbody="$(cat "${2#@}")"; else reqbody="$2"; fi
```

`tests/fixtures/jira-version-curl-shim.sh:27–28`:

```bash
--data-binary)
    if [ "${2#@}" != "$2" ]; then body="$(cat "${2#@}")"; else body="$2"; fi
```

Tests that post comments or create issues now exercise the same code path as
production.

### Lint guard

`tests/tooling/test-tracker-adapter-lint.sh` asserts:

```
PASS  no adapter payload on argv (no 'json.loads(sys.argv' in jira-tracker.sh)
```

Any future change that routes a request payload back through argv fails this guard
before it can reach review.

---

## Regression guards

**Test 9h** (`test-jira-tracker.sh`): posts a ~2 MB comment via `--body-file` (past
this host's ARG_MAX). Asserts exit 0 and that the literal `WRITE-PATH-MARKER` is
present in the captured request body (full payload, not truncated). Fails on the
pre-fix adapter with E2BIG.

**Test 9i** (`test-jira-tracker.sh`): feeds `cmd_get` a malformed comment page.
Asserts non-zero exit AND zero leaked `jira-comments.*` dirs. Fails on the pre-fix
adapter (leaks one dir).

**AC5 guard** (`test-tracker-adapter-lint.sh`): asserts `no json.loads(sys.argv`
in the adapter — 3/3 green post-fix; fails on pre-fix (flags line 1147).

**Test 9g** (ABS-250): ~1.5 MB comment history read path — unaffected, still green.

Full suite result (post-fix): `test-jira-tracker.sh` 128 passed / 1 skipped (live
tier) / 0 failed; `test-tracker-adapter-lint.sh` 3/3; `test-mock-tracker.sh` 147/0;
`test-release-notes.sh` 25/0.

---

## Merge-ordering note (ABS-263 stacked on ABS-250)

`ABS-263-auto` is stacked on `ABS-250-auto`. The write-path fix contains
ABS-250's read-path commits as its base. Merge ABS-250 (PR #174) onto the epic
branch first, then rebase ABS-263 onto the updated epic tip before merging PR #179.
After the rebase the diff reduces to ABS-263's two commits only.

---

## Troubleshooting

### Issue: `comment` or `create` fails with `Argument list too long` on Windows/MSYS

**Symptoms**: adapter exits non-zero; stderr contains `Argument list too long`
**Cause**: running a checkout of `scripts/jira-tracker.sh` that predates ABS-263
**Solution**: update to a commit that includes ABS-263's changes on
`epic/ABS-245-consumer-feedback-defork`

```bash
git log --oneline scripts/jira-tracker.sh | head -3
```

Confirm the commit message includes `write-path argv-limit fix`.

### Issue: leftover `jira-body.*` temp files in `$TMPDIR`

**Symptoms**: `ls "${TMPDIR:-/tmp}/jira-body."*` shows leftover files
**Cause**: adapter killed mid-request before line 341 runs (e.g. `SIGKILL`)
**Solution**: delete manually; they contain only the JSON body of the last request

```bash
rm -f "${TMPDIR:-/tmp}"/jira-body.*
```

### Issue: `cmd_get` exits non-zero on a ticket with many comments

**Symptoms**: `get` fails; stderr contains `malformed comment page`
**Cause**: Jira returned a page that does not parse as expected JSON
**Note**: since ABS-263 the page dir is always cleaned up — no leaked dirs remain

---

## Related

- `scripts/jira-tracker.sh` — Jira adapter implementation
- `scripts/release-notes.sh:258` — source of the `--data-binary "@file"` pattern
- `tests/tooling/test-jira-tracker.sh` — adapter test suite (128 tests; 9h/9i guard this fix)
- `tests/tooling/test-tracker-adapter-lint.sh` — lint guard (`no json.loads(sys.argv`)
- `tests/fixtures/jira-curl-shim.sh`, `tests/fixtures/jira-version-curl-shim.sh`
- `docs/guides/JIRA_TRACKER_STDIN_JSON_GUIDE.md` — read-path counterpart (ABS-250)
- Epic ABS-245 — consumer feedback and de-fork epic; ABS-56 (Windows support)
