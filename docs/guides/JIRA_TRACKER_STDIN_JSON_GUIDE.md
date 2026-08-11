# Feature Guide: `jira-tracker.sh` — Response JSON via stdin (ABS-250)

**Story**: ABS-250 — jira-tracker.sh: JSON-Antworten per stdin statt argv parsen
**Adapter affected**: `scripts/jira-tracker.sh`
**Tests updated**: `tests/tooling/test-jira-tracker.sh`, `tests/fixtures/jira-curl-shim.sh`

---

## Overview

Before ABS-250, `scripts/jira-tracker.sh` passed Jira API responses into Python
as a shell argument (`json.loads(sys.argv[1])`). On Windows/MSYS, where ARG_MAX
is roughly 32 KB, any response larger than that limit caused:

```
Argument list too long
```

macOS is not immune — ARG_MAX there is ~1 MB, so a ticket with a long comment
history (400+ comments) fails on macOS too; Windows just hits the wall far
earlier.

ABS-250 converts all ten response-JSON handovers to stdin
(`printf '%s' "$x" | python3 -c '... json.load(sys.stdin)'`). Small control
values — ids, field names, status names, label prefixes — stay in argv; only
response payloads move.

**External API unchanged.** Consumer scripts call the adapter identically after
this fix. The `--body-file` / `--expect-from` flags are unaffected.

---

## What changed

### Response paths converted to stdin (10 total)

| Command | Python entry point | What moves via stdin |
| --- | --- | --- |
| `get` (issue JSON) | `cmd_get` — issue parse | full issue JSON |
| `get` (comment merge) | `cmd_get` — page merge | merged comment array |
| `search` | `cmd_search` | search-response JSON |
| `children` | `cmd_children` | search-response JSON |
| `child-count` | `cmd_child_count` | search-response JSON |
| `events` | `cmd_events` | search-response JSON |
| `transition` | `cmd_transition` | transitions-list JSON |
| `link` (get-link-type) | `cmd_link` | link-types JSON |
| `link` (get-issue-links) | `cmd_link` | issue JSON |
| `update` label helpers | `update_ac_blocking_label`, `update_list_labels`, `update_plain_labels` | issue JSON |

Small argv values (ids, field names, status strings, label prefixes) are
unchanged — they are never large enough to trigger E2BIG.

### `cmd_get` page-merge improvement

`cmd_get` previously passed the merged comment blob through a second Python
process and a shell variable. It now merges comment pages inside the **same**
Python call that processes the issue JSON, reading page files it already wrote to
disk. One Python process instead of two; the merged blob never round-trips
through a shell variable.

Error handling is also improved: `cmd_get` captures the Python exit code with
`|| rc=$?` so a parse failure frees the mktemp page directory and propagates a
non-zero exit. Previously a parse failure could leak the temp directory under
`set -e`.

---

## Write-path argv gap — closed by ABS-263

Outbound **request** bodies were not covered by this fix. `http_call` passed
request bodies to curl as `--data-binary "$body"`, and two Python sites built
request ADF with `json.loads(sys.argv[1])`:

- `create` — description ADF
- `post_structured_comment` — comment ADF

On Windows/MSYS, curl hit E2BIG on these before Python did — seats could read
tickets but could not post evidence to them.

**ABS-263 closes this gap.** `http_call` now writes the body to a temp file and
passes `--data-binary "@$bodyfile"`. Both Python sites read their ADF payload
from stdin (`sys.stdin.read()`). Both curl shims resolve the `@file` form. A lint
guard in `test-tracker-adapter-lint.sh` asserts `no json.loads(sys.argv` in the
adapter. See `docs/guides/JIRA_TRACKER_ATFILE_WRITE_PATH_GUIDE.md` for details.

---

## Regression guard

Test 9g (`tests/tooling/test-jira-tracker.sh`) asserts on a ~1.5 MB comment history
(served by a new shim route in `tests/fixtures/jira-curl-shim.sh`):

- `get` exits 0 (no E2BIG)
- the literal string `Argument list too long` does not appear in output
- canonical frontmatter is present
- all 400 comments are rendered
- the newest comment survives

The System Architect reverted the adapter to `main` and re-ran Test 9g — it
**fails 5/5** on the pre-fix code with the literal E2BIG error. The guard is
real, not a vacuous assertion.

---

## Troubleshooting

### Issue: `Argument list too long` on `get`, `search`, or `children`

**Symptoms**: adapter exits non-zero; stderr contains `Argument list too long`
**Cause**: running a checkout of `scripts/jira-tracker.sh` that predates ABS-250
**Solution**: update to a commit that includes `7dfb1ad` or later on
`epic/ABS-245-consumer-feedback-defork`

```bash
git log --oneline scripts/jira-tracker.sh | head -3
```

Confirm the commit message includes `parse Jira response JSON via stdin`.

### Issue: `comment` or `create` still fails with E2BIG on Windows/MSYS

**Symptoms**: posting a large comment or creating an issue with a long
description fails with `Argument list too long`
**Cause**: running a checkout that predates ABS-263 — request bodies still use
`--data-binary "$body"` on those older commits
**Solution**: update to a commit that includes ABS-263's write-path fix on
`epic/ABS-245-consumer-feedback-defork`; see
`docs/guides/JIRA_TRACKER_ATFILE_WRITE_PATH_GUIDE.md`

### Issue: temp directory left behind after a failed `get`

**Symptoms**: leftover `jira-comments.*` directories in your temp path after a
`get` that errors on a malformed comment page
**Cause**: pre-existing behaviour in the page-fetch loop — fixed by ABS-263 as
part of the write-path change. The loop now takes the parse exit code by hand and
frees the directory on every exit path.
**Solution**: update to a commit that includes ABS-263. If running an older
checkout, delete leaked dirs manually.

---

## Related

- `scripts/jira-tracker.sh` — Jira adapter implementation
- `scripts/mock-tracker.sh` — reference adapter (parity unaffected by ABS-250)
- `tests/tooling/test-jira-tracker.sh` — adapter test suite (128 tests; Test 9g guards the
  read-path fix; Tests 9h/9i guard the write-path fix from ABS-263)
- `tests/fixtures/jira-curl-shim.sh` — curl shim (oversized-response route added)
- `profiles/neutral/adapters/task-tracking.md` — canonical adapter contract
- `docs/guides/ADAPTER_CLAIM_KIND_GUIDE.md` — related adapter guide (ABS-182)
- `docs/guides/JIRA_TRACKER_ATFILE_WRITE_PATH_GUIDE.md` — write-path counterpart (ABS-263)
- Epic ABS-245 — consumer feedback and de-fork epic
- ABS-56 — Windows support (ABS-250 read-path + ABS-263 write-path together close this)
