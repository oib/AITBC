# Orchestrator Standard Operating Procedure (SOP)

**Purpose**: Operational runbook for `scripts/orchestrator.sh` — the event-loop Coordinator that turns tracker status-change events into fresh-subagent spawns

**Version**: 1.8 — per-ticket history is the append-only [change log](./ORCHESTRATOR_SOP_CHANGELOG.md) (ABS-215: add a **new line** there, never edit this parenthetical — the old single-line list was a recurring epic-integration merge-conflict magnet).
**Last Updated**: 2026-07-18
**Spec**: [`specs/ABS-36-orchestrator-spec.md`](../../specs/ABS-36-orchestrator-spec.md)

---

## Overview

The orchestrator is a single foreground polling loop (bash + awk, zero-dependency) that:

1. Polls `TRACKER_CMD events` for ticket status-change events.
2. Maps each event's destination status (`to`) to an action — **SPAWN** (fresh subagent),
   **SPAWN-then-NOTIFY**, **NOTIFY** (human-facing comment only), or **NOOP** — per the table in
   §2 of the spec.
3. For SPAWN actions, resolves the implementer role (ticket `role` frontmatter, falling back to
   `ORCH_DEFAULT_ROLE`), builds a minimal context packet, and invokes the spawn seam
   (`ORCH_SPAWN_CMD`).
4. Posts the returned handoff back to the ticket as a `kind: handoff` comment (in `--live` mode).

It realizes three standing invariants: **fresh subagent per task** (ADR-A-0002 — clean context
in, handoff out), **active tracking** (ADR-A-0006 — every transition is a trigger), and
**adapter-only tracker access** (ADR-A-0007 — it speaks only the canonical task-tracking
operations through `$TRACKER_CMD`, never touching `work/tickets/*.md` or a vendor API directly).

> **Which Jira lane?** The orchestrator poll loop is the **autonomous lane** — it reaches Jira only
> through the `scripts/jira-tracker.sh` curl adapter behind `$TRACKER_CMD`, never the interactive
> Atlassian MCP server. See the authoritative
> [lane doctrine](../../profiles/neutral/adapters/task-tracking.md#lane-doctrine-tracker_cmd-adapter-and-the-jira-two-lane-exception)
> for why the two lanes exist and why the one-JQL-sweep-per-poll budget is deliberate.

**Defaults to dry-run.** Out of the box the orchestrator logs spawn *intents* only and spawns
nothing. Nothing calls a model, spends budget, or writes to a real tracker until you explicitly
opt in with `--live` and a real `TRACKER_CMD`/`ORCH_SPAWN_CMD`.

---

## Prerequisites

- bash 3.2+ (macOS stock bash / Linux bash) and standard `awk`/`grep`/`sed` — no `yq`, `jq`, or
  Python.
- A task-tracking adapter reachable via `$TRACKER_CMD` implementing the canonical operations
  (`profiles/neutral/adapters/task-tracking.md`). Locally this is `scripts/mock-tracker.sh`; in
  production it is the configured tracker MCP/adapter binding.
- For `--live` runs only: a real `claude` binary on `PATH` (the default `ORCH_SPAWN_CMD` binding,
  `scripts/orchestrator-spawn-claude.sh`, execs it) and `<role>.md` agent definitions for every
  role the mapping can select (`po-agent`, `be-developer`, `fe-developer`, `data-engineer`,
  `system-architect`, `qas`, `tech-writer`). The spawn seam resolves these namespace-first —
  `harness/claude/agents/` if present, else the legacy live path `.claude/agents/` (ABS-96; see
  "Stable-Governs-Dev Mode" below).
- `scripts/hooks/iteration-guard.sh` present (ships with the repo) for the §5.5 bounce-cap
  integration. The orchestrator fails open (never blocks) if it is missing.
- Tickets whose deliverables live under `.claude/` require the human co-op step — a spawned agent
  cannot write there itself (see "Known Limitations — Headless Spawn Write Boundaries" below).

---

## Starting and Stopping

### Start (dry-run — default, safe)

```bash
scripts/orchestrator.sh
# equivalent: scripts/orchestrator.sh --dry-run
```

Logs `INTENT SPAWN/NOOP/NOTIFY/...` lines to stdout and runner logs (`orchestrator: ...`) to
stderr, on an infinite poll loop (`ORCH_POLL_INTERVAL` seconds apart). No ticket is transitioned,
no comment is posted, no subagent is spawned.

### Start (live — spawns real subagents, incurs cost)

```bash
scripts/orchestrator.sh --live
```

Routes every SPAWN intent to `$ORCH_SPAWN_CMD` (default: the shipped Claude Code binding), posts
handoffs back to the ticket, and can transition tickets to `Blocked` on escalation. **Requires a
deliberate choice** — see "Dry-run vs `--live`" below before flipping this on anywhere but a test
fixture.

### Single-cycle / test mode

```bash
scripts/orchestrator.sh --dry-run --once   # one poll pass, then exit — manual smoke test
```

`--once` runs exactly one poll cycle (drain pending, reconcile-if-due, poll, dispatch) and exits.
This is what `tests/test-orchestrator.sh` and `tests/e2e-orchestrator-dryrun.sh` use for
deterministic, non-looping assertions. `ORCH_MAX_CYCLES=N` (env-only, no flag) stops a
non-`--once` run cleanly after N cycles — the hook the E2E concurrency-cap scenarios use to avoid
racing a `sleep`-based poll interval.

### Stop — the kill switch

```bash
touch work/.orchestrator-stop
```

Checked at the top of every cycle (before drain/reconcile/poll) and again immediately before each
spawn attempt (§5.3). A running loop finishes its current cycle, logs
`kill-switch present (...); finishing, no new spawns; exit 0`, and exits 0 — no new dispatch is
started once the file exists. Remove the file (`rm work/.orchestrator-stop`) to allow a fresh
start; the kill switch does not need to be cleared mid-run because the process has already exited.

Override the path with `ORCH_STOP_FILE` (default: `$ORCH_STATE_ROOT/work/.orchestrator-stop`,
where `ORCH_STATE_ROOT` defaults to the repo root in single-repo mode). The backend shipper's
`stop-run` command derives the same default (`scripts/backend-shipper.sh`), so in single-repo mode
the human board `stop-run` and `orchestrator.sh` agree with no configuration.

**Self-hosting matching requirement (ABS-388).** The shipper computes `$REPO_ROOT` from its own
script dir. When that differs from the operator's `ORCH_STATE_ROOT`, export a single explicit
**matching** `ORCH_STOP_FILE` to **both** the shipper and `orchestrator.sh`. Without a match, a
board `stop-run` no-ops: the shipper writes the stop file where `orchestrator.sh` never looks.

---

## Stable-Governs-Dev Mode (ABS-92)

When you are **developing the boilerplate itself**, run it under a pinned **stable**
checkout so a stable release governs the work on `dev`. This is the self-hosting operating
mode: `~/boilerplate-stable` (a checked-out release tag) holds the rules and scripts that
govern; the dev repo is only the **work target**.

**Two-checkout model:**

- **stable** (the harness) — `~/boilerplate-stable`, a pinned release checkout. Its
  `scripts/` run, and its agent definitions supply the roles: `harness/claude/agents/` if the
  pinned tag ships the namespace (ABS-96+), else the legacy `.claude/agents/` (pre-ABS-96 tags,
  e.g. v2.16.0) — the spawn seam resolves this automatically (§ above, "Prerequisites").
- **dev** (the work target) — this repo. Its `CLAUDE.md`, hooks, and agent definitions are
  **work product, never instructions**. All work-state (`work/.orchestrator`, the stop
  file, the mock ticket store) lives under the dev repo's `work/`.

**Launch recipes:**

```bash
# Orchestrator (headless) — stable's script, dev as the target:
ORCH_TARGET_REPO=$PWD ~/boilerplate-stable/scripts/orchestrator.sh --dry-run   # then --live
```

`ORCH_TARGET_REPO` retargets the state dir, stop file, and (for the mock adapter) the
ticket store to the dev repo, and sets each spawn's cwd to the dev repo. `ORCH_HARNESS_HOME`
marks the stable root (defaults to the running script's own repo). The startup log prints a
provenance line: `provenance: harness=<...> target=<...>`. With **both** seams unset the
orchestrator behaves exactly as in single-repo mode.

```bash
# Interactive — a governed session (rules load from stable, dev is added as a work dir):
scripts/dev-session.sh
```

`dev-session.sh` resolves stable (`ORCH_HARNESS_HOME` → `~/boilerplate-stable`), verifies
stable and dev share the same git origin (same product), then `cd`s into stable and execs
`claude --add-dir <dev repo>`.

**Isolation scope (tiered).** Phase 1 isolation is **agent-definitions only**: headless
spawns read their role defs from stable but keep cwd = the dev repo (they must be able to
edit the code under development). **Full isolation** — redirecting hooks and `CLAUDE.md`
loading away from the dev repo — arrives with the Phase-2b drift guard. Until then, treat
the dev repo's harness files as work product by discipline, reinforced by the guard below.

**The wrong-entry guard.** A `SessionStart` hook (`scripts/session-wrong-entry-guard.sh`)
refuses a **bare interactive session launched inside the dev repo** when a same-product
stable checkout exists — it exits 2 and prints the launch recipe. It fires only when a
stable root resolves, its git origin matches the dev repo's origin (so it is a silent
no-op in consuming projects), cwd is the dev repo, and no spawn markers are set (headless
orchestrator spawns run in the dev repo and are **never** blocked). Escape hatch:
`SAW_GUARD_DISABLE=1` for a deliberate bare session.

**Stable escape hatch.** Never edit the stable checkout in place. If stable itself needs a
fix, cut a **patch release** and re-checkout the new tag — stable stays a clean, pinned
release at all times.

### Harness-release preflight (PILOT-81)

A live run **spawns seats that execute the harness checkout's code**, so the governing
checkout must *be* a published release — not a development branch. On 2026-07-26 (ABS-594)
`~/boilerplate-stable` sat on `epic/PILOT-58-...`, four commits past `v2.32.0`, and a whole
pilot ran unpublished code while its report claimed `Stable: v2.32.0`. The provenance line
and ADR-A-0013's "rules load from the stable checkout only" are only *claims* until something
proves the checkout really is on the pinned release.

`check_harness_release()` (in the runner, `scripts/orchestrator.sh`, called once at startup
after `init_run_id`) fail-closes a **live** start unless the harness checkout
(`$ORCH_HARNESS_HOME`) is:

1. **Exactly on an annotated release tag** — `git describe --exact-match --tags HEAD` must
   succeed. A **prefix match is insufficient**: the legacy operator launcher compared
   `git describe --tags` against a prefix (`v2.32`), and `v2.32.0-4-g42dadc14` matched and
   passed — it never checked that HEAD *is* the tagged commit. `--exact-match` returns empty
   (fails) for anything past the tag, which is exactly the class the guard must catch.
2. **On a clean tree** — `git status --porcelain` must be empty (no uncommitted *or* untracked
   change to a versioned path); otherwise the runner is not executing the clean release.

**In the runner, not (only) the launcher (AC3).** The launcher is operator tooling and does
not exist in consumer installs; the check lives in `scripts/orchestrator.sh` so every install
that runs the runner is covered. Kill switch (ABS-111, default ON):
`ORCH_HARNESS_RELEASE_GUARD=0` restores the legacy unguarded start.

**Telemetry (AC6).** The resolved harness version is *measured*, not asserted: a
`HARNESS-VERSION` run.log line records `tag=<tag> sha=<sha> dirty=<yes|no>` on **every** live
start — including a refused one — so after the fact it is provable which code actually ran.

**Which seat parked the checkout, and how it is closed (AC4).** In single-repo self-hosting
the harness checkout *is* the work target, so seats necessarily operate inside it; each
implementer gets its own runner-provisioned **worktree** (cwd = the worktree, not the main
checkout), and the main checkout is meant to rest on the release tag (detached HEAD). The
parking came from work happening in the **main checkout** instead of a worktree — two commits
on two different days in the reflog (PILOT-64, PILOT-50). Three mechanical layers now close
that: the ABS-224 pre-commit guard forbids a commit to `main`; the PILOT-66 post-checkout
guard warns/restores when a seat moves the main checkout's HEAD onto a work branch; and this
PILOT-81 preflight **refuses the next start** if the main checkout was left off-tag or dirty —
turning a silent parked state into a loud refusal the operator must clear before any code runs.

### RC dogfooding (governing under a release candidate)

Before promoting `harness/claude` work into a real release, you can govern a throwaway
checkout under a **release-candidate tag** to shake it out end-to-end — without touching the
main repo's pin or its drift guard. The live `.claude/` of the main repo is
`generated(.governor-tag)`; an RC dogfood lives entirely in a separate checkout with its own
`.governor-tag`.

Procedure:

1. **Cut an RC tag** on the commit you want to trial: `git tag v2.17.0-rc0` (a pre-release
   name; the generator accepts any existing tag, incl. RC names). Keep it local until you
   deliberately choose to publish it.
2. **Clone/worktree a throwaway checkout** of the repo (e.g.
   `git clone --local . /tmp/rc-dogfood` or `git worktree add`), so nothing here is disturbed.
3. **Set THAT checkout's pin to the RC** and materialize it:
   ```bash
   cd /tmp/rc-dogfood
   printf 'v2.17.0-rc0\n' > .governor-tag
   bash scripts/generate-governor.sh          # live .claude == generated(rc0), banner stamped rc0
   bash scripts/generate-governor.sh --check   # must pass
   ```
4. **Govern with it**: point the orchestrator/session at the RC checkout as the stable root —
   `ORCH_HARNESS_HOME=/tmp/rc-dogfood`. The generator's layout detection picks the right source
   automatically: `harness/claude/**` when the RC tag ships the namespace (post-ABS-96), else
   the legacy `.claude/<items>`.
5. **The main repo's drift guard is unaffected** — its `.governor-tag` still points at the
   released pin, and `bash scripts/generate-governor.sh --check` there stays clean. When the RC
   graduates to a real release, promotion (ABS-95) bumps the main repo's pin to the final tag.
6. **Throw the RC checkout away** when done (`rm -rf /tmp/rc-dogfood`); delete the local RC tag
   if you did not publish it.

---

## Dry-run vs `--live`

| | `--dry-run` (default) | `--live` |
| --- | --- | --- |
| Spawns a subagent | No — logs `INTENT SPAWN ...` only | Yes — routes to `$ORCH_SPAWN_CMD` |
| Posts handoff comments | No | Yes — `kind: handoff` comment on success |
| Transitions tickets (Blocked, escalation) | No | Yes |
| Sends NOTIFY comments | No — logs `INTENT NOTIFY ...` only | Yes — posted via the adapter |
| Cost | None | Real (LLM API usage per spawn) |
| Safe to run against a real tracker | Yes | Only with a human-approved cost budget (ADR-A-0009) |

Use `--dry-run` (the default) to validate the mapping and role selection against a real or mock
ticket set before ever spending a token. Flip to `--live` only after a human has approved the run
(cost gate, below) and — for anything beyond a disposable fixture — with `ORCH_NOTIFY_TICKET` set
so budget/escalation notices land somewhere a human will see them.

---

## Environment Knobs

All knobs are environment variables; there is no config file. Every default is a
comment-documented constant at the top of `scripts/orchestrator.sh`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRACKER_CMD` | `scripts/mock-tracker.sh` | Task-tracking adapter command (script path or `PATH` command). ADR-A-0007: the only way the runner touches tickets. Written verbatim into each packet header and folded into the packet-cache signature (ABS-202) — a cross-run change to the adapter path invalidates cached packets for all tickets whose `updated` field has not changed. |
| `ORCH_POLL_INTERVAL` | `10` (seconds) | Delay between poll cycles in a long-running (non-`--once`) loop. |
| `ORCH_SPAWN_CMD` | `scripts/orchestrator-spawn-claude.sh` | The spawn seam (§3). Tests/E2E point this at `tests/fixtures/stub-spawn.sh`. |
| `ORCH_MAX_CONCURRENT` | `3` | Live-spawn concurrency cap per cycle (§5.1). The `(N+1)`th eligible event this cycle is deferred to the in-memory pending set, not dropped. |
| `ORCH_PRIORITY_DISPATCH` | `1` (on) | ABS-261: when there are more dispatchable tickets than free slots, the reconcile sweep offers slots in canonical-priority order (`hotfix > high > normal > low`; age ASC within a band via a stable sort) BEFORE the concurrency cap, so an incoming hotfix takes the next free seat ahead of wartende Feature-Arbeit — with **no** preemption of running seats (the idle watchdog stays the only seat-beender). Priority source is the adapter dump's canonical `priority` field (ABS-242 mapping); absent/unknown ⇒ `normal`, so a tree with no priorities dispatches byte-identically. DEFER-CAP intents name the deferred ticket's priority. `0` = legacy adapter arrival/key order (ABS-111 kill-switch pattern). |
| `ORCH_HOTFIX_CAP_BONUS` | `1` | ABS-261: extra concurrency slots a `priority=hotfix` ticket may claim over `ORCH_MAX_CONCURRENT` — the gate only raises the admission ceiling for the new hotfix spawn, it **never** kills a running seat (no preemption). `0` = hotfix obeys the plain cap. Only takes effect while `ORCH_PRIORITY_DISPATCH=1`. |
| `ORCH_MAX_SPAWNS_PER_RUN` | `50` | Per-run **soft** spawn cap (§5.4, ADR-A-0009). At the cap the run auto-extends on progress, else drains — see "Cost gate" below (PILOT-47). |
| `ORCH_MAX_SPAWNS_PER_TICKET` | `25` | Per-ticket spawn cap (PILOT-47): a single ticket that respawns this many times this run is escalated to `Needs PO Decision` (`BLOCK-TICKET-SPAWN-CAP`) while the run continues. `0` disables it. |
| `ORCH_SPAWN_BUDGET_AUTOEXTEND` | `1` | PILOT-47: while the run shows progress (Done count rising), grow the soft cap instead of stopping. `0` = drain at the soft cap with no extension. |
| `ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT` | `25` | PILOT-47: each auto-extension adds this percent of the original soft cap to the remaining budget. |
| `ORCH_SPAWN_BUDGET_HARD_MULTIPLE` | `2` | PILOT-47: the fail-closed absolute per-run ceiling = soft cap × this multiple. Auto-extend never crosses it; reaching it keeps the ABS-455 exit-75 restart handshake. |
| `ORCH_RECONCILE_EVERY_N_CYCLES` | `10` | Cadence for the reconciliation sweep (§5.1), plus always once on startup (`ORCH_RECONCILE_ON_STARTUP=1` by default). |
| `ORCH_RECONCILE_ON_STARTUP` | `1` | Toggle the startup reconciliation sweep. The sweep only re-derives transient work states, so resting `Backlog`/`Done` tickets are never swept; `0` is mainly for tests that want a fully deterministic event-only pass. |
| `ORCH_STALL_EPIC_SECONDS` | `900` (seconds) | Stall rule 1 (ABS-62): an epic resting in `Backlog` with zero children older than this is mechanically raised to `Needs PO Decision` (which spawns a fresh PO-Agent). `0` disables rule 1. Subject to the Backlog opt-in gate — only `orchestrator-ready` epics are candidates. |
| `ORCH_STALL_RESTING_SECONDS` | `0` (disabled) | Stall rule 2 (ABS-62, opt-in): any ticket resting in `Backlog` whose `updated:` is older than this is raised to `Needs PO Decision`. Default `0` = off. Subject to the Backlog opt-in gate — only `orchestrator-ready` tickets are candidates. |
| `ORCH_REAP_SPAWN_CHILDREN` | `1` (Reaping an) | ABS-601: setzt `set -m` fuer die Spawn-Subshell, damit im Hintergrund gestartete Kinder eine eigene Prozessgruppe bekommen und beim Spawn-Ende mit eingesammelt werden — sonst ueberlebt z. B. eine backgroundete 15-min-Suite ihren Seat als Waise. `set -m` wirkt AUSSCHLIESSLICH in dieser Command-Substitution-Subshell und wird direkt nach dem Erfassen von `$!` zurueckgenommen. Ist Job-Control nicht verfuegbar, teilt das Kind die Gruppe des Runners und das Group-Reaping trifft schlicht nichts (keine lebende Gruppe hat die id des Spawns) — es wird nie ein Prozess ausserhalb des Spawns beendet (Common Rule 8). `0` schaltet das Reaping ab. | `orchestrator.sh` |
| `ORCH_REQUIRE_START_LABEL` | `1` (gate on) | Backlog opt-in gate (ABS-101): the orchestrator acts on a `Backlog` ticket only when it carries `ORCH_START_LABEL` — no PO sweep, no stall raise, no reconcile re-derive otherwise. `0` disables the gate (every `Backlog` ticket eligible; legacy behaviour). See "Backlog opt-in gate" below. |
| `ORCH_START_LABEL` | `orchestrator-ready` | The label the gate looks for. A ticket is released to the factory by adding this label (in the tracker UI, or `create --label` / `update <id> labels [..]` on the mock adapter). |
| `ORCH_STUCK_SWEEPS` | `3` | Stuck detector (ABS-116): consecutive RECONCILE sweeps a ticket may rest in an unowned status (not reconcilable, not a legit resting state, no in-flight lock, no backoff marker) before the one-per-episode NOTIFY fires. At default cadence ≈ 5 minutes. `0` disables. NOTIFY-only — never routes. |
| `ORCH_LIVENESS_WATCHDOG` | `1` (on) | Liveness watchdog (ABS-312): detects a full standstill (0 live seats + 0 spawns this sweep + ≥ 1 actionable ticket) and, after `ORCH_STANDSTILL_SWEEPS` sweeps, self-heals once (resets expired/exhausted backoffs, reclaims orphaned locks) then escalates loudly (`INTENT-STANDSTILL` + epic comment + operator push). Never lifts budget brakes or human gates. `0` disables. |
| `ORCH_STANDSTILL_SWEEPS` | `10` | Consecutive standstill sweeps before the liveness watchdog acts (self-heal, then escalate). |
| `ORCH_STANDSTILL_PUSH` | `1` (on) | Operator push on escalation (macOS `display dialog`, live mode only, best-effort). `0` disables the dialog (the `INTENT-STANDSTILL` run.log line + epic comment still fire). |
| `ORCH_INVARIANT_SWEEP` | `1` (on) | ABS-406 wait-state invariant sweep (degraded adapter-lane mirror of the ABS-391 v3 watchdog): checks every reconcile snapshot for tickets resting in a wait-state without the required evidence (open PR, active branch/seat, merged PR). Detection-only — never transitions (ADR-A-0004). Idempotent per status episode. Fail-open when no `$FORGE_CMD`. `0` disables. See "Wait-State Invariant Sweep" below. |
| `ORCH_INVARIANT_RULES` | see below | Declarative `status\|evidence\|grace\|desc` rule table for the wait-state sweep. Default mirrors `WAIT_STATE_INVARIANTS` from the ABS-391 v3 backend 1:1. Override by exporting a replacement — same pipe-delimited format, one rule per line. Editing this variable changes enforcement without touching code. |
| `ITERATION_GUARD_DEFAULT_CAP` | `3` | Iteration guard per-gate cap **floor** (PILOT-64): the minimum effective cap regardless of any marker. A `Iteration N of M` marker may only RAISE the cap above this floor (max over all markers seen), never lower it — so an agent cannot shrink its own bounce budget via comment prose and deadlock already-approved work (the PILOT-32 class). Aligns with ADR-A-0026: control state in typed config/fields, not parsed comments. |
| `ITERATION_GUARD_TICKET_CAP` | `9` | Iteration guard v2 (ABS-115): cumulative never-reset real-bounce budget per ticket; both guard levels escalate to `Needs PO Decision`. `0` disables the cumulative level. |
| `ORCH_BACKOFF_BASE_SECONDS` | `60` | Crash backoff (ABS-118): first retry delay after a SPAWN-CRASH per (ticket, status); each further crash multiplies by `ORCH_BACKOFF_FACTOR` (default `2`) up to `ORCH_BACKOFF_MAX_SECONDS` (default `1800`). Success resets. `0` disables (legacy retry-at-cadence). |
| `ORCH_FASTFAIL_SECONDS` | `10` | Crashes faster than this count toward the outage burst (an instant death = environment problem; a slow failure = ticket problem and resets the burst). |
| `ORCH_OUTAGE_BURST` | `3` | Consecutive fast-fail crashes (across tickets) that declare an environment outage and pause ALL spawns (`SKIP-OUTAGE`). `0` disables outage detection. |
| `ORCH_OUTAGE_RESUME` | `auto` | `auto`: one probe spawn per interval from `ORCH_PROBE_INTERVALS` (default `300 900 1800`, last repeats); a probe that gets an answer resumes the run (NOTIFY both at pause and resume). `manual`: hard pause until the operator deletes `work/.orchestrator/outage`. Outage state survives runner restarts. |
| `ORCH_MAX_TURNS` | `25` | Per-spawn turn ceiling passed to the spawn seam (§3.2); raised 12→25 in ABS-150. **Ceiling, not target.** Setting it explicitly is an operator-wide cap that overrides ALL per-role defaults below (a deliberate all-seats cap). Left unset it is NO LONGER a seat's silent fallback (PILOT-65): every role resolves to a calibrated built-in, the implementer default, or `ORCH_MAX_TURNS_DEFAULT_ROLE`. |
| `ORCH_MAX_TURNS_IMPLEMENTER` | `140` | Built-in turn ceiling for implementer seats (`be-developer` `fe-developer` `data-engineer`) — the write-heavy seats that build AND commit a story. PILOT-65 calibrated this to ~1.5× the observed peak (~90, where they were dying at the old 90 cap); the cap must sit ABOVE the observed maximum, not hug the median (be-developer median 80). Yields to an explicit operator-wide `ORCH_MAX_TURNS` and to `ORCH_MAX_TURNS_<ROLE>`. |
| `ORCH_MAX_TURNS_DEFAULT_ROLE` | `50` | PILOT-65: per-role ceiling for any non-implementer role WITHOUT a measured built-in (`bsa`, `tdm`, …). Replaces the old **silent** fall to the lean global 25 — every role now resolves to an explicit, documented cap. 50 sits ~1.5× above the highest observed capless median (~32). Yields to an explicit operator-wide `ORCH_MAX_TURNS`. |
| `ORCH_AGENT_TIMEOUT` | `900` (seconds) | Watchdog: a spawn running longer than this is killed and treated as a failure (§6.1). Under the default **idle watchdog** (`ORCH_WATCHDOG_IDLE=1`, below) this value no longer kills directly — it FEEDS the derived `ORCH_AGENT_MAX_LIFETIME` (2×) and is the resolved base for the legacy wall-time path when the idle watchdog is switched off. |
| `ORCH_AGENT_TIMEOUT_<ROLE>` | *(unset)* | ABS-157: per-seat watchdog override (same naming as `ORCH_MAX_TURNS_<ROLE>`, role uppercased, dashes→underscores). Beats the global `ORCH_AGENT_TIMEOUT` for that seat only. Set this for seats that legitimately run long — e.g. `ORCH_AGENT_TIMEOUT_QAS=1800` so a qas seat running the full test suite (400+ tests on a large model) is not killed mid-run — WITHOUT inflating every other seat's watchdog (which would delay detection of a genuine hang). Still honored under the idle watchdog: it is the per-seat base the derived `ORCH_AGENT_MAX_LIFETIME` (2×) is computed from, so existing per-role launchers keep working. |
| `ORCH_WATCHDOG_IDLE` | `1` (on) | ABS-225 progress-based watchdog: kill a seat on **proven inactivity** (`ORCH_AGENT_IDLE_TIMEOUT`) with an absolute `ORCH_AGENT_MAX_LIFETIME` backstop, instead of a static wall-time ceiling that every larger ticket outgrows (ABS-151/157/213). A long *active* verify phase (e.g. a full pre-release-check) survives on its own; a hung seat still dies, sooner than the old wall. `0` = legacy hard wall-time kill at the resolved `ORCH_AGENT_TIMEOUT[_<ROLE>]` with no activity check (ABS-111 kill-switch pattern). |
| `ORCH_ASYNC_WAIT_SENSOR` | `1` (Sensor an) | ABS-601: erkennt einen Handoff, der auf eine ASYNCHRONE Completion-Notification wartet — ein `claude -p`-Spawn ist ein Einmal-Aufruf und hat keinen spaeteren Turn und keinen Event-Loop, in dem sie eintreffen koennte. Der Fall wird als eigener Zustand `ASYNC-WAIT-STALL` benannt (nicht als generisches `HANDOFF-NOMOVE`) und direkt nach `Needs PO Decision` eskaliert, weil ein identischer Respawn das Anti-Muster reproduziert: No-Move-Runden zu zaehlen verbrennt nur Budget und verdeckt das WARUM (Pilot 8 erreichte so nomoves=2 und eine nichtssagende Eskalation). Terminale und bereits in NPD stehende Stationen werden benannt, aber nicht erneut eskaliert (keine unzulaessige Selbst-Transition). `0` schaltet den Sensor ab. | `orchestrator.sh` |
| `ORCH_AGENT_IDLE_TIMEOUT` | `900` (seconds) | Idle watchdog: kill a seat that shows NO activity for this long. "Activity" = a session-transcript write (any tool/model turn) OR a live child process of the spawn. A single long Bash call (e.g. a 10-min test suite) writes no transcript between start and end but IS a live child, so it reads as active and is never idle-killed (AC4 process-check). A genuinely active seat is never idle-killed — that is `ORCH_AGENT_MAX_LIFETIME`'s job. `<=0` disables idle-kill. |
| `ORCH_AGENT_MAX_LIFETIME` | *(unset → derived 2× resolved role timeout)* | Absolute lifetime cap regardless of activity — the loop/abuse backstop (a looping seat is "active" and must still be reaped, ABS-132/151). Unset: derived per spawn as 2× the resolved `ORCH_AGENT_TIMEOUT[_<ROLE>]`, so legacy timeout knobs keep meaning. An explicit value is a hard operator-wide cap that wins. `<=0` disables the cap (idle-kill only). |
| `ORCH_WATCHDOG_POLL` | `15` (seconds) | Interval between activity probes (process + transcript scan). Liveness and the `ORCH_AGENT_MAX_LIFETIME` cap are still checked on the 1s base tick; only the heavier activity evaluation is throttled to this interval. |
| `ORCH_LOCK_TTL` | `1800` (seconds) | Age at which a held single-flight lock is considered stale (crashed runner) and reclaimed (§5.2). |
| `ORCH_PACKET_MAX_BYTES` | `32768` | Soft cap on the context packet; the ticket-body tail is truncated to stay under it while the header and latest handoff are preserved in full (§4). Folded into the packet-cache signature (ABS-202) — a cross-run cap change invalidates cached packets for tickets whose `updated` field has not changed. |
| `ORCH_POLICY_INJECT` | `on` | ABS-382 (ABS-231 S5): prepend the seat role's revision-pinned effective policy as a `=== POLICY (policy_rev: <hash>) ===` block before `=== TICKET ===` when the adapter offers the `policies` op (S4/ABS-381). `off` forces the byte-identical legacy packet even on a capable adapter. Adapters without `policies` (mock/jira) are byte-identical regardless — the op exits non-zero and the block is omitted. `policy_rev` folds into the packet-cache signature (a policy change re-derives the packet, an unchanged set re-hits), and every spawn writes a `POLICY-INJECT` run.log audit line. Injection is context only — it grants the seat no new authority. See "Revision-Pinned Policy Injection" below. |
| `ORCH_DEFAULT_ROLE` | `be-developer` | Implementer-role fallback when a ticket has no `role` frontmatter (§2.2). |
| `ORCH_REVIEW_TOOLS` | `Read, Bash, Grep, Glob` | Read-only toolset handed to the `In Review` spawn (see "Read-only review gate" below). |
| `ORCH_STATE_DIR` | `<repo>/work/.orchestrator` | Runtime dir for locks and packets. Nothing here is part of the tracker's data — safe to delete between runs. |
| `ORCH_STOP_FILE` | `$ORCH_STATE_ROOT/work/.orchestrator-stop` | Kill-switch path; shipper derives the same default. Under self-hosting (different roots) export a matching value to both processes (ABS-388, §above). |
| `ORCH_NOTIFY_TICKET` | *(unset)* | Ticket to receive budget-exhaustion / ops NOTIFY comments when a per-ticket notify target doesn't apply. Set this in any `--live` run a human is expected to watch. |
| `ORCH_MAX_CYCLES` | `0` (unbounded) | Test/ops hook: stop a non-`--once` loop cleanly after N cycles. `0` keeps the production infinite loop. |
| `ORCH_ASYNC_SPAWNS` | `1` (on) | ABS-111 A1: run live spawns as background jobs so `ORCH_MAX_CONCURRENT` caps in-flight spawns for real. `0` restores the legacy synchronous one-at-a-time scheduler. See "Async spawns" below. |
| `ORCH_SESSION_RESUME` | `1` (on) | ABS-111 A2: resume the same Claude session on rework bounces / re-reviews / handoff repair until acceptance (`Merging`/`Done`). `0` = strictly fresh per spawn. See "Session resume" below. |
| `ORCH_SALVAGE_MAX_TURNS` | `5` | ABS-175: default turn budget for the ONE salvage resume a spawn gets when it exits at the turn cap (result JSON `subtype=error_max_turns`). Instead of discarding the truncated session (ABS-129 lost $2.01 that way), the runner resumes it once with a per-role-resolved cap (see `ORCH_SALVAGE_MAX_TURNS_<ROLE>` and `salvage_max_turns()` below) and a fixed "commit + handoff + stop" prompt, then feeds the salvage output into the normal handoff flow; a salvage that also fails falls through to the crash path. Needs `ORCH_SESSION_RESUME=1`; no salvage in dry-run. See "Turn-cap salvage" below. |
| `ORCH_SALVAGE_MAX_TURNS_<ROLE>` | *(unset)* | ABS-605: per-seat salvage budget override (role uppercased, dashes→underscores, e.g. `ORCH_SALVAGE_MAX_TURNS_RTE=42`). Beats the built-in per-role value and the default `ORCH_SALVAGE_MAX_TURNS`. Unset = use the `builtin_role_salvage_max_turns()` built-in (rte=30; others have no built-in and fall to the default 5). Resolved by `salvage_max_turns()` in `scripts/orchestrator.sh`. |
| `ORCH_SESSION_POISON_GUARD` | `1` (on) | ABS-254 / ADR-A-0023 rule 3: refuse to store a session whose spawn result carried a denied **mutating** tool (`ORCH_MUTATING_DENIAL_TOOLS`). A resumed session carries its transcript — including any `permission denied` errors — so a seat that hit denials keeps reporting the phantom blocker even after the settings are fixed underneath it. ABS-598: a denied **read-only** tool (Read/Grep/Glob) leaves nothing inconsistent (the model just did not see a file), so it does NOT poison — only a mutating denial (Write/Edit/Bash) can leave the tree/process state inconsistent and forces a cold start. The `SESSION-POISONED` log names the triggering tool + target. `0` = legacy store-anyway behaviour. See "Poisoned-session guard" below. |
| `ORCH_MUTATING_DENIAL_TOOLS` | `Write Edit MultiEdit NotebookEdit Bash` | ABS-598: the space-separated tool set whose DENIAL poisons a session (see `ORCH_SESSION_POISON_GUARD`). A denied tool NOT in this set (Read/Grep/Glob/…) is treated as read-only and leaves the session storable. |
| `ORCH_DEPENDS_GATING` | `1` (on) | ABS-111 C8: hold a `Ready for Development`/`Design` dispatch while a `depends_on` blocker is unmet — satisfied when the blocker is `Done`, its head is an ancestor of the target branch (merge fact; PILOT-19), or it rests in `Docs` (POST-MERGE status per ABS-266; PILOT-44); `depends-strict` dependents wait for `Done` only. `0` disables the gate. See "depends_on gate" below. |
| `ORCH_WORKTREE_SPAWNS` | `1` (on) | ABS-111 C9: provision a git worktree per implementer spawn (`tmp/<ticket>-work`, branch `<ticket>-auto`) handed to the seam as `ORCH_SPAWN_CWD`. `0` disables (spawn keeps the repo-root cwd). See "Runner-provisioned worktrees" below. |
| `ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS` | `5` | PILOT-66: bound the fail-closed worktree-provisioning retry. Each failed `git worktree add` is counted per ticket and backed off (`record_backoff`, so `spawn_dispatch` skips it for free during the delay); after N consecutive failures the runner escalates the ticket to `Blocked` with a `NOTIFY` Attention-Event and a gate-results comment instead of retrying silently forever (the 131-`SKIP-NOWORKTREE` budget drain). The provisioning check runs before the spawn budget/lock/seam, so failed retries cost no budget. `0` = never escalate (count + back off indefinitely). |
| `ORCH_WORKTREE_EXTRA_ALLOW` | `Bash,Write,Edit` | ABS-131/ABS-154: comma-separated Claude-Code permission entries merged into the **worktree's** `settings.local.json` so seats can read/write/commit/push inside the isolated tree without widening the main-checkout allowlist. ABS-154 default = bare `Bash,Write,Edit` (covers compound commands, heredocs and `git push`) so seats no longer depend on the restrictive copied target allowlist. Override to change; set empty to disable. Needs `jq`. See "Local permissions travel into the worktree". |
| `ORCH_MAX_TURNS_<ROLE>` | *(unset)* | ABS-111 A3: per-seat turn-ceiling override (role uppercased, dashes→underscores, e.g. `ORCH_MAX_TURNS_ISSUE_ENRICHMENT=120`). Beats `ORCH_MAX_TURNS`. |
| `ORCH_MODEL_<ROLE>` | *(unset)* | ABS-111 B6: per-seat model override (same naming, e.g. `ORCH_MODEL_QAS=sonnet`). Beats the role frontmatter and global `ORCH_MODEL`. |
| `ORCH_MODEL_LABEL_ROLES` | `be-developer fe-developer data-engineer qas tech-writer` | ABS-128: allowlist of roles a `model:`-label **downsize** (`sonnet`/`haiku`) may take effect for (comma/space separated). Review/judgment seats not on the list ignore a downsize and keep their role default (`MODEL-LABEL-SKIP` event); a `model:opus` **upsize** always applies to ALL roles. Blank after parsing → `WARN-MODEL-LABEL-ROLES` + built-in default (never a crash). |
| `ORCH_ASSIGNEE` | *(unset)* | ABS-126: default Jira accountId assigned to a ticket at seat spawn. Empty = skip (graceful, no error). **Never hardcode accountIds** — always supply via this env var (ADR-A-0010). |
| `ORCH_ASSIGNEE_<ROLE>` | *(unset)* | ABS-126: per-seat assignee override, same naming as `ORCH_MODEL_<ROLE>` (e.g. `ORCH_ASSIGNEE_BE_DEVELOPER=accountId`). Beats `ORCH_ASSIGNEE`. Unset = fall back to `ORCH_ASSIGNEE`. |
| `ORCH_CLAIM_ASSIGN` | `0` | ABS-186: **cosmetic** human-visibility layer. When `1` *and* a claim mode is armed (`ORCH_CLAIM_MODE` ≠ `off`), a **won** remote claim stamps the ticket assignee (reusing `ORCH_ASSIGNEE_<ROLE>`/`ORCH_ASSIGNEE`) so the ticket visibly shows which machine holds it. The assignee is **never** the claim of record and is never read back to decide ownership — the claim comment remains the sole authority. A failed assign is logged and non-fatal. Default `0` = no assign after a claim. |
| `ORCH_MAX_SPAWNS_PER_DAY` | `400` (`0` off) | Per-**day** spawn cap across runs via the dated ledger (spec §3.9). Recalibrated from 200 (PILOT-63 AC3): measured runs consumed 161–251, so one epic wave overran the old default. See "Per-day spawn budget". |
| `ORCH_RUN_LOG` | `<state-dir>/run.log` | ABS-111 D11: path of the structured timestamped TSV event log. See "Observability" below. |
| `ORCH_HANDOFF_TRANSITION` | `1` (on) | ABS-132: after a cleanly parsed handoff the runner applies the handoff's declared target status ITSELF via `$TRACKER_CMD transition` (actor = the seat role, so the rework counter still counts a runner-applied bounce), idempotent when the seat already reached the target (Ist=Soll → no double transition). `0` = legacy seat-only transitions. Transitions remain ALSO allowed by seats. See "Transition-on-handoff" below. |
| `ORCH_RESPAWN_LIMIT` | `2` | ABS-132 loop-guard: consecutive respawns at one status that each parsed a handoff but left the status UNCHANGED (no declared target the runner could apply and the seat did not transition) before the runner escalates to `Needs PO Decision` with a reasoned `decision` comment instead of resuming endlessly. The window re-arms on any transition. `0` disables the guard. See "Transition-on-handoff" below. |
| `ORCH_REWORK_INFRA_RE` | *(transient/infra reason set)* | PILOT-69 (ADR-A-0018 transient class, Anschluss ABS-555): pipe-separated reason substrings (case-insensitive) that mark a backward transition as an INFRASTRUCTURE abort — budget-**neutral** for `rework_count()`, so a transient crash/timeout/rate-limit/session-poison bounce consumes no rework unit (mirrors the iteration guard's `INFRA_ABORT_RE`). Kept in step with `blocker_class()`'s `transient` set; a handoff **mis-report** is deliberately ABSENT (a content fault still counts, ADR-A-0024 e). Empty string = count every backward move (pre-PILOT-69 behaviour). |
| `ORCH_CROSSVISIT_LOOPBREAKER` / `ORCH_CROSSVISIT_THRESHOLD` | `1` (on) / `2` | ABS-199 (ADR-A-0018) cross-visit same-blocker loop-breaker: a failed dispatch is classified (`environment-denial`/`transient`/`logic`) from its ABS-151 diagnostic and recorded in `work/.orchestrator/blocker-<ticket>`. On the **threshold-th** occurrence of the **same `(environment-denial, seat)`** across ANY visits the ticket auto-parks to **Blocked** (human-owned) with exactly one operator NOTIFY and **no re-spawn** — a deterministic wall retrying cannot clear (the ABS-168 lesson). `transient`/`logic` and any distinct `(class, seat)` stay on the per-visit ABS-118/ABS-132/ABS-74 path. `LOOPBREAKER=0` disables. See "Cross-visit loop-breaker" below. |
| `ORCH_ESCALATION_LOOPBREAKER` / `ORCH_ESCALATION_BUDGET` | `1` (on) / `3` | ABS-199 (ADR-A-0018) per-ticket escalation budget: counts resting rounds that do **not** advance the ticket's `chain_index` (folded from ABS-198 M4). At `BUDGET` rounds → one operator NOTIFY + park to **Blocked**, no further seats. The counter **and** the blocker marker reset **only** on real forward progress (a transition to a strictly greater `chain_index` high-water mark); a backward bounce never resets — closing the ABS-181 bounce loop. `LOOPBREAKER=0` disables. See "Cross-visit loop-breaker" below. |
| `ORCH_MERGE_QUEUE` | `1` (on) | ABS-256 (ADR-A-0025): per-epic merge token — at most one story per epic occupies the `rte` `Merging` seat at a time; the token is **held across a merge-bounce** so the epic tip cannot move while the holder fixes its rebase (the livelock-prevention rule). `0` restores the pre-ABS-256 unserialized behavior in one env edit. See "Per-Epic Merge Token" below. |
| `ORCH_VERIFY_COMMITS` | `1` (on) | ABS-255 (ADR-A-0024): before a handoff is accepted, every hash on its `commits:` line is checked for existence (`git cat-file -e <sha>^{commit}`) and reachability (`git for-each-ref --contains <sha>`). A hash that fails is a **mis-report**: the handoff is refused, any implementer self-transition is undone back to `Ready for Development`, a `HANDOFF-MISREPORT` gate-results comment names each failing hash and which check failed, and the ticket rests for a fresh implementer. Prose commit claims with no `commits:` field get a non-blocking `HANDOFF-CLAIM-NOHASH` advisory. Fail-open when `commits:` is absent. `0` restores pre-ABS-255 unverified handoffs. See "Handoff Commit Verification" below. |
| `ORCH_VERIFY_MARKERS` | `1` (on) | ABS-297: before a handoff is accepted, any prose claim about a marker-backed effect is verified against the tracker. Two duties: (1) a po-agent handoff that claims a child is `JOIN-EXEMPT (triage)` triggers a check that the exact marker text exists in a `kind: decision` comment on that child; (2) a bsa handoff that claims the follow-up pile is empty triggers a check that no `kind: follow-up` without a `kind: bsa-decision` reply remains on the ticket. A missing marker is a **marker mis-report**: the handoff is refused, the seat self-transition is undone, a `MARKER-MISSING` gate-results comment names the required marker and its target ticket, and the ticket rests for a fresh seat. Table-driven off existing printers (`join_exempt_marker()`, `epic_has_unprocessed_followups()`). Fail-open when the claim cannot be parsed. `0` restores pre-ABS-297 unchecked prose claims. See "Handoff Marker Duty Verification" below. |
| `ORCH_VERIFY_PUSH` | `1` (on) | PILOT-75 (ADR-A-0024 + ADR-A-0030): for a forward-completion handoff (story chain `In Review`=4 .. `Done`=12), every claimed commit must be reachable under `refs/remotes/<active-remote>/` — the ref `git push` writes on a successful push. A local-only commit is refused on the ABS-255 mis-report path (transition not applied; work bounces back to push). Active remote resolved via `active_remote_name()`, never hardcoded `origin` (ADR-A-0030). `0` restores pre-PILOT-75 local-ref-only reachability. |
| `ORCH_REMOTE_PROBE_TIMEOUT` | `12` (seconds) | ABS-355: wall-clock ceiling for each remote probe in `resolve_fresh_base`. Every `ls-remote`/`fetch` call runs inside `_bounded_git`; a remote that does not respond within this window is treated as unreachable and skipped. Prevents a stalled HTTPS GitLab-fallback remote from hanging worktree provisioning on the same outage the fix targets. Raise on slow links. See "Fresh-base provisioning" below. |

---

### Additional knobs (ABS-517 audit)

The knob table above lists the day-to-day tuning surface. The ABS-517 audit
(sensor: `scripts/orch-knob-doc-drift.sh`, test: `tests/test-orch-knob-drift.sh`)
found the knobs below read in `scripts/` but undocumented; they are recorded
here name-by-name so the code→doc drift guard stays green. Defaults are the
`${VAR:-default}` values at audit time; the defining script is authoritative.

| Knob | Default | Defined in |
|------|---------|------------|
| `ORCH_AGENTS_ARG_MAX` | `24000` | `orchestrator-spawn-claude.sh` |
| `ORCH_AUTOMERGE` | `0` / off (ADR-A-0014) | rte seat, `merge-target-guard.sh` |
| `ORCH_BACKLOG_SKIP_EPIC_CHILDREN` | `1` | `orchestrator.sh` |
| `ORCH_BLOCKED_AUTO_RELEASE` | `1` (ABS-296 sweep) | `orchestrator.sh` |
| `ORCH_BLOCKED_RELEASE_CHURN_CAP` | `3` (PILOT-72: max blocked-auto-release episodes per ticket before the sweep stops releasing and raises one deduped Attention-Event) | `orchestrator.sh` |
| `ORCH_BUDGET_PAUSE_EXIT_CODE` | `75` (ADR-A-0009) | `orchestrator.sh` |
| `ORCH_BUDGET_PUSH` | `1` | `orchestrator.sh` |
| `ORCH_CLAIM_WARN_MINUTES` | `10` | `orchestrator.sh` |
| `ORCH_CLAUDE_ACCOUNT` | unset | `orchestrator.sh` |
| `ORCH_CLAUDE_BARE` | `0` | `orchestrator-spawn-claude.sh` |
| `ORCH_CLAUDE_BIN` | `claude` | `orchestrator-spawn-claude.sh` |
| `ORCH_CRASH_REPAIR_SECONDS` | `300` | `orchestrator.sh` |
| `ORCH_CURSOR_BIN` | `cursor` | `orchestrator-spawn-cursor.sh` |
| `ORCH_CURSOR_FORCE` | `0` | `orchestrator-spawn-cursor.sh` |
| `ORCH_DOCS_IDENTIFIER_CHECK` | `1` (ABS-337; default-on since ABS-517) | `docs-identifier-check.sh` |
| `ORCH_EPIC_REVIEW_GATING` | `1` (ABS-518 pre-filled-epic child hold) | `orchestrator.sh` |
| `ORCH_EPIC_SPLIT_GUARD` | `1` | `orchestrator.sh` |
| `ORCH_ESCALATION_WORK_BUDGET` | `3` (ADR-A-0018) | `orchestrator.sh` |
| `ORCH_ESCALATION_WORK_CREDIT` | `1` (ADR-A-0018; on by default, PILOT-63 AC2) | `orchestrator.sh` |
| `ORCH_EVIDENCE_PATH_PREFIX` | `docs/agent-outputs/` | `orchestrator.sh` |
| `ORCH_FASTLANE_BUNDLE` | `1` (batch lane) | `orchestrator.sh` |
| `ORCH_FASTLANE_BUNDLE_MAX` | `4` | `orchestrator.sh` |
| `ORCH_FASTLANE_COLLAPSE` | `1` | `orchestrator.sh` |
| `ORCH_FASTLANE_DIFF_BUDGET` | `400` | `orchestrator.sh` |
| `ORCH_FASTLANE_EJECT` | `1` | `orchestrator.sh` |
| `ORCH_FASTLANE_EJECT_ITER` | `2` | `orchestrator.sh` |
| `ORCH_FASTLANE_PROTECTED_PATHS` | `*/migrations/* */adapters/* *.sql .github/*` | `orchestrator.sh` |
| `ORCH_FOLLOWUP_REPAIR_SECONDS` | `300` | `orchestrator.sh` |
| `ORCH_GUARD_MAIN_BRANCH` | unset (PILOT-66: the branch the post-checkout main-HEAD guard restores a seat's main checkout to; empty = first existing `ORCH_PROTECTED_BRANCHES` entry) | `hooks/post-checkout-main-head-guard.sh` |
| `ORCH_HEAD_GUARD_ACTIVE` | `0` (PILOT-66 internal re-entry flag: set to `1` by the post-checkout main-HEAD guard's own restoring `git checkout` so the hook never recurses — not an operator dial) | `hooks/post-checkout-main-head-guard.sh` |
| `ORCH_INPROGRESS_HEAL_SWEEPS` | `3` | `orchestrator.sh` |
| `ORCH_INSTANCE_ID_SOURCE` | unset | `orchestrator.sh` |
| `ORCH_INTEGRATION_CONFLICT_ROUTE` | `1` | `orchestrator.sh` |
| `ORCH_KILL_GUARD` | `1` (ABS-243 kill-guard hook) | `orchestrator-spawn-claude.sh` |
| `ORCH_LOCAL_MAIN_BRANCH` | `main` | `orchestrator.sh` |
| `ORCH_MAIN_REMOTE` | unset (this repo pins `gitlab` — PILOT-25 remote doctrine: GitLab live, Bitbucket=release mirror; the active-remote pin every push/MR follows, `scripts/active-remote-guard.sh`) | `orchestrator.sh` |
| `ORCH_EVENTS_WAIT` | `1` (ADR-A-0029 push path: the adapter prefers long-poll `events?wait=` when `capabilities` lists `events-wait`; `0` forces interval polling) | `orchestrator.sh` |
| `ORCH_EVENTS_WAIT_BUFFER` | `10` seconds of headroom subtracted from the server's wait cap so the client gives up before the server closes the long-poll | `orchestrator.sh`, `backend-shipper.sh` |
| `ORCH_RECONCILE_EVERY_SEC` | derived: `ORCH_RECONCILE_EVERY_N_CYCLES × ORCH_POLL_INTERVAL` — on the push path there are no cycles to count, so the reconcile sweep is paced in wall-clock seconds instead | `orchestrator.sh` |
| `ORCH_SEAT_UPSERT` | `1` (PILOT-26/ABS-499: the runner POSTs seat open/close rows first-hand so Live-Spawns are visible in Mission Control; `0` disables the producer) | `orchestrator.sh` |
| `ORCH_SEAT_UPSERT_TIMEOUT` | `4` seconds `curl --max-time` for the seat-upsert POST — telemetry must never stall a dispatch | `orchestrator.sh` |
| `ORCH_MERGE_GUARD` | `1` (PILOT-11 merge chokepoint; `0` restores unguarded merges) | `orchestrator.sh`, `hooks/pre-bash-merge-guard.sh` |
| `ORCH_MIRROR_REMOTE` | `origin` (PILOT-25 remote doctrine: the release-mirror remote — Bitbucket — that `release-mirror-push.sh` pushes main+tags to) | `release-mirror-push.sh` |
| `ORCH_MERGE_TOPO` | `1` (ADR-A-0025) | `orchestrator.sh` |
| `ORCH_MIRROR_GUARD` | `1` | `hooks/pre-commit-mirror-drift-guard.sh` |
| `ORCH_OPS_SWEEP_INTERVAL` | `3600` seconds (PILOT-42 cadence ops-sweep; `0` = OFF, byte-identical to legacy) | `orchestrator.sh` |
| `ORCH_OPS_SWEEP_MAX_PER_RUN` | `24` (the sweep's own per-run spawn budget, separate from the story/daily budget) | `orchestrator.sh` |
| `ORCH_OPS_SWEEP_ROLE` | `tdm` (seat role dispatched for the sweep — reused, not a new role) | `orchestrator.sh` |
| `ORCH_OPS_SWEEP_TICKET` | `ops-sweep` (synthetic key for the sweep's single-flight lock, packet filename and telemetry) | `orchestrator.sh` |
| `ORCH_OPS_SWEEP_TIERS` | unset / `""` = Phase-0 shadow (PILOT-43; `A` = Tier A mechanical hygiene, `AB` = Tier A+B evidence-bound tracker resolution; Tier C/D never auto-activate) | `orchestrator.sh` |
| `ORCH_OPS_SWEEP_MAX_PER_CLASS` | `3` (PILOT-43 runaway guard: > N findings of one class in a sweep => escalate instead of N actions) | `orchestrator.sh` |
| `ORCH_PHANTOM_EVENT_GUARD` | `1` | `orchestrator.sh` |
| `ORCH_PROMPT_SIZE_BUDGET` | `24000` bytes (PILOT-55/ABS-566: declared per-seat prompt budget — commons + role def + overlay; `scripts/agent-prompt-size.sh` reports the actual size per role and flags anything over budget as a defect, not an operating mode) | `agent-prompt-size.sh` |
| `ORCH_PROTECTED_BRANCHES` | `main master` | `hooks/pre-commit-local-main-guard.sh`, `merge-target-guard.sh` |
| `ORCH_PROTECT_LOCAL_MAIN` | `1` | `orchestrator-spawn-claude.sh` |
| `ORCH_RUN_ID_SEPARATION` | `1` | `orchestrator.sh` |
| `ORCH_SEAT_RACE_GUARD` | `1` (ABS-300 seat lock) | `orchestrator.sh` |
| `ORCH_SKILLS_DIR` | `$ORCH_HARNESS_HOME/.claude/skills` when that dir exists, else unset (ABS-535: the LIVE skills dir; concrete `harness/claude/skills/<name>` references in agent-def bodies are rewritten to it at spawn time and reads under it are allowlisted read-only, so a seat never resolves a skill load into the inert `harness/claude/` source and session-poisons itself on the permission denial) | `orchestrator-spawn-claude.sh` |
| `ORCH_STASH_GUARD` | `1` (ABS-272 stash-guard hook) | `orchestrator-spawn-claude.sh` |
| `ORCH_SYNC_TARGET_ALLOWLIST` | `1` | `orchestrator.sh` |
| `ORCH_TICKET_TAG_GUARD` | `1` (PILOT-79 commit-tag guard: the runner installs a `commit-msg` hook on provisioned story worktrees that rejects a seat/story commit whose message lacks the `[PREFIX-XXX]` ticket tag, so the RTE epic-integration bisect can always map a culprit commit to its story; `0` uninstalls the marker hook and skips the install — see `docs/sop/COMMIT_TAG_GUARD_SOP.md`) | `orchestrator.sh`, `hooks/commit-msg-ticket-tag-guard.sh` |
| `ORCH_VERIFY_EVIDENCE` | `1` (ABS-297) | `orchestrator.sh` |
| `ORCH_WORKTREE_DENY` | `Bash(git stash:*)` | `orchestrator.sh` |

> **`ORCH_AUTOMERGE` scope (ADR-A-0014, PILOT-10/ABS-513).** Auto-merge is legitimate
> **only for story MRs onto an epic integration branch** (`epic/*`) — never onto `main`.
> Epic-less lanes (e.g. v3 single-story pilots) have **no legitimate auto-merge target**;
> their MRs go to HITL. This is enforced mechanically, independent of the knob's value, by
> `scripts/merge-target-guard.sh check <target>` (rte duty step 4): any target in
> `ORCH_PROTECTED_BRANCHES` (default `main master`) is refused with a `MERGE-GUARD-REFUSE`
> intent line, no matter what `ORCH_AUTOMERGE` is set to (or claimed to be).

### Seat-context variables (spawn-seam contract, not operator knobs)

The runner sets these per spawned seat; operators never set them by hand. They
are listed so the knob drift guard can distinguish "undocumented knob" from
"seam contract variable": `ORCH_ROLE`, `ORCH_SEAT`, `ORCH_TICKET`,
`ORCH_RUN_ID`, `ORCH_SEAT_TOKEN`, `ORCH_PACKET_FILE`, `ORCH_PACKET_MODE`,
`ORCH_AGENTS_DIR`, `ORCH_OVERRIDES_DIR`, `ORCH_NOW`, `ORCH_GUARD_BRANCH`,
`ORCH_MIRROR_GUARD_STAGED` (the last two are hook-internal derivations).

## Async Spawns (ABS-111 A1)

Live spawns run as **background jobs**. The whole attempt→retry→record sequence runs in a subshell
that holds the ticket's single-flight lock for its lifetime; budget/dedupe/pending bookkeeping stays
in the parent. `live_spawn_count` prunes dead pids so `ORCH_MAX_CONCURRENT` (default 3) caps the
number of **in-flight** spawns — before ABS-111 the synchronous scheduler kept at most one spawn in
flight, so the cap was effectively inert.

- On `--once` and on every loop-exit path (kill switch, budget halt, `ORCH_MAX_CYCLES`) the runner
  **drains** in-flight background spawns (`wait_for_spawns`) before returning, so the `--once` test
  tier keeps its synchronous post-conditions.
- The concurrency cap still defers the `(N+1)`th eligible spawn to the in-memory pending set
  (`INTENT DEFER-CAP`), retried next cycle — unchanged from §5.1.
- `ORCH_ASYNC_SPAWNS=0` restores the legacy synchronous one-at-a-time scheduler (the mode the legacy
  test suites pin).

---

## Priority-Aware Dispatch (ABS-261)

The reconcile sweep dispatches tickets in adapter search order by default. With priority-aware
dispatch (`ORCH_PRIORITY_DISPATCH=1`, on by default) the sweep sorts the dispatchable set by
canonical `priority` field before the concurrency cap: a `hotfix` ticket claims the next free seat
ahead of queued feature work with no preemption of running seats.

### Priority order

| Priority | Rank | Notes |
| --- | --- | --- |
| `hotfix` | 0 (first) | May also overrun the concurrency cap; see below |
| `high` | 1 | |
| `normal` | 2 | Default when the field is absent or unknown |
| `low` | 3 | |

Within a band, tickets dispatch in the order the adapter search returns them (stable age-ascending
on the mock adapter; Jira-default order within a band on the live adapter).

### Setting priority on a ticket

Priority comes from the adapter dump's canonical `priority` field (ABS-242 mapping). On the mock
adapter:

```bash
# At creation:
scripts/mock-tracker.sh create "Fix login crash" --priority hotfix
# Update an existing ticket:
scripts/mock-tracker.sh update ABS-123 priority hotfix
```

On the live Jira adapter, set the Jira `Priority` field (`Hotfix`, `High`, `Normal`, `Low`) before
the ticket enters `Ready for Development`. Seats never set this field: only a Human or PO may
promote a ticket to `hotfix` (`harness/claude/agents/_common-rules.md` §12, "Prioritäts-Charter").

### Hotfix cap overrun (ORCH_HOTFIX_CAP_BONUS)

A `priority=hotfix` ticket may claim up to `ORCH_MAX_CONCURRENT + ORCH_HOTFIX_CAP_BONUS` concurrent
seats (default: `cap+1`). The dispatch gate raises the effective ceiling for the hotfix spawn; no
running seat is killed. A third hotfix at `cap=1, bonus=1` defers once two hotfixes already occupy
the ceiling.

Set `ORCH_HOTFIX_CAP_BONUS=0` to keep hotfixes within the plain cap (they still dispatch ahead of
lower-priority work). The knob has no effect when `ORCH_PRIORITY_DISPATCH=0`.

### Kill-switch

```bash
ORCH_PRIORITY_DISPATCH=0   # revert to legacy adapter-order dispatch
```

With the switch off, the dispatch order reverts to pre-ABS-261 adapter arrival/key order and
DEFER-CAP intents carry no `note=` field (byte-identical to the old behavior). Existing setups
without this var continue unmodified: the default is `1`, and an all-`normal` priority board
dispatches identically either way.

### Observability

With `ORCH_PRIORITY_DISPATCH=1`, every DEFER-CAP intent names the deferred ticket's priority in its
`note=` field:

```
DEFER-CAP ticket=ABS-123 role=be-developer to=Ready for Development note=priority=normal
```

To inspect the priority queue from the run log:

```bash
grep 'DEFER-CAP\|INTENT.*SPAWN' work/.orchestrator/run.log | tail -40
```

### Relationship to the multi-orchestrator workaround

Running two orchestrators partitioned by `JIRA_JQL_FILTER` (ABS-181) was the standard workaround
for passing a hotfix ahead of in-flight feature work. Priority-aware dispatch handles the common
case with one orchestrator: the hotfix advances to the head of the dispatch queue. The
multi-orchestrator lane (§ "Multi-Orchestrator Operating Mode" below) remains valid for traffic
that requires genuine isolation (separate credentials, per-lane cost caps, or a dedicated hotfix
runner) but is no longer the only path to expedite a single hotfix.

---

## Session Resume Until Acceptance (ABS-111 A2)

The runner keeps a **session store** under `$ORCH_STATE_DIR/sessions/`, one file per
`(ticket, role, status)`, holding the session id parsed from the spawn's JSON result. When a stored
session exists for a `(ticket, role, status)`, the runner **resumes** it instead of paying a cold
start (`INTENT RESUME`): the seam is handed `ORCH_RESUME_SESSION_ID`, which makes
`orchestrator-spawn-claude.sh` invoke `claude -p --resume <id>` and omit `--agents`/`--agent` (the
resumed session already carries its agent definition). This is the intra-task resume the ADR-A-0002
2026-07-06 amendment describes.

- **Resumes:** rework bounces (e.g. `Story Acceptance → Ready for Development`) and re-reviews
  (`In Review`/`In Test` re-entry) continue with warm context.
- **Retries stay fresh.** After a failed attempt the retry always spawns a fresh session — resuming
  a just-failed/timed-out session would repeat the failure mode.
- **Acceptance ends the scope.** Entering `Merging`/`Done` (acceptance passed) deletes the ticket's
  stored sessions (`clear_sessions`). Every spawn after that is fresh — no context bleeds across the
  task boundary.
- **Config generation gates every file-based resume (ABS-117).** Each stored session carries a
  generation stamp (line 2 of the session file): `cksum` over `orchestrator.sh` +
  `orchestrator-spawn-claude.sh`, computed once at runner startup. On mismatch — or a legacy
  unstamped file — the session is invalidated (`SESSION-INVALIDATED` run.log event) and the spawn
  proceeds fresh. `ORCH_CONFIG_GENERATION` overrides the computed value (operator
  force-invalidate: set any throwaway value and restart). Design record:
  `specs/ABS-117-session-generation-spec.md`. **Note (ADR-A-0023):** a resume is a new OS
  process that re-reads the live permission surface; `settings.local.json` therefore stays OUT of
  the generation (retro 2026-07-10, proven empirically — ADR-A-0023 §Context). What a resume
  DOES carry is the **conversation transcript**: the agent re-reads its own history of tool calls,
  including any prior `permission denied` errors. See "Poisoned-session guard" below for how the
  runner breaks that loop.
- `ORCH_SESSION_RESUME=0` disables resume entirely (strictly fresh per spawn).

### Poisoned-session guard (ABS-254 / ADR-A-0023 rule 3)

A seat that hit permission denials re-reads those `denied` entries from its transcript on every
resume and keeps reporting the phantom blocker — after the settings have already been fixed
underneath it. Consumer impact: 6+ spawns still failing with `Read denied` loops, escalating into
a demand for blanket write allowlists. No config-generation input can detect this, because a
poisoned session's generation inputs are identical to a healthy one's.

The fix: **do not store a session whose spawn result carried a denied _mutating_ tool.**
`store_session()` drops the file and deletes any previously stored session for that
`(ticket, role, status)`, logging `SESSION-POISONED` with the triggering tool + target. The next
spawn starts fresh against the fixed permission surface with no denial history. Blast radius:
exactly the affected sessions; a healthy store is never cold-started by a permission edit.

**Read-only denials do not poison (ABS-598).** The verdict is classified by the tool's mutation
property (`result_has_mutating_denial`), not by "a denial occurred". A refused read-only tool
(Read/Grep/Glob — see `ORCH_MUTATING_DENIAL_TOOLS`) leaves nothing inconsistent: the model simply
did not see a file, and the session's whole context is still usable. Only a refused mutating tool
(Write/Edit/NotebookEdit/Bash) can leave the tree/process state inconsistent with what the model
believes it did, which is what makes a resume unsafe. This stops a single denied `Read` from
discarding a full session's context (the Pilot-8 epic-integration incident: one refused
`Read` → 61 turns dropped → a cap-5 salvage that could not run the exit suite).

**Salvage interaction (ABS-175).** When a birth spawn hits both the turn cap AND permission
denials, the salvage resume re-reads the same poisoned transcript — the salvage's OWN result may
be clean, but it resumes the same session. The salvage store therefore inherits the birth-spawn
denial state (`force_poison` arg in `store_session`) and drops the session too.

**Input classification (ADR-A-0023).** The guard embodies the rule: hash what a session bakes,
ignore what a resume re-reads. Inputs classified:

| Input | Class | In generation? |
| --- | --- | --- |
| `settings.local.json` permissions / allowlist | spawn-fresh (re-read on resume) | No |
| Workspace trust (`~/.claude.json`) | not read in `-p` mode | No |
| `orchestrator.sh` + spawn seam | session-baked (shaped the system prompt) | Yes |
| Agent definitions | session-baked (`--agents` omitted on resume) | Yes |
| Conversation transcript / denial history | session-baked | handled by poison guard |

Kill-switch: `ORCH_SESSION_POISON_GUARD=0` (restores legacy store-anyway behaviour).

### Account-switch session invalidation (ABS-302)

The Claude CLI binds sessions to the **account** used when they were created.
Switching accounts — whether by `claude /login` as a different user, or by changing
`CLAUDE_CONFIG_DIR` to a directory the CLI has not used before — makes all previously cached
sessions unreachable: the CLI returns `No conversation found with session ID`. The built-in
one-retry (always a fresh session) catches the failure, but it discards accumulated session context
and wastes a turn.

On every **startup**, the runner derives the current account identity and compares it to the value
stored in `$SESSIONS_DIR/.account-id` from the last run. The identity is read from
`${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json` → `oauthAccount.accountUuid`, composed as
`uuid@configdir` (so a same-UUID account in a different config dir is also detected). When that
file is absent or has no UUID (pre-login or enterprise-SSO), the identity falls back to the config
dir path. If the stored and current identities differ:

1. Every session file in `$SESSIONS_DIR/` is deleted (except the `.account-id` marker itself).
2. An `ACCOUNT-SWITCH` line is written to `run.log`: `stored-account=… current-account=…;
   invalidating all cached sessions`.
3. A human-readable log line goes to stderr: `Claude account changed (… -> …); cached sessions
   invalidated`.

The fresh spawn then starts with no resume attempt (clean respawn, no wasted turn).

**Operator recipe when you intend to switch accounts:** restart the orchestrator after `claude
/login` or changing `CLAUDE_CONFIG_DIR`; the startup sweep clears the stale sessions automatically.
No manual session-dir cleanup is needed.

Kill-switch (shared with session resume): `ORCH_SESSION_RESUME=0` — sessions disabled entirely,
nothing to guard.

### Session-local watchers and operator notifications (ABS-302)

Background tasks (watchers, `Monitor` jobs, `run_in_background` processes) send notifications to
the **Claude session**, not to the operator. On a suspended app, or when the Claude process ends,
those notifications are never seen.

**Rule (SOP):** Whenever you set up a session-local watcher to monitor an orchestrator event
(run completion, JOIN fired, runner crash, human gate reached), always send the notification
**through two channels**:

1. `PushNotification` — reaches the operator's device via the Claude notification channel.
2. A macOS system dialog via `osascript`:
   ```bash
   osascript -e 'tell application "System Events" to display dialog "…" buttons {"OK"} default button 1 giving up after 300' &
   ```
   (`display notification` is unreliable on macOS when "Summarise notifications" is on; use
   `display dialog` instead: it surfaces as a blocking dialog that requires a click.)

Never rely on session-local output alone for operator-reaching events. The session may be gone by
the time the event fires.

### Handoff repair + status-evidence success (ABS-111 A2c / C7)

Two failure modes from live run 1 are fixed here:

- **Missing handoff → repair.** A spawn that exits cleanly but emits no parseable handoff is
  **resumed** with a tiny 4-turn budget and asked for only the `## Handoff` block (`INTENT
  REPAIR-HANDOFF`) — instead of a full duplicate re-spawn.
- **Status-evidence success.** If there is still no handoff but the ticket has **demonstrably left**
  the spawned status, the runner **synthesizes** a handoff from that evidence (`INTENT
  SYNTH-HANDOFF`) rather than recording a phantom `SPAWN-CRASH`. Committed work that simply didn't
  print a handoff block is no longer mislabeled as a crash.

---

## depends_on Gate (ABS-111 C8, release points: PILOT-19 merge-fact, PILOT-44 Docs-status)

At an **implementation-entry** status (`Ready for Development`, `Design`) the runner reads the
ticket's `depends_on` list; while any dependency is unmet, the ticket **rests** — the runner
logs `INTENT DEPENDS-WAIT` (note `unmet=<dep>:<status>`) and does **not** spawn. The reconcile sweep
re-derives the spawn once the dependency lands; there is no marker and no crash. An unreadable
dependency means WAIT (transient adapter errors clear on their own; a dead reference is an
operator fix). `ORCH_DEPENDS_GATING=0` disables the gate.

Release points — a blocker counts as satisfied the instant **any** of the following holds:

* it is `Done` (terminal; the Done-PR gate guarantees `Done` implies a merged PR), **or**
* its story head is an **ancestor of its merge target** — the epic integration branch for an epic
  child, else `main` — proven **mechanically** by `git merge-base --is-ancestor` (the
  PILOT-4/ABS-494 forge-less probe, `story_merge_state`), never inferred from a status label
  (PILOT-19 merge-fact — supersedes the ABS-119 Docs-label shortcut), **or**
* it rests in **`Docs`** (PILOT-44 — `Docs` is a POST-MERGE exit per ABS-266: a story reaches it
  only after its code is merged; only the documentation tail then runs). `Docs` is therefore treated
  as SATISFIED without re-proving it through the ancestry probe, releasing the downstream wave
  without the 10–20 min idle that the timing-flaky probe can impose. This is not a label-trust
  shortcut: `Docs` is structurally post-merge (ABS-266 makes it so), and the merge-fact probe
  remains in force for every other non-Done, non-Docs status.

This is the ABS-513 doctrine: *verify the merge, don't trust the label* — extended by PILOT-44 to
also trust the structural post-merge guarantee encoded in the `Docs` station. A `Done` status change
after a merge-fact or Docs release never re-blocks the dependent. The gate is entry-only: a
dependency later resting in `Blocked` from Docs never re-gates an already-running dependent. New
work branches of epic children base on the epic's integration branch tip (`epic/<parent>-*`,
lexicographic pick + warning on multi-match; fallback HEAD).

**Declarable exception (`depends-strict`).** A dependent that needs the blocker's **own finished
artifact** (e.g. the merged documentation, not just its code) carries the free-form label
`depends-strict`; for it **both** the merge-fact early release **and** the `Docs` early release are
suppressed — every `depends_on` must reach `Done`. The strict check runs first in `depends_unmet()`,
so `depends-strict` takes precedence over PILOT-44. This is the only opt-out — one label, no new
semantics. Default remains merge-fact / Docs release.

The epic-completion gate is unchanged and out of scope: an epic completes (JOINs) only when **all**
children are `Done` — a child in `Docs` does not complete the epic. Design lineage:
`specs/ABS-119-depends-acceptance-release-spec.md`.

---

## Runner-Provisioned Worktrees (ABS-111 C9)

Isolation is **infrastructure, not agent discipline**. For each implementer spawn (`Ready for
Development`) the runner provisions a git worktree `tmp/<ticket>-work` on branch `<ticket>-auto`
(under the state root) and hands it to the spawn seam as `ORCH_SPAWN_CWD` — the seam `cd`s there
before exec, so the agent physically **cannot** touch the main checkout (where the running loop
lives). `ORCH_SPAWN_CWD` takes precedence over `ORCH_TARGET_REPO`. Review/test seats are read-only
and keep the repo root.

- `git worktree add` calls are **serialized** via a global `mkdir` lock (concurrent adds against one
  `.git` can race; concurrent commits in separate worktrees are safe — per-worktree index).
- Worktrees must live **inside** the repo (`tmp/<ticket>-work`, gitignored) — the headless file-tool
  sandbox refuses writes outside the project dir (see "Known Limitations" below).
- **Provisioning fails closed, bounded, and escalating (PILOT-66).** If the worktree cannot be
  created (lock timeout, `git worktree add` error), the runner does **not** fall back to the main
  checkout — it emits `INTENT SKIP-NOWORKTREE` with `attempt=n/N` and git's own error text
  (previously the runlog showed only a bare `(git worktree add)`), rests the ticket at
  `Ready for Development`, and backs it off via `record_backoff` so the next reconcile cycle skips
  it for free during the delay period. After `ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS` consecutive
  failures (default 5) the runner escalates to `Blocked` with a `NOTIFY` Attention-Event and a
  gate-results comment instead of retrying silently. Failed retries cost no budget: the check runs
  before the spawn budget/lock/seam are touched. `ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS=0` counts
  and backs off indefinitely without escalating. Running a write-capable implementer under
  `--permission-mode dontAsk` in the loop's own tree is the failure C9 exists to prevent; the
  runner never degrades to it silently. `ORCH_WORKTREE_SPAWNS=0` opts the whole seam out of
  isolation.
- **Post-checkout main-HEAD guard (PILOT-66 AC3).** Root cause of 131 alarmless
  `SKIP-NOWORKTREE` retries in Pilot 5: a non-worktree seat running in the main checkout ran
  `git checkout -b <work-branch>` and left it checked out for hours — after which
  `git worktree add` on that branch fails for every dependent implementer. The
  `provision_main_head_guard` function (called at orchestrator startup) installs
  `scripts/hooks/post-checkout-main-head-guard.sh` as the repo's `post-checkout` hook. When a
  seat in the main checkout switches HEAD to a non-protected branch and the restore is provably
  safe (clean tree, new branch at the same commit as the protected branch — the exact
  `git checkout -b` fingerprint), the hook snaps HEAD back and preserves the branch ref so a
  later `git worktree add` succeeds. On an unsafe move the hook warns only (fail-open); the
  count -> backoff -> escalate path catches the downstream block with git's own error text.
  Kill switch: `ORCH_PROTECT_LOCAL_MAIN=0` (ABS-111 pattern; sibling of the ABS-224
  pre-commit guard).
- **Scope.** The worktree-eligible spawn statuses are `Ready for Development`, `In Progress`,
  `In Review`, and `In Test` (single source: `worktree_eligible_status` in `scripts/orchestrator.sh`).
  The `Ready for Development` seat owns the `<ticket>-auto` branch the RTE later opens a PR from;
  `In Review`/`In Test` seats reconnect that same branch so reviewers see the work without switching
  the main checkout (ABS-111 hotfix). `In Progress` is eligible for the ABS-116 BOUNCE-REROUTE resume
  ONLY — a reviewer/gate backward bounce (`In Review`/`In Test -> In Progress`) that re-routes to the
  implementer; forward and neutral `In Progress` transitions map to NOOP and never spawn, so this
  never provisions a worktree for a non-implementer seat (ABS-207, closing the residual ABS-166
  cwd-loss on the recovery path). The `Design` seat writes design docs and keeps the repo root.
- `ORCH_WORKTREE_SPAWNS=0` disables provisioning (the spawn keeps the repo-root / `ORCH_TARGET_REPO`
  cwd). This closes live run 1's failure where agents switched the main checkout's branch.

### Local permissions travel into the worktree (ABS-131)

`git worktree add` only carries **tracked** files, but `.claude/settings.local.json` (the operator's
local Write/Edit grants) is **gitignored** — so a freshly-provisioned worktree inherited none of
those grants and the implementer seat failed closed on its first edit, composing its whole
implementation as a Jira comment instead (Befund 1, run ABS-126). ABS-134 root-caused the related
Befund 3 symptom — denials on the **first** Bash tool calls of any fresh spawn — as the same race:
the allow-list file arrives out-of-band after `git worktree add` and races the spawn's first tool
call under `--permission-mode dontAsk`; verbatim replay of the denied commands succeeded later in
the same session, proving the denial is a function of spawn state, not command content. The decisive
tell: the same `po-agent` role appeared on both the affected (prioritization, fresh spawn) and
unaffected (acceptance, resumed/warmed) sides (full root-cause analysis:
`docs/agent-outputs/ABS-134-bash-denial-analysis.md`). Provisioning now closes that gap:

- After a successful `git worktree add`, the runner copies
  `<state-root>/.claude/settings.local.json` into `tmp/<ticket>-work/.claude/`. **Absent source is a
  graceful no-op** with a `worktree provisioning: no settings.local.json …` log event — never a
  crash (the worktree is still usable; the seat simply relies on the committed baseline allowlist).
- It then merges `ORCH_WORKTREE_EXTRA_ALLOW` into the copy's `permissions.allow`. **Default**
  `Bash,Write,Edit` (ABS-154) — bare tool grants so a seat can read/write/commit/**push** reliably
  **inside the isolated tree** instead of depending on the (possibly restrictive) copied target
  allowlist, which left headless seats hitting intermittent Bash denials (ABS-130-RC-Run: the
  ABS-137 seat landed 1 of ~10 edits; `rte` could not push). This is safe because the grants apply
  **only inside the isolated, throwaway worktree** — the live loop lives in the main checkout, whose
  allowlist is never touched. Override with any comma-separated Claude-Code permission entries, or
  set it empty to disable the extension. The merge is idempotent (`unique`) and needs `jq`; absent
  `jq` is a logged no-op.
- **This never touches the main-checkout allowlist** and never commits `settings.local.json` — the
  copy stays gitignored/untracked inside the worktree, so it is discarded automatically when the
  worktree is torn down (`git worktree remove` / `rm -rf tmp/<ticket>-work`). No cleanup step needed.

### Fresh-base provisioning (ABS-355)

`ensure_worktree` previously based new seat branches unconditionally on `origin/main`. During
the 2026-07-16 Bitbucket outage, `origin` was frozen at a pre-release tip while `gitlab/main` was
current; seats provisioned from the stale tip lacked the ABS-335 live-state guard, and their test
teardown traps wiped the live state dir (the "second live-state wipe" incident).

`resolve_fresh_base()` replaces the hardcoded `origin/main` reference: before `git worktree add`,
the runner probes every configured remote via `ls-remote` (the "fetch success" check) and picks the
one whose `<main>` tip carries the **newest commit timestamp**. A frozen or unreachable remote
produces no output and is skipped. With no reachable remote at all the runner falls back to the
checkout HEAD and logs a warning. This matches the remote-selection the RTE/merge path makes under
the GitLab-fallback doctrine — provisioning and merging always agree on the base.

Every probe runs inside `_bounded_git`, a portable hand-rolled wall-clock timeout (no `timeout(1)`
or `gtimeout` required; absent on stock macOS) with `http.lowSpeedLimit/lowSpeedTime` set so a
stalled HTTPS transfer also aborts. The ceiling is `ORCH_REMOTE_PROBE_TIMEOUT` (default 12 s). A
remote that exceeds the ceiling counts as unreachable; the runner moves to the next one.

---

## Spawn-Seam Env Scrub (ABS-355)

The runner exports its live-state variables (`ORCH_STATE_DIR`, `ORCH_STOP_FILE`, `ORCH_RUN_LOG`,
`ORCH_INSTANCE_ID_FILE`, `JIRA_TRACKER_STATE`) at launch; before ABS-355 these leaked into every
seat. A seat whose worktree contained `tests/test-orchestrator.sh` inherited those paths, drove
tests against the runner's **live** state dir, and its `EXIT` trap (`rm -rf "$ORCH_STATE_DIR"`)
wiped the live dir — the double wipe on 2026-07-16.

`run_spawn_cmd` now prepends
`env -u ORCH_STATE_DIR -u ORCH_STOP_FILE -u ORCH_RUN_LOG -u ORCH_INSTANCE_ID_FILE -u JIRA_TRACKER_STATE`
to every seat exec. The runner's own environment is untouched; the seat and its child processes see
clean variables. The ABS-335 fail-closed guard (which refuses to touch a state dir whose instance-id
does not match the spawning runner) remains defense-in-depth, not the only line.

### Main-checkout seat isolation (ABS-393)

ABS-355's env-scrub covered worktree seats. It left a gap for seats that run **in the main
checkout** — rte, tech-writer, and bsa. A seat whose `REPO_ROOT` is the main checkout re-derives
the live state dir from the default `${ORCH_STATE_DIR:-$ORCH_STATE_ROOT/work/.orchestrator}` even
after the env-scrub clears `ORCH_STATE_DIR`, because `ORCH_STATE_ROOT` defaults to `REPO_ROOT`.
The ABS-205 nested re-pin cannot help: its condition (`REPO_ROOT != ORCH_PARENT_STATE_ROOT`) is
false for a main-checkout seat, so it falls through to the live path. A suite or cleanup subpath
`rm` inside that seat then wipes the live ledger/locks/sessions/instance-id while leaving `run.log`
intact — the exact forensic signature of the 2026-07-17 partial wipe (168 ledger entries,
TDM visited-throttle, and session-resume continuity lost).

ABS-393 extends the nested-isolation seam (orchestrator.sh:456–481). When a seat's
`REPO_ROOT == ORCH_PARENT_STATE_ROOT` (main-checkout seat):

- `ORCH_STATE_ROOT` stays set to the real checkout so git operations inside the seat still
  point to the correct repo.
- The **default state dir** is redirected to a disposable throwaway:
  `${ORCH_SEAT_STATE_ROOT:-${TMPDIR:-/tmp}/orch-seat-state-$$-${RANDOM}}/work/.orchestrator`.
  A seat's suite or cleanup trap now targets that throwaway, never the live ledger.
- An explicit `ORCH_STATE_DIR` env var still takes precedence (`${VAR:-default}` semantics),
  so tests that pin a deterministic path via `new_env` are byte-for-byte unchanged.
- The top-level runner (no `ORCH_PARENT_STATE_ROOT` set) is untouched.

*Test override:* set `ORCH_SEAT_STATE_ROOT` to a deterministic temp directory when you need a
predictable throwaway path in test setups (the regression suite in
`tests/orchestrator.d/ABS-393-main-checkout-state-isolation.sh` uses this).

---

## State-Dir Self-Heal (ABS-355 / ABS-393)

When a seat wiped `ORCH_STATE_DIR` from under the runner (via the pre-ABS-355 env leak), the
runner entered a `LOCKS_DIR`-ENOENT loop: `acquire_lock` called `mkdir <per-ticket-lock-dir>`,
hit ENOENT on the wiped parent, returned `1`, and misread that as "ticket already held" — every
ticket appeared locked and the runner spun owning nothing.

Two fixes close this:

- **`acquire_lock`** recreates `LOCKS_DIR` with `mkdir -p` before the per-ticket `mkdir`. The call
  is cheap and idempotent on the normal path (directory already present).
- **`heal_state_dir()`** runs at the top of every `one_cycle()` pass. When `ORCH_STATE_DIR` or the
  instance-id file is absent, it recreates the base directory tree (`ORCH_STATE_DIR`, `LOCKS_DIR`,
  `PACKETS_DIR`, `SESSIONS_DIR`), re-stamps the runner's own instance-id marker, and emits a `WARN`
  event to `run.log`. It only stamps the marker when the file is **absent** — never when a differing
  id is present — so in a two-orchestrator setup the ABS-335 guard remains the authority for
  instance-id conflicts.

### Forensic self-heal logging (ABS-393)

Before ABS-393, `heal_state_dir` emitted a single blanket `WARN state-dir self-heal: … was missing`
line that hid exactly which live subtrees were lost. The 2026-07-17 partial wipe (ledger/locks/
sessions/packets/instance-id gone, `run.log` survived) showed that a finer-grained record is needed.

`heal_state_dir` now:

1. Classifies the wipe as **full** (the `ORCH_STATE_DIR` directory itself is gone) or **partial**
   (the top-level directory survived but subdirectories or files under it are missing).
2. Enumerates each missing component before recreating it: `state-dir`, `locks/`, `packets/`,
   `sessions/`, `instance-id`, `spawn-ledger`.
3. Emits a single forensic line: `WARN state-dir self-heal (<full|partial> wipe): recreated <components>`.
4. After recreating the directories, calls `rebuild_daily_ledger` if the spawn-ledger file is
   missing (see "Wipe-resistant spawn ledger" below).

*Operator symptom:* a `WARN state-dir self-heal` line in `run.log` means the state dir was wiped
mid-run. The `(partial wipe)` vs `(full wipe)` tag and the component list identify which incident
class occurred. No operator action is needed for the runner to continue; check the listed
components to understand the blast radius. If `spawn-ledger` appears in the list, confirm the
reconstructed entry count in the same line (`spawn-ledger reconstructed from run.log (N entries —
budget preserved)`) matches your expected daily spend.

---

## Per-Seat Turn / Model Overrides (ABS-111 A3 / B6)

Two per-seat overrides let one heavyweight seat get more room without raising the global ceiling:

- `ORCH_MAX_TURNS_<ROLE>` — per-seat turn ceiling, beats the global `ORCH_MAX_TURNS`.
- `ORCH_MODEL_<ROLE>` — per-seat model, beats the role frontmatter and global `ORCH_MODEL`.

`<ROLE>` is the role name uppercased with dashes turned into underscores — e.g.
`ORCH_MAX_TURNS_ISSUE_ENRICHMENT=120`, `ORCH_MODEL_QAS=sonnet`. (Handoff-repair internally uses a
tiny 4-turn budget that beats even these, since it only needs to re-print the handoff block.)

### Turn-ceiling resolution (ABS-156, calibrated PILOT-65)

Every role's turn cap is **calibrated from the measured turn distribution**, not guessed. The rule:
`cap = ceil_to_10( observed_peak × 1.5 )` (observed_peak = measured max where known, else median),
so the median run sits at ~2/3 of the cap and the cap is a genuine **emergency brake ABOVE the
observed maximum** — not a target the median hugs. PILOT-65 corrected the earlier values, where every
measured `error_max_turns` abort landed exactly on the role's ceiling:

| seat(s) | built-in cap | basis |
| --- | --- | --- |
| `be-developer` `fe-developer` `data-engineer` | `140` (`ORCH_MAX_TURNS_IMPLEMENTER`) | observed peak ~90 × 1.5 |
| `qas` | `180` | observed **max 119** × 1.5 (old cap 80 sat *below* the max) |
| `tech-writer` | `80` | median 53 (old cap 50 sat *below* the median) |
| `system-architect` | `60` | median 40 (old cap 40 = median) |
| `ui-ux-design` `qas-design` `data-provisioning-eng` `security-engineer` | `50` | median 30–32; **previously had NO built-in and fell silently to 25** — 6 aborts in Pilot 5 |
| `rte` | `100` | ABS-605: `ceil_to_10(61 × 1.5)` — hit `error_max_turns` at `num_turns=61` against the old cap 60; an epic-integration run drives sync-rebase + ABS-453 full suite + deploy + smoke |
| `issue-enrichment` | `60` | unmeasured, kept |
| `po-agent` | `40` | unmeasured, kept |
| any other role | `50` (`ORCH_MAX_TURNS_DEFAULT_ROLE`) | explicit per-role default — never the lean 25 |

The per-spawn ceiling resolves highest-precedence first:

1. handoff-repair `SPAWN_MAX_TURNS_OVERRIDE` (tiny budget, beats everything);
2. `ORCH_MAX_TURNS_<ROLE>` — explicit per-seat override;
3. an **explicitly set** operator-wide `ORCH_MAX_TURNS` (a deliberate all-seats cap);
4. the calibrated per-seat built-in (`builtin_role_max_turns`, table above);
5. `ORCH_MAX_TURNS_IMPLEMENTER` (140) for implementer seats;
6. `ORCH_MAX_TURNS_DEFAULT_ROLE` (50) for every other seat — PILOT-65 removed the silent fall to 25.

The cap is a ceiling, not a target — a fast seat that finishes early is unaffected by a higher ceiling.
A seat that DOES hit the cap is logged as its own `turn-cap` blocker class (not a crash) and is
budget-neutral for the iteration/rework counters: the iteration-guard's `INFRA_ABORT_RE` excludes it
and `rework_count` skips the orchestrator-actor route that carries it, so a cap abort is never billed
as a functional bounce (PILOT-65 AC3/AC4, continuing ABS-555).

---

## Observability — run.log and timestamps (ABS-111 D11 / D12)

Runner log lines are timestamped, and every intent/log line is **mirrored** into a structured,
append-only **TSV event log** at `$ORCH_RUN_LOG` (default `$ORCH_STATE_DIR/run.log`). Columns:

```text
ts    kind    ticket    role    to    note
```

- `kind` is `INTENT-<ACTION>` (e.g. `INTENT-SPAWN`, `INTENT-DEFER-CAP`, `INTENT-RESUME`), `LOG`, etc.
- `SEAT-CWD` (ABS-194) records the **effective working directory** every spawn is handed, emitted
  once per spawn at the single spawn choke point (first spawn, salvage-resume, handoff-repair). The
  `note` column is `cwd=<path>` (the provisioned worktree) or `cwd=<main-checkout>` when the seat runs
  in the repo root. On a resume the runner **re-derives** this identically to the first spawn
  (`worktree_for <ticket>`) instead of falling back to the main checkout (origin ABS-166), so a Cwd
  loss on the resume/race path is immediately visible here — `grep SEAT-CWD run.log` shows the tree
  each seat actually ran in. Mirrored to a human `LOG` line on stderr.
- One `printf` per line, so concurrent background spawns (A1) interleave safely.
- Spawn **stderr** is captured to a file and **kept on failure** (previously discarded; spawn
  failures were undiagnosable); the last line is logged. Spawn **stdout** (the Claude CLI
  Result-JSON from `--output-format json`) is also retained on failure (`rc != 0` or no parseable
  handoff) as a `*.out.*` file alongside the stderr; `run.log` records a `spawn stdout kept:` line
  naming the path. The success path (`rc=0` with a handoff) removes it. (ABS-265)
- When the crashed spawn's Result-JSON is parseable, `$pf.diag` gains a `subtype=` line naming the
  failure class (e.g. `error_during_execution`, `error_max_turns`). The blocker classifier reads it
  from `attempt_diag`; crash escalation comments name the error class without a live `lsof`/`ps`
  probe. (ABS-265)
- `SKIP-UNLABELLED` is emitted to **stdout once per ticket per run** (the reconcile sweep used to spam
  one line per resting Backlog ticket per sweep); the run.log still records every occurrence.
- `POLICY-INJECT` (ABS-382) records the `policy_rev` each seat is spawned against — one line per
  packet build, with `note=policy_rev=<hash>` (or `policy_rev=none` on an adapter without the
  `policies` op or when `ORCH_POLICY_INJECT=off`). It fires on both a cache hit and a miss (emitted
  before the cache-hit early return), so the audit trail is unbroken: `grep POLICY-INJECT run.log`
  ties every spawn to the exact revision-pinned policy text it saw. See "Revision-Pinned Policy
  Injection" below.

**Timing analysis.** Because `run.log` timestamps every `INTENT-SPAWN` / `HANDOFF` / `RESUME` /
`SALVAGE-RESUME` / `DEFER-CAP`, you can measure per-seat spawn latency, resume vs. cold-start cost,
salvage frequency vs. full respawn cost, and concurrency-cap defer frequency directly from it — e.g.
diff the `INTENT-SPAWN` and matching `HANDOFF` timestamps for a `(ticket, role)` pair to get
wall-clock spawn duration, count `INTENT-DEFER-CAP` rows to see whether `ORCH_MAX_CONCURRENT` is
throttling, and count `INTENT-SALVAGE-RESUME` rows to see how often turn-cap exits are recovered
without a full cold respawn. It is the primary data source for tuning the budgets and the concurrency
cap after a real run.

---

## Revision-Pinned Policy Injection (ABS-382 / ABS-231 S5)

Every spawn packet can carry the seat role's effective governance policy, pinned to the exact
revision the seat saw. When the tracker adapter offers the `policies` op (delivered by S4/ABS-381),
`build_packet` prepends a policy block to the packet **before** `=== TICKET ===`:

```text
=== POLICY (policy_rev: 3a1b2c…) ===
<rendered effective-policy text for this seat's role>

=== TICKET ===
<ticket dump>
```

The runner calls `tracker policies --audience "$role"` once per build. The op prints the rendered
policy text followed by a trailing `policy_rev: <sha256>` line; the runner lifts that hash into the
block header and strips the trailing line from the body. The `policies` op itself is documented in
[docs/guides/AGENTIC-BACKEND-API.md](../guides/AGENTIC-BACKEND-API.md).

### Default-safe behaviour

This is the second opt-in orchestrator edit after the ABS-238 packet probe, and it defaults safe:

- **Adapter without `policies` (mock/jira):** the op exits non-zero, the block is omitted, and the
  packet is **byte-identical** to the legacy packet. No change for anyone not running a
  `policies`-capable adapter.
- **`ORCH_POLICY_INJECT=off`:** forces the legacy path even on a capable adapter — also
  byte-identical to the legacy packet.

Injection is context only. It hands the seat governance text to read; it grants no new authority and
touches no human-only boundary. Policy writes stay server-side (403 for agent tokens in S2/S3).

### Cache invalidation

`policy_rev` folds into the `build_packet` cache signature alongside the ticket's `updated` field.
A policy change bumps the hash and re-derives the packet — exactly like an `updated` change — while
an unchanged policy set re-hits the cache and serves the same packet.

### Audit trail

Each spawn writes one `POLICY-INJECT` line to `run.log` recording its `policy_rev` (`policy_rev=none`
when no policy applies). The line is emitted before the cache-hit early return, so it fires on both a
hit and a miss. To reconstruct which revision a seat was spawned against:

```bash
grep POLICY-INJECT work/.orchestrator/run.log | tail -40
```

---

## Live-Run Allowlist Baseline

For a `dontAsk` (`--permission-mode dontAsk`) live run, the spawned agents' `.claude/settings.local.json`
must pre-permit every command and write path a seat needs — a spawn cannot pause for a permission
prompt. Beyond the tracker adapter scripts (`scripts/mock-tracker.sh` / `scripts/jira-tracker.sh` and
whatever `$TRACKER_CMD` resolves to), the baseline allowlist needs:

- **Shell basics** used inside compound commands: `echo`, `env`, `pwd`, `which`, `find`, `sort`,
  `uniq`, `tr`, `cut`, `date`, `test`, `printf`. A compound command (`a && b && c`, pipelines) fails
  if **any single segment** is not allowed — allow all of these, not just the "interesting" command,
  or an otherwise-permitted pipeline is denied on its first unlisted segment.
- **Write/Edit** on the paths a seat legitimately produces: `tmp/**` (the provisioned worktree, C9),
  `specs/**`, `docs/**`, `tests/**`.
- **NOT `scripts/**` in the main checkout.** The running orchestrator loop lives under `scripts/`;
  implementers work in their **provisioned worktree** (`tmp/<ticket>-work`, C9), never the main
  checkout's `scripts/`. Keeping `scripts/**` off the write allowlist is deliberate — it prevents a
  spawn from editing the live loop out from under itself. (Live `.claude/` writes are blocked by a
  separate built-in guard regardless of the allowlist — see "Known Limitations" below.)

**Adapter path-form variants (ABS-193).** If you pin the tracker adapter to a *literal-path* Bash
rule instead of a bare `Bash` grant (a restrictive main-checkout allowlist), the Claude Code
permission matcher matches on the **exact command prefix** — `Bash(scripts/jira-tracker.sh:*)` and
`Bash(/abs/path/scripts/jira-tracker.sh:*)` match those literals, but a `./`-prefixed invocation
(`./scripts/jira-tracker.sh …`) is a **different** prefix and is **denied** under
`--permission-mode dontAsk`. The primary defence is that the runner tells every seat to invoke
`$TRACKER_CMD` **verbatim as printed** (build_packet's duty-note: "do NOT prepend `./`"), so a seat
that copies the packet's literal never emits the `./` form. As belt-and-suspenders for operators who
run with a **relative** `TRACKER_CMD` (e.g. `scripts/jira-tracker.sh`), also seed the `./` variant so
an improvised local-script invocation still matches:

```jsonc
// settings.local.json (restrictive main checkout) — seed BOTH forms, or use a bare "Bash" grant
"Bash(scripts/jira-tracker.sh:*)",     // the packet-literal (relative) form
"Bash(./scripts/jira-tracker.sh:*)",   // ABS-193: the ./-prefixed form a seat may improvise
"Bash(scripts/mock-tracker.sh:*)",     // local mock-adapter equivalents
"Bash(./scripts/mock-tracker.sh:*)"
```

The widening is minimal and justified: it grants **only** the same adapter script under an
equivalent path spelling, no new command surface (AC ABS-193 #6). A bare `Bash` grant (the ABS-154
worktree default) sidesteps the whole path-form question and needs none of these entries.

Validate the baseline on a fenced dry-run first, then a single-ticket live run; use `run.log`
(above) to confirm each seat completed without a permission-denied stall before widening scope.

---

## Backlog Opt-In Gate (ABS-101)

By default the orchestrator does **not** touch a `Backlog` ticket. It picks one up — the PO
prioritization sweep, and the mechanical stall rules — **only when the ticket carries the
`orchestrator-ready` label** (`ORCH_START_LABEL`). An unlabelled ticket is fully inert: the
`Backlog` event logs `INTENT SKIP-UNLABELLED` and returns, no stall rule fires, and the reconcile
sweep does not re-derive it.

**Why opt-in (a "start" label), not opt-out (a "skip" label):**

- **Fail-safe default.** A forgotten label yields *inaction*, never an agent grabbing an
  under-specified ticket. The cost of the mistake is "nothing happened", not "money burned on the
  wrong work".
- **Cheap migration.** Adopting the boilerplate into a project with an existing backlog means
  labelling only the handful of tickets you want worked — not skip-labelling everything else.

**Operating it:**

- **Release a ticket:** add the `orchestrator-ready` label (tracker UI; or, on the mock adapter,
  `scripts/mock-tracker.sh create --label orchestrator-ready …` / `… update <id> labels
  "[orchestrator-ready]"`). Adding it to a ticket already resting in `Backlog` takes effect on the
  next reconcile sweep — no restart needed.
- **Disable the gate entirely:** `ORCH_REQUIRE_START_LABEL=0` (every `Backlog` ticket eligible).
  Suitable for a greenfield project where every ticket is agent-created and enriched.
- **Rename the label:** `ORCH_START_LABEL=<label>`.
- **Jira:** the label maps to a native Jira label. For an even tighter fence, set
  `JIRA_JQL_FILTER='labels = orchestrator-ready'` so unlabelled tickets never enter the sweep at
  the adapter level at all.

Not to be confused with enrichment's *agent-ready* (which means "groomed and executable" — the
**output** of grooming). `orchestrator-ready` is the human **input** gate: "you may start this."

---

## The Cost Gate (ADR-A-0009)

License and LLM API costs are a human-approval boundary, not a runtime knob an agent can silently
raise. The orchestrator enforces this mechanically:

- **`ORCH_MAX_SPAWNS_PER_RUN`** (default 50) is the per-run **soft** spawn cap. It is decremented on
  every spawn attempt (only `--live` spawns consume it) and is **not** persisted across runs; each
  process starts with a full budget.
- **Progress-aware behaviour at the soft cap (PILOT-47).** Reaching the soft cap no longer hard-stops
  a healthy run — the sensor used to be progress-blind and paused productive long runs mid-flight.
  Instead, in order:
  - **Auto-extend** (`ORCH_SPAWN_BUDGET_AUTOEXTEND`, default on): while the run shows progress (the
    Done count rose since the last checkpoint) the soft cap grows in increments of
    `ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT`% (default 25) of the original cap. Each extension logs
    `SPAWN-BUDGET-EXTEND` with a health picture (`x/y Done, spawns=N, cost=$Z`) and wakes the
    operator over the push channel — instead of stopping. It never crosses the hard backstop.
  - **Drain** (`SPAWN-BUDGET-DRAIN`): if it cannot extend (no progress, or auto-extend off), the run
    enters **drain mode** — it holds **new intake** (logs `INTENT SKIP-DRAIN-INTAKE`) but lets every
    **in-flight** ticket (one that already spawned this run) finish its pipeline. Once nothing is
    in-flight it ends the run **cleanly** with `DRAIN-COMPLETE` and **exit 0** — not the exit-75 pause.
- **Per-ticket cap** (`ORCH_MAX_SPAWNS_PER_TICKET`, default 25) is the precise loop-breaker: a single
  ticket that respawns that many times this run is escalated to `Needs PO Decision`
  (`BLOCK-TICKET-SPAWN-CAP`) while the run continues for everything else.
- **Hard backstops still fail-closed to exit 75.** The absolute per-run ceiling
  (`ORCH_MAX_SPAWNS_PER_RUN` × `ORCH_SPAWN_BUDGET_HARD_MULTIPLE`, default 2× = 100) and the per-day
  ledger (`ORCH_MAX_SPAWNS_PER_DAY`) keep the ABS-455 restart handshake: NOTIFY, `INTENT SKIP-BUDGET`,
  the `BUDGET-PAUSE exit` line + persisted restart counter, and exit code 75. Raising these is a human
  decision — there is no auto-resume for the hard case.
- **Concurrency (`ORCH_MAX_CONCURRENT`, default 3)** is a *cost-shape* control, not a budget: it
  caps how many spawns happen in one cycle, smoothing burst cost/load rather than limiting total
  spend. Deferred events are retried automatically (pending set, §5.1) once a slot frees — they
  are not lost and do not require a human to re-trigger them.

---

## Multi-Orchestrator Operating Mode (ABS-181)

Out of the box the orchestrator assumes it is the **only** runner touching the tracker: it stakes
no cross-machine claim (`ORCH_CLAIM_MODE=off`, byte-for-byte the single-runner dispatch path). To
run **two or more** orchestrators against the same tracker safely, arm the distributed
whole-ticket claim. It is a **Tier-2** lock — a `kind: claim` comment posted through the adapter
(ADR-A-0007) and adjudicated by **server comment-creation order** — layered above the per-checkout
**Tier-1** `mkdir` single-flight lock (§5.2). Two runners that stake near-simultaneously each wait
a settle window, re-read, and the earliest-created live claim wins; the loser skips the ticket
(`INTENT SKIP-CLAIMED`). The mechanism is zero-dependency bash (ADR-A-0009): settle/jitter via
`sleep`, TTL via `date`+arithmetic, identity via a persisted file — no external service.

Design source of truth: `specs/distributed-ticket-claim-spec.md` (§4.5 affinity, §4.6 fairness,
§6 rollout, §7 dispatch wiring, §10 recovery). The runner functions live in
`scripts/orchestrator.sh` (`acquire_remote_claim`, `first_live_claim`, `stake_claim`,
`refresh_claim`, `resolve_instance_id`).

### Claim configuration (env vars)

| Variable | Default | Purpose |
| --- | --- | --- |
| `ORCH_CLAIM_MODE` | `off` | Master switch. `off` = single-runner path, no claim staked (ADR-A-0010 regression guard). Any other value (e.g. `on`) arms the Tier-2 cross-machine claim in `dispatch`, gated **after** the concurrency-cap admission (see Fairness). |
| `ORCH_INSTANCE_ID` | *(unset → minted)* | This runner's staking identity — the adjudication key written into every claim comment. Precedence: an explicit env override is used verbatim (never minted-over or persisted-over); else the persisted file is reused; else a fresh id is minted and persisted. **Set this explicitly per machine only if you want stable, human-readable instance ids** — otherwise leave it to the mint/persist path. |
| `ORCH_INSTANCE_ID_FILE` | `<state-dir>/instance-id` | Where the minted identity is persisted. **Reused verbatim across restarts** — the identity invariant: a restart must NOT re-mint, or the runner would fail to recognize its own still-live claims and self-yield for up to one TTL. |
| `ORCH_CLAIM_SETTLE_MS` | `1500` | Fixed wait (ms) after staking, before adjudication, so every near-simultaneous stake is visible to all racers. |
| `ORCH_CLAIM_JITTER_MS` | `1000` | Extra random `0..N` ms added to the settle wait so two racing runners do not adjudicate in lockstep. |
| `ORCH_CLAIM_TTL` | `600` (seconds) | Claim staleness / reclaim window. A claim counts as **live** only while its server-side comment timestamp is younger than this; the holder re-stakes (heartbeat) at ~`TTL/3` to stay live. A stale claim is reclaimable by any peer (TTL takeover — see Recovery). |

> **`ORCH_CLAIM_ASSIGN` / `ORCH_CLAIM_MAX_OWNED`** were scoped in the ABS-181 epic design but are
> **not implemented** in the current claim code (`scripts/orchestrator.sh` as of ABS-185) — setting
> them has no effect. Fairness is enforced structurally by the post-cap claim placement below, not
> by a per-machine owned-count knob. This note will be replaced with real rows if/when those knobs land.

### One-step rollout — enable `ORCH_CLAIM_MODE=on` on ALL machines at once

When you add the second orchestrator, flip `ORCH_CLAIM_MODE=on` on **every participating machine in
the same deliberate step**. **There is no supported mixed on+off fleet.** A runner with the claim
**off** stakes no claim and does not check for a peer's claim — it will spawn a ticket another
machine is already working, **double-spawning** it (two seats, two branches, duplicate handoffs and
tracker comments for the same `(ticket, status)`).

The rule is safe precisely because the fleet grows **1 → 2 in one operator action**: you are never
in a stable steady state where one runner has the flag and another does not. Enable on all, or run a
single orchestrator with the flag off (the default) — never a partial rollout.

*Operator-visible symptom of getting it wrong:* two `INTENT-SPAWN` rows (different instance ids /
machines) for the same ticket and status in the merged run logs, and duplicate `kind: handoff`
comments on the ticket.

### Affinity — a ticket sticks to the machine that first claimed it

Every episode of a ticket (initial development, rework bounces, re-reviews) runs on the machine that
first won its claim, until the ticket is **terminal** (`Done` / `Epic Done`). The holder heartbeats
its claim, so on any re-dispatch its own claim is still live: `acquire_remote_claim`'s pre-check
finds the live holder is itself and returns an idempotent win (`INTENT CLAIM-WON note=reclaim=own
idempotent`) — no second stake. A peer that evaluates the same ticket finds someone else's live
claim and backs off (`INTENT SKIP-CLAIMED holder=<other-id>`). A terminal ticket has no holder, so
its claims are ignored.

*Operator-visible symptom:* in the run logs the owning machine repeatedly logs `CLAIM-WON
reclaim=own idempotent` for the ticket across its whole lifecycle; peers log `SKIP-CLAIMED
holder=<owner-id>`. Work never hops machines mid-ticket.

### Fairness — claim only what you can spawn now

The claim is staked **after** the concurrency-cap admission and **before** the budget/`LIVE_SPAWNS`
increment (ABS-185 dispatch placement). Two consequences:

- A ticket **deferred for the concurrency cap** (`INTENT DEFER-CAP`) is **never claimed** this
  cycle — it stays free for a peer to pick up. A machine therefore claims only what it can spawn
  *now*, so no single machine hogs the backlog.
- A **lost** claim releases the Tier-1 lock immediately and consumes **no** spawn slot or budget —
  the slot goes straight back.

An **idle** machine picks up any **unclaimed** ticket, but it **cannot steal an in-flight one**: a
live claim within TTL blocks it (`SKIP-CLAIMED`). The only way work moves to another machine is a
TTL takeover after the holder crashes or is parked (below).

*Operator-visible symptom:* a busy machine at its cap logs `DEFER-CAP` with **no** following `CLAIM`
for that ticket; an idle peer logs `CLAIM` → `CLAIM-WON adjudicated` and spawns it. Backlog spreads
across machines instead of piling on one.

### Recovery — TTL takeover of a crashed / parked holder

A claim is live only while its comment timestamp is younger than `ORCH_CLAIM_TTL` (default 600 s). A
holder that crashes or is parked stops heartbeating; once its last claim ages past the TTL, the next
peer to adjudicate the ticket finds **no live holder**, stakes its own claim, and wins the takeover.
Because each implementer seat pushes its `<ticket>-auto` branch, the taking-over machine
re-provisions its own worktree from that pushed branch tip and continues — no committed work is
lost (fresh-subagent-per-task, ADR-A-0002; the durable state is the pushed branch and the tracker,
never a machine-local worktree).

*Operator-visible symptom:* a roughly one-TTL (~10-minute default) quiet gap on the ticket, then a
**different** instance id logs `CLAIM` → `CLAIM-WON` and work resumes on the new machine. Tune
`ORCH_CLAIM_TTL` to trade takeover latency against tolerance for slow (but alive) holders — too low
and a legitimately long-running seat is reclaimed mid-spawn; too high and a genuine crash sits idle
longer before a peer recovers it.

### Fleet budget accounting — per-runner, NOT shared

The spawn budget is **per orchestrator process**, not a shared fleet pool. `ORCH_MAX_SPAWNS_PER_RUN`
(default 50) and `ORCH_MAX_SPAWNS_PER_DAY` (default 400) each apply **independently on every
machine**. Therefore:

> **Total fleet spend = N × `SPAWN_BUDGET`**, where **N** is the number of orchestrator machines.
> The budget is **per-runner and is NOT shared across machines.**

A two-machine fleet at defaults can spawn up to **2 × 50 = 100** per run (and up to 2 × 200 = 400
per day). The cost gate (ADR-A-0009) fires per machine, so each runner pauses and NOTIFYs on its own
exhaustion. Budget the fleet as the **sum** of the per-runner caps — do not assume the fleet shares
one budget.

### Verifying claim mutual exclusion (ABS-187)

Two artifacts verify the exactly-one-winner property before and during fleet deployment.

**CI test suite — `tests/test-claim-mutex.sh`** (auto-discovered by the `tests/test-*.sh` CI matrix):

```bash
bash tests/test-claim-mutex.sh   # 22 checks; run locally or in CI
```

| Part | What it proves |
| --- | --- |
| Unit (mock), two runners | one contested ticket → exactly one `CLAIM-WON` + one `SKIP-CLAIMED`; only the winner stakes a claim comment |
| Idempotent re-dispatch | the holder re-dispatching re-wins (`reclaim=own idempotent`) with no second stake |
| TTL reclaim | a claim aged past `ORCH_CLAIM_TTL` is reclaimed by a fresh runner |
| Concurrency harness (N=4) | four parallel `acquire_remote_claim` calls → one winner, three `SKIP-CLAIMED` |
| E2E dry-run | real orchestrator `--dry-run` + `ORCH_CLAIM_MODE=on` logs `CLAIM`/`CLAIM-WON` and `SKIP-CLAIMED` intents; a lost claim spawns nothing |

Drives the real `scripts/mock-tracker.sh` from separate `bash -c` processes — no stubs inside the orchestrator. Zero-dependency bash (ADR-A-0009); shellcheck-clean.

**Two-machine live smoke — `scripts/smoke-claim-two-machine.sh`** (operator-run; requires live Jira and two separate checkouts):

```bash
# On MACHINE 1 (checkout A):
export TRACKER_CMD="$PWD/scripts/jira-tracker.sh"
export ORCH_INSTANCE_ID="machine-1"   # stable, human-readable id
scripts/smoke-claim-two-machine.sh probe ABS-999   # prints WON or SKIP-CLAIMED

# On MACHINE 2 (checkout B) — fire at the same time, within one settle window:
export TRACKER_CMD="$PWD/scripts/jira-tracker.sh"
export ORCH_INSTANCE_ID="machine-2"
scripts/smoke-claim-two-machine.sh probe ABS-999

# On either machine — verify the shared state:
scripts/smoke-claim-two-machine.sh tally ABS-999   # expect: exactly 1 live holder

# On either machine — emit raw timing signals for the three measurements:
scripts/smoke-claim-two-machine.sh measure ABS-999
```

`probe` adjudicates this machine's claim without spawning. `tally` prints the live holder and per-instance claim counts. `measure` times own-claim read-back visibility and emits the signals for the operator fill-in tables in `docs/agent-outputs/qa-validations/ABS-187-claim-mutex-evidence.md`.

Pick any active, non-terminal Jira ticket labelled `orchestrator-ready` as the contested target. Expect: `probe` prints `RESULT: WON` on one machine and `RESULT: SKIP-CLAIMED` on the other; `tally` prints `distinct live holders: 1`.

**Tuned defaults (from ABS-187 measurements)**

| Parameter | Default | Tuned recommendation |
| --- | --- | --- |
| `ORCH_CLAIM_SETTLE_MS` | `1500` ms | Keep. Raise only if live Jira p99 comment-visibility exceeds ~1200 ms. |
| `ORCH_CLAIM_JITTER_MS` | `1000` ms | Keep. Worst-case settle window: 2500 ms. |
| `ORCH_CLAIM_TTL` | `600` s | Keep. Gives 3× headroom over the 200 s heartbeat cadence. Raise — or fire `refresh_claim` on handoff — if live handoff→pickup idle gaps exceed ~400 s. |
| `ORCH_CLAIM_MAX_OWNED` | *(unset)* | Leave unset by default (YAGNI). Add the opt-in cap only if the live smoke shows one machine monopolising the backlog. |

Full evidence and decision rules with operator fill-in tables: `docs/agent-outputs/qa-validations/ABS-187-claim-mutex-evidence.md`.

---

## Per-Epic Merge Token (ABS-256, ADR-A-0025)

The Merging seat (Path-B / epic child) serializes per epic. At most one story of a given epic may hold the `rte` `Merging` seat at a time; siblings wait in the `Merging` status and are dispatched on a later sweep once the token is free.

### Why the token alone is not enough — the cross-bounce hold rule

The five-bounce livelock observed in ABS-245 (consumer feedback item 15) had two compounding causes:
no per-epic serialization, and the runner pricing a mechanical rebase conflict identically to a code
defect (full re-gate walk). Serializing merges alone does not fix this — while the bounced story
re-gates, a sibling merges and moves the epic tip, so the story returns to a changed tip, conflicts
again, and bounces again. **The token is held across the bounce** (`Ready for Development` and the
entire re-gate walk). The epic tip cannot move while the token holder fixes its rebase; when it
returns to `Merging` it rebases against the same tip it already resolved — a clean rebase.
ADR-A-0014's "sequentially per epic, in acceptance order" finally has a mechanism (ADR-A-0025 §3).

The token releases when the holder **exits the merge path**: reaching `Docs` (merged), `Ready for Merge`, or `Needs PO Decision`. It is **not** released on a bounce to `Ready for Development`.

### Token implementation

- **Lock store:** `$LOCKS_DIR/merge/<epic-id>/holder` — the same atomic `mkdir` idiom as the per-ticket single-flight lock, keyed by epic id. No new status and no new queue store; `Merging` is the wait state.
- **Epic resolution:** `tracker parent <ticket>` (same call the runner makes elsewhere at ~L3105 of `scripts/orchestrator.sh`).
- **Staleness:** the holder is considered stale when it is gone or has left the merge path (liveness check, not TTL reclaim — a valid hold spans a full re-gate walk that outlasts any sane TTL).
- **Kill-switch:** `ORCH_MERGE_QUEUE=1` (default on); `=0` restores pre-ABS-256 unserialized behavior in one env edit, consistent with the boilerplate kill-switch convention (`ORCH_VERIFY_COMMITS`, `ORCH_DESIGN_FIRST_ROUTING`).

### Observability

`merge_token_gate()` logs a structured `intent` line on every `Merging` dispatch, including `bounces=N` (a count of backward `Merging → Ready for Development` exits driven by the `rte` seat, reusing the existing `rework_count` derivation filtered to `actor=rte`):

| Intent code | When | Note field |
| --- | --- | --- |
| `MERGE-TOKEN-ACQUIRE` | Token taken — `rte` spawned | `epic=<id> bounces=N` |
| `MERGE-TOKEN-HOLD` | Token re-entered after a bounce — `rte` spawned | `epic=<id> bounces=N` |
| `MERGE-QUEUE-WAIT` | Token held by a sibling — **no spawn** | `epic=<id> holder=<sibling>` |
| `MERGE-TOKEN-RELEASE` | Token released (holder exited merge path) | `epic=<id>` |

With the token working correctly `bounces=N` never exceeds `1` for a given story — the second bounce is what the cross-bounce hold rule makes structurally impossible (ADR-A-0025 §3).

### Head-of-line blocking

A token holder that fails repeatedly stalls its epic's remaining merges. This is bounded by the existing ABS-74 rework counter: once a story hits the rework limit it is routed to `Needs PO Decision` — which also releases the token, unblocking siblings. ADR-A-0014 accepted this trade-off explicitly; ABS-256 makes it real.

### Test suite

```bash
bash tests/test-merge-token.sh   # 36 checks
```

| Section | What it proves |
| --- | --- |
| A — single holder | one story acquires the token; sibling emits `MERGE-QUEUE-WAIT` |
| B — bounce hold | S1 bounced to `Ready for Development` → token not released → S2 still waits → S1 re-enters (`MERGE-TOKEN-HOLD`) → `bounces=1`, `bounces=2` absent → S1 reaches `Docs`, releases → S2 acquires |
| C + F — telemetry | `bounces=N` on every `Merging` dispatch; `merge_bounce_count` unit derivation |

Drives the real runner (`--dry-run --once`) against the mock tracker. Zero new test fixtures.

### Scope and what is not bundled

The adjacent proposal
`work/improvement-proposals/2026-07-11-reduce-shared-file-conflict-magnets-at-epic-integration.md`
addresses conflicts between the **epic branch and `main`** at `Epic Integration` (monolithic test
file, SOP version header). This ADR addresses conflicts between a **story branch and the epic tip**
at `Merging`. They share a symptom but different mechanisms — the merge token cannot help the former,
and splitting conflict magnets cannot help the latter. The proposal remains valid on its own merits
and is tracked separately (ADR-A-0025 §6).

---

## Handoff Commit Verification (ABS-255, ADR-A-0024)

Before the runner accepts a handoff it verifies every hash the seat claims to have committed. This
closes the failure class where seats reported edits as committed that never reached the repository
(consumer-feedback item 14, Epic ABS-245): `git log -S` proved the claimed commits existed in no
ref, and the downstream seat echoed the claim. Evidence-Disziplin (`_common-rules` §1, ABS-137)
was already a rule; ABS-255 makes it a mechanical gate executed in `handoff_followthrough`, before
`apply_handoff_transition` — so a false claim is caught before the handoff is accepted.

### The `commits:` field (seat contract)

Seats that commit MUST name their hashes on a `commits:` line in the handoff record:

```markdown
## Handoff

- role: <role>
- ticket: <ticket-id>
- commits: <sha> [<sha> ...]   # REQUIRED when this spawn created commits; OMIT when it created none
- summary: ...
- status: ...
- next: ...
```

A seat that omits the field after committing receives a non-blocking `HANDOFF-CLAIM-NOHASH`
advisory (prose regex; not blocking in v1 — false-positive class: "no code committed; review only"
from review/PO seats; promotion criterion in ADR-A-0024 (f)). A seat that creates no commits
simply omits the field; the gate does nothing.

### What the gate checks

For every hash on the `commits:` line, against `$ORCH_STATE_ROOT`:

1. **Existence** — `git cat-file -e <sha>^{commit}` — the object exists and is a commit.
   Failure means the hash is fiction.
2. **Reachability** — `git for-each-ref --contains <sha> --count=1 refs/heads/ refs/remotes/` is
   non-empty — at least one ref contains the commit. Failure means the commit is a dangling object
   (committed on a detached HEAD, or on a branch since reset/discarded). This is the exact ground
   truth the Befund established: "kein Ref enthielt sie je".

The gate is **fail-open**: absent `commits:` field, missing git, or unreachable repo → no verdict.
It blocks only when a check demonstrably returns no.

### Failure semantics

On a mis-report the runner:

1. Refuses the handoff — the declared transition is not applied.
2. Undoes any implementer self-transition: `In Progress → Ready for Development` (now a legal
   edge — see "Status-machine change" below).
3. Posts a `HANDOFF-MISREPORT status=<status> (orchestrator)` gate-results comment naming each
   failing hash and which check it failed.
4. Rests the ticket so the reconcile sweep re-spawns a fresh implementer to actually commit.

Repeated mis-reports feed the existing rework/no-move counters — no new counter, no new
loop-breaker. The backward transition is counted natively by `rework_count()` and bounded by
`ORCH_REWORK_LIMIT`; the rested ticket feeds the ADR-A-0018 escalation budget via `record_misreport`
(same shape as `record_nomove`).

### Status-machine change: `In Progress → Ready for Development`

ABS-255 adds this edge to `profiles/neutral/adapters/statuses.yaml`. It was the only active
implementation/review status missing the ADR-A-0002 impl-fix bounce target; every other stage
(`In Review`, `Security Review`, `Test Prep`) already carries it. The live Jira workflow already
permitted it (operators used it twice on ABS-255's crash reroutes). Without the edge,
`record_misreport()`'s undo of an implementer self-transition would be rejected by the adapter,
leaving the ticket at `In Progress` — a resting state with NOOP re-derive and NOTIFY-only
STUCK-detect, which orphans the ticket.

### Kill-switch

`ORCH_VERIFY_COMMITS=1` (default on, ABS-111 convention); `=0` restores pre-ABS-255 unverified
handoffs.

### Test suite

```bash
bash tests/test-orchestrator.sh   # includes 22 new ABS-255 assertions
```

ABS-255 scenarios cover: fabricated hash refused, orphaned commit refused, valid commit accepted,
no-claim handoff fail-open, kill-switch off, prose advisory, mis-report marker + failing-hash
naming, both check-type messages, respawn-limit → Needs PO Decision, and the
`In Progress → Ready for Development` undo.

---

## Remote Push Verification (PILOT-75, ADR-A-0024 + ADR-A-0030)

ABS-255's commit-verification gate (`ORCH_VERIFY_COMMITS`) checks that a claimed hash is
reachable from **any local ref** (`refs/heads/` or `refs/remotes/`). A commit that exists only
in a seat's worktree satisfies that check — it has a local `refs/heads/<story>-auto` pointing at
it — yet it is invisible outside the worktree and disappears when the worktree is cleaned up.
PILOT-75 closes this gap: for a **forward-completion handoff** (the story chain from `In Review`
through `Done`), every claimed commit must be reachable under `refs/remotes/<active-remote>/` —
the ref namespace that `git push` updates on a successful push.

### Why this gate exists — four incidents across three runs

| Run | Ticket | What happened |
|-----|--------|---------------|
| Pilot #4 | PILOT-23/24 | Branches existed only in local seat worktrees; MRs !182/!183 were empty. Operator recovered commits from `tmp/PILOT-23-work` and `tmp/PILOT-24-work` by hand. |
| Pilot #6 | PILOT-44 | Docs seat updated the SOP correctly but never committed. Changes sat in the main checkout; a subsequent `git merge --ff-only` would have silently discarded them. |
| Pilot #7 | PILOT-64 | Implementation commit `a5a1e627` was done and the seat transitioned to `In Review` — the branch existed only in the seat worktree, no remote ref. Operator recovered it. |
| Pilot #7 (systematic) | PILOT-59/65/66/67/69 + 8 others | ABS-549 sensor reported 13 × `branch-recoverable`: story branches only local. Not an edge case — the normal state absent the gate. |

In each case the transition was technically valid (local commit existed, local ref contained it)
but the status board claimed work was complete while the remote had nothing to show.

### Scope

`push_verify_failures()` runs only for **forward-completion transitions**: story chain
`In Review` (chain index 4) through `Done` (12). Out of scope and fail-open:

- Backward moves (any direction from a completion station back toward `Ready for Development`)
- `Design` / `Ready for Development` / `In Progress` (chain indices 1–3): a seat that adds a
  local spike commit before pushing is not blocked from transitioning to `In Progress`.
- Off-chain statuses (epic stations, `Needs PO Decision`, `Blocked`, `Docs`, human-gate statuses)
- Handoffs with no `commits:` field (fail-open, same as ABS-255)

**Double-reporting discipline**: a hash that does not exist locally at all is left to
`commit_verify_failures` (the ABS-255 gate). `push_verify_failures` only reports hashes that
exist locally but are absent from the active remote — the two gates never fire on the same hash.

### What the gate checks

For every sha on the `commits:` line, given `to` is a completion-claiming forward station:

1. **Local existence** — `git cat-file -e <sha>^{commit}` succeeds. If not: skip (left to
   `commit_verify_failures`; no double-report).
2. **Remote reachability** — `git for-each-ref --contains <sha> --count=1 refs/remotes/<active-remote>/`
   is non-empty. Failure means the commit was never pushed to the active remote.

The **active remote** is resolved by `active_remote_name()`, which reads the repo's remote pin —
never a hardcoded `origin` (ADR-A-0030). On this repo the active remote is `gitlab`; a
`HANDOFF-MISREPORT` refusal comment names the actual remote so the re-spawned seat knows exactly
where to push.

The check is **network-free**: `git for-each-ref` reads the local `refs/remotes/` namespace that
`git push` updates on success. No live remote probe is needed, consistent with
`resolve_active_main_ref` discipline elsewhere in the runner.

### Failure semantics

On a push mis-report the runner follows the same path as ABS-255:

1. Refuses the handoff — the declared transition is not applied.
2. Undoes any implementer self-transition back to `Ready for Development`.
3. Posts a `HANDOFF-MISREPORT status=<status> (orchestrator)` gate-results comment naming each
   failing sha and the active-remote name it was missing from.
4. Rests the ticket for the reconcile sweep to re-spawn a fresh implementer.

### AC3 — main-checkout seat sensor

Seats that work in the main checkout (docs/PO/RTE roles) do not use story worktrees. For them
the failure mode is uncommitted or unpushed changes sitting in the main checkout when they
forward-transition. The `detect_worktree_hygiene()` sensor in `scripts/ops-sweep-sensors.sh`
reports sub-case **(c)**: tracked uncommitted changes in the main checkout
(`git status --porcelain --untracked-files=no` non-empty). The sensor fires with finding
`unclean-main-checkout=N-file(s)` and advice `commit-and-push-or-discard-main-checkout-edits`.
The finding appears in the ops-sweep run log before the next reconcile; it does not block a
transition but surfaces the fault state for the operator.

### Seat contract (applies to all seats)

- **Commit AND push** to the active remote before forwarding to `In Review` or any later station.
- A never-pushed commit is refused on the mis-report path — the same hard-error class as a
  fabricated hash, not an advisory.
- Main-checkout seats (docs/PO/RTE): work in the main checkout must be committed **and pushed**
  before transitioning. Uncommitted edits are a fault state (`_common-rules.md §1`, updated by
  PILOT-75).

### Kill-switch

`ORCH_VERIFY_PUSH=1` (default on, ABS-111 convention); `=0` restores pre-PILOT-75
local-ref-only reachability for the forward-completion check. `ORCH_VERIFY_COMMITS` is
unaffected.

### Test suite

```bash
bash tests/orchestrator.d/PILOT-75-remote-push-verify.sh   # 7 assertions
```

Scenarios: local-only commit refused on forward transition (AC1/AC4); same commit pushed →
accepted (AC4 control); `In Progress` target exempt (out of scope); `ORCH_VERIFY_PUSH=0`
kill-switch disables gate.

---

## Handoff Marker Duty Verification (ABS-297)

ABS-297 extends the ABS-255 handoff-refusal precedent (ADR-A-0024) from commit hashes to
**marker duties**: when a seat's handoff *claims* an effect that a machine-readable marker must
carry, the runner verifies the marker exists before accepting the handoff. Without this, a seat
could declare "JOIN released" or "pile empty" in prose that the runner cannot confirm — exactly
the incidents on 2026-07-13 (ABS-248: po-agent claimed JOIN-EXEMPT with no marker on the child;
ABS-249/252/260: bsa claimed pile empty with `kind: follow-up` replies still absent) that each
required an operator to post the markers by hand.

### Two duties in scope

**Duty 1 — JOIN exemption (po-agent)**

A handoff that contains `JOIN-EXEMPT (triage)` for a child ticket triggers a check that the
exact marker text appears in a `kind: decision` comment **on that child**. The detector extracts
the child ticket ID from the same prose line that carries the claim and calls `child_join_exempt()`
(the same function `join_check_epic()` uses) to verify the marker.

**Duty 2 — BSA follow-up decision (bsa)**

A handoff that claims the follow-up pile is empty (phrases like "all follow-ups answered",
"pile is empty", "no pending follow-ups") triggers a check via `epic_has_unprocessed_followups()`:
if any `kind: follow-up` comment on the ticket lacks a `kind: bsa-decision` reply, the handoff
is refused.

Both detectors are **table-driven off the existing marker printers** (`join_exempt_marker()`,
`epic_has_unprocessed_followups()` / bsa-decision counting) so they cannot drift from the
vocabulary they validate (ABS-279 architecture binding rule).

### Failure semantics

On a marker mis-report the runner:

1. Refuses the handoff — the declared transition is not applied.
2. Undoes any seat self-transition back to the spawn status (actor = seat role, so `rework_count`
   increments natively).
3. Posts a `MARKER-MISSING status=<status> (orchestrator)` gate-results comment naming the
   **exact required marker text** and the **ticket it must appear on** — so the re-spawned seat
   can fix it in one turn.
4. Rests the ticket for the reconcile sweep to re-spawn a fresh seat.

The `MARKER-MISSING` path feeds no separate escalation counter. The rework/no-move counters
(ABS-132 / ADR-A-0018) that already exist bound any loop; if stuck-detect (ABS-116) fires after
three ownerless sweeps, the operator is notified.

### Seat contracts

**po-agent**: before handing off any JOIN-exemption declaration, post the marker on the child
ticket:

```bash
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment <child-ticket-id> \
  --kind decision --actor po-agent \
  --body "Optional dependency — parked. JOIN-EXEMPT (triage): <reason>."
```

**bsa**: the `kind: bsa-decision` reply you post IS the completion signal. Post it before
handing off. A handoff that claims pile-empty without that reply is refused.

### Kill-switch

`ORCH_VERIFY_MARKERS=0` restores pre-ABS-297 unchecked prose claims. `=1` is the default
(ABS-111 convention).

### Fail-open guards

Both checks skip without error when the real condition cannot be resolved: JOIN-exempt check
skips when no child ticket ID is extractable from the claim line; follow-up check skips when
the epic ticket ID is absent from the handoff context. A valid marker present → handoff accepted,
transition applied — the happy path is unchanged.

### Test suite

```bash
bash tests/orchestrator.d/ABS-297-marker-duty.sh   # 11 assertions
```

Covers: JOIN-exempt claim refused without marker (AC1), bsa pile-empty claim refused with pending
follow-up (AC2), happy path accepted with markers present (AC3), refusal comment names exact
marker and target ticket (AC4).

---

## Human-Only Boundaries (Never Auto-Spawned)

Two statuses are permanently outside the spawn mapping — the runner treats them as **NOOP**, full
stop, regardless of mode:

- **`Ready for Merge`** — the merge button is a human gate (ADR-A-0004, ADR-A-0005). The Release
  Agent has already prepared the PR by the time a ticket reaches this status; the orchestrator
  does not spawn anything and does not send a NOTIFY either — the human already owns this gate
  from the moment the ticket enters it. Merging autonomously is explicitly out of scope of this
  spec (§9). *(Parentless / Path-A tickets, ABS-106: the ready-to-test NOTIFY for such a ticket has
  already fired **upstream** from the RTE `Merging` seat on PR-open — see "Path-A tail" — so this
  gate is still a silent NOOP; the seat is the notify origin, not this rest state.)*
- **`In Progress`** — technically not a *human* boundary but the same "never spawn here" shape: a
  ticket enters `In Progress` because the implementer subagent that was just spawned for
  `Ready for Development` set it there itself. Spawning again on this event would double-spawn a
  ticket already being worked.

One further status is **SPAWN-then-NOTIFY** — an agent acts (PO-Agent's acceptance check) *and* a
human is told, but the human is not asked to do the spawning:

- **`Ready for Human Acceptance`** — PO-Agent runs its epic-completion check, then a NOTIFY tells a
  human when the epic is fully complete and awaiting their acceptance decision.

`Blocked` is a plain **SPAWN** in v3 (ABS-76): the tdm triages first — classify, resolve/reroute,
resume to the recorded pre-blocked status — and only genuinely human-only calls (credentials, cost,
new features) get a NOTIFY escalation from the tdm itself; see "Blocked → TDM triage" below.

**Epic acceptance itself is always a human decision** — the PO-Agent's spawn on
`Ready for Human Acceptance` prepares the acceptance check and notifies; it never transitions the
ticket to `Ready for Merge` on its own authority.

---

## Epic Lifecycle (v3 — ABS-69)

v3 seats **every** agent role (16 of 17, all but `boilerplate-migration`) in one automated
workflow. A human writes an epic and gets notified once — when the epic is on staging, ready to
test. Everything between is orchestrator-driven: two pipelines, one seated agent per transient
status, mechanical fan-in and safety guards. Spec: [`specs/ABS-69-workflow-v3-full-agent-team-spec.md`](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md).
The **executable definition** is `tests/e2e-workflow-v3.sh` (ABS-80) — S1–S16 as bash dry-runs
against the real runner; treat it as the workflow's source of truth and the epic's exit gate.

The v3 rows live in the same `map_action` / `is_reconcilable_status` machinery documented above —
nothing here replaces the v1/v2 status handling; v3 is purely additive.

### Epic pipeline (one ticket per epic)

| Status | Action | Seat | Exit |
| --- | --- | --- | --- |
| `PO Triage` | SPAWN | po-agent | scope, WSJF, guardrails → `Grooming` (or `Backlog` to defer) |
| `Grooming` | SPAWN | bsa | story drafts, testable ACs, sets `design`/`security`/`data` flags → `Enrichment` |
| `Enrichment` | SPAWN | issue-enrichment | dedup + child-ticket creation → `Ticket Review` |
| `Ticket Review` | SPAWN | qas | **Definition-of-Ready gate** over all children (see below) → `Architecture Review` |
| `Architecture Review` | SPAWN | system-architect | patterns, `#PATH_DECISION`; **releases stories** → `Stories In Flight` |
| `Stories In Flight` | NOOP (rests) | — | JOIN rule advances it → `Epic Integration` |
| `Epic Integration` | SPAWN | rte | sync-rebase epic branch onto `main`; staging deploy + smoke; on fail `git bisect` the ticket-tagged commits → reopen offending story → `Ready for Epic Acceptance` |
| `Ready for Epic Acceptance` | NOTIFY | — (human) | **the ready-to-test signal**: human tests the epic branch and merges its PR to `main` → `Epic Done` |
| `Epic Done` | SPAWN | self-improvement | retro + skill mining + proposals (terminal after the spawn) |

### Story pipeline (per child story)

| Status | Action | Seat | Notes |
| --- | --- | --- | --- |
| `Design` | SPAWN | ui-ux-design | **conditional** (`design`): design + measurable design ACs |
| `Ready for Development` | SPAWN | implementer | role from ticket `role:` (default `be-developer`) |
| `In Progress` | NOOP | — | implementer set it on start |
| `In Review` | SPAWN | system-architect | read-only (ABS-57 toolset narrowing) |
| `Security Review` | SPAWN | security-engineer | **conditional** (`security`): RLS/authz/injection, independence gate |
| `Test Prep` | SPAWN | data-provisioning-eng | **conditional** (`data`): fixtures, seeded data, RLS contexts |
| `In Test` | SPAWN | qas | functional ACs + evidence |
| `Design Test` | SPAWN | qas-design | **conditional** (`design`): implemented UI vs design ACs |
| `Story Acceptance` | SPAWN | po-agent | evidence-based accept → `Merging` / reject → `Ready for Development` |
| `Merging` | SPAWN | rte | **Path-B (epic child):** sequential per epic onto the epic integration branch: rebase + CI + auto-merge on green (never merges to `main`). **Path-A (parentless):** own branch off `main` + PR-to-`main`, fires the ready-to-test NOTIFY from this seat on PR-open, human merges, no auto-merge — see "Path-A tail" below (ABS-106) |
| `Docs` | SPAWN | tech-writer | story documentation → `Done` |

The historical sim status names map onto real statuses: sim `Implement` = `Ready for Development`,
sim `Code Review` = `In Review`. **The `Docs` station (chain_index 11, before the human merge gate)
is the sole docs mechanism** — documentation happens *before* the human merges, never after
(ABS-137). The `Done` row is **NOOP**: a story reaching `Done` is never spawned to `tech-writer`,
so there is no post-merge tech-writer spawn. The runner also detects the `Docs -> Done` transition
and emits `SKIP-DOCS-DONE`, keeping that transition an explicit no-op — a plain story is pinned at
exactly 6 spawns (the sixth being the `Docs` seat).

**Handoff truthfulness (ABS-137).** Every seat must re-validate the actual repository state
(`git status --short`, `git log --oneline -1`, and confirm pushed) *before* writing its handoff, and
the handoff MUST describe that verified end state — never a stale "changes staged but not
committed"/"commit pending" claim when the commit already exists (Befund 9, run ABS-126). The
identical rule is embedded in each implementing seat's agent-def under the same `Handoff
truthfulness (ABS-137)` marker.

### Path-A tail — parentless ticket: own branch + RTE PR-to-`main`, human merges (v3.1, ABS-106)  `#EXPORT_CRITICAL`

The `Merging` row above (RTE onto a **per-epic integration branch**, ADR-A-0014) is the **Path-B /
epic-child** tail. A **parentless ticket** (Path-A, no `parent` link — intake-classified by ABS-104,
solo pipeline by ABS-105) has **no epic**, so it takes a different tail: RTE prepares a PR **to
`main`** and the flow rests for a **human** to test and merge it — exactly the classic single-ticket
merge boundary (ADR-A-0004 / ADR-A-0005), unchanged.

The RTE `Merging` seat **branches on the ticket's `parent` field** (read via the adapter) as step 0:

- **`parent` empty → Path-A.** RTE:
  1. creates a **per-ticket branch off `origin/main`** — the normal `AITBC-XXX-{description}`
     convention, **never an `epic/`-prefixed integration branch** (no epic branch is created for a
     parentless ticket — assertable: no such ref exists);
  2. **rebases the per-ticket branch onto current `origin/main` (or verifies it is already current)
     immediately before opening/updating the PR** (`git fetch origin && git rebase origin/main`,
     then `git push --force-with-lease`). A parentless branch forks off `origin/main` and then
     **rests indefinitely** at the `Ready for Merge` human-merge gate (step 5), so `main` routinely
     advances while it rests; a **non-rebased** PR-to-`main` then diffs as **deleting** everything
     that landed on `main` in the interim — the **stale-branch security-doc revert risk**. Concrete
     instance: a branch tip that forked at v2.18.0 diffs against a v2.19.0 `main` as removing the
     entire ABS-111 hardening block, including the *Runner-Provisioned Worktrees (C9)* and *Live-Run
     Allowlist Baseline* **security-isolation** sections. Rebasing onto the current tip closes this
     *by construction* in the seat, instead of relying on the human PR reviewer as a single backstop.
     This is the standard rebase-before-PR workflow (CONTRIBUTING.md, "rebase-first workflow"), now
     mandated in the seat SOP;
  3. opens a **PR targeting `main`** (via the tracker/`bb` seam), **idempotently** — if a PR from the
     branch is already open it is *updated* (with the freshly-rebased branch), never duplicated
     (re-running the seat rebases and updates the existing PR, opening no second PR);
  4. **fires the ready-to-test/merge NOTIFY from this RTE `Merging` seat itself**, as part of the
     SPAWN on PR-open — **not** from the downstream `Ready for Merge` rest state, which by design
     emits no NOTIFY (see "Human-Only Boundaries" and "Notify points" below). The NOTIFY carries the
     PR URL so the human can test and merge;
  5. **transitions the ticket to the `Ready for Merge` human-merge gate and hands off to HITL**, where
     it rests — **auto-merge is NOT invoked and no agent merges the PR.** No second NOTIFY fires at the
     gate; the seat already sent the one ready-to-test signal in step 4.
- **`parent` names an epic → Path-B.** The unchanged epic-branch `Merging` seat runs (the `Merging`
  row above).

**The ADR-A-0014 per-epic auto-merge code path is never reached for a parentless ticket** — by
construction, because there is no epic branch to auto-merge onto, and by that ADR's own text:
*"Epic-less stories are explicitly out of scope of this ADR … a per-story PR merged to `main` by a
human (ADR-A-0005 / ADR-A-0004, unaffected by this ADR)."* No auto-merge configuration changes
this: on Path-A, RTE **only** creates the branch and opens the PR to `main`; it **never** merges it.
The merge-to-`main` authorization boundary is human-only, unchanged (ADR-A-0004 / ADR-A-0005). The
`Ready for Merge` human-only gate ("Human-Only Boundaries" above) is where the parentless ticket rests
— the ready-to-test NOTIFY has already fired from the RTE `Merging` seat on PR-open (step 4 above)
*before* the ticket enters that gate, so the gate itself stays a silent NOOP as specified.

This is dry-run assertable (the E2E S-A1 scenario, ABS-110): a parentless ticket reaches its
human-merge rest state with **no `epic/` ref created**, **no auto-merge transition**, **no epic
integration status** in its transition log, **the PR-open branch not stale** — its merge-base with
`origin/main` equals the current `origin/main` tip (step 2 rebase) — and **exactly one ready-to-test
NOTIFY emitted from the RTE `Merging` seat** (on PR-open, not from the `Ready for Merge` gate).

### Epic entry — how a ticket enters the pipeline

A human writes the epic in `Backlog`, then either routes it into `PO Triage` directly, or the
`Backlog`-spawned po-agent routes it there (`Backlog → PO Triage` is an allowed transition in
`statuses.yaml`). The stall subsystem is the backstop: an undecomposed epic resting in `Backlog`
past `ORCH_STALL_EPIC_SECONDS` is mechanically raised to `Needs PO Decision`, which spawns the
po-agent to triage or decompose it. Stories enter the story pipeline when the **Architecture
Review** seat releases them (`Backlog → Design`), not by hand.

### Intake classification — three-way route (v3.1, ABS-102)

Before a top-level ticket runs the pipeline, the runner **classifies its intake shape** — bash-only,
no LLM (ADR-A-0009) — by reading the ticket's **parent-epic link** and **child count** via the
adapter (ABS-104). The classifier writes a `kind: gate-results` audit comment naming the chosen path,
then routes one of three ways:

- **Empty epic → the existing v3.0 flow (unchanged).** An epic with no attached children takes the
  standard decomposition path: `PO Triage → Grooming → Enrichment` generate the stories, then the
  `Ticket Review` gate. This is the default v3.0 behavior; the v3.1 change is purely additive and does
  not touch it (regression-guarded by scenario S-B3).

- **Parentless ticket → Path-A (new intake head).** A standalone story/bug with **no parent epic**
  runs a **solo story pipeline**: the per-story stages directly (SKIP-FORWARD still elides unflagged
  conditional stages), its **own branch**, and a tail that ends at an **RTE PR-to-main** — **no
  auto-merge**. Auto-merge stays epic-only (ADR-A-0014); merges to `main` remain human-only
  (#EXPORT_CRITICAL). Spec ABS-105 (pipeline) / ABS-106 (PR-to-main tail).

- **Epic with pre-existing children → Path-B (new intake head).** A **pre-populated epic** authored
  with its child tickets already attached **skips Grooming decomposition** and instead runs the
  **Ticket-Review Definition-of-Ready gate as the *entry* gate** over the existing children (plus
  epic-prerequisite checks). **No BSA decomposition spawn occurs** — assertable in the epic's
  transition log (no `Grooming` SPAWN entry precedes the `Ticket Review` gate). A conformant epic
  (scenario S-B1) goes straight to `Architecture Review` with **no story generation**, and from
  Architecture Review the **unchanged v3.0 tail** runs (JOIN → Epic Integration → ready-to-test
  NOTIFY → human merge of the epic PR to `main`); a non-conformant one enters the **auto-fix rework
  loop** (mechanical fixes applied; only substance gaps escalate to `Needs PO Decision`; the §3.2
  counter caps it at 3 bounces). Spec ABS-107 (entry gate) / ABS-108 (rework loop). The DoR checklist
  itself is unchanged and reused verbatim — see
  [`docs/sop/DEFINITION_OF_READY.md`](DEFINITION_OF_READY.md) "Path-B entry-gate reuse" and its
  "epic-prerequisite check" subsection. The epic reaches `Ticket Review` mechanically via
  STATION-GUARD redirect — without it, the runner's own JOIN-rest park carries a pre-filled
  epic `Backlog → Stories In Flight`, bypassing the gate silently (ABS-271; see STATION-GUARD
  section below).

Both new heads (parentless-ticket, epic-with-children) **feed the existing pipeline** — they add entry
routes, not new stages. Diagram: [`specs/assets/workflow-v2.drawio`](../../specs/assets/workflow-v2.drawio)
(the two `Intake head` boxes feeding `Implement` and `Ticket Review`).

#### Path-A — parentless-ticket solo pipeline (ABS-105, spec §3 / §5)

Once the classifier tags a `Backlog` ticket `INTAKE-CLASS=parentless-ticket`, the runner still maps
`Backlog` entry to **SPAWN po-agent** — that spawn is the **Path-A triage + Definition-of-Ready head**:
the *same* PO-Triage seat and charter run in **single-ticket mode** over the one ticket (resolved
`#PATH_DECISION` (a); **exactly one seat, no new role**). The QAS batch `Ticket Review` gate is
degenerate for a single ticket (no batch, no coverage map), so the head runs the **per-ticket half of
the DoR checklist inline** — testable AC present, scope fits one spawn, `design`/`security`/`data`
flags consistent with content — and yields exactly one of three outcomes:

- **ready** → transition `Backlog → Design`, releasing the ticket into the **story** pipeline head. It
  **never** transitions to an epic-pipeline status (`PO Triage`, `Grooming`, `Enrichment`,
  `Ticket Review`, `Architecture Review`, `Epic Integration`).
- **rework** → `Backlog` with the missing/inconsistent readiness item recorded; it re-enters the head
  once fixed.
- **needs-decision** → `Needs PO Decision` for a substance gap the head cannot resolve (untestable AC,
  oversized scope).

From `Design` the ticket walks the **existing v3.0 story pipeline verbatim** —
`Design → Implement (Ready for Development) → Code Review (In Review) → Security Review → Test Prep →
In Test → Design Test → Story Acceptance → …` — with the four conditional stages
(`Design`/`Security Review`/`Test Prep`/`Design Test`) **SKIP-FORWARDed by the runner** exactly as for
a story inside an epic (audit comment + re-transition, **no spawn**) when their flag is unset. A
`security`-flagged parentless ticket therefore still spawns `security-engineer` at `Security Review` —
flags are honoured unchanged. **No new pipeline code is forked** (ADR-A-0010): Path-A reuses the story
seat mapping and SKIP-FORWARD paths as-is. Because the ticket is parentless, the **JOIN rule (spec
§3.1) never evaluates** for it — the fan-in check is parent-gated, so no sibling count / fan-in ever
runs. The merge tail (`Merging` PR-to-main variant) is delivered by Story 4 (ABS-106).

### Ticket-Review DoR gate (spec §3.10)

`Ticket Review` maps to a **qas** spawn — a Definition-of-Ready batch review of **all** the epic's
child tickets before any story is released. QAS is the seat (not a new role) because the reviewer
must be independent of the authors (BSA/issue-enrichment) and the decisive lens is testability.
Full checklist, coverage-mapping rule, blind-spot catalog and verdict routing:
[`docs/sop/DEFINITION_OF_READY.md`](DEFINITION_OF_READY.md). Three verdicts:

- **ready** → `Architecture Review` (the architect then reviews only complete tickets — reviews once).
- **rework** → bounce to `Grooming` with a concrete defect list. Counted by the epic ticket's
  rework counter (below); no separate guard.
- **open question** → `Needs PO Decision`. Anything the reviewer cannot decide from ticket text
  (unwritten domain knowledge) is **never guessed** — the po-agent that triaged the epic decides.

### Path-B auto-fix rework loop (v3.1, ABS-108)

For a **pre-populated epic** (Path-B), a `rework` verdict does not re-decompose — the children already
exist. The runner bounces `Ticket Review → Grooming` (the same transition, no new status), where
BSA/issue-enrichment **auto-normalize the existing children at child granularity** against the
`gate-results` defect list, then the epic **re-enters `Ticket Review`**. The loop repeats until `ready`
(→ `Architecture Review`) or the counter caps out. Two invariants the runner enforces, both reusing
existing mechanics:

- **Bounded authority (ADR-A-0004).** Auto-fix is limited to an enumerated, closed normalization set —
  tighten a vague AC over the same behavior, set/repair a `design`/`security`/`data` flag or `role:`
  hint, add a missing pattern/spec ref, create a coverage-gap story for an unmapped epic goal, split an
  oversized story. Each item maps to a **canonical tracker operation** and touches nothing the adapter
  cannot express (ABS-66): flag repairs are an in-place `update flags`; a coverage-gap story is an
  additive `create --body-file`; and any body-touching fix (tightening an AC, repairing a `role:` hint,
  adding a ref, retiring a split original) uses **close-and-replace** — `create` a corrected successor
  child and close the original — since the canonical `update` op cannot rewrite a description (body /
  role are create-only). "In place" therefore means **child granularity**, not a same-issue mutation. A
  **substance/scope gap** (rewriting what a story delivers or adding an unwritten requirement) is **not**
  auto-fixed — the gate issues `open question` → `Needs PO Decision` so the po-agent decides. Full
  enumeration + mechanism + boundary:
  [`docs/sop/DEFINITION_OF_READY.md`](DEFINITION_OF_READY.md) "Path-B auto-fix rework loop".
- **3-bounce cap (spec §3.2, reused verbatim).** Each `Ticket Review → Grooming` bounce increments the
  **epic ticket's** existing rework counter (below); at `ORCH_REWORK_LIMIT` (default 3) the runner routes
  to `Needs PO Decision` instead of re-spawning — the escalation-to-human safety valve against an
  unbounded auto-fix loop. **No new counter/threshold mechanics** (ADR-A-0010 minimal-change).

### JOIN rule + guards (spec §3.1, §3.6)

An epic resting in `Stories In Flight` advances to `Epic Integration` when **all** its children —
original stories **plus AC-blocking follow-up additions** — are `Done`. Mechanical, bash-only
(ADR-A-0009). It fires from two places: the reconciliation sweep (per epic row) and a child's
`Done` event in `dispatch()`, so the last story completing advances the epic without waiting a full
reconcile cadence. Idempotent — once the epic left `Stories In Flight`, further calls are no-ops.

Two guards, both from scenario testing:

- **Empty-epic** — zero children at JOIN evaluation → `Needs PO Decision` (`INTENT JOIN-EMPTY`),
  never a vacuous integration + ready-to-test NOTIFY.
- **Quiescence** — JOIN never fires while the epic tree carries an **unprocessed follow-up**
  comment (a `kind: follow-up` without a `kind: bsa-decision` reply); it logs `INTENT JOIN-WAIT`
  and waits. Sweep order is **watcher → JOIN** in the same sweep, so an AC-blocking follow-up filed
  in the same cycle the last story finishes cannot lose the race.
- **Optional/parked-child exemption (ABS-210)** — a child deliberately parked out of scope (e.g. a
  TDM `external-dependency` triage that never resolves this run) used to hold the epic **silently**
  in `Stories In Flight` (ABS-181/ABS-189, JOIN stalled >20 min until an operator adjudicated). A
  triage seat (TDM/PO) can now declare a **mechanical exemption** by writing the exact marker
  `JOIN-EXEMPT (triage)` into the body of a `kind: decision` comment **on that child**. At JOIN
  evaluation the runner partitions the not-`Done` children: an exempted child is excluded, so an
  epic with all other children `Done` **JOINs** and the log **names** the exclusion
  (`INTENT JOIN-EXEMPT … exempt-children:<id>`). A not-`Done` child **without** the marker is a real
  blocker — JOIN keeps waiting but now **names** the pending child once
  (`INTENT JOIN-WAIT … pending-children:<id>`) instead of hanging silently. This is an
  ADR-A-0019-style *declared* marker (anchored to a decision-comment body, so a mere quote elsewhere
  cannot exempt); it changes only the JOIN evaluation, never Blocked/TDM-triage semantics (ABS-76).

### SKIP-FORWARD — conditional stages are the runner's job (spec §3.3)

The four conditional stages (`Design`, `Security Review`, `Test Prep`, `Design Test`) require a
matching ticket flag (`design`/`security`/`data`). On entry into one, the runner reads the flag via
the adapter; when the ticket is **unflagged** it posts an audit comment (`kind: skip`, actor
`orchestrator`) and **re-transitions to the next stage itself** — no spawn, no budget, no lock
(`INTENT SKIP-FORWARD`). Agents carry zero routing logic; the flag→next-stage map lives only in the
runner (`conditional_flag_for` / `skip_forward_target`). This is why a plain (unflagged) story costs
exactly 6 spawns while a design+security+data story runs all stages.

### STATION-GUARD — flag-conditional station enforcement (ABS-247)

SKIP-FORWARD (above) is the runner's path for conditional stages: when a ticket is unflagged, the
runner skips that stage itself and re-transitions. The STATION-GUARD enforces the other direction:
when an agent performs a forward jump that skips a mandatory station, the guard catches it, posts an
audit comment, and redirects the ticket to the missed station.

Before ABS-247, `first_skipped_mandatory` treated all four conditional stages (`Design`,
`Security Review`, `Test Prep`, `Design Test`) as unconditionally skippable for guard purposes,
regardless of the ticket's flags. A design-flagged ticket hopping `In Test -> Story Acceptance`
passed the guard unchallenged, silently folding the `Design Test` seat (consumer-feedback CSV item
12; ABS-216/ABS-136).

ABS-247 closes this gap. The guard reads the ticket's `design`/`security`/`data` flags through
`active_conditional_flags` (which calls the existing `ticket_has_flag` helper) and passes the
resulting flag set into `first_skipped_mandatory` and `forward_skip_illegitimate`. A conditional
station whose gating flag is set on the ticket counts as mandatory for that ticket. One predicate
drives both:

```
chain_station_mandatory <name> [active_flags]
  unconditional station                  -> always mandatory
  gating flag present in active_flags    -> mandatory for this ticket (ABS-247)
  gating flag absent from active_flags   -> skippable (ABS-84 SKIP-FORWARD)
```

When the guard intercepts a skip of a now-mandatory conditional station, it:

1. Posts a `kind: skip` audit comment naming the gating flag and citing ABS-247.
2. Transitions the ticket back to the missed station.
3. Returns exit 0 (`INTERVENED`); the redirect triggers a normal dispatch on the next sweep.

On an unflagged ticket, `active_conditional_flags` returns an empty string. The optional third
argument to `first_skipped_mandatory` / `forward_skip_illegitimate` is absent, so both functions
behave identically to the pre-ABS-247 two-arg call. SKIP-FORWARD legitimacy is unchanged.

The redirect mechanic and audit-comment format follow the ABS-216 pattern (`kind: skip`, actor
`orchestrator`, `INTENT STATION-GUARD` log prefix).

**Flag-to-station map** (single source of truth: `conditional_flag_for` in `orchestrator.sh`):

| Flag | Conditional station it gates |
|---|---|
| `design` | `Design`, `Design Test` |
| `security` | `Security Review` |
| `data` | `Test Prep` |

**Merge-boundary exemption (ABS-266).** Station order is a pre-merge concern. `Docs` carries
`entered_when: Story merged` in `profiles/neutral/adapters/statuses.yaml`, making it a
post-merge status by definition. `forward_skip_illegitimate()` now returns immediately (exempt)
when the landing status is `Docs` — the STATION-GUARD never pulls a story back from there.

Why this matters: ABS-234 was PO-accepted, QAS-green, and HITL-merged. Sixteen seconds after the
RTE released it to `Docs`, the guard dragged it back to `In Review` because the RTE's move was
recorded as `In Progress -> Docs`. Re-spawning an implementer to rebuild already-merged code is
the most destructive misbehaviour the guard can produce.

The exemption is narrow by design. `In Test -> Done` and `Merging -> Done` remain flagged
(ABS-136 Befund 6 regressions asserted). Merge evidence at `Done` is enforced independently by
`done_pr_gate` (ABS-211) — exempting `Docs` from station order does not weaken that gate.

**Post-merge `Needs PO Decision` exit (ABS-266).** A story escalated to `Needs PO Decision` from
a post-merge state previously had no forward route: every exit in the next-table is backward into
re-implementation. The po-agent for ABS-234 laundered the story through `Blocked` purely because
`Blocked`'s resume-to-origin next-table happened to include `Docs`. `Docs` is now a legal exit
from `Needs PO Decision` in `statuses.yaml` — a post-merge escalation routes forward directly,
without a `Blocked` hop. `Done` is not added; `Docs -> Done` remains gated by the tech-writer
seat and `done_pr_gate`.

**Pre-filled epic DoR gate enforcement (ABS-271).** Path-B's `Ticket Review` entry gate is
enforced by a STATION-GUARD extension, not a status edge. A pre-filled epic
(`INTAKE-CLASS=epic-with-children`) has no forward move from `Backlog` through `Ticket Review`:
the runner's ABS-214 JOIN-rest park (`epic_join_rest_complete`) transitions it
`Backlog → Stories In Flight` automatically. Before ABS-271, STATION-GUARD never saw the hop —
`Backlog` is `chain_index` 0 and index-0 sources are guard-exempt — so the epic's children were
released to `Ready for Development` with no DoR check. Verified against epic ABS-278:
fourteen children released on 2026-07-13T22:03:05Z with no gate run. Violates spec ABS-103
§6's shift-left invariant ("No story is ever released before this gate passes").

ABS-271 adds `prefilled_epic_entry_index`, which hands the guard `Enrichment`'s chain index as
the effective source for a pre-filled epic. Any forward hop landing beyond `Ticket Review` then
reads as a skipped mandatory station; the guard redirects to `Ticket Review` where the existing
qas DoR batch review runs. A `Stories In Flight → Ticket Review` edge in `statuses.yaml`
makes the redirect legal (runner-only — no seat transitions this directly).

**The discriminator is `epic_visited_grooming`, not child-count.** Both epic classes carry
children: a decomposed epic's children are created during `Grooming`, so the predicate "has
children AND has not passed the gate" matches both. Clamping on that alone redirects a decomposed
epic skipping mandatory `Enrichment` to `Ticket Review` instead of `Enrichment`, silently forgiving
a mandatory station (ABS-136/ABS-247 regression, verified against clean HEAD~1). The pre-filled
epic never visits `Grooming` — its children are authored before intake — which is exactly what
`epic_visited_grooming` tests. Without it, the fix regresses the guard it reuses.

The guard arms only while `epic_passed_dor_gate` returns false: an epic that already passed
`Ticket Review` is not dragged back, keeping ABS-214's JOIN-rest edge intact (idempotent). The
`route_intake` audit comment now names STATION-GUARD as the enforcing mechanism and no longer
claims it "routed to the Path-B entry gate" (AC2, spec ABS-103 §6.1 `#PATH_DECISION` (c)).

### Pre-filled-epic child hold — EPIC-REVIEW-WAIT (ABS-518)

Children of a **pre-filled** epic (the PO decomposed by hand: children set
`Ready for Development`, epic returned to `Backlog`; the epic never visited
`Grooming`) rest at their entry status until the epic has **visited
`Architecture Review`** — the station that releases stories on the decomposed
path. Without this hold the epic's Ticket Review + Architecture Review run
after the children are already in flight and degrade to rubber-stamps
(ABS-392 incident, 2026-07-18 proposal). Same resting semantics as
`DEPENDS-WAIT`: no marker, the reconcile sweep re-derives the spawn once the
epic clears the station; an unreadable parent epic means WAIT, not
"satisfied". Decomposed epics (Grooming visited) are untouched, and so are
v1-plain CONTAINER epics (grouping shell, children dispatched directly): the
hold applies only to a pipeline-armed epic — one carrying the Backlog opt-in
label (ABS-101) or having visited an epic intake station. Kill-switch:
`ORCH_EPIC_REVIEW_GATING=0`. Sensor: `epic_review_owed()` +
`tests/orchestrator.d/ABS-518-epic-review-wait.sh`.

### Rework counter (spec §3.2)

Every **backward** agent transition along the canonical chain increments one per-ticket counter,
regardless of which stage pair bounced — the cross-stage net the pairwise ABS-12 iteration guard
cannot see (that guard remains the inner, `In Review`/`In Test`-specific cap). At
`ORCH_REWORK_LIMIT` (default 3) the runner transitions to `Needs PO Decision` instead of spawning
(`INTENT REWORK-LIMIT`). Key properties, all landed:

- The counter is **derived from the ticket's transition-comment history**, never shell state, so it
  survives a runner restart for free.
- It applies to **story AND epic** tickets — the epic's DoR bounce (`Ticket Review → Grooming`)
  feeds the **same** counter (chain indices 21–29 for epic statuses, 1–12 for story statuses,
  disjoint ranges), so 3 DoR bounces → `Needs PO Decision` with no story ever released.
- The counting **window resets on any PO-decision exit** (`Needs PO Decision → *`, any target), so
  a PO routing the ticket onward re-arms a fresh window instead of instantly re-escalating.
- Transitions by actor **`human` are excluded** — human rejection is forward-fix, never counted.

### Crash escalation (spec §3.8)

When a live spawn fails twice (attempt + one retry, §6) the runner **no longer transitions the
ticket to `Blocked`** (in v3 `Blocked` would spawn the TDM — the wrong seat for a crashing spawn).
Instead it posts a `SPAWN-CRASH status=<st> role=<r> (orchestrator)` marker (`INTENT SPAWN-CRASH`)
and leaves the ticket **resting in place** for the sweep to re-derive. Consecutive markers for the
same `(ticket, status)` with no intervening successful handoff accumulate; at `ORCH_CRASH_LIMIT`
(default 3) the runner escalates to `Needs PO Decision` (`INTENT CRASH-LIMIT`). One successful
handoff resets the run. This closes the otherwise-infinite sweep-retry loop on a deterministically
crashing seat (bad prompt, oversized packet).

### Transition-on-handoff + respawn loop-guard (ABS-132)

Befund 4 of run ABS-126 — the single most expensive finding — was that no early seat executed its
own transition: the handoffs parsed, the status stayed put, and the runner resumed the same session
endlessly (à $0.2–0.8/respawn) until an operator drove six transitions by hand. Two default-on
mechanisms close it; both carry an env kill-switch and neither removes the seat's own right to
transition (transitions remain **also** allowed by seats — every runner move is idempotent):

- **Transition-on-handoff** (`ORCH_HANDOFF_TRANSITION=1`). After a cleanly parsed handoff the runner
  reads the handoff's **declared target status** and applies it itself via `$TRACKER_CMD transition`.
  The declarative field is `to:` (a machine target), with `next-status:` and a bare-status `next:`
  accepted as fallbacks (precedence `to > next-status > next`); the value is honoured only when it is
  a **canonical status**, so the ubiquitous prose `next:` line ("proceed per the status machine") is
  never mis-parsed. The transition's **actor is the seat role**, so a runner-applied bounce is counted
  by the rework counter exactly like a seat-applied one. When the seat already reached the target
  (**Ist=Soll**) the runner no-ops — never a double transition, no error; when the seat moved the
  ticket somewhere else the runner does not fight it. Records `INTENT RUNNER-TRANSITION` /
  `INTENT-RUNNER-TRANSITION` in run.log.
  - **Per-status default target (ABS-133, Befund 7).** When a seat hands off cleanly but declares
    **no** target of its own, the runner falls back to a per-status default (`handoff_default_target`).
    Today only **`Merging` → `Ready for Merge`** has one: once the `rte` seat has opened the PR and
    handed off to the human merge (auto-merge off), the story must rest at the human-owned
    `Ready for Merge` gate — **not** loop in the reconcilable `Merging` seat, which otherwise
    re-spawned a fresh `rte` (~$0.75) every reconcile cadence while the PR waited for the human
    (run ABS-126). Every other status has an empty default, so the loop-guard below stays the
    backstop there. A seat that declares its own target overrides the default.
  - **Escalation-resume fallback (ADR-A-0019, ABS-204).** After the per-status default, one further
    fallback applies exclusively to the `tdm`/`Blocked` escalation seat (`escalation_resume_target`).
    When the TDM handoff declares no target, the runner reads the recorded `BLOCKED-FROM` marker and
    transitions the ticket back to its pre-blocked origin. Origins that are themselves escalation
    statuses (`Backlog`, `Blocked`, `Needs PO Decision`) are excluded — the runner halts idempotently
    in `Blocked` instead, avoiding discretionary-status picks and escalation ping-pong. A **declared**
    `target: Backlog` from the po-agent (a legitimate PO deprioritisation, `verdict: deprioritize`)
    wins at the `handoff_target_status` step before this fallback is ever reached — the
    `last_po_park_epoch` / `stall_raise_suppressed` PO-park guard is unaffected. For all other seats
    this fallback is a no-op; the respawn loop-guard below remains the backstop.
- **Respawn loop-guard** (`ORCH_RESPAWN_LIMIT`, default 2). A handoff that parses but leaves the
  status **unchanged** (no declared target the runner could apply *and* the seat did not transition)
  posts a `HANDOFF-NOMOVE status=<st> (orchestrator)` marker. Consecutive no-move markers for the
  same status accumulate (the window re-arms on any transition); at `ORCH_RESPAWN_LIMIT` the runner
  escalates to `Needs PO Decision` with a reasoned `decision` comment (`INTENT RESPAWN-LIMIT`)
  instead of resuming forever. Suppressed when already at `Needs PO Decision` (no self-escalation).

**Default-on validation (ABS-175).** Both mechanisms ship **default-on** (`ORCH_HANDOFF_TRANSITION=1`
since ABS-132). ABS-175 validated the behaviour with the transition-on-handoff cases in
`tests/test-orchestrator.sh`, which drive a story seat through the full handoff→transition cycle: the
runner applies the declared target (`INTENT RUNNER-TRANSITION`, mirrored to `run.log`), is idempotent
when the seat already moved the ticket, honours the `ORCH_HANDOFF_TRANSITION=0` kill-switch, and
escalates to `Needs PO Decision` at `ORCH_RESPAWN_LIMIT` when handoffs parse but never move the status.
The seat-chain end-to-end suite (`tests/e2e-workflow-v3.sh`) additionally exercises runner-applied
transitions across every seat under the stub provider. The env flag stays as the documented opt-out
(`ORCH_HANDOFF_TRANSITION=0` = legacy seat-only transitions).

### Cross-visit loop-breaker + escalation budget (ABS-199 / ADR-A-0018)

The ABS-132 respawn guard and the ABS-74 crash escalation are **per-visit**: they count failures
*within one resting episode* at one status and re-arm on any transition. That is right for a ticket
wrestling with its own logic, but blind to a ticket that keeps hitting the **same external wall**
across different statuses — ABS-181 cycled `Enrichment → Needs PO Decision → Enrichment` **5×** on one
persistent denial, and ABS-168 burned **4 dispatches** (~$1–3.5 each) re-learning the same
deterministic `.claude` write-protection. ABS-199 adds a second, **orthogonal** axis: cross-visit
memory of *why* a ticket keeps failing. Two default-on mechanisms, each with an env kill-switch and a
per-ticket marker file under `$ORCH_STATE_DIR` (the **machine authority**; the tracker comment stays
the human-readable audit trail — never parsed back, ADR-A-0018 §b):

- **Blocker classification (§a).** Every failed dispatch is classified into exactly one class,
  derived **mechanically** from the ABS-151 crash diagnostic (`attempt_diag`) — never from prose —
  by `blocker_class`:
  - `environment-denial` — a tool-policy / permission denial (`.claude` write-protection, permission
    deny, allowlist reject). **Deterministic**: retrying cannot succeed.
  - `transient` — network / rate-limit / auth / non-zero exit / empty handoff / turn-ceiling.
    **Recoverable**: retry is the remedy (the existing ABS-118/ABS-74 path). This is the **safe
    default** for any unmatched diagnostic — an ambiguous failure is never parked.
  - `logic` — a parsed handoff that bounces on a test/gate failure (ticket-owned rework).
  - Precedence on overlap: `environment-denial > transient > logic`.
- **Cross-visit auto-park (§c/§e).** Each classified failure appends a `class · seat · status ·
  timestamp` line to `work/.orchestrator/blocker-<ticket>`. On the **2nd** occurrence
  (`ORCH_CROSSVISIT_THRESHOLD`) of the **same `(environment-denial, seat)`** across *any* visits, the
  runner transitions the ticket to **Blocked** (a human-owned rest state, **not** the reconcilable
  `Needs PO Decision` the per-visit path uses), **suppresses the re-spawn**, and emits **exactly one**
  operator NOTIFY (`INTENT CROSSVISIT-PARK`). The threshold is 2 (not 3) because the first retry
  already proved recurrence and a deterministic denial cannot improve — a third dispatch is pure
  wasted budget (the ABS-168 lesson). `transient`/`logic` and any *distinct* `(class, seat)` fall
  through to the per-visit machinery unchanged, so no recoverable ticket is parked prematurely.
- **Escalation budget (§d, folds ABS-198 Measure 4).** Independent of blocker class, a ticket that
  makes `ORCH_ESCALATION_BUDGET` (default 3) resting rounds **without advancing its `chain_index`**
  exhausts its budget: one NOTIFY + park to Blocked (`INTENT ESCALATION-BUDGET`), no further seats.
  The counter (and the blocker marker) reset **only on real forward progress** — a transition whose
  target has a strictly greater `chain_index` than the ticket's high-water mark. A **bounce**
  (backward transition, e.g. review → Ready for Development) does **not** reset it, so a ticket cannot
  bounce-and-retry forever — this is the direct fix for the ABS-181 cross-visit bounce loop.
- **NOTIFY-once dedup (§e).** Auto-park and budget-exhaustion each emit exactly one NOTIFY, deduped by
  a `NOTIFIED <key>` line in the marker (`<class>:<seat>` for a blocker park, `escalation-budget` for
  the budget park). A repeat dead-end parks **silently** — the operator was already told.
- **Budget dead-end at the JOIN gate (§d/§e).** An exhausted `ORCH_FOLLOWUP_BUDGET` that blocks a
  JOIN check used to leave the epic waiting **silently** (ABS-164 waited >1h). Now `join_check_epic`
  detects the exhausted budget, **names** it in the `JOIN-WAIT` intent
  (`followup-budget-exhausted budget=N`), and emits a single naming operator NOTIFY (deduped by a
  `JOIN-BUDGET-DEADLOCK` marker comment) instead of waiting.

Validated by the **ABS-199 section of `tests/test-orchestrator.sh`**: the taxonomy + precedence, the
2nd-visit auto-park with NOTIFY-once, the no-false-positive negative case (two distinct classes, and
the same class at distinct seats), the escalation-budget park + reset-on-forward-progress + no-reset-
on-bounce, and the JOIN budget dead-end naming NOTIFY.

### Turn-cap salvage (ABS-175)

A spawn that runs out of turns (result JSON `subtype=error_max_turns`) used to be discarded as a
crash — run ABS-129 lost the whole $2.01 of a capped implementer spawn that way, then re-spawned it
cold. ABS-175 salvages it instead: when a spawn exits at the cap and a resumable session id exists
(`ORCH_SESSION_RESUME=1`, live mode only), the runner resumes that **same session** exactly **once**
with a turn budget resolved per-role (`salvage_max_turns()`: `ORCH_SALVAGE_MAX_TURNS_<ROLE>` env > `builtin_role_salvage_max_turns()` built-in > `ORCH_SALVAGE_MAX_TURNS` default 5) and a fixed prompt — *"Turn-Limit
erreicht — committe was fertig ist, schreibe deinen Handoff, stoppe."* The salvage output then feeds
the normal handoff flow: if it produced a handoff the spawn succeeds and the station advances as
usual. Details:

- **Exactly one salvage per spawn attempt.** The salvage is straight-line code inside a single spawn
  attempt (it calls the spawn seam directly, never re-enters the attempt), so a salvage that itself
  caps out is **not** salvaged again — it falls through to the existing retry-once-then-crash path
  (`INTENT RETRY` → `INTENT SPAWN-CRASH`). No endless-salvage loop is possible.
- **Not a rework bounce.** A salvage drives no backward transition, so the rework counter never sees
  it; it is a rescue of in-progress work, not a re-review.
- **Observability.** `INTENT SALVAGE-RESUME` (stdout) and `INTENT-SALVAGE-RESUME` (run.log) mark the
  event, with a `SPAWN-USAGE` line accounting the salvage's own cost. After a cap event the run.log
  therefore shows a salvage resume rather than a full fresh respawn.
- Turn-cap **right-sizing** (how high the caps are set) is out of scope here — see ABS-156.
- **Station-aware salvage cap (ABS-605).** The rte/epic-integration station's hard exit criterion is a full ABS-453 suite that 5 turns cannot run; its built-in salvage budget is 30 turns (`builtin_role_salvage_max_turns rte`). Every other seat has no built-in and falls to the default 5. Override any seat with `ORCH_SALVAGE_MAX_TURNS_<ROLE>`.

### Blocked → TDM triage (spec §1.3, §3.7, ABS-76)

`Blocked` (from **any** stage, story or epic pipeline) maps to `SPAWN tdm` and spawns the tdm
exactly once per Blocked **entry** (comment-keyed guard, the ABS-62/ABS-75 marker pattern —
`has_blocked_marker`/`blocked_from_marker` in `scripts/orchestrator.sh`). Before the spawn, the
runner reads the ticket's own transition history for the most recent `<from> -> Blocked` transition
and persists that **pre-blocked status** in a `BLOCKED-FROM=<status> (orchestrator)` marker comment
(`kind: gate-results`, actor `orchestrator`) — TDM reads this marker rather than recomputing it. The
TDM classifies the blocker (environment / external-dependency / scope), resolves or reroutes what
agents can fix, and escalates only genuinely human-only calls (credentials, cost, new features) to
the escalation NOTIFY. When TDM's handoff **declares a target**, the runner applies it via the
normal `apply_handoff_transition` path (ABS-132) — epics resume `Grooming`, stories resume their
implementing seat, etc. When the TDM handoff **declares no target**, `escalation_resume_target`
(ADR-A-0019) drives the resume deterministically: the runner reads the `BLOCKED-FROM` marker and
transitions back to that pre-blocked origin. Origins that are themselves escalation statuses
(`Backlog`, `Blocked`, `Needs PO Decision`) are excluded — the runner halts idempotently in
`Blocked` in that case. The runner never picks a status by discretion. Re-entering `Blocked` later
(a fresh `-> Blocked` transition) has no marker newer than that entry, so it is a new entry and
gets a fresh TDM spawn.

### Per-day spawn budget (spec §3.9)

Beyond the per-run budget (`ORCH_MAX_SPAWNS_PER_RUN`, above), v3 adds a per-**day** cap,
`ORCH_MAX_SPAWNS_PER_DAY` (default 400, `0` disables), enforced through a **dated ledger file**
under the state dir (`spawn-ledger-YYYYMMDD`) that survives restarts and applies **across runs**.
One ledger line is appended per spawn intent (dry-run included, mirroring the per-run accounting).
At exhaustion the runner posts a NOTIFY, logs `INTENT SKIP-BUDGET-DAY` for each would-be spawn, and
halts the cycle — same shape as the per-run budget. Recalibrated to 400 (PILOT-63 AC3) from the
original sim-pin guess of 200: measured runs consumed 161 (Pilot 4) and 251 (Pilot 5), so a single
epic wave already overran 200 and hard-stopped a healthy run. Only spawns that actually reach a seat
are charged — PILOT-63 AC1 stopped counting worktree-provisioning failures (INTENT-SKIP-NOWORKTREE),
which had been 62.5% of the units at the 2026-07-25 pause.

### Wipe-resistant spawn ledger (ABS-393)

A state-dir wipe zeros the dated ledger, silently re-opening the full daily budget. The 2026-07-17
incident demonstrated this: 168 ledger entries were wiped, and the operator had to hand-reconstruct
the count from `run.log`.

`rebuild_daily_ledger()` closes this gap. When `heal_state_dir` finds the dated ledger missing, it
calls `rebuild_daily_ledger` to re-seed it from `run.log` before the run continues:

1. Reads `$ORCH_RUN_LOG` (the append-only TSV event log that survives a state-dir wipe when pinned
   outside the state dir via `ORCH_RUN_LOG`, as in the incident).
2. Counts today's `INTENT-SPAWN` rows — one per live spawn, the same chokepoint that appends a
   ledger line in normal operation.
3. Writes that many placeholder lines back into the ledger file so `daily_budget_exhausted`
   (a `wc -l`) reads the correct count.

If `ORCH_RUN_LOG` is unset or the file does not exist, `rebuild_daily_ledger` prints `0` and
returns cleanly — no worse than a fresh run with no prior history. The reconstruction is
budget-conservative: it counts each spawn once, matching the original `record_daily_spawn` ledger.

*Operator note:* after a self-heal, confirm the reconstructed entry count in the `run.log` WARN
line (`spawn-ledger reconstructed from run.log (N entries — budget preserved)`) matches your
expected daily spend before resuming a long run.

### Notify points

There is exactly **one** planned human notification in a clean epic run: the **ready-to-test**
NOTIFY when the epic enters `Ready for Epic Acceptance`. The runner special-cases this status —
`ready-to-test: epic <id> is deployed to staging and ready for human acceptance` — versus the
generic ops NOTIFY text used everywhere else. All other NOTIFYs are exception paths (budget
exhaustion, tdm's human-only Blocked escalation, SPAWN-NOTIFY acceptance checks), not part of the
happy path.

That exactly-one invariant describes the **epic** path. A **parentless / Path-A ticket** (ABS-106)
never reaches `Ready for Epic Acceptance` — it has no epic — so its single ready-to-test NOTIFY fires
instead from the RTE `Merging` seat on PR-open (see "Path-A tail"), carrying the PR URL for the human
to test and merge. The `Ready for Merge` gate it then rests at still emits none (it is a silent NOOP,
per "Human-Only Boundaries"). Net: exactly one planned ready-to-test NOTIFY per completed unit of work
in both paths — from `Ready for Epic Acceptance` on the epic path, from the RTE `Merging` seat on Path-A.

### Watcher / cron notification rule (ABS-302)

Session-local cron jobs and watchers (scripts that run inside a Claude Code session and watch for
an event) can only wake the **Claude session** — they cannot reach the **operator** if the operator's
terminal is not in that session. The rule:

> **Operator-relevant events must go out via `PushNotification` (+ macOS dialog via `osascript`),
> never via session-local stdout/stderr alone.**

A session-local `echo` or `log` line is invisible once the operator's terminal has detached or the
session is backgrounded. `PushNotification` (the Claude Code built-in tool) and a concurrent
`osascript` dialog reach the operator's OS notification tray regardless of session state. Use both:

```bash
# Pattern: operator-reaching watcher notification
osascript -e "display notification \"$msg\" with title \"Orchestrator\"" 2>/dev/null || true
```

and emit a `PushNotification` tool call from the Claude session for the same event. This rule applies
to all watcher scripts that the operator sets up to monitor long-running orchestrator runs
(e.g. "alert me when the epic enters Ready for Epic Acceptance"). It does NOT change how the runner
itself emits its built-in NOTIFY events (those go through `scripts/orchestrator-spawn-claude.sh`'s
notification seam, which is already operator-reaching).

### Cost pins (sim §5, ADR-A-0009)

The per-day budget is sized from the simulation's spawn-count pins. These are **assertions**, not
estimates — the E2E suite (ABS-80) checks them and a divergence is a finding, not a test to relax:

- **27 spawns** for a 3-story epic including the DoR gate (S1 happy path).
- **6 spawns** for a plain (unflagged) story — implement, review, qas, acceptance, merge, docs
  (all four conditional stages SKIP-FORWARD; S4). The sixth is the `Docs` station — the **sole**
  docs mechanism, running before the human merge gate; `Done` is NOOP, so there is no seventh
  post-merge tech-writer spawn (ABS-137).
- **16 spawns** to NOTIFY for a max-flag (design+security+data) story incl. the Ticket-Review gate
  — the upper per-story cost pin (S13).

---

## Iteration-Guard → Needs PO Decision Behavior (§5.5, counting model v2: ABS-115)

`In Review` and `In Test` are "bounce-capable" statuses — an implement↔validate loop the ABS-12
iteration guard governs. Before spawning the review/QA agent on one of these transitions, the
orchestrator calls `scripts/hooks/iteration-guard.sh <ticket>` (or `$ORCH_ITERATION_GUARD` if
overridden):

- **Exit 2 (at cap)**: the orchestrator does **not** spawn. Instead it logs
  `INTENT BLOCK-ITERATION-CAP`, posts a `kind: gate-results` comment and escalates the ticket to
  `Needs PO Decision` (in `--live`; dry-run only logs the intent).
- **Any other outcome (0, or the guard script missing/unreachable)**: fail-open — proceed to the
  normal spawn path. A broken tracker or missing guard must never deadlock the loop; the ABS-11
  prompt-level rules remain the fallback layer.

Counting model v2 (ABS-115, specs/ABS-115-iteration-guard-v2-spec.md): only REAL bounces count —
a marker-bearing gate comment (`kind: gate-results|handoff`, "Iteration N of M") followed by a
backward transition. APPROVE results carrying the marker informationally ("… (no bounce)") and
operator comments quoting a marker do NOT count (the ABS-107 false-positive fix). Two levels:

- **Per-gate counter**, effective cap = `max(ITERATION_GUARD_DEFAULT_CAP, highest "of M" seen)`
  (floor default 3, PILOT-64). A `Iteration N of M` marker may only RAISE the cap above the
  configured floor — the max over all markers wins, not "most recent" — so an agent cannot
  shrink its own budget via prose and deadlock already-approved work (the PILOT-32 class;
  ADR-A-0026: control state in typed config, not parsed comments). Forward progress over a gate
  resets ONLY that gate's counter; a later fall-back counts fresh. The block message names the
  cap source (`[configured floor …]` vs `[raised by marker to …]`) alongside the
  functional-vs-abort split so the operator need not hand-diagnose the cap.
- **Cumulative ticket counter** (never resets), cap `ITERATION_GUARD_TICKET_CAP` (default 9,
  `0` = off) — the general per-ticket budget brake. Distinct from the §3.2 rework counter
  (`ORCH_REWORK_LIMIT`), which is windowed (re-arms on every PO decision) and marker-independent;
  the guard's lifetime budget catches repeated PO-round-trip churn that §3.2's window forgives.

Do NOT disable the guard by pointing `ORCH_ITERATION_GUARD` at a nonexistent path — that
ABS-102-era workaround is obsolete since the v2 counting model and must not appear in run recipes.

This is a mechanical backstop, not a replacement for the ABS-11 in-prompt iteration rules that
gate agents already follow.

---

## Read-only Review Gate (ABS-57)

The `In Review` spawn reuses the write-capable **`system-architect`** role (the AGENTS.md Stage 1
reviewer, which carries `Write`/`Edit` for its ADR/spec-authoring duties). A reviewer, though, must
only be able to **review, comment, and transition** — never edit the code under review. Otherwise a
review agent could "just fix" the issue it finds, ship code that was never reviewed, and bypass the
implement↔review bounce loop and its iteration cap.

So for the `In Review` transition only, the runner hands the spawn seam a read-only toolset via
`ORCH_TOOLS` (default `$ORCH_REVIEW_TOOLS` = `Read, Bash, Grep, Glob`), which overrides the role's
own `tools:` frontmatter for that spawn — `system-architect.md` itself is unchanged. Every other
spawn passes an empty override and keeps its frontmatter tools.

`In Test` (`qas`) is intentionally **not** narrowed: `qas` already ships without `Write`/`Edit` and
needs its tracker-comment tools to post evidence and transition the ticket. Forcing the read-only
set on it would strip those.

---

## Reconciliation and Crash Recovery (§5.1)

The mock adapter's `events` snapshot **advances on read, not on processing** — a concurrency-cap-
deferred event is never redelivered by the adapter itself. Two mechanisms backstop this:

1. **In-memory pending set.** A cap-deferred event (`INTENT DEFER-CAP`) is held in-process and
   retried at the **start of the next cycle**, ahead of freshly polled events, once a concurrency
   slot frees. This is pure in-memory state — it is lost if the process dies. **A lock-skipped
   dispatch (`INTENT SKIP-LOCKED`) defers into the same pending set (ABS-133, Befund 5):** when a
   dispatch is skipped because a *different* in-flight spawn holds the ticket's single-flight lock,
   it is re-queued (rc 3, exactly like a cap defer) and retried once the lock releases — rather than
   dropped. Without this a dispatch skipped while the ticket rests in a status reconcile does **not**
   re-derive (a legit-rest status, e.g. `Done → tech-writer`) was lost forever, since the crash-safe
   sweep below only covers reconcilable statuses. The re-read guard (§5.4) makes the retry a no-op if
   the ticket has since moved on, so it never double-spawns.
2. **Reconciliation sweep.** Runs once on startup (`ORCH_RECONCILE_ON_STARTUP=1`, the default) and
   every `ORCH_RECONCILE_EVERY_N_CYCLES` cycles thereafter. It scans **all** current ticket state
   via `tracker search` (not the event stream) and re-derives actionable state: any ticket sitting
   in a *transient work* status (`Ready for Development`, `In Review`, `In Test`, `Ready for Human
   Acceptance` — see `is_reconcilable_status()`) with no live single-flight lock held is dispatched
   as if freshly observed. Tickets resting in entry/terminal/human-owned states (`Backlog`, `In
   Progress`, `Done`, `Ready for Merge`, `Blocked`) are deliberately **skipped**: they are
   legitimate resting states, so sweeping them would mass-spawn a whole backlog on startup.
   (`Done` is NOOP as of ABS-137 — docs come only from the `Docs` station before the human gate —
   so it would never re-spawn `tech-writer`, but it is skipped here regardless as a terminal state.)
   This is the crash-safe net — it repairs a lost pending-set entry from an orchestrator process
   that died mid-cycle, with no persisted queue required.

Both paths reuse the same re-read guard (§5.4: dispatch is a no-op if the ticket has moved out of
the event's `to` status by the time it's acted on) and the single-flight lock (§5.2), so a
reconciliation dispatch over an already-succeeded or already-in-flight ticket is safe — it will
not double-spawn. `tests/e2e-orchestrator-dryrun.sh` step 9 demonstrates this exact sequence:
cap=1 defer → simulated crash → fresh runner's startup sweep recovers the lost ticket exactly
once, while the ticket that already succeeded is correctly left alone.

**Because reconciliation exists, the pending set can safely stay ephemeral** — there is no
persisted spawn queue to inspect or repair by hand. If you suspect a crash mid-cycle, simply start
a fresh orchestrator process; the startup sweep does the recovery.

---

## Agentic Backend Binding (ABS-229)

`scripts/backend-tracker.sh` is a drop-in `$TRACKER_CMD` that speaks the canonical operations
against the **self-hosted agentic delivery backend** (Node/Postgres, `docker compose up`). It is
CLI-byte-identical to `scripts/mock-tracker.sh`, so the orchestrator runs **unmodified** against
it (ADR-A-0021 §d). Its only dependency is `bash` + `curl` — no `python3`, no `jq`.

**Lane doctrine (key difference from Jira):** with the backend there is a **single sanctioned
lane** — both the orchestrator poll loop and interactive human sessions use
`scripts/backend-tracker.sh` behind `$TRACKER_CMD`. No Atlassian MCP server is loaded and the
`jira-sop` skill is not used. See the authoritative
[lane doctrine](../../profiles/neutral/adapters/task-tracking.md#lane-doctrine-tracker_cmd-adapter-and-the-jira-two-lane-exception)
for details.

### Binding it

```bash
# Point the orchestrator at the backend adapter (dry-run first — always).
export TRACKER_CMD=scripts/backend-tracker.sh
scripts/orchestrator.sh                 # dry-run: logs intents, spawns nothing

# When ready, go live (spawns real subagents, writes to the backend):
scripts/orchestrator.sh --live
```

### Environment variables (human-provisioned)

| Variable | Required | Purpose |
| --- | --- | --- |
| `BACKEND_URL` | no | Backend base URL. Default `http://localhost:8420`. |
| `BACKEND_TOKEN` | **yes** | Project-scoped orchestrator token. Provisioned once at registration (step 4 of the install guide); stored hashed server-side — returned exactly once. **Secret.** Never commit to the repo. |
| `TRACKER_PROJECT` | **yes** | Project key (e.g. `ABS`) that scopes every adapter call. |
| `ORCH_INSTANCE_ID` | no | Orchestrator instance id (e.g. `orch-01`). Sent as `X-Orch-Instance`; the backend tracks live/stale per instance and uses it for the server-side event cursor. Set to distinguish multiple orchestrator processes against the same project. |

`BACKEND_TOKEN` is a **human-only** provisioning step (ADR-A-0004). Provision it via shell
profile or secret manager — the adapter reads it from the environment only and it never
appears on any command line or in any log.

### Registration and token bootstrap

See the full walkthrough in [`docs/guides/AGENTIC-BACKEND-INSTALL.md`](../../docs/guides/AGENTIC-BACKEND-INSTALL.md).
Quick reference:

```bash
TOKEN=$BACKEND_BOOTSTRAP_TOKEN   # the admin bootstrap token set in backend/.env
BASE=http://localhost:8420

# 1) create the project (once)
curl -sf -X POST "$BASE/api/admin/projects" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"key":"ABS","name":"My project"}'

# 2) register this orchestrator instance -> project-scoped token (returned ONCE)
curl -sf -X POST "$BASE/agent/v1/orchestrators" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"project":"ABS","instance":"orch-01"}'
# save the returned "token" field as BACKEND_TOKEN

# 3) export into env and point the orchestrator
export BACKEND_URL=http://localhost:8420
export BACKEND_TOKEN=<token from step 2>
export TRACKER_PROJECT=ABS
export TRACKER_CMD=scripts/backend-tracker.sh
```

### TRACKER_CMD switching recipe

To switch a running project from the mock adapter or Jira to the backend:

```bash
# 1. Import existing tickets (if any) into the backend:
tar -cf - -C work/tickets . | \
  curl -sf -X POST "$BASE/api/admin/import?project=ABS" \
    -H "authorization: Bearer $TOKEN" \
    -H "content-type: application/x-tar" --data-binary @-

# 2. Swap the adapter env and restart the orchestrator:
export TRACKER_CMD=scripts/backend-tracker.sh
export BACKEND_TOKEN=<your registered orchestrator token>
export TRACKER_PROJECT=ABS
scripts/orchestrator.sh --dry-run --once   # confirm wiring

# 3. Go live:
scripts/orchestrator.sh --live
```

The conformance suite (`tests/test-backend-tracker.sh`) asserts that `scripts/backend-tracker.sh`
passes every mock-adapter assertion — any CLI divergence is a release blocker (ADR-A-0021 §d).

For a **staged Jira → backend migration** (Shadow → Pilot → Cutover, with the dual-write shim
`scripts/shadow-tracker.sh` and the divergence reporter `scripts/tracker-divergence.sh`), follow
[TRACKER-MIGRATION-RUNBOOK.md](TRACKER-MIGRATION-RUNBOOK.md) (epic ABS-326) — it wraps this
switching recipe in per-phase checklists, gate criteria and the rollback procedure.

### Allowlist baseline

The backend adapter path variants follow the same allowlist rule as the Jira adapter — seed both
forms so a seat that prepends `./` is not silently denied:

```json
"Bash(scripts/backend-tracker.sh:*)",
"Bash(./scripts/backend-tracker.sh:*)"
```

### Board URL

The dashboard (`http://localhost:8420` by default) shows the kanban, ticket detail drawer, live
event feed, escalation inbox, and orchestrator live/stale status. All human write actions
(transition, comment, release toggle) go through the same `/api/v1` routes and the same
transition engine as agent ops — one write path, one audit log.

---

## Jira Cloud Binding (ABS-64)

> **Legacy scope:** this binding is for projects that use **Jira Cloud as their tracker** and
> are bound to the `jira-github-postgres` (or a custom Jira) profile. New projects using the
> agentic backend (ADR-A-0021) use `scripts/backend-tracker.sh` (above) and do not need the
> Atlassian MCP server or the `jira-sop` skill. `scripts/jira-tracker.sh` and this section
> are retained for Jira-profile consumers and are not deleted (ADR-A-0021 Consequences).

`scripts/jira-tracker.sh` is a drop-in `$TRACKER_CMD` that speaks the canonical operations
against the **Jira Cloud REST API v3**. It mirrors `scripts/mock-tracker.sh`'s CLI surface exactly
(same subcommands, flags, output shapes, exit codes, error messages), so the orchestrator runs
**unmodified** against it. Its only dependencies are `bash`, `curl`, and `python3` (all already
harness prerequisites — `python3` handles JSON parse/serialize and ADF wrapping; **no `jq`**).

### Binding it

```bash
# Point the orchestrator at the Jira adapter (dry-run first — always).
export TRACKER_CMD=scripts/jira-tracker.sh
scripts/orchestrator.sh                 # dry-run: logs intents, spawns nothing

# When ready, go live (spawns real subagents, writes to Jira):
scripts/orchestrator.sh --live
```

### Environment variables (human-provisioned)

| Variable | Required | Purpose |
|----------|----------|---------|
| `JIRA_SITE` | yes | Jira Cloud base URL, e.g. `https://acme.atlassian.net`. |
| `JIRA_EMAIL` | yes | Atlassian account email (Basic-auth user). |
| `JIRA_API_TOKEN` | yes | Atlassian API token. **Secret.** Never stored in the repo, never echoed. |
| `JIRA_PROJECT_KEY` | yes | Project key (e.g. `ABS`) that fences every `create`/`search`/`events` sweep. |
| `JIRA_JQL_FILTER` | no | Extra JQL AND-ed into the fence (see Fencing below). |
| `JIRA_STATUS_ALIASES` | no | Boundary renames for statuses your Jira workflow spells differently, `Canonical=Jira` (newline-separated for several). Case-only differences are folded automatically and need no entry. See Status-mapping prerequisite. |

The API token is a **human-only** provisioning step (ADR-A-0004). Provision it out-of-band (shell
profile, secret manager, CI secret) — the adapter reads it from the environment only. It is passed
to `curl` through a mode-600 `--config` file (never on the command line, so it never appears in
`ps` or in curl's verbose trace), and all curl output is scrubbed before it can reach a log. A
credential-leak test (`tests/test-jira-tracker.sh`, Test 10) asserts a known dummy token never
appears in any output.

### Fencing (do this before the first live run)

`JIRA_JQL_FILTER` restricts every sweep to a designated subset. **The first live runs MUST be
fenced** to a small set of throwaway tickets so a misconfiguration cannot touch real backlog:

```bash
# Only tickets labelled orchestrator-live are visible to the adapter.
export JIRA_JQL_FILTER='labels = orchestrator-live'
```

Combined with `JIRA_PROJECT_KEY`, the effective fence is
`project = "<KEY>" AND (labels = orchestrator-live)`. Widen it only once a fenced run has passed.

### Status-mapping prerequisite (human Jira workflow config)

Canonical statuses map **1:1 to Jira workflow statuses** — no lossy folding. The Jira project's
workflow must define every canonical status the pipeline uses so the adapter can resolve a
transition to each. Names should match the canonical spelling, with two boundary allowances the
adapter handles for you (a rename, never a fold):

- **Case differences are folded automatically** — a Jira status spelled `in review` or
  `ready for Merge` is surfaced to the orchestrator as the canonical `In Review` / `Ready for Merge`.
- **A genuinely different name is aliased** via `JIRA_STATUS_ALIASES` (`Canonical=Jira`,
  newline-separated). Example — this repo's own `ABS` project keeps Jira's native
  `Selected for Development` board status instead of `Ready for Development`:

  ```bash
  export JIRA_STATUS_ALIASES="Ready for Development=Selected for Development"
  ```

The full canonical set the v3 pipeline transitions between is the single source of truth in
[`profiles/neutral/adapters/statuses.yaml`](../../profiles/neutral/adapters/statuses.yaml) (the
`- name:` entries — story pipeline, epic pipeline, and the cross-cutting `Blocked` /
`Needs PO Decision`). The Jira workflow must define each (modulo the case-fold / alias allowances
above). The transition between these statuses must be permitted by the Jira workflow — the adapter
resolves the target status name to its per-issue transition id at call time and fails clearly if the
workflow offers no transition to it. Issue types must include `Epic`, `Story`, and `Sub-task` (the
canonical `epic`/`ticket`/`subtask` mapping). The implementer-`role` hint has no native Jira field,
so it is stored as a `role:<name>` **label** and surfaced by `get`.

**Timestamp normalization (stall-detection compatibility).** Jira returns native timestamps with
millis and a numeric offset (e.g. `2026-07-04T10:00:00.000+0530`). The adapter's `get` normalizes
every emitted timestamp — `created:`/`updated:` and each comment `### <at>` header — to the mock's
canonical UTC `Z` form (`2026-07-04T04:30:00Z`), because the orchestrator's `iso_to_epoch` parses
only that form. This keeps the ABS-62 stall subsystem (ticket-age rules, PO-park re-raise guard)
working unchanged; `scripts/orchestrator.sh` is not modified.

### First-run safety checklist

1. **Dry-run first.** Confirm the log shows the intended spawn *intents* and nothing else.
2. **Fence to one designated ticket** via `JIRA_JQL_FILTER` (e.g. a single `orchestrator-live`
   labelled test ticket).
3. **Cap spawns:** set a low `ORCH_MAX_SPAWNS_PER_RUN` (e.g. `1`) for the first live run.
4. Only after a clean fenced run, widen the fence and raise the cap.

### API-call budget

Steady-state cost is dominated by the `events` poll: **exactly one JQL sweep per poll cycle** of
the fenced project. At the default `ORCH_POLL_INTERVAL=15` that is one search call every 15s. Other
operations are 1–2 calls each (`get` = issue GET + 1 comment-list GET per page, so 2 calls for
a single-page ticket, +1 per extra page of 100 comments; `transition` = transitions-list + POST;
`create` = one POST). The adapter header documents the per-op budget in full.

**Fence ceiling (single-page sweeps).** Every JQL sweep (`search`/`children`/`events`) fetches one
page of `maxResults=200` issues and does **not** paginate (the minimal-change v1 default). Keep the
fenced set (`JIRA_PROJECT_KEY` + `JIRA_JQL_FILTER`) **under 200 issues** so no ticket is missed. If
a fence can grow past 200, tighten `JIRA_JQL_FILTER` (e.g. add a sprint/label clause) or extend
`jql_search` with pagination.

---

## Gitea Tracker Adapter (this project's task-tracking provider)

`scripts/gitea-tracker.sh` implements the canonical task-tracking operations
(`profiles/neutral/adapters/task-tracking.md`) against the real Gitea issue tracker at
`$GITEA_SITE/$GITEA_OWNER/$GITEA_REPO`. Its CLI surface mirrors `scripts/mock-tracker.sh` exactly
(same subcommands, flags, output shapes, exit codes), so the orchestrator runs **unmodified**
against it. Dependencies: `bash`, `curl`, `python3` (JSON only — no `jq`).

Unlike Jira, Gitea has **no native custom-status field** (only open/closed) and no native
lane/role/priority/parent/depends-on fields, so this adapter maps every canonical field onto
labels (using Gitea's *exclusive scoped label* feature — `scope/value`, at most one label per
scope on an issue at a time) plus a hidden HTML-comment metadata block at the top of the issue
body for the handful of fields with no label-shaped representation (`parent`, `depends_on`,
`links`, `iteration_cap`). See the adapter's own header comment for the full mapping table.

### One-time setup (required before first use)

```bash
export GITEA_SITE="https://your-gitea-host"
export GITEA_TOKEN="..."          # repo-scope access token; never commit this
export GITEA_OWNER="your-org-or-user"
export GITEA_REPO="your-repo"

scripts/gitea-tracker.sh setup     # idempotent: creates the ~47 required labels
                                   # (28 canonical statuses + type/lane/role/priority/flag
                                   # scopes + ac-blocking). Safe to re-run at any time.
```

### Binding it

```bash
export TRACKER_CMD=scripts/gitea-tracker.sh
scripts/orchestrator.sh                 # dry-run: logs intents, spawns nothing
scripts/orchestrator.sh --live          # spawns real subagents, writes to Gitea issues
```

### Environment variables (human-provisioned)

| Variable | Required | Purpose |
|----------|----------|---------|
| `GITEA_SITE` | yes | Gitea base URL, e.g. `https://gitea.example.com`. |
| `GITEA_TOKEN` | yes | Gitea access token (repo scope). **Secret.** Never stored in the repo, never echoed. |
| `GITEA_OWNER` | yes | Repo owner/org. |
| `GITEA_REPO` | yes | Repo name. |
| `GITEA_TICKET_PREFIX` | no | Cosmetic id prefix (default `AITBC`). Ticket identity is always the Gitea issue number; unlike the mock adapter's `--prefix`, this does not create a separate id namespace — Gitea has one issue-number sequence per repo. |

The token is delivered to `curl` through a mode-600 `--config` file (never on the command line, so
it never appears in `ps` or curl's verbose trace), and all curl output is scrubbed before it can
reach a log (same discipline as `jira-tracker.sh`).

### Fencing / safety

Gitea issues are already repo-scoped (one tracker per repo), so there is no cross-project fence to
configure the way `JIRA_JQL_FILTER` fences a shared Jira instance. The natural fence is: point a
first live run at a **throwaway test repo** (a separate `GITEA_REPO`), not the real project repo,
and only switch `GITEA_REPO` to the real one once a fenced run has passed. As with Jira, cap
`ORCH_MAX_SPAWNS_PER_RUN` low for the first live run against real issues.

### API-call budget

`events` costs one `GET /issues` sweep per poll cycle (paged past 50 issues). `get` costs one issue
GET + one comments GET per page of 50. `create`/`transition`/`comment`/`link`/`update`/`assign`
cost one or two calls each; label lookups reuse a per-invocation in-memory cache (one `GET /labels`
per script invocation, not per label).

---

## Stall Detection (ABS-62)

The same reconciliation sweep that recovers dropped spawns also runs two **mechanical, bash-only**
stall rules over resting `Backlog` tickets. This is a detection mechanism only — all judgment stays
with a fresh PO-Agent, spawned through the normal event path when a rule fires (ADR-A-0009: bash
detects for free, an LLM is only spent on an actual finding; ADR-A-0002: judgment is a fresh
single-ticket spawn). There is **no LLM stall analysis and no periodic PO spawns**.

The two rules (v1 — deliberately few and mechanical):

1. **Undecomposed epic** — a ticket of `type: epic`, status `Backlog`, with zero children, older
   than `ORCH_STALL_EPIC_SECONDS` (default 900s). This is the common "epic filed and forgotten,
   never broken into stories" stall.
2. **Resting too long** (opt-in) — any ticket in `Backlog` whose `updated:` is older than
   `ORCH_STALL_RESTING_SECONDS`. Default `0` disables it; set it to opt in to a general
   backlog-freshness sweep.

**On a rule firing** the sweep raises the ticket to `Needs PO Decision`: in `--live` it posts an
`actor: orchestrator`, `kind: decision` comment naming the rule and transitions the ticket (the
raise is itself a tracked transition — ADR-A-0006), and the ABS-61 event mapping then spawns the
PO-Agent. In `--dry-run` it logs
`INTENT STALL-RAISE ticket=<id> role=- to=Needs PO Decision note=rule=<n>` only, consistent with
the sweep's other dry-run intents.

**Re-raise guard (unified, cross-rule).** A ticket the PO has already parked is never re-flagged by
**either** rule. Each raise leaves a `STALL-RAISE rule=<n> (orchestrator)` marker in its
`kind: decision` comment body; the guard only counts a marker that actually appears in the body of
an `actor: orchestrator`, `kind: decision` comment (a comment that merely *quotes* the marker text —
realistic for a ticket about ABS-62 itself — does not disarm detection). The guard suppresses any
raise (rule 1 or rule 2) when the ticket carries such a marker **and** the PO has since parked it
back in `Backlog` — i.e. there is a `Needs PO Decision -> Backlog` transition (the PO's "leave it in
Backlog" decision). Suppression lifts only when `updated:` is strictly **newer** than that park
transition's timestamp: an edit after the park (a `tracker update`, a new comment, or a
re-transition) re-arms the rules. The comparison is against the **PO-park timestamp**, not the raise
time, because the raise's own comment and transition already bump `updated:`.

Suppression is scoped to a *live PO park*. A marker with **no** `Needs PO Decision -> Backlog`
transition does **not** suppress — the ticket is eligible to be raised again. This covers two real
cases the guard must not deadlock: the PO routed the ticket onward (e.g. to `Ready for Development`)
and it was later deprioritized back to `Backlog` still stalled, and a half-raise where the marker
comment landed but its transition failed (so no PO-Agent was ever spawned) — both must retry. There
is no loop risk: a fresh raise then park re-enters the normal park-suppress path. Without the guard a
PO decision of "leave it in Backlog" would loop forever; keying the re-arm on `updated:` also honors
the ticket's contract that a genuine edit after the decision must be re-flagged.

---

## Spawn Telemetry (ABS-125)

Per completed spawn the runner parses the session transcript (found by session UUID under
`ORCH_TRANSCRIPT_DIR`, default `~/.claude/projects`) and records tool/MCP/skill usage — NAMES,
counts and call order only, never arguments/payloads: a `TELEMETRY` run.log line
(`Read=14 Bash=9 Skill=1 …`) plus the ordered sequence in
`work/.orchestrator/telemetry/<ticket>.<role>.<epoch>.seq` (the sequence exposes behavior
patterns like "reads 6 documents before the first edit"). Any lookup/parse failure — crash,
foreign provider (Cursor seats have no transcript), CLI format change — degrades to
`TELEMETRY … unavailable`, never a pipeline break. Resumed sessions aggregate the whole session,
not the delta (documented caveat). `ORCH_TELEMETRY=0` disables. The cost report's
"tools used vs granted" section lists per-role least-privilege candidates (caveat: In Review
spawns run under `ORCH_REVIEW_TOOLS`, not the system-architect frontmatter). Design record:
`specs/ABS-125-spawn-telemetry-spec.md`.

---

## Built-in Skills for Spawned Seats (ABS-123)

Audit result (`docs/agent-outputs/ABS-123-headless-skill-audit.md`, real probe spawns): headless
`claude -p` sessions load the full skill catalog (repo, user, CLI built-ins); the ONLY blockers
were (1) the `tools:` frontmatter allowlist — `Skill` was missing — and (2) skill INVOCATION
being permission-denied under `--permission-mode dontAsk` for repo/user skills, lifted by
`--allowedTools "Skill"`. Plan B (mirroring skills into the repo) is unnecessary; the one real
gap: `anthropic-skills:*` (docx/pdf/…) do not exist headless.

Wiring: mapped seats carry `Skill` in `tools:` (both namespaces) + a per-seat mapping section in
their defs; the spawn seam passes `--allowedTools "Skill"` exactly when the resolved toolset
contains it (granular `Skill(<name>)` rules are unverified — least privilege is the `tools:`
allowlist + the mapping, quality over tokens per the operator decision; costs are visible in the
ABS-120 report). The packet header carries a one-sentence pointer. `ORCH_REVIEW_TOOLS` includes
`Skill` (code-review reads, never edits).

| Seat | Mapped skills |
|---|---|
| be-/fe-developer, data-engineer | `verify`, `simplify` |
| system-architect (In Review) | `code-review` |
| qas | `testing-patterns` (repo skill) |
| rte | `git-advanced` |
| po-agent | none (judgment seat, least privilege) |

---

## Review-Gate Sizing (ABS-124) and Per-Role Spawn Providers (ABS-122)

Gate sizing (opt-OUT, architect-approved skip matrix in
`specs/ABS-124-review-gate-sizing-spec.md`): a ticket flagged `skip-review` (docs-only, no
executable code) skips the In Review seat (`In Review → Security Review`, the conditional
machinery continues); `skip-test` (strict subset: pure docs/label fixes, requires `skip-review`,
v3 epic children only) also skips the QAS seat (`In Test → Design Test`). Every skip is loud
(`GATE-SKIP` intent + `kind: skip` audit comment); fail-safe = ALL gates on missing,
contradictory (`GATE-SKIP-CONTRADICTION`: any opt-in flag, or skip-test without skip-review) or
ineligible (`GATE-SKIP-INELIGIBLE`: parentless) combinations. PO acceptance and the human merge
gates are never sizable. BSA sets the flags at decomposition, enrichment adds fallback —
justification in the ticket body.

Per-role spawn provider (ABS-122): `ORCH_SPAWN_CMD_<ROLE>` overrides `ORCH_SPAWN_CMD` for one
seat (same seam contract). `scripts/orchestrator-spawn-cursor.sh` is the EVALUATION-status Cursor
adapter — do not wire a seat onto it before the live verification in
`docs/agent-outputs/ABS-122-cursor-spawn-provider-evaluation.md` is done (blocked on the
human-only `cursor agent login`).

---

## Token/Cost Accounting and the Cost Report (ABS-120)

Every spawn attempt appends one `SPAWN-USAGE` line to run.log (a NEW event kind — the existing
6-column TSV is untouched): note field `tokens_in=<n> tokens_out=<n> cost_usd=<x>`, extracted
from the spawn's own `--output-format json` result. Crashes/foreign providers degrade to empty
values — the line always appears.

`scripts/orchestrator-report.sh [run.log]` aggregates per seat (role), per story (ticket) and —
with `TRACKER_CMD` configured — per epic (parent via the adapter, one `get` per distinct ticket).
Zero-dependency bash+awk; without a tracker the epic section is skipped with a notice.

Model right-sizing defaults (operator-decided): the mechanical seats `qas`, `tech-writer`, `rte`
carry `model: sonnet` in their role frontmatter (both namespaces, ABS-96); `system-architect` and
`po-agent` stay on opus. Precedence (ABS-121): `ORCH_MODEL`/`ORCH_MODEL_<ROLE>` env (operator
emergency lever, always wins) > role-filtered `model:<sonnet|opus|haiku>` ticket label (BSA-assigned at
decomposition, enrichment-gate fallback; `MODEL-LABEL`/`WARN-MODEL-LABEL` run.log events; haiku
trivial-only) > role frontmatter > CLI default.

**The `model:`-label sizes IMPLEMENTATION effort, not review effort (ABS-128).** A **downsize**
(`model:sonnet`/`model:haiku`) reaches only the mechanical implementer/checker seats on the
`ORCH_MODEL_LABEL_ROLES` allowlist (default: `be-developer fe-developer data-engineer qas
tech-writer`); for a review/judgment seat (`system-architect`, `po-agent`, `bsa`,
`security-engineer`, …) the downsize is ignored and the seat keeps its role default (a
`MODEL-LABEL-SKIP` run.log event records the decision — visible in `--dry-run`). This stops a
per-ticket `model:sonnet` from silently dropping the architect review off opus (Live-Run ABS-126
finding). An **upsize** (`model:opus`) is never filtered — a hard ticket may lift ANY seat.
When labelling a ticket, size it by how much *building* it takes, not how much *reviewing*.
NOTE: the spawn seam currently pins every sonnet-family
alias to `claude-sonnet-4-6` (Sonnet 5 token regression — single chokepoint in
`orchestrator-spawn-claude.sh`; remove when resolved). Design record:
`specs/ABS-120-token-accounting-spec.md`.

---

## Crash Backoff, Outage Pause and Escalation Halt (ABS-118)

Three brakes against crash storms (rate-limit incident: 13 crash cycles in ~40 min), all checked
in `spawn_dispatch` in this pinned order: kill-switch → outage(+probe) → halt → backoff → budget.
Skips are free (no budget, no lock); probes are real spawns and stay budget-gated (ADR-A-0009).

- **Backoff** — after a SPAWN-CRASH the (ticket, status) gets an exponentially growing retry
  delay (`backoff-<ticket>` in the state dir); inside the window the sweep logs `SKIP-BACKOFF`
  and passes over. A successful spawn clears it. Crash at a different status restarts the ladder.
- **Outage pause** — `ORCH_OUTAGE_BURST` consecutive INSTANT crashes (< `ORCH_FASTFAIL_SECONDS`,
  across tickets) look like a rate-limit/auth outage: the loop stops spawning (`SKIP-OUTAGE`)
  and NOTIFYs. In `auto` mode (default) ONE probe spawn runs per `ORCH_PROBE_INTERVALS` step —
  the claim is taken synchronously before the (async) spawn launches, so probes never burst — and
  an answered probe auto-resumes with a NOTIFY. In `manual` mode the operator resumes by deleting
  `work/.orchestrator/outage`. The state survives restarts.
- **Escalation halt** — a crash OF the escalation seat itself (po-agent at `Needs PO Decision`)
  writes `halt-<ticket>` + ops NOTIFY instead of entering the rest→re-derive loop; the sweep logs
  `SKIP-HALT` and the stuck detector stays silent (the human already knows). Operator resume:
  delete the halt marker.

run.log events: `BACKOFF`, `OUTAGE-PAUSE`, `PROBE`, `AUTO-RESUME`, `ESCALATION-CRASH`.
Design record: `specs/ABS-118-crash-backoff-outage-spec.md`.

---

## Bounce Routing into In Progress + Stuck Detector (ABS-116)

A BACKWARD transition into `In Progress` (e.g. the reviewer bouncing `In Review → In Progress`,
observed live on ABS-108) no longer NOOP-deadlocks: the dispatcher reads the event's `from`, and
when it is a chain status later than In Progress it spawns/resumes the implementer exactly like a
`Ready for Development` bounce (role from ticket, all §5 safety gates, §3.2 rework backstop,
ABS-111 session resume). Forward entries (`Ready for Development → In Progress`), creation events
and `Blocked`/`Needs PO Decision` returns stay NOOP. Design record:
`specs/ABS-116-bounce-routing-stuck-detector-spec.md`.

**Worktree isolation (ABS-207).** The bounced implementer runs in its provisioned worktree
(`tmp/<ticket>-work`, branch `<ticket>-auto`), not the main checkout — `In Progress` is
worktree-eligible specifically for this BOUNCE-REROUTE path. Provisioning fails closed: if the
worktree cannot be reconnected the ticket rests; the runner never degrades to the main-checkout cwd.
See "Runner-Provisioned Worktrees" § Scope for the full eligible-status set.

The generic **stuck detector** complements it: a ticket resting `ORCH_STUCK_SWEEPS` consecutive
reconcile sweeps in a status nobody owns — not reconcilable, not a documented resting state
(Backlog/Blocked/Ready for Merge/Done/Epic Done/Stories In Flight/Ready for Epic Acceptance), no
in-flight single-flight lock, no `backoff-*` marker in the state dir — gets exactly ONE
`kind: notification` comment per (ticket, status) episode plus a `STUCK-DETECT` run.log event.
It never routes (ADR-A-0004: NOTIFY-only; the remedy is by definition unknown — unlike the
ABS-62 stall rules, which raise because their remedy is known). Primary real trigger: an
implementer that crashed after setting In Progress — the only net under that case, since
In Progress is not reconcilable. State: `work/.orchestrator/stuck-state` (persists across runner
restarts on purpose — stuck stays stuck, no re-NOTIFY after a restart).

### Liveness watchdog — full-standstill detection (ABS-312)

STUCK-DETECT is **per-ticket** and NOTIFY-only; backoffs are silent; parked tickets rest by design.
None of them sees the **whole-runner** state where **0 seats run while actionable work waits** — the
2026-07-14/15 ~4 h dead run, where two `SPAWN-CRASH` backoffs, one orphaned lock, one blocked-park
and one `ADR-A-0009` budget brake composed into a total standstill no single mechanism detected.

The **liveness watchdog** closes that gap. It runs at the **end of every reconcile sweep**, judging
the same ticket snapshot the sweep used:

- **Standstill sweep** = `live_spawn_count() == 0` **and** zero spawns emitted this sweep **and** ≥ 1
  fenced ticket in an *actionable* status (one the sweep would dispatch — reconcilable, or a labelled
  `Backlog` ticket). A live seat or any spawn clears the counter (a moving queue never trips it).
- After `ORCH_STANDSTILL_SWEEPS` consecutive standstill sweeps it acts **once per episode**, in two
  ordered stages recorded in `work/.orchestrator/standstill-episode` (so the credit is not re-granted
  every sweep):
  1. **Self-heal** (only when there is runner-owned work): reset **expired/exhausted** `backoff-*`
     markers and reclaim **orphaned** seat locks (a bounded, standstill-only exception to ABS-116's
     never-route rule — it fires only inside a confirmed standstill, never in normal operation), then
     give the heal a sweep to spawn. `STANDSTILL-SELFHEAL` in the run.log.
  2. **Escalate** if still stuck (heal produced nothing, or the only waiting tickets are behind human
     gates): `INTENT-STANDSTILL` to the run.log, a `kind: notification` comment on the affected
     epic **naming the blockers**, and an operator push (macOS `display dialog` — a banner is
     missable). A genuine spawn/seat in a later sweep clears the episode marker.
- **Hard boundary:** the watchdog **never lifts a budget brake (ADR-A-0009) or a human gate**
  (`Ready for Merge` / `Ready for Human Acceptance` / `Ready for Epic Acceptance` / `Blocked`). It
  only *names* them in the escalation. Contrast with STUCK-DETECT: that is per-ticket and never
  routes; this is whole-runner and self-heals **only** the runner-owned blockers (backoff/orphan
  lock), once per episode. Disable with `ORCH_LIVENESS_WATCHDOG=0`.

### Wait-State Invariant Sweep — adapter-lane parity (ABS-406)

The ABS-391 v3-backend watchdog guards wait-states by querying Postgres (`work_item × pr_mirror ×
seat_spawn`). On the **jira and mock profiles** — where daily ABS work runs — the same query is
unavailable, so silent mis-bookings stayed undetected: two real cases established the pattern
(ABS-354: ticket left `Ready for Merge` with no branch or PR ever opened; ABS-333: ticket
transitioned to `Done` after `Docs` while the implementation MR was still open).

The **wait-state invariant sweep** (`invariant_sweep` in `scripts/orchestrator.sh`) fills that gap.
It runs at the **end of every reconcile sweep**, evaluating the same ticket snapshot via three
adapter-lane channels: `$TRACKER_CMD` for status, the `story_pr_state` forge seam (`glab`) for
PR/branch evidence, and the seat lock directory for active-seat evidence.

**Rule table.** The sweep reads a shared declarative variable:

```
ORCH_INVARIANT_RULES (default, pipe-delimited: status|evidence|grace_seconds|description)

  Ready for Merge  | open-mr        | 0   | resting at the human merge gate requires an OPEN mirrored PR
  Merging          | branch-or-seat | 600 | a merging story requires a branch (PR) or an active seat
  Docs             | mr-merged      | 0   | a story in Docs requires its PR to be MERGED (merge-base gate)
```

The three rules mirror `WAIT_STATE_INVARIANTS` in `backend/packages/core/src/invariants.ts` 1:1
(status values, evidence kinds, 600 s grace, descriptions). Override by exporting `ORCH_INVARIANT_RULES`
in the same `status|evidence|grace|desc` format — one rule per line — before launching the runner.

**Violation signal.** A new violation (first occurrence in the current status episode) produces:

- An `INTENT INVARIANT-VIOLATION` line in the run.log and session stdout.
- A `kind: invariant-violation` tracker comment (actor `watchdog`) naming the ticket, the
  status, the missing evidence, and the rule description. Example body:

  > WAIT-STATE-INVARIANT: ABS-999 rests in 'Ready for Merge' but no PR mirrored for the item
  > (resting at the human merge gate requires an OPEN mirrored PR). Detection-only (ABS-406,
  > degraded mirror of the ABS-391 v3 watchdog): the runner NEVER transitions or merges here —
  > a human/TDM must correct the booking or supply the missing evidence (ADR-A-0004).

**Boundaries:**

- **Detection-only (ADR-A-0004 / AC5).** The sweep calls `tracker comment` only — never
  `tracker transition`. No auto-correction, no status write.
- **Idempotent per status episode (AC6).** A violation already recorded at or after the last
  `transition-reason` comment is not re-reported. One signal per episode, not per sweep.
- **Fail-open.** When `$FORGE_CMD` is unset the sweep returns immediately (no false-positive
  spam on unconfigured profiles, matching `done_pr_gate` / `docs_pr_gate`).
- **Grace period.** The `Merging` rule carries a 600 s grace: a just-entered story legitimately
  has no branch or seat for a few seconds after the transition; the sweep skips it until grace
  expires.

Disable globally with `ORCH_INVARIANT_SWEEP=0`.

**Relationship to ABS-391.** The two watchdogs cover the same three wait-state rules but run on
separate evidence channels: the v3 backend queries Postgres and fires a database-native event;
this sweep reads the forge seam and the lock dir, fires a tracker comment, and is wired into the
bash reconcile loop. On the jira/mock profiles only the bash sweep runs; on a v3-backend profile
the v3 watchdog is authoritative and this sweep is additive (both produce `invariant-violation`
comments, the idempotency guard deduplicates them per episode).

**Conformance tests.** `tests/orchestrator.d/ABS-406-invariant-sweep.sh` covers both sides —
sixteen assertions for all three rules: violation (ABS-354/ABS-333 replays, grace-expired
Merging) and no-violation (open MR, active seat within grace, merged MR, off-switch,
no-transition proof, idempotency).

---

## Known Limitations — Headless Spawn Write Boundaries

Live run 3 (2026-07-04, ABS-60 / PR #31) established two hard write boundaries that apply to every
headless spawn — the `--permission-mode dontAsk` invocation the default spawn seam
(`scripts/orchestrator-spawn-claude.sh`) uses. Both sit **above** the ticket/agent `permissions.allow`
list: no allow rule can grant past them. Know them before authoring an orchestrator ticket, so a
spawn is not sent at work it cannot mechanically finish.

### The `.claude/` write guard

Claude Code enforces a built-in guard on `.claude/` paths for headless spawns that sits **above**
`permissions.allow`. In LIVE-3 the guard denied **Write, Edit, and an allowlisted bash `cp`** into a
`.claude/` path alike — even inside an inert git-worktree copy of the repo, where nothing the agent
touches is the live checkout. There is no allow rule that opens it.

**Consequence.** A ticket whose deliverables live under `.claude/` (agent definitions, skills,
commands) cannot be completed by a spawned agent alone. This is a **safety property, not a defect**:
a spawned agent being unable to rewrite its own agent definition or harness config is exactly the
boundary we want. The sanctioned way through is a co-op step with a human — not a bypass:

**ABS-96 update.** The shipped harness (agent defs, skills, commands, hook config) now has its
SOURCE at `harness/claude/` — an ordinary, non-`.claude` path outside this guard's literal
match — with the live `.claude/` kept as a byte-identical copy (Phase 2b generates it
mechanically). A ticket whose deliverables are shipped-harness content should target
`harness/claude/…` directly; only edits to the **live runtime copy** at `.claude/…` itself still
hit the guard and need the staging + human-install flow below. This has not yet been
corroborated against a real headless spawn — treat "harness/claude/ is guard-free" as expected,
not proven, until a live run confirms it.

**ABS-95 supersession (ADR-A-0013 — self-hosting).** Editing the shipped harness at its
`harness/claude/**` SOURCE is now an **ordinary edit** — no per-file staging + human-install
ceremony. `adrs/agentic/ADR-A-0013-self-hosting-stable-governs-dev.md` supersedes MOST of the
ABS-63 write-boundary ceremony: agents change harness source freely (it is inert work product),
and the governor rolls forward only at **promotion = release** (`scripts/promote-release.sh`,
human-gated). The staged-file + human-install co-op below **survives only** for (a) legacy /
non-self-hosted setups that still edit a live `.claude/` as their source, and (b) any direct edit
to the live `.claude/` runtime tree — which the **drift guard now rejects mechanically**
(`tests/test-harness-parity.sh` runs `generate-governor.sh --check`; CI fails a hand-edit), so the
sanctioned path there is a promotion, not a hand-edit. The historical procedure is retained below
for exactly those two cases; it is no longer the default for harness work.

1. **Implementer pre-composes** the complete, final file at `staging/<name>` inside its worktree
   (an ordinary path the file tools can write).
2. **Implementer escalates** via `Blocked`, naming the staged path in its handoff so the human knows
   exactly what to install and from where.
3. **Human reviews** the staged file and installs it from an interactive session —
   `cp staging/<name> .claude/...` — which is where the `.claude/` guard does not apply.
4. **Human re-stages** the ticket (transitions it back onto the normal flow) so work resumes.

### Project-dir file-tool sandbox

Headless file tools cannot write **outside the project directory**, regardless of any allow rule.
Orchestrator worktrees therefore **must live inside the repo**. The proven location is
`tmp/<branch>-work` (gitignored). External sibling paths such as `../foo-work` fail — the file tools
refuse the write even when the shell would allow it.

### Ticket-authoring guidance

When authoring an orchestrator ticket:

- Name the worktree location as `tmp/<branch>-work` in the body, so the spawn works inside the
  sandbox rather than tripping the project-dir boundary.
- Shipped-harness deliverables (agent defs, skills, commands) belong under `harness/claude/…`
  (ABS-96) — the spawn can edit that path directly, no staging needed.
- When any **live** `.claude/` file is in scope (not `harness/claude/`), **pre-declare the staging
  + human-install flow** above in the ticket body (stage at `staging/<name>`, escalate `Blocked`,
  human installs, human re-stages), so the spawn escalates cleanly instead of failing mid-task.

### Observed, unconfirmed cause

In LIVE-3's spawns the **Edit** tool was denied **session-wide** — even on allowlisted, non-`.claude`
paths — while Write-new-file plus allowlisted bash worked. This is flagged as *observed, cause
unconfirmed*; a future run should corroborate it before we treat it as a fixed rule rather than a
one-run artifact.

**Evidence**: LIVE-3 (2026-07-04) — mock ticket LIVE-3 → ABS-60, PR #31.

---

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Nothing spawns even in `--live` | Still passing `--dry-run` (check the actual flag), or the kill switch (`work/.orchestrator-stop`) exists | Confirm mode; `rm work/.orchestrator-stop` if present |
| `INTENT SKIP-KILLSWITCH` on every event | Kill switch file exists | `rm $ORCH_STOP_FILE` (default `work/.orchestrator-stop`) to resume |
| `INTENT SKIP-BUDGET` + "spawn budget exhausted" notify | `ORCH_MAX_SPAWNS_PER_RUN` reached | Human reviews the notify ticket/`ORCH_NOTIFY_TICKET`; restart with an approved higher budget if warranted |
| `INTENT SKIP-LOCKED` for a ticket that isn't actually in flight | A stale lock dir under `$ORCH_STATE_DIR/locks/<ticket>` from a crashed run | Wait for `ORCH_LOCK_TTL` (default 1800s) for auto-reclaim, or `rmdir` it manually once you've confirmed no spawn is really running |
| `INTENT DEFER-CAP` never resolves | Looping run never reaches another cycle (e.g., `--once` used repeatedly without draining pending first) | Use the non-`--once` loop, or re-invoke `--once` — the pending set only lives inside one process; a fresh process relies on reconciliation, not the old pending set |
| `INTENT BLOCK-ITERATION-CAP` + ticket moved to `Blocked` | ABS-12 iteration cap reached on a bounce-capable status | Expected behavior — human reviews the `gate-results` comment and the bounce history; not a bug |
| `INTENT SPAWN-CRASH` (ticket rests in place) | A live spawn failed twice (non-zero exit, timeout, or no parseable handoff); the ticket keeps a `SPAWN-CRASH` marker and rests for the sweep to re-derive (spec §3.8) | Check the spawn seam / model provider health; a transient failure self-heals on the next sweep, a deterministic one accumulates toward `CRASH-LIMIT` |
| `INTENT CRASH-LIMIT` + ticket moved to `Needs PO Decision` | `ORCH_CRASH_LIMIT` (default 3) consecutive crashes at the same `(ticket, status)` with no successful handoff between — a deterministically crashing seat (bad prompt, oversized packet) | Expected containment, not a bug — fix the seat/packet, then the PO reviews the `decision` comment and routes the ticket back onto the pipeline |
| `INTENT RUNNER-TRANSITION` | Transition-on-handoff (ABS-132): the runner applied the handoff's declared target status itself (actor = seat role), because the seat left the ticket resting at its spawn status | Expected — this is the runner completing a parsed handoff. `ORCH_HANDOFF_TRANSITION=0` reverts to seat-only transitions |
| `INTENT SALVAGE-RESUME` in the log after a turn-cap exit | A spawn hit the turn cap (`subtype=error_max_turns`) and the runner resumed it once with a per-role-resolved cap (`salvage_max_turns()`: rte=30, all others=5 by default; override with `ORCH_SALVAGE_MAX_TURNS_<ROLE>`) and a fixed "commit + handoff + stop" prompt (ABS-175/ABS-605) | Expected recovery — not a crash. If the salvage also fails the ticket receives a `SPAWN-CRASH` marker; check `ORCH_SESSION_RESUME=1` and live mode are set if this event never appears despite frequent cap exits |
| `INTENT RESPAWN-LIMIT` + ticket moved to `Needs PO Decision` | `ORCH_RESPAWN_LIMIT` (default 2) consecutive respawns whose handoffs parsed but never moved the ticket (no declared target and the seat did not transition) — the endless-respawn loop-guard (ABS-132) | Expected containment — the PO reviews the `decision` comment; usually the seat/handoff needs a declarative `to:` target or the seat must transition itself |
| `INTENT MERGE-QUEUE-WAIT` on a `Merging` ticket, no spawn | A sibling story holds the epic's merge token (ABS-256): the runner did not spawn `rte` — the ticket rests in `Merging` until the sibling releases the token | Expected — not a bug. The holder's `bounces=N` in `MERGE-TOKEN-ACQUIRE/HOLD` lines shows how many bounces it has taken. If the holder appears stuck, check its ticket status; if the hold has been open far longer than expected, verify the holder's story is not `Done`/`Docs` (which should have released the token); `ORCH_MERGE_QUEUE=0` is the emergency escape hatch |
| `HANDOFF-MISREPORT status=<s>` in a gate-results comment | A seat claimed commits on its `commits:` line that failed existence or reachability verification (ABS-255): the handoff was refused, any implementer self-transition was undone to `Ready for Development`, and the ticket rests for a fresh implementer | Expected containment — the gate-results comment names each failing hash and which check failed. The seat must actually commit and name real hashes. Repeated mis-reports escalate via `rework_count` / the ADR-A-0018 no-move budget. `ORCH_VERIFY_COMMITS=0` disables the gate |
| `HANDOFF-CLAIM-NOHASH` advisory in a gate-results comment | A seat's handoff prose suggests a commit claim but the handoff carries no `commits:` field (ABS-255) | Non-blocking advisory in v1; the handoff was still accepted. Add `commits: <sha>` to the handoff record to give the runner a machine-readable hash to verify |
| `MARKER-MISSING status=<s>` in a gate-results comment | A seat's handoff claimed a marker-backed effect (JOIN exemption or bsa pile-empty) but the required marker is absent from the named ticket (ABS-297): the handoff was refused, any seat self-transition was undone, and the ticket rests for a fresh seat | Expected containment — the gate-results comment names the exact missing marker and its target ticket. The re-spawned seat must post the marker first, then hand off. Repeated mis-reports feed `rework_count` / the ADR-A-0018 no-move budget. `ORCH_VERIFY_MARKERS=0` disables the gate |
| Role always falls back to `be-developer` | Ticket has no `role:` frontmatter | Expected for tickets created without `--role` (mock adapter) or without the field (other adapters); set `role` on creation if a non-default implementer is needed |
| Reconciliation seems to "re-spawn" a ticket you already handled | Ticket is still sitting in the SPAWN-mapped status because nothing transitioned it out (e.g., a stub/test spawn that doesn't advance the ticket) | Not a bug in the runner — the re-read guard only protects **already-moved-on** tickets; a spawn that never advanced the ticket looks identical to one that was never dispatched. Advance the ticket status as the real subagent would. |
| Tests fail only on Linux CI, pass locally on macOS (or vice versa) | `stat -f`/`stat -c` or lock/watchdog portability edge case | The lock TTL check and watchdog are written to try both BSD and GNU `stat` forms — file an issue with the exact OS/bash version if a real divergence is found |

---

## Related Documents

- [`specs/ABS-36-orchestrator-spec.md`](../../specs/ABS-36-orchestrator-spec.md) — full design spec (event mapping, spawn mechanics, packet format, safety model, test strategy)
- [`scripts/orchestrator.sh`](../../scripts/orchestrator.sh) — the runner
- [`scripts/orchestrator-spawn-claude.sh`](../../scripts/orchestrator-spawn-claude.sh) — the default (production) spawn seam binding
- [`tests/test-orchestrator.sh`](../../tests/test-orchestrator.sh) — unit/scenario test suite
- [`tests/e2e-orchestrator-dryrun.sh`](../../tests/e2e-orchestrator-dryrun.sh) — full-lifecycle E2E dry-run scenario
- [`docs/agent-outputs/qa-validations/ABS-36-e2e-dry-run.md`](../agent-outputs/qa-validations/ABS-36-e2e-dry-run.md) — E2E gate evidence
- [`adrs/agentic/ADR-A-0009-cost-approval-gate.md`](../../adrs/agentic/ADR-A-0009-cost-approval-gate.md) — cost-approval gate ADR
- [`adrs/agentic/ADR-A-0002-fresh-subagent-execution.md`](../../adrs/agentic/ADR-A-0002-fresh-subagent-execution.md) — fresh-subagent-per-task ADR (2026-07-06 amendment: intra-task session resume, task boundary = acceptance)
- [`knowledge/orchestrator-hardening-abs-111.md`](../../knowledge/orchestrator-hardening-abs-111.md) — the ABS-111 operating model (async, resume, gates, run.log) as an OKF concept
- [`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`](../../adrs/agentic/ADR-A-0004-human-approval-boundaries.md) — human-only boundaries ADR
- [`adrs/agentic/ADR-A-0019-po-deprioritize-vs-misdump-signal.md`](../../adrs/agentic/ADR-A-0019-po-deprioritize-vs-misdump-signal.md) — escalation-resume routing signal: explicit declared-target distinguishes legit PO-deprioritize from a mis-dump; no target → resume-to-origin or halt in Blocked (ABS-204)
- [`docs/sop/PO_AGENT_SOP.md`](PO_AGENT_SOP.md) — PO-Agent acceptance/escalation flows the orchestrator's SPAWN-then-NOTIFY rows hand off into
- [`specs/ABS-69-workflow-v3-full-agent-team-spec.md`](../../specs/ABS-69-workflow-v3-full-agent-team-spec.md) — the v3 full-agent-team spec (both pipelines, seat charters, design decisions §3.1–§3.10)
- [`docs/sop/DEFINITION_OF_READY.md`](DEFINITION_OF_READY.md) — the Ticket-Review DoR checklist, coverage-mapping rule, blind-spot catalog and verdicts (spec §3.10)
- [`adrs/agentic/ADR-A-0025-per-epic-merge-token.md`](../../adrs/agentic/ADR-A-0025-per-epic-merge-token.md) — per-epic merge token decision: one merge seat per epic, token held across a bounce, narrows ADR-A-0014 §3 periodic sync-rebase to `Epic Integration` only (ABS-256)
- [`tests/test-merge-token.sh`](../../tests/test-merge-token.sh) — 36-check suite for the per-epic merge token; drives the real runner against the mock tracker (AC2/AC3, ABS-256)
- [`adrs/agentic/ADR-A-0024-handoff-commit-verification.md`](../../adrs/agentic/ADR-A-0024-handoff-commit-verification.md) — handoff commit verification: runner verifies claimed hashes before accepting a handoff, `commits:` field contract, `In Progress → Ready for Development` status-machine edge (ABS-255)
- [`tests/orchestrator.d/ABS-297-marker-duty.sh`](../../tests/orchestrator.d/ABS-297-marker-duty.sh) — 11-assertion marker-duty suite: JOIN-exempt refused without marker, bsa pile-empty refused with pending follow-up, happy path accepted, refusal comment names exact marker + target ticket (ABS-297)
- `tests/e2e-workflow-v3.sh` — the workflow's executable definition (S1–S16 bash dry-runs; the epic's exit gate, ABS-80)
