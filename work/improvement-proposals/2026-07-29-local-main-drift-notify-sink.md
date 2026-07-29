# Make the local-main-drift sensor reachable when no notify ticket is configured

- **Date**: 2026-07-29
- **Source**: AITBC-60 epic retro (dependency/security audit remediation)
- **Boilerplate version in use**: 2.35.0
- **Boilerplate-owned files**: `scripts/orchestrator.sh`

## Rationale

`check_local_main_drift()` (`scripts/orchestrator.sh:7660-7678`) is the ABS-224 AC3 /
PILOT-3 detection path for a guard bypass — the sensor that catches commits slipped onto
local `main`, outside any story branch or PR. It is the *last* line of defence, because
by definition it fires only when the pre-commit guard has already been evaded.

It is also the one sensor that cannot reach a human in the default configuration.

The drift alert is repo-scoped, not ticket-scoped, so it has no natural ticket to attach
to and calls:

```sh
notify "${ORCH_NOTIFY_TICKET:-}" \
    "local '$br' is $ahead commit(s) ahead of $active ..."
```

`ORCH_NOTIFY_TICKET` defaults to empty (`scripts/orchestrator.sh:646`), and `notify()`
fail-opens on an empty ticket (`scripts/orchestrator.sh:6796`):

```sh
[ -n "$ticket" ] || { log "notify skipped (no notify ticket): $body"; return 0; }
```

So out of the box the warning degrades to a line in `work/.orchestrator/run.log` — a file
nobody reads while a run is healthy — and the run continues green.

Every *other* notify call site avoids this sink in one of two ways, which is what makes
this one an outlier rather than a deliberate design:

| Call site | Reachability |
| --------- | ------------ |
| `check_claim_protocol` (`:7700`) and 18 more | falls back to the ticket: `${ORCH_NOTIFY_TICKET:-$ticket}` |
| `pause_for_daily_budget` (`:8208`), `pause_for_budget` (`:8222`) | empty fallback, but compensate with `budget_pause_push` (ABS-455 AC1, "a tracker comment is missable at 03:00") |
| **`check_local_main_drift` (`:7673`)** | **empty fallback, no push compensation — silent** |

### Observed evidence (this run)

The sensor fired correctly and was thrown away, twice:

```
16:16:56  INTENT-LOCAL-MAIN-DRIFT  ahead=11 branch=main remote=origin/main head=2b0ba05f9
16:16:56  LOG  notify skipped (no notify ticket): local 'main' is 11 commit(s) ahead ...
16:20:13  INTENT-LOCAL-MAIN-DRIFT  ahead=11 branch=main remote=origin/main head=2b0ba05f9
16:20:13  LOG  notify skipped (no notify ticket): local 'main' is 11 commit(s) ahead ...
```

Meanwhile the AITBC-60 epic was accepted to `Epic Done` while its entire deliverable —
50 modified files, 630 insertions, including the `poetry.lock` bump carrying 3 CVE fixes —
sat **uncommitted** in the main checkout, and 3 commits sat unpushed to the active remote.
No human was alerted by the mechanism built for exactly this. It surfaced only because the
retro seat happened to run `git status` as part of its own evidence discipline.

The detection logic is not at fault; it worked. Only the delivery of its verdict is.

## Suggested boilerplate change

`scripts/orchestrator.sh`:

1. **Route the ticket-less drift alert through the existing push channel.** `budget_pause_push`
   (ABS-455 AC1) already exists to wake an operator when a tracker comment is not an option;
   reuse it rather than inventing a second escape hatch. Either call it alongside the
   `notify` in `check_local_main_drift`, or generalise it to an `ops_push <body>` helper and
   have both the budget pauses and the drift sensor call that.
2. **Do not let a repo-scoped alert silently no-op.** When neither a notify ticket nor a push
   channel is available, `check_local_main_drift` should log at a level the run summary
   surfaces (an `INTENT` row alone is not enough — it is already emitted and was still missed).
3. **Name the resolution source in the drift line (diagnosability).** The alert prints
   `remote=origin/main` with no indication of *how* that remote was chosen —
   `resolve_active_main_ref` picks in order `ORCH_MAIN_REMOTE` pin → `branch@{push}` →
   `remote.pushDefault` → sole remote → hardcoded `origin`. In this repo it resolved to
   `origin` from a clone-set `branch.main.remote`, while the project actually pushes to a
   different remote — so the reported `ahead=11` measured drift against a remote the project
   does not use (true drift against the real push target was 3). Printing the source
   (`remote=origin/main (source=branch.main.remote)`) turns a misleading number into a
   diagnosable one. *(Note: the resolution order itself behaved as documented — this is a
   diagnosability request, not a claim that resolution is buggy.)*

Items 1–2 are the substance; item 3 is a cheap add-on in the same function and same review.

## Impact

- **Who benefits**: every consumer project that has not set `ORCH_NOTIFY_TICKET` — i.e. the
  default configuration. The failure is silent, so affected projects cannot know they are affected.
- **Severity**: the sensor guards against work that reaches no PR and no remote, which is
  unrecoverable once a worktree or checkout is cleaned. Silent failure here is the
  difference between a warning and lost work.
- **Risk**: low. Items 1–2 reuse an existing, proven channel; item 3 is a string change.
- **Effort**: small — one function, plus optionally extracting a shared `ops_push` helper.

## Copy-paste-ready issue body

```markdown
**Title**: local-main-drift sensor silently no-ops when ORCH_NOTIFY_TICKET is unset

**Finding**

`check_local_main_drift()` (scripts/orchestrator.sh:7660-7678) is the ABS-224 AC3 / PILOT-3
detection path for commits slipped onto local `main`. Being repo-scoped it has no ticket to
attach to and calls `notify "${ORCH_NOTIFY_TICKET:-}" ...`. `ORCH_NOTIFY_TICKET` defaults to
empty (:646) and `notify()` fail-opens on an empty ticket (:6796,
`[ -n "$ticket" ] || { log "notify skipped (no notify ticket): $body"; return 0; }`).

In the default configuration the alert therefore degrades to a run.log line and the run stays
green. This is the only notify call site with neither a ticket fallback nor a push
compensation: 19 sites use `${ORCH_NOTIFY_TICKET:-$ticket}` (e.g. check_claim_protocol :7700),
and the two other ticket-less sites (pause_for_daily_budget :8208, pause_for_budget :8222)
compensate via `budget_pause_push` (ABS-455 AC1).

**Repro**

1. Leave `ORCH_NOTIFY_TICKET` unset (the default).
2. Create a commit on local `main` that is not on the active remote.
3. Run the orchestrator.
4. Observe in `work/.orchestrator/run.log`:
   `INTENT-LOCAL-MAIN-DRIFT ahead=N ...` immediately followed by
   `notify skipped (no notify ticket): local 'main' is N commit(s) ahead ...`
   No tracker comment, no push, no non-zero exit. Nothing reaches a human.

Live occurrence: consumer project on v2.35.0, 2026-07-29. The sensor fired on two consecutive
sweeps (16:16:56, 16:20:13) and was discarded both times while an accepted epic's entire
deliverable (50 files, 630 insertions, incl. a poetry.lock carrying 3 CVE fixes) sat
uncommitted and 3 commits sat unpushed. Surfaced only by a retro seat running `git status`
by hand.

**Fix**

1. Route the ticket-less drift alert through the existing `budget_pause_push` channel
   (ABS-455 AC1), or generalise that into an `ops_push <body>` helper used by both the budget
   pauses and the drift sensor.
2. When neither a notify ticket nor a push channel is available, ensure the drift verdict
   surfaces in the run summary — the existing INTENT row alone demonstrably is not enough.
3. Diagnosability: have the drift line name how the remote was resolved
   (`remote=origin/main (source=branch.main.remote)`), since `resolve_active_main_ref` has a
   5-step fallback chain ending in a hardcoded `origin`. A clone-set `branch.main.remote`
   caused `ahead=11` to be reported against a remote the project does not push to (true drift
   against the real target: 3), with nothing in the output to reveal the mismatch.

**Fork**

No local fork. Reported upstream from the consumer project; no boilerplate-owned file was
modified locally (ADR-A-0008).
```
