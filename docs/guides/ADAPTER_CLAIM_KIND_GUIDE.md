# Feature Guide: `claim` Comment Kind and `cmd_get` Pagination

**Story**: ABS-182 — Adapter: add `claim` comment kind (mock + jira + contract)  
**Adapters affected**: `scripts/mock-tracker.sh`, `scripts/jira-tracker.sh`  
**Contract updated**: `profiles/neutral/adapters/task-tracking.md`

---

## Overview

ABS-182 adds `claim` as an allowed structured-comment kind and fixes `jira-tracker.sh::cmd_get` to exhaust all comment pages. Both changes are load-bearing for distributed ticket-claim adjudication (ABS-181 epic).

**What this enables**: the orchestrator can stake a distributed ticket claim by posting a `kind: claim` comment via the existing `comment` operation — no new adapter subcommand needed.

---

## Prerequisites

- `$TRACKER_CMD` pointing to either `scripts/mock-tracker.sh` or `scripts/jira-tracker.sh`
- For Jira: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` set

---

## Quick Start

### Post a claim comment

```bash
# Mock adapter
$TRACKER_CMD comment DEMO-3 \
  --kind claim \
  --actor orchestrator \
  --body "Claiming ABS-182 for orchestrator instance A (run-id: abc123)"

# Jira adapter (same CLI surface)
$TRACKER_CMD comment ABS-182 \
  --kind claim \
  --actor orchestrator \
  --body "Claiming ABS-182 for orchestrator instance A (run-id: abc123)"
```

**Expected output**: `comment added`

### Verify an unknown kind still fails

```bash
$TRACKER_CMD comment DEMO-3 --kind bogus --actor orchestrator --body "test"
# ERROR: comment: invalid kind 'bogus'
# exit code 1
```

### Read claim comments back

```bash
$TRACKER_CMD get DEMO-3
```

Claim comments render in the standard structured-comment format:

```
### 2026-07-10T21:45:00Z | kind: claim | actor: orchestrator

Claiming ABS-182 for orchestrator instance A (run-id: abc123)
```

---

## Core Concepts

### The `claim` kind

All structured comments carry a `--kind` tag. The allowed kinds are enumerated in the adapter contract (`profiles/neutral/adapters/task-tracking.md`, `comment(id, body, kind)` row):

```
kind: understanding | transition-reason | gate-results | handoff | decision
    | notification | follow-up | bsa-decision | skip | claim
```

`claim` is the kind the orchestrator uses to stake a distributed ticket claim. It follows the same wire format as every other structured comment — there is no new adapter subcommand.

### `cmd_get` comment pagination (ABS-182 amendment)

Before ABS-182, `jira-tracker.sh::cmd_get` fetched comments with a single API call (one page).
Jira returns comments **oldest-first**, so a ticket that accumulates more than one page silently
drops the newest comments. For claim adjudication that means the freshest peer claim could be
invisible — both orchestrators adjudicate themselves the winner.

ABS-182 fixes this with a page-exhaustion loop (`startAt`/`total`-driven, zero-dep bash + existing `py` helper):

```
GET /rest/api/3/issue/<id>/comment?startAt=0&maxResults=100   → page 0
GET /rest/api/3/issue/<id>/comment?startAt=100&maxResults=100 → page 1 (if needed)
…
```

Pages are merged in order and the result is identical to the existing single-page path for tickets that fit in one page. The same fix patches the latent ABS-62 stall-subsystem hazard (stall detection also reads comment headers).

**API-call cost change**: `get` was `2 calls` (issue + comments). It is now `2 calls` for a single-page ticket, `+1 per additional comment page` of 100. See the adapter header in `scripts/jira-tracker.sh` for the full per-op budget.

---

## Adapter Contract Reference

The `comment(id, body, kind)` operation in `profiles/neutral/adapters/task-tracking.md` now lists
`claim` as an allowed kind alongside the existing set:

```
kind: understanding | transition-reason | gate-results | handoff | decision
    | notification | follow-up | bsa-decision | skip | claim
```

All adapters that implement the canonical interface must accept `claim` as a valid kind and reject
unknown kinds with `comment: invalid kind '<k>'` (exit 1).

---

## Troubleshooting

### Issue: `comment: invalid kind 'claim'` on the mock adapter

**Symptoms**: exit 1, error message above  
**Cause**: running an older checkout of `scripts/mock-tracker.sh` that predates ABS-182  
**Solution**: verify the branch/commit includes commit `02b0f2f` or later; `git log --oneline scripts/mock-tracker.sh`

### Issue: `get` returns an incomplete comment list on Jira

**Symptoms**: claim adjudication finds no peer claim even though one was posted  
**Cause**: running an older checkout of `scripts/jira-tracker.sh` that predates ABS-182 (single-page fetch)  
**Solution**: verify commit `02b0f2f` or later; re-run the get and confirm the full page count

### Issue: `get` makes more API calls than expected after ABS-182

**Symptoms**: Jira API quota alerts on high-comment tickets  
**Cause**: expected behaviour — `cmd_get` now fetches every comment page (100 comments/page)  
**Mitigation**: keep individual tickets under ~100 comments for single-page cost; the per-op budget is documented in `scripts/jira-tracker.sh` header

---

## ADR Compliance

- **ADR-A-0007 (adapter-only)**: PASS — `claim` is additive to the `comment` contract; no vendor API added.
- **ADR-A-0009 (zero-dep bash)**: PASS — pagination loop uses `curl` + shell + the existing `py` merge helper only.
- **ADR-A-0010 (minimal-change)**: PASS — scoped, reversible; pagination fix is a BSA-mandated correctness change (spec §8).

---

## Related

- `profiles/neutral/adapters/task-tracking.md` — canonical adapter contract
- `scripts/mock-tracker.sh` — reference adapter implementation
- `scripts/jira-tracker.sh` — Jira binding
- `specs/distributed-ticket-claim-spec.md` — claim adjudication design (ABS-181 epic)
- `docs/sop/ORCHESTRATOR_SOP.md` — orchestrator runbook (API-call budget section)
