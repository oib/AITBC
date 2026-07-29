---
name: run-boilerplate
description: Run, launch, drive, or smoke-test this repo's orchestrator (scripts/orchestrator.sh) safely in a sandbox — mock tracker, stub spawn seam, isolated state. Use when asked to run the orchestrator, verify an orchestrator change actually works, reproduce a dispatch/handoff behavior, or drive a ticket through the status machine without touching Jira or a live run.
---

# Run the boilerplate (orchestrator)

All paths are relative to the repo root.

The runnable surface of this repo is `scripts/orchestrator.sh` — a
zero-dependency bash poll loop that turns tracker status events into agent
spawns. There is no GUI and no server; you drive it by seeding tickets in the
mock tracker, running the loop for one cycle (`--once`), and reading the
`INTENT …` lines it prints. The committed driver wraps the whole sandbox
setup.

## Prerequisites

None beyond what a dev machine already has: bash 3.2+, git. No install step,
no build step (plain bash + awk by design).

## Run (agent path) — the driver

```bash
.claude/skills/run-boilerplate/driver.sh smoke
```

Seeds a `DEMO-1` ticket in a mktemp sandbox, asserts the dry-run intake
intent (`INTENT SPAWN … role=po-agent`), releases the ticket, runs one live
cycle against the **stub** spawn seam (`tests/fixtures/stub-spawn.sh` — no
real `claude`, no Jira), and asserts the ticket landed in `In Progress`.
Prints `SMOKE PASS` / `SMOKE FAIL` (exit 1). Takes ~5 seconds. Safe to run
while a real orchestrator is live elsewhere — state, tickets, and spawns are
fully isolated.

For interactive exploration (drive transitions by hand, watch intents):

```bash
eval "$(.claude/skills/run-boilerplate/driver.sh sandbox)"
scripts/mock-tracker.sh create --type ticket --title "My case" --prefix DEMO --role be-developer
scripts/orchestrator.sh --dry-run --once          # prints INTENT lines, spawns nothing
scripts/mock-tracker.sh transition DEMO-1 "Ready for Development" --actor human-operator --reason "release"
STUB_TRANSITION_TO="In Progress" scripts/orchestrator.sh --live --once   # stub seat "works" the ticket
scripts/mock-tracker.sh get DEMO-1                # inspect status + comment trail
.claude/skills/run-boilerplate/driver.sh clean    # remove sandboxes when done
```

Stub behavior knobs (crash/timeout/no-handoff branches) are documented in the
header of `tests/fixtures/stub-spawn.sh` (`STUB_FAIL`, `STUB_HANG`,
`STUB_NO_HANDOFF`, `STUB_MAX_TURNS_EXIT`, …).

## Run (human path) — live against Jira

A real run (live tracker, real `claude` seats) is an operator action with its
own launch recipe — env for Jira creds, per-seat turn ceilings, budgets. See
`docs/sop/ORCHESTRATOR_SOP.md`. Do not start one casually: it spawns real
paid model sessions.

## Test

```bash
bash tests/e2e-orchestrator-dryrun.sh   # full-lifecycle e2e (same sandbox technique)
bash tests/test-orchestrator.sh         # unit-level suite
```

## Gotchas (all hit for real)

- **Backlog tickets are invisible by default.** `ORCH_REQUIRE_START_LABEL=1`
  is the default gate — without the `orchestrator-ready` label nothing is
  eligible. The driver sets `ORCH_REQUIRE_START_LABEL=0`.
- **Worktree provisioning is real even with a stub spawn.** Without
  `ORCH_WORKTREE_SPAWNS=0` a live-mode cycle creates an actual git worktree
  `tmp/<ticket>-work` + branch `<ticket>-auto` in THIS repo. If you forgot:
  `git worktree remove --force tmp/DEMO-1-work && git branch -D DEMO-1-auto`.
- **`STUB_TRANSITION_TO` fails silently on a non-canonical status.** The
  status must exist in `profiles/neutral/adapters/statuses.yaml` (e.g.
  `In Progress`, not `Ready for QAS`), and `STUB_TRACKER` must point at the
  mock tracker — otherwise the seat "works" but the ticket never moves and
  you get `INTENT HANDOFF-NOMOVE`.
- **Unset `MOCK_TRACKER_TICKETS_DIR` writes into the repo.** The mock tracker
  defaults to `<repo>/work/tickets/` — that's where stray `DEMO-*.md` files
  come from. Always sandbox (the driver does).
- **State persists per `ORCH_STATE_DIR`.** Instance id, spawn ledgers, locks
  and the events snapshot live there; reusing a sandbox reuses them
  (`instance-id: … source=reused`). Fresh scenario ⇒ fresh sandbox.

## Troubleshooting

- `INTENT DEFER-CAP …` — you hit `ORCH_MAX_CONCURRENT` (default 3) in one
  cycle; the next cycle picks the deferred ticket up. Expected with >3
  eligible tickets.
- Orchestrator prints only `reconciliation sweep` lines and no intents —
  nothing is eligible: check the start-label gate and that your tickets are
  in the sandbox store (`scripts/mock-tracker.sh search --status Backlog`).
