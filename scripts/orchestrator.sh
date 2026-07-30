#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Orchestrator — event-loop Coordinator (spec: specs/ABS-36-orchestrator-spec.md)
# =============================================================================
# A single foreground poll loop (bash + awk, zero-dependency like the mock
# adapter) that turns tracker status-change events into fresh-subagent spawns
# and advances the status machine. It realizes three standing invariants:
#   - Fresh subagent per task   (ADR-A-0002): clean context in, handoff out.
#   - Active tracking           (ADR-A-0006): every transition is a trigger.
#   - Adapter-only tracker access (ADR-A-0007): speaks only the nine canonical
#     operations of task-tracking.md through $TRACKER_CMD — never touches
#     work/tickets/*.md or a vendor API directly.
#
# DEFAULTS TO DRY-RUN: logs spawn INTENTS only, spawns nothing. --live routes
# intents to the spawn adapter ($ORCH_SPAWN_CMD).
#
# Usage:
#   scripts/orchestrator.sh [--dry-run|--live] [--once]
#
# Environment overrides (see spec):
#   TRACKER_CMD                 adapter command (default: scripts/mock-tracker.sh)
#   ORCH_POLL_INTERVAL          seconds between polls (default: 10; the interval-poll
#                               fallback / when events-wait is off, S4/PILOT-30)
#   ORCH_EVENTS_WAIT            1=blocking events long-poll when the backend supports
#                               it (event-driven dispatch), 0=kill switch: interval-
#                               poll only, byte-identical to pre-S4 (default: 1)
#   EVENT_WAIT_CAP_SECONDS      long-poll wait cap, one value shared with the server
#                               (ADR-A-0029 §7, default: 55)
#   ORCH_EVENTS_WAIT_BUFFER     curl --max-time buffer over the cap (default: 10)
#   ORCH_RECONCILE_EVERY_SEC    wall-clock reconcile cadence in events-wait mode
#                               (default: ORCH_RECONCILE_EVERY_N_CYCLES*interval)
#   ORCH_SPAWN_CMD              spawn seam (default: internal Claude Code binding, §3)
#   ORCH_MAX_CONCURRENT         live-spawn cap (default: 3, §5.1)
#   ORCH_PRIORITY_DISPATCH      1=allocate free slots in canonical-priority order
#                               (hotfix>high>normal>low; age ASC within a band)
#                               before the concurrency cap; 0=legacy arrival/key
#                               order (ABS-261, ABS-111 kill-switch pattern)
#   ORCH_HOTFIX_CAP_BONUS       extra concurrency slots a priority=hotfix ticket
#                               may claim over ORCH_MAX_CONCURRENT — never kills a
#                               running seat (no preemption; default: 1, ABS-261)
#   ORCH_MAX_SPAWNS_PER_RUN     per-run SOFT spawn cap (default: 50, §5.4). At the
#                               cap the run DRAINS (no new intake, in-flight work
#                               finishes) and auto-extends on progress, rather than
#                               hard-stopping (PILOT-47).
#   ORCH_MAX_SPAWNS_PER_TICKET  per-ticket spawn cap; a cyclic ticket -> Needs PO
#                               Decision while the run continues (default: 25,
#                               0=off, PILOT-47/§5.4)
#   ORCH_SPAWN_BUDGET_AUTOEXTEND  1=grow the soft cap while the run shows progress;
#                               0=drain without extension (default: 1, PILOT-47)
#   ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT  extend increment as % of the soft cap
#                               (default: 25, PILOT-47)
#   ORCH_SPAWN_BUDGET_HARD_MULTIPLE  absolute per-run ceiling = soft cap x this;
#                               reaching it fail-closes to exit 75 (default: 2,
#                               PILOT-47/§5.4)
#   ORCH_MAX_SPAWNS_PER_DAY     per-DAY spawn budget across runs via a dated
#                               ledger; 0=off (default: 200, ABS-74/§5.4)
#   ORCH_REWORK_LIMIT           cross-stage backward-transition cap since the
#                               last PO decision; at the cap the dispatch
#                               escalates to Needs PO Decision instead of
#                               spawning (default: 3, ABS-74/§3.2)
#   ORCH_CRASH_LIMIT            consecutive SPAWN-CRASH markers for one status
#                               (no intervening handoff) before escalating to
#                               Needs PO Decision (default: 3, ABS-74/§3.8)
#   ORCH_HANDOFF_TRANSITION     1=after a parsed handoff the runner applies the
#                               handoff's declared target status ITSELF via the
#                               adapter (actor = seat role, so the rework counter
#                               still counts a runner-applied bounce), idempotent
#                               when the seat already transitioned; 0=legacy
#                               (seat-only transitions) (default: 1, ABS-132)
#   ORCH_RESPAWN_LIMIT          consecutive respawns at one status that each
#                               parsed a handoff but left the status UNCHANGED
#                               (no declared target + seat did not transition)
#                               before escalating to Needs PO Decision instead of
#                               resuming endlessly (default: 2, ABS-132)
#   ORCH_FOLLOWUP_BUDGET        per-epic cap on kind:follow-up comments; the
#                               watcher escalates the (budget+1)th instead of
#                               spawning bsa (default: 5, ABS-75/§3.4, S7/S9).
#                               Runtime-overridable without a restart: an
#                               integer in $ORCH_STATE_DIR/followup-budget wins
#                               each sweep when present (ABS-298)
#   ORCH_FOLLOWUP_REPAIR_SECONDS seconds a FOLLOWUP-SPAWN marker may sit WITHOUT a
#                               matching kind:bsa-decision (and no live lock)
#                               before the watcher re-spawns the bsa for that
#                               ordinal instead of de-duping it forever; 0=off=
#                               today's behaviour (default: 300, ABS-298)
#   ORCH_RECONCILE_EVERY_N_CYCLES  reconciliation cadence (default: 10, §5.1)
#   ORCH_STALL_EPIC_SECONDS     stall rule 1: undecomposed epic age (default: 900, ABS-62)
#   ORCH_STALL_RESTING_SECONDS  stall rule 2: Backlog resting age; 0=disabled (default: 0, ABS-62)
#   ORCH_REQUIRE_START_LABEL    Backlog opt-in gate: 1=only labelled tickets are
#                               eligible, 0=disabled (default: 1, ABS-101)
#   ORCH_START_LABEL            the opt-in label (default: orchestrator-ready, ABS-101)
#   ORCH_MAX_TURNS              per-spawn turn ceiling (default: 25, §3.2;
#                               raised from 12 in ABS-150 — 12 truncated
#                               implementer seats mid commit/verify). Setting
#                               this explicitly is an operator-wide cap that
#                               overrides the implementer default below.
#   ORCH_MAX_TURNS_IMPLEMENTER  built-in turn ceiling for implementer seats
#                               (be-developer fe-developer data-engineer),
#                               default 140 (PILOT-65: 1.5x the observed peak of
#                               ~90 where they were dying; was 90). Ceiling, not
#                               target — a cap must sit ABOVE the observed
#                               maximum, not hug the median. Yields to an explicit
#                               operator ORCH_MAX_TURNS and to per-seat overrides.
#   ORCH_MAX_TURNS_DEFAULT_ROLE per-role ceiling for any non-implementer role
#                               WITHOUT a measured built-in, default 50 (PILOT-65
#                               AC2). Replaces the old silent fall to the lean
#                               global 25 — every role now resolves to an explicit,
#                               documented cap. Yields to an explicit operator
#                               ORCH_MAX_TURNS (a deliberate all-seats cap wins).
#   ORCH_MAX_TURNS_<ROLE>       per-seat turn ceiling override, role uppercased
#                               with dashes as underscores, e.g.
#                               ORCH_MAX_TURNS_ISSUE_ENRICHMENT=120 (ABS-111 A3).
#                               Known-hungry seats also carry BUILT-IN ceilings,
#                               calibrated from the measured distribution (PILOT-65):
#                               qas 180, tech-writer 80, system-architect 60,
#                               ui-ux-design/qas-design/data-provisioning-eng/
#                               security-engineer 50, rte 100 (ABS-605:
#                               ceil_to_10(observed peak 61 x1.5); died at the old
#                               60), issue-enrichment 60, po-agent 40 — see
#                               builtin_role_max_turns().
#   ORCH_MODEL_<ROLE>           per-seat model override, same naming; beats the
#                               role frontmatter via the seam's ORCH_MODEL
#                               (ABS-111 B6, e.g. ORCH_MODEL_QAS=sonnet)
#   ORCH_MODEL_LABEL_ROLES      allowlist of roles a model:-label DOWNSIZE
#                               (sonnet/haiku) may take effect for (comma/space
#                               separated). Review/judgment seats not on the list
#                               ignore a downsize label and keep their role
#                               default; a model:opus UPSIZE always applies to
#                               ALL roles. Blank after parsing -> WARN + built-in
#                               default (be-developer fe-developer data-engineer
#                               qas tech-writer). ABS-128.
#   ORCH_ASSIGNEE               default accountId assigned to a ticket at every
#                               seat spawn (ABS-126); empty = skip (graceful,
#                               no error). Never hardcode accountIds — always use
#                               this env var or ORCH_ASSIGNEE_<ROLE> (ADR-A-0010).
#   ORCH_ASSIGNEE_<ROLE>        per-seat assignee override, same naming as
#                               ORCH_MODEL_<ROLE> (e.g.
#                               ORCH_ASSIGNEE_BE_DEVELOPER=accountId). Beats
#                               ORCH_ASSIGNEE. Unset = fall back to ORCH_ASSIGNEE.
#   ORCH_ASYNC_SPAWNS           1=spawns run as background jobs so
#                               ORCH_MAX_CONCURRENT has real effect; 0=legacy
#                               synchronous one-at-a-time (default: 1, ABS-111 A1)
#   ORCH_SESSION_RESUME         1=store each spawn's session id and resume the
#                               same session on rework bounces / re-reviews /
#                               handoff repair, until the story passes
#                               acceptance (default: 1, ABS-111 A2)
#   ORCH_SALVAGE_MAX_TURNS      turn budget for the ONE salvage resume a spawn
#                               gets after it exits at the turn cap
#                               (subtype=error_max_turns): resume the same
#                               session with a fixed "commit + handoff + stop"
#                               prompt instead of discarding the work, then fall
#                               through to the normal crash path if it also
#                               fails (default: 5, ABS-175). Needs
#                               ORCH_SESSION_RESUME=1; no salvage in dry-run.
#                               STATION-AWARE (ABS-605): resolved per-role like
#                               the turn ceilings — per-seat ORCH_SALVAGE_MAX_TURNS_<ROLE>
#                               > built-in per-role (rte 30, whose hard exit is a
#                               full suite that 5 turns cannot run, ABS-453) >
#                               this default 5. See salvage_max_turns().
#   ORCH_SALVAGE_MAX_TURNS_<ROLE>  per-seat salvage budget override, role
#                               uppercased with dashes->underscores (same naming
#                               as ORCH_MAX_TURNS_<ROLE>); beats the built-in
#                               per-role value and the default (ABS-605).
#   ORCH_SESSION_POISON_GUARD   1=do NOT store a session whose spawn result
#                               carried permission denials — its transcript
#                               would keep re-reporting the blocker after the
#                               permission surface was fixed underneath it, so
#                               the next spawn starts fresh instead
#                               (default: 1, ABS-254 / ADR-A-0023 rule 3).
#                               0=legacy store-anyway behaviour.
#   ORCH_DEPENDS_GATING         1=hold Ready-for-Development/Design dispatch
#                               while a depends_on blocker is unmet — satisfied on
#                               the merge fact (Done, or head ancestor of target;
#                               PILOT-19), Done-only for a depends-strict dependent
#                               (default: 1, ABS-111 C8)
#   ORCH_BLOCKED_AUTO_RELEASE   1=the reconcile sweep auto-releases a Blocked
#                               ticket back to its recorded BLOCKED-FROM origin
#                               when all depends_on are Done (dependency-caused
#                               Blocked only; non-dependency Blocked entries —
#                               TDM-parked, escalation-parked, human-parked —
#                               rest untouched); 0=today's behaviour, no auto-
#                               release (default: 1, ABS-296).
#   ORCH_BLOCKED_RELEASE_CHURN_CAP
#                               PILOT-72: max blocked-auto-release episodes for one
#                               ticket before the sweep stops releasing and raises a
#                               single Attention-Event instead. The cause-keyed
#                               idempotency (fact fingerprint) already suppresses a
#                               Re-Block whose dependency facts are unchanged; this
#                               cap bounds the residual case where the facts DO keep
#                               changing yet the ticket keeps returning to Blocked
#                               (default: 3, PILOT-72).
#   ORCH_WORKTREE_SPAWNS        1=provision a git worktree per implementer
#                               spawn (tmp/<ticket>-work, branch <ticket>-auto)
#                               and hand it to the seam as ORCH_SPAWN_CWD
#                               (default: 1, ABS-111 C9)
#   ORCH_WORKTREE_EXTRA_ALLOW   comma-separated Claude-Code permission entries
#                               merged into the worktree's settings.local.json so
#                               seats can read/write/commit/push inside the
#                               ISOLATED tree (default: bare Bash,Write,Edit —
#                               ABS-154, reliable vs the restrictive target
#                               copy). Set empty to disable the extension.
#   ORCH_SYNC_TARGET_ALLOWLIST  1=also merge ORCH_WORKTREE_EXTRA_ALLOW into the
#                               TARGET checkout's settings.local.json at startup
#                               (live mode only, idempotent). Retro 2026-07-10:
#                               non-worktree seats (docs/PO/BSA/TDM) run in the
#                               target checkout and hit dontAsk write-denials
#                               whenever its allowlist drifted from the worktree
#                               grants. 0=old behavior (default: 1)
#   ORCH_RUN_LOG                structured timestamped TSV event log (default:
#                               <state-dir>/run.log, ABS-111 D11)
#   ORCH_RUN_ID                 explicit run-ID override; when empty and
#                               ORCH_RUN_ID_SEPARATION=1, minted per invocation
#                               (format: YYYYMMDDTHHmmss-pid-rand4, ABS-347)
#   ORCH_RUN_ID_SEPARATION      1=mint a unique run-ID per orchestrator invocation
#                               and stamp it on artifacts: RUN-START event in
#                               run.log, run-ID prefix on telemetry .seq filenames,
#                               run-ID field on spawn-ledger lines; 0=legacy
#                               single-stream behavior (default: 1, ABS-347;
#                               escape hatch per ADR-A-0010)
#   ORCH_AGENT_TIMEOUT          per-spawn watchdog seconds (default: 900, §6.1).
#                               Setting it explicitly is an operator-wide cap
#                               that overrides the built-in per-seat timeouts
#                               (qas/implementers 3600, retro 2026-07-10 — see
#                               builtin_role_timeout()).
#   ORCH_AGENT_TIMEOUT_<ROLE>   per-seat watchdog override, same naming as
#                               ORCH_MAX_TURNS_<ROLE>; beats ORCH_AGENT_TIMEOUT
#                               (ABS-157, e.g. ORCH_AGENT_TIMEOUT_QAS=1800 so a
#                               qas full-suite run is not killed mid-test).
#                               Under the default idle watchdog (below) this no
#                               longer kills directly — it FEEDS the MAX_LIFETIME
#                               default (2x); no operator launcher breaks.
#   ORCH_WATCHDOG_IDLE          ABS-225 progress-based watchdog: kill a seat on
#                               proven INACTIVITY, not hard wall-time (default 1;
#                               0 = legacy wall-time kill at the resolved
#                               ORCH_AGENT_TIMEOUT[_<ROLE>]). Kill-switch per the
#                               ABS-111 pattern.
#   ORCH_AGENT_IDLE_TIMEOUT     idle-kill threshold: no activity (no transcript
#                               write AND no live tool child) for this many
#                               seconds -> kill (default: 900). An ACTIVE seat is
#                               never idle-killed — that is MAX_LIFETIME's job.
#   ORCH_AGENT_MAX_LIFETIME     absolute lifetime cap regardless of activity
#                               (loop/abuse guard — a looping seat is "active",
#                               ABS-132/151). Empty -> derived per spawn as 2x
#                               the resolved role timeout; an explicit value is a
#                               hard operator-wide cap.
#   ORCH_WATCHDOG_POLL          seconds between idle/activity evaluations
#                               (default: 15). Liveness + MAX_LIFETIME are still
#                               checked every 1s tick; only the activity probe
#                               (process + transcript scan) is throttled.
#   ORCH_LOCK_TTL               stale-lock reclaim seconds (default: 4000, §5.2;
#                               retro 2026-07-10: must exceed the largest agent
#                               timeout or running seats get reclaimed)
#   ORCH_SEAT_RACE_GUARD        1=refuse a handoff-declared transition when a
#                               DIFFERENT, still-live seat (lock age < LOCK_TTL)
#                               owns the ticket's station (SEAT-RACE, ABS-300;
#                               default 1). 0=legacy (apply regardless of owner).
#   ORCH_PACKET_MAX_BYTES       packet soft cap (default: 32768, §4)
#   ORCH_POLICY_INJECT          on=prepend the seat role's revision-pinned effective
#                               policy as a `=== POLICY (policy_rev: <hash>) ===`
#                               block before `=== TICKET ===` when the adapter offers
#                               the `policies` op (S4/ABS-381); off=force the legacy
#                               byte-identical packet. Adapters without `policies`
#                               (mock/jira) are byte-identical regardless (default:
#                               on, ABS-382 / ABS-231 S5)
#   ORCH_DEFAULT_ROLE           implementer fallback role (default: be-developer, §2.2)
#   ORCH_DESIGN_FIRST_ROUTING   1=route a `design-first`-labelled ticket's first
#                               Ready-for-Development spawn to system-architect for
#                               proposed-ADR authoring; the architect's handoff
#                               appends `design-first-done`, so the next sweep
#                               resolves to the dev role (default: 1, ABS-213 /
#                               ADR-A-0020). =0 restores label-blind role resolution.
#   ORCH_FASTLANE_COLLAPSE      1=collapse the story pipeline for a `lane=fastlane`
#                               ticket (ABS-322): the implementer becomes a
#                               Solo-Seat (dev+scoped-tests+self-review), In Review
#                               is the single COMBINED review/test gate, and the
#                               QAS (In Test) + PO (Story Acceptance) tail folds
#                               into the merge-queue. `lane=normal` is untouched
#                               (default: 1). =0 restores the full v3 chain.
#   ORCH_FASTLANE_BUNDLE        1=bundle several eligible `lane=fastlane` tickets
#                               waiting at Ready for Development into ONE Solo-Seat
#                               run sharing ONE branch + ONE PR (ABS-324): the
#                               lexicographically-first member is the LEAD and
#                               spawns once with the whole roster in its seat_note;
#                               non-lead members fold (no separate spawn/branch/PR)
#                               and ride the lead's run. `lane=normal` never bundles
#                               (default: 1). =0 dispatches each fastlane ticket on
#                               its own (ABS-322 single-ticket collapsed chain).
#   ORCH_FASTLANE_BUNDLE_MAX    Max tickets per bundle so it stays reviewable
#                               (ABS-324 AC4); eligible tickets beyond the cap form
#                               the next bundle (default: 4).
#   ORCH_FASTLANE_EJECT         1=EJECT (auto-demote) a `lane=fastlane` ticket to
#                               the normal lane when it trips a safety trigger
#                               (ABS-325): red tests from iteration >=2, a diff
#                               budget overrun, a touched protected path, or a
#                               firing station guard. The ticket is set lane=normal,
#                               an ejection reason is recorded, and it resumes on the
#                               normal v3 pipeline at Ready for Development — never
#                               Blocked, never a human-wait (default: 1). =0 keeps a
#                               fastlane ticket on the collapsed chain regardless.
#   ORCH_FASTLANE_EJECT_ITER    Iteration from which red tests eject a fastlane
#                               ticket (default: 2 — eject once it has bounced back
#                               at least once, i.e. the tests are still red on the
#                               2nd combined-gate run).
#   ORCH_FASTLANE_DIFF_BUDGET   Max added+deleted lines across a fastlane Solo-Seat's
#                               claimed commits before it ejects (default: 400; 0
#                               disables the diff-budget trigger).
#   ORCH_FASTLANE_PROTECTED_PATHS  Space-separated case-glob patterns; a fastlane
#                               commit that touches any match ejects (default:
#                               "*/migrations/* */adapters/* *.sql .github/*" —
#                               schema/adapter/CI surfaces the epic excludes from
#                               fastlane eligibility).
#   ORCH_MERGE_QUEUE            1=serialize `Merging` per EPIC with a merge token
#                               held ACROSS a merge-bounce, so the epic tip cannot
#                               move under a story that is fixing its rebase
#                               against it (default: 1, ABS-256 / ADR-A-0025, §5.7).
#                               =0 restores the unserialized (racy) behavior.
#   ORCH_MERGE_TOPO             1=grant the merge token in depends_on TOPOLOGICAL
#                               order, not arrival/FIFO: a dependent story defers
#                               so its predecessor merges first and the dependent
#                               rebases onto the merged tip (default: 1, ABS-396).
#                               =0 restores plain FIFO token grant.
#   ORCH_STATE_DIR              runtime dir (default: <repo>/work/.orchestrator)
#   ORCH_STOP_FILE              kill-switch path (default: <repo>/work/.orchestrator-stop)
#   ORCH_NOTIFY_TICKET          ticket to receive budget/ops notifications (optional)
#   ORCH_TARGET_REPO            self-hosting work TARGET (ABS-92): when set, all
#                               work-state paths (state dir, stop file, mock
#                               ticket store) and the spawn cwd point at this dev
#                               repo while stable's scripts run. Unset = today's
#                               single-repo behavior, byte-for-byte.
#   ORCH_HARNESS_HOME           stable/harness root (ABS-92, default: <repo> of
#                               the running script). Exported so the spawn seam
#                               resolves agent defs from the harness, not the target.
#   ORCH_PARENT_STATE_ROOT      nested-instance sentinel (ABS-205). Auto-exported
#                               by every run = the state root it owns; not set by
#                               operators. A child orchestrator that INHERITS it
#                               (e.g. a worktree smoke/dry-run) re-pins its state
#                               to its own repo root instead of the parent's LIVE
#                               state, without breaking legitimate self-hosting
#                               (which starts in a clean env, no sentinel).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- ABS-92 stable-governs-dev seams (Phase 1) --------------------------------
# Two optional seams let stable's scripts (this REPO_ROOT = the harness) run
# against a separate dev repo as the work TARGET. Both unset -> single-repo mode,
# unchanged. Isolation in Phase 1 is agent-defs only (PATH_DECISION 1): spawns
# keep cwd = the target repo; no hook/CLAUDE.md redirection.
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"
ORCH_TARGET_REPO="${ORCH_TARGET_REPO:-}"
if [ -n "$ORCH_TARGET_REPO" ]; then
    # Validate the target is an existing git repo root (a .git dir/file present).
    # (die() is defined later in the file, so use plain echo/exit here.)
    [ -d "$ORCH_TARGET_REPO" ] || {
        echo "ERROR: ORCH_TARGET_REPO does not exist: $ORCH_TARGET_REPO" >&2; exit 1; }
    [ -e "$ORCH_TARGET_REPO/.git" ] || {
        echo "ERROR: ORCH_TARGET_REPO is not a git repo root (no .git): $ORCH_TARGET_REPO" >&2; exit 1; }
    # Work-state paths default UNDER the target's work/ (explicit env still wins,
    # resolved in the config block below). The mock adapter is retargeted here so
    # tickets are read/written in the target; jira-tracker.sh is remote-backed and
    # unaffected. Only set MOCK_TRACKER_TICKETS_DIR when the caller has not.
    ORCH_TARGET_WORK="$ORCH_TARGET_REPO/work"
    if [ -z "${MOCK_TRACKER_TICKETS_DIR:-}" ]; then
        export MOCK_TRACKER_TICKETS_DIR="$ORCH_TARGET_WORK/tickets"
    fi
fi
# Export both seams so the spawn seam (orchestrator-spawn-claude.sh) sees them.
export ORCH_HARNESS_HOME
export ORCH_TARGET_REPO

# --- Configuration (comment-tunable constants, not hardcoded literals) --------
TRACKER_CMD="${TRACKER_CMD:-$REPO_ROOT/scripts/mock-tracker.sh}"
# ABS-211 done-gate forge seam: an adapter-neutral command (same resolution
# shapes as $TRACKER_CMD) that reports a story's implementation-PR state via
# `$FORGE_CMD pr-state <ticket-id>` -> "STATE [REF]" (STATE in MERGED|OPEN|NONE;
# REF the optional PR identifier). It lets the done-gate (done_pr_gate) refuse a
# Done landing whose PR is not merged on the target/epic branch. DEFAULT EMPTY:
# the boilerplate ships with no forge platform, so the gate is FAIL-OPEN by
# construction (no $FORGE_CMD -> direct-to-branch placeholder case -> Done passes
# unchanged, ADR-A-0004/0005 boundaries untouched). Real deployments set it to
# their platform adapter (e.g. a `bb`/`gh` wrapper).
FORGE_CMD="${FORGE_CMD:-}"
ORCH_POLL_INTERVAL="${ORCH_POLL_INTERVAL:-10}"
ORCH_MAX_CONCURRENT="${ORCH_MAX_CONCURRENT:-3}"
ORCH_MAX_SPAWNS_PER_RUN="${ORCH_MAX_SPAWNS_PER_RUN:-50}"
# PILOT-47 progress-aware spawn budget (extends ADR-A-0009). ORCH_MAX_SPAWNS_PER_RUN
# above is now a SOFT cap: reaching it no longer hard-stops a healthy run.
#   ORCH_MAX_SPAWNS_PER_TICKET  the precise loop-breaker — one ticket that respawns
#       this many times this run is escalated to Needs PO Decision while the run
#       continues (0 disables). Default 25 leaves ample headroom over a normal
#       ~7-10-station pipeline yet catches a cyclic respawn.
#   ORCH_SPAWN_BUDGET_AUTOEXTEND  1 = while the run shows progress (Done count
#       rising), grow the soft cap in increments instead of stopping; 0 = drain at
#       the soft cap with no extension.
#   ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT  each extension adds this percent of the
#       ORIGINAL soft cap to the remaining budget.
#   ORCH_SPAWN_BUDGET_HARD_MULTIPLE  the fail-closed absolute ceiling = soft cap x
#       this multiple; auto-extend never crosses it and reaching it keeps the
#       ABS-455 exit-75 restart handshake (AC4/AC5). The per-day ledger
#       (ORCH_MAX_SPAWNS_PER_DAY) is the other hard backstop.
ORCH_MAX_SPAWNS_PER_TICKET="${ORCH_MAX_SPAWNS_PER_TICKET:-25}"
ORCH_SPAWN_BUDGET_AUTOEXTEND="${ORCH_SPAWN_BUDGET_AUTOEXTEND:-1}"
ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT="${ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT:-25}"
ORCH_SPAWN_BUDGET_HARD_MULTIPLE="${ORCH_SPAWN_BUDGET_HARD_MULTIPLE:-2}"
# ABS-455 budget-pause restart handshake: on spawn-budget exhaustion (per-run or
# per-day, ADR-A-0009) the run stops CLEANLY and exits with this DISTINCT code so a
# supervisor wrapper can tell "budget pause, restart wanted after cost review" from a
# clean stop (0) or a crash (non-zero, other). 75 = EX_TEMPFAIL ("temporary failure,
# retry later"). The runner persists a monotonic restart counter (state dir) and logs
# it on every budget-pause exit — the ADR-A-0009 review point stays auditable and the
# human cost gate is NOT auto-lifted. Set ORCH_BUDGET_PUSH=0 to suppress the operator
# push on a budget pause (the tracker NOTIFY still fires).
ORCH_BUDGET_PAUSE_EXIT_CODE="${ORCH_BUDGET_PAUSE_EXIT_CODE:-75}"
ORCH_RECONCILE_EVERY_N_CYCLES="${ORCH_RECONCILE_EVERY_N_CYCLES:-10}"
ORCH_RECONCILE_ON_STARTUP="${ORCH_RECONCILE_ON_STARTUP:-1}"
# S4/PILOT-30 Poll->Push (event-driven main loop). When the adapter+backend
# advertise the `events-wait` capability (probed once per run) the between-cycle
# `sleep $ORCH_POLL_INTERVAL` is replaced by a BLOCKING `tracker events --wait`
# long-poll: a transition on any instance dispatches in <1s instead of up to the
# poll interval, and the open request books this runner's heartbeat server-side.
#   ORCH_EVENTS_WAIT      1=use the long-poll when available (default), 0=kill
#                         switch: always interval-poll, byte-identical to pre-S4.
#   EVENT_WAIT_CAP_SECONDS  the wait cap in seconds — ONE value, ONE source shared
#                         with the server (ADR-A-0029 §7, default 55, under the 60s
#                         proxy/LB idle timeout). The runner requests this as the
#                         hold; the server re-caps. Same env var the backend reads.
#   ORCH_EVENTS_WAIT_BUFFER  seconds added to the server cap for curl --max-time so
#                         a genuinely hung connection (proxy) fails-fast into the
#                         interval fallback rather than blocking past the cap.
# With a variable (up to ~cap) cycle time, the cycle-count reconcile cadence would
# drift (5x too slow at rest, too fast under an event storm), so the sweep runs on
# WALL-CLOCK time in wait-mode: reconcile when >= ORCH_RECONCILE_EVERY_SEC elapsed
# since the last sweep. Default preserves today's ~N*interval wall-clock cadence.
ORCH_EVENTS_WAIT="${ORCH_EVENTS_WAIT:-1}"
EVENT_WAIT_CAP_SECONDS="${EVENT_WAIT_CAP_SECONDS:-55}"
ORCH_EVENTS_WAIT_BUFFER="${ORCH_EVENTS_WAIT_BUFFER:-10}"
ORCH_RECONCILE_EVERY_SEC="${ORCH_RECONCILE_EVERY_SEC:-$(( ORCH_RECONCILE_EVERY_N_CYCLES * ORCH_POLL_INTERVAL ))}"
# PILOT-42 — cadence-triggered TDM ops-sweep (time-driven, ticket-overarching).
# Every ORCH_OPS_SWEEP_INTERVAL seconds the reconcile sweep spawns ONE TDM seat
# with reason 'ops-sweep' to diagnose the recurring stuck-classes (worktree/lock/
# dep-release/NOMOVE/…). PHASE 0 = SHADOW: the seat writes a report and executes
# NO action. Guardrails (work/improvement-proposals/2026-07-25-hourly-ops-sweep-janitor.md):
#   ORCH_OPS_SWEEP_INTERVAL       seconds between sweeps; 0 = OFF => the runner is
#                                 byte-identical to legacy (ops_sweep_dispatch returns
#                                 before any side effect). Default 3600 (1h).
#   ORCH_OPS_SWEEP_MAX_PER_RUN    the sweep's OWN small per-run budget, separate from
#                                 the story/daily spawn budget — the janitor never eats
#                                 story slots.
#   ORCH_OPS_SWEEP_ROLE           the seat role dispatched for the sweep (reused, not new).
#   ORCH_OPS_SWEEP_TICKET         synthetic key for the sweep's single-flight lock,
#                                 packet filename and telemetry (no real ticket exists).
# PILOT-43 — Tier A/B activation (the shadow phase is over). The sweep seat only
# EXECUTES the tiers named here; the DEFAULT (empty) keeps Phase-0 shadow behaviour
# byte-for-byte, so a run that does not opt in is unchanged. Rollback = unset.
#   ORCH_OPS_SWEEP_TIERS          which action tiers the seat may execute:
#                                 "" (default) = Phase-0 SHADOW, report only;
#                                 "A"  = Tier A (mechanical, reversible: worktree/lock/
#                                        marker hygiene); "AB" = Tier A + Tier B
#                                        (evidence-bound tracker resolution: dep-release,
#                                        NOMOVE completion). Case-insensitive; other
#                                        letters ignored. Tier C/D never auto-activate.
#   ORCH_OPS_SWEEP_MAX_PER_CLASS  runaway guard: more than N findings of ONE class in a
#                                 single sweep => the seat ESCALATES instead of applying N
#                                 actions (a systemic defect must not be mass-"healed").
ORCH_OPS_SWEEP_INTERVAL="${ORCH_OPS_SWEEP_INTERVAL:-3600}"
ORCH_OPS_SWEEP_MAX_PER_RUN="${ORCH_OPS_SWEEP_MAX_PER_RUN:-24}"
ORCH_OPS_SWEEP_ROLE="${ORCH_OPS_SWEEP_ROLE:-tdm}"
ORCH_OPS_SWEEP_TICKET="${ORCH_OPS_SWEEP_TICKET:-ops-sweep}"
ORCH_OPS_SWEEP_TIERS="${ORCH_OPS_SWEEP_TIERS:-}"
ORCH_OPS_SWEEP_MAX_PER_CLASS="${ORCH_OPS_SWEEP_MAX_PER_CLASS:-3}"
# Stall detection (ABS-62): mechanical, bash-only rules run inside the
# reconciliation sweep. On a rule firing they raise "Needs PO Decision" (which
# the ABS-61 mapping then routes to a fresh PO-Agent spawn) — no LLM analysis.
ORCH_STALL_EPIC_SECONDS="${ORCH_STALL_EPIC_SECONDS:-900}"      # rule 1: undecomposed-epic age
ORCH_STALL_RESTING_SECONDS="${ORCH_STALL_RESTING_SECONDS:-0}"  # rule 2: Backlog resting age (0=off)
# Backlog opt-in gate (ABS-101): the orchestrator only acts on a Backlog ticket
# that carries $ORCH_START_LABEL. An unlabelled ticket rests untouched — no PO
# sweep, no stall raise. This is the fail-safe default (a forgotten label yields
# inaction, never an agent grabbing an under-specified ticket) and makes
# migration cheap (label only the few tickets you want worked, not skip-label the
# rest). Set ORCH_REQUIRE_START_LABEL=0 to disable the gate (legacy behaviour:
# every Backlog ticket is eligible) — e.g. a greenfield project where every
# backlog ticket is agent-created and enriched. NB: distinct from enrichment's
# "agent-ready" (that means groomed/executable — the OUTPUT of enrichment);
# orchestrator-ready is the human INPUT gate ("you may start, grooming included").
ORCH_REQUIRE_START_LABEL="${ORCH_REQUIRE_START_LABEL:-1}"
ORCH_START_LABEL="${ORCH_START_LABEL:-orchestrator-ready}"
# ABS-304: the Backlog PO sweep must not spawn a po-agent on a Backlog child
# whose parent epic is still IN the epic pipeline BEFORE "Stories In Flight"
# (PO Triage..Architecture Review). Those children are architect-released — the
# Backlog -> Ready for Development edge belongs to the Architecture Review seat,
# not the PO sweep — so a po-agent there can only score-and-park: a guaranteed
# HANDOFF-NOMOVE, one paid no-op per labelled child per run (ABS-279 had 9). The
# child-side of the same class epic_join_rest_complete() closed on the epic side.
# Suppress the spawn (emit SKIP-EPIC-CHILD instead). Parentless Backlog tickets
# and children of an epic at Stories In Flight or later are UNCHANGED. Set to 0
# to restore today's behaviour (the epic child IS spawned).
ORCH_BACKLOG_SKIP_EPIC_CHILDREN="${ORCH_BACKLOG_SKIP_EPIC_CHILDREN:-1}"
# ABS-308: drop a polled non-creation event whose claimed transition into `to`
# is not backed by a real recorded transition in the ticket (events-snapshot
# drift emitting phantom, oscillating from_status for a resting ticket). Set to 0
# to restore today's behaviour (every polled event is dispatched verbatim).
ORCH_PHANTOM_EVENT_GUARD="${ORCH_PHANTOM_EVENT_GUARD:-1}"
# ABS-156: was the global cap set explicitly by the operator? Captured BEFORE the
# default is applied so an explicit operator-wide ORCH_MAX_TURNS overrides the
# implementer built-in default, while the built-in 25 does not.
ORCH_MAX_TURNS_SET="${ORCH_MAX_TURNS:+1}"
ORCH_MAX_TURNS="${ORCH_MAX_TURNS:-25}"  # ABS-150: raised from 12 (ceiling, not target)
# ABS-156: implementer seats (write-heavy — build AND commit a story) need more
# room than mechanical/review seats. 25 truncated ABS-128 pre-commit; ABS-129
# needed 50. Ceiling, not target: fast/mechanical seats keep the lean 25 above.
ORCH_MAX_TURNS_IMPLEMENTER="${ORCH_MAX_TURNS_IMPLEMENTER:-140}"  # PILOT-65: 1.5x the observed peak (~90) where be/fe/data seats died at the old 90; ceiling, not target
# PILOT-65 AC2: any non-implementer role WITHOUT a measured built-in resolves to
# THIS explicit, documented cap instead of silently falling to the lean global 25
# (bsa, tdm, boilerplate-migration, self-improvement, …). 50 sits above the highest
# observed capless median (~32) with the same ~1.5x margin the measured seats get.
ORCH_MAX_TURNS_DEFAULT_ROLE="${ORCH_MAX_TURNS_DEFAULT_ROLE:-50}"
# retro 2026-07-10: was the global watchdog set explicitly by the operator?
# Captured BEFORE the default so an explicit operator-wide ORCH_AGENT_TIMEOUT
# beats the built-in per-seat timeouts, while the built-in 900 does not
# (same ABS-156 idiom as ORCH_MAX_TURNS_SET above).
ORCH_AGENT_TIMEOUT_SET="${ORCH_AGENT_TIMEOUT:+1}"
ORCH_AGENT_TIMEOUT="${ORCH_AGENT_TIMEOUT:-900}"
# ABS-225 progress-based watchdog (idle-detection). Default ON; the kill-switch
# ORCH_WATCHDOG_IDLE=0 restores the legacy hard-wall-time kill (at the resolved
# ORCH_AGENT_TIMEOUT[_<ROLE>], no activity check) — ABS-111 kill-switch pattern.
ORCH_WATCHDOG_IDLE="${ORCH_WATCHDOG_IDLE:-1}"
# Kill a seat that shows NO activity (no session-transcript write AND no live
# tool child process) for this long. Independent of total runtime — a genuinely
# active seat (e.g. a full pre-release-check) is never idle-killed.
ORCH_AGENT_IDLE_TIMEOUT="${ORCH_AGENT_IDLE_TIMEOUT:-900}"
# Absolute lifetime cap regardless of activity (loop/abuse guard, ABS-132/151).
# Empty -> derived per spawn as 2x the resolved role timeout (run_spawn_cmd), so
# existing ORCH_AGENT_TIMEOUT(_<ROLE>) knobs keep working; an explicit value is a
# hard operator-wide cap that wins.
ORCH_AGENT_MAX_LIFETIME="${ORCH_AGENT_MAX_LIFETIME:-}"
# Seconds between activity probes (process + transcript scan). Liveness and the
# MAX_LIFETIME cap are still checked on a 1s base tick; only the (heavier)
# activity evaluation is throttled to this interval.
ORCH_WATCHDOG_POLL="${ORCH_WATCHDOG_POLL:-15}"
# retro 2026-07-10: must exceed the largest built-in per-seat timeout (3600),
# else the sweep reclaims locks of legitimately running long seats.
ORCH_LOCK_TTL="${ORCH_LOCK_TTL:-4000}"
# ABS-300 — seat-race guard. Before a handoff-declared transition is applied,
# the runner checks whether the handoff's author owns the ticket's seat lock. If
# a DIFFERENT, still-live seat (lock age < ORCH_LOCK_TTL) holds it, the transition
# is refused (SEAT-RACE): the station stays where the live owner left it. A pure
# safety refusal, so default-on (like ABS-295 crash-repair); =0 restores legacy.
# Evidence: a sweep-spawned bsa follow-up hijacked the active RTE Merging seat's
# station and ABS-254 landed in `Ready for Merge` with no PR (retro 2026-07-13).
ORCH_SEAT_RACE_GUARD="${ORCH_SEAT_RACE_GUARD:-1}"
# ABS-184 — distributed whole-ticket remote claim (spec §4.3–4.4). The Tier-2
# claim layered ABOVE the Tier-1 mkdir lock (§5.2): staked as a `kind: claim`
# comment via the adapter (ADR-A-0007, ABS-182) and adjudicated by server
# comment-creation order so competing runners on separate machines pick a single
# winner. The functions ship self-contained + unit-tested here; wiring into
# dispatch is ABS-185. ORCH_INSTANCE_ID (the staking identity) is minted by
# ABS-183. Zero-dep (ADR-A-0009): settle/jitter via `sleep`, TTL via date+arith.
ORCH_CLAIM_SETTLE_MS="${ORCH_CLAIM_SETTLE_MS:-1500}"  # fixed settle wait (ms) before adjudication
ORCH_CLAIM_JITTER_MS="${ORCH_CLAIM_JITTER_MS:-1000}"  # extra random 0..N ms added to the settle wait
ORCH_CLAIM_TTL="${ORCH_CLAIM_TTL:-600}"               # claim staleness / reclaim window (seconds)
# ABS-185: gate the distributed remote claim (§5.6) in dispatch. "off" (default)
# = byte-for-byte the single-runner path (no claim staked, ADR-A-0010 regression
# guard); any other value arms the Tier-2 cross-machine claim (needs ABS-184).
ORCH_CLAIM_MODE="${ORCH_CLAIM_MODE:-off}"
# ABS-186: optional human-visibility layer. "1" AND an armed claim mode makes a
# WON claim stamp the ticket assignee (reusing ABS-126 ORCH_ASSIGNEE_<ROLE> /
# ORCH_ASSIGNEE) so the ticket visibly shows which machine holds it. COSMETIC
# ONLY — the claim comment stays the claim of record and the assignee is NEVER
# read back to decide ownership (spec §3). Default "0" = no assign call after a
# claim, single-runner path unchanged (ADR-A-0010).
ORCH_CLAIM_ASSIGN="${ORCH_CLAIM_ASSIGN:-0}"
ORCH_PACKET_MAX_BYTES="${ORCH_PACKET_MAX_BYTES:-32768}"
ORCH_DEFAULT_ROLE="${ORCH_DEFAULT_ROLE:-be-developer}"
# ABS-213 / ADR-A-0020: default-on design-first architect-first routing seam.
ORCH_DESIGN_FIRST_ROUTING="${ORCH_DESIGN_FIRST_ROUTING:-1}"
# ABS-256 / ADR-A-0025: default-on per-epic merge token (§5.7). =0 restores the
# pre-token behavior (siblings of one epic race the same epic-branch tip).
ORCH_MERGE_QUEUE="${ORCH_MERGE_QUEUE:-1}"
ORCH_MERGE_TOPO="${ORCH_MERGE_TOPO:-1}"   # ABS-396: grant merge token in depends_on topo-order (not FIFO); 0=plain FIFO
# ABS-92: work-state defaults follow ORCH_TARGET_REPO when set (an explicit env
# override still wins, since ${VAR:-default} only substitutes when VAR is unset).
# ORCH_STATE_ROOT is $REPO_ROOT in single-repo mode, the target in self-hosting.
_orch_computed_state_root="${ORCH_TARGET_REPO:-$REPO_ROOT}"
# ABS-205: nested-orchestrator state isolation. Every orchestrator EXPORTS
# ORCH_PARENT_STATE_ROOT = the state root it owns (bottom of this block). A child
# orchestrator invoked from WITHIN a parent's run (e.g. a QAS smoke/dry-run spawned
# in a git worktree that inherits the parent's exported ORCH_TARGET_REPO) therefore
# sees an INHERITED ORCH_PARENT_STATE_ROOT. That inherited sentinel is THE
# mechanical criterion separating a nested/worktree instance from a fresh operator
# self-hosting run: legitimate self-hosting sets ORCH_TARGET_REPO in a clean env and
# never carries the sentinel, so it is unaffected (the ABS-92 tests stay green).
# When the sentinel is inherited AND our own repo root differs from the parent's
# state root AND we would otherwise collide with it, we re-pin state to THIS
# instance's own repo root (the worktree) so the child cannot write into the
# parent's LIVE lock/ledger/log state. An explicit ORCH_STATE_DIR/STOP_FILE still
# wins below (${VAR:-default}).
# ABS-415: normalize a trailing slash on both operands before the seat-classification
# equality compare (${var%/}), so a trailing-slash ORCH_TARGET_REPO cannot make a
# main-checkout seat compare unequal and be misclassified as a worktree seat (which
# would defeat the ABS-393 redirect). The ORCH_STATE_ROOT assignments below keep the
# raw (un-normalized) values — only the classification compares are normalized.
if [ -n "${ORCH_PARENT_STATE_ROOT:-}" ] \
   && [ "${_orch_computed_state_root%/}" = "${ORCH_PARENT_STATE_ROOT%/}" ]; then
    if [ "${REPO_ROOT%/}" != "${ORCH_PARENT_STATE_ROOT%/}" ]; then
        # Worktree seat: our repo root is our own tree, so re-pin state there — the
        # child cannot write into the parent's LIVE lock/ledger/log state (ABS-205).
        ORCH_STATE_ROOT="$REPO_ROOT"
    else
        # ABS-393: a MAIN-CHECKOUT seat (rte/tech-writer/bsa run in the main checkout,
        # so REPO_ROOT == the parent's live state root — the ABS-205 re-pin above cannot
        # help, it would land right back ON the live dir). ORCH_STATE_ROOT stays the real
        # checkout (git commit/drift checks — git -C "$ORCH_STATE_ROOT" — still need the
        # true repo), but the DEFAULT STATE DIR is redirected to a DISPOSABLE throwaway
        # below so the seat's suite/cleanup traps rm a throwaway, never the live ledger/
        # locks/sessions/instance-id. This closes the ABS-355 gap: env-scrub covered
        # worktree seats, but a main-checkout seat's DEFAULT ${ORCH_STATE_DIR:-...} still
        # re-derived the live dir (the 2026-07-17 partial wipe). ORCH_SEAT_STATE_ROOT lets
        # a test pin a deterministic throwaway; otherwise a unique per-process temp dir.
        # ABS-415: derive the throwaway base with `mktemp -d` (atomic create, mode-700,
        # unpredictable suffix) instead of the guessable `$$-$RANDOM` interpolation — a
        # local actor cannot pre-create/symlink the path to redirect the seat's throwaway
        # writes (defense-in-depth). The ORCH_SEAT_STATE_ROOT test override still wins via
        # ${VAR:-default}, so mktemp is not even invoked when a test pins the base.
        ORCH_STATE_ROOT="$_orch_computed_state_root"
        _orch_seat_statedir_base="${ORCH_SEAT_STATE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/orch-seat-state-$$-XXXXXX")}"
    fi
else
    ORCH_STATE_ROOT="$_orch_computed_state_root"
fi
unset _orch_computed_state_root
# Publish the state root we own so any orchestrator we (transitively) spawn can
# detect it as an inherited parent and isolate its own state (see criterion above).
export ORCH_PARENT_STATE_ROOT="$ORCH_STATE_ROOT"
# ABS-393: base for the DEFAULT state paths — the real state root, unless a main-checkout
# seat redirected it to a disposable throwaway above. An explicit ORCH_STATE_DIR/STOP_FILE
# still wins (${VAR:-default}), so new_env-pinned tests are byte-for-byte unchanged.
_orch_statedir_base="${_orch_seat_statedir_base:-$ORCH_STATE_ROOT}"
unset _orch_seat_statedir_base
ORCH_STATE_DIR="${ORCH_STATE_DIR:-$_orch_statedir_base/work/.orchestrator}"
ORCH_STOP_FILE="${ORCH_STOP_FILE:-$_orch_statedir_base/work/.orchestrator-stop}"
unset _orch_statedir_base
ORCH_NOTIFY_TICKET="${ORCH_NOTIFY_TICKET:-}"
ORCH_ITERATION_GUARD="${ORCH_ITERATION_GUARD:-$SCRIPT_DIR/hooks/iteration-guard.sh}"
# ABS-116 stuck detector: consecutive sweeps a ticket may rest in an unowned
# status before the one-per-episode NOTIFY fires. 0 disables.
ORCH_STUCK_SWEEPS="${ORCH_STUCK_SWEEPS:-3}"
# ABS-451 In Progress orphan self-heal: consecutive sweeps an UNOWNED "In
# Progress" ticket (no seat lock, no in-flight spawn, no own SPAWN-CRASH marker)
# may rest before the runner DOWNGRADES it to a SPAWNABLE status ("Ready for
# Development") so a fresh seat is dispatched — instead of the ABS-116
# NOTIFY-only dead-end. Closes the resume/release-to-In-Progress trap where a
# TDM blocker-resume (or human release) parks a ticket in In Progress, a status
# no seat is re-derived for, so the runner only notified forever (ABS-417 3x/12h,
# ABS-438). This is NOT the ABS-195-rejected session-resume-spawn (which needs a
# retained session id to re-drive the SAME dead seat); it routes to a spawnable
# status so reconcile derives a FRESH seat — the objection in ABS-195 rationale
# #3 does not apply. Crash-origin orphans still go through ABS-295 CRASH-REPAIR
# (precise origin routing); the heal defers whenever a SPAWN-CRASH marker exists.
# 0 disables (restores pure ABS-116 NOTIFY-only).
ORCH_INPROGRESS_HEAL_SWEEPS="${ORCH_INPROGRESS_HEAL_SWEEPS:-3}"
# ABS-312 liveness watchdog: detects a FULL standstill — 0 live seats AND 0
# spawns in the sweep AND >=1 fenced ticket in an actionable status — that
# persists ORCH_STANDSTILL_SWEEPS consecutive sweeps. Unlike STUCK-DETECT
# (ABS-116: per-ticket, NOTIFY-only, never routes), this watches the WHOLE
# runner's aliveness and, once per standstill episode, self-heals (resets
# expired/exhausted backoffs, reclaims orphaned locks) then escalates loudly if
# still stuck. It NEVER lifts budget brakes (ADR-A-0009) or human gates — it only
# names them as blockers. Set ORCH_LIVENESS_WATCHDOG=0 to disable.
ORCH_LIVENESS_WATCHDOG="${ORCH_LIVENESS_WATCHDOG:-1}"
ORCH_STANDSTILL_SWEEPS="${ORCH_STANDSTILL_SWEEPS:-10}"
# ABS-406 wait-state-watchdog (degraded adapter-lane mirror of the ABS-391
# v3-native checker). Default ON; set ORCH_INVARIANT_SWEEP=0 to disable. The
# rule table is DECLARATIVE config, not logic — one `status|evidence|grace|desc`
# record per line, iterated by invariant_sweep. Editing this variable (or
# exporting a replacement) changes what the watchdog enforces without touching a
# query, exactly like ABS-391's WAIT_STATE_INVARIANTS array. The three shipped
# rules mirror that array 1:1 (evidence names kept identical): the two observed
# silent mis-bookings (ABS-354 `Ready for Merge` with no PR; ABS-333 `Docs`
# released before the human merge) plus the `Merging` branch/seat gate.
ORCH_INVARIANT_SWEEP="${ORCH_INVARIANT_SWEEP:-1}"
ORCH_INVARIANT_RULES="${ORCH_INVARIANT_RULES:-$(printf '%s\n' \
    'Ready for Merge|open-mr|0|resting at the human merge gate requires an OPEN mirrored PR' \
    'Merging|branch-or-seat|600|a merging story requires a branch (PR) or an active seat' \
    'Docs|mr-merged|0|a story in Docs requires its PR to be MERGED (merge-base gate)')}"
# ABS-295 crash-repair: seconds after the runner's own SPAWN-CRASH marker before
# the reconcile sweep auto-routes the orphaned In Progress ticket back to its
# origin station. 0 = off (preserves today's NOTIFY-only STUCK-DETECT behaviour).
ORCH_CRASH_REPAIR_SECONDS="${ORCH_CRASH_REPAIR_SECONDS:-300}"
# ABS-224: seats must never commit to the local main of the main checkout. Kill
# switch (ABS-111 pattern), default ON. When ON, provision_local_main_guard
# installs the pre-commit guard into the checkout's shared .git/hooks and
# check_local_main_drift warns when local main drifts ahead of the ACTIVE push
# remote (PILOT-3). =0 turns BOTH off (installer removes the guard, drift no-ops).
ORCH_PROTECT_LOCAL_MAIN="${ORCH_PROTECT_LOCAL_MAIN:-1}"
# ABS-243: HARD RULE — a seat kills ONLY processes it started, by a remembered
# PID or its own process group/session, NEVER by name/pattern. A name-pattern
# kill (`pkill -f`, `killall`, `kill $(pgrep -f …)`) matches processes outside
# the seat spawn tree and reaped the operator's LIVE orchestrator twice (session
# a33f54f8). The PreToolUse Bash guard (.claude/hooks/pre-bash-kill-guard.sh)
# enforces this for every seat; PID-scoped kills (`kill "$pid"`, `pkill -P
# "$pid"`) below and elsewhere stay valid. Kill switch (ABS-111, default ON):
# ORCH_KILL_GUARD=0 restores the legacy unguarded behavior; blocked kills are
# logged to ORCH_KILL_GUARD_LOG (ABS-66 observability).
ORCH_KILL_GUARD="${ORCH_KILL_GUARD:-1}"
# ABS-272: HARD RULE — a seat NEVER uses `git stash` in its worktree. `refs/stash`
# is ONE stack that ALL worktrees of a repo SHARE (only HEAD, refs/bisect,
# refs/worktree, refs/rewritten are per-worktree), while the runner operates seats
# CONCURRENTLY in their own worktrees — so one seat's `git stash pop` pops a
# SIBLING seat's stash and silently eats its uncommitted work (3 incidents on
# 2026-07-13: ABS-251←ABS-255, ABS-254←ABS-265). Seats improvised the stash for
# baseline comparisons; the stash-FREE recipe (throwaway `git worktree add
# --detach` on the base commit) is now codified in the common seat rules
# (harness/claude/agents/_common-rules.md §9). Two mechanical layers enforce it:
# the `Bash(git stash:*)` deny rule this runner injects into every seat worktree's
# settings.local.json (merge_deny_rules below), and the PreToolUse Bash guard
# (.claude/hooks/pre-bash-stash-guard.sh) whose refusal message carries the recipe.
# Kill switch (ABS-111, default ON): ORCH_STASH_GUARD=0 drops BOTH (no deny rule
# injected, hook allows); blocked stashes are logged to ORCH_STASH_GUARD_LOG.
ORCH_STASH_GUARD="${ORCH_STASH_GUARD:-1}"
# PILOT-11 / twin ABS-513: seat-independent merge chokepoint. The PreToolUse Bash
# guard (.claude/hooks/pre-bash-merge-guard.sh) routes EVERY seat `bb pr merge` /
# `glab mr merge` through scripts/merge-target-guard.sh before it reaches the git
# host, so a seat that skips the rte duty-step can no longer self-merge onto a
# protected branch (the MR !150 defect class). Kill switch (ABS-111, default ON):
# ORCH_MERGE_GUARD=0 restores the legacy unguarded behavior; blocked merges are
# logged to ORCH_MERGE_GUARD_LOG.
ORCH_MERGE_GUARD="${ORCH_MERGE_GUARD:-1}"
# PILOT-81: harness-release preflight. A live run spawns seats that EXECUTE the
# harness checkout's code, so that checkout must be a published release — not a
# development branch. On 2026-07-26 the governing stable checkout sat on
# epic/PILOT-58-... four commits past v2.32.0, and a whole pilot ran unpublished
# code while its report claimed "Stable: v2.32.0". The operator launcher's guard
# compared `git describe --tags` against a PREFIX ("v2.32"); the description
# `v2.32.0-4-g42dadc14` matched the prefix and passed — a prefix match does NOT
# prove HEAD is EXACTLY on a release tag with a clean tree, so it lets through the
# exact class it exists to catch. This guard (in the RUNNER, so consumer installs
# that have no launcher are covered too — a launcher is operator-only) fail-closes
# a live start unless the harness checkout is EXACTLY on an annotated tag
# (`git describe --exact-match --tags HEAD` succeeds) AND its tree is clean. The
# resolved tag+SHA is written to the run.log head either way (telemetry: what
# actually ran, not just what the launcher expected). Kill switch (ABS-111,
# default ON): ORCH_HARNESS_RELEASE_GUARD=0 restores the legacy unguarded start.
ORCH_HARNESS_RELEASE_GUARD="${ORCH_HARNESS_RELEASE_GUARD:-1}"
# Deny rules injected into each seat WORKTREE's settings.local.json (ABS-272).
# Worktree-only on purpose: the main checkout's file is the OPERATOR's own, and a
# human shell must keep full authority over its stash (same boundary as the ABS-243
# kill guard and the ABS-224 local-main guard).
ORCH_WORKTREE_DENY="${ORCH_WORKTREE_DENY:-Bash(git stash:*)}"
# Local main branch name whose drift-ahead-of-the-active-remote the reconcile
# sweep watches (AC3). The pre-commit guard's own protected set is
# ORCH_PROTECTED_BRANCHES (default "main master"), read by the hook at commit time.
ORCH_LOCAL_MAIN_BRANCH="${ORCH_LOCAL_MAIN_BRANCH:-main}"
# PILOT-3 (ABS-493): explicit override for the ACTIVE push remote the drift guard
# compares local main against. Empty (default) = resolve it from git's own push
# target (branch.<br>.pushRemote / remote.pushDefault / branch.<br>.remote via
# <br>@{push} — the remote `git push`/the git-host adapter actually uses), then
# fall back to `origin`. Set this (e.g. =gitlab) to pin the comparison remote when
# the primary host is down and its cached ref has gone stale (origin=Bitbucket
# unreachable since 2026-07-16 → phantom LOCAL-MAIN-DRIFT ahead=287 every sweep).
ORCH_MAIN_REMOTE="${ORCH_MAIN_REMOTE:-}"
# ABS-224 AC6 claim-protocol warning: minutes a ticket may sit in "Ready for
# Development" WITH an active seat lock (i.e. a seat is working but never pulled
# the ticket to In Progress) before the reconcile sweep warns. 0 disables.
# WARN-only — never an auto-transition (the status chain stays seat-led).
ORCH_CLAIM_WARN_MINUTES="${ORCH_CLAIM_WARN_MINUTES:-10}"
# Spawn seam (§3.1): prefer Devin CLI if installed, otherwise Claude Code.
# Tests override with a stub. Explicit ORCH_SPAWN_CMD always wins.
if [ -z "${ORCH_SPAWN_CMD:-}" ]; then
    if command -v devin >/dev/null 2>&1; then
        ORCH_SPAWN_CMD="$SCRIPT_DIR/orchestrator-spawn-devin.sh"
    elif command -v claude >/dev/null 2>&1; then
        ORCH_SPAWN_CMD="$SCRIPT_DIR/orchestrator-spawn-claude.sh"
    else
        # No provider on PATH — keep the Claude default for a clear error message later.
        ORCH_SPAWN_CMD="$SCRIPT_DIR/orchestrator-spawn-claude.sh"
    fi
fi
# Read-only toolset handed to the In Review spawn (ABS-57 separation-of-duties):
# the reviewer reuses the write-capable `system-architect` role but must only be
# able to review, comment, and transition — never edit the code under review. The
# runner passes this to the spawn seam as ORCH_TOOLS, overriding the role's own
# `tools:` frontmatter for that spawn only. (In Test/qas is intentionally excluded
# — qas ships without Write/Edit already and needs its tracker-comment tools.)
# ABS-123: Skill is deliberately part of the read-only review toolset — the
# code-review built-in reads, it never edits.
ORCH_REVIEW_TOOLS="${ORCH_REVIEW_TOOLS:-Read, Bash, Grep, Glob, Skill}"

LOCKS_DIR="$ORCH_STATE_DIR/locks"
PACKETS_DIR="$ORCH_STATE_DIR/packets"
# --- ABS-111 hardening seams (all default-on; set =0 to restore legacy) -------
SESSIONS_DIR="$ORCH_STATE_DIR/sessions"                   # A2: session-id store per (ticket,role,status)
ORCH_RUN_LOG="${ORCH_RUN_LOG:-$ORCH_STATE_DIR/run.log}"   # D11: timestamped structured event log (TSV)
ORCH_RUN_ID_SEPARATION="${ORCH_RUN_ID_SEPARATION:-1}"  # ABS-347: per-run artifact namespace; 0=legacy single-stream
ORCH_RUN_ID="${ORCH_RUN_ID:-}"                         # ABS-347: stable run ID, minted by init_run_id()
# ABS-337: docs-story identifier gate. Default 0 = OFF (today's behaviour, no
# gate). When 1, scripts/docs-identifier-check.sh fails a docs-only change whose
# prose cites an ORCH_* env token absent from scripts/ or a scripts/* path that
# does not exist — the factual-content gate the ABS-124 skip matrix strips off a
# docs-only story down to PO-acceptance-only (closes the ABS-303 defect class).
ORCH_DOCS_IDENTIFIER_CHECK="${ORCH_DOCS_IDENTIFIER_CHECK:-0}"
# ABS-183: persisted per-checkout runner identity (spec §4.1). Minted once, then
# reused verbatim across restarts so a runner recognizes its own claims.
ORCH_INSTANCE_ID_FILE="${ORCH_INSTANCE_ID_FILE:-$ORCH_STATE_DIR/instance-id}"
ORCH_ASYNC_SPAWNS="${ORCH_ASYNC_SPAWNS:-1}"               # A1: background spawns, real ORCH_MAX_CONCURRENT
# PILOT-26: PRIMARY seat-lifecycle emit. The runner POSTs the seat open/close
# upsert first-hand at spawn/reap (Live-Spawns producer, ABS-352 S7) — outbound
# only, non-fatal. No-op unless BACKEND_TOKEN + TRACKER_PROJECT are set. 0=off.
ORCH_SEAT_UPSERT="${ORCH_SEAT_UPSERT:-1}"
ORCH_SEAT_UPSERT_TIMEOUT="${ORCH_SEAT_UPSERT_TIMEOUT:-4}"  # curl --max-time for the seat upsert POST
ORCH_PRIORITY_DISPATCH="${ORCH_PRIORITY_DISPATCH:-1}"     # ABS-261: priority-ordered slot allocation in the sweep; 0=legacy arrival/key order
ORCH_HOTFIX_CAP_BONUS="${ORCH_HOTFIX_CAP_BONUS:-1}"       # ABS-261: extra slots a priority=hotfix may claim over the cap (no preemption)
ORCH_DEPENDS_GATING="${ORCH_DEPENDS_GATING:-1}"           # C8: depends_on gate at implementation entry
ORCH_EPIC_REVIEW_GATING="${ORCH_EPIC_REVIEW_GATING:-1}"   # ABS-518: hold pre-filled-epic children until the epic clears its review stations
ORCH_BLOCKED_AUTO_RELEASE="${ORCH_BLOCKED_AUTO_RELEASE:-1}" # ABS-296: auto-release dependency-caused Blocked on depends_on Done
ORCH_BLOCKED_RELEASE_CHURN_CAP="${ORCH_BLOCKED_RELEASE_CHURN_CAP:-3}" # PILOT-72: max release episodes per ticket before escalating instead of re-releasing
ORCH_WORKTREE_SPAWNS="${ORCH_WORKTREE_SPAWNS:-1}"         # C9: runner-provisioned worktree per implementer spawn
# PILOT-66: bound the fail-closed worktree-provisioning retry. Before this a seat
# whose `git worktree add` could not check out its branch (root cause: a
# main-checkout seat left the work branch checked out, blocking the same branch)
# was re-derived and re-attempted EVERY sweep — unbounded, alarmless, and
# budget-draining (131 INTENT-SKIP-NOWORKTREE in one pilot over ~4h). Now each
# failure is COUNTED per ticket, BACKED OFF (record_backoff, so the sweep skips it
# for free during the delay) and — after N attempts — ESCALATED to Blocked with an
# Attention-Event (notify). 0 = never escalate (count + backoff forever, legacy-ish).
ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS="${ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS:-5}"
# ABS-131/ABS-154: worktree-local permission travel. settings.local.json is
# gitignored, so it does NOT ride along with `git worktree add`; a fresh spawn
# therefore inherits none of the operator's local grants and fails closed on the
# first write (Befund 1, run ABS-126). Provisioning copies the file in and merges
# a worktree-only safe allow extension.
# ABS-154 (Befund, ABS-130-RC-Run): the earlier narrow default (scripts/**+
# harness/** Write/Edit only) still left implementer seats depending on the
# COPIED target allowlist for Bash/git-push and for edits outside those two
# trees. Headless seats (--permission-mode dontAsk) then hit INTERMITTENT Bash
# denials (the ABS-137 seat landed 1 of ~10 edits) and rte could not push (0
# PRs). The fix: grant bare Bash/Write/Edit so reliable read/write/commit/push
# never depends on the restrictive target copy. Bare Bash also covers compound
# commands, heredocs and `git push`. SAFE because these grants apply ONLY inside
# the isolated, throwaway worktree — the live loop lives in the main checkout,
# whose allowlist is never touched. Empty string disables the extension.
ORCH_WORKTREE_EXTRA_ALLOW="${ORCH_WORKTREE_EXTRA_ALLOW-Bash,Write,Edit}"
ORCH_SESSION_RESUME="${ORCH_SESSION_RESUME:-1}"           # A2: resume same session on rework/re-review/repair
ORCH_SALVAGE_MAX_TURNS="${ORCH_SALVAGE_MAX_TURNS:-5}"     # ABS-175: turn budget for the one salvage resume after a turn-cap exit
ORCH_SESSION_POISON_GUARD="${ORCH_SESSION_POISON_GUARD:-1}"  # ABS-254: never store a session whose spawn hit permission denials
# ABS-302: override the detected Claude CLI account email (tests / offline).
# When set, invalidate_sessions_on_account_switch uses this value instead of
# calling `claude auth status`. Empty string (default) = auto-detect.
ORCH_CLAUDE_ACCOUNT="${ORCH_CLAUDE_ACCOUNT:-}"
# In-flight background spawn pids (A1). Reaped lazily in live_spawn_count().
SPAWN_PIDS=""
# Tickets whose SKIP-UNLABELLED intent was already emitted this run (D12).
SKIPPED_UNLABELLED=""
# ABS-304: tickets whose SKIP-EPIC-CHILD intent was already emitted this run
# (throttled like SKIPPED_UNLABELLED — one intent per ticket per run).
SKIPPED_EPIC_CHILD=""
# PILOT-22: tickets whose SKIP-DELEGATED intent was already emitted this run
# (throttled like SKIPPED_UNLABELLED — one intent per ticket per run).
SKIPPED_DELEGATED=""
# ABS-324: non-lead fastlane bundle members whose FASTLANE-BUNDLE-FOLD intent was
# already emitted this run (throttled like SKIPPED_UNLABELLED); and the roster a
# bundle LEAD carries into its Solo-Seat seat_note (set in dispatch, read in
# do_spawn_action, reset every dispatch).
BUNDLE_FOLDED=""
FL_BUNDLE_ROSTER=""

# --- Modes --------------------------------------------------------------------
MODE="dry-run"   # dry-run (default) | live
ONCE=0           # --once: run a single poll cycle then exit (tests)

# --- Runner state (in-memory only; nothing persisted outside the tracker) -----
SPAWN_BUDGET=0          # remaining spawns this run (set in main)
CYCLE=0                 # poll-cycle counter (reconciliation cadence)
LIVE_SPAWNS=0           # live spawns in flight this cycle (§5.1 concurrency cap)
BUDGET_HALT=0           # set once the HARD spawn backstop trips (§5.4, ABS-455)
BUDGET_HALT_REASON=""    # ABS-455: human-readable cause, named in the exit line
OPS_SWEEP_COUNT=0       # PILOT-42: ops-sweep spawns this run (own budget, separate from SPAWN_BUDGET)
# PILOT-47 progress-aware spawn budget state (in-memory only).
SPAWNS_USED=0           # total spawns emitted this run (monotonic; hard backstop)
DRAIN_MODE=0            # 1 once the soft cap is reached without an auto-extend
DRAIN_COMPLETE=0        # 1 once drain settled (no in-flight work) -> clean run end
TICKET_SPAWNS=""        # per-ticket spawn tally: "[<id>|<n>]" accumulator (AC3)
DONE_AT_LAST_CHECK=-1   # Done-count watermark for progress detection (set in main)
SPAWN_BUDGET_EXTENDS=0  # count of auto-extensions this run (reporting/health)
# Pending set (cap-deferred events, §5.1): newline-separated "ticket_id<TAB>to".
PENDING=""
# Dedupe set for the current process lifetime (§1.4): "(ticket_id, to, at)".
SEEN_EVENTS=""
# Per-cycle "already dispatched (ticket|to)" guard so reconcile + poll don't
# double-act within one cycle. Reset at the top of each cycle.
DISPATCHED_CYCLE=""

# =============================================================================
# print_* helpers (match mock-tracker.sh style)
# =============================================================================
die() {
    echo "ERROR: $*" >&2
    exit 1
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

# runlog <KIND> <ticket> <role> <to> [note] — one timestamped TSV line into the
# structured run log (ABS-111 D11). Append-only, one write per line, so
# concurrent background spawns interleave safely. Never fails the caller.
runlog() {
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(timestamp)" "$1" "${2:--}" "${3:--}" "${4:--}" "${5:-}" \
        >> "$ORCH_RUN_LOG" 2>/dev/null || true
}

log() {
    # Structured, greppable runner log lines to stderr (stdout is reserved for
    # intent lines so tests can assert on them cleanly). Timestamped since
    # ABS-111 D11; mirrored into the structured run log.
    echo "orchestrator: [$(timestamp)] $*" >&2
    runlog LOG - - - "$*"
}

# intent <ACTION> <ticket> <role-or-dash> <to-status> [note]
# The structured intent log line (stdout). Tests assert on these — the stdout
# shape is FROZEN; the timestamped copy goes to the run log (D11).
intent() {
    local action="$1" ticket="$2" role="$3" to="$4" note="${5:-}"
    if [ -n "$note" ]; then
        printf 'INTENT %s ticket=%s role=%s to=%s note=%s\n' "$action" "$ticket" "$role" "$to" "$note"
    else
        printf 'INTENT %s ticket=%s role=%s to=%s\n' "$action" "$ticket" "$role" "$to"
    fi
    runlog "INTENT-$action" "$ticket" "$role" "$to" "$note"
}

# role_env <role> <suffix> — value of ORCH_<suffix>_<ROLE> (role uppercased,
# dashes to underscores), empty when unset. Powers the per-seat overrides
# ORCH_MAX_TURNS_<ROLE> (A3) and ORCH_MODEL_<ROLE> (B6), e.g.
# ORCH_MAX_TURNS_ISSUE_ENRICHMENT=120, ORCH_MODEL_QAS=sonnet.
role_env() {
    local role_up
    role_up="$(printf '%s' "$1" | tr 'a-z-' 'A-Z_')"
    eval "printf '%s' \"\${ORCH_${2}_${role_up}:-}\""
}

# is_implementer_role <role> — true for the write-heavy seats that build AND
# commit a story (ABS-156). These get the higher ORCH_MAX_TURNS_IMPLEMENTER
# default so a realistic run reaches its commit before the turn cap; mechanical
# and review/judgment seats keep the lean global ORCH_MAX_TURNS. This is the
# ticket-derived implementer family (ORCH_DEFAULT_ROLE=be-developer) — a subset
# of the broader ABS-128 model-label allowlist, which also covers the qas and
# tech-writer review/checker seats.
is_implementer_role() {
    case "$1" in
        be-developer|fe-developer|data-engineer) return 0 ;;
        *) return 1 ;;
    esac
}

# builtin_role_max_turns <role> — built-in per-seat turn ceilings, CALIBRATED
# from the measured turn distribution (PILOT-65). The prior values acted as a
# TARGET, not a brake: every measured error_max_turns abort landed exactly on the
# role's ceiling and the medians hugged it (qas median 68 / max 119 vs cap 80 —
# the cap sat BELOW the observed max; tech-writer median 53 vs cap 50; system-
# architect median 40 = cap 40). The documented rule now is
#   cap = ceil_to_10( observed_peak x 1.5 )   (observed_peak = measured max where
# known, else median), so the median sits at ~2/3 of the cap and the cap is a
# genuine emergency brake ABOVE the observed maximum:
#   qas 180 (peak 119 x1.5), tech-writer 80 (median 53), system-architect 60
#   (median 40). The four seats that previously had NO built-in and fell silently
#   to the global 25 — while their medians were 30-32 (6 aborts in Pilot 5) — now
#   carry an explicit 50 each: ui-ux-design, qas-design, data-provisioning-eng,
#   security-engineer. issue-enrichment 60 / po-agent 40 are unmeasured here and
#   keep their existing explicit values. rte is now MEASURED (ABS-605): it died
#   at subtype=error_max_turns num_turns=61 against the old cap 60, so applying
#   the same rule gives ceil_to_10(61 x1.5) = 100 — an epic integration runs a
#   sync-rebase, an etappen-suite (ABS-453), a staging deploy and a smoke, which
#   60 turns did not survive. Precedence is unchanged: per-seat
# env > explicit operator-wide ORCH_MAX_TURNS > these built-ins > implementer
# default > per-role default (ORCH_MAX_TURNS_DEFAULT_ROLE). Empty = role has no
# specific built-in and takes the implementer/per-role default (never the lean 25).
builtin_role_max_turns() {
    case "$1" in
        qas) echo 180 ;;
        tech-writer) echo 80 ;;
        system-architect) echo 60 ;;
        ui-ux-design|qas-design|data-provisioning-eng|security-engineer) echo 50 ;;
        rte) echo 100 ;;  # ABS-605: ceil_to_10(observed peak 61 x1.5); died at the old 60
        issue-enrichment) echo 60 ;;
        po-agent) echo 40 ;;
        *) echo "" ;;
    esac
}

# builtin_role_salvage_max_turns <role> — built-in per-role budget for the ONE
# turn-cap salvage resume (ABS-605). The default salvage cap (ORCH_SALVAGE_MAX_TURNS,
# 5) fits a normal station whose salvage only has to "commit what exists + write
# the handoff". The rte/epic-integration station's HARD exit criterion is a full
# suite (ABS-453) that 5 turns cannot run, so its salvage gets a larger, bounded
# budget: 30 turns — enough for one suite run + commit + handoff, still well below
# the 100-turn first cap. Empty = role has no station-specific salvage budget and
# takes the default. Resolved by salvage_max_turns() (precedence: per-seat env >
# this built-in > default).
builtin_role_salvage_max_turns() {
    case "$1" in
        rte) echo 30 ;;
        *) echo "" ;;
    esac
}

# salvage_max_turns <role> — effective turn budget for a role's salvage resume.
# Precedence (highest first): per-seat ORCH_SALVAGE_MAX_TURNS_<ROLE> env >
# built-in per-role value > the ORCH_SALVAGE_MAX_TURNS default (ABS-605).
salvage_max_turns() {
    local v
    v="$(role_env "$1" SALVAGE_MAX_TURNS)"
    [ -n "$v" ] || v="$(builtin_role_salvage_max_turns "$1")"
    [ -n "$v" ] || v="$ORCH_SALVAGE_MAX_TURNS"
    printf '%s' "$v"
}

# builtin_role_timeout <role> — built-in per-seat watchdog seconds (retro
# 2026-07-10). qas runs the full test suite (2400s killed ABS-165's qas);
# implementer seats build AND commit (2400s killed ABS-163's be-developer,
# finding 2026-07-09). Same precedence idiom as the turn ceilings: per-seat
# env > explicit operator-wide ORCH_AGENT_TIMEOUT > these built-ins > global
# default. ORCH_LOCK_TTL's default (4000) exceeds the largest value here.
builtin_role_timeout() {
    case "$1" in
        qas|be-developer|fe-developer|data-engineer) echo 3600 ;;
        *) echo "" ;;
    esac
}

# json_unescape — decode a JSON string VALUE (\n, \t, \", \\, \r) read from the
# CLI's --output-format json `result` field. Root cause of the literal "\n"
# artifacts in posted handoff comments (ABS-111 C10 finding).
json_unescape() {
    awk 'BEGIN { RS = "\x01" } {
        s = $0; out = ""; n = length(s)
        for (i = 1; i <= n; i++) {
            c = substr(s, i, 1)
            if (c == "\\" && i < n) {
                d = substr(s, i + 1, 1)
                if      (d == "n")  { out = out "\n"; i++ }
                else if (d == "t")  { out = out "\t"; i++ }
                else if (d == "\"") { out = out "\""; i++ }
                else if (d == "\\") { out = out "\\"; i++ }
                else if (d == "r")  { i++ }
                else out = out c
            } else out = out c
        }
        printf "%s", out
    }'
}

# json_escape <string> — minimal JSON string-body escaper (mirrors
# backend-shipper.sh / backend-tracker.sh; no jq dependency). Used to build the
# seat-upsert POST body (PILOT-26), where the diagnostic can carry quotes /
# backslashes / newlines from a captured stderr tail.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '%s' "$s"
}

# --- PILOT-26: PRIMARY Live-Spawns producer ----------------------------------
# The runner emits the seat open/close upsert itself, first-hand, at the moment
# it spawns a seat and reaps it — so the Mission-Control Live-Spawns panel
# reflects REAL seats (ABS-352 S7 had no production caller). Outbound POST only
# (ADR-A-0010); the log-derived heuristic lives ONLY in the shipper reconcile
# fallback. A dedicated `SEAT-SPAWN` run.log marker carries the full identity so
# that fallback can heal a missed POST 1:1.

# seat_spawn_id <ticket> <role> — deterministic id run_id:ticket:role:attempt[#seq].
# SPAWN_ATTEMPT is set by attempt_spawn (1 for the birth spawn, 2 for the retry);
# it defaults to 1 for direct callers (resume paths, unit probes).
# PILOT-78: SPAWN_SEQ is an optional per-dispatch discriminator. Ticket seats leave
# it UNSET — their run_id:ticket:role:attempt is already unique because the ticket id
# varies per seat. Ticket-LESS recurring seats (the hourly ops-sweep) reuse the SAME
# run_id:ticket:role:attempt on every dispatch of a run, so they set SPAWN_SEQ to a
# per-run monotonic count, appended as "#N", to keep each dispatch's id unique. The
# attempt counter stays its own field (run.log attempt=, JSON "attempt") — the seq
# never replaces it (PILOT-78 AC1).
seat_spawn_id() {
    printf '%s:%s:%s:%s%s' "${ORCH_RUN_ID:-norun}" "$1" "$2" "${SPAWN_ATTEMPT:-1}" "${SPAWN_SEQ:+#$SPAWN_SEQ}"
}

# emit_seat_upsert <phase> <spawn_id> <ticket> <role> <started_at> <completed_at> <exit_code> <diag> [session_id] [session_stored]
#   phase: open | close (informational; the endpoint upserts on spawn_id).
#   completed_at / exit_code / diag are "" on open (sent as JSON null).
#   PILOT-27: session_id / session_stored feed PILOT-24's fields. session_id is
#   the resumed session at OPEN (empty for a first spawn) and the spawn result's
#   own session at CLOSE; session_stored ("true"/"false", "" -> null) says whether
#   that session was persisted for resume (false when the poison guard dropped it).
# Fire-and-forget: non-fatal, bounded by --max-time, ALL output to /dev/null.
# CRITICAL: this runs inside run_spawn_cmd's command-substitution subshell, so it
# must never write to stdout (that stream is captured as the seat's handoff).
# No-op unless the backend env is configured (dry-run / offline tests stay quiet).
emit_seat_upsert() {
    [ "${ORCH_SEAT_UPSERT:-1}" = "1" ] || return 0
    [ -n "${BACKEND_TOKEN:-}" ] && [ -n "${TRACKER_PROJECT:-}" ] || return 0
    # shellcheck disable=SC2034 — `phase` (open|close) is informational: the
    # endpoint upserts on spawn_id, so we never branch on it. Kept as the first
    # positional arg so call sites read `emit_seat_upsert open ...`.
    local phase="$1" spawn_id="$2" ticket="$3" role="$4" started_at="$5" \
          completed_at="$6" exit_code="$7" diag="$8" session_id="${9:-}" session_stored="${10:-}"
    local completed_json="null" exit_json="null" diag_json="null" \
          session_id_json="null" session_stored_json="null"
    [ -n "$completed_at" ] && completed_json="\"$(json_escape "$completed_at")\""
    [ -n "$exit_code" ] && exit_json="$exit_code"
    [ -n "$diag" ] && diag_json="\"$(json_escape "$diag")\""
    [ -n "$session_id" ] && session_id_json="\"$(json_escape "$session_id")\""
    case "$session_stored" in true) session_stored_json="true" ;; false) session_stored_json="false" ;; esac
    local body
    body="$(printf '{"spawn_id":"%s","instance_id":"%s","run_id":"%s","ticket_id":"%s","role":"%s","attempt":%s,"started_at":"%s","completed_at":%s,"exit_code":%s,"diagnostic":%s,"session_id":%s,"session_stored":%s}' \
        "$(json_escape "$spawn_id")" "$(json_escape "${ORCH_INSTANCE_ID:-}")" \
        "$(json_escape "${ORCH_RUN_ID:-}")" "$(json_escape "$ticket")" \
        "$(json_escape "$role")" "${SPAWN_ATTEMPT:-1}" "$(json_escape "$started_at")" \
        "$completed_json" "$exit_json" "$diag_json" "$session_id_json" "$session_stored_json")"
    local url cfg
    url="${BACKEND_URL:-http://localhost:8420}/agent/v1/projects/$TRACKER_PROJECT/spawns"
    cfg="$(mktemp)" || return 0
    printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"
    "${BACKEND_CURL:-curl}" -sS --max-time "${ORCH_SEAT_UPSERT_TIMEOUT:-4}" --config "$cfg" \
        -o /dev/null -X POST -H "Content-Type: application/json" \
        --data-binary "$body" "$url" >/dev/null 2>&1 || true
    rm -f "$cfg" 2>/dev/null || true
}

# --- A2 session store: one file per (ticket, role, to-status) -----------------
# Format since ABS-117: line 1 = session id, line 2 = config-generation stamp.
session_file() {
    local key
    key="$(printf '%s.%s.%s' "$1" "$2" "$3" | tr ' /' '__')"
    echo "$SESSIONS_DIR/$key"
}

# --- ABS-117 config generation ------------------------------------------------
# A resumed Claude session keeps the SYSTEM PROMPT and the agent definition it
# was born with (--resume omits --agents) plus its transcript; it re-reads the
# live permission surface, because a resume is a new process (ABS-254 proved it:
# deny Bash(echo:*) -> spawn -> denied; flip to allow -> resume the SAME session
# -> the call succeeds). The original ABS-117 rationale here ("a pre-allowlist-fix
# session stayed tracker-denied on every resume") was a MISDIAGNOSIS of transcript
# poisoning; do not re-add settings.local.json to the hash on its authority.
# Stamp every stored session with a config-generation hash and refuse to resume
# across a mismatch — fresh is always allowed (ADR-A-0002). Inputs = only what a
# resume FREEZES: the runner + spawn seam (version proxies) and the resolved agent
# defs (ABS-96 resolution mirrored from orchestrator-spawn-claude.sh). See
# ADR-A-0023 for the session-baked vs spawn-fresh taxonomy.
# Per-spawn parameters (--model/--max-turns/...) are passed on resume too and
# deliberately NOT hashed. Recomputed once per SWEEP (ticket constraint): fresh
# spawns of a running runner pick up an operator's mid-run settings edit, so
# the stamp must notice it too — unchanged inputs hash identically, so the
# recompute costs nothing when nothing changed.
# ORCH_CONFIG_GENERATION overrides (tests; operator force-invalidate).
config_agents_dir() {
    if [ -n "${ORCH_AGENTS_DIR:-}" ]; then
        echo "$ORCH_AGENTS_DIR"
    elif [ -d "$ORCH_HARNESS_HOME/harness/claude/agents" ]; then
        echo "$ORCH_HARNESS_HOME/harness/claude/agents"
    elif [ -d "$ORCH_HARNESS_HOME/harness/.claude/agents" ]; then
        # Pre-v2.23.0 stable checkouts still use the dotted namespace.
        echo "$ORCH_HARNESS_HOME/harness/.claude/agents"
    else
        echo "$ORCH_HARNESS_HOME/.claude/agents"
    fi
}
compute_config_generation() {
    # Every input is optional: a missing file/dir contributes nothing instead
    # of failing the pipeline (set -o pipefail would otherwise kill the runner
    # at load when e.g. the agents dir does not exist yet).
    local f defs
    defs="$(find "$(config_agents_dir)" -name '*.md' 2>/dev/null | LC_ALL=C sort || true)"
    # retro 2026-07-10 (upheld + PROVEN by ABS-254): settings.local.json is
    # deliberately NOT hashed. The allowlist is read fresh from the settings files
    # at every spawn, resumes included — it never shapes a stored session's system
    # prompt — so an allowlist edit must not cold-start every resumable session
    # (observed live: one operator allowlist fix invalidated the whole session
    # store). Workspace trust (~/.claude.json hasTrustDialogAccepted) stays out for
    # the same reason and a stronger one: headless `claude -p` never consults it
    # (ABS-254). Only inputs baked into a session (runner code, spawn seam, agent
    # defs) belong in the generation — ADR-A-0023.
    {
        cat "$SCRIPT_DIR/orchestrator.sh" 2>/dev/null || true
        cat "$SCRIPT_DIR/orchestrator-spawn-claude.sh" 2>/dev/null || true
        for f in $defs; do cat "$f" 2>/dev/null || true; done
    } | cksum | awk '{print $1}'
}
refresh_config_generation() {
    CONFIG_GENERATION="${ORCH_CONFIG_GENERATION:-$(compute_config_generation)}"
}
refresh_config_generation   # initial value at startup; re-derived once per sweep in reconcile()

# extract_session_id <spawn-stdout> — the session_id from the CLI JSON result.
extract_session_id() {
    printf '%s' "$1" | tr '\n' ' ' \
        | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F-]\{8,\}\)".*/\1/p' | head -1
}

# resolve_model_label <ticket> — ABS-121: the model:<sonnet|opus|haiku> label
# from the ticket (sibling of the role:<name> convention, ABS-36 §2.2). Sized
# at BSA decomposition, enrichment-gate fallback for unlabelled tickets; haiku
# is trivial-only per the sizing rule in the enrichment guidance. An invalid
# value (model:gpt5) is ignored with a WARN run.log event — fallback to the
# next precedence level, never a crash.
resolve_model_label() {
    local dump lbl
    dump="$(tracker get "$1" 2>/dev/null || true)"
    lbl="$(printf '%s\n' "$dump" | sed -n 's/^labels: \[\(.*\)\]/\1/p' | head -1 \
        | tr ',' '\n' | tr -d ' ' | sed -n 's/^model:\(.*\)$/\1/p' | head -1)"
    [ -n "$lbl" ] || return 0
    case "$lbl" in
        sonnet|opus|haiku) printf '%s' "$lbl" ;;
        *) runlog WARN-MODEL-LABEL "$1" - - "invalid=$lbl ignored" ;;
    esac
    return 0
}

# --- ABS-128: role-aware model:-label downsizing ------------------------------
# The model:-label sizes IMPLEMENTATION effort, not review effort. A downsize
# (model:sonnet / model:haiku) may only take effect for mechanical
# implementer/checker seats; for review/judgment seats (system-architect,
# po-agent, bsa, security-engineer, …) it is ignored so they keep their role
# default (frontmatter / ORCH_MODEL_<ROLE>). An UPSIZE (model:opus) is never
# filtered — a hard ticket may lift ANY seat (#PLAN_UNCERTAINTY resolved: upsize
# stays role-blind). Allowlist configurable via ORCH_MODEL_LABEL_ROLES; blank
# after parsing -> WARN + built-in default, never a crash (fail-safe to shipped).
ORCH_MODEL_LABEL_ROLES_DEFAULT="be-developer fe-developer data-engineer qas tech-writer"
_MODEL_LABEL_ROLES_WARNED=0
model_label_roles() {
    local raw
    raw="$(printf '%s' "${ORCH_MODEL_LABEL_ROLES:-}" | tr ',' ' ' | xargs 2>/dev/null || true)"
    if [ -z "$raw" ]; then
        if [ -n "${ORCH_MODEL_LABEL_ROLES:-}" ] && [ "$_MODEL_LABEL_ROLES_WARNED" = 0 ]; then
            runlog WARN-MODEL-LABEL-ROLES - - - "blank ORCH_MODEL_LABEL_ROLES -> built-in default allowlist"
            _MODEL_LABEL_ROLES_WARNED=1
        fi
        raw="$ORCH_MODEL_LABEL_ROLES_DEFAULT"
    fi
    printf '%s' "$raw"
}

# model_label_applies <role> <label> — does the validated model:-label take
# effect for this seat? Upsize (opus) always; downsize (sonnet/haiku) only for an
# allowlisted mechanical seat.
model_label_applies() {
    local role="$1" lbl="$2" roles
    [ "$lbl" = "opus" ] && return 0
    roles=" $(model_label_roles) "
    case "$roles" in
        *" $role "*) return 0 ;;
        *) return 1 ;;
    esac
}

# resolve_spawn_model <ticket> <role> <to> — the model to hand the spawn seam,
# honoring precedence: ORCH_MODEL_<ROLE>/ORCH_MODEL env (always wins) >
# role-filtered ticket model:-label (ABS-121 + ABS-128) > "" (seam resolves the
# role frontmatter). Emits MODEL-LABEL (applied) / MODEL-LABEL-SKIP (downsize
# ignored for a review/judgment seat) as a side effect. Echoes the resolved
# model ("" = let the seam pick the role frontmatter default).
resolve_spawn_model() {
    local ticket="$1" role="$2" to="$3" model lbl
    model="$(role_env "$role" MODEL)"; [ -n "$model" ] || model="${ORCH_MODEL:-}"
    if [ -z "$model" ]; then
        lbl="$(resolve_model_label "$ticket")"
        if [ -n "$lbl" ]; then
            if model_label_applies "$role" "$lbl"; then
                model="$lbl"
                runlog MODEL-LABEL "$ticket" "$role" "$to" "model=$model"
            else
                runlog MODEL-LABEL-SKIP "$ticket" "$role" "$to" "downsize model:$lbl ignored (review/judgment seat keeps role default)"
            fi
        fi
    fi
    printf '%s' "$model"
}

# =============================================================================
# ABS-125 spawn telemetry — tool/MCP/skill usage per spawn (names only)
# =============================================================================
# After a spawn completes, the session transcript (the CLI's own JSONL under
# ~/.claude/projects/<cwd-slug>/<session_id>.jsonl) is parsed for tool_use
# entries: aggregated name=count into a TELEMETRY run.log line + the ordered
# call sequence into $ORCH_STATE_DIR/telemetry/<ticket>.<role>.<epoch>.seq.
# #PATH_DECISION (spec): transcript parsing over a stream-json seam rebuild —
# zero seam change; the CLI-internals dependency is mitigated by graceful
# degradation (any lookup/parse failure -> note=unavailable, never a break).
# Names/counts/order ONLY — never arguments or payloads. ORCH_TELEMETRY=0 off.
ORCH_TELEMETRY="${ORCH_TELEMETRY:-1}"
ORCH_TRANSCRIPT_DIR="${ORCH_TRANSCRIPT_DIR:-$HOME/.claude/projects}"

# telemetry_tool_sequence <transcript-file> — ordered tool_use names, one per
# line. Per tool_use BLOCK the FIRST "name" after the type marker is the tool
# name (the block emits type/id/name before input) — a greedy match would grab
# a payload key literally called "name" (real MCP inputs carry one; architect
# F1) and a single per-line match would drop parallel tool calls (F2). Only
# the tool name is recorded — a Skill call logs plain `Skill`; its skill
# sub-name lives in input and is a payload (F4).
telemetry_tool_sequence() {
    awk '{
        s = $0
        while (match(s, /"type":[[:space:]]*"tool_use"/)) {
            s = substr(s, RSTART + RLENGTH)
            if (match(s, /"name":[[:space:]]*"[^"]*"/)) {
                n = substr(s, RSTART, RLENGTH)
                sub(/^"name":[[:space:]]*"/, "", n)
                sub(/"$/, "", n)
                print n
                s = substr(s, RSTART + RLENGTH)
            }
        }
    }' "$1" 2>/dev/null || true
}

# record_spawn_telemetry <ticket> <role> <to> <spawn-stdout>
record_spawn_telemetry() {
    [ "$ORCH_TELEMETRY" = "1" ] || return 0
    local ticket="$1" role="$2" to="$3" out="$4" sid tf seq counts
    sid="$(extract_session_id "$out")"
    if [ -z "$sid" ]; then
        runlog TELEMETRY "$ticket" "$role" "$to" "unavailable (no session_id in spawn result)"
        return 0
    fi
    # find-by-UUID beats slug derivation: the CLI's cwd->slug transform is
    # undocumented (maps / AND _ to -, architect F7) — do not "optimize" this.
    # ABS-165: worktree cwds nest the project slug deeper than the old
    # -maxdepth 2 reached (~/.claude/projects/<worktree-slug>/<sid>.jsonl where
    # the slug expands every path segment), so the lookup missed every spawn.
    # -maxdepth 4 covers the real structure; on a miss the attempted path is
    # logged (not a bare "unavailable") so the failure is diagnosable.
    tf="$(find "$ORCH_TRANSCRIPT_DIR" -maxdepth 4 -type f -name "$sid.jsonl" 2>/dev/null | head -1)"
    if [ -z "$tf" ] || [ ! -f "$tf" ]; then
        runlog TELEMETRY "$ticket" "$role" "$to" "unavailable (no transcript: searched $ORCH_TRANSCRIPT_DIR for $sid.jsonl)"
        return 0
    fi
    seq="$(telemetry_tool_sequence "$tf")"
    if [ -z "$seq" ]; then
        runlog TELEMETRY "$ticket" "$role" "$to" "unavailable"
        return 0
    fi
    counts="$(printf '%s\n' "$seq" | sort | uniq -c | awk '{printf "%s%s=%s", (NR>1?" ":""), $2, $1}')"
    runlog TELEMETRY "$ticket" "$role" "$to" "$counts"
    mkdir -p "$ORCH_STATE_DIR/telemetry" 2>/dev/null || true
    printf '%s\n' "$seq" > "$ORCH_STATE_DIR/telemetry/${ORCH_RUN_ID:+${ORCH_RUN_ID}.}$(printf '%s.%s.%s' "$ticket" "$role" "$(date -u +%s)" | tr ' /' '__').seq" 2>/dev/null || true
    return 0
}

# extract_usage_note <spawn-stdout> — ABS-120/ABS-165/ABS-554: the cost/usage
# fields the CLI JSON result already carries, rendered as the SPAWN-USAGE
# run.log note. ABS-165: the bulk of real input volume lives in the cache fields
# (cache_read_input_tokens / cache_creation_input_tokens) — parsing only
# input_tokens read tokens_in=1-2 per spawn (nutzlos), so all five fields are
# surfaced.
#
# WHY THIS PARSES STRUCTURALLY (ABS-554 — read before "simplifying" back to sed):
# the session totals live at `.usage.*`, but the SAME four field names repeat
# inside `.usage.iterations[]` (the per-assistant-message usage). The old parser
# used `sed 's/.*"input_tokens"...\1/p'`, whose leading `.*` is GREEDY, so the
# match landed on the LAST occurrence in the flattened JSON — the final assistant
# message's usage, not the session sum. Measured on a real result JSON
# (PILOT-34, 91 turns): logged cache_read=177377 where the truth was 11534075
# (65x too small), tokens_in=2 vs 6335, tokens_out=390 vs 53915. Only
# total_cost_usd was correct, because it occurs exactly once.
# The pre-ABS-554 comment here claimed the greedy match "does NOT collide with
# cache_*_input_tokens" — true but irrelevant: the leading `"` does exclude the
# `_input_tokens` SUFFIX collision, and that reasoning was silently mistaken for
# proof that the whole match was safe. It said nothing about iterations[], which
# is why the defect survived two releases. Note also that JSON does not guarantee
# key order, so "take the first match instead of the last" is a heuristic, not a
# fix: the fields must be addressed by PATH.
#
# Contract unchanged and still fail-soft: missing/unparseable fields degrade to
# empty values, the line always appears, the pipeline never breaks. jq (already a
# hard dependency of this script) is the primary path; the text fallback below
# covers a missing jq and non-JSON stdout — stub spawns in the test suites print
# a plain handoff, not a result JSON.
extract_usage_note() {
    local jq_filter parsed="" flat t_in="" c_read="" c_create="" t_out="" cost=""
    # Exact paths: `.usage.*` is the session sum; `.usage.iterations[]` is ignored.
    jq_filter='[ (.usage.input_tokens? // ""), (.usage.cache_read_input_tokens? // ""),
                 (.usage.cache_creation_input_tokens? // ""), (.usage.output_tokens? // ""),
                 (.total_cost_usd? // "") ]
               | map(if type == "number" then tostring else "" end) | @tsv'
    if command -v jq >/dev/null 2>&1; then
        # 1. The whole stdout as JSON (the normal case).
        parsed="$(printf '%s' "$1" | jq -r "$jq_filter" 2>/dev/null | head -1 || true)"
        # 2. Spawn stdout may carry a preamble before the result JSON (CLI notices,
        #    wrapper output). Re-anchor at the first '{' and retry — still
        #    path-addressed, so still structural.
        if [ -z "${parsed//[[:space:]]/}" ]; then
            parsed="$(printf '%s' "$1" \
                | awk 'f{print;next} /\{/{sub(/^[^{]*/,""); print; f=1}' \
                | jq -r "$jq_filter" 2>/dev/null | head -1 || true)"
        fi
    fi
    if [ -n "${parsed//[[:space:]]/}" ]; then
        IFS=$'\t' read -r t_in c_read c_create t_out cost <<< "$parsed"
    else
        # 3. FALLBACK (no jq, or stdout that is not JSON at all). Split on JSON
        #    punctuation so every field lands on its own line, then take the FIRST
        #    occurrence in document order. Deliberately weaker than the jq path —
        #    a positional heuristic, not a path — but it prefers the session-level
        #    `usage` object over the later `iterations[]` entries instead of the
        #    old greedy LAST-match behaviour.
        flat="$(printf '%s' "$1" | tr '\n' ' ' | tr ',{}[]' '\n\n\n\n\n')"
        t_in="$(printf '%s\n' "$flat"    | sed -n 's/^[[:space:]]*"input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        c_read="$(printf '%s\n' "$flat"  | sed -n 's/^[[:space:]]*"cache_read_input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        c_create="$(printf '%s\n' "$flat"| sed -n 's/^[[:space:]]*"cache_creation_input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        t_out="$(printf '%s\n' "$flat"   | sed -n 's/^[[:space:]]*"output_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
        cost="$(printf '%s\n' "$flat"    | sed -n 's/^[[:space:]]*"total_cost_usd"[[:space:]]*:[[:space:]]*\([0-9.][0-9.]*\).*/\1/p' | head -1)"
    fi
    printf 'tokens_in=%s cache_read=%s cache_create=%s tokens_out=%s cost_usd=%s' \
        "$t_in" "$c_read" "$c_create" "$t_out" "$cost"
}

# clear_sessions <ticket> — drop all stored sessions once the story passed
# acceptance (entering Merging/Done): resume scope is "until acceptance"
# (ADR-A-0002 interpretation, ABS-111 A2). After that, always fresh.
clear_sessions() {
    rm -f "$SESSIONS_DIR/$1".* 2>/dev/null || true
}

# detect_claude_account — return the active Claude CLI account email, or empty
# if not logged in or the CLI is unavailable. ORCH_CLAUDE_ACCOUNT overrides
# the detection (operator force-set, useful in tests and offline environments).
detect_claude_account() {
    if [ -n "${ORCH_CLAUDE_ACCOUNT:-}" ]; then
        printf '%s' "$ORCH_CLAUDE_ACCOUNT"
        return
    fi
    # `claude auth status` is a local read of the cached credential file — no
    # network call. Parse the email field; fall back to empty on any failure.
    claude auth status 2>/dev/null | py '
import sys, json
try:
    d = json.load(sys.stdin)
    sys.stdout.write(d.get("email","") or "")
except Exception:
    sys.stdout.write("")
' 2>/dev/null || true
}

# invalidate_sessions_on_account_switch — ABS-302: if the CLI account changed
# since the last runner startup, wipe the entire session store and log the
# change. A stored session id belongs to the account that created it; resuming
# it under a different account would silently spawn fresh anyway (the CLI
# reports session-not-found) while burning a spawn turn. Better to detect the
# switch at startup, clear proactively, and record the event.
#
# Kill-switch: ORCH_SESSION_RESUME=0 (session resume is already off — nothing
# to guard). ORCH_CLAUDE_ACCOUNT="" in an environment with no CLI available
# also skips the check gracefully.
invalidate_sessions_on_account_switch() {
    [ "$ORCH_SESSION_RESUME" = "1" ] || return 0
    local account_file current stored
    account_file="$ORCH_STATE_DIR/.claude-account"
    current="$(detect_claude_account)"
    [ -n "$current" ] || return 0   # no account detected (offline / no CLI)
    stored="$(cat "$account_file" 2>/dev/null || true)"
    if [ -n "$stored" ] && [ "$stored" != "$current" ]; then
        runlog SESSION-ACCOUNT-CHANGED - - - "from=$stored to=$current"
        log "Claude account changed (from=$stored to=$current) — invalidating all stored sessions"
        rm -f "$SESSIONS_DIR"/* 2>/dev/null || true
    fi
    printf '%s\n' "$current" > "$account_file" 2>/dev/null || true
}

# emit_run_usage_rollup — ABS-165: at run end, aggregate every SPAWN-USAGE line
# already in run.log into RUN-USAGE summary lines, one per ticket and one per
# role (spawns + summed token/cost fields). Purely mechanical (awk over the
# TSV log); empty fields on crashed spawns degrade to 0. RUN-USAGE lines are
# themselves ignored by the aggregation, so re-emitting on a later cycle never
# double-counts. Never fails the caller.
emit_run_usage_rollup() {
    [ -f "$ORCH_RUN_LOG" ] || return 0
    local scope key note
    awk -F'\t' '
        $2 == "SPAWN-USAGE" {
            ticket = $3; role = $4; note = $6
            ti = cr = cc = to = co = 0
            n = split(note, a, /[ =]/)
            for (i = 1; i < n; i += 2) {
                k = a[i]; v = a[i + 1] + 0
                if      (k == "tokens_in")    ti = v
                else if (k == "cache_read")   cr = v
                else if (k == "cache_create") cc = v
                else if (k == "tokens_out")   to = v
                else if (k == "cost_usd")     co = v
            }
            if (ticket != "" && ticket != "-") {
                tks[ticket]++; tti[ticket]+=ti; tcr[ticket]+=cr; tcc[ticket]+=cc; tto[ticket]+=to; tco[ticket]+=co
            }
            if (role != "" && role != "-") {
                rks[role]++; rti[role]+=ti; rcr[role]+=cr; rcc[role]+=cc; rto[role]+=to; rco[role]+=co
            }
        }
        END {
            for (t in tks) printf "ticket\t%s\tspawns=%d tokens_in=%d cache_read=%d cache_create=%d tokens_out=%d cost_usd=%.4f\n", t, tks[t], tti[t], tcr[t], tcc[t], tto[t], tco[t]
            for (r in rks) printf "role\t%s\tspawns=%d tokens_in=%d cache_read=%d cache_create=%d tokens_out=%d cost_usd=%.4f\n", r, rks[r], rti[r], rcr[r], rcc[r], rto[r], rco[r]
        }
    ' "$ORCH_RUN_LOG" 2>/dev/null | while IFS=$'\t' read -r scope key note; do
        case "$scope" in
            ticket) runlog RUN-USAGE "$key" - - "$note" ;;
            role)   runlog RUN-USAGE - "$key" - "$note" ;;
        esac
    done
    return 0
}

# =============================================================================
# Adapter access (ADR-A-0007: only ever through $TRACKER_CMD)
# =============================================================================
# Resolve $TRACKER_CMD into a runnable command, accepting a script path (run via
# bash so a missing +x bit does not disable the runner) or a PATH command, with
# or without args — same shapes iteration-guard.sh accepts.
tracker() {
    # shellcheck disable=SC2206
    local words=($TRACKER_CMD)
    local cmd="${words[0]:-}"
    [ -n "$cmd" ] || die "TRACKER_CMD is empty"
    if [ -f "$cmd" ]; then
        bash "${words[@]}" "$@"
    else
        "${words[@]}" "$@"
    fi
}

# =============================================================================
# §2 Event -> action mapping (keyed on destination status `to`)
# =============================================================================
# Action classes: SPAWN | SPAWN-NOTIFY | NOTIFY | NOOP.
# map_action <to-status> -> prints "ACTION ROLE" (ROLE is "-" when N/A or when
# the implementer role is ticket-derived, resolved later in dispatch()).
map_action() {
    case "$1" in
        "Backlog")                      echo "SPAWN po-agent" ;;
        "Ready for Development")        echo "SPAWN -" ;;        # role from ticket (§2.2)
        "In Progress")                  echo "NOOP -" ;;         # implementer set it on start
        "In Review")                    echo "SPAWN system-architect" ;;  # Stage 1 reviewer (AGENTS.md)
        "In Test")                      echo "SPAWN qas" ;;
        "Ready for Human Acceptance")   echo "SPAWN-NOTIFY po-agent" ;;
        "Ready for Merge")              echo "NOOP -" ;;         # human-owned gate
        "Done")                         echo "NOOP -" ;;         # ABS-137: docs come only from the Docs station (before the human gate); no post-merge tech-writer spawn
        "Blocked")                      echo "SPAWN tdm" ;;   # blocker triage (ABS-76, spec §1.3/§3.7)
        "Needs PO Decision")            echo "SPAWN po-agent" ;;   # on-demand product decision (ABS-61)
        # --- v3 epic pipeline (ABS-71, spec §1.1) ---------------------------
        "PO Triage")                    echo "SPAWN po-agent" ;;          # scope/WSJF/guardrails
        "Grooming")                     echo "SPAWN bsa" ;;               # story drafts + flags
        "Enrichment")                   echo "SPAWN issue-enrichment" ;;  # dedup + child creation
        "Ticket Review")                echo "SPAWN qas" ;;               # DoR gate (spec §3.10)
        "Architecture Review")          echo "SPAWN system-architect" ;;  # releases stories
        "Stories In Flight")            echo "NOOP -" ;;                  # rests; JOIN advances (ABS-73)
        "Epic Integration")             echo "SPAWN rte" ;;               # staging deploy + smoke (ABS-90)
        "Ready for Epic Acceptance")    echo "NOTIFY -" ;;                # THE ready-to-test signal
        "Epic Done")                    echo "SPAWN self-improvement" ;;  # retro + skill mining
        # --- v3 story pipeline (ABS-72/ABS-83, spec §1.2). The four
        # conditional stages are SKIP-FORWARDed by the runner when the ticket
        # lacks the matching flag (ABS-84); In Review / In Test rows above are
        # unchanged (sim "Code Review" = In Review, "Implement" = Ready for
        # Development).
        "Design")                       echo "SPAWN ui-ux-design" ;;          # flag: design
        "Security Review")              echo "SPAWN security-engineer" ;;     # flag: security
        "Test Prep")                    echo "SPAWN data-provisioning-eng" ;; # flag: data
        "Design Test")                  echo "SPAWN qas-design" ;;            # flag: design
        "Story Acceptance")             echo "SPAWN po-agent" ;;              # evidence-based accept
        "Merging")                      echo "SPAWN rte" ;;                   # sequential auto-merge (ABS-89)
        "Docs")                         echo "SPAWN tech-writer" ;;           # story documentation
        *)                              echo "NOOP -" ;;
    esac
}

# =============================================================================
# §2.3 v3 SKIP-FORWARD — conditional stages are the runner's job (ABS-84)
# =============================================================================
# Flag->status mapping lives HERE only; agents carry zero routing logic
# (spec §3.3). On a transition into a conditional stage, the runner reads the
# ticket's flags via the adapter; when unflagged it re-transitions to the next
# stage itself with an audit comment (kind: skip, actor: orchestrator) — no
# spawn, no budget use.

# conditional_flag_for <status> — the flag gating this status ("" = not conditional).
conditional_flag_for() {
    case "$1" in
        "Design"|"Design Test") echo "design" ;;
        "Security Review")      echo "security" ;;
        "Test Prep")            echo "data" ;;
        *)                      echo "" ;;
    esac
}

# skip_forward_target <status> — the next story stage the runner re-transitions
# an unflagged ticket to.
skip_forward_target() {
    case "$1" in
        "Design")          echo "Ready for Development" ;;
        "Security Review") echo "Test Prep" ;;
        "Test Prep")       echo "In Test" ;;
        "Design Test")     echo "Story Acceptance" ;;
    esac
}

# =============================================================================
# ABS-124 review-gate sizing — opt-OUT skip flags (architect-approved matrix)
# =============================================================================
# The always-on gates In Review (code/architecture review) and In Test (QAS)
# become sizable per ticket via skip-review / skip-test flags, set by the BSA
# at decomposition (enrichment-gate fallback) per the skip matrix in
# specs/ABS-124-review-gate-sizing-spec.md. Fail-safe by design: no flags,
# invalid or CONTRADICTORY flags -> every gate runs. The skip targets feed the
# existing conditional SKIP-FORWARD machinery, which carries an unflagged v3
# ticket onward; PO acceptance (Story Acceptance) and the human merge gates
# are never sizable.

# gate_skip_target <status> — the v3 pass-route target of a sized gate.
gate_skip_target() {
    case "$1" in
        "In Review") echo "Security Review" ;;
        "In Test")   echo "Design Test" ;;
    esac
}

# gate_skip_blocked <dump> <flag> <ticket> <to> — 0 (true) when the skip must
# NOT run (fail-safe: all gates). Loud in run.log, never a crash.
gate_skip_blocked() {
    local dump="$1" flag="$2" ticket="$3" to="$4" f
    # An opt-in flag asserts non-trivial content — contradictory with any skip.
    for f in design security data; do
        if ticket_has_flag "$dump" "$f"; then
            runlog GATE-SKIP-CONTRADICTION "$ticket" - "$to" "skip=$flag conflicts flag=$f; all gates run"
            return 0
        fi
    done
    if [ "$flag" = "skip-test" ]; then
        # skip-test is a strict subset of skip-review cases (matrix): claiming
        # "nothing testable" while refusing "no executable code" is the
        # dangerous contradiction (architect F2).
        if ! ticket_has_flag "$dump" "skip-review"; then
            runlog GATE-SKIP-CONTRADICTION "$ticket" - "$to" "skip-test without skip-review; all gates run"
            return 0
        fi
        # v3-story-only (architect F1): the In Test skip target is the v3 tail
        # (Design Test -> Story Acceptance -> Merging). A parentless/v1 ticket
        # would be derailed PAST its human Ready-for-Merge gate — never sizable.
        if [ -z "$(fm_field "$dump" parent)" ]; then
            runlog GATE-SKIP-INELIGIBLE "$ticket" - "$to" "skip-test on parentless ticket; all gates run"
            return 0
        fi
    fi
    return 1
}

# gate_skip <ticket> <to> <flag> — audit comment + forward re-transition, no
# spawn, no budget (same mechanic as skip_forward, own wording/events:
# architect F4 — here a flag IS set, the ABS-84 "flag not set" text would lie).
gate_skip() {
    local ticket="$1" to="$2" flag="$3" target
    target="$(gate_skip_target "$to")"
    [ -n "$target" ] || return 0
    intent GATE-SKIP "$ticket" - "$to" "flag=$flag target=$target"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind skip --actor orchestrator \
        --body "Gate sized away: no '$to' seat spawned — the ticket carries the '$flag' opt-out flag (ABS-124 skip matrix; justification in the ticket body). Re-transitioning to '$target'; the conditional-stage machinery continues from there. PO acceptance still runs." \
        >/dev/null 2>&1 || log "gate-skip comment failed on $ticket"
    tracker transition "$ticket" "$target" --actor orchestrator \
        --reason "review-gate sizing: $flag (ABS-124)" \
        >/dev/null 2>&1 || log "gate-skip transition failed on $ticket"
}

# =============================================================================
# ABS-322 v3 FASTLANE — collapsed story chain for `lane=fastlane` tickets
# =============================================================================
# A `lane=fastlane` ticket (lane is a first-class field, ABS-319) folds the
# multi-seat story pipeline into: ONE Solo-Seat (dev + scoped tests + self-review)
# -> ONE combined review/test gate (In Review) -> merge-queue. The Solo-Seat and
# combined-gate marks are set at spawn time (resolve_implementer_role /
# do_spawn_action); the tail folding is done HERE, mirroring the ABS-84 / ABS-124
# skip machinery: on entry to a folded-away station the runner re-transitions the
# ticket forward over a LEGAL edge — no spawn, no budget. `lane=normal` never
# matches any target below, so the full v3 chain is byte-for-byte unchanged.
# The chain ends at the merge-queue (Merging): the merge-token, the full suite at
# epic integration, and the human merge to main are all untouched (ABS-322 AC5).

# ticket_lane <ticket-dump> — the lane field, defaulting to "normal" (ABS-319:
# a ticket with no lane field counts as normal).
ticket_lane() {
    local l; l="$(fm_field "$1" lane)"
    [ -n "$l" ] && printf '%s\n' "$l" || printf 'normal\n'
}

# fastlane_collapse_target <status> — for a fastlane ticket, the forward station
# the runner folds this one into ("" = not folded away). In Test (QAS) folds into
# the In Review combined gate; Story Acceptance (PO) folds into the merge-queue
# (async PO acceptance is ABS-323). Both targets are legal forward edges in
# statuses.yaml (In Test -> Design Test -> Story Acceptance -> Merging), so the
# re-transition is never rejected.
fastlane_collapse_target() {
    case "$1" in
        "In Test")          echo "Design Test" ;;
        "Story Acceptance") echo "Merging" ;;
    esac
}

# fastlane_skip <ticket> <to> — audit comment + forward re-transition folding a
# tail station into the collapsed fastlane chain (same mechanic as gate_skip:
# dry-run logs the intent only; live writes the comment + transition).
fastlane_skip() {
    local ticket="$1" to="$2" target
    target="$(fastlane_collapse_target "$to")"
    [ -n "$target" ] || return 0
    intent FASTLANE-COLLAPSE "$ticket" - "$to" "target=$target"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind skip --actor orchestrator \
        --body "Fastlane collapse (ABS-322): no '$to' seat spawned — this lane=fastlane ticket's review+tests run as ONE combined gate at In Review, and PO acceptance is handled by the async daily batch (ABS-323). Re-transitioning to '$target'; the collapsed chain ends at the merge-queue." \
        >/dev/null 2>&1 || log "fastlane-skip comment failed on $ticket"
    tracker transition "$ticket" "$target" --actor orchestrator \
        --reason "fastlane collapse: fold '$to' into combined gate/merge-queue (ABS-322)" \
        >/dev/null 2>&1 || log "fastlane-skip transition failed on $ticket"
}

# --- ABS-324 fastlane bundling -------------------------------------------------
# Several eligible lane=fastlane tickets waiting at "Ready for Development" share
# ONE Solo-Seat run, ONE branch, and ONE PR — reproducing natively the operator
# batch that shipped 6-9 tickets in hours (ABS-286..294, ABS-304..312). The
# candidate pool is chunked into deterministic, capped bundles; the
# lexicographically-first member of a chunk is the LEAD. The lead spawns once
# with the whole roster in its seat_note (so the Solo-Seat commits each ticket
# atomically as [ABS-XXX] on the shared branch and opens ONE PR referencing every
# id); every non-lead member folds (no separate spawn/branch/PR). The bundle
# still ends at the merge-queue — no self-merge, no merge token (guardrail
# cluster 5). Built on the ABS-322 collapsed chain (each bundled ticket is itself
# a fastlane Solo-Seat ticket).

# fastlane_bundle_eligible <ticket-dump> — 0 (true) when a ticket may join a
# bundle: lane=fastlane, none of the heavy flags (design/data/security) that
# force the full chain, and NO depends_on (an eligible fastlane ticket is
# standalone, so a bundle never bakes in an unmet prerequisite). Mirrors the
# epic's eligibility intent (diff-surface only; no schema/security; no deps).
fastlane_bundle_eligible() {
    local dump="$1" deps
    [ "$(ticket_lane "$dump")" = "fastlane" ] || return 1
    if ticket_has_flag "$dump" design;   then return 1; fi
    if ticket_has_flag "$dump" data;     then return 1; fi
    if ticket_has_flag "$dump" security; then return 1; fi
    deps="$(printf '%s\n' "$dump" | sed -n 's/^depends_on: \[\(.*\)\]/\1/p' | head -1 | tr -d ' ')"
    [ -z "$deps" ] || return 1
    return 0
}

# fastlane_bundle_roster <ticket> — the ordered, capped set of tickets that share
# ONE Solo-Seat run / branch / PR with <ticket> (AC1). The candidate pool is every
# lane=fastlane, bundle-eligible ticket waiting at "Ready for Development" under
# the SAME parent (adapter-filtered), sorted lexicographically and chunked into
# groups of $ORCH_FASTLANE_BUNDLE_MAX (default 4, AC4). Emits the chunk that
# CONTAINS <ticket>, one id per line — so every member of a chunk computes the
# IDENTICAL roster and the SAME lead (first id), independent of dispatch order. An
# ineligible ticket, or one with no eligible peer, yields just itself (no bundle).
fastlane_bundle_roster() {
    local self="$1" dump parent cap ids id cand_dump all
    dump="$(tracker get "$self" 2>/dev/null || true)"
    if ! fastlane_bundle_eligible "$dump"; then printf '%s\n' "$self"; return 0; fi
    parent="$(fm_field "$dump" parent)"
    cap="${ORCH_FASTLANE_BUNDLE_MAX:-4}"
    case "$cap" in ''|*[!0-9]*) cap=4 ;; esac
    [ "$cap" -ge 1 ] || cap=1
    ids="$(tracker search --status "Ready for Development" --lane fastlane 2>/dev/null | cut -f1 || true)"
    all="$({
        printf '%s\n' "$self"
        for id in $ids; do
            [ "$id" = "$self" ] && continue
            cand_dump="$(tracker get "$id" 2>/dev/null || true)"
            [ "$(fm_field "$cand_dump" parent)" = "$parent" ] || continue
            fastlane_bundle_eligible "$cand_dump" || continue
            printf '%s\n' "$id"
        done
    } | LC_ALL=C sort -u)"
    printf '%s\n' "$all" | awk -v self="$self" -v cap="$cap" '
        { row[NR] = $0 }
        END {
            pos = 0
            for (i = 1; i <= NR; i++) if (row[i] == self) { pos = i; break }
            if (pos == 0) { print self; exit }
            start = int((pos - 1) / cap) * cap + 1
            end = start + cap - 1; if (end > NR) end = NR
            for (i = start; i <= end; i++) print row[i]
        }'
}

# fastlane_bundle_fold <member> <lead> — audit + intent for a NON-lead bundle
# member at "Ready for Development": no separate spawn/branch/PR is created here;
# the member's work is committed atomically ([<member>]) inside the lead's shared
# Solo-Seat run. Rests reconcilably at Ready for Development (the lead's seat
# transitions it forward once it starts); a later sweep re-derives the fold if the
# lead has moved on (then the member may itself become a lead). Dry-run logs the
# intent only; live also writes the membership comment.
fastlane_bundle_fold() {
    local member="$1" lead="$2"
    intent FASTLANE-BUNDLE-FOLD "$member" - "Ready for Development" "lead=$lead"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$member" --kind skip --actor orchestrator \
        --body "Fastlane bundle (ABS-324): folded into the shared Solo-Seat run led by $lead — ONE branch ($lead-auto), ONE PR referencing the whole bundle. This ticket's changes are committed atomically ([$member]) in that run; no separate seat/branch/PR spawns here. The combined gate attributes pass/fail per ticket, and the bundle still ends at the merge-queue (no self-merge)." \
        >/dev/null 2>&1 || log "bundle-fold comment failed on $member"
    return 0
}

# --- ABS-325 fastlane EJECTION (Auswurf statt Parkung) -------------------------
# When a `lane=fastlane` ticket trips a safety trigger, the runner does NOT park
# it (never Blocked, never a human-wait): it DEMOTES the ticket to the normal
# lane, records an ejection reason, and resumes it on the normal v3 pipeline at
# `Ready for Development` — the canonical impl-fix re-entry (ADR-A-0002: a fresh
# implementer, a legal backward edge from every chain station, statuses.yaml).
# Under lane=normal the full chain (separate QAS, review, PO acceptance, epic
# integration full-suite, merge-token, human merge) applies — ejection bypasses
# NO gate (guardrail cluster 5). Removes the recurring stuck-state class the
# 2026-07-13 retro flagged. Kill-switch ORCH_FASTLANE_EJECT=0.
ORCH_FASTLANE_EJECT="${ORCH_FASTLANE_EJECT:-1}"
ORCH_FASTLANE_EJECT_ITER="${ORCH_FASTLANE_EJECT_ITER:-2}"
ORCH_FASTLANE_DIFF_BUDGET="${ORCH_FASTLANE_DIFF_BUDGET:-400}"
ORCH_FASTLANE_PROTECTED_PATHS="${ORCH_FASTLANE_PROTECTED_PATHS:-*/migrations/* */adapters/* *.sql .github/*}"

# fastlane_resume_stage <status> — the normal-lane station a fastlane ticket
# resumes at after ejection. "" = already at/before the dev re-entry (just flip
# the lane, no transition); otherwise Ready for Development, the ONE impl-fix
# bounce target every chain station has a legal backward edge to (ADR-A-0002 /
# ABS-284). Never Blocked, never a human-wait.
fastlane_resume_stage() {
    case "$1" in
        "Backlog"|"Ready for Development") echo "" ;;
        *) echo "Ready for Development" ;;
    esac
}

# fastlane_eject <ticket> <trigger> <detail> — demote a fastlane ticket to the
# normal lane and resume it (§Goal). Emits INTENT FASTLANE-EJECT (dry-run stops
# here, like fastlane_skip); live: set lane=normal, record the ejection reason
# comment (AC5), and re-transition to the resume stage over a legal edge. The
# resume target is NEVER Blocked and NEVER a human-wait station.
fastlane_eject() {
    local ticket="$1" trigger="$2" detail="$3" cur resume
    cur="$(ticket_status "$ticket")"
    resume="$(fastlane_resume_stage "$cur")"
    intent FASTLANE-EJECT "$ticket" - "$cur" "trigger=$trigger detail=$detail resume=${resume:-$cur}"
    [ "$MODE" = "live" ] || return 0
    tracker update "$ticket" lane normal >/dev/null 2>&1 \
        || log "fastlane-eject lane update failed on $ticket"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "FASTLANE-EJECT trigger=$trigger ($detail): this lane=fastlane ticket tripped a safety trigger, so it is DEMOTED to the normal lane and resumed on the full v3 pipeline${resume:+ at '$resume'} — never Blocked, never a human-wait (ABS-325, Auswurf statt Parkung; retro 2026-07-13). The normal lane retains every standard gate (QAS, review, PO acceptance, epic-integration full-suite, merge-token, human merge); ejection bypasses none of them." \
        >/dev/null 2>&1 || log "fastlane-eject comment failed on $ticket"
    if [ -n "$resume" ] && [ "$resume" != "$cur" ]; then
        tracker transition "$ticket" "$resume" --actor orchestrator \
            --reason "fastlane ejection ($trigger): demote to normal lane, resume at $resume (ABS-325)" \
            >/dev/null 2>&1 || log "fastlane-eject transition failed on $ticket"
    fi
}

# fastlane_diff_offense <ticket-dump> — inspect the commit hashes the ticket's
# handoffs CLAIM (the same `commits:` field the ABS-255 verifier reads) and print
# the FIRST offense, or nothing. "protected-path:<path>" when a touched file
# matches ORCH_FASTLANE_PROTECTED_PATHS (checked first — a schema/CI touch ejects
# regardless of size); "diff-budget:<total>/<budget>" when added+deleted lines
# exceed ORCH_FASTLANE_DIFF_BUDGET. Shells git against $ORCH_STATE_ROOT (git is
# not the tracker), fail-open like commit_verify_failures: no git / no repo / no
# claimed hash prints nothing.
fastlane_diff_offense() {
    local dump="$1" shas sha total=0 add del path pat budget protected
    [ "$ORCH_FASTLANE_EJECT" = "1" ] || return 0
    command -v git >/dev/null 2>&1 || return 0
    git -C "$ORCH_STATE_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
    shas="$(handoff_commits "$dump")"
    [ -n "$shas" ] || return 0
    protected="$ORCH_FASTLANE_PROTECTED_PATHS"
    budget="$ORCH_FASTLANE_DIFF_BUDGET"; case "$budget" in ''|*[!0-9]*) budget=0 ;; esac
    while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        git -C "$ORCH_STATE_ROOT" cat-file -e "${sha}^{commit}" 2>/dev/null || continue
        while IFS=$'\t' read -r add del path; do
            [ -n "$path" ] || continue
            for pat in $protected; do
                # shellcheck disable=SC2254
                case "$path" in $pat) printf 'protected-path:%s\n' "$path"; return 0 ;; esac
            done
            case "$add" in ''|*[!0-9]*) add=0 ;; esac   # binary diffs report "-"
            case "$del" in ''|*[!0-9]*) del=0 ;; esac
            total=$((total + add + del))
        done <<EOF
$(git -C "$ORCH_STATE_ROOT" show --numstat --format= "$sha" 2>/dev/null)
EOF
    done <<EOF
$shas
EOF
    if [ "$budget" -gt 0 ] && [ "$total" -gt "$budget" ]; then
        printf 'diff-budget:%s/%s\n' "$total" "$budget"
    fi
    return 0
}

# fastlane_eject_gate <ticket> <to> — 0 (EJECTED) when a `lane=fastlane` ticket at
# a chain station tripped a safety trigger and was demoted; 1 otherwise. Checks
# cheapest-first from the ticket dump alone (so it is visible in a dry-run trace):
# (d) a station guard would fire (illegal forward station skip); (a) red tests
# from iteration >= ORCH_FASTLANE_EJECT_ITER (>=1 backward bounce already
# recorded); then (b)/(c) the handoff-commit diff budget / protected path. The
# call site is placed BEFORE the ABS-322 collapse / ABS-324 bundle handling, so an
# ejected ticket (now lane=normal) falls through to the full chain and is never
# re-grabbed by the fastlane path. AC6: it acts on ONE ticket id, so ejecting a
# bundle member never touches its still-eligible mates.
fastlane_eject_gate() {
    local ticket="$1" to="$2" dump pair lf lt n offense idx
    [ "$ORCH_FASTLANE_EJECT" = "1" ] || return 1
    # Only the story PRE-merge stations (Design..Story Acceptance, index 1..9):
    # a ticket already at Merging/Docs/Done or on the epic chain is never ejected.
    idx="$(chain_index "$to")"
    [ "$idx" -ge 1 ] && [ "$idx" -le 9 ] || return 1
    ticket_still_in "$ticket" "$to" || return 1
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    [ "$(ticket_lane "$dump")" = "fastlane" ] || return 1
    # (d) a guard fires: the last actual transition is an illegal forward skip.
    pair="$(last_transition_pair "$dump")"
    lf="${pair%%$'\t'*}"; lt="${pair##*$'\t'}"
    if [ -n "$lf" ] && [ "$lt" = "$to" ] \
        && forward_skip_illegitimate "$lf" "$lt" "$(active_conditional_flags "$dump")"; then
        fastlane_eject "$ticket" guard "illegal-skip $lf->$lt"
        return 0
    fi
    # (a) red tests from iteration >= ORCH_FASTLANE_EJECT_ITER: a backward bounce
    # already happened (rework_count counts it natively, ABS-74; no new counter).
    n="$(rework_count "$dump")"
    if [ "$n" -ge 1 ] && [ "$n" -ge "$(( ORCH_FASTLANE_EJECT_ITER - 1 ))" ]; then
        fastlane_eject "$ticket" red-tests "iteration=$(( n + 1 ))"
        return 0
    fi
    # (b)/(c) diff budget overrun / protected path touched (Solo-Seat commits).
    offense="$(fastlane_diff_offense "$dump")"
    case "$offense" in
        protected-path:*) fastlane_eject "$ticket" protected-path "${offense#protected-path:}"; return 0 ;;
        diff-budget:*)    fastlane_eject "$ticket" diff-budget "${offense#diff-budget:}"; return 0 ;;
    esac
    return 1
}

# ticket_has_flag <ticket-dump> <flag> — 0 (true) when the flags frontmatter
# list contains the flag (word match inside "flags: [a, b]").
ticket_has_flag() {
    printf '%s\n' "$(fm_field "$1" flags)" | tr -d '[],' | grep -qw "$2"
}

# ticket_has_label <ticket-dump> <label> — 0 (true) when the labels frontmatter
# list contains <label> EXACTLY (ABS-101). Unlike ticket_has_flag (fixed vocab,
# no shared substrings) labels are free-form, so an exact per-token compare is
# used to avoid "ready" matching inside "orchestrator-ready".
ticket_has_label() {
    fm_field "$1" labels | tr -d '[]' | awk -v want="$2" -F',' '
        { for (i = 1; i <= NF; i++) { gsub(/^[ \t]+|[ \t]+$/, "", $i); if ($i == want) f = 1 } }
        END { exit(f ? 0 : 1) }'
}

# ticket_is_delegated <ticket-dump> — 0 (true) when the ticket carries a machine-
# readable DELEGATION marker: label `delegated` or `lane:external`, or a
# DO-NOT-DISPATCH annotation in the body/comments (PILOT-22). Such a ticket is
# worked by an EXTERNAL system of record — a v3 pilot twin, shadow coexistence
# (ABS-326), or a human by hand — that may book it "In Progress" with no
# orchestrator seat and no lock, which looks exactly like a crashed-seat orphan.
# The runner must never heal it into a dispatchable status nor spawn a seat for
# it: two correct mechanisms (orphan-heal + dispatch, both BELOW the opt-in label
# gate) otherwise compose into a duplicate delivery (ABS-492, 2026-07-20).
ticket_is_delegated() {
    local dump="$1"
    ticket_has_label "$dump" "delegated" && return 0
    ticket_has_label "$dump" "lane:external" && return 0
    printf '%s\n' "$dump" | grep -q 'DO-NOT-DISPATCH' && return 0
    return 1
}

# orchestrator_ready <ticket> — 0 (true) when the Backlog opt-in gate (ABS-101)
# is satisfied: either the gate is disabled ($ORCH_REQUIRE_START_LABEL != 1) or
# the ticket carries $ORCH_START_LABEL. Consulted ONLY on the Backlog intake
# (dispatch + stall + reconcile); once a ticket is in the pipeline its other
# statuses are ungated.
orchestrator_ready() {
    [ "$ORCH_REQUIRE_START_LABEL" = "1" ] || return 0
    ticket_has_label "$(tracker get "$1" 2>/dev/null || true)" "$ORCH_START_LABEL"
}

# backlog_epic_child_parent <ticket> — echo the parent epic id when <ticket> is a
# Backlog child whose parent epic is in an epic-pipeline status BEFORE
# "Stories In Flight" (chain_index 21..25: PO Triage, Grooming, Enrichment,
# Ticket Review, Architecture Review), else nothing. Non-zero when there is no
# such parent. The release edge for these children (Backlog -> Ready for
# Development) belongs to the epic's Architecture Review seat, not the PO sweep,
# so a po-agent spawn here is a structural no-move (ABS-304). Gated OFF by
# ORCH_BACKLOG_SKIP_EPIC_CHILDREN=0. A parent at Stories In Flight (26) or later
# is the normal story pipeline and is NOT matched (children get released there).
backlog_epic_child_parent() {
    [ "$ORCH_BACKLOG_SKIP_EPIC_CHILDREN" = "0" ] && return 1
    local parent pstatus pidx
    parent="$(fm_field "$(tracker get "$1" 2>/dev/null || true)" parent)"
    [ -n "$parent" ] || return 1
    pstatus="$(fm_field "$(tracker get "$parent" 2>/dev/null || true)" status)"
    pidx="$(chain_index "$pstatus")"
    if [ "$pidx" -ge 21 ] && [ "$pidx" -lt 26 ]; then
        printf '%s' "$parent"; return 0
    fi
    return 1
}

# add_start_label <ticket> — idempotently add $ORCH_START_LABEL to <ticket>'s
# free-form labels (ABS-208). `tracker update labels` replaces the whole set, so
# the current labels are re-emitted with the start label appended (read-modify-
# write). No-op when the label is already present. Dry-run logs the intent only;
# live writes — the same MODE discipline as raise_stall/skip_forward.
add_start_label() {
    local ticket="$1" dump labels newset lbl
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    ticket_has_label "$dump" "$ORCH_START_LABEL" && return 0
    labels="$(fm_field "$dump" labels | tr -d '[]')"
    newset="$ORCH_START_LABEL"
    for lbl in $(printf '%s' "$labels" | tr ',' ' '); do
        [ -n "$lbl" ] || continue
        newset="$newset, $lbl"
    done
    intent LABEL-PROPAGATE "$ticket" - - "+$ORCH_START_LABEL"
    [ "$MODE" = "live" ] || return 0
    tracker update "$ticket" labels "[$newset]" >/dev/null 2>&1 \
        || log "label propagation failed on $ticket"
}

# propagate_start_label_to_children <epic> — copy $ORCH_START_LABEL from a
# labelled epic onto its non-terminal children (ABS-208, operator retro
# 2026-07-11). Without this a child the enrichment seat created mid-flight, or a
# child that predates the label gate, never inherits the label and drops out of
# the Backlog opt-in sweep after an orchestrator restart. No-op unless the gate
# is ON and the epic ITSELF carries the label (AC3: no label materializes on a
# parentless/unlabelled tree). Done / Epic Done children are left untouched
# (AC2). Called deterministically by the runner right after the issue-enrichment
# seat creates children (AC1) and on every reconcile sweep over a labelled epic
# (AC2 restart/laggard catch-up). Idempotent — add_start_label skips children
# that already carry the label.
propagate_start_label_to_children() {
    local epic="$1" rows line id status
    [ "$ORCH_REQUIRE_START_LABEL" = "1" ] || return 0
    ticket_has_label "$(tracker get "$epic" 2>/dev/null || true)" "$ORCH_START_LABEL" || return 0
    rows="$(epic_children_rows "$epic")"
    [ -n "$rows" ] || return 0
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        id="$(printf '%s' "$line" | awk -F'\t' '{print $1}')"
        status="$(printf '%s' "$line" | awk -F'\t' '{gsub(/^\[|\]$/, "", $2); print $2}')"
        [ -n "$id" ] || continue
        case "$status" in
            "Done"|"Epic Done"|"Canceled"|"Rejected") continue ;;
        esac
        add_start_label "$id"
    done <<EOF
$rows
EOF
}

# skip_forward <ticket> <to> <flag> — realize the skip. Dry-run logs the intent
# only (like raise_stall); live posts the audit comment then re-transitions.
skip_forward() {
    local ticket="$1" to="$2" flag="$3" target
    target="$(skip_forward_target "$to")"
    intent SKIP-FORWARD "$ticket" - "$target" "unflagged=$flag at=$to"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind skip --actor orchestrator \
        --body "SKIP-FORWARD: conditional stage '$to' skipped (flag '$flag' not set); re-transitioning to '$target' (ABS-84, spec §3.3)." \
        >/dev/null 2>&1 || log "skip-forward comment failed on $ticket"
    tracker transition "$ticket" "$target" --actor orchestrator \
        --reason "SKIP-FORWARD: '$to' needs flag '$flag' (unset)" \
        >/dev/null 2>&1 || log "skip-forward transition failed on $ticket"
}

# Whether a SPAWN on this `to` status is a bounce-capable implement<->validate
# loop that the iteration guard governs (§5.5).
is_bounce_status() {
    case "$1" in
        "In Review"|"In Test") return 0 ;;
        *) return 1 ;;
    esac
}

# Whether a SPAWN on this `to` status is a review gate that must run read-only
# (ABS-57). Only In Review qualifies: it reuses the write-capable system-architect
# role, so the runner narrows its toolset to $ORCH_REVIEW_TOOLS. In Test (qas) is
# excluded on purpose — qas has no Write/Edit and needs its tracker-comment tools.
is_readonly_review_status() {
    case "$1" in
        "In Review") return 0 ;;
        *) return 1 ;;
    esac
}

# Whether reconcile() may re-derive a spawn from a ticket *resting* in this
# status (§5.1). Only transient work states qualify — states an assigned agent
# is expected to promptly transition OUT of, so a ticket found resting there
# with no in-flight lock genuinely implies a dropped status-change event that
# must be recovered. Entry/terminal/human-owned resting states are deliberately
# excluded: tickets legitimately *rest* in Backlog (ungroomed), In Progress
# (agent working), Done (terminal), Ready for Merge (human gate) and Blocked
# (awaiting human). Re-deriving those would mass-spawn a whole backlog on the
# startup sweep and re-spawn every cadence forever (e.g. Done -> tech-writer),
# burning the ADR-A-0009 budget. The re-read guard cannot catch this because a
# resting ticket really is still in that status.
#
# Backlog is the ONE case with a controlled exception (ABS-101,
# reconcilable_labelled_backlog): a Backlog ticket carrying $ORCH_START_LABEL was
# explicitly released to the factory, so reconcile re-derives its PO sweep like
# any transient state — this is exactly what lets a label added at runtime be
# picked up on the next sweep without a restart. The mass-spawn concern the
# exclusion guards against does NOT apply, because unlabelled tickets (the bulk
# of a migrated backlog) stay excluded.
is_reconcilable_status() {
    case "$1" in
        "Ready for Development"|"In Review"|"In Test"|"Ready for Human Acceptance"|"Needs PO Decision") return 0 ;;
        # v3 epic pipeline (ABS-71): agent-owned transient seats are crash-
        # recoverable. "Stories In Flight" and "Ready for Epic Acceptance"
        # REST (JOIN rule / human own them). "Epic Done" also rests despite
        # being agent-mapped: it is terminal, so a resting ticket there is the
        # NORMAL end state — re-deriving would re-spawn self-improvement every
        # sweep forever (same reasoning as Done -> tech-writer above); stall
        # coverage for a crashed retro spawn is deliberately traded away.
        "PO Triage"|"Grooming"|"Enrichment"|"Ticket Review"|"Architecture Review"|"Epic Integration") return 0 ;;
        # v3 story seats (ABS-72/ABS-83): all transient agent-owned stages are
        # crash-recoverable, incl. Docs (tech-writer promptly exits to Done).
        # SKIP-FORWARD keeps a re-derive on an unflagged conditional stage a
        # cheap no-spawn skip.
        "Design"|"Security Review"|"Test Prep"|"Design Test"|"Story Acceptance"|"Merging"|"Docs") return 0 ;;
        *) return 1 ;;
    esac
}

# reconcilable_labelled_backlog <id> <status> — 0 (true) when this is a Backlog
# ticket the human opted into via $ORCH_START_LABEL, so reconcile may re-derive
# its PO sweep (ABS-101). Only fires when the gate is ON: with the gate OFF the
# legacy behaviour holds (Backlog is never reconcilable, so reconcile never
# mass-spawns an ungroomed backlog). dispatch() re-checks the label anyway, so
# an unlabelled ticket that slipped through would still SKIP-UNLABELLED.
reconcilable_labelled_backlog() {
    [ "$2" = "Backlog" ] && [ "$ORCH_REQUIRE_START_LABEL" = "1" ] || return 1
    ticket_has_label "$(tracker get "$1" 2>/dev/null || true)" "$ORCH_START_LABEL"
}

# =============================================================================
# ABS-116 Stuck detector (NOTIFY-only — eyes, not hands; ADR-A-0004)
# =============================================================================
# A ticket is STUCK when it rests for ORCH_STUCK_SWEEPS consecutive sweeps in a
# status nobody owns: not reconcilable (no seat is re-derived), not a documented
# legitimate resting state, no in-flight spawn (single-flight lock), and no
# pending backoff/pause marker ($ORCH_STATE_DIR/backoff-<ticket>* — the ABS-118
# forward-compat seam; the glob is empty until backoff lands). Today that set
# is effectively {In Progress without a running session} plus any unknown
# status — deliberately generic so future NOOP edges surface instead of resting
# silently (observed live: the ABS-108 In Review -> In Progress deadlock).
# One NOTIFY per (ticket, status) episode; the run.log keeps a throttled
# STUCK-DETECT line per further sweep (D12 pattern). Never routes.
#
# ABS-195 decision — STUCK-DETECT on "In Progress" once stayed NOTIFY-only (no
# auto session-resume-spawn of the last seat). Rationale:
#  1. ADR-A-0004 makes the stuck detector "eyes, not hands": it observes and
#     escalates, it does not act. An automatic resume-spawn is "hands".
#  2. The detector cannot tell a crashed/ended seat from a legitimately busy one
#     beyond the lock + sweep heuristic; a resume-spawn on a false positive would
#     double-drive a ticket that a live (but lock-less) seat still owns.
#  3. A deterministic resume needs the last session id, which the orchestrator
#     does not reliably retain for an In-Progress ticket owned by a seat that
#     ended its own process — the exact failure this ticket addresses.
#  4. The ROOT cause is fixed at the source instead: common seat-rule #5
#     (harness/claude/agents/_common-rules.md, "Background-Task-Disziplin")
#     forbids a seat from ending its spawn while a background task is still
#     running, so the orphaned In-Progress + lost-result state should not arise.
#
# ABS-451 REVISION — a SECOND source of orphaned In Progress proved the NOTIFY
# was not enough: a TDM blocker-resume (or human release) that targets "In
# Progress" parks a ticket in a status NO seat is re-derived for, so it dead-ends
# with only a repeating stuck NOTIFY (ABS-417 3x in 12h, ABS-438). The runner now
# SELF-HEALS this class: after ORCH_INPROGRESS_HEAL_SWEEPS sweeps it DOWNGRADES an
# unowned In Progress ticket to "Ready for Development" (a spawnable status) so
# reconcile derives a FRESH seat. This does NOT reopen the ABS-195 objections:
# it is not a session-resume-spawn (no session id, no re-drive of the dead seat
# — objection #3), and it routes to a spawnable rest state rather than double-
# driving a busy seat (the candidate gate still requires no live lock — #2). A
# real crash keeps its precise path: the heal DEFERS whenever a SPAWN-CRASH marker
# is present, leaving ABS-295 CRASH-REPAIR to route to the recorded origin. The
# NOTIFY still fires for every OTHER unowned status, and for In Progress when the
# heal is disabled (ORCH_INPROGRESS_HEAL_SWEEPS=0), so any residual orphan still
# surfaces to a human/PO (ABS-116) rather than resting silently.

# Legitimate resting states (§5.1 rationale): entry/terminal/human-owned/JOIN.
# Ready for Human Acceptance is reconcilable and listed defensively only.
is_legit_rest_status() {
    case "$1" in
        "Backlog"|"Blocked"|"Ready for Merge"|"Ready for Human Acceptance"|"Done"|"Epic Done"|"Canceled"|"Rejected"|"Stories In Flight"|"Ready for Epic Acceptance") return 0 ;;
        *) return 1 ;;
    esac
}

STUCK_STATE_FILE=""   # resolved lazily so tests overriding ORCH_STATE_DIR work
stuck_state_file() { echo "${STUCK_STATE_FILE:-$ORCH_STATE_DIR/stuck-state}"; }

# clear_stuck_row <ticket> — drop the ticket's stuck-state row so its rest-clock
# restarts from zero. Called whenever the runner itself transitions a ticket
# INTO an unowned status (e.g. ABS-296 blocked-auto-release to an In Progress
# origin): the ticket has just ARRIVED, so the ABS-451 heal must grant it a fresh
# ORCH_INPROGRESS_HEAL_SWEEPS grace rather than count sweeps from a prior episode.
clear_stuck_row() {
    local f tab; f="$(stuck_state_file)"; tab="$(printf '\t')"
    [ -f "$f" ] || return 0
    if grep -q "^$1$tab" "$f" 2>/dev/null; then
        grep -v "^$1$tab" "$f" > "$f.tmp" 2>/dev/null || true
        mv "$f.tmp" "$f" 2>/dev/null || true
    fi
}

# check_stuck <ticket> <status> — run for EVERY ticket each sweep; filters
# candidates itself and clears finished episodes (status changed / became owned).
check_stuck() {
    local ticket="$1" status="$2"
    [ "$ORCH_STUCK_SWEEPS" -gt 0 ] || return 0
    local f tab
    f="$(stuck_state_file)"
    tab="$(printf '\t')"

    # Candidate = unowned resting status with no live work attached.
    local candidate=1
    if is_reconcilable_status "$status" || is_legit_rest_status "$status"; then
        candidate=0
    elif [ -d "$(lock_dir_for "$ticket")" ]; then
        candidate=0
    elif ls "$ORCH_STATE_DIR"/backoff-"$ticket"* >/dev/null 2>&1; then
        candidate=0
    elif [ -f "$ORCH_STATE_DIR/halt-$ticket" ]; then
        # ABS-118 escalation halt: the human was already NOTIFYed; a second
        # stuck NOTIFY would be noise.
        candidate=0
    fi

    if [ "$candidate" -eq 0 ]; then
        # Episode over (or never one): drop any stored row so a later fall-back
        # into an unowned status starts a FRESH episode (and may notify again).
        if [ -f "$f" ] && grep -q "^$ticket$tab" "$f" 2>/dev/null; then
            grep -v "^$ticket$tab" "$f" > "$f.tmp" 2>/dev/null || true
            mv "$f.tmp" "$f" 2>/dev/null || true
        fi
        return 0
    fi

    local row count=0 notified=0 prev_status=""
    row="$(grep "^$ticket$tab" "$f" 2>/dev/null | tail -1 || true)"
    if [ -n "$row" ]; then
        prev_status="$(printf '%s\n' "$row" | cut -f2)"
        if [ "$prev_status" = "$status" ]; then
            count="$(printf '%s\n' "$row" | cut -f3)"
            notified="$(printf '%s\n' "$row" | cut -f4)"
        fi
    fi
    count=$((count + 1))

    # ABS-451 In Progress orphan self-heal — the stuck candidate is an unowned
    # "In Progress" ticket (candidate gate above already proved: no live lock, no
    # in-flight spawn, no backoff/halt). After ORCH_INPROGRESS_HEAL_SWEEPS sweeps
    # the runner DOWNGRADES it to a spawnable status instead of only notifying, so
    # reconcile derives a fresh seat (closes the resume-to-In-Progress dead-end).
    # heal_inprogress_orphan returns 0 when it healed (episode resolved — drop the
    # row and stop), 1 when it deferred (SPAWN-CRASH marker present → ABS-295
    # CRASH-REPAIR owns it) so we fall through to the ABS-116 NOTIFY safety net.
    if [ "$status" = "In Progress" ] && [ "$ORCH_INPROGRESS_HEAL_SWEEPS" -gt 0 ] \
       && [ "$count" -ge "$ORCH_INPROGRESS_HEAL_SWEEPS" ]; then
        if heal_inprogress_orphan "$ticket"; then
            clear_stuck_row "$ticket"   # episode resolved — drop the row
            return 0
        fi
    fi

    if [ "$count" -ge "$ORCH_STUCK_SWEEPS" ]; then
        if [ "$notified" -eq 0 ]; then
            runlog STUCK-DETECT "$ticket" - "$status" "sweeps=$count"
            notify "${ORCH_NOTIFY_TICKET:-$ticket}" \
                "stuck detected: $ticket rests in '$status' for $count consecutive sweeps with no owning seat, no in-flight spawn and no pending wait; not routing (ABS-116) — human/PO attention needed"
            notified=1
        else
            runlog STUCK-DETECT "$ticket" - "$status" "sweeps=$count throttled"
        fi
    fi

    { grep -v "^$ticket$tab" "$f" 2>/dev/null || true
      printf '%s\t%s\t%s\t%s\n' "$ticket" "$status" "$count" "$notified"; } > "$f.tmp" \
        && mv "$f.tmp" "$f" 2>/dev/null || true
}

# heal_inprogress_orphan <ticket> — downgrade an unowned "In Progress" ticket to
# "Ready for Development" (a spawnable status) so reconcile derives a fresh seat.
# The caller (check_stuck) has already established the ticket is an orphan (no
# live lock, no in-flight spawn, N sweeps at rest). Returns:
#   0 — healed (transition + gate-results comment emitted)
#   1 — deferred: a SPAWN-CRASH marker is present, so ABS-295 CRASH-REPAIR must
#       own the routing (it goes to the RECORDED origin, not a blunt RfD).
# The transition itself is the idempotency guard: once the ticket leaves In
# Progress it is no longer a stuck candidate, so this never fires twice.
heal_inprogress_orphan() {
    local ticket="$1"
    local dump
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    # Confirm the ticket is still In Progress (a lost race may have moved it).
    printf '%s\n' "$dump" | grep -q '^status: In Progress' || return 1
    # Defer to ABS-295 CRASH-REPAIR when a crash marker exists — that path routes
    # to the precise recorded origin instead of a blunt Ready for Development.
    printf '%s\n' "$dump" | grep -q 'SPAWN-CRASH status=' && return 1
    # PILOT-22: an EXTERNALLY delegated ticket (v3 pilot twin, shadow coexistence
    # ABS-326, a human by hand) looks like a crashed-seat orphan — booked "In
    # Progress" by that system of record with no seat and no lock. Healing it to a
    # dispatchable status made the runner spawn a DUPLICATE seat that reimplemented
    # the delegated work in parallel (ABS-492). Two guards keep the heal below the
    # opt-in gate; both DEFER (return 1) to the ABS-116 NOTIFY so a human still
    # sees the orphan rather than resting silently:
    #   1. an explicit delegation marker is a hands-off — never heal it.
    #   2. the Backlog opt-in gate applies to a heal-produced status too: without
    #      $ORCH_START_LABEL the factory never owned this ticket, so the heal must
    #      not MANUFACTURE a dispatchable status below the gate (no below-the-gate
    #      path). A legit crashed-seat orphan carries the label (propagated to
    #      every factory child) and still heals — the ABS-451 behaviour is intact.
    if ticket_is_delegated "$dump"; then
        runlog INPROGRESS-HEAL-SKIP "$ticket" - "In Progress" "delegated (external owner) — not healed (PILOT-22)"
        return 1
    fi
    if [ "$ORCH_REQUIRE_START_LABEL" = "1" ] && ! ticket_has_label "$dump" "$ORCH_START_LABEL"; then
        runlog INPROGRESS-HEAL-SKIP "$ticket" - "In Progress" "opt-in gate: no $ORCH_START_LABEL — not healed (PILOT-22)"
        return 1
    fi

    intent INPROGRESS-HEAL "$ticket" - "Ready for Development" "sweeps>=$ORCH_INPROGRESS_HEAL_SWEEPS"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "INPROGRESS-HEAL=Ready for Development (orchestrator): ticket rested in 'In Progress' with no owning seat, no in-flight spawn and no crash marker for $ORCH_INPROGRESS_HEAL_SWEEPS consecutive sweeps — a status no seat is re-derived for (resume/release-to-In-Progress dead-end). Downgrading to 'Ready for Development' so reconcile dispatches a fresh seat instead of notifying forever (ABS-451; extends ABS-116)." \
        >/dev/null 2>&1 || log "inprogress-heal: comment failed on $ticket"
    tracker transition "$ticket" "Ready for Development" --actor orchestrator \
        --reason "INPROGRESS-HEAL: unowned 'In Progress' for $ORCH_INPROGRESS_HEAL_SWEEPS sweeps (no lock, no spawn, no crash marker); routing to a spawnable status so a fresh seat is dispatched (ABS-451)" \
        >/dev/null 2>&1 || { log "inprogress-heal: transition failed on $ticket"; return 1; }
    runlog INPROGRESS-HEAL "$ticket" - "Ready for Development" "sweeps>=$ORCH_INPROGRESS_HEAL_SWEEPS"
    return 0
}

# =============================================================================
# ABS-295 CRASH-REPAIR (reconcile heal — AD-1, ADR-A-0004)
# =============================================================================
# check_crash_repair <ticket> <status>
# All four conditions must hold for a repair to fire:
#   1. A runner-own SPAWN-CRASH gate-results marker exists on the ticket with
#      instance= matching ORCH_INSTANCE_ID (crash_marker_body embeds it).
#   2. No live seat lock, or lock is stale (age >= ORCH_LOCK_TTL).
#   3. Crash age >= ORCH_CRASH_REPAIR_SECONDS (0 = off = NOTIFY-only today).
#   4. Marker's instance= == own ORCH_INSTANCE_ID (two-runner safety — same
#      check as condition 1; the awk exits immediately on a mismatch).
# Idempotency key: a CRASH-REPAIR gate-results comment already on the ticket.
# Returns 0 when repair fired (reconcile loop should skip dispatch for this
# ticket). Returns 1 in every no-repair case.
check_crash_repair() {
    local ticket="$1" status="$2"
    # Condition 3 gate: 0 = off; reproduces NOTIFY-only behaviour exactly.
    [ "${ORCH_CRASH_REPAIR_SECONDS:-300}" -gt 0 ] || return 1
    # Only examine In Progress tickets (seat-owned crash scenario).
    [ "$status" = "In Progress" ] || return 1

    local dump
    dump="$(tracker get "$ticket" 2>/dev/null || true)"

    # Conditions 1 + 4: find the most recent SPAWN-CRASH gate-results comment
    # whose instance= matches our ORCH_INSTANCE_ID. Extract origin status (the
    # status= field) and the comment timestamp in one awk pass.
    # CRITICAL-1 FIX: use last-wins (END block) — comments are dumped oldest-
    # first; the previous `exit` on first match returned the oldest marker, not
    # the newest, violating AD-1's "only back to the origin that marker records".
    local marker_info
    marker_info="$(printf '%s\n' "$dump" | awk -v inst="${ORCH_INSTANCE_ID:-}" '
        /^### / {
            split($0, h, " ")
            cur_ts = h[2]
            in_crash = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/)
            next
        }
        in_crash && /SPAWN-CRASH status=/ {
            # Condition 4: skip markers from foreign runners.
            if (inst != "" && index($0, "instance=" inst) == 0) {
                in_crash = 0; next
            }
            # Extract status= value: between "SPAWN-CRASH status=" and " role=".
            line = $0
            sub(/.*SPAWN-CRASH status=/, "", line)
            sub(/ role=.*/, "", line)
            # Record most recent match; last assignment wins in END block.
            last = cur_ts "\t" line
            in_crash = 0
            next
        }
        END { if (last != "") print last }
    ')"
    [ -n "$marker_info" ] || return 1   # conditions 1 or 4 not met

    local crash_ts origin_status
    crash_ts="$(printf '%s\n' "$marker_info" | cut -f1)"
    origin_status="$(printf '%s\n' "$marker_info" | cut -f2-)"
    [ -n "$origin_status" ] || return 1

    # MEDIUM-4 FIX: same-status repair is a no-op and burns the idempotency key.
    # A resume spawn that crashes while the ticket is already In Progress writes
    # status=In Progress; transitioning In Progress → In Progress is bogus.
    [ "$origin_status" != "$status" ] || return 1

    # CRITICAL-2 FIX: dedup key is episode-scoped (own instance + crash timestamp).
    # Placed after marker extraction so inst and crash_ts are known.
    # The old "CRASH-REPAIR instance=" match hit ANY prior repair from ANY runner,
    # giving each ticket exactly one repair ever and letting a foreign runner's
    # comment permanently block ours — the opposite of two-runner safety.
    local inst="${ORCH_INSTANCE_ID:-unknown}"
    printf '%s\n' "$dump" | grep -q "CRASH-REPAIR instance=${inst} crash-time=${crash_ts}" && return 1

    # Condition 2: no live lock (or stale — age >= ORCH_LOCK_TTL).
    if [ -d "$(lock_dir_for "$ticket")" ]; then
        local lage
        lage="$(lock_age_for "$ticket" 2>/dev/null || echo 0)"
        [ "$lage" -ge "$ORCH_LOCK_TTL" ] || return 1
    fi

    # Condition 3: crash age (now - crash comment timestamp) >= threshold.
    # MEDIUM-3 FIX: delegate to iso_to_epoch() (reuse, not reinvent); fail
    # closed on empty/unparseable timestamp — the old inline `|| echo 0` yielded
    # crash_epoch=0 → age ≈ 1.7e9 → condition 3 passed silently on bad input.
    local crash_epoch age_s
    crash_epoch="$(iso_to_epoch "$crash_ts")"
    [ -n "$crash_epoch" ] || return 1
    age_s=$(( $(now_epoch) - crash_epoch ))
    [ "$age_s" -ge "${ORCH_CRASH_REPAIR_SECONDS:-300}" ] || return 1

    # All 4 conditions met — post audit comment, transition, emit intent line.
    intent CRASH-REPAIR "$ticket" - "$origin_status" "instance=$inst"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "CRASH-REPAIR instance=${inst} crash-time=${crash_ts:-unknown} session=${inst} origin=${origin_status}: runner's own SPAWN-CRASH marker (${crash_ts:-unknown}) proves seat is dead; routing orphaned ticket back to origin station (ABS-295)." \
        >/dev/null 2>&1 || log "crash-repair: comment failed on $ticket"
    tracker transition "$ticket" "$origin_status" --actor orchestrator \
        --reason "CRASH-REPAIR: own SPAWN-CRASH marker (${crash_ts:-unknown}, instance ${inst}) proves seat is dead; routing back to ${origin_status} (ABS-295)" \
        >/dev/null 2>&1 || log "crash-repair: transition failed on $ticket"
    runlog CRASH-REPAIR "$ticket" - "$origin_status" "instance=${inst} crash-time=${crash_ts:-unknown}"
    return 0
}

# =============================================================================
# ABS-62 Stall detection (mechanical, bash-only — runs inside the sweep)
# =============================================================================
# Two deliberately-few, mechanical rules that catch tickets silently stuck. When
# a rule fires they raise the ticket to "Needs PO Decision" with actor
# orchestrator + a reason comment naming the rule; the ABS-61 event mapping then
# spawns a fresh PO-Agent to make the judgment call (ADR-A-0009: bash detects for
# free, LLM only on a finding; ADR-A-0002: judgment = fresh single-ticket spawn).
# No LLM stall analysis, no periodic PO spawns.
#
# The raise is itself a tracked transition (ADR-A-0006), so the re-raise guard is
# keyed off the ticket's own comment history: a ticket already carrying an
# orchestrator stall-raise for the same rule is skipped, UNLESS its `updated:`
# changed since that raise (which means the ticket moved on and may legitimately
# stall again). Without this guard a PO decision of "leave it in Backlog" would
# loop forever.

# The marker each raise records in its `kind: decision` comment body, keyed by
# rule number. The re-raise guard matches on the rule-agnostic
# "STALL-RAISE rule=...(orchestrator)" substring to tell whether this ticket was
# already stall-raised by EITHER rule.
stall_marker() { printf 'STALL-RAISE rule=%s (orchestrator)' "$1"; }

# iso_to_epoch <iso-8601-Z> — best-effort ISO-8601 UTC -> unix seconds. Tries BSD
# `date -j -f` then GNU `date -d` (same both-forms portability as the lock TTL's
# `stat`). Prints nothing on failure so callers can treat it as "unknown age".
iso_to_epoch() {
    local ts="$1"
    [ -n "$ts" ] || return 0
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$ts" +%s 2>/dev/null \
        || date -u -d "$ts" +%s 2>/dev/null \
        || true
}

# fm_field <ticket-dump> <field> — read one frontmatter field from a `get` dump.
fm_field() {
    printf '%s\n' "$1" | awk -F': ' -v key="$2" '
        /^---$/ { fm++; next }
        fm == 1 && $1 == key { sub(/^[^:]*: ?/, ""); print; exit }
        fm >= 2 { exit }
    '
}

# ticket_priority <ticket> — the ticket's canonical priority (ABS-261). Reads the
# `priority` frontmatter field from the adapter dump (the canonical field ABS-242
# maps from the tracker); an absent/blank/unknown value yields `normal`, so a
# tree with no priorities behaves exactly as before (AC3). Only a Human/PO sets a
# non-normal priority — seats never raise it (AC6, _common-rules charter line).
ticket_priority() {
    local p
    p="$(fm_field "$(tracker get "$1" 2>/dev/null || true)" priority)"
    case "$p" in
        hotfix|high|normal|low) printf '%s' "$p" ;;
        *) printf 'normal' ;;
    esac
}

# priority_rank <priority> — numeric slot-allocation key, lower served first:
# hotfix=0 > high=1 > normal=2 > low=3 (ABS-261 AC1).
priority_rank() {
    case "$1" in
        hotfix) printf 0 ;;
        high)   printf 1 ;;
        low)    printf 3 ;;
        *)      printf 2 ;;
    esac
}

# prioritize_rows — reorder the sweep's search rows (on stdin) so a higher-priority
# ticket is offered a free slot before a lower one (ABS-261 AC1). The sort is
# STABLE within a priority band: the adapter's original (age-ascending) order is
# preserved as the tiebreak via a zero-padded sequence key, so a tree with no
# priorities is byte-identical to legacy dispatch (AC3).
#
# ABS-331: adapters now carry the canonical priority as a search COLUMN — the row
# is `id<TAB>type<TAB>status<TAB>priority<TAB>title` (5 fields). When that column
# is present we read priority from it and issue ZERO per-row `tracker get` calls
# for prioritization (the N-per-sweep cost this ticket removes). An older adapter
# that emits only the legacy 4-field row (`…<TAB>title`, no 5th field) falls back
# to the per-row `ticket_priority` read, keeping full backward compatibility. Each
# input line is preserved VERBATIM in the output (the reconcile loop reads
# id/type/status and ignores any trailing column), so ignoring callers are
# byte-identical.
prioritize_rows() {
    local line id rest f4 prio rank tab i=0
    tab="$(printf '\t')"
    while IFS= read -r line; do
        id="${line%%"$tab"*}"
        [ -n "$id" ] || continue
        # Peel the first three tab-delimited fields to expose field 4 and detect a
        # 5th. Five fields => the priority column is present (field 4); four fields
        # => legacy layout (field 4 is the title) and we fall back to a per-row get.
        rest="${line#*"$tab"}"; rest="${rest#*"$tab"}"; rest="${rest#*"$tab"}"
        f4="${rest%%"$tab"*}"
        if [ "$rest" != "${rest#*"$tab"}" ]; then
            # Column present: trust the enum, default anything unmapped to normal.
            case "$f4" in
                hotfix|high|normal|low) prio="$f4" ;;
                *) prio="normal" ;;
            esac
        else
            prio="$(ticket_priority "$id")"
        fi
        rank="$(priority_rank "$prio")"
        printf '%s\t%010d\t%s\n' "$rank" "$i" "$line"
        i=$((i + 1))
    done | sort -t "$tab" -k1,1n -k2,2n | cut -f3-
}

# last_po_park_epoch <ticket-dump> — the unix-seconds timestamp of the MOST
# RECENT "Needs PO Decision -> Backlog" transition (the PO's "leave it in
# Backlog" decision on a raise). Empty when the ticket has never been parked back
# to Backlog from a PO decision. Correlates each transition-reason comment's
# `### <at> | ...` header timestamp with its body line, adapter-only (the mock
# writes both verbatim). Pure awk; BSD/GNU safe via iso_to_epoch.
last_po_park_epoch() {
    local dump="$1" at
    at="$(printf '%s\n' "$dump" | awk '
        /^### / {
            # Header line: "### <timestamp> | kind: ... | actor: ...". Grab field 2.
            n = split($0, f, " ")
            cur = (n >= 2 ? f[2] : "")
            next
        }
        /^Transition: Needs PO Decision -> Backlog\./ { last = cur }
        END { if (last != "") print last }')"
    [ -n "$at" ] || return 0
    iso_to_epoch "$at"
}

# has_orchestrator_stall_marker <ticket-dump> — 0 (true) when the ticket carries a
# real orchestrator stall-raise: the "STALL-RAISE rule=...(orchestrator)" marker
# must appear in the BODY of a comment whose header is `kind: decision` AND
# `actor: orchestrator`. A bare substring scan over the whole dump would be
# disarmed by any comment that merely QUOTES the marker text (realistic for a
# ticket that is itself about ABS-62), so we parse comment blocks. Adapter-only:
# reads the `get` dump the mock writes verbatim.
has_orchestrator_stall_marker() {
    printf '%s\n' "$1" | awk '
        /^### / {
            hdr = $0
            in_orch_decision = (hdr ~ /kind: decision/ && hdr ~ /actor: orchestrator/)
            next
        }
        in_orch_decision && /STALL-RAISE rule=.*\(orchestrator\)/ { found = 1 }
        END { exit(found ? 0 : 1) }
    '
}

# stall_raise_suppressed <ticket-dump> — 0 (true, "suppress ANY stall raise") when
# the ticket has already been stall-raised (for EITHER rule) and the PO has since
# parked it back in Backlog, with no edit AFTER that decision. This is the unified,
# cross-rule re-raise guard the ticket requires ("never re-flag a ticket the PO
# already routed") — it must hold across both rules, so a rule-1 raise the PO
# parks is not re-flagged by rule 2.
#
# The `updated:` contract: skip UNLESS `updated:` changed since the raise. The
# raise's own comment+transition bump `updated:`, so we compare `updated:` against
# the PO-PARK transition timestamp (the last "Needs PO Decision -> Backlog"), not
# the raise time. If `updated:` is strictly newer than the park, something touched
# the ticket AFTER the PO's decision (a `tracker update` edit, a new comment, a
# re-transition) — the ticket re-arms and a fresh raise is allowed.
#
# Suppression applies ONLY once the PO has parked the ticket back to Backlog. If a
# stall-marker is present but there is no "Needs PO Decision -> Backlog" park
# transition, the ticket is NOT under a live PO decision and is eligible to be
# raised again — e.g. the PO routed it to Ready for Development and it was later
# deprioritized back to Backlog still bare+aged, or a half-raise where the comment
# landed but the transition failed (no PO-Agent was ever spawned). Suppressing
# those would deadlock detection forever. No loop risk: a fresh raise -> park then
# re-enters the normal park-suppress path.
stall_raise_suppressed() {
    local dump="$1" park_epoch cur_epoch
    # No genuine orchestrator stall-raise marker -> nothing to suppress.
    has_orchestrator_stall_marker "$dump" || return 1
    park_epoch="$(last_po_park_epoch "$dump")"
    # Marker present but never parked back by the PO -> not a live PO decision ->
    # eligible to re-raise (FINDING 1: must NOT suppress forever here).
    [ -n "$park_epoch" ] || return 1
    cur_epoch="$(iso_to_epoch "$(fm_field "$dump" updated)")"
    # Unparseable `updated:` -> be conservative, suppress (never risk a loop).
    [ -n "$cur_epoch" ] || return 0
    # `updated:` strictly newer than the PO park -> edited after the decision ->
    # re-arm (return 1, eligible). Otherwise the PO's decision stands -> suppress.
    if [ "$cur_epoch" -gt "$park_epoch" ]; then
        return 1
    fi
    return 0
}

# ticket_age_seconds <ticket-dump> <field> — age in seconds of a frontmatter
# timestamp field (created|updated). Prints -1 when the age can't be computed.
ticket_age_seconds() {
    local dump="$1" field="$2" ts epoch now
    ts="$(fm_field "$dump" "$field")"
    epoch="$(iso_to_epoch "$ts")"
    [ -n "$epoch" ] || { echo "-1"; return 0; }
    now="$(date -u +%s)"
    echo $((now - epoch))
}

# raise_stall <ticket> <rule> <human-reason> — realize a stall raise. Dry-run
# logs INTENT STALL-RAISE only. Live: post an orchestrator `kind: decision`
# comment naming the rule (carrying the re-raise marker so the guard can spot it
# later), then transition Backlog -> "Needs PO Decision". The ABS-61 mapping
# picks up the transition and spawns a fresh PO-Agent (ADR-A-0002). Comment
# BEFORE the transition so the marker survives even if the transition were
# rejected.
raise_stall() {
    local ticket="$1" rule="$2" reason="$3" marker
    intent STALL-RAISE "$ticket" - "Needs PO Decision" "rule=$rule"
    [ "$MODE" = "live" ] || return 0
    marker="$(stall_marker "$rule")"
    tracker comment "$ticket" --kind decision --actor orchestrator \
        --body "Stall detected: $reason [$marker]" \
        >/dev/null 2>&1 || log "stall-raise comment failed on $ticket"
    tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
        --reason "$reason (ABS-62 rule $rule)" \
        >/dev/null 2>&1 || log "stall-raise transition failed on $ticket"
}

# check_stall_rules <ticket> <type> <status> — evaluate the mechanical stall
# rules for one ticket during the sweep. Only Backlog tickets are candidates
# (non-Backlog states are untouched). Fires at most one raise per ticket per
# sweep (rule 1 short-circuits rule 2). The unified cross-rule re-raise guard
# (stall_raise_suppressed) is checked ONCE up front so a ticket the PO already
# routed is never re-flagged by EITHER rule.
check_stall_rules() {
    local ticket="$1" type="$2" status="$3"
    [ "$status" = "Backlog" ] || return 0

    local dump age
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    [ -n "$dump" ] || return 0

    # Backlog opt-in gate (ABS-101): an unlabelled Backlog ticket is intentionally
    # resting (not yet released to the factory), not stalled — never raise
    # "Needs PO Decision" on it. Reuses the dump already fetched above.
    if [ "$ORCH_REQUIRE_START_LABEL" = "1" ] && ! ticket_has_label "$dump" "$ORCH_START_LABEL"; then
        return 0
    fi

    # Cross-rule re-raise guard: if the ticket was already raised (any rule) and
    # the PO has since parked it back in Backlog with no edit after, suppress all
    # rules. An edit after the park (newer `updated:`) re-arms it.
    if stall_raise_suppressed "$dump"; then
        return 0
    fi

    # --- Rule 1: undecomposed epic (type epic, Backlog, zero children, aged) ---
    if [ "$type" = "epic" ] && [ "$ORCH_STALL_EPIC_SECONDS" -gt 0 ]; then
        local kids
        kids="$(tracker children "$ticket" 2>/dev/null || true)"
        if [ -z "$kids" ]; then
            age="$(ticket_age_seconds "$dump" created)"
            if [ "$age" -ne -1 ] && [ "$age" -ge "$ORCH_STALL_EPIC_SECONDS" ]; then
                raise_stall "$ticket" 1 \
                    "undecomposed epic resting in Backlog with no children for ${age}s (>= ${ORCH_STALL_EPIC_SECONDS}s)"
                return 0
            fi
        fi
    fi

    # --- Rule 2: resting too long in Backlog (opt-in; 0 = disabled) -----------
    if [ "$ORCH_STALL_RESTING_SECONDS" -gt 0 ]; then
        age="$(ticket_age_seconds "$dump" updated)"
        if [ "$age" -ne -1 ] && [ "$age" -ge "$ORCH_STALL_RESTING_SECONDS" ]; then
            raise_stall "$ticket" 2 \
                "ticket resting in Backlog untouched for ${age}s (>= ${ORCH_STALL_RESTING_SECONDS}s)"
        fi
    fi
}

# =============================================================================
# v3 safety guards — rework counter + crash escalation (ABS-74, spec §3.2/§3.8)
# =============================================================================
# Both counters are DERIVED from the ticket's adapter dump (transition and
# gate-results comment history), never shell state — they survive any runner
# restart for free (ABS-74 persistence AC).
#
# Rework counter (§3.2): every BACKWARD agent transition along the canonical
# chain counts, regardless of which stage pair bounced (the cross-stage net the
# pairwise ABS-12 iteration guard cannot see; that guard remains the inner,
# In Review/In Test-specific cap). At ORCH_REWORK_LIMIT the runner transitions
# to "Needs PO Decision" instead of spawning. The counting WINDOW resets at
# every PO-decision exit ("Needs PO Decision -> *", any target — architecture
# review finding 3), so a PO routing the ticket onward re-arms a fresh window
# instead of instantly re-escalating. Transitions by actor "human" are ignored
# (human rejection = forward-fix, never counted; sim parity).
#
# Crash escalation (§3.8): a dispatch whose spawn failed twice (attempt+retry,
# §6) posts a SPAWN-CRASH marker and leaves the ticket RESTING in its status
# for the sweep to re-derive — it no longer transitions to Blocked (which in
# v3 would wrongly spawn the TDM; architecture review finding 2). At
# ORCH_CRASH_LIMIT consecutive markers for the same status with no intervening
# successful handoff, the runner escalates to "Needs PO Decision".

ORCH_REWORK_LIMIT="${ORCH_REWORK_LIMIT:-3}"
# PILOT-69 / ADR-A-0018 transient class (Anschluss ABS-555): reason substrings
# (matched case-insensitively) that mark a backward transition as an INFRASTRUCTURE
# abort — budget-neutral for rework_count(), mirroring iteration-guard.sh's
# INFRA_ABORT_RE. Kept in step with blocker_class()'s `transient` set. Content
# faults (a handoff MIS-REPORT / marker-missing) are deliberately ABSENT so
# ADR-A-0024 (e) still counts them as rework.
ORCH_REWORK_INFRA_RE="${ORCH_REWORK_INFRA_RE:-crash-repair|inprogress-heal|spawn crashed|wait-state repair|error_max_turns|max_turns|turn ceiling|session-poison|session poisoned|salvage|rate limit|ratelimit|429|timeout|connection|non-zero exit|network}"
ORCH_CRASH_LIMIT="${ORCH_CRASH_LIMIT:-3}"
ORCH_FOLLOWUP_BUDGET="${ORCH_FOLLOWUP_BUDGET:-5}"  # ABS-75, spec §3.4/S7: per-epic cap
# ABS-298: seconds a FOLLOWUP-SPAWN marker may sit without a matching
# kind:bsa-decision (and no live lock) before the watcher re-spawns the bsa for
# that ordinal (a seat that died before posting its decision). 0 = off = today's
# dedupe-forever behaviour. Bounded by ORCH_CRASH_LIMIT / ORCH_RESPAWN_LIMIT.
ORCH_FOLLOWUP_REPAIR_SECONDS="${ORCH_FOLLOWUP_REPAIR_SECONDS:-300}"
# ABS-132: the runner applies a parsed handoff's declared target transition
# itself (transition-on-handoff), and caps endless no-move respawns.
ORCH_HANDOFF_TRANSITION="${ORCH_HANDOFF_TRANSITION:-1}"  # apply handoff target via adapter
ORCH_RESPAWN_LIMIT="${ORCH_RESPAWN_LIMIT:-2}"           # no-move respawns before NPD

# ABS-336 / ADR-A-0014: autonomous integration-conflict resolution. When an epic
# blocks FROM `Epic Integration` on a `sync-rebase conflict` (the RTE seat's
# spec-conformant abort), the runner routes a forward-fix implementer (role from
# the failing commit's ticket) instead of ending autonomy at the tdm/human triage,
# then re-reviews the merged epic via `Architecture Review`. Default-on with the
# ABS-111 kill-switch convention; =0 restores the pre-ABS-336 (tdm-only) behaviour.
ORCH_INTEGRATION_CONFLICT_ROUTE="${ORCH_INTEGRATION_CONFLICT_ROUTE:-1}"

# ABS-255 / ADR-A-0024: the runner verifies the commit hashes a handoff CLAIMS
# (`commits:` field) before it ACCEPTS the handoff — existence + ref-reachability.
# A claim that does not hold is a mis-report: the transition is refused and the
# work bounces back to the seat that claimed it. Default-on with the ABS-111
# kill-switch convention; =0 restores the pre-ABS-255 (unverified) behaviour.
ORCH_VERIFY_COMMITS="${ORCH_VERIFY_COMMITS:-1}"

# PILOT-75 / ADR-A-0024 + ADR-A-0030: a FORWARD transition that claims work
# COMPLETE (story chain 'In Review' and beyond) is accepted only when the claimed
# commits are reachable on the ACTIVE remote — i.e. actually PUSHED. A purely
# local commit passes the ABS-255 existence+ref-reachability check (any local ref
# contains it) yet LIES about the remote's state: outside the seat worktree the
# work does not exist and vanishes on cleanup (four belebte Faelle in three runs,
# ABS-581). The active remote is the only source (ADR-A-0030) — never a hardcoded
# origin. Same refusal path as the ABS-255 commit mis-report. Default-on with the
# ABS-111 kill-switch convention; =0 restores the pre-PILOT-75 (local-only-OK)
# behaviour.
ORCH_VERIFY_PUSH="${ORCH_VERIFY_PUSH:-1}"

# ABS-482: evidence-commit hygiene. A QA/evidence commit (one touching the
# evidence path docs/agent-outputs/**) must ride the STORY BRANCH of the ticket
# under test (refs/heads/<ticket>-*) and carry NOTHING else. The runner refuses a
# handoff whose evidence commit landed on a foreign/stale branch or bundled
# non-evidence dirty-workspace files (both happened in the ABS-482 Befund: a QA
# report committed onto ABS-444-docs with 6 unrelated files). Same refusal path
# as the ABS-255 commit mis-report. Default-on with the ABS-111 kill-switch
# convention; =0 restores the pre-ABS-482 (unchecked) behaviour. The evidence
# path prefix is overridable for non-default profiles.
ORCH_VERIFY_EVIDENCE="${ORCH_VERIFY_EVIDENCE:-1}"
ORCH_EVIDENCE_PATH_PREFIX="${ORCH_EVIDENCE_PATH_PREFIX:-docs/agent-outputs/}"

# ABS-297 / ADR-A-0024: the runner verifies that a handoff claiming a marker-duty
# effect (JOIN exemption, bsa follow-up decision) is backed by the actual
# machine-readable marker on the target ticket before accepting the handoff.
# Same precedent as ABS-255 commit verification. Default-on with the ABS-111
# kill-switch convention; =0 restores pre-ABS-297 (unchecked) behaviour.
ORCH_VERIFY_MARKERS="${ORCH_VERIFY_MARKERS:-1}"

# ABS-199 / ADR-A-0018: cross-visit same-blocker loop-breaker + per-ticket
# escalation budget. Both default-on with an env kill-switch (same convention as
# ABS-132/ABS-118). Thresholds match the ADR: the 2nd occurrence of the same
# (environment-denial class, seat) across ANY visits auto-parks to Blocked; a
# ticket that rests ORCH_ESCALATION_BUDGET rounds without forward status progress
# exhausts its budget and parks. Orthogonal to the per-visit ABS-132 respawn
# limit (which stays the backstop for logic loops inside a single status).
ORCH_CROSSVISIT_LOOPBREAKER="${ORCH_CROSSVISIT_LOOPBREAKER:-1}"
ORCH_CROSSVISIT_THRESHOLD="${ORCH_CROSSVISIT_THRESHOLD:-2}"
ORCH_ESCALATION_LOOPBREAKER="${ORCH_ESCALATION_LOOPBREAKER:-1}"
ORCH_ESCALATION_BUDGET="${ORCH_ESCALATION_BUDGET:-3}"
# ABS-311 / ADR-A-0018 §d: work-credit signal on the no-move path. A resting
# round that produced VERIFIED work is not a stall — it must not consume the
# escalation budget. ON by default (PILOT-63 AC2): the two pilots that motivated
# this signal ran with it OFF and it was wirkungslos, so a seat that had genuinely
# committed work still burned escalation budget on no-move rounds. The signal is
# safe to default-on because credit only WITHHOLDS a stall increment; it never
# resets the counter and never forces a spawn. Strong credit (source A) is the
# runner-VERIFIED commits: line — it cannot be forged. Set 0 to restore the
# pre-PILOT-63 always-count behaviour. ORCH_ESCALATION_WORK_BUDGET bounds the weak,
# self-asserted `progress:` credit (source B) at N times per ticket per run so a
# seat that only ASSERTS progress without producing artefacts is still parked.
ORCH_ESCALATION_WORK_CREDIT="${ORCH_ESCALATION_WORK_CREDIT:-1}"
ORCH_ESCALATION_WORK_BUDGET="${ORCH_ESCALATION_WORK_BUDGET:-3}"

# chain_index <status> — position in the canonical v3 chain; 0 = not a chain
# status (Backlog/Blocked/Needs PO Decision/v2 human gates never count toward
# bounces). Story chain 1..12, epic chain 21..29 (disjoint tickets, so the two
# ranges never compare against each other).
chain_index() {
    case "$1" in
        "Design") echo 1 ;; "Ready for Development") echo 2 ;; "In Progress") echo 3 ;;
        "In Review") echo 4 ;; "Security Review") echo 5 ;; "Test Prep") echo 6 ;;
        "In Test") echo 7 ;; "Design Test") echo 8 ;; "Story Acceptance") echo 9 ;;
        "Merging") echo 10 ;; "Docs") echo 11 ;; "Done") echo 12 ;;
        "PO Triage") echo 21 ;; "Grooming") echo 22 ;; "Enrichment") echo 23 ;;
        "Ticket Review") echo 24 ;; "Architecture Review") echo 25 ;;
        "Stories In Flight") echo 26 ;; "Epic Integration") echo 27 ;;
        "Ready for Epic Acceptance") echo 28 ;; "Epic Done") echo 29 ;;
        *) echo 0 ;;
    esac
}

# guard_chain_index <status> — chain_index, plus a guard-side supplement for
# out-of-chain human-gate stations that FOLD a mandatory station when jumped
# into (ABS-216). 'Ready for Human Acceptance' has no canonical chain_index
# (it is a v2 human gate, index 0), so an 'In Test -> Ready for Human Acceptance'
# hop was exempted by forward_skip_illegitimate even though it silently folds the
# mandatory Story Acceptance station (v2.24.0 smoke-gate Befund). Functionally
# RfHA sits between Story Acceptance (9) and Merging (10), so the guard treats it
# as index 10 for SKIP DETECTION ONLY: 'In Test (7) -> RfHA' now spans the
# mandatory Story Acceptance (9) and is flagged, while the legal 'Story Acceptance
# (9) -> RfHA' (9 -> 10, nothing mandatory strictly between) stays green and
# 'RfHA -> Ready for Merge/Merging/Done' (to an off-chain or same/higher index)
# stays untouched. The canonical chain_index — used for bounce counting and the
# high-water mark — is deliberately NOT changed.
guard_chain_index() {
    case "$1" in
        "Ready for Human Acceptance") echo 10 ;;
        *) chain_index "$1" ;;
    esac
}

# =============================================================================
# ABS-136 station-machine guard — reject illegitimate forward station skips
# =============================================================================
# Befund 6 (run ABS-126): a seat transitioned In Test -> Done in ONE hop,
# jumping the mandatory Story Acceptance / Merging / Docs seats; the operator
# had to reset the ticket. chain_index already orders the canonical chain but
# was only used for rework counting, never validation. This guard validates the
# ticket's most recent ACTUAL transition (parsed from the adapter dump, like
# rework_count — NOT the collapsed polling net event, so a legit multi-step
# traversal seen as a single net event is never mis-flagged) and redirects a
# forward jump that skips a mandatory seat to the first skipped mandatory
# station, with an audit comment (kind: skip, actor: orchestrator). A conditional
# stage (Design / Security Review / Test Prep / Design Test) stays legitimately
# skippable (ABS-84 SKIP-FORWARD) UNLESS the ticket carries its gating flag: a
# flag-set conditional station is mandatory-for-this-ticket and skipping it is
# flagged exactly like a mandatory station (ABS-247 — the guard reads the ticket
# flags it already dumps). Backward transitions (review bounces) and moves
# touching a chain_index-0 status (entry / human gates / cross-cutting) are never
# flagged.

# chain_status_at <idx> — inverse of chain_index (the canonical bijection).
chain_status_at() {
    case "$1" in
        1) echo "Design" ;; 2) echo "Ready for Development" ;; 3) echo "In Progress" ;;
        4) echo "In Review" ;; 5) echo "Security Review" ;; 6) echo "Test Prep" ;;
        7) echo "In Test" ;; 8) echo "Design Test" ;; 9) echo "Story Acceptance" ;;
        10) echo "Merging" ;; 11) echo "Docs" ;; 12) echo "Done" ;;
        21) echo "PO Triage" ;; 22) echo "Grooming" ;; 23) echo "Enrichment" ;;
        24) echo "Ticket Review" ;; 25) echo "Architecture Review" ;;
        26) echo "Stories In Flight" ;; 27) echo "Epic Integration" ;;
        28) echo "Ready for Epic Acceptance" ;; 29) echo "Epic Done" ;;
        *) echo "" ;;
    esac
}

# chain_station_mandatory <name> [active_flags] — 0 (true) when <name> must run
# for THIS ticket: an unconditional station always, OR a conditional station whose
# gating flag is present in the space-separated <active_flags> set (ABS-247). A
# conditional station with no matching flag is skippable (ABS-84 SKIP-FORWARD).
# conditional_flag_for is the single source of truth for which flag gates a stage.
chain_station_mandatory() {
    local cf; cf="$(conditional_flag_for "$1")"
    [ -z "$cf" ] && return 0                             # unconditional -> always mandatory
    case " ${2:-} " in *" $cf "*) return 0 ;; esac       # gating flag set -> mandatory (ABS-247)
    return 1                                             # conditional, unflagged -> skippable
}

# first_skipped_mandatory <from_idx> <to_idx> [active_flags] — echo the first
# MANDATORY chain station strictly between the two indices, or "" when every
# intermediate station is a skippable conditional stage (a legitimate ABS-84
# SKIP-FORWARD). With <active_flags> a flag-set conditional station counts as
# mandatory (ABS-247); without it (2-arg call) behaviour is unchanged.
first_skipped_mandatory() {
    local i=$(( $1 + 1 )) hi="$2" flags="${3:-}" name
    while [ "$i" -lt "$hi" ]; do
        name="$(chain_status_at "$i")"
        if [ -n "$name" ] && chain_station_mandatory "$name" "$flags"; then
            echo "$name"; return 0
        fi
        i=$(( i + 1 ))
    done
    echo ""
}

# forward_skip_illegitimate <from> <to> [active_flags] [from_idx] — 0 (true) when
# from->to is a FORWARD jump along ONE canonical chain range that skips at least one
# mandatory seat. <active_flags> (the ticket's conditional flags) makes a flag-set
# conditional station count as mandatory (ABS-247). <from_idx> overrides the source
# index for tickets whose ENTRY into the chain is not what its `from` status says —
# the pre-filled epic of ABS-271 (see prefilled_epic_entry_index); omitted (3-arg
# call) behaviour is unchanged.
forward_skip_illegitimate() {
    local fi ti flags="${3:-}"
    fi="${4:-$(guard_chain_index "$1")}"; ti="$(guard_chain_index "$2")"
    [ "$fi" -gt 0 ] && [ "$ti" -gt 0 ] || return 1     # entry / human / x-cutting: exempt
    [ "$ti" -gt "$fi" ] || return 1                    # backward or same: always allowed
    # ABS-266 MERGE BOUNDARY: `Docs` carries entered_when "Story merged"
    # (statuses.yaml), so a landing in Docs is BY DEFINITION post-merge — while
    # station order is a PRE-merge concern. Pulling a merged story back to In
    # Review re-spawns an implementer to rebuild already-merged code (ABS-234:
    # PO-accepted, QAS-green, HITL-merged, dragged backward 16s after the RTE
    # released it to Docs, because the RTE's move was recorded In Progress -> Docs).
    # Deliberately narrow — ONLY the Docs landing is exempt: In Test -> Done and
    # Merging -> Done stay flagged (ABS-136 Befund 6), and merge evidence at Done
    # stays enforced by done_pr_gate (ABS-211).
    if [ "$2" = "Docs" ]; then return 1; fi
    # story range 1..12 and epic range 21..29 are disjoint tickets — never mix.
    if { [ "$fi" -lt 20 ] && [ "$ti" -ge 20 ]; } || { [ "$fi" -ge 20 ] && [ "$ti" -lt 20 ]; }; then
        return 1
    fi
    [ -n "$(first_skipped_mandatory "$fi" "$ti" "$flags")" ]
}

# active_conditional_flags <ticket-dump> — the space-separated set of conditional
# gating flags (design/security/data) the ticket carries, for the flag-aware
# STATION-GUARD (ABS-247). Deliberately narrow to the three flags that gate a
# conditional station; skip-review/skip-test are a different (opt-OUT) gate.
active_conditional_flags() {
    local dump="$1" out="" f
    for f in design security data; do
        ticket_has_flag "$dump" "$f" && out="$out $f"
    done
    printf '%s' "${out# }"
}

# =============================================================================
# ABS-271 — the PRE-FILLED epic reaches its own Definition-of-Ready gate
# =============================================================================
# An epic whose children already exist at intake (classify_intake:
# `epic-with-children`) never traverses Grooming/Enrichment — those two stations
# exist to CREATE children, and its children are already there. But the DoR gate
# that follows them (`Ticket Review`, entered_when "Child tickets created" ->
# SPAWN qas, the ABS-107 batch review of all children) is exactly the station
# such an epic still owes: nothing has ever checked that its pre-filled children
# are actually ready.
#
# It never arrived there. ABS-214 added a `Backlog -> Stories In Flight` edge so a
# DECOMPOSED epic could rest in its JOIN state; a PRE-FILLED epic takes that same
# edge on its way in and lands PAST the gate — and STATION-GUARD could not see it,
# because `Backlog` has chain_index 0 and index-0 sources are exempt. Verified on
# the live epic ABS-278 (2026-07-13T22:03:05Z): `Backlog -> Stories In Flight` in
# ONE guard-exempt hop, 14 children released to Ready for Development, the DoR gate
# never run. The gate was only ever honoured by the PO seat's own diligence
# (ABS-245) — courtesy, not mechanism.
#
# The fix reuses the guard instead of adding a second gate: a pre-filled epic
# ENTERS the epic chain with decomposition already satisfied, so its guard-side
# source index is Enrichment's — the station right BEFORE the gate. Every forward
# hop that lands beyond `Ticket Review` therefore reads as a skip of a mandatory
# station and STATION-GUARD redirects it to `Ticket Review`, where the existing qas
# DoR batch review runs. No new gate, no new mechanism, no LLM.

# epic_visited_station <dump> <station> — 0 (true) when the epic has EVER been
# transitioned INTO <station>. Anchored to the "Transition: X -> Y." line the tracker
# writes (the same parse the rework counter and last_transition_pair use), so prose
# merely quoting a station name cannot arm it.
epic_visited_station() {
    printf '%s\n' "$1" | awk -v needle=" -> $2." '
        /^Transition: / && index($0, needle) > 0 { found = 1 }
        END { exit(found ? 0 : 1) }'
}

# Has the epic already run its DoR gate? Keeps ABS-214's JOIN-rest edge intact (a
# gate-passed epic re-entering Stories In Flight is NOT dragged back) and makes the
# guard's own redirect idempotent — once it lands at Ticket Review, it has visited it.
epic_passed_dor_gate() { epic_visited_station "$1" "Ticket Review"; }

# Is the epic DECOMPOSED rather than pre-filled? Grooming is the station that CREATES
# children (`Grooming` -> SPAWN bsa), so it is the one station a pre-filled epic —
# which has nothing to decompose — never visits.
epic_visited_grooming() { epic_visited_station "$1" "Grooming"; }

# prefilled_epic_entry_index <ticket> <dump> — echo the guard-side source index for
# an epic that arrived with children and still owes the DoR gate: Enrichment's index
# (decomposition satisfied by construction). Echo "" for every other ticket, so the
# guard falls back to the real `from` index. Ordered cheapest-first: the three dump
# reads settle it for every non-epic before the child-count adapter call is made.
#
# The Grooming test is load-bearing, not belt-and-braces. "Is an epic AND has children"
# is true of BOTH classes — a decomposed epic has children the moment bsa creates them
# — so without it the clamp fires on the decomposed class and the guard forgives the
# very station it exists to enforce (ABS-136/ABS-247 regression, caught in review).
prefilled_epic_entry_index() {
    local ticket="$1" dump="$2" count
    [ "$(fm_field "$dump" type)" = "epic" ] || { echo ""; return 0; }
    epic_passed_dor_gate "$dump" && { echo ""; return 0; }   # gate already run
    epic_visited_grooming "$dump" && { echo ""; return 0; }  # DECOMPOSED, not pre-filled
    count="$(tracker child-count "$ticket" 2>/dev/null || echo 0)"
    case "$count" in ''|*[!0-9]*) count=0 ;; esac
    [ "$count" -gt 0 ] || { echo ""; return 0; }             # empty epic: normal v3.0 path
    chain_index "Enrichment"
}

# last_transition_pair <dump> — echo "<from>\t<to>" of the most recent
# transition-reason comment ("Transition: X -> Y. Reason: ..."), or "" when the
# ticket has no recorded transition. Same parse the rework counter uses.
last_transition_pair() {
    printf '%s\n' "$1" | awk '
        /^Transition: / {
            line = $0; sub(/^Transition: /, "", line)
            p = index(line, " -> "); if (p == 0) next
            lf = substr(line, 1, p - 1)
            rest = substr(line, p + 4)
            q = index(rest, ". Reason:")
            lt = (q > 0 ? substr(rest, 1, q - 1) : rest)
        }
        END { if (lt != "") print lf "\t" lt }'
}

# operator_released_from_merge_gate <dump> — PILOT-67 AC4. 0 (true) when the MOST
# RECENT transition-reason comment is a NON-orchestrator actor (a human/operator)
# moving the ticket OUT of `Ready for Merge`. Used by docs_pr_gate to detect a
# manual operator release its own merge probe disagrees with: three such releases
# were silently bounced straight back to `Ready for Merge` (PILOT-34) because the
# probe falsely read the merged story as OPEN. The contradiction must be surfaced,
# not re-parked. Parses per-comment headers ("### ... | kind: ... | actor: ...")
# exactly like the other transition-reason readers.
operator_released_from_merge_gate() {
    printf '%s\n' "$1" | awk '
        /^### / {
            in_tr = ($0 ~ /kind: transition-reason/)
            cur_actor = ""
            if (match($0, /actor: /)) { cur_actor = substr($0, RSTART + 7); sub(/[ \t|].*$/, "", cur_actor) }
            next
        }
        in_tr && /^Transition: / {
            line = $0; sub(/^Transition: /, "", line)
            p = index(line, " -> ")
            last_from = (p > 0 ? substr(line, 1, p - 1) : "")
            last_actor = cur_actor
            in_tr = 0
        }
        END { exit (last_from == "Ready for Merge" && last_actor != "" && last_actor != "orchestrator" ? 0 : 1) }'
}

# station_guard <ticket> <to> — 0 (INTERVENED) when the ticket now rests in `to`
# and its most recent actual transition was an illegitimate forward station
# skip; posts an audit comment (live) and redirects to the first skipped
# mandatory station so the jumped seat runs. Returns 1 (no-op) otherwise. Dry-run
# logs the intent only (like skip_forward). Idempotent WHEN the redirect LANDS:
# the ticket's last transition is then a BACKWARD move, so it never re-fires. If
# the adapter REJECTS the redirect (the backward edge is missing from the status
# table), the guard does NOT report INTERVENED — it fails LOUDLY and returns 1 so
# the dispatcher is not trapped in a silent no-spawn loop (ABS-284 Defect 2): a
# rejected redirect leaves the ticket at the forward-skip landing, so reporting
# INTERVENED would suppress the spawn forever while the log reads as enforcement.
station_guard() {
    local ticket="$1" to="$2" dump flags pair lf lt target cf reason from_idx pre_idx
    [ "$(guard_chain_index "$to")" -gt 1 ] || return 1
    ticket_still_in "$ticket" "$to" || return 1
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    flags="$(active_conditional_flags "$dump")"          # flag-set conditional stages are mandatory (ABS-247)
    pair="$(last_transition_pair "$dump")"
    lf="${pair%%$'\t'*}"; lt="${pair##*$'\t'}"
    [ -n "$lf" ] && [ "$lt" = "$to" ] || return 1      # only guard the landing we just observed
    from_idx="$(guard_chain_index "$lf")"
    # ABS-271: a pre-filled epic entered the chain with decomposition already done,
    # so it is guarded from Enrichment's index onward — never from `Backlog`'s
    # index 0 (exempt) or from a pre-decomposition station it legitimately skipped.
    # The clamp only ever RAISES the source index, so an epic already past
    # Enrichment (e.g. bounced Ticket Review -> Grooming) keeps its real one.
    pre_idx="$(prefilled_epic_entry_index "$ticket" "$dump")"
    if [ -n "$pre_idx" ] && [ "$from_idx" -lt "$pre_idx" ]; then
        from_idx="$pre_idx"
    fi
    forward_skip_illegitimate "$lf" "$lt" "$flags" "$from_idx" || return 1
    target="$(first_skipped_mandatory "$from_idx" "$(guard_chain_index "$lt")" "$flags")"
    [ -n "$target" ] || return 1
    intent STATION-GUARD "$ticket" - "$target" "illegal-skip $lf->$lt"
    [ "$MODE" = "live" ] || return 0
    # Wording is truthful for BOTH classes: a truly mandatory station, or a
    # conditional station made mandatory-for-this-ticket by a set flag (ABS-247).
    # A conditional target can ONLY have been selected because its flag is set
    # (first_skipped_mandatory required it), so a non-empty cf proves the flag.
    cf="$(conditional_flag_for "$target")"
    if [ -n "$cf" ]; then
        reason="the conditional '$target' stage is mandatory for this ticket because it carries the '$cf' flag"
    else
        reason="the mandatory '$target' stage was skipped without a skip flag / SKIP-FORWARD entitlement"
    fi
    tracker comment "$ticket" --kind skip --actor orchestrator \
        --body "STATION-GUARD: transition '$lf' -> '$lt' skipped '$target' — $reason; redirecting to '$target' so the jumped seat runs (ABS-136, Befund 6 / run ABS-126; flag-conditional enforcement ABS-247)." \
        >/dev/null 2>&1 || log "station-guard comment failed on $ticket"
    if tracker transition "$ticket" "$target" --actor orchestrator \
        --reason "STATION-GUARD: '$lf' -> '$lt' skipped mandatory '$target' (ABS-136 / ABS-247)" \
        >/dev/null 2>&1; then
        return 0                                   # redirect LANDED -> genuine INTERVENED
    fi
    # ABS-284 Defect 2: the redirect was REJECTED (the status table lacks the
    # '$to' -> '$target' backward edge). Do NOT report INTERVENED — that would
    # suppress the seat spawn while the ticket stays parked at the forward-skip
    # landing, so the guard re-fires every visit forever (a silent permanent stall
    # that reads in the log as enforcement). Fail LOUDLY (log + run.log event +
    # a naming audit comment) and return 1 so the dispatcher does NOT suppress the
    # spawn — a visible failure regardless of which edge is missing.
    log "STATION-GUARD: redirect REJECTED on $ticket — status table lacks the '$to' -> '$target' edge; NOT intervening (would stall the ticket silently). Add the edge to profiles/neutral/adapters/statuses.yaml (ABS-284)."
    runlog STATION-GUARD-REJECTED "$ticket" - "$target" "rejected-edge $to->$target"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "STATION-GUARD could NOT enforce: the redirect '$to' -> '$target' was rejected by the status adapter (edge missing from the transition table). The mandatory '$target' stage was skipped and the guard cannot repair it — surfacing loudly instead of silently stalling the ticket (ABS-284; add the '$to' -> '$target' edge to profiles/neutral/adapters/statuses.yaml)." \
        >/dev/null 2>&1 || log "station-guard rejection comment failed on $ticket"
    return 1
}

# =============================================================================
# ABS-211 done-gate — a story reaches Done only when its implementation PR is
# MERGED on the target (epic) branch
# =============================================================================
# ABS-192 (epic ABS-190): a story reached Done while its implementation PR #133
# was still open; the epic JOIN fired on that FALSE signal and the rte had to
# block Epic Integration until the operator merged the PR and resumed. ABS-202
# was the sibling case (PR #129 skipped Merging entirely). The Docs seat only
# validates doc-completeness, so a Done with an unmerged PR was never caught.
#
# done_pr_gate is the deterministic fail-CLOSED backstop: it mirrors
# station_guard (post-landing, idempotent, MODE-aware) and, whenever a ticket
# rests in Done with a still-open PR, redirects it back to Merging with a naming
# gate-results comment BEFORE the epic JOIN can fire (the redirect is wired into
# dispatch ahead of join_check_epic). It is fail-OPEN for the boilerplate
# placeholder case: no $FORGE_CMD (no platform) or no PR for the story
# (direct-to-branch merge) -> the check is skipped and Done passes unchanged
# (AC2 + the PO guardrail). ADR-A-0004/0005 merge rights are untouched — the
# gate never merges anything, it only refuses a premature Done.

# forge <args...> — resolve $FORGE_CMD into a runnable command (same script-path
# / PATH-command shapes as tracker()). No-op (rc 0, no output) when unset.
forge() {
    # shellcheck disable=SC2206
    local words=($FORGE_CMD)
    local cmd="${words[0]:-}"
    [ -n "$cmd" ] || return 0
    if [ -f "$cmd" ]; then
        bash "${words[@]}" "$@"
    else
        "${words[@]}" "$@"
    fi
}

# story_pr_state <ticket> — the merge state of the story's implementation PR via
# the forge seam. Prints "STATE\tREF": STATE normalized to MERGED | DECLINED |
# OPEN | NONE, REF the PR identifier the adapter reported ("" when absent). NONE
# when no forge is configured or the adapter reports no PR (direct-to-branch).
# A closed-without-merge PR (the adapter's DECLINED) surfaces as DECLINED so the
# merge-wait gate can escalate a story resting on a merge that can no longer land
# (PILOT-20); every other live, non-merged state (open / superseded) normalizes
# to OPEN so the gate still fails closed on anything that is not a clean merge.
# DECLINED is a superset of the old OPEN bucket for all *-merged consumers
# (merge_wait_release fires only on MERGED, ready_for_merge_mr_gate only on NONE,
# done_pr_gate on neither MERGED nor NONE) — so their behavior is unchanged.
story_pr_state() {
    [ -n "$FORGE_CMD" ] || { printf 'NONE\t'; return 0; }
    local raw state ref
    raw="$(forge pr-state "$1" 2>/dev/null | head -1)"
    state="$(printf '%s' "$raw" | awk '{print toupper($1)}')"
    ref="$(printf '%s' "$raw" | awk '{print $2}')"
    case "$state" in
        MERGED)             printf 'MERGED\t%s' "$ref" ;;
        DECLINED)           printf 'DECLINED\t%s' "$ref" ;;
        ""|NONE|NOTFOUND)   printf 'NONE\t' ;;
        *)                  printf 'OPEN\t%s' "$ref" ;;
    esac
}

# story_branch_remote_state <ticket> — ABS-481. Does the story branch
# <ticket>-auto EXIST on the ACTIVE remote? This is the never-pushed case the
# ABS-454 MR probe (story_pr_state) misses: that probe asks the forge MIRROR, so a
# branch that was committed locally but never pushed — no remote branch, hence no
# MR — reads as NONE only when a mirror is configured AND reachable. When $FORGE_CMD
# is unset, or the mirror host is down (the GitLab-fallback era, Bitbucket down),
# the MR probe cannot see the gap at all and the story rests human-invisibly at the
# merge gate with nothing to merge (regression: ABS-461, 2026-07-19).
#
# We answer straight from git against the remotes actually configured — never a
# hardcoded host, so the GitLab fallback is covered — and prints exactly one of:
#   FOUND       the branch exists on at least one REACHABLE remote.
#   ABSENT      >=1 remote answered AND none carry the branch — the never-pushed /
#               lost-push defect: self-heal it (AC1).
#   UNREACHABLE remotes are configured but NONE answered (degraded connectivity):
#               we cannot prove absence, so the caller fails LOUD, never silent-pass
#               (AC2) — reporting FOUND here would resurrect the very silent-pass bug.
#   NOREMOTE    no git remote configured (boilerplate placeholder / mock env) —
#               fail-open, the caller falls through to the MR-probe path.
# Every probe is bounded by _bounded_git (the same hard wall-clock ceiling the
# ABS-355 fresh-base path uses), so a down HTTPS remote cannot hang the sweep.
story_branch_remote_state() {
    local ticket="$1" branch="$1-auto" repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    local probe_to="${ORCH_REMOTE_PROBE_TIMEOUT:-12}" r out rc reached=0 nremotes=0
    for r in $(git -C "$repo" remote 2>/dev/null || true); do
        nremotes=$((nremotes + 1))
        out="$(_bounded_git "$probe_to" "$repo" ls-remote --heads "$r" "$branch" 2>/dev/null)"; rc=$?
        [ "$rc" -eq 0 ] || continue          # this remote is unreachable/errored -> skip it
        reached=1
        if [ -n "$out" ]; then printf 'FOUND'; return 0; fi
    done
    if [ "$nremotes" -eq 0 ]; then printf 'NOREMOTE'; return 0; fi
    if [ "$reached" -eq 1 ]; then printf 'ABSENT'; else printf 'UNREACHABLE'; fi
}

# story_merge_target_branch <ticket> <remote> — ABS-537. The story's DECLARED
# (primary) MR target: the parent's epic INTEGRATION branch epic/<parent>-*
# (ADR-A-0014) when the tracker names a parent, else main. Defined as the FIRST
# candidate of story_merge_target_branches so the two never drift. Used for the
# mergeability dry-run (story_mergeability / merge_conflict_fp), where the declared
# target is what a rebase would land on; the merged-ness probe uses the FULL set.
story_merge_target_branch() {
    story_merge_target_branches "$1" "$2" | head -1
}

# story_merge_target_branches <ticket> <remote> — PILOT-67. EVERY branch the
# story's MR could plausibly TARGET, one per line, most-specific first: the
# parent's epic integration branch (when a parent is named), main (always), and
# EVERY epic integration branch present. AC1: a PARENTLESS story can still be
# merged into an epic branch (PILOT-34 -> !196 into epic/PILOT-28-poll-to-push),
# so the epic branches are ALWAYS candidates — independent of whether the ticket
# carries a parent field. The epic name is resolved exactly like the ABS-119
# worktree base pick (lexicographically first match across local heads AND the
# active remote's tracking refs), never a new naming convention. AC2: the epic
# refs are FETCHED before they are listed, so a stale/missing local tracking ref
# never silently hides a target (the old resolver fell back to main whenever the
# tracking ref was absent). Deduped, order-preserving.
story_merge_target_branches() {
    local ticket="$1" remote="$2" repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    local probe_to="${ORCH_REMOTE_PROBE_TIMEOUT:-12}" parent
    parent="$(tracker get "$ticket" 2>/dev/null | sed -n 's/^parent: //p' | head -1 || true)"
    # AC2: refresh the epic tracking refs from the active remote BEFORE resolving
    # names, so resolution reads the true remote state instead of a stale ref.
    _bounded_git "$probe_to" "$repo" fetch -q "$remote" \
        "refs/heads/epic/*:refs/remotes/$remote/epic/*" >/dev/null 2>&1 || true
    {
        if [ -n "$parent" ]; then
            git -C "$repo" for-each-ref --format='%(refname:short)' \
                "refs/heads/epic/$parent-*" "refs/remotes/$remote/epic/$parent-*" 2>/dev/null \
                | sed "s#^$remote/##" | LC_ALL=C sort -u | head -1
        fi
        printf '%s\n' "$ORCH_LOCAL_MAIN_BRANCH"
        git -C "$repo" for-each-ref --format='%(refname:short)' \
            "refs/heads/epic/*" "refs/remotes/$remote/epic/*" 2>/dev/null \
            | sed "s#^$remote/##" | LC_ALL=C sort -u
    } | awk 'NF && !seen[$0]++'
}

# story_git_merge_state <ticket> — PILOT-4. The forge-LESS merge probe: is the
# story branch <ticket>-auto merged into ANY branch its MR could target on the
# ACTIVE push remote, answered straight from git ancestry? PILOT-67: the head is
# checked against EVERY candidate (story_merge_target_branches — main AND every
# epic integration branch), so a parentless story merged into an epic branch is
# MERGED even though its declared target is main. ABS-537's single-target probe
# (epic child -> epic branch, parentless -> main) read such a head OPEN forever
# (its head lived only in epic/*), so all 5 PILOT-5 stories sat a whole night in
# 'Ready for Merge' after their MRs were human-merged (v3-pilot #3 finding), and
# PILOT-34 bounced three operator releases. Ancestry into main is one candidate in
# the set, so it still covers an epic branch integrated to main and then deleted.
# This is the pilot-lane analogue of story_pr_state:
# the pilot lane runs no $FORGE_CMD, so the docs_pr_gate / merge_wait_release
# merge-wait park+resume (ABS-270) could never fire there — a green story waiting
# on a human merge spawned the tech-writer, who could only refuse Done and rest,
# which the runner misread as an ABS-132 stuck loop and escalated to the PO
# (ABS-494 v3-pilot finding: 2 futile respawns + a false escalation + a PO
# Blocked-park for a plain human-merge wait). It uses exactly the check the
# docs-station skill (ABS-457) and the PILOT-1 PO escalation use —
# `merge-base --is-ancestor` against the active remote's copy of the target
# branch (resolve_active_main_ref, PILOT-3 — never a hardcoded origin) — so it
# works with no forge at all.
#
# Prints "STATE\tREF" like story_pr_state (MERGED | OPEN | NONE):
#   MERGED\t<sha>  the story branch head IS an ancestor of the active-remote
#                  target branch (or of main, for the integrated-epic fallback).
#   OPEN\t<sha>    the branch exists but is NOT yet an ancestor (merge still owed).
#   NONE\t         no story branch anywhere, or git is unavailable -> fail-OPEN, so
#                  the caller proceeds exactly as before (no false park/release).
# The branch head is taken from the runner's LOCAL ref first (it survives a
# post-merge remote-branch delete), falling back to the remote head. The remote
# main tip is refreshed under _bounded_git so a down HTTPS host cannot hang the
# sweep; containment is tested against the remote-tracking ref, NEVER local HEAD (a
# stale local checkout never contains the human merge — the ABS-452 stale-HEAD trap).
story_git_merge_state() {
    local ticket="$1" branch="$1-auto" repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    local probe_to="${ORCH_REMOTE_PROBE_TIMEOUT:-12}" active remote main sha candidates cand
    local have_target=0 evref=""
    command -v git >/dev/null 2>&1 || { printf 'NONE\t'; return 0; }
    active="$(resolve_active_main_ref "$ORCH_LOCAL_MAIN_BRANCH" "$repo")"   # e.g. gitlab/main
    remote="${active%%/*}"; main="${active#*/}"
    sha="$(git -C "$repo" rev-parse --verify -q "refs/heads/$branch" 2>/dev/null || true)"
    [ -n "$sha" ] || sha="$(_bounded_git "$probe_to" "$repo" ls-remote --heads "$remote" "$branch" 2>/dev/null | awk 'NR==1{print $1}')"
    # PILOT-67 (AC1): probe EVERY plausible target — main AND every epic integration
    # branch — regardless of the parent field. story_merge_target_branches already
    # fetched the epic tracking refs (AC2); refresh main once more here.
    candidates="$(story_merge_target_branches "$ticket" "$remote")"
    _bounded_git "$probe_to" "$repo" fetch -q "$remote" "$main" >/dev/null 2>&1 || true
    # ABS-596: walk each candidate target ONCE and answer from the STRONGEST evidence
    # available, so a merge is recognised even after the source branch is deleted:
    #   (a) git ancestry — the head is an ancestor of the target (needs the branch
    #       head; PILOT-67 primary signal). Precise while the ref survives.
    #   (b) branch-INDEPENDENT: the MERGE COMMIT the merge left IN THE TARGET naming
    #       the source branch ("Merge branch '<ticket>-auto'…" on GitLab, "Merged in
    #       <ticket>-auto…" on Bitbucket). This survives a post-merge source-branch
    #       delete (the ABS-596 defect). The old probe knew only (a), so once GitLab
    #       auto-deleted <ticket>-auto after the merge the head could not be found and
    #       the story read 'not merged' and parked at a human gate. --merges + the
    #       branch token keeps this precise: a plain commit that merely MENTIONS the
    #       ticket id is not a merge commit and never matches (a self-hosting repo's
    #       own history discusses ids and -auto branch names in prose — matching the
    #       bare id there falsely read unrelated tickets MERGED, ABS-596 iteration).
    # have_target records whether ANY target ref was actually reachable, so an
    # unreachable evidence source becomes a NAMED 'unknown' (AC3), never a silent
    # 'not merged'. The printed REF names WHICH ref/source decided it (AC4).
    while IFS= read -r cand; do
        [ -n "$cand" ] || continue
        git -C "$repo" rev-parse --verify -q "refs/remotes/$remote/$cand" >/dev/null 2>&1 || continue
        have_target=1
        if [ -n "$sha" ] && git -C "$repo" merge-base --is-ancestor "$sha" "$remote/$cand" 2>/dev/null; then
            printf 'MERGED\t%s (ancestor of %s/%s)' "$sha" "$remote" "$cand"; return 0
        fi
        evref="$(git -C "$repo" log --merges -1 --format='%H' -F --grep="$branch" "$remote/$cand" 2>/dev/null || true)"
        if [ -n "$evref" ]; then
            printf 'MERGED\t%s (merge commit for %s in %s/%s)' "$evref" "$branch" "$remote" "$cand"; return 0
        fi
    done <<EOF
$candidates
EOF
    if [ "$have_target" -eq 0 ]; then
        # AC3: not a single target ref on the active remote was reachable, so the
        # evidence source needed to decide is GONE. Report a named UNKNOWN that says
        # WHICH source is missing — never the misleading silent 'not merged' that
        # parks the story like a human merge gate.
        printf 'UNKNOWN\tno target ref reachable on %s to decide merge state (targets: %s)' \
            "$remote" "$(printf '%s' "$candidates" | tr '\n' ' ' | sed 's/  */ /g;s/ *$//')"
        return 0
    fi
    [ -n "$sha" ] && { printf 'OPEN\t%s' "$sha"; return 0; }   # branch exists, genuinely not merged yet
    printf 'NONE\t'   # no story branch AND no merge trace in any target -> fail-open, as before
}

# story_merge_state <ticket> — the unified merge-state probe used by the merge-wait
# gates (PILOT-4). With a $FORGE_CMD configured (Jira lane) it asks the forge/mirror
# (story_pr_state, unchanged); with none configured (pilot lane) it falls back to the
# forge-less git-ancestry check (story_git_merge_state). Both print "STATE\tREF" with
# the same MERGED | OPEN | NONE vocabulary, so the callers are lane-agnostic.
story_merge_state() {
    if [ -n "$FORGE_CMD" ]; then story_pr_state "$1"; else story_git_merge_state "$1"; fi
}

# story_mergeability <ticket> — PILOT-18. Is the story's OPEN MR still mergeable
# into its target branch, or did a FOREIGN merge just conflict it? The merged-ness
# probes above only check ancestry (is it merged yet), never mergeability — so a
# story resting at the human merge gate whose MR was broken by another merge (the
# !159-after-!158 migration-number collision, v3-pilot #3) was human-invisible.
# Prints exactly ONE token:
#   CONFLICT  the MR cannot merge cleanly — a seat must rebase + resolve.
#   CLEAN     merges cleanly (or already merged) — the legitimate merge-wait rest.
#   UNKNOWN   cannot be determined -> the caller takes NO action (fail-open, so a
#             degraded host or old git never triggers a false redirect — AC2).
# Forge lane ($FORGE_CMD): reads the adapter's canonical `mergeable=BOOL` field.
# The git-host-adapter seam owns the mapping (GitLab detailed_merge_status
# conflict/cannot_be_merged, Bitbucket `mergeable`) onto that one boolean — the
# orchestrator stays host-agnostic ("Adapter-Seam für den Status-Feldnamen").
# Costs the single `forge pr-state` call the ticket budgets ("1 API-Call je
# wartendem MR"). Pilot lane (no forge): a hermetic `git merge-tree` dry-run of
# <ticket>-auto into its target on the active remote — the very probe the operator
# ran by hand on !159 (2026-07-22). Already-merged (ancestor) short-circuits CLEAN.
story_mergeability() {
    local ticket="$1"
    if [ -n "$FORGE_CMD" ]; then
        local raw m
        raw="$(forge pr-state "$ticket" 2>/dev/null | head -1)"
        m="$(printf '%s\n' "$raw" | tr ' ' '\n' | sed -n 's/^mergeable=//p' | head -1 | tr 'A-Z' 'a-z')"
        case "$m" in
            false) printf 'CONFLICT' ;;
            true)  printf 'CLEAN' ;;
            *)     printf 'UNKNOWN' ;;   # field absent / no MR -> undecidable, fail-open
        esac
        return 0
    fi
    # Pilot lane — forge-less git merge-tree dry-run (mirrors story_git_merge_state).
    command -v git >/dev/null 2>&1 || { printf 'UNKNOWN'; return 0; }
    local branch="$ticket-auto" repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    local probe_to="${ORCH_REMOTE_PROBE_TIMEOUT:-12}" active remote target sha ttip rc=0
    active="$(resolve_active_main_ref "$ORCH_LOCAL_MAIN_BRANCH" "$repo")"
    remote="${active%%/*}"
    sha="$(git -C "$repo" rev-parse --verify -q "refs/heads/$branch" 2>/dev/null || true)"
    [ -n "$sha" ] || sha="$(_bounded_git "$probe_to" "$repo" ls-remote --heads "$remote" "$branch" 2>/dev/null | awk 'NR==1{print $1}')"
    [ -n "$sha" ] || { printf 'UNKNOWN'; return 0; }   # no branch -> nothing to judge
    target="$(story_merge_target_branch "$ticket" "$remote")"
    _bounded_git "$probe_to" "$repo" fetch -q "$remote" "$target" >/dev/null 2>&1 || true
    ttip="$(git -C "$repo" rev-parse --verify -q "refs/remotes/$remote/$target" 2>/dev/null || true)"
    [ -n "$ttip" ] || { printf 'UNKNOWN'; return 0; }
    if git -C "$repo" merge-base --is-ancestor "$sha" "$ttip" 2>/dev/null; then
        printf 'CLEAN'; return 0                         # already merged -> not a conflict
    fi
    # ABS-225 ID-collision guard (v3-pilot #4): only probe a branch that GENUINELY
    # belongs to THIS story — one whose commits ahead of the target carry a
    # `[<ticket>]` tag (the SAFe commit format every story commit follows). A
    # foreign branch that merely SHARES the `<id>-auto` name — e.g. a real
    # `DEMO-1-auto` from unrelated work colliding with a test ticket id — carries
    # no such tag; treat it as UNKNOWN so its unrelated divergence never fires a
    # false CONFLICT redirect (it did: e7a704fb probed a real DEMO-1-auto and
    # broke 3 test-orchestrator.sh assertions at the PILOT-17 epic gate).
    if ! git -C "$repo" log --grep="[$ticket]" --fixed-strings -1 \
            --format=%H "$ttip..$sha" 2>/dev/null | grep -q .; then
        printf 'UNKNOWN'; return 0
    fi
    # git >=2.38 `merge-tree --write-tree`: exit 0 clean, 1 conflicted, other = could
    # not run (e.g. option unsupported on older git) -> UNKNOWN, never a false CONFLICT.
    git -C "$repo" merge-tree --write-tree "$ttip" "$sha" >/dev/null 2>&1 || rc=$?
    case "$rc" in
        0) printf 'CLEAN' ;;
        1) printf 'CONFLICT' ;;
        *) printf 'UNKNOWN' ;;
    esac
}

# done_pr_gate <ticket> <to> — 0 (INTERVENED) when the ticket now rests in Done
# but its implementation PR is not yet MERGED; posts a naming gate-results
# comment (live) and redirects it back to Merging so the PR merges before Done.
# Returns 1 (no-op) when to != Done, no forge is configured, the ticket already
# moved on, or the PR is MERGED / absent (fail-open placeholder case). Dry-run
# logs the intent only. Idempotent WHEN the redirect LANDS: the ticket then rests
# in Merging, so a later Done landing only re-fires if the PR is STILL open. If the
# adapter REJECTS the 'Done' -> 'Merging' redirect (edge missing from the table),
# the gate does NOT report INTERVENED — it fails LOUDLY and returns 1 rather than
# trapping the runner in a silent no-spawn loop while the false-signal Done stands
# (ABS-284 Defect 2).
done_pr_gate() {
    local ticket="$1" to="$2" pair state ref
    [ "$to" = "Done" ] || return 1
    [ -n "$FORGE_CMD" ] || return 1        # no forge platform -> placeholder skip (AC2/guardrail)
    ticket_still_in "$ticket" "$to" || return 1
    pair="$(story_pr_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    case "$state" in
        MERGED|NONE) return 1 ;;           # merged (AC2) or no PR (direct-to-branch) -> allow
    esac
    intent DONE-PR-GATE "$ticket" - "Merging" "unmerged-pr ${ref:-?} state=$state"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "DONE-GATE: story reached 'Done' while its implementation PR ${ref:+$ref }is '$state' (not merged on the target/epic branch). Redirecting to 'Merging' so the PR is merged before Done — a Done with an open PR is a false signal for the epic JOIN (ABS-211; recurrence of ABS-192 PR #133, ABS-202 PR #129)." \
        >/dev/null 2>&1 || log "done-pr-gate comment failed on $ticket"
    if tracker transition "$ticket" "Merging" --actor orchestrator \
        --reason "DONE-GATE: implementation PR ${ref:-(unknown)} not merged ($state) — redirect Done -> Merging (ABS-211)" \
        >/dev/null 2>&1; then
        return 0                                   # redirect LANDED -> genuine INTERVENED
    fi
    # ABS-284 Defect 2: the 'Done' -> 'Merging' redirect was REJECTED (edge absent
    # from the table). Reporting INTERVENED here would suppress the spawn while the
    # story sits in Done with an open PR — the gate re-fires forever silently and
    # the epic JOIN is left free to fire on the false signal (the exact ABS-192 /
    # ABS-202 defect this gate exists to stop). Fail LOUDLY (log + run.log event +
    # naming audit comment) and return 1 so the dispatcher is not trapped in a
    # silent no-spawn loop: a visible failure, not a phantom intervention.
    log "DONE-GATE: redirect REJECTED on $ticket — status table lacks the 'Done' -> 'Merging' edge; NOT intervening (would stall the ticket silently). Add the edge to profiles/neutral/adapters/statuses.yaml (ABS-284)."
    runlog DONE-PR-GATE-REJECTED "$ticket" - "Merging" "rejected-edge Done->Merging"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "DONE-GATE could NOT enforce: the redirect 'Done' -> 'Merging' was rejected by the status adapter (edge missing from the transition table). The story rests in 'Done' with PR ${ref:+$ref }'$state' (not merged) — surfacing loudly instead of silently stalling (ABS-284; add the 'Done' -> 'Merging' edge to profiles/neutral/adapters/statuses.yaml)." \
        >/dev/null 2>&1 || log "done-pr-gate rejection comment failed on $ticket"
    return 1
}

# =============================================================================
# ABS-270 merge-wait rest — "story correct, PR open, waiting on the human"
# =============================================================================
# done_pr_gate (above) refuses a Done whose PR is not merged. That gate is right,
# but the state it NECESSARILY produces had no resting place: a story whose
# pipeline is fully green and whose PR only awaits the HUMAN merge landed in
# `Docs` — a SPAWN-triggering station. The tech-writer seat correctly refused the
# Done transition (the seat-side mirror of done_pr_gate), had nothing else to do,
# and rested; the runner read two consecutive no-move respawns as an ABS-132 stuck
# loop and escalated to `Needs PO Decision` — routing a HUMAN merge wait to the PO,
# who has no merge authority at all (human-only #2, ADR-A-0005). Measured on
# ABS-253 (PR #173): two tech-writer spawns + one po-agent spawn burnt to discover
# that a human had not clicked merge; ABS-250 (PR #174) was queued in the same loop.
#
# #PATH_DECISION (ABS-270) — CHOSEN: option 1, the Docs-station precondition.
# The runner does not spawn the tech-writer while the story's PR is unmerged; it
# rests the story at `Ready for Merge` — the status that ALREADY means exactly
# this (class: resting, human-owned merge gate, statuses.yaml) and that the runner
# already treats correctly on the three axes this needs:
#   map_action              -> NOOP   (no seat is spawned there)
#   is_reconcilable_status  -> false  (no sweep re-derive => no respawn => nothing
#                                      for the ABS-132 no-move counter to count)
#   is_legit_rest_status    -> true   (the stuck detector does not flag it)
# So the fix is a park + a release edge — no new status, no new counter, no
# exemption in the escalation logic. It also makes the wait VISIBLE in the status
# itself ("Ready for Merge" = the human owes a merge) instead of disguising it as
# a tech-writer at work.
#
# REJECTED (the ticket's other two options):
#   2. Exempt "no-move with an open PR" from the ABS-132 respawn count — stops the
#      escalation but still spawns a tech-writer every reconcile cadence that can
#      only refuse and rest. Fixes the symptom, keeps the cost.
#   3. Route the escalation to the human instead of the PO — right addressee, wrong
#      layer: it still treats a LEGITIMATE rest as an escalation. Its useful half is
#      kept: the park fires ONE human notification (the merge is human-only,
#      ADR-A-0005) instead of an escalation.
# Both leave `Docs` as the resting place of a story that is not doing Docs work —
# the root defect.
#
# Deliberately the same shape as done_pr_gate: post-landing, idempotent, MODE-aware,
# fail-OPEN in the placeholder case (no $FORGE_CMD / no PR -> unchanged, the
# tech-writer spawns as before). The two gates are complementary: docs_pr_gate keeps
# the story OUT of Docs until the merge lands; done_pr_gate remains the fail-closed
# backstop that keeps it out of Done (so the ABS-192 epic-JOIN poisoning stays fixed).

# docs_pr_gate <ticket> <to> — 0 (INTERVENED) when the ticket landed in `Docs` while
# its implementation PR is not yet MERGED: audits it, notifies the human whose merge
# it waits on, and rests it at `Ready for Merge` WITHOUT spawning the tech-writer.
# Returns 1 (no-op) when to != Docs, the ticket already moved on, or the PR is
# MERGED / absent — then Docs proceeds exactly as before. PILOT-4: the merge state
# now comes from story_merge_state, so this fires in the pilot lane too (no forge —
# the ABS-494 finding) via the forge-less git-ancestry check; the placeholder case
# (no forge AND no story branch) still reads NONE -> fail-OPEN, Docs proceeds.
docs_pr_gate() {
    local ticket="$1" to="$2" pair state ref dump
    [ "$to" = "Docs" ] || return 1
    ticket_still_in "$ticket" "$to" || return 1
    pair="$(story_merge_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    case "$state" in
        MERGED|NONE) return 1 ;;           # merged, or no PR/branch -> Docs proceeds
    esac
    # PILOT-67 AC4: if an operator MANUALLY released this story out of the merge
    # gate and our probe still reads it unmerged, the two DISAGREE — surface it
    # loudly instead of silently re-parking it to `Ready for Merge` (three such
    # releases bounced straight back on PILOT-34). Respect the operator: let Docs
    # proceed (done_pr_gate stays the fail-closed Done backstop) and post a visible
    # conflict comment + notification so the contradiction is human-visible.
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    if operator_released_from_merge_gate "$dump"; then
        intent MERGE-WAIT-CONFLICT "$ticket" - "$to" "operator-release-vs-probe=$state ref=${ref:-?}"
        [ "$MODE" = "live" ] || return 1
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "MERGE-WAIT CONFLICT: an operator manually released $ticket out of 'Ready for Merge', but the runner's merge probe reads its PR ${ref:+$ref }as '$state' (not merged on any target/epic branch). NOT silently re-parking it — the operator's release stands and 'Docs' proceeds; done_pr_gate remains the fail-closed backstop that keeps it out of 'Done' until the merge actually lands. If the probe is wrong, this is the PILOT-34 target-resolution class — check that the story's real MR target (main OR an epic integration branch) is reachable on the active push remote (PILOT-67 AC4)." \
            >/dev/null 2>&1 || log "merge-wait conflict comment failed on $ticket"
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "merge-wait CONFLICT on $ticket: operator released it from the merge gate but the runner probe still reads it '$state' (not merged). Not re-parking — verify whether the PR ${ref:-(unknown)} is actually merged on its target/epic branch (PILOT-67)."
        return 1
    fi
    # ABS-596 AC3: the probe could NOT decide (the evidence source is gone — e.g. the
    # source branch was deleted post-merge AND the target ref was unreachable). Do NOT
    # disguise this as 'not merged'. Rest at the human-owned merge gate with a message
    # that NAMES the missing evidence source ($ref, AC4), and re-probe each sweep —
    # merge_wait_release releases it the moment the state resolves to MERGED, so a
    # transient unreachability self-heals. done_pr_gate stays the fail-closed backstop.
    if [ "$state" = "UNKNOWN" ]; then
        intent MERGE-WAIT-UNKNOWN "$ticket" - "Ready for Merge" "merge-state-unknown ${ref:-?}"
        [ "$MODE" = "live" ] || return 0
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "MERGE-STATE UNKNOWN: the runner could NOT determine whether $ticket's implementation is merged — $ref. This is NOT a 'not merged' verdict: the evidence source is unavailable (the classic ABS-596 case is a source branch auto-deleted after the merge, with the target branch briefly unreachable). Resting at 'Ready for Merge' and RE-PROBING each sweep — the story releases to 'Docs' on its own the moment the merge state can be read; no operator step is needed unless it never resolves. done_pr_gate remains the fail-closed backstop that keeps it out of 'Done' until the merge is confirmed." \
            >/dev/null 2>&1 || log "merge-state-unknown comment failed on $ticket"
        tracker transition "$ticket" "Ready for Merge" --actor orchestrator \
            --reason "MERGE-STATE UNKNOWN: cannot confirm merge for $ticket — $ref. Resting at the merge gate and re-probing (ABS-596), not silently reading 'not merged'." \
            >/dev/null 2>&1 || log "merge-state-unknown transition failed on $ticket"
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "merge-state UNKNOWN on $ticket: $ref. Re-probing each sweep; releases automatically once the state can be read (ABS-596). Verify the merge manually only if it never resolves."
        return 0
    fi
    intent MERGE-WAIT "$ticket" - "Ready for Merge" "unmerged-pr ${ref:-?} state=$state"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "MERGE-WAIT: story reached 'Docs' while its implementation PR ${ref:+$ref }is '$state' (not merged on the target/epic branch). Nothing is stuck: the pipeline is green and the story is WAITING ON A HUMAN MERGE (human-only #2, ADR-A-0005). Resting it at 'Ready for Merge' instead of spawning the tech-writer, which could only refuse the Done transition (done_pr_gate, ABS-211) and rest — which the runner then misread as an ABS-132 stuck loop. Once the PR is merged the runner releases the story back to 'Docs' automatically, no manual step needed (ABS-270)." \
        >/dev/null 2>&1 || log "merge-wait comment failed on $ticket"
    tracker transition "$ticket" "Ready for Merge" --actor orchestrator \
        --reason "MERGE-WAIT: implementation PR ${ref:-(unknown)} not merged ($state) — waiting on human merge; resting at the human-owned merge gate until it lands (ABS-270)" \
        >/dev/null 2>&1 || log "merge-wait transition failed on $ticket"
    notify "${ORCH_NOTIFY_TICKET:-$ticket}" "waiting on human merge: $ticket is pipeline-green and its PR ${ref:-(unknown)} is $state — merge it and the runner finishes the story on its own (ABS-270)"
    return 0
}

# ABS-537 (v3-pilot #3 retro, finding #7): the origin filter that used to live
# here (parked_at_merge_gate — release only when the LAST transition into
# `Ready for Merge` came from Docs or Merging) is GONE. The wait posture is now
# armed by ENTERING `Ready for Merge` at all, no matter over which path: the
# MERGE-TOKEN-RELEASE edge, a seat handoff, a human transition, or a seeded
# ticket never armed the old marker-parsing filter, so a merged story could
# rest at the gate forever with the release blind to it. Every ticket resting
# at `Ready for Merge` is a merge wait by definition of the station (map_action
# NOOP, human-owned merge gate); a MERGED probe therefore always releases it to
# `Docs`, and an OPEN/NONE probe always keeps it resting — the probe, not the
# arrival path, is the gate. (The former Path-A RfHA-origin exclusion falls
# with this: after the human merge its continuation is the same Docs seat.)

# merge_wait_release <ticket> <status> — the other half of the park (AC4): a story
# resting at the human-owned merge gate continues ON ITS OWN once the human merges.
# Runs for every ticket in the reconcile sweep, because `Ready for Merge` is
# deliberately NOT reconcilable (that is precisely why resting there costs no spawns)
# and dispatch therefore never re-derives it. ABS-537: it covers EVERY resting
# ticket at `Ready for Merge`, regardless of arrival path (see the arming note
# above) — the docs_pr_gate park, the Merging-origin rest (PILOT-2 3h stall),
# the Path-A human gate, and any other entry into the station.
# When such a story has a MERGED PR (story_merge_state — forge in the Jira
# lane, forge-less git ancestry in the pilot lane), it is transitioned back to
# `Docs`; the next poll dispatches that landing, the
# tech-writer spawns as normal, and (its PR now merged) done_pr_gate lets it reach
# Done. --expect-from makes a lost race with a human a logged NOOP (ABS-198).
# 0 = released, 1 = no-op (every other ticket, so the human gate keeps resting).
merge_wait_release() {
    local ticket="$1" status="$2" pair state ref
    [ "$status" = "Ready for Merge" ] || return 1
    pair="$(story_merge_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    [ "$state" = "MERGED" ] || return 1
    intent MERGE-WAIT-RELEASE "$ticket" - "Docs" "merged-pr ${ref:-?}"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "MERGE-WAIT RELEASE: implementation PR ${ref:+$ref }is MERGED — the human merge this story was resting for has landed. Releasing it back to 'Docs' so the tech-writer seat finishes it and it reaches Done without a manual step (ABS-270; PILOT-4: works in the pilot lane via the forge-less merge-base check, and also advances a Merging-origin 'Ready for Merge' rest — the PILOT-2 3h-stall posture)." \
        >/dev/null 2>&1 || log "merge-wait release comment failed on $ticket"
    tracker transition "$ticket" "Docs" --actor orchestrator \
        --reason "MERGE-WAIT RELEASE: implementation PR ${ref:-(unknown)} merged — resuming the story at 'Docs' (ABS-270)" \
        --expect-from "Ready for Merge" \
        >/dev/null 2>&1 || log "merge-wait release transition failed on $ticket"
    return 0
}

# =============================================================================
# PILOT-18 merge-conflict redirect — a story resting at the human merge gate whose
# OPEN MR was CONFLICTED by a foreign merge falls back to Merging for resolution.
# =============================================================================
# merge_wait_release (above) only asks "is the MR merged yet" (ancestry). It never
# asks "does the MR still merge cleanly". On 2026-07-22 (v3-pilot #3) MR !159 was
# broken by the merge of !158 (migration-number collision 015/015 + migrate.test.ts)
# and sat conflicted at the gate — invisible to the sweep; only the operator caught
# it and hand-redirected it with a resolution recipe. This gate closes that wound:
# for every story resting at `Ready for Merge` it probes MERGEABILITY (story_merge-
# ability — the adapter `mergeable` field with a forge, a `git merge-tree` dry-run
# without one) and, on CONFLICT, redirects to `Merging` with the PILOT-9 resolution
# recipe so a seat rebases + resolves. AC4: merged-ness stays merge_wait_release's
# authority — this fires ONLY on a live conflict, never on a MERGED or clean MR.
#
# Flapping guard (AC3): the redirect fires ONCE per (MR-head, target-head). The same
# conflict standstill (both tips unchanged) is fingerprinted and skipped, so a
# rejected edge or a slow resolving seat cannot re-spam the ticket/operator; a NEW
# foreign merge (target moves) or a rebase (MR head moves) is a fresh fingerprint and
# may redirect again. Same shape as the sibling gates: MODE-aware, --expect-from-
# guarded, fail-OPEN on UNKNOWN, silent on CLEAN (no log/comment/intent -> AC2).
merge_conflict_marker() { echo "${ORCH_STATE_DIR}/merge-conflict-$1"; }

# merge_conflict_fp <ticket> — "<mr-head>:<target-head>", best-effort from git.
# Empty when git cannot resolve either tip (the redirect then relies on the ticket
# LEAVING `Ready for Merge` for idempotency, exactly like the sibling gates).
merge_conflict_fp() {
    local ticket="$1" branch="$1-auto" repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    command -v git >/dev/null 2>&1 || { printf ''; return 0; }
    local active remote target mrsha tsha
    active="$(resolve_active_main_ref "$ORCH_LOCAL_MAIN_BRANCH" "$repo")"
    remote="${active%%/*}"
    mrsha="$(git -C "$repo" rev-parse --verify -q "refs/heads/$branch" 2>/dev/null || true)"
    target="$(story_merge_target_branch "$ticket" "$remote")"
    tsha="$(git -C "$repo" rev-parse --verify -q "refs/remotes/$remote/$target" 2>/dev/null || true)"
    [ -n "$mrsha$tsha" ] || { printf ''; return 0; }
    printf '%s:%s' "$mrsha" "$tsha"
}

# merge_conflict_redirect <ticket> <status> — 0 (INTERVENED) when a story resting at
# `Ready for Merge` has a CONFLICTED open MR: redirects it to `Merging` with the
# PILOT-9 resolution recipe + a notification. Returns 1 (no-op) for every other
# ticket / status, a clean or undecidable MR, and a repeat of the same conflict
# standstill (AC3). Runs from the reconcile sweep next to merge_wait_release.
merge_conflict_redirect() {
    local ticket="$1" status="$2" mstate fp last branch="$1-auto"
    [ "$status" = "Ready for Merge" ] || return 1
    ticket_still_in "$ticket" "$status" || return 1
    mstate="$(story_mergeability "$ticket")"
    [ "$mstate" = "CONFLICT" ] || return 1     # CLEAN / UNKNOWN -> no action, no log (AC2)
    # AC3 flapping guard: skip if we already redirected for this exact (MR, target) head.
    fp="$(merge_conflict_fp "$ticket")"
    last="$(cat "$(merge_conflict_marker "$ticket")" 2>/dev/null || true)"
    [ -n "$fp" ] && [ "$fp" = "$last" ] && return 1
    intent MERGE-CONFLICT-REDIRECT "$ticket" - "Merging" "conflicted-open-mr $branch"
    [ "$MODE" = "live" ] || return 0
    mkdir -p "$ORCH_STATE_DIR" 2>/dev/null || true
    printf '%s' "$fp" > "$(merge_conflict_marker "$ticket")" 2>/dev/null || true
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "MERGE-CONFLICT-REDIRECT: story rested at 'Ready for Merge' but its open MR (branch ${branch}) NO LONGER MERGES CLEANLY into its target — a foreign merge conflicted it (the !159-after-!158 migration-number-collision class, v3-pilot #3, 2026-07-22). The merged-ness sweep only checks ancestry, never mergeability, so this was human-invisible. Redirecting to 'Merging' so a seat resolves it: rebase onto the CURRENT target branch; identify the colliding artefacts (for migration-number collisions draw a FRESH number via scripts/next-migration-number.sh AFTER the rebase — never guess); get the suite green; push with --force-with-lease. Once it is back at the gate the normal path resumes (PILOT-18)." \
        >/dev/null 2>&1 || log "merge-conflict-redirect comment failed on $ticket"
    if tracker transition "$ticket" "Merging" --actor orchestrator \
        --reason "MERGE-CONFLICT-REDIRECT: open MR for ${branch} conflicted by a foreign merge — redirect Ready for Merge -> Merging. Resolve: rebase onto the current target, re-draw colliding migration numbers via scripts/next-migration-number.sh (do not guess), suite green, --force-with-lease (PILOT-18)." \
        --expect-from "Ready for Merge" \
        >/dev/null 2>&1; then
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "merge conflict at the gate: ${ticket}'s open MR no longer merges cleanly (foreign-merge conflict) — the runner redirected it to 'Merging' for auto-resolution; no action needed from you (PILOT-18)."
        return 0                                   # redirect LANDED -> genuine INTERVENED
    fi
    # Same fail-LOUD posture as the sibling gates: the 'Ready for Merge' -> 'Merging'
    # edge is absent (should not happen — ABS-454/ABS-481 rely on it). Surface it
    # instead of silently stalling; the marker above already prevents re-spam (AC3).
    log "MERGE-CONFLICT-REDIRECT: redirect REJECTED on $ticket — status table lacks the 'Ready for Merge' -> 'Merging' edge; NOT intervening (would stall silently). Add the edge to profiles/neutral/adapters/statuses.yaml (PILOT-18)."
    runlog MERGE-CONFLICT-REDIRECT-REJECTED "$ticket" - "Merging" "rejected-edge Ready for Merge->Merging"
    return 1
}

# =============================================================================
# ABS-454 ready-for-merge MR-existence gate — a story rests at the human merge
# gate only when its MR actually EXISTS (open OR merged); a no-MR entry self-heals
# =============================================================================
# On 2026-07-18 three stories reached `Ready for Merge` with NO mirrored MR and
# then stalled human-invisibly: ABS-425 (branch pushed, MR-create failed),
# ABS-420 (no MR), ABS-416 (branch only local — push + MR lost in a runner
# restart); the operator repaired all three by hand (ABS-354 class). The ABS-406
# invariant_sweep already DETECTS this (its `open-mr` rule) but is detection-only
# — it comments and leaves the ticket resting. This gate is the SELF-HEAL half:
# when a story rests at `Ready for Merge` with no MR at all, it redirects back to
# `Merging` with a gate-results comment so the RTE respawn (re)pushes the branch
# AND (re)creates the MR — a silent stall becomes an automatic recovery (AC1).
#
# It fires ONLY when the MR state is NONE (neither OPEN nor MERGED):
#   OPEN   -> the legitimate docs_pr_gate merge-wait park (a green story waiting
#             on the human merge, ABS-270) — left untouched (AC2: no false alarm).
#   MERGED -> already merged (Path-A direct landing, or a merge race) — the gate
#             is satisfied, no-op (AC2).
#   NONE   -> the defect class: no MR exists -> self-heal to Merging.
#
# ABS-481 adds an EARLIER half checked first and independently of $FORGE_CMD: the
# story branch itself must EXIST on the active remote. The MR probe above asks the
# forge MIRROR, so a branch committed locally but never pushed (ABS-461: no push at
# all, then only NOOPs) is invisible to it whenever no mirror is configured or the
# mirror host is down. story_branch_remote_state resolves the branch against the
# real remotes (GitLab fallback included, no hardcoded host); ABSENT self-heals to
# Merging like the NONE case, and UNREACHABLE (no remote answered) fails LOUD in the
# run log instead of silent-passing the merge gate on an unverifiable branch.
# Same shape as done_pr_gate: post-landing, idempotent (once the redirect LANDS
# the ticket rests in Merging, so it only re-fires if it reaches `Ready for Merge`
# again still MR-less), MODE-aware, fail-OPEN in the placeholder case (no
# $FORGE_CMD -> unchanged). Like done_pr_gate, a REJECTED redirect fails LOUDLY
# (return 1 + audit) rather than trapping the runner in a silent no-spawn loop.
# Called from BOTH dispatch (entry into `Ready for Merge`) AND the reconcile sweep
# (a ticket already resting there across a runner restart — the ABS-416 case —
# is never re-dispatched, since `Ready for Merge` is deliberately not reconcilable).
ready_for_merge_mr_gate() {
    local ticket="$1" to="$2" pair state ref branch_state
    [ "$to" = "Ready for Merge" ] || return 1
    ticket_still_in "$ticket" "$to" || return 1

    # ABS-481: the never-pushed / lost-push half — checked FIRST and INDEPENDENTLY
    # of $FORGE_CMD, because the MR probe below cannot see a branch that never
    # reached the remote (ABS-461: committed in the worktree, never pushed; the
    # runner transitioned to Ready for Merge and then only NOOPed — no MR, no
    # self-heal). Resolve the branch against the ACTIVE remote (GitLab fallback
    # included) and fail LOUD on degraded connectivity rather than silent-pass.
    branch_state="$(story_branch_remote_state "$ticket")"
    case "$branch_state" in
        ABSENT)
            # The story branch exists only locally — no remote branch, so no MR can
            # exist. Self-heal to Merging so the RTE respawn PUSHES it and opens the
            # MR (AC1), exactly like the no-MR path below but for the earlier gap.
            intent READY-FOR-MERGE-NO-BRANCH "$ticket" - "Merging" "local-only branch self-heal"
            [ "$MODE" = "live" ] || return 0
            tracker comment "$ticket" --kind gate-results --actor orchestrator \
                --body "READY-FOR-MERGE-GATE: story branch ${ticket}-auto exists ONLY locally — it was committed but NEVER pushed (or the push was lost in a runner restart), so no remote branch and no MR can exist (ABS-461 regression, ABS-481). Redirecting to 'Merging' so the RTE respawn pushes the branch AND opens the MR against the active remote, instead of resting human-invisibly at the merge gate with nothing to merge." \
                >/dev/null 2>&1 || log "ready-for-merge-gate no-branch comment failed on $ticket"
            if tracker transition "$ticket" "Merging" --actor orchestrator \
                --reason "READY-FOR-MERGE-GATE: story branch ${ticket}-auto absent from the active remote (never pushed) — redirect Ready for Merge -> Merging so the RTE respawn pushes it (self-heal, ABS-481)" \
                --expect-from "Ready for Merge" \
                >/dev/null 2>&1; then
                return 0                               # redirect LANDED -> genuine INTERVENED
            fi
            log "READY-FOR-MERGE-GATE: no-branch redirect REJECTED on $ticket — status table lacks the 'Ready for Merge' -> 'Merging' edge; NOT intervening (would stall silently). Add the edge to profiles/neutral/adapters/statuses.yaml (ABS-481)."
            runlog READY-FOR-MERGE-GATE-REJECTED "$ticket" - "Merging" "rejected-edge Ready for Merge->Merging (no-branch)"
            tracker comment "$ticket" --kind gate-results --actor orchestrator \
                --body "READY-FOR-MERGE-GATE could NOT enforce: the redirect 'Ready for Merge' -> 'Merging' was rejected by the status adapter (edge missing from the transition table). The story branch ${ticket}-auto is local-only with no MR — surfacing loudly instead of silently stalling (ABS-481; add the 'Ready for Merge' -> 'Merging' edge to profiles/neutral/adapters/statuses.yaml)." \
                >/dev/null 2>&1 || log "ready-for-merge-gate no-branch rejection comment failed on $ticket"
            return 1
            ;;
        UNREACHABLE)
            # AC2: degraded host connectivity fails LOUD, never silent-pass. No
            # remote answered, so we cannot prove the branch is absent — do NOT
            # self-heal (would thrash a healthy story) and do NOT treat the gate as
            # satisfied (would hide the ABS-461 defect). Surface it in the runner
            # log and rest; no tracker comment, so a persistent outage does not spam
            # the ticket every sweep.
            log "READY-FOR-MERGE-GATE: no remote reachable to verify branch ${ticket}-auto on $ticket — connectivity degraded; refusing to pass the merge gate on an unverifiable branch (fail-loud, not silent-pass, ABS-481)."
            runlog READY-FOR-MERGE-GATE-UNREACHABLE "$ticket" - "$to" "no reachable remote to verify ${ticket}-auto"
            return 1
            ;;
        # FOUND (branch is on the remote) or NOREMOTE (placeholder) -> fall through
        # to the ABS-454 MR-existence half below.
    esac

    # ABS-454 MR-existence half — only meaningful with a forge/mirror configured.
    [ -n "$FORGE_CMD" ] || return 1        # no forge platform -> placeholder skip (fail-open)
    pair="$(story_pr_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    [ "$state" = "NONE" ] || return 1      # OPEN (docs_pr_gate park) or MERGED -> satisfied (AC2)
    intent READY-FOR-MERGE-NO-MR "$ticket" - "Merging" "no-mr self-heal"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "READY-FOR-MERGE-GATE: story rests in 'Ready for Merge' with NO mirrored MR (neither open nor merged) — MR-create failed or the branch push was lost in a runner restart (ABS-425 / ABS-420 / ABS-416, ABS-354 class). Redirecting to 'Merging' so the RTE respawn (re)pushes the branch AND creates the MR, instead of stalling human-invisibly at the merge gate (self-heal, ABS-454)." \
        >/dev/null 2>&1 || log "ready-for-merge-gate comment failed on $ticket"
    if tracker transition "$ticket" "Merging" --actor orchestrator \
        --reason "READY-FOR-MERGE-GATE: no MR exists for the story branch — redirect Ready for Merge -> Merging so the RTE respawn creates it (self-heal, ABS-454)" \
        --expect-from "Ready for Merge" \
        >/dev/null 2>&1; then
        return 0                                   # redirect LANDED -> genuine INTERVENED
    fi
    # The 'Ready for Merge' -> 'Merging' redirect was REJECTED (edge absent from the
    # table). Reporting INTERVENED would suppress dispatch while the story sits MR-less
    # in Ready for Merge — the gate re-fires forever silently, the exact stall this
    # gate exists to stop. Fail LOUDLY (log + run.log + audit comment) and return 1.
    log "READY-FOR-MERGE-GATE: redirect REJECTED on $ticket — status table lacks the 'Ready for Merge' -> 'Merging' edge; NOT intervening (would stall silently). Add the edge to profiles/neutral/adapters/statuses.yaml (ABS-454)."
    runlog READY-FOR-MERGE-GATE-REJECTED "$ticket" - "Merging" "rejected-edge Ready for Merge->Merging"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "READY-FOR-MERGE-GATE could NOT enforce: the redirect 'Ready for Merge' -> 'Merging' was rejected by the status adapter (edge missing from the transition table). The story rests in 'Ready for Merge' with no MR — surfacing loudly instead of silently stalling (ABS-454; add the 'Ready for Merge' -> 'Merging' edge to profiles/neutral/adapters/statuses.yaml)." \
        >/dev/null 2>&1 || log "ready-for-merge-gate rejection comment failed on $ticket"
    return 1
}

# =============================================================================
# PILOT-20 merge-wait DECLINED escalation — a story parked at `Ready for Merge`
# whose implementation PR is DECLINED / closed-without-merge gets a DISTINCT human
# escalation, instead of resting silently and human-invisibly forever.
# =============================================================================
# ABS-270 gave the green *awaiting-merge* rest (docs_pr_gate park) and the
# *merge-lands -> auto-resume* release (merge_wait_release). It deliberately left
# one terminal branch uncovered: a parked PR that is later DECLINED. story_pr_state
# used to collapse DECLINED -> OPEN, so merge_wait_release (fires only on MERGED)
# never releases it and ready_for_merge_mr_gate (fires only on NONE — a declined PR
# still EXISTS as an MR) never self-heals it. `Ready for Merge` is a legit rest
# (not reconcilable, not stuck-flagged — that is why resting is free), so the story
# rests indefinitely on a merge that can no longer land.
#
# #PATH_DECISION (PILOT-20) — CHOSEN: option (a), a single `kind: notification`
# comment naming the declined PR, mirroring the initial human notification the park
# already emits. It is the least disruptive and keeps the human-owned-gate semantics
# intact (the story stays at `Ready for Merge`; the human re-opens/re-creates the PR
# or moves it on — the runner never merges, ADR-A-0005). Option (b) — transition to
# `Blocked` — is REJECTED as the default: it leaves the human merge gate for a status
# no seat owns and is reserved for a truly unrecoverable decline, which the runner
# cannot distinguish from a re-openable one.
#
# Idempotent (AC4): the notification carries a stable marker ("MERGE-WAIT DECLINED")
# and the gate re-reads the ticket dump each sweep — once the comment is on the
# ticket the gate no-ops, so a resting declined story is escalated exactly once (the
# same dump-marker idempotency the crash-repair / inprogress-heal gates use). Runs in
# the reconcile sweep next to merge_wait_release, because `Ready for Merge` is not
# reconcilable and dispatch never re-derives it. MODE-aware; fail-OPEN in the
# placeholder case (no $FORGE_CMD -> no DECLINED signal at all).
#
# merge_wait_declined_gate <ticket> <status> — 0 (ESCALATED) when a story rests at
# `Ready for Merge`, a forge is configured, its PR is DECLINED, and no prior
# escalation exists. 1 (no-op) otherwise: not at the gate, no forge, PR not DECLINED
# (OPEN keeps resting — AC2; MERGED is released by merge_wait_release — AC3), or the
# escalation already fired (AC4).
merge_wait_declined_gate() {
    local ticket="$1" status="$2" pair state ref dump
    [ "$status" = "Ready for Merge" ] || return 1
    [ -n "$FORGE_CMD" ] || return 1        # no forge -> no DECLINED signal (fail-open)
    pair="$(story_pr_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    [ "$state" = "DECLINED" ] || return 1  # OPEN keeps resting (AC2); MERGED released elsewhere (AC3)
    # AC4: escalate exactly once — skip if a prior notification is already on the ticket.
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    printf '%s' "$dump" | grep -qF "MERGE-WAIT DECLINED" && return 1
    intent MERGE-WAIT-DECLINED "$ticket" - "$status" "declined-pr ${ref:-?}"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind notification --actor orchestrator \
        --body "MERGE-WAIT DECLINED: the implementation PR ${ref:+$ref }for this story was DECLINED / closed without merging, but the story is resting at 'Ready for Merge' waiting on a merge that can no longer land. A human must re-open or re-create the PR (or move the story on) — the runner never merges (ADR-A-0005). Surfacing this once so the story does not rest silently and human-invisibly forever (PILOT-20; extends the ABS-270 merge-wait rest, which covers only the still-open and merged cases)." \
        >/dev/null 2>&1 || log "merge-wait-declined notification failed on $ticket"
    return 0
}

# rework_count <ticket-dump> — backward agent transitions since the last
# PO-decision exit, parsed from the transition-reason comment history.
#
# Two actors are excluded (ABS-267):
#   human        — forward-fix semantics; a human rejection is not agent thrash.
#   orchestrator — the RUNNER's own mechanical station corrections (station_guard's
#                  redirect to a skipped station, done_pr_gate's Done -> Merging
#                  redirect) are BOOKKEEPING, not a seat rejecting the work. Counting
#                  them made ONE QA bounce burn TWO of three rework units (the qas
#                  bounce + the guard's redirect), halving the effective budget and
#                  escalating sound stories to Needs PO Decision (ABS-235).
# This is an ACTOR exclusion, NOT a "the runner applied it" exclusion: a runner-applied
# transition-on-handoff (ABS-132) carries the SEAT's actor (e.g. be-developer), so real
# seat bounces still count no matter who called the adapter.
#
# A THIRD exclusion (PILOT-69 / ADR-A-0018 transient class, Anschluss ABS-555):
# a backward transition whose REASON denotes a transient/infrastructure abort
# (crash, error_max_turns, timeout, rate-limit, session-poison, a non-zero exit,
# or the runner's own CRASH-REPAIR / INPROGRESS-HEAL / WAIT-STATE REPAIR routes)
# carries NO functional verdict and is budget-neutral — mirroring the iteration
# guard's ABS-555 infra-abort exclusion so BOTH counters treat the transient
# class the same way (the ADR-A-0018 taxonomy previously had an effect only for
# environment-denial; 'transient' was recorded and then ignored by the very
# counters it should have spared — PILOT-32). A handoff MIS-REPORT ("claimed
# commits do not verify") is a CONTENT fault, deliberately NOT in ORCH_REWORK_INFRA_RE,
# so ADR-A-0024 (e) still counts a mis-report bounce natively.
rework_count() {
    printf '%s\n' "$1" | awk -v infra_re="$ORCH_REWORK_INFRA_RE" '
        function idx(s) {
            if (s == "Design") return 1
            if (s == "Ready for Development") return 2
            if (s == "In Progress") return 3
            if (s == "In Review") return 4
            if (s == "Security Review") return 5
            if (s == "Test Prep") return 6
            if (s == "In Test") return 7
            if (s == "Design Test") return 8
            if (s == "Story Acceptance") return 9
            if (s == "Merging") return 10
            if (s == "Docs") return 11
            if (s == "Done") return 12
            if (s == "PO Triage") return 21
            if (s == "Grooming") return 22
            if (s == "Enrichment") return 23
            if (s == "Ticket Review") return 24
            if (s == "Architecture Review") return 25
            if (s == "Stories In Flight") return 26
            if (s == "Epic Integration") return 27
            if (s == "Ready for Epic Acceptance") return 28
            if (s == "Epic Done") return 29
            return 0
        }
        /^### / {
            cur_actor = ""
            if (match($0, /actor: /)) cur_actor = substr($0, RSTART + 7)
            next
        }
        /^Transition: / {
            line = $0
            sub(/^Transition: /, "", line)
            p = index(line, " -> ")
            if (p == 0) next
            from = substr(line, 1, p - 1)
            rest = substr(line, p + 4)
            q = index(rest, ". Reason:")
            to = (q > 0 ? substr(rest, 1, q - 1) : rest)
            reason = (q > 0 ? substr(rest, q + 9) : "")
            # Window reset: ANY PO-decision exit re-arms the counter.
            if (from == "Needs PO Decision") { n = 0; next }
            # Human transitions never count (forward-fix semantics).
            if (tolower(cur_actor) == "human") next
            # The runner is not an agent seat: its own STATION-GUARD / DONE-GATE
            # redirects are mechanical corrections, not rework (ABS-267).
            if (tolower(cur_actor) == "orchestrator") next
            # PILOT-69 / ADR-A-0018 transient class (Anschluss ABS-555): a backward
            # transition whose REASON is a transient/infrastructure abort renders no
            # functional verdict -> budget-neutral, never counted as rework. Same
            # fail-safe bias as the iteration guard: over-classifying as infra only
            # makes the budget MORE lenient; a false MISS re-creates the deadlock.
            if (infra_re != "" && tolower(reason) ~ infra_re) next
            if (idx(from) > 0 && idx(to) > 0 && idx(to) < idx(from)) n++
        }
        END { print n + 0 }'
}

# merge_bounce_count <ticket-dump> — how many MERGE-bounces this story has taken:
# backward exits from `Merging` driven by the `rte` seat (a rebase or CI failure ->
# Ready for Development, rte.md step 5). ABS-256 AC3 telemetry: reuses rework_count's
# derivation (transition-reason comments + their `actor:` headers) filtered to
# actor=rte, so NO new metrics store is introduced. Reported as `bounces=N` on every
# Merging dispatch (INTENT MERGE-TOKEN-*), which is what makes the token's effect
# visible per story and per epic: with the token held across a bounce, this count
# must never exceed 1 for a given story (ADR-A-0025 §3).
# `Merging -> Docs|Done` are the FORWARD exits (a successful merge), never bounces.
merge_bounce_count() {
    printf '%s\n' "$1" | awk '
        /^### / {
            cur_actor = ""
            if (match($0, /actor: /)) cur_actor = substr($0, RSTART + 7)
            next
        }
        /^Transition: Merging -> / {
            if (tolower(cur_actor) != "rte") next
            line = $0
            sub(/^Transition: Merging -> /, "", line)
            q = index(line, ". Reason:")
            to = (q > 0 ? substr(line, 1, q - 1) : line)
            sub(/\.$/, "", to)
            if (to != "Docs" && to != "Done") n++
        }
        END { print n + 0 }'
}

# reached_merge_tier <ticket-dump> — 0 (true) when the ticket's transition history
# shows it ENTERED the acceptance/merge tier at least once: a story status with
# chain idx >= Story Acceptance (9..12: Story Acceptance/Merging/Docs/Done) or an
# epic acceptance status (>= Ready for Epic Acceptance, 28..29). A ticket that got
# that far passed its implementation, review, security and test gates — its work is
# DEMONSTRABLY FINISHED. Used to steer a cap/rework park to Blocked (merge path one
# hop away) rather than Needs PO Decision (PILOT-69 AC1).
reached_merge_tier() {
    printf '%s\n' "$1" | awk '
        function idx(s) {
            if (s == "Story Acceptance") return 9
            if (s == "Merging") return 10
            if (s == "Docs") return 11
            if (s == "Done") return 12
            if (s == "Ready for Epic Acceptance") return 28
            if (s == "Epic Done") return 29
            return 0
        }
        /^Transition: / {
            line = $0; sub(/^Transition: /, "", line)
            p = index(line, " -> "); if (p == 0) next
            rest = substr(line, p + 4)
            q = index(rest, ". Reason:")
            to = (q > 0 ? substr(rest, 1, q - 1) : rest)
            ti = idx(to)
            if (ti > 0) found = 1
        }
        END { exit (found ? 0 : 1) }'
}

# escalation_park_target <ticket> — the rest status a cap/rework escalation parks
# to: Blocked when the ticket is demonstrably finished (reached_merge_tier), else
# Needs PO Decision (PILOT-69 AC1 / ADR-A-0018). Rationale: Blocked's exhaustive
# resume-to-origin list includes Merging, so a human/TDM routes finished-but-parked
# work straight to the RTE merge seat without a po-agent re-spawn that could re-trip
# the same cap — the merge path stays reachable. Not-finished work keeps the
# reconcilable Needs PO Decision park (a fresh product decision is genuinely owed).
# This complements the PILOT-49/ABS-555 NPD->Merging escape edge, it does not replace it.
escalation_park_target() {
    local dump
    dump="$(tracker get "$1" 2>/dev/null || true)"
    if [ -n "$dump" ] && reached_merge_tier "$dump"; then
        echo "Blocked"
    else
        echo "Needs PO Decision"
    fi
}

# rework_blocks <ticket> — 0 (true) when the derived count is at the limit.
rework_blocks() {
    local dump n
    dump="$(tracker get "$1" 2>/dev/null || true)"
    [ -n "$dump" ] || return 1
    n="$(rework_count "$dump")"
    [ "$n" -ge "$ORCH_REWORK_LIMIT" ]
}

# escalate_rework <ticket> <to> — realize §3.2: gate-results comment + park. The
# park target is Blocked for demonstrably-finished work (merge path stays reachable)
# else Needs PO Decision (PILOT-69 AC1 / ADR-A-0018).
escalate_rework() {
    local ticket="$1" to="$2" target
    target="$(escalation_park_target "$ticket")"
    intent REWORK-LIMIT "$ticket" - "$target" "at=$to"
    [ "$MODE" = "live" ] || return 0
    local escape
    if [ "$target" = "Blocked" ]; then
        escape="This ticket already reached the acceptance/merge tier, so its work is finished; parking in Blocked (whose resume-to-origin list includes Merging) keeps the merge path one hop away for a human/TDM — no po-agent re-spawn that could re-trip the cap (PILOT-69 AC1)."
    else
        escape="If the work is already approved, the PO may route it forward (Needs PO Decision -> Merging, PILOT-49/ABS-555)."
    fi
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "Rework limit reached: $ORCH_REWORK_LIMIT backward transitions since the last PO decision (cross-stage counter, ABS-74 / spec §3.2). Escalating to $target instead of another spawn at '$to'. $escape" \
        >/dev/null 2>&1 || log "rework-limit comment failed on $ticket"
    tracker transition "$ticket" "$target" --actor orchestrator \
        --reason "rework limit reached at $to (ABS-74); parked to $target (PILOT-69 AC1)" \
        >/dev/null 2>&1 || log "rework-limit transition failed on $ticket"
}

# =============================================================================
# ABS-118 crash backoff / outage pause / escalation halt
# =============================================================================
# Instant spawn failures must not burn budget at sweep cadence (rate-limit
# incident: 13 crash cycles in ~40 min). Three mechanisms, all keyed on files
# in $ORCH_STATE_DIR (existing state dir; survives restarts on purpose):
#   backoff-<ticket>   per-(ticket,status) exponential retry delay
#   halt-<ticket>      permanent stop after an escalation-seat (NPD) crash
#   outage / fastfail / probe-inflight   global environment-outage pause state
# Gate order in spawn_dispatch (architect F3): kill-switch -> outage(+probe)
# -> halt -> backoff -> budget -> ... (probes stay budget-gated, ADR-A-0009).
# Spec: specs/ABS-118-crash-backoff-outage-spec.md.

ORCH_BACKOFF_BASE_SECONDS="${ORCH_BACKOFF_BASE_SECONDS:-60}"   # 0 = backoff off
ORCH_BACKOFF_FACTOR="${ORCH_BACKOFF_FACTOR:-2}"
ORCH_BACKOFF_MAX_SECONDS="${ORCH_BACKOFF_MAX_SECONDS:-1800}"
ORCH_FASTFAIL_SECONDS="${ORCH_FASTFAIL_SECONDS:-10}"
ORCH_OUTAGE_BURST="${ORCH_OUTAGE_BURST:-3}"                    # 0 = outage detection off
ORCH_OUTAGE_RESUME="${ORCH_OUTAGE_RESUME:-auto}"               # auto | manual
ORCH_PROBE_INTERVALS="${ORCH_PROBE_INTERVALS:-300 900 1800}"   # last value repeats

# now_epoch — scheduling clock, injectable for deterministic tests (ORCH_NOW).
# Durations (fast-fail classification) use the real clock, not this one.
now_epoch() { echo "${ORCH_NOW:-$(date -u +%s)}"; }

backoff_file()       { echo "$ORCH_STATE_DIR/backoff-$1"; }
halt_file()          { echo "$ORCH_STATE_DIR/halt-$1"; }
outage_file()        { echo "$ORCH_STATE_DIR/outage"; }
fastfail_file()      { echo "$ORCH_STATE_DIR/fastfail"; }
probe_inflight_file(){ echo "$ORCH_STATE_DIR/probe-inflight"; }

# probe_interval_for <n> — the n-th (1-based) word of ORCH_PROBE_INTERVALS;
# past the end, the last word repeats forever.
probe_interval_for() {
    local i=1 w last=300
    for w in $ORCH_PROBE_INTERVALS; do
        last="$w"
        [ "$i" -eq "$1" ] && { echo "$w"; return 0; }
        i=$((i + 1))
    done
    echo "$last"
}

# record_backoff <ticket> <status> — grow the retry delay after a crash. A
# crash at a DIFFERENT status restarts the ladder (fresh failure mode).
record_backoff() {
    [ "$ORCH_BACKOFF_BASE_SECONDS" -gt 0 ] || return 0
    local f delay prev_status prev_delay
    f="$(backoff_file "$1")"
    delay="$ORCH_BACKOFF_BASE_SECONDS"
    if [ -f "$f" ]; then
        prev_status="$(cut -f1 "$f" 2>/dev/null | head -1 || true)"
        prev_delay="$(cut -f3 "$f" 2>/dev/null | head -1 || true)"
        if [ "$prev_status" = "$2" ] && [ "$prev_delay" -gt 0 ] 2>/dev/null; then
            delay=$((prev_delay * ORCH_BACKOFF_FACTOR))
            [ "$delay" -gt "$ORCH_BACKOFF_MAX_SECONDS" ] && delay="$ORCH_BACKOFF_MAX_SECONDS"
        fi
    fi
    printf '%s\t%s\t%s\n' "$2" "$(( $(now_epoch) + delay ))" "$delay" > "$f" 2>/dev/null || true
    runlog BACKOFF "$1" - "$2" "delay=${delay}s"
}

# backoff_active <ticket> <to> — 0 (true) while the (ticket, status) delay runs.
backoff_active() {
    local f st ne
    f="$(backoff_file "$1")"
    [ -f "$f" ] || return 1
    st="$(cut -f1 "$f" 2>/dev/null | head -1 || true)"
    ne="$(cut -f2 "$f" 2>/dev/null | head -1 || true)"
    [ "$st" = "$2" ] || return 1
    [ "$(now_epoch)" -lt "${ne:-0}" ]
}

# declare_outage <ticket> — write the global pause state (idempotent) + NOTIFY.
declare_outage() {
    [ -f "$(outage_file)" ] && return 0
    local now
    now="$(now_epoch)"
    printf '%s\t%s\t%s\n' "$now" 0 "$(( now + $(probe_interval_for 1) ))" > "$(outage_file)" 2>/dev/null || true
    runlog OUTAGE-PAUSE "$1" - - "burst=$ORCH_OUTAGE_BURST mode=$ORCH_OUTAGE_RESUME"
    log "environment outage: $ORCH_OUTAGE_BURST consecutive instant spawn failures; pausing all spawns (mode=$ORCH_OUTAGE_RESUME)"
    notify "${ORCH_NOTIFY_TICKET:-$1}" "orchestrator paused: $ORCH_OUTAGE_BURST consecutive instant spawn failures look like an environment outage (rate limit/auth). Resume mode=$ORCH_OUTAGE_RESUME; manual resume = remove work/.orchestrator/outage (ABS-118)."
}

# resolve_outage <ticket> <status> <why> — clear the pause + NOTIFY (auto-resume).
resolve_outage() {
    [ -f "$(outage_file)" ] || return 0
    rm -f "$(outage_file)" "$(probe_inflight_file)" 2>/dev/null || true
    printf '0\n' > "$(fastfail_file)" 2>/dev/null || true
    runlog AUTO-RESUME "$1" - "$2" "$3"
    log "outage resolved ($3) on $1; resuming spawns"
    notify "${ORCH_NOTIFY_TICKET:-$1}" "orchestrator auto-resumed: the environment answers again ($3 on $1, ABS-118)."
}

# record_spawn_result <ticket> <status> <rc> <duration-seconds> — the ABS-118
# bookkeeping around every live_spawn outcome, counted ONCE per spawn (not per
# attempt; architect F2). Runs in the async subshell; the state files are the
# shared medium (same idiom as locks/sessions). Concurrent writers can lose an
# increment/reset of the fast-fail counter — accepted: the counter re-arms on
# the very next crash, and the pause itself is idempotent (architect F4).
record_spawn_result() {
    local ticket="$1" status="$2" rc="$3" duration="$4"
    if [ "$rc" -eq 0 ]; then
        rm -f "$(backoff_file "$ticket")" 2>/dev/null || true
        printf '0\n' > "$(fastfail_file)" 2>/dev/null || true
        resolve_outage "$ticket" "$status" "successful spawn"
        return 0
    fi
    record_backoff "$ticket" "$status"
    if [ "$ORCH_OUTAGE_BURST" -gt 0 ] && [ "$duration" -lt "$ORCH_FASTFAIL_SECONDS" ] 2>/dev/null; then
        local n
        n="$(cat "$(fastfail_file)" 2>/dev/null || echo 0)"
        n=$(( ${n:-0} + 1 ))
        printf '%s\n' "$n" > "$(fastfail_file)" 2>/dev/null || true
        [ "$n" -ge "$ORCH_OUTAGE_BURST" ] && declare_outage "$ticket"
        # A failed probe: the schedule was already advanced at admission (F1);
        # just release the probe slot.
        if [ "$(cat "$(probe_inflight_file)" 2>/dev/null || true)" = "$ticket" ]; then
            rm -f "$(probe_inflight_file)" 2>/dev/null || true
            runlog PROBE "$ticket" - "$status" "failed"
        fi
    else
        # Slow failure: the environment answered (a ticket problem, not an
        # outage) — reset the burst counter; during a pause it counts as proof
        # of life and resumes the run (spec §3).
        printf '0\n' > "$(fastfail_file)" 2>/dev/null || true
        resolve_outage "$ticket" "$status" "slow failure (environment answered)"
    fi
    return 0
}

# crash_marker_body <status> <role> — the SPAWN-CRASH marker line (greppable).
# ABS-295: instance= embedded so check_crash_repair can verify condition 4
# (two-runner safety) from the marker alone, without a separate ledger.
# crash_count's prefix match "SPAWN-CRASH status=<st> " at position 1 is
# unaffected — instance= comes after the role= field.
crash_marker_body() { printf 'SPAWN-CRASH status=%s role=%s instance=%s (orchestrator)' "$1" "$2" "${ORCH_INSTANCE_ID:-unknown}"; }

# crash_count <ticket-dump> <status> — consecutive SPAWN-CRASH markers for this
# status since the last successful handoff comment (a handoff resets the run).
crash_count() {
    printf '%s\n' "$1" | awk -v st="$2" '
        /^### / {
            in_gate = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/)
            if ($0 ~ /kind: handoff/) n = 0
            next
        }
        in_gate && index($0, "SPAWN-CRASH status=" st " ") == 1 { n++ }
        END { print n + 0 }'
}

# record_spawn_crash <ticket> <to> <role> [diag] — post the marker; escalate at
# limit. Called from the live spawn path only (dry-run never spawns, so never
# crashes). ABS-151: <diag> carries the last attempt's failure diagnostic
# (exit code + captured stderr, or the empty-handoff classification) so the
# marker is not opaque and an operator can tell a transient hiccup from a
# permanent fault.
record_spawn_crash() {
    local ticket="$1" to="$2" role="$3" diag="${4:-}" dump n diag_note=""
    [ -n "$diag" ] && diag_note=" Diagnostic: $diag."
    intent SPAWN-CRASH "$ticket" "$role" "$to"
    # ABS-118: a crash OF the escalation seat itself (po-agent at Needs PO
    # Decision — the seat every other limit escalates TO) must not enter the
    # rest->re-derive retry loop: NPD is reconcilable, so without a halt the
    # sweep respawns it until the run budget dies (observed live). NOTIFY the
    # human and halt the ticket; operator resume = delete the halt marker.
    if [ "$to" = "Needs PO Decision" ]; then
        printf 'escalation-seat crash role=%s at=%s\n' "$role" "$(timestamp)" > "$(halt_file "$ticket")" 2>/dev/null || true
        runlog ESCALATION-CRASH "$ticket" "$role" "$to" "$diag"
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "escalation seat ($role at Needs PO Decision) crashed for $ticket; ticket HALTED — no automatic respawn.$diag_note Operator resume: remove work/.orchestrator/halt-$ticket (ABS-118)."
        return 0
    fi
    # ABS-199 / ADR-A-0018: cross-visit same-blocker loop-breaker. Record this
    # failure in the per-ticket blocker marker; on the 2nd occurrence of the SAME
    # (environment-denial, seat) across ANY visits, auto-park to Blocked with one
    # operator NOTIFY and NO re-spawn (a deterministic wall retrying cannot clear
    # — the ABS-168 lesson). transient/logic and any DISTINCT (class,seat) fall
    # through to the per-visit crash path below unchanged (no false-positive).
    if crossvisit_guard "$ticket" "$to" "$role" "$diag"; then
        return 0
    fi
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(crash_marker_body "$to" "$role"): spawn failed twice (non-zero exit or no parseable handoff, §6).$diag_note Ticket rests in '$to'; the reconciliation sweep re-derives the spawn (ABS-74 / spec §3.8)." \
        >/dev/null 2>&1 || log "crash marker comment failed on $ticket"
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    n="$(crash_count "$dump" "$to")"
    if [ "$n" -ge "$ORCH_CRASH_LIMIT" ]; then
        intent CRASH-LIMIT "$ticket" "$role" "Needs PO Decision" "crashes=$n"
        tracker comment "$ticket" --kind decision --actor orchestrator \
            --body "Consecutive-crash limit reached: $n failed spawns of $role at '$to' with no successful handoff in between. Escalating to Needs PO Decision instead of an endless sweep-retry loop (ABS-74 / spec §3.8)." \
            >/dev/null 2>&1 || log "crash-limit comment failed on $ticket"
        tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
            --reason "spawn crashed $n consecutive times at $to (ABS-74)" \
            >/dev/null 2>&1 || log "crash-limit transition failed on $ticket"
    fi
}

# =============================================================================
# ABS-132 transition-on-handoff + endless-respawn escalation
# =============================================================================
# Befund 4 (Run ABS-126, the single most expensive finding): early seats parsed
# their handoff but never executed their own transition, so the status stayed
# and the runner resumed the same session forever (à $0.2–0.8/respawn) until an
# operator drove the transitions by hand. Two mechanisms fix it, both default-on
# with an env kill-switch; transitions remain ALSO allowed by seats (idempotent):
#   (a) transition-on-handoff — after a clean, parsed handoff the runner reads
#       the handoff's DECLARED target status and applies it via $TRACKER_CMD
#       transition, actor = the seat role (so a runner-applied bounce is counted
#       by the rework counter exactly like a seat-applied one). No-op when the
#       seat already reached the target (Ist=Soll); never a double transition.
#   (b) loop-guard — a handoff that parses but leaves the status UNCHANGED (no
#       declared target the runner could apply AND the seat did not transition)
#       records a HANDOFF-NOMOVE marker; at ORCH_RESPAWN_LIMIT consecutive
#       no-move respawns the runner escalates to Needs PO Decision with a reason
#       comment (mirrors the crash/rework escalations) instead of resuming forever.

# ticket_status <ticket> — current frontmatter status via the adapter. Empty
# when unreadable. The single frontmatter-status read; ticket_still_in wraps it.
ticket_status() {
    tracker get "$1" 2>/dev/null | awk -F': ' '
        /^---$/ { fm++; next }
        fm == 1 && $1 == "status" { print $2; exit }
        fm >= 2 { exit }
    '
}

# is_known_status <status> — 0 (true) when the argument is a canonical status the
# runner may hand to `tracker transition`. Guards the handoff parse against prose
# (a free-form `next:` line) being mistaken for a target.
is_known_status() {
    case "$1" in
        "Backlog"|"Ready for Development"|"In Progress"|"In Review"|"In Test"|\
        "Ready for Human Acceptance"|"Ready for Merge"|"Done"|"Blocked"|"Needs PO Decision"|\
        "PO Triage"|"Grooming"|"Enrichment"|"Ticket Review"|"Architecture Review"|\
        "Stories In Flight"|"Epic Integration"|"Ready for Epic Acceptance"|"Epic Done"|"Canceled"|"Rejected"|\
        "Design"|"Security Review"|"Test Prep"|"Design Test"|"Story Acceptance"|"Merging"|"Docs")
            return 0 ;;
        *) return 1 ;;
    esac
}

# handoff_target_status <handoff-text> — the DECLARED target status of a handoff.
# #PLAN_UNCERTAINTY resolved (ticket scope 1): the declarative field is `to:`
# (a machine target), with `next-status:` and a bare-status `next:` accepted as
# fallbacks — all EXISTING handoff fields (no seat-prompt change, ticket Out).
# The value is only returned when it is a canonical status, so the ubiquitous
# prose `next:` line ("proceed per the status machine") is never mis-parsed.
# Empty when no declarative target is present (then the loop-guard is the
# backstop). Precedence: to > next-status > next.
handoff_target_status() {
    local text="$1" key val
    for key in to next-status next; do
        val="$(printf '%s\n' "$text" | sed -n "s/^[[:space:]]*[-*]*[[:space:]]*${key}:[[:space:]]*//p" | head -1)"
        [ -n "$val" ] || continue
        val="$(printf '%s' "$val" | tr -d '`"' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/[.,;]*$//')"
        if is_known_status "$val"; then printf '%s' "$val"; return 0; fi
    done
    return 0
}

# handoff_default_target <spawn-status> — the resting status the runner moves a
# ticket to when a seat hands off CLEANLY but declares no target of its own
# (ABS-133, Befund 7). Only Merging has one: once the rte seat has created the
# PR and handed off to the human merge (auto-merge off), the story must rest at
# the human-owned Ready for Merge gate — NOT loop in the reconcilable Merging
# seat, which re-spawned a fresh rte (~$0.75) every reconcile cadence while the
# PR waited for the human. Empty for every other status, so the loop-guard stays
# the backstop everywhere else. A seat that declares its own target (Docs on
# auto-merge, Ready for Development on a bounce) overrides this default.
handoff_default_target() {
    case "$1" in
        "Merging") echo "Ready for Merge" ;;
        *)         echo "" ;;
    esac
}

# escalation_resume_target <spawn-status> <ticket> — ADR-A-0019: the deterministic
# resume target for the tdm ESCALATION seat (spawned at Blocked) whose handoff
# declared NO target. Prints the status the runner should route to; empty for any
# other status (the loop-guard stays the backstop there). It NEVER prints Backlog:
# a Backlog park is legitimate ONLY when a seat DECLARES it (`target: Backlog`
# deprioritise verdict), which apply_handoff_transition honours BEFORE reaching
# here — so last_po_park_epoch / stall_raise_suppressed are untouched. A target-less
# resume is a mis-dump and must not masquerade as a park.
#   Blocked (tdm) -> Resume-to-Origin: the recorded BLOCKED-FROM pre-blocked work
#     status (last_transition_into_blocked_from). Backlog / Blocked / Needs PO
#     Decision are never a resume origin (no discretionary-Backlog dump, no
#     escalation-status ping-pong); with no usable origin it Halts in Blocked
#     (idempotent). The po-agent's `Needs PO Decision` seat is deliberately NOT
#     handled: that status is a pending product decision that must REST for the
#     PO-Agent (a target-less po-agent handoff never routes to Backlog via the
#     runner — a legit deprioritise is a DECLARED `target: Backlog`, applied above).
escalation_resume_target() {
    local to="$1" ticket="$2" dump origin
    [ "$to" = "Blocked" ] || return 0   # only the tdm/Blocked escalation seat
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    # ABS-336 / ADR-A-0014: an integration-conflict forward-fix that handed off
    # cleanly (no declared target) resumes to Architecture Review — re-review the
    # freshly-merged epic branch — NOT straight back to Epic Integration. The RTE
    # seat repeats the integration only after that review releases the epic again.
    if [ "${ORCH_INTEGRATION_CONFLICT_ROUTE:-1}" = "1" ] && is_integration_conflict "$dump"; then
        printf 'Architecture Review'; return 0
    fi
    origin="$(last_transition_into_blocked_from "$dump")"
    case "$origin" in
        ""|"Backlog"|"Blocked"|"Needs PO Decision") origin="" ;;
    esac
    if [ -n "$origin" ] && is_known_status "$origin"; then
        printf '%s' "$origin"
    else
        printf 'Blocked'
    fi
}

# merging_docs_waitstate_gate <ticket> <to> <target> <cur> <role> — the
# ready-for-Merge wait-state invariant (PILOT-2, origin ABS-492). Entry to `Docs`
# is legal from the human-owned `Ready for Merge` gate, the runner's own
# merge-confirmed release (merge_wait_release, ABS-270 — transitions FROM `Ready
# for Merge`, never reaches here), OR the accepted auto-merge rte exit that
# declares/self-moves `Merging -> Docs` AFTER a CONFIRMED merge (ADR-A-0014,
# statuses.yaml:275). The defect this gate fixes is narrower: a `Merging` seat
# jumping toward `Docs` while its PR is STILL UNMERGED — the v3-pilot finding
# (PILOT-1's seat did exactly that, and the runner only skip-logged it as "seat
# moved elsewhere"). So the gate is MERGE-STATE-AWARE, mirroring docs_pr_gate: it
# probes story_pr_state and repairs ONLY the unmerged jump, resting the story at
# `Ready for Merge` with a naming gate-results comment so it advances to `Docs`
# only once the merge is confirmed. A confirmed MERGED exit (the auto-merge happy
# path), a direct-to-branch story with no PR (NONE), the no-forge placeholder
# case, a clean target-less rte handoff (ABS-133 default -> Ready for Merge), a
# Ready-for-Development bounce, and Blocked are all UNTOUCHED (fail-open, no false
# alarm). 0 = intervened (repaired), 1 = no-op (normal handoff flow proceeds).
# Deliberately the same shape as docs_pr_gate: MODE-aware, --expect-from-guarded
# (lost race NOOPs, ABS-198).
merging_docs_waitstate_gate() {
    local ticket="$1" to="$2" target="$3" cur="$4" role="$5" pair state ref
    [ "$to" = "Merging" ] || return 1                       # only a Merging-seat handoff
    { [ "$target" = "Docs" ] || [ "$cur" = "Docs" ]; } || return 1   # Docs outcome only
    [ -n "$FORGE_CMD" ] || return 1        # no forge platform -> placeholder, nothing to gate (fail-open)
    pair="$(story_pr_state "$ticket")"
    state="${pair%%$'\t'*}"; ref="${pair##*$'\t'}"
    case "$state" in
        MERGED|NONE) return 1 ;;           # merge confirmed (ADR-A-0014 auto-merge exit) or no PR (direct-to-branch) -> the Docs jump is legal, allow it
    esac
    # state=OPEN (or any non-merged live state): the actual PILOT-1 defect — a jump
    # to Docs while the human merge is still pending. Refuse/repair it.
    intent MERGING-DOCS-WAITSTATE "$ticket" "$role" "Ready for Merge" \
        "refused UNMERGED Merging->Docs jump (pr ${ref:-?} state=$state cur=$cur target=$target); resting at the human merge gate"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "WAIT-STATE REPAIR: a 'Merging' seat handed off toward 'Docs' while its implementation PR ${ref:+$ref }is '$state' (NOT merged), bypassing the human-owned 'Ready for Merge' gate. Entry to 'Docs' is legal only from 'Ready for Merge', the runner's merge-confirmed release (merge_wait_release, ABS-270), or the auto-merge exit AFTER a confirmed merge (ADR-A-0014). Resting the story at 'Ready for Merge' instead of accepting the unmerged jump; once the merge is confirmed the runner advances it to 'Docs' on its own — no manual step (PILOT-2, origin ABS-492)." \
        >/dev/null 2>&1 || log "waitstate repair comment failed on $ticket"
    tracker transition "$ticket" "Ready for Merge" --actor orchestrator \
        --reason "WAIT-STATE REPAIR: unmerged 'Merging' -> 'Docs' jump refused (PR ${ref:-(unknown)} $state) — resting at the human-owned merge gate until the merge is confirmed (PILOT-2, origin ABS-492)" \
        --expect-from "$cur" \
        >/dev/null 2>&1 || log "waitstate repair transition failed on $ticket"
    return 0
}

# apply_handoff_transition <ticket> <to> <role> <handoff> — mechanism (a).
# Returns 0 when the ticket is at/moved to the declared target (nothing left to
# do or applied), non-zero when it could NOT move it (no target, or the adapter
# rejected the transition) — the caller then falls through to the loop-guard.
# ROLE-AGNOSTIC by design: a declared `to:` target is applied for ANY seat,
# including a po-agent FIRST-TRIAGE at Backlog (ABS-409). The po-agent that
# scores a parentless Backlog ticket and declares `to: Ready for Development`
# (or Design/PO Triage) is runner-applied here — no self-loop, no HANDOFF-NOMOVE
# respawn, no Needs PO Decision detour where a second seat re-does the move the
# first triage already decided. A target-less prose "dispatchable" verdict has no
# machine target and still rests to the loop-guard (mechanism b), so the miss is
# auditable rather than silent.
apply_handoff_transition() {
    local ticket="$1" to="$2" role="$3" handoff="$4" target cur reason
    [ "$ORCH_HANDOFF_TRANSITION" = "1" ] || return 1
    target="$(handoff_target_status "$handoff")"
    # ABS-133: no seat-declared target -> fall back to the per-status default
    # (Merging -> Ready for Merge) so the human-gate rest happens without the
    # seat prompt having to declare it. Still empty elsewhere -> loop-guard.
    [ -n "$target" ] || target="$(handoff_default_target "$to")"
    # ADR-A-0019: the tdm escalation seat (spawned at Blocked) that declared no
    # target resumes to its recorded BLOCKED-FROM origin or halts in Blocked —
    # never a discretionary Backlog dump. A declared target (incl. a legit
    # `target: Backlog` PO-park from the po-agent) already won above; this only
    # sets the missing-declaration default, leaving the PO-park guard path unchanged.
    [ -n "$target" ] || target="$(escalation_resume_target "$to" "$ticket")"
    [ -n "$target" ] || return 1
    cur="$(ticket_status "$ticket")"
    # PILOT-2 wait-state invariant: a Merging-seat handoff toward Docs (declared or
    # self-moved) is refused/repaired to the human-owned Ready for Merge gate BEFORE
    # the noop/skip branches below could accept or skip-log it (origin ABS-492).
    if merging_docs_waitstate_gate "$ticket" "$to" "$target" "$cur" "$role"; then
        return 0
    fi
    if [ "$cur" = "$target" ]; then
        # Ist=Soll: the seat already transitioned — idempotent no-op, NOT a
        # second transition (ticket AC 2). run.log records the observation.
        runlog RUNNER-TRANSITION "$ticket" "$role" "$target" "noop already-at-target (seat transitioned)"
        escalation_note_progress "$ticket" "$target"   # ABS-199 §d reset on forward progress
        return 0
    fi
    if [ "$cur" != "$to" ]; then
        # The seat moved it somewhere OTHER than its declared target — do not
        # fight it; the pipeline already advanced.
        runlog RUNNER-TRANSITION "$ticket" "$role" "$target" "skip current=$cur (seat moved elsewhere)"
        return 0
    fi
    reason="$(printf 'runner-applied handoff target: %s wants %s (ABS-132)' "$role" "$target")"
    if tracker transition "$ticket" "$target" --actor "$role" --reason "$reason" >/dev/null 2>&1; then
        intent RUNNER-TRANSITION "$ticket" "$role" "$target"
        escalation_note_progress "$ticket" "$target"   # ABS-199 §d reset on forward progress
        return 0
    fi
    log "runner-applied transition $ticket $to -> $target rejected (illegal or race); leaving to rest for the loop-guard"
    runlog RUNNER-TRANSITION "$ticket" "$role" "$target" "rejected from=$cur target=$target"
    return 1
}

# nomove_marker <status> — the greppable HANDOFF-NOMOVE marker line (mechanism b).
nomove_marker() { printf 'HANDOFF-NOMOVE status=%s (orchestrator)' "$1"; }

# nomove_count <ticket-dump> <status> — consecutive HANDOFF-NOMOVE markers for
# this status in the current stuck episode: markers (in orchestrator
# gate-results comments) since the most recent transition-reason line. ANY
# transition resets the window — a ticket that finally moves re-arms cleanly.
nomove_count() {
    printf '%s\n' "$1" | awk -v st="$2" '
        /^### / { in_orch = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/); next }
        /^Transition: .* -> / { n = 0; next }
        in_orch && index($0, "HANDOFF-NOMOVE status=" st " ") == 1 { n++ }
        END { print n + 0 }'
}

# record_async_wait_stall <ticket> <to> <role> — ABS-601: a seat that ended
# subtype=success but whose handoff only PROMISED to wait for an async background-
# task completion notification did NOTHING — a one-shot `claude -p` spawn has no
# later turn or event loop for the notification to arrive in. NAME the defect
# (ASYNC-WAIT-STALL, distinct from a generic HANDOFF-NOMOVE) and escalate straight
# to Needs PO Decision: an identical respawn reproduces the anti-pattern, so
# counting no-move rounds only burns budget and MASKS the WHY (Pilot 8 reached
# nomoves=2 then a generic escalation). Terminal / already-NPD stations are named
# but not re-escalated (no illegal self-transition). Kill-switch: ORCH_ASYNC_WAIT_SENSOR=0.
record_async_wait_stall() {
    local ticket="$1" to="$2" role="$3"
    intent ASYNC-WAIT-STALL "$ticket" "$role" "$to" "seat awaited an async completion notification a one-shot spawn never delivers (ABS-601)"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "ASYNC-WAIT-STALL status=$to role=$role (orchestrator): the $role spawn ended subtype=success but its handoff only PROMISED to wait for a background-task completion notification. A spawned seat is a ONE-SHOT claude -p invocation — no later turn and no surviving event loop — so that notification structurally cannot arrive and the seat advanced nothing. This is a DEFECT, not a successful run. Long-running work must run SYNCHRONOUSLY: a blocking call with a sufficient timeout, or the staged runner tests/staged-suite.sh with synchronous per-stage calls (Common Seat Rule 5, ABS-601)." \
        >/dev/null 2>&1 || log "async-wait-stall marker comment failed on $ticket"
    if ! status_is_terminal "$to" && [ "$to" != "Needs PO Decision" ]; then
        tracker comment "$ticket" --kind decision --actor orchestrator \
            --body "Escalating to Needs PO Decision: a $role seat at '$to' awaited an async completion notification a one-shot spawn cannot deliver (ABS-601). Retrying reproduces the anti-pattern; a human must re-route, or the work must be re-run synchronously." \
            >/dev/null 2>&1 || log "async-wait-stall escalation comment failed on $ticket"
        tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
            --reason "async-wait stall: seat awaited a completion notification a one-shot spawn never delivers (ABS-601)" \
            >/dev/null 2>&1 || log "async-wait-stall transition failed on $ticket"
    fi
}

# record_nomove <ticket> <to> <role> — mechanism (b): post the marker; at
# ORCH_RESPAWN_LIMIT consecutive markers escalate to Needs PO Decision. The
# escalation is suppressed when already at Needs PO Decision (no self-escalation,
# same guard shape as the escalation-seat crash halt).
record_nomove() {
    local ticket="$1" to="$2" role="$3" handoff="$4" dump n
    # ABS-601: a "success" handoff that only PROMISED to wait for an async
    # background-task completion notification is a DEFECT, not a no-move — a
    # one-shot spawn has no later turn for the notification to arrive in. Name it
    # (ASYNC-WAIT-STALL) and escalate directly, BEFORE the generic no-move path
    # masks it as a HANDOFF-NOMOVE that burns respawn budget on a futile retry.
    if [ "${ORCH_ASYNC_WAIT_SENSOR:-1}" = "1" ] && handoff_awaits_async_completion "$handoff"; then
        record_async_wait_stall "$ticket" "$to" "$role"
        return 0
    fi
    # ABS-339: terminal-status exemption for the ABS-132 respawn limiter.
    # A status with terminal: true in statuses.yaml (Epic Done) has no legal
    # forward edge (next: []): a Retro / Follow-up-watcher seat spawned there
    # CORRECTLY does not transition — its no-move handoff is the intended
    # terminal rest, not a stall. Counting it drove the limiter to escalate the
    # terminal ticket to Needs PO Decision, from which NO legal edge returns to
    # the terminal state, so the sweep re-derived endlessly (~$0.6-1.0/cycle) and
    # only a manual operator restore resolved it (evidence: ABS-111/126/279/181/190).
    # Skip the marker (so nomove_count never rises → the counter is not
    # incremented, AC1), the RESPAWN-LIMIT escalation (AC3), AND the ABS-199 stall
    # increment. The mixed-role pump (a self-improvement retro NOMOVE + a bsa
    # follow-up-watcher NOMOVE summing to the limit at one Epic Done, operator
    # evidence ABS-111) is covered because nomove_count keys on status, not role —
    # every terminal NOMOVE is skipped here regardless of seat. Mirrors
    # escalation_note_stall's guard; reads the flag from the file, never a
    # hardcoded name list (architect AD-2, ABS-301).
    if status_is_terminal "$to"; then
        intent HANDOFF-NOMOVE-EXEMPT "$ticket" "$role" "$to" "terminal rest (next: []); not counted (ABS-339)"
        return 0
    fi
    intent HANDOFF-NOMOVE "$ticket" "$role" "$to"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(nomove_marker "$to"): the $role handoff parsed but the ticket did not leave '$to' — no declared target the runner could apply and the seat did not transition. It rests; the sweep re-derives (ABS-132)." \
        >/dev/null 2>&1 || log "nomove marker comment failed on $ticket"
    [ "$to" != "Needs PO Decision" ] || return 0
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    n="$(nomove_count "$dump" "$to")"
    if [ "$n" -ge "$ORCH_RESPAWN_LIMIT" ]; then
        intent RESPAWN-LIMIT "$ticket" "$role" "Needs PO Decision" "nomoves=$n"
        tracker comment "$ticket" --kind decision --actor orchestrator \
            --body "Respawn limit reached: $n consecutive $role respawns at '$to' each parsed a handoff but never moved the ticket. Escalating to Needs PO Decision instead of resuming endlessly (ABS-132)." \
            >/dev/null 2>&1 || log "respawn-limit comment failed on $ticket"
        tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
            --reason "handoff parsed but status unchanged after $n respawns at $to (ABS-132)" \
            >/dev/null 2>&1 || log "respawn-limit transition failed on $ticket"
    fi
    # ABS-199 / ADR-A-0018 §d: this resting round advanced nothing → count it
    # toward the per-ticket escalation budget (the cross-visit backstop for the
    # ABS-181 bounce loop). Only when the ABS-132 RESPAWN-LIMIT escalation above
    # did NOT already move the ticket off this status (no double escalation).
    # ABS-311: but a no-move round that produced VERIFIED work is not a stall —
    # withhold the increment (escalation_work_credit returns 0). The counter is
    # paused, never reset: only a forward transition resets it (ABS-301 ratchet).
    if ticket_still_in "$ticket" "$to"; then
        if escalation_work_credit "$ticket" "$to" "$handoff"; then
            : # verified work this round → stall increment withheld (ABS-311)
        else
            escalation_note_stall "$ticket" "$to" "$role" || true
        fi
    fi
}

# =============================================================================
# ABS-255 / ADR-A-0024: handoff commit verification (the runner checks the hash)
# =============================================================================
# Lineage: consumer-feedback item 14 (Epic ABS-245) — the ui-ux-design seat
# claimed a template reconciliation TWICE; `git log -S` proved no ref ever
# contained it, and the downstream fe-developer seat ECHOED the claim. Handoff
# truthfulness (_common-rules §1, ABS-137) was an honor-system rule with no
# mechanical consequence, and a false claim became downstream context.
#
# The gate runs in the runner (deterministic, single-point, zero tokens) at the
# one choke point every accepted handoff passes through, BEFORE the transition
# is applied — never in a reviewer-seat template (the reference Befund IS a
# reviewer-side failure; see ADR-A-0024 (a)). It parses ONLY the declarative
# `commits:` field — never hex scraped from prose, which also matches PR ids and
# UUID fragments (a false positive on a BLOCKING gate costs a respawn cycle).
#
# Fail-OPEN on "cannot check" (no git, no repo, no claim); fail-CLOSED only when
# a check demonstrably says no.

# handoff_commits <handoff-text> — the hashes a handoff CLAIMS, one per line.
# Reads the declarative `- commits: <sha> [<sha> ...]` field only (ADR-A-0024 b).
# Non-hex tokens (e.g. "none", "n/a") are dropped, so a seat that writes
# `commits: none` is treated as claiming nothing rather than as a mis-report.
handoff_commits() {
    printf '%s\n' "$1" \
        | sed -n 's/^[[:space:]]*[-*]*[[:space:]]*commits:[[:space:]]*//p' \
        | head -1 | tr -d '`",' | tr ' ' '\n' | tr 'A-Z' 'a-z' \
        | grep -Eo '^[0-9a-f]{7,40}$' || true
}

# handoff_claims_commit <handoff-text> — 0 (true) when the PROSE claims a commit
# ("committed" / "pushed"). Only used for the non-blocking (f) advisory: a prose
# regex has a real false-positive class ("no code committed; review only" from a
# review/PO seat), so it never blocks — it only advises.
handoff_claims_commit() {
    printf '%s\n' "$1" | grep -Eiq '\b(commit(ted)?|pushed)\b'
}

# handoff_progress_marker <handoff-text> — 0 (true) when the handoff carries an
# explicit declarative `progress: <what advanced>` field naming what moved this
# round (ABS-311 credit source B — the artefact-free work marker, e.g. a bisect
# that produced no commit). Same declarative-field discipline as handoff_commits:
# a single `- progress: ...` line, never scraped from prose (a prose regex has a
# real false-positive class). A bare `progress: none` / `n/a` is not a claim.
handoff_progress_marker() {
    local val
    val="$(printf '%s\n' "$1" \
        | sed -n 's/^[[:space:]]*[-*]*[[:space:]]*progress:[[:space:]]*//p' \
        | head -1 | sed 's/[[:space:]]*$//')"
    [ -n "$val" ] || return 1
    case "$(printf '%s' "$val" | tr 'A-Z' 'a-z')" in
        none|n/a|na|-) return 1 ;;
    esac
    return 0
}

# handoff_awaits_async_completion <handoff-text> — 0 (true) when a handoff signals
# the seat is WAITING for an ASYNCHRONOUS background-task completion notification to
# arrive in a later turn (ABS-601). A spawned seat is a one-shot `claude -p`
# invocation with no surviving event loop, so this wait can NEVER resolve — the seat
# exits subtype=success having advanced nothing (Pilot 8: an RTE backgrounded the
# ~15-min suite and awaited a "completion notification", twice, and the epic
# escalated). Keyed on the SPECIFIC idiom (the literal "completion notification", a
# "keep checking until it …", a "wait for the background task/job/process", or a
# background task/job/process paired with "still running"/"before proceeding"), NOT
# on any mention of a background process — so a handoff that REPORTS a FINISHED
# background run ("suite passed, all stages green") does not false-match.
handoff_awaits_async_completion() {
    printf '%s' "$1" | tr '\n' ' ' | grep -Eiq \
        'completion notification|keep checking until it|wait(ing)? for the background (task|job|process)|background (task|job|process)[^.]{0,60}(has been running|still running|before proceeding|until it (completes|finishes|is done))'
}

# handoff_work_verified <handoff-text> — 0 (true) when the handoff carries
# commits: hashes that the runner could AND did VERIFY (existence +
# ref-reachability, ADR-A-0024 / ABS-255). This is ABS-311 credit source A:
# strong, evidence-bound, unbounded. Verification must actually run — a fail-open
# skip (verify off, no git, no repo) or a round with no claimed hashes is NOT
# verified work and returns 1 (no evidence → no credit; #PATH_DECISION). A round
# whose hashes FAIL verification never reaches here: it is refused as a
# HANDOFF-MISREPORT (record_misreport) before the no-move path, and counts as a stall.
handoff_work_verified() {
    local handoff="$1"
    [ "$ORCH_VERIFY_COMMITS" = "1" ] || return 1
    command -v git >/dev/null 2>&1 || return 1
    git -C "$ORCH_STATE_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 1
    [ -n "$(handoff_commits "$handoff")" ] || return 1
    [ -z "$(commit_verify_failures "$handoff")" ] || return 1
    return 0
}

# commit_verify_failures <handoff> — the verdict. Prints one "<sha>: <reason>"
# line per hash that FAILED a check; prints NOTHING when every claimed hash
# holds, when nothing is claimed, or when the gate cannot check (fail-open).
# Two checks per hash, against $ORCH_STATE_ROOT (git is not the tracker, so the
# runner shells it directly — same as ensure_worktree / done_pr_gate):
#   1. existence    — `git cat-file -e <sha>^{commit}`: the hash is FICTION.
#   2. reachability — `git for-each-ref --contains <sha>`: the commit exists as a
#      dangling object but NO REF CONTAINS IT (detached HEAD, or a branch since
#      reset/discarded) — exactly the Befund's ground truth. Checked against ANY
#      ref, not the ticket's work branch: ensure_worktree accepts any
#      refs/heads/<ticket>-* name and legit work may land on the epic branch.
commit_verify_failures() {
    local handoff="$1" sha shas
    [ "$ORCH_VERIFY_COMMITS" = "1" ] || return 0
    command -v git >/dev/null 2>&1 || return 0                      # cannot check
    git -C "$ORCH_STATE_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
    shas="$(handoff_commits "$handoff")"
    [ -n "$shas" ] || return 0                                      # no claim
    printf '%s\n' "$shas" | while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        if ! git -C "$ORCH_STATE_ROOT" cat-file -e "${sha}^{commit}" 2>/dev/null; then
            printf '%s: does not exist in the repository (git cat-file -e)\n' "$sha"
        elif [ -z "$(git -C "$ORCH_STATE_ROOT" for-each-ref --contains "$sha" --count=1 \
                        refs/heads/ refs/remotes/ 2>/dev/null)" ]; then
            printf '%s: exists but NO ref contains it (git for-each-ref --contains)\n' "$sha"
        fi
    done
}

# push_verify_failures <handoff> <to> — PILOT-75 / ADR-A-0024 + ADR-A-0030.
# The remote-reachability verdict. Prints one "<sha>: <reason>" line per CLAIMED
# commit that exists LOCALLY but is NOT reachable on the ACTIVE remote; prints
# NOTHING when every claimed commit is on the active remote, when nothing is
# claimed, when the transition does not claim completed work, or when the gate
# cannot check (fail-open).
#
# WHY a separate check from commit_verify_failures: that gate accepts a commit
# reachable from ANY local ref (refs/heads/ OR refs/remotes/) — a purely local,
# never-pushed commit satisfies it. That is exactly the four-Faelle Befund
# (ABS-581): the seat forward-transitions on work that lives only in its worktree
# and vanishes on cleanup. So for a forward transition that CLAIMS completion, the
# stronger success-condition is reachability under refs/remotes/<active-remote>/ —
# which `git push` updates locally on a successful push, so the check stays
# network-free like the rest of the runner (resolve_active_main_ref discipline).
#
# Scope: ONLY forward transitions that claim work COMPLETE — the story chain from
# 'In Review' (chain_index 4) through 'Done' (12). Backward moves, Design/RfD/In
# Progress, and every off-chain / epic / human-gate status are out of scope and
# fail-open (return nothing): a review/PO seat that legitimately produces no commit
# is never blocked. A pure-fiction hash (exists nowhere) is left to
# commit_verify_failures so the two gates never double-report the same sha.
push_verify_failures() {
    local handoff="$1" to="$2" idx remote sha shas
    [ "${ORCH_VERIFY_PUSH:-1}" = "1" ] || return 0
    command -v git >/dev/null 2>&1 || return 0                      # cannot check
    git -C "$ORCH_STATE_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
    idx="$(chain_index "$to")"
    # Only the story chain's completion span (In Review .. Done). 0 (off-chain),
    # 1..3 (Design/RfD/In Progress), and the 21.. epic range are all out of scope.
    { [ "$idx" -ge 4 ] && [ "$idx" -le 12 ]; } 2>/dev/null || return 0
    shas="$(handoff_commits "$handoff")"
    [ -n "$shas" ] || return 0                                      # no claim
    remote="$(active_remote_name)"
    [ -n "$remote" ] || return 0                                    # cannot resolve active remote
    printf '%s\n' "$shas" | while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        # A fictional hash (exists nowhere) is commit_verify_failures' report, not
        # ours — skip anything that does not exist locally so we never double-count.
        git -C "$ORCH_STATE_ROOT" cat-file -e "${sha}^{commit}" 2>/dev/null || continue
        if [ -z "$(git -C "$ORCH_STATE_ROOT" for-each-ref --contains "$sha" --count=1 \
                        "refs/remotes/$remote/" 2>/dev/null)" ]; then
            printf '%s: exists locally but NOT reachable on the active remote %s (never pushed; git for-each-ref refs/remotes/%s/)\n' \
                "$sha" "$remote" "$remote"
        fi
    done
}

# evidence_commit_failures <handoff> <ticket> — ABS-482 evidence-commit hygiene.
# Prints one "<sha>: <reason>" line per CLAIMED commit that TOUCHES the evidence
# path (docs/agent-outputs/**) but violates either invariant:
#   (a) foreign-file bundling — the same commit also touches non-evidence files
#       (dirty-workspace edits smuggled alongside the QA doc); or
#   (b) off-branch — the commit is NOT reachable from the ticket's OWN story
#       branch refs/heads/<ticket>-* (it landed on a foreign/stale branch, the
#       ABS-444-docs Befund). Non-evidence commits (product code) are IGNORED so
#       the ABS-255 epic-branch exemption for real work is untouched.
# Prints NOTHING when clean, when nothing is claimed, or when it cannot check
# (fail-open, same discipline as commit_verify_failures). Called with the ticket
# so it can name the required story branch.
evidence_commit_failures() {
    local handoff="$1" ticket="$2" shas
    [ "$ORCH_VERIFY_EVIDENCE" = "1" ] || return 0
    [ -n "$ticket" ] || return 0                                    # no anchor
    command -v git >/dev/null 2>&1 || return 0                      # cannot check
    git -C "$ORCH_STATE_ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
    shas="$(handoff_commits "$handoff")"
    [ -n "$shas" ] || return 0                                      # no claim
    printf '%s\n' "$shas" | while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        # A fictional hash yields no file list here (commit_verify_failures owns
        # the existence FAILURE report), so the empty-files guard below skips it.
        local files f has_ev=0 nonev="" nonev_n=0
        files="$(git -C "$ORCH_STATE_ROOT" show --no-renames --name-only \
                    --format='' "$sha" 2>/dev/null | grep -v '^$' || true)"
        [ -n "$files" ] || continue
        while IFS= read -r f; do
            [ -n "$f" ] || continue
            case "$f" in
                "$ORCH_EVIDENCE_PATH_PREFIX"*) has_ev=1 ;;
                *) nonev="$nonev $f"; nonev_n=$((nonev_n + 1)) ;;
            esac
        done <<EVIDENCE_FILES
$files
EVIDENCE_FILES
        [ "$has_ev" = "1" ] || continue                             # not an evidence commit
        # (a) foreign-file bundling
        if [ "$nonev_n" -gt 0 ]; then
            printf '%s: evidence commit bundles %s non-evidence file(s) outside %s** (dirty-workspace files smuggled):%s\n' \
                "$sha" "$nonev_n" "$ORCH_EVIDENCE_PATH_PREFIX" "$nonev"
        fi
        # (b) off the ticket's own story branch: no local branch whose name is
        #     <ticket> or <ticket>-* (the ensure_worktree namespace) contains this
        #     commit. Filtering refname:short by prefix is robust where a
        #     for-each-ref glob pattern is not.
        local br on_story=0
        while IFS= read -r br; do
            [ -n "$br" ] || continue
            case "$br" in
                "$ticket"|"$ticket"-*) on_story=1; break ;;
            esac
        done <<STORY_BRANCHES
$(git -C "$ORCH_STATE_ROOT" for-each-ref --contains "$sha" \
        --format='%(refname:short)' refs/heads/ 2>/dev/null)
STORY_BRANCHES
        if [ "$on_story" != "1" ]; then
            printf '%s: evidence commit is not on the story branch of %s (refs/heads/%s-*); it landed on a foreign/stale branch\n' \
                "$sha" "$ticket" "$ticket"
        fi
    done
}

# misreport_marker <status> — the greppable HANDOFF-MISREPORT marker line. A
# marker DISTINCT from HANDOFF-NOMOVE keeps the two diagnosable apart while both
# land in the same escalation budget (ADR-A-0024 e).
misreport_marker() { printf 'HANDOFF-MISREPORT status=%s (orchestrator)' "$1"; }

# misreport_count <ticket-dump> <status> — consecutive HANDOFF-MISREPORT markers
# for this status since the most recent transition. Same shape as nomove_count.
misreport_count() {
    printf '%s\n' "$1" | awk -v st="$2" '
        /^### / { in_orch = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/); next }
        /^Transition: .* -> / { n = 0; next }
        in_orch && index($0, "HANDOFF-MISREPORT status=" st " ") == 1 { n++ }
        END { print n + 0 }'
}

# record_misreport <ticket> <to> <role> <failures> — ADR-A-0024 (d): refuse the
# handoff and put the work back on the seat that claimed it.
#   1. the declared transition is NOT applied (the caller returns before it);
#   2. a self-transition is UNDONE — back to the spawn status, actor = the seat
#      role, so rework_count() counts the backward non-human transition NATIVELY
#      (AC3: no new counter) and ORCH_REWORK_LIMIT bounds the bounce;
#   3. a gate-results comment names EACH failing hash and WHICH check it failed
#      (auditable; the next spawn's session-resume sees what was disbelieved);
#   4. the ticket rests — the sweep re-spawns the same seat to actually commit;
#      the rested branch feeds the ADR-A-0018 escalation budget + the
#      ORCH_RESPAWN_LIMIT escalation, mirroring record_nomove.
record_misreport() {
    local ticket="$1" to="$2" role="$3" failures="$4" cur dump n
    intent HANDOFF-MISREPORT "$ticket" "$role" "$to"
    log "handoff MISREPORT on $ticket ($role): claimed commits do not verify"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(misreport_marker "$to"): the $role handoff claimed commits that FAILED runner verification, so the handoff was NOT accepted and the declared transition was refused (ADR-A-0024, ABS-255).

Failing hashes:
$(printf '%s\n' "$failures" | sed 's/^/- /')

Every hash on a handoff's \`commits:\` line is checked against the repository for (1) existence (\`git cat-file -e <sha>^{commit}\`) and (2) reachability (\`git for-each-ref --contains <sha>\` — at least one ref must contain it). A commit that no ref contains never reached the repository, whatever the handoff prose says (_common-rules §1 Evidence-Disziplin, ABS-137/ABS-174).

The ticket rests in '$to'. The next spawn of $role MUST actually create and push the commits it claims, and name the real hashes on the \`commits:\` line." \
        >/dev/null 2>&1 || log "misreport marker comment failed on $ticket"
    # (d.2) Undo a self-transition. If the seat moved the ticket off its spawn
    # status before lying about the commit, transition it BACK — actor = the seat
    # role, so rework_count() counts the backward non-human move NATIVELY (AC3, no
    # new counter) and ORCH_REWORK_LIMIT / escalate_rework bounds the bounce. This
    # backward move also resets the misreport window, so the rested-path counting
    # below is deliberately skipped in this branch (the two branches feed two
    # different existing counters — ADR-A-0024 (e)).
    cur="$(ticket_status "$ticket")"
    if [ -n "$cur" ] && [ "$cur" != "$to" ]; then
        if tracker transition "$ticket" "$to" --actor "$role" \
            --reason "handoff mis-report: claimed commits do not verify; undoing the self-transition back to $to (ADR-A-0024, ABS-255)" \
            >/dev/null 2>&1; then
            intent MISREPORT-UNDO "$ticket" "$role" "$to" "from=$cur"
        else
            log "misreport back-transition $ticket $cur -> $to failed"
        fi
        return 0
    fi
    [ "$to" != "Needs PO Decision" ] || return 0
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    n="$(misreport_count "$dump" "$to")"
    if [ "$n" -ge "$ORCH_RESPAWN_LIMIT" ]; then
        intent RESPAWN-LIMIT "$ticket" "$role" "Needs PO Decision" "misreports=$n"
        tracker comment "$ticket" --kind decision --actor orchestrator \
            --body "Respawn limit reached: $n consecutive $role handoffs at '$to' claimed commits that do not verify. Escalating to Needs PO Decision instead of respawning a seat that keeps mis-reporting (ADR-A-0024, ABS-255)." \
            >/dev/null 2>&1 || log "misreport respawn-limit comment failed on $ticket"
        tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
            --reason "handoff claimed unverifiable commits on $n consecutive respawns at $to (ADR-A-0024, ABS-255)" \
            >/dev/null 2>&1 || log "misreport respawn-limit transition failed on $ticket"
    fi
    # ADR-A-0018 §d: this round advanced nothing → count it toward the per-ticket
    # escalation budget, but only if the escalation above did not already move it.
    if ticket_still_in "$ticket" "$to"; then
        escalation_note_stall "$ticket" "$to" "$role" || true
    fi
}

# record_claim_nohash <ticket> <to> <role> — ADR-A-0024 (f): the handoff PROSE
# claims a commit but names NO hash. This violates the (b) contract but is
# deliberately NOT blocked in v1 and does NOT count: the only detector is a prose
# regex with a real false-positive class (review/PO seats correctly write "no code
# committed; review only"), and a blocking gate with known false positives is
# worse than an honest advisory (ADR-A-0010). It emits the evidence needed to
# decide the promotion to the blocking path.
record_claim_nohash() {
    local ticket="$1" to="$2" role="$3"
    intent HANDOFF-CLAIM-NOHASH "$ticket" "$role" "$to"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "HANDOFF-CLAIM-NOHASH status=$to role=$role (orchestrator): this handoff's prose mentions a commit but carries no \`commits:\` field, so the runner could not verify it. ADVISORY ONLY — the handoff was accepted and nothing was counted (ADR-A-0024 (f)). A seat that commits MUST name its hashes on a \`commits: <sha> [<sha> ...]\` line (_common-rules §1); it already runs \`git log --oneline -1\`, so this only makes the evidence machine-readable." \
        >/dev/null 2>&1 || log "claim-nohash advisory comment failed on $ticket"
}

# =============================================================================
# ABS-297 / ADR-A-0024: marker duty validation — runner refuses handoff claims
# whose required machine-readable marker is absent on the target ticket.
# Follows the ABS-255 commit-hash refusal precedent: declared transition not
# applied; gate-results comment names the required marker and where it must go;
# seat is bounced back to actually post the marker before handing off again.
# Two duties: (a) JOIN exemption; (b) bsa follow-up decision.
# Kill-switch: ORCH_VERIFY_MARKERS=0 restores pre-ABS-297 behaviour (default 1).
# Architecture (ABS-297 arch note): functions are table-driven off the EXISTING
# marker printers — join_exempt_marker() and followup_pending_count — so this
# detector cannot drift from the vocabulary it validates.
# =============================================================================

# marker_missing_marker <required-marker> <on-ticket> — greppable token posted
# in the gate-results comment body, keyed by the required marker text and the
# ticket it must appear on. Called with join_exempt_marker() or "kind: bsa-decision"
# — never a hardcoded literal — so it cannot drift from the printer it validates.
marker_missing_marker() { printf 'MARKER-MISSING: required=[%s] on=%s (orchestrator)' "$1" "$2"; }

# handoff_claims_join_exempt <handoff-text> — 0 (true) when the handoff prose
# contains the join_exempt_marker() token, indicating the seat claims to have
# posted the JOIN exemption on a child. Driven off join_exempt_marker() so this
# detector never drifts from the printer it validates (ABS-297 arch).
handoff_claims_join_exempt() {
    printf '%s\n' "$1" | grep -qF "$(join_exempt_marker)"
}

# handoff_join_exempt_child_ids <handoff-text> <parent-id> — print each ticket
# ID that appears on the SAME LINE as the join_exempt_marker() token, excluding
# the parent ticket itself. These are the children the handoff claims to have
# exempted from the JOIN gate. Scoping to the same line keeps extraction precise
# and fail-open: if no ticket ID appears on that line, nothing is returned and
# the check is skipped rather than blocking a legitimate handoff.
handoff_join_exempt_child_ids() {
    local marker; marker="$(join_exempt_marker)"
    printf '%s\n' "$1" | grep -F "$marker" \
        | grep -Eo '[A-Z][A-Z0-9]+-[0-9]+' | grep -v "^${2}$" | sort -u || true
}

# handoff_claims_followup_empty <handoff-text> — 0 (true) when the handoff
# claims the follow-up pile is empty / all bsa-decisions have been posted.
# Pattern targets the incident idioms ("pile is empty", "no pending follow-ups",
# "all follow-ups answered") while remaining false-positive-safe for passing
# references such as "created a follow-up ticket" or "follow-up SOP".
handoff_claims_followup_empty() {
    printf '%s\n' "$1" | grep -Eiq \
        '(follow[- ]?up|pile).{0,40}(empty|no.{0,15}pending|all.{0,20}answer|all.{0,20}done|all.{0,20}process)'
}

# record_marker_missing <ticket> <to> <role> <required-marker> <on-ticket> —
# ABS-297: refuse a handoff that claims an effect not backed by a machine-readable
# marker. Mirrors record_misreport (ADR-A-0024): the declared transition is not
# applied; a gate-results comment names the required marker and the ticket it
# must go on; a seat self-transition is undone (actor = seat role so rework_count
# counts it natively — same pattern as ABS-255 AC3).
record_marker_missing() {
    local ticket="$1" to="$2" role="$3" marker="$4" on="$5" cur
    intent MARKER-MISSING "$ticket" "$role" "$to" "marker=$marker on=$on"
    log "handoff MARKER-MISSING on $ticket ($role): claimed '$marker' but it is absent on $on"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(marker_missing_marker "$marker" "$on"): the $role handoff claims an effect that requires the marker '$marker' to exist on $on, but that marker is absent. The handoff was NOT accepted and the declared transition was refused (ABS-297, ADR-A-0024).

To fix: post a \`kind: decision\` comment on $on whose body contains the exact text '$marker', then hand off again. The runner re-validates on the next attempt and accepts as soon as the marker is present." \
        >/dev/null 2>&1 || log "marker-missing comment failed on $ticket"
    # Undo a seat self-transition: if the seat moved the ticket off the spawn
    # status before claiming the marker, transition it back (actor = seat role so
    # rework_count counts the backward move natively, mirroring record_misreport d.2).
    cur="$(ticket_status "$ticket")"
    if [ -n "$cur" ] && [ "$cur" != "$to" ]; then
        if tracker transition "$ticket" "$to" --actor "$role" \
            --reason "handoff marker-missing: '$marker' absent on $on; undoing self-transition back to $to (ABS-297)" \
            >/dev/null 2>&1; then
            intent MARKER-MISSING-UNDO "$ticket" "$role" "$to" "from=$cur"
        else
            log "marker-missing back-transition $ticket $cur -> $to failed"
        fi
    fi
}

# handoff_seat_race_refused <ticket> <to> <role> — ABS-300. 0 (refuse) when a
# still-LIVE seat lock (age < ORCH_LOCK_TTL) on this ticket is owned by a seat
# OTHER than the current handoff author ($ORCH_SEAT_TOKEN); else 1 (proceed).
# A foreign handoff must not overwrite the station of a live seat (the ABS-254
# hijack: a sweep-spawned bsa follow-up moved the ticket the active RTE Merging
# seat still owned). The refusal keeps the station, records SEAT-RACE + a comment,
# and returns before ANY budget-bearing path — a race is not the seat's fault, so
# it must not count as a HANDOFF-NOMOVE/misreport stall.
# Fail-OPEN (never a false refusal): guard off, no lock, an unstamped (legacy)
# lock, an unknown author, this seat owning the lock, or a STALE lock (age >=
# ORCH_LOCK_TTL — a dead seat must not freeze the ticket) all proceed.
handoff_seat_race_refused() {
    local ticket="$1" to="$2" role="$3" owner age
    [ "$ORCH_SEAT_RACE_GUARD" = "1" ] || return 1
    [ -n "${ORCH_SEAT_TOKEN:-}" ] || return 1          # author unknown -> never refuse
    [ -d "$(lock_dir_for "$ticket")" ] || return 1     # no seat holds the station
    owner="$(seat_lock_owner "$ticket")"
    [ -n "$owner" ] || return 1                        # unstamped (legacy) lock
    [ "$owner" != "$ORCH_SEAT_TOKEN" ] || return 1     # this seat owns it -> proceed
    age="$(lock_age_for "$ticket" 2>/dev/null || echo 0)"
    [ "$age" -lt "$ORCH_LOCK_TTL" ] || return 1        # stale lock: dead seat, do not freeze
    # A live, foreign seat owns the station -> refuse this handoff's transition.
    intent SEAT-RACE "$ticket" "$role" "$to" "owner=$owner"
    runlog SEAT-RACE "$ticket" "$role" "$to" "refused: live lock held by another seat (owner=$owner author=$ORCH_SEAT_TOKEN age=${age}s)"
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "SEAT-RACE status=$to role=$role (orchestrator): a $role handoff declared a transition out of '$to', but a still-live seat lock (age ${age}s < ${ORCH_LOCK_TTL}s) is held by another seat. The station belongs to the live owner — the declared transition is NOT applied and the owning seat continues undisturbed. This refusal does not count against the ticket's rework/no-move budget (ABS-300, evidence ABS-254)." \
        >/dev/null 2>&1 || log "seat-race comment failed on $ticket"
    return 0
}

# handoff_followthrough <ticket> <to> <role> <handoff> — the post-handoff step
# wired into both live_spawn success paths: verify the commits the handoff CLAIMS
# (ABS-255), then apply the declared transition, then (if the ticket is STILL
# resting in its spawn status) run the loop-guard.
# Always returns 0 — a follow-through hiccup must never fail the spawn (set -e).
handoff_followthrough() {
    local ticket="$1" to="$2" role="$3" handoff="$4" failures
    # ABS-300: refuse a foreign handoff BEFORE any budget-bearing path (commit
    # verify / marker duty / apply / no-move). A live seat owns the station; a
    # race is not this seat's fault, so it must not consume rework/no-move budget.
    if handoff_seat_race_refused "$ticket" "$to" "$role"; then
        return 0
    fi
    # ABS-255 / ADR-A-0024: verify BEFORE accepting. A handoff whose claimed
    # commits do not verify is refused — the declared transition is never applied
    # and the work bounces back to the seat, so a false claim can never become
    # downstream context (the fe-developer echo is structurally prevented).
    failures="$(commit_verify_failures "$handoff")"
    # ABS-482: evidence-commit hygiene — a QA/evidence commit off the story branch
    # or bundling foreign dirty-workspace files is refused on the SAME path as a
    # commit mis-report (the declared transition is never applied; the work bounces
    # back to the seat). Appended to the commit-verify failures so both flow through
    # record_misreport in one refusal.
    local evfailures
    evfailures="$(evidence_commit_failures "$handoff" "$ticket")"
    if [ -n "$evfailures" ]; then
        failures="$(printf '%s\n%s' "$failures" "$evfailures" | grep -v '^$' || true)"
    fi
    # PILOT-75 / ADR-A-0024 + ADR-A-0030: for a FORWARD transition that claims work
    # COMPLETE (In Review and beyond), the claimed commits must be reachable on the
    # ACTIVE remote — a purely local, never-pushed commit lies about the remote's
    # state and vanishes on worktree cleanup (ABS-581). Appended to the failures so a
    # not-pushed commit is refused on the SAME mis-report path (declared transition
    # never applied; work bounces back to the seat to actually push).
    local pushfailures
    pushfailures="$(push_verify_failures "$handoff" "$to")"
    if [ -n "$pushfailures" ]; then
        failures="$(printf '%s\n%s' "$failures" "$pushfailures" | grep -v '^$' || true)"
    fi
    if [ -n "$failures" ]; then
        record_misreport "$ticket" "$to" "$role" "$failures"
        return 0
    fi
    # (f) advisory: prose claims a commit but named no hash — never blocking.
    if [ "$ORCH_VERIFY_COMMITS" = "1" ] && [ -z "$(handoff_commits "$handoff")" ] \
       && handoff_claims_commit "$handoff"; then
        record_claim_nohash "$ticket" "$to" "$role"
    fi
    # ABS-297 / ADR-A-0024: marker duty — JOIN exemption.
    # A handoff containing the join_exempt_marker() token is claiming the seat
    # posted it on a child. Verify each claimed child actually carries the marker;
    # refuse if any does not (same path as commit mis-report). Fail-open when no
    # child ID is extractable from the same line as the token.
    if [ "${ORCH_VERIFY_MARKERS:-1}" = "1" ] && handoff_claims_join_exempt "$handoff"; then
        local child_id missing_child=""
        while IFS= read -r child_id; do
            [ -n "$child_id" ] || continue
            if ! child_join_exempt "$child_id" 2>/dev/null; then
                missing_child="$child_id"
                break
            fi
        done <<EXEMPT_IDS
$(handoff_join_exempt_child_ids "$handoff" "$ticket")
EXEMPT_IDS
        if [ -n "$missing_child" ]; then
            record_marker_missing "$ticket" "$to" "$role" "$(join_exempt_marker)" "$missing_child"
            return 0
        fi
    fi
    # ABS-297 / ADR-A-0024: marker duty — bsa follow-up decision.
    # A handoff claiming the follow-up pile is empty must have the kind:
    # bsa-decision replies that actually cleared the pending count. Refuse if
    # the ticket still carries unanswered follow-up comments.
    if [ "${ORCH_VERIFY_MARKERS:-1}" = "1" ] && handoff_claims_followup_empty "$handoff"; then
        if epic_has_unprocessed_followups "$ticket"; then
            record_marker_missing "$ticket" "$to" "$role" "kind: bsa-decision" "$ticket"
            return 0
        fi
    fi
    apply_handoff_transition "$ticket" "$to" "$role" "$handoff" || true
    if ticket_still_in "$ticket" "$to"; then
        # ABS-203: a write-light Path-B enrichment that handed off cleanly but
        # never moved the epic (dedup was a no-op; the seat's own exit transition
        # was tracker-write-denied) is completed forward by the runner instead of
        # looping toward the no-move respawn escalation.
        writelight_enrichment_complete "$ticket" "$to" "$role" && return 0
        # ABS-214: a decomposed epic (children already released) whose po-agent
        # handoff parsed cleanly but declared no legal target out of Backlog is
        # rested forward into its JOIN state (Stories In Flight) by the runner,
        # instead of looping as a HANDOFF-NOMOVE in Backlog until an operator
        # hand-transitions it.
        epic_join_rest_complete "$ticket" "$to" "$role" && return 0
        record_nomove "$ticket" "$to" "$role" "$handoff"
    fi
    return 0
}

# =============================================================================
# ABS-203: write-light Path-B enrichment (no-op dedup tolerant of write denial)
# =============================================================================
# Lineage: ABS-181 (issue-enrichment write-denial crash → catastrophic re-cycle
# loop). When the Enrichment seat re-runs on an epic whose children ALREADY
# exist, its per-draft dedup yields NO new tickets — every create would be a
# no-op. The only substantive write left is the completion signal (the exit
# transition Enrichment → Ticket Review). If a tool-policy denial blocks the
# seat's writes, the seat must not crash and the epic must not be left resting
# in Enrichment (which the reconcile sweep re-derives → same denial → loop).

# enrichment_write_mode <epic> — classify an issue-enrichment spawn's write
# needs from the epic's current child count (adapter-only read, ADR-A-0007):
#   write-light — child-count > 0: the children already exist, so this run's
#                 dedup is a no-op; the seat skips child-creation writes and
#                 emits only the completion signal.
#   full-write  — child-count == 0: the FIRST enrichment, which MUST create the
#                 child set (never write-skipped — AC3, no dropped children).
enrichment_write_mode() {
    local epic="$1" count
    count="$(tracker child-count "$epic" 2>/dev/null || echo 0)"
    case "$count" in ''|*[!0-9]*) count=0 ;; esac
    if [ "$count" -gt 0 ]; then echo "write-light"; else echo "full-write"; fi
}

# writelight_enrichment_complete <ticket> <to> <role> — the runner-side
# completion signal for a write-light Path-B enrichment. Returns 0 (handled)
# when this is a write-light issue-enrichment spawn at Enrichment and either the
# epic already advanced (seat moved it — nothing to do) or the runner emitted the
# forward transition itself via $TRACKER_CMD (the lightest path, outside the
# seat's denied sandbox); non-zero (not handled) when the guard does not apply,
# so callers fall through to their normal crash / no-move handling. Scoped
# strictly to write-light: a full-write first enrichment (child-count == 0) is
# never short-circuited, so no children are dropped (AC3). An incomplete child
# set forwarded here is caught by the downstream Ticket-Review DoR gate
# (spec ABS-103 §6), never silently lost.
writelight_enrichment_complete() {
    local ticket="$1" to="$2" role="$3" target="Ticket Review"
    [ "$role" = "issue-enrichment" ] || return 1
    [ "$to" = "Enrichment" ] || return 1
    [ "$(enrichment_write_mode "$ticket")" = "write-light" ] || return 1
    # Seat already advanced the epic (its writes went through) — clean, nothing
    # left for the runner to do.
    ticket_still_in "$ticket" "$to" || return 0
    if [ "$MODE" != "live" ]; then
        intent WRITE-LIGHT-COMPLETE "$ticket" "$role" "$target" "dry-run"
        return 0
    fi
    if tracker transition "$ticket" "$target" --actor "$role" \
        --reason "ABS-203 write-light Path-B: epic children already exist (dedup no-op); runner emitted the completion signal after a seat tracker-write denial" \
        >/dev/null 2>&1; then
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "WRITE-LIGHT-COMPLETE status=$to role=$role (orchestrator): the epic's children already exist (dedup no-op) and the seat did not transition — the runner emitted the completion signal (-> $target) via \$TRACKER_CMD. A tracker-write denial at this seat is non-catastrophic; no re-cycle (ABS-203, lineage ABS-181)." \
            >/dev/null 2>&1 || log "write-light-complete comment failed on $ticket"
        intent WRITE-LIGHT-COMPLETE "$ticket" "$role" "$target"
        return 0
    fi
    log "write-light enrichment completion transition $ticket $to -> $target rejected; falling through to normal handling"
    return 1
}

# =============================================================================
# ABS-214: epic JOIN-rest completion (decomposed epic resting in Backlog)
# =============================================================================
# Lineage: recurring HANDOFF-NOMOVE loop on decomposed epics (ABS-190 [3
# incidents 2026-07-10/11], ABS-181, ABS-153, ABS-152, ABS-138). The po-agent
# decomposes a bare epic (Branch B), releases its children as Ready for
# Development, then leaves the epic resting in Backlog. On the next sweep the
# Backlog seat re-spawns the po-agent on that now-decomposed epic, but Backlog
# has no legal edge into the epic's correct JOIN rest-state (Stories In Flight)
# — so the po-agent's clean handoff never moves the epic and record_nomove
# fires, run after run, until an operator hand-transitions it (or the po-agent
# does a Backlog->Blocked workaround just to have a declared target).
#
# The Backlog->Stories In Flight edge is now legal (profiles/neutral/adapters/
# statuses.yaml). This runner-side completion is the deterministic backstop
# (analog to writelight_enrichment_complete, ABS-203): when a po-agent handoff
# parses cleanly but leaves a DECOMPOSED epic (child-count > 0, adapter-only
# read per ADR-A-0007) resting in Backlog, the runner emits the JOIN-rest
# transition itself instead of recording a no-move. The JOIN rule (ABS-73) then
# advances the epic to Epic Integration mechanically once all children are Done
# — existing behavior, unchanged.

# epic_join_rest_complete <ticket> <to> <role> — returns 0 (handled) when this
# is a po-agent spawn at Backlog on a decomposed epic and either the seat
# already advanced the epic (nothing to do) or the runner emitted the JOIN-rest
# transition (Backlog -> Stories In Flight) via $TRACKER_CMD; non-zero (not
# handled) when the guard does not apply, so callers fall through to their
# normal no-move handling. Scoped strictly: an epic with NO children
# (child-count == 0 — undecomposed, or a plain Backlog ticket) is never moved,
# so a bare epic still rests for the ABS-62 stall rule and a normal ticket that
# the po-agent deprioritised keeps resting in Backlog.
epic_join_rest_complete() {
    local ticket="$1" to="$2" role="$3" target="Stories In Flight" count
    [ "$role" = "po-agent" ] || return 1
    [ "$to" = "Backlog" ] || return 1
    count="$(tracker child-count "$ticket" 2>/dev/null || echo 0)"
    case "$count" in ''|*[!0-9]*) count=0 ;; esac
    [ "$count" -gt 0 ] || return 1
    # Seat already advanced the epic (its own transition went through) — clean,
    # nothing left for the runner to do.
    ticket_still_in "$ticket" "$to" || return 0
    if [ "$MODE" != "live" ]; then
        intent EPIC-JOIN-REST "$ticket" "$role" "$target" "dry-run children=$count"
        return 0
    fi
    if tracker transition "$ticket" "$target" --actor "$role" \
        --reason "ABS-214 epic JOIN-rest: decomposed epic ($count children released) has no legal edge out of Backlog; runner emitted the JOIN-rest completion so it rests in its correct state instead of a HANDOFF-NOMOVE loop" \
        >/dev/null 2>&1; then
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "EPIC-JOIN-REST status=$to role=$role (orchestrator): decomposed epic with $count released children and no legal edge out of Backlog — the runner emitted the JOIN-rest completion (-> $target) via \$TRACKER_CMD. The JOIN rule (ABS-73) advances it once all children are Done; no operator hand-transition, no HANDOFF-NOMOVE loop (ABS-214, lineage ABS-203/ABS-190)." \
            >/dev/null 2>&1 || log "epic-join-rest comment failed on $ticket"
        # ABS-301 §d ratchet fix: runner-mechanical epic transition must reset
        # the escalation counter so Stories In Flight (chain_index 26) is
        # recorded as forward progress and the stall counter starts from 0.
        escalation_note_progress "$ticket" "$target"
        intent EPIC-JOIN-REST "$ticket" "$role" "$target" "children=$count"
        return 0
    fi
    log "epic JOIN-rest completion transition $ticket $to -> $target rejected; falling through to normal handling"
    return 1
}

# =============================================================================
# ABS-199 / ADR-A-0018 — cross-visit same-blocker loop-breaker + escalation budget
# =============================================================================
# The per-visit ABS-132 (no-move) and ABS-74 (crash) escalations count failures
# WITHIN one resting episode and re-arm on any transition. They are blind to a
# ticket that keeps hitting the SAME external wall across different statuses
# (ABS-181 cycled 5x; ABS-168 burned 4 dispatches on one deterministic denial).
# This module adds a second, orthogonal axis: cross-visit memory of WHY a ticket
# keeps failing, so a deterministic denial parks after one retry instead of
# relearning the same wall. State lives in per-ticket marker files under
# $ORCH_STATE_DIR (the machine authority; the tracker comment stays the audit
# trail — ADR-A-0018 §b). See adrs/agentic/ADR-A-0018-cross-visit-blocker-classification.md.

blocker_file()    { echo "$ORCH_STATE_DIR/blocker-$1"; }
escalation_file() { echo "$ORCH_STATE_DIR/escalation-$1"; }

# blocker_class <diag> [marker] — classify a failed dispatch into EXACTLY one
# class, derived mechanically from the ABS-151 crash diagnostic + gate markers,
# never from prose (ADR-A-0018 §a). Precedence environment-denial > turn-cap >
# transient > logic; an unmatched diagnostic defaults to transient (the SAFE
# default — keeps recover-and-retry rather than parking a possibly-recoverable
# ticket).
blocker_class() {
    local hay
    hay="$(printf '%s\n%s' "${1:-}" "${2:-}" | tr 'A-Z' 'a-z')"
    # (a) environment-denial — deterministic tool-policy / permission denial.
    case "$hay" in
        *denied*|*denial*|*permission*|*"not allowed"*|*"not permitted"*|*"write-protect"*|\
        *"write protection"*|*dontask*|*allowlist*|*forbidden*|*"read-only file system"*|\
        *eacces*|*eperm*|*"operation not permitted"*)
            echo "environment-denial"; return 0 ;;
    esac
    # (a2) turn-cap — the seat ran to its turn ceiling (error_max_turns). PILOT-65
    #      AC3: its OWN class, NOT a generic crash. Recoverable like transient (the
    #      ABS-175 salvage resume, then retry) and budget-neutral for the iteration/
    #      rework counters (the iteration-guard INFRA_ABORT_RE excludes it; the
    #      rework counter skips the orchestrator-actor route that carries it), so a
    #      cap abort is never billed as a functional bounce (AC4). Kept ahead of the
    #      transient bucket so a cap exit is labelled distinctly in the blocker log.
    case "$hay" in
        *"turn ceiling"*|*error_max_turns*|*"max_turns"*|*"turn cap"*|*"turn-cap"*)
            echo "turn-cap"; return 0 ;;
    esac
    # (b) transient — network / rate-limit / auth / non-zero exit / empty handoff.
    #     Recoverable: retry is the remedy (ABS-118/ABS-74 path).
    case "$hay" in
        *"rate limit"*|*ratelimit*|*network*|*timeout*|*"non-zero exit"*|*"no parseable handoff"*|\
        *"connection"*|*"exit="*|*auth*)
            echo "transient"; return 0 ;;
    esac
    # (c) logic — a parsed handoff that bounces on a test/gate failure (ticket-owned).
    case "$hay" in
        *"gate fail"*|*"test fail"*|*"tests failed"*|*rework*|*bounce*|*"ac not met"*|*"handoff-nomove"*)
            echo "logic"; return 0 ;;
    esac
    echo "transient"   # unmatched -> safe default
}

# blocker_class_seat_count <ticket> <class> <seat> — number of recorded lines
# with the SAME (class, seat) across ANY visit (0 when no marker file).
blocker_class_seat_count() {
    local f; f="$(blocker_file "$1")"
    [ -f "$f" ] || { echo 0; return 0; }
    awk -F'\t' -v c="$2" -v s="$3" '$1 == c && $2 == s { n++ } END { print n + 0 }' "$f"
}

# record_blocker <ticket> <class> <seat> <status> — append one cross-visit line
# (class \t seat \t visit-status \t timestamp) and echo the resulting count of
# lines with the same (class, seat), INCLUDING this one.
record_blocker() {
    local f; f="$(blocker_file "$1")"
    printf '%s\t%s\t%s\t%s\n' "$2" "$3" "$4" "$(timestamp)" >> "$f" 2>/dev/null || true
    blocker_class_seat_count "$1" "$2" "$3"
}

# blocker_notified <ticket> <key> — 0 (true) when a NOTIFIED <key> line already
# exists (ADR-A-0018 §e dedup: exactly one operator NOTIFY per distinct dead-end).
blocker_notified() {
    local f; f="$(blocker_file "$1")"
    [ -f "$f" ] || return 1
    grep -qF "NOTIFIED $2" "$f" 2>/dev/null
}
mark_blocker_notified() {
    printf 'NOTIFIED %s\n' "$2" >> "$(blocker_file "$1")" 2>/dev/null || true
}

# crossvisit_autopark <ticket> <class> <seat> <status> — the §c/§e loop-breaker:
# park to Blocked (human-owned, NOT the reconcilable Needs PO Decision) with a
# single deduped operator NOTIFY and NO re-spawn. Always returns 0 (the caller
# treats a park as "handled — do not fall through to the per-visit path").
crossvisit_autopark() {
    local ticket="$1" class="$2" seat="$3" status="$4" key="$2:$3"
    intent CROSSVISIT-PARK "$ticket" "$seat" "Blocked" "class=$class visits>=$ORCH_CROSSVISIT_THRESHOLD"
    [ "$MODE" = "live" ] || return 0
    if ! blocker_notified "$ticket" "$key"; then
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "cross-visit loop-breaker: seat '$seat' hit the same '$class' blocker on $ticket for the ${ORCH_CROSSVISIT_THRESHOLD}nd time across visits (from '$status'); parking in Blocked with NO further re-spawn — a deterministic wall retrying cannot clear. Operator action required (ADR-A-0018 §c/§e, ABS-199)."
        mark_blocker_notified "$ticket" "$key"
    fi
    if ! ticket_still_in "$ticket" "Blocked"; then
        tracker transition "$ticket" "Blocked" --actor orchestrator \
            --reason "cross-visit same-blocker loop-breaker: '$seat' recurred on '$class' (${ORCH_CROSSVISIT_THRESHOLD}x across visits); auto-parked, no re-spawn (ADR-A-0018, ABS-199)." \
            >/dev/null 2>&1 || log "cross-visit auto-park transition failed on $ticket"
    fi
    return 0
}

# crossvisit_guard <ticket> <status> <seat> <diag> — record this failure in the
# cross-visit marker and, on the 2nd occurrence of the SAME (environment-denial,
# seat) across ANY visits, auto-park. Returns 0 ONLY when it parked (caller must
# then suppress the per-visit crash path). transient/logic and any DISTINCT
# (class,seat) return 1 → the existing ABS-118/ABS-74 machinery runs unchanged.
crossvisit_guard() {
    local ticket="$1" status="$2" seat="$3" diag="$4" class n
    [ "$ORCH_CROSSVISIT_LOOPBREAKER" = "1" ] || return 1
    class="$(blocker_class "$diag")"
    n="$(record_blocker "$ticket" "$class" "$seat" "$status")"
    [ "$class" = "environment-denial" ] || return 1
    [ "$n" -ge "$ORCH_CROSSVISIT_THRESHOLD" ] || return 1
    crossvisit_autopark "$ticket" "$class" "$seat" "$status"
    return 0
}

# escalation_state <ticket> — echo "<count>\t<highwater-chain-index>" (0/0 when
# no state file yet). count = resting rounds without forward progress; highwater
# = the greatest chain_index the ticket has reached this run.
escalation_state()     { local f; f="$(escalation_file "$1")"; if [ -f "$f" ]; then head -1 "$f"; else printf '0\t0\n'; fi; }
escalation_count()     { escalation_state "$1" | cut -f1; }
escalation_highwater() { escalation_state "$1" | cut -f2; }
escalation_write()     { printf '%s\t%s\n' "$2" "$3" > "$(escalation_file "$1")" 2>/dev/null || true; }

# ABS-311: per-ticket-per-run counter of source-B (self-asserted `progress:`)
# work credits consumed. Distinct from the escalation state file so it survives
# the ratchet reset of the stall counter (source-B budget is a per-run ceiling,
# not a per-episode one — a seat cannot re-earn immunity by bouncing forward once).
escalation_workcredit_file()  { echo "$ORCH_STATE_DIR/escalation-workcredit-$1"; }
escalation_workcredit_count() { local f; f="$(escalation_workcredit_file "$1")"; if [ -f "$f" ]; then head -1 "$f"; else echo 0; fi; }
escalation_workcredit_bump()  { local n; n="$(escalation_workcredit_count "$1")"; printf '%s\n' "$(( ${n:-0} + 1 ))" > "$(escalation_workcredit_file "$1")" 2>/dev/null || true; }

# status_is_terminal <status> — return 0 when the status carries terminal: true
# in statuses.yaml (ABS-301 / ADR-A-0018 §d). A terminal status has no legal
# forward edge; a ticket resting there is done, not stuck. Reads the flag from
# the file, never a hardcoded name list (architect AD-2, ABS-301). Returns 1
# (not terminal) when the file is absent.
status_is_terminal() {
    local sf
    sf="${MOCK_TRACKER_STATUSES:-$ORCH_HARNESS_HOME/profiles/neutral/adapters/statuses.yaml}"
    [ -f "$sf" ] || return 1
    awk -v name="$1" '
        /^  - name: / { cur = substr($0, 11); next }
        cur == name && /^    terminal: true/ { found=1; exit }
        END { exit (found ? 0 : 1) }
    ' "$sf"
}

# escalation_note_progress <ticket> <status> — §d reset rule: a transition whose
# target chain_index STRICTLY exceeds the ticket's high-water mark is real
# forward progress → reset the counter to 0 and clear the blocker marker. A
# bounce (backward / same) or an off-chain target (Blocked / Needs PO Decision /
# entry, chain_index 0) never resets — closing the ABS-181 bounce loop.
# Called both from the seat-handoff path (apply_transition, record_nomove) and
# from runner-mechanical transitions (join_check_epic, epic_join_rest_complete)
# so that epic-pipeline advances reset the counter (ABS-301 ratchet fix).
escalation_note_progress() {
    local ticket="$1" idx hw
    idx="$(chain_index "$2")"
    [ "$idx" -gt 0 ] || return 0
    hw="$(escalation_highwater "$ticket")"
    if [ "$idx" -gt "${hw:-0}" ]; then
        escalation_write "$ticket" 0 "$idx"
        rm -f "$(blocker_file "$ticket")" 2>/dev/null || true
        runlog ESCALATION-RESET "$ticket" - "$2" "forward-progress idx=$idx"
    fi
    return 0
}

# escalation_work_credit <ticket> <status> <handoff> — ABS-311 / ADR-A-0018 §d:
# the work-credit signal on the no-move path. A resting round advanced the STATUS
# by definition of "no-move"; this asks the second question the budget never asked
# — did it advance any VERIFIED WORK? Returns 0 (CREDIT: the caller must NOT count
# the stall) when it did; 1 (no credit: count the stall exactly as before) when it
# did not.
#   Source A (strong, unbounded): handoff carries runner-verified commits: hashes.
#     Cannot be forged — the runner mechanically checked them (ADR-A-0024).
#   Source B (weak, bounded): handoff carries an explicit progress: marker but no
#     commits (the artefact-free round, e.g. a bisect). Self-asserted, so credited
#     at most ORCH_ESCALATION_WORK_BUDGET times per ticket per run; after the
#     ceiling the stall resumes and a seat that only ASSERTS progress is parked.
# Credit PAUSES the counter (withholds the +1); it NEVER resets it to 0 — only a
# forward transition resets (escalation_note_progress, the ABS-301 ratchet).
# ON by default (PILOT-63 AC2): ORCH_ESCALATION_WORK_CREDIT=0 restores the legacy
# "1 always" (every no-move round counts) behaviour.
escalation_work_credit() {
    local ticket="$1" status="$2" handoff="$3" used
    [ "$ORCH_ESCALATION_WORK_CREDIT" = "1" ] || return 1
    if handoff_work_verified "$handoff"; then
        runlog ESCALATION-WORK-CREDIT "$ticket" - "$status" "source=commits verified; stall increment withheld"
        return 0
    fi
    if handoff_progress_marker "$handoff"; then
        used="$(escalation_workcredit_count "$ticket")"
        if [ "${used:-0}" -lt "$ORCH_ESCALATION_WORK_BUDGET" ]; then
            escalation_workcredit_bump "$ticket"
            runlog ESCALATION-WORK-CREDIT "$ticket" - "$status" "source=progress used=$(( ${used:-0} + 1 )) budget=$ORCH_ESCALATION_WORK_BUDGET; stall increment withheld"
            return 0
        fi
        runlog ESCALATION-WORK-CREDIT "$ticket" - "$status" "source=progress EXHAUSTED used=${used:-0} budget=$ORCH_ESCALATION_WORK_BUDGET; stall counted"
    fi
    return 1
}

# escalation_note_stall <ticket> <status> <seat> — §d/§e: a resting round that
# advanced nothing. Bump the per-ticket counter; at ORCH_ESCALATION_BUDGET emit
# one deduped NOTIFY (key "escalation-budget") + park to Blocked, no re-spawn.
# Returns 0 when it parked, 1 otherwise.
escalation_note_stall() {
    local ticket="$1" status="$2" seat="$3" n hw
    [ "$ORCH_ESCALATION_LOOPBREAKER" = "1" ] || return 1
    # Terminal-status exemption (ABS-301 / ADR-A-0018 §d): a status with
    # terminal: true in statuses.yaml has no legal forward edge. A ticket resting
    # there is done, not stuck. Read the flag from the file, not a hardcoded name
    # list (architect AD-2, ABS-301).
    status_is_terminal "$status" && return 1
    n="$(escalation_count "$ticket")"; hw="$(escalation_highwater "$ticket")"
    n=$(( ${n:-0} + 1 ))
    escalation_write "$ticket" "$n" "${hw:-0}"
    [ "$n" -ge "$ORCH_ESCALATION_BUDGET" ] || return 1
    intent ESCALATION-BUDGET "$ticket" "$seat" "Blocked" "rounds=$n budget=$ORCH_ESCALATION_BUDGET"
    [ "$MODE" = "live" ] || return 0
    if ! blocker_notified "$ticket" "escalation-budget"; then
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" "escalation budget exhausted: $ticket made $n rounds with no forward status progress (budget=$ORCH_ESCALATION_BUDGET); parking in Blocked with a single operator NOTIFY and no further seat spawns (ADR-A-0018 §d, ABS-199)."
        mark_blocker_notified "$ticket" "escalation-budget"
    fi
    if ! ticket_still_in "$ticket" "Blocked"; then
        tracker transition "$ticket" "Blocked" --actor orchestrator \
            --reason "escalation budget of $ORCH_ESCALATION_BUDGET rounds without status progress exhausted; auto-parked, no re-spawn (ADR-A-0018 §d, ABS-199)." \
            >/dev/null 2>&1 || log "escalation-budget park transition failed on $ticket"
    fi
    return 0
}

# =============================================================================
# v3 Blocked -> TDM triage, pre-blocked-status persistence (ABS-76, spec §1.3/§3.7)
# =============================================================================
# `Blocked` (from ANY stage, either pipeline) spawns tdm exactly once per
# Blocked ENTRY (comment-keyed guard, same idiom as stall_marker/followup_marker
# above). Before the spawn, the runner records the PRE-BLOCKED status — the
# status the ticket blocked FROM, read off its own transition history — in a
# greppable marker comment; TDM reads that comment rather than recomputing it
# (docs/sop/ORCHESTRATOR_SOP.md "Blocked -> TDM triage"). TDM (or a human) later
# resumes the ticket to that recorded status itself via `tracker transition` —
# the runner does not drive the resume, it only supplies the recorded target.

# blocked_from_marker <pre-blocked-status> — the greppable marker recording the
# status this Blocked entry came from. Doubles as the once-per-entry spawn
# guard key: its mere presence (in an orchestrator gate-results comment) means
# this entry already got its TDM spawn.
blocked_from_marker() { printf 'BLOCKED-FROM=%s (orchestrator)' "$1"; }

# last_transition_into_blocked_from <ticket-dump> — the `from` status of the
# MOST RECENT "<from> -> Blocked" transition-reason comment. Empty if the
# ticket has never transitioned into Blocked (should not happen when called on
# a ticket resting in Blocked, but callers must not assume non-empty).
last_transition_into_blocked_from() {
    printf '%s\n' "$1" | awk '
        /^Transition: / {
            line = $0
            sub(/^Transition: /, "", line)
            p = index(line, " -> Blocked.")
            if (p > 0) last = substr(line, 1, p - 1)
        }
        END { if (last != "") print last }
    '
}

# has_blocked_marker <ticket-dump> — 0 (true) when THIS Blocked entry already
# carries a BLOCKED-FROM marker (i.e. TDM was already spawned for it). Scoped
# to `kind: gate-results` / actor orchestrator blocks, same anchoring as
# has_followup_marker/has_orchestrator_stall_marker so a comment merely
# quoting the marker text cannot disarm the guard. Re-entering Blocked later
# (a fresh "-> Blocked" transition after a resume) posts a NEW marker with the
# ordinal-free "most recent wins" semantics of last_transition_into_blocked_from,
# so a later re-entry is never masked by an earlier, already-resumed one: the
# guard only needs to know whether the CURRENT (latest) entry has a marker
# comment newer than its own "-> Blocked" transition, which the ordering below
# checks directly.
has_blocked_marker() {
    printf '%s\n' "$1" | awk '
        /^### / {
            hdr = $0
            entering_blocked = (hdr ~ /kind: transition-reason/)
            in_orch = (hdr ~ /kind: gate-results/ && hdr ~ /actor: orchestrator/)
            next
        }
        entering_blocked && /^Transition: .* -> Blocked\./ { blocked_at = NR; entering_blocked = 0 }
        in_orch && /BLOCKED-FROM=/ { marker_at = NR }
        END { exit (marker_at > 0 && marker_at > blocked_at ? 0 : 1) }
    '
}

# record_blocked_from <ticket> <from> — post the BLOCKED-FROM marker comment
# (live only; dry-run never persists). Called once, right before the TDM spawn
# for this Blocked entry.
record_blocked_from() {
    local ticket="$1" from="$2"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(blocked_from_marker "$from"): recording pre-blocked status so TDM (or a human) can resume to origin (ABS-76 / spec §1.3, §3.7)." \
        >/dev/null 2>&1 || log "blocked-from marker comment failed on $ticket"
}

# =============================================================================
# ABS-336 / ADR-A-0014 — autonomous integration-conflict forward-fix route
# =============================================================================
# The RTE `Epic Integration` seat aborts (branch untouched) on a sync-rebase
# conflict and blocks the epic for triage (spec §3.5). Rather than ending
# autonomy there, the Blocked triage recognises this specific class and routes a
# forward-fix implementer that MERGES main into the epic branch (never rebases /
# rewrites history), then re-reviews the merged epic via `Architecture Review`
# before the RTE seat repeats the integration. RTE stays abort-only.

# is_integration_conflict <ticket-dump> — 0 (true) when THIS Blocked entry came
# FROM `Epic Integration` on a `sync-rebase conflict`. Derived mechanically from
# the most recent `Transition: <from> -> Blocked.` reason line (same parse point
# as last_transition_into_blocked_from), never from free prose — both the origin
# station and the conflict phrase must be present.
is_integration_conflict() {
    local last_line
    last_line="$(printf '%s\n' "$1" | awk '
        /^Transition: / && / -> Blocked\./ { last = $0 }
        END { if (last != "") print last }
    ')"
    [ -n "$last_line" ] || return 1
    case "$last_line" in
        "Transition: Epic Integration -> Blocked."*) ;;
        *) return 1 ;;
    esac
    case "$last_line" in
        *"sync-rebase conflict"*) return 0 ;;
        *) return 1 ;;
    esac
}

# failing_commit_ticket <ticket-dump> — the ticket id named in the RTE gate
# comment's `Failing commit: <sha> ... [ABS-nnn]` line (most recent wins). Empty
# when no such line/token exists. The `[<PREFIX>-<n>]` token is matched whole so
# a sha or a prose reference cannot masquerade as the ticket.
failing_commit_ticket() {
    printf '%s\n' "$1" | awk '
        /Failing commit:/ {
            line = $0; tok = ""
            while (match(line, /\[[A-Za-z][A-Za-z0-9]*-[0-9]+\]/)) {
                tok = substr(line, RSTART + 1, RLENGTH - 2)
                line = substr(line, RSTART + RLENGTH)
            }
            if (tok != "") last = tok
        }
        END { if (last != "") print last }
    '
}

# failing_commit_role <ticket-dump> — the implementer role that OWNS the failing
# commit: the `role:` frontmatter of the ticket the RTE gate comment names.
# Fail-safe default be-developer when the ticket is absent/unreadable or carries
# no role (mirrors resolve_implementer_role's ORCH_DEFAULT_ROLE fallback).
failing_commit_role() {
    local fc fcdump role=""
    fc="$(failing_commit_ticket "$1")"
    if [ -n "$fc" ]; then
        fcdump="$(tracker get "$fc" 2>/dev/null || true)"
        role="$(fm_field "$fcdump" role)"
    fi
    [ -n "$role" ] || role="${ORCH_DEFAULT_ROLE:-be-developer}"
    printf '%s' "$role"
}

# integration_conflict_note_body — the forward-fix packet-note. Posted as an
# orchestrator gate-results comment (so it rides into the seat's packet via the
# ticket dump, same idiom as the BLOCKED-FROM marker). Carries the merge doctrine
# the seat must follow: MERGE (never rebase), Feature-Union, full suite green,
# a commits: line in the handoff.
integration_conflict_note_body() {
    printf '%s' "INTEGRATION-CONFLICT-FORWARDFIX (orchestrator): autonomous sync-rebase-conflict resolution (ABS-336, ADR-A-0014). Do NOT rebase, cherry-pick, reset, or otherwise rewrite history — MERGE origin/main INTO the epic integration branch (a merge commit is expected). Apply the Feature-Union doctrine: keep BOTH sides' features when resolving each hunk; never drop a sibling story's work to clear a conflict. Run the FULL test suite and hand off only once it is green. Your handoff MUST include a commits: line naming the merge commit(s). On a successful handoff the runner routes the epic to Architecture Review (re-review), NOT back to Epic Integration; the RTE seat then repeats the integration."
}

# record_integration_conflict_note <ticket> <role> — post the forward-fix packet
# note (live only; dry-run never persists). Once per Blocked entry, alongside the
# BLOCKED-FROM marker written by record_blocked_from.
record_integration_conflict_note() {
    local ticket="$1" role="$2"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(integration_conflict_note_body) Forward-fix role: $role (from the failing commit's ticket)." \
        >/dev/null 2>&1 || log "integration-conflict note comment failed on $ticket"
}

# =============================================================================
# ABS-296 Blocked auto-release: dependency-caused Blocked entries return to
# their pre-blocked origin once all depends_on are Done.
# =============================================================================
# PILOT-37 migration note: the NEW path no longer PRODUCES dependency-caused
# Blocked entries — depends_unmet() now holds a dependency-waiting ticket in its
# resting status (Backlog/RfD/Design), never moving it to Blocked (a human-
# attention status). This sweep is retained for LEGACY entries: tickets a seat or
# a human already parked in Blocked citing a dependency, plus any produced by an
# older runner. Once such legacy entries drain it becomes a no-op, but it stays
# on so a mid-upgrade board self-heals.
# Controlled by ORCH_BLOCKED_AUTO_RELEASE (default 1; 0 = no auto-release =
# today's behaviour). A release fires ONLY when ALL of the following hold:
#   1. The ticket has depends_on entries (non-dependency Blocked = skip).
#   2. The ticket's transition history records a pre-Blocked from-status
#      (last_transition_into_blocked_from); fail-closed when absent.
#   3. The origin is a known active status, not Backlog/Blocked/terminal.
#   4. All depends_on are now Done (same parent-cross-epic logic as depends_unmet).
#   5. No BLOCKED-AUTO-RELEASED marker already posted for THIS Blocked entry.
# Reuses the existing ORCH_DEPENDS_GATING knob: when gating is off, auto-
# release is also skipped (both read the same dep evaluation logic).

# blocked_release_fact_fingerprint <deps-space-separated> — a stable, greppable
# fingerprint of the release CAUSE: each dependency's CURRENT status, sorted so it
# is order-independent. This is the "Faktenstand" of AC1/AC2 (PILOT-72): it is
# identical across a Re-Block that leaves the dependency facts untouched (the exact
# churn case — a dep with no commits and an unchanged status), and it CHANGES the
# moment a dependency's status moves (the "nachweisbare Aenderung" that re-enables
# a release). Spaces are folded to '_' so the value embeds cleanly in a one-line
# marker and greps as a whole token.
blocked_release_fact_fingerprint() {
    local deps="$1" dep st out=""
    for dep in $deps; do
        st="$(ticket_status "$dep")"   # reuse the canonical front-matter status reader
        out="$out${dep}=${st:-UNKNOWN};"
    done
    printf '%s\n' "$out" | tr ' ' '_' | tr ';' '\n' | grep -v '^$' | LC_ALL=C sort | paste -sd, -
}

# blocked_auto_release_marker <origin> <fingerprint> — greppable marker for the
# auto-release event. The trailing `fact=[...]` token is the cause-keyed
# idempotency key (PILOT-72 AC1): a release already fired for this ticket at this
# exact dependency fact state. The leading `BLOCKED-AUTO-RELEASED=<origin>
# (orchestrator)` shape is preserved so the ABS-296 audit grep keeps matching.
blocked_auto_release_marker() { printf 'BLOCKED-AUTO-RELEASED=%s (orchestrator) fact=[%s]' "$1" "$2"; }

# has_blocked_auto_release_marker <ticket-dump> <fingerprint> — 0 (true) when a
# release already fired for THIS fact state. PILOT-72: the key hangs on the CAUSE
# (which dependency facts were evaluated), NOT on the Blocked entry, so a Re-Block
# — which starts a fresh Blocked entry — does NOT reset it. The release re-fires
# only after a dependency fact actually changes (a new fingerprint).
has_blocked_auto_release_marker() {
    printf '%s\n' "$1" | grep -qF "fact=[$2]"
}

# blocked_auto_release_count <ticket-dump> — number of release episodes recorded
# for the ticket so far (PILOT-72 AC3 churn counter). Each BLOCKED-AUTO-RELEASED
# marker is one release/re-block cycle.
blocked_auto_release_count() {
    printf '%s\n' "$1" | grep -cF "BLOCKED-AUTO-RELEASED="
}

# blocked_reason_names_dep <ticket-dump> <dep-ids-space-separated>
# Returns 0 (true) when the most recent "-> Blocked" Transition line names at
# least one of the dep ids.  Fail-closed: returns 1 when no such line exists or
# no dep id appears in the reason text.
#
# This is the AD-1 / ADR-A-0004 gate: loop-breaker parks (crossvisit_autopark,
# escalation_note_stall) and TDM/human parks never carry a dep id in their
# transition reason, so they are excluded automatically.  A dependency-caused
# entry (written by a seat handoff or a human citing the dep) names the id.
blocked_reason_names_dep() {
    local dump="$1" deps="$2"
    # Find the most recent "Transition: ... -> Blocked." line (same parse point
    # as last_transition_into_blocked_from, just returns the full line).
    local last_line
    last_line="$(printf '%s\n' "$dump" | awk '
        /^Transition: / && / -> Blocked\./ { last = $0 }
        END { if (last != "") print last }
    ')"
    [ -n "$last_line" ] || return 1
    # Whole-token match: normalise every character that cannot appear in a ticket
    # id (alphanumeric or hyphen) to a space, then wrap with sentinel spaces.
    # "PROJ-4" no longer matches inside "PROJ-42", and "ABS-199" in a loop-breaker
    # reason no longer satisfies deps ABS-1, ABS-19, or ABS-199 (each is a distinct
    # whole token after normalisation).
    local dep norm
    norm=" ${last_line//[^[:alnum:]-]/ } "
    for dep in $deps; do
        case "$norm" in
            *" $dep "*) return 0 ;;
        esac
    done
    return 1
}

# blocked_auto_release_sweep — one sweep pass: find Blocked tickets whose
# depends_on are all Done and release them back to their BLOCKED-FROM origin.
# Called from reconcile(), before the per-ticket dispatch loop, so a just-
# released ticket is already moving before this cycle's dispatch re-derives it.
blocked_auto_release_sweep() {
    [ "$ORCH_BLOCKED_AUTO_RELEASE" = "1" ] || return 0
    [ "$ORCH_DEPENDS_GATING" = "1" ] || return 0
    local id type status _title
    while IFS="$(printf '\t')" read -r id type status _title; do
        [ -n "$id" ] || continue
        [ "$status" = "Blocked" ] || continue

        local dump
        dump="$(tracker get "$id" 2>/dev/null || true)"
        [ -n "$dump" ] || continue

        # Only dependency-caused Blocked entries: ticket must have depends_on.
        local deps
        deps="$(printf '%s\n' "$dump" | sed -n 's/^depends_on: \[\(.*\)\]/\1/p' | head -1 | tr -d ' ' | tr ',' ' ')"
        [ -n "$deps" ] || continue

        # AD-1 / ADR-A-0004 gate: the most recent -> Blocked transition reason
        # must name at least one of the ticket's depends_on ids.  Fail-closed
        # when it names none.  Loop-breaker parks (crossvisit_autopark,
        # escalation_note_stall) and TDM/human parks never carry a dep id in
        # their reason text; they are excluded here and must remain Blocked until
        # a human or TDM releases them (ADR-A-0018 "no re-spawn, operator action
        # required").
        blocked_reason_names_dep "$dump" "$deps" || continue

        # Fail-closed: no BLOCKED-FROM marker -> can't determine origin; skip.
        local origin
        origin="$(last_transition_into_blocked_from "$dump")"
        [ -n "$origin" ] || continue
        # Origin sanity: must be a known active status, not a terminal or entry
        # that makes no sense as a resume target for a released dependency block.
        # Note: Backlog is excluded deliberately — a released dep should not land
        # in Backlog even though statuses.yaml lists Blocked.next includes it.
        case "$origin" in
            ""|"Backlog"|"Blocked"|"Needs PO Decision"|"Done"|"Epic Done") continue ;;
        esac
        is_known_status "$origin" || continue

        # PILOT-72 AC1/AC2 — cause-keyed idempotency. The fact fingerprint is the
        # dependency set + each dep's current status. If a release already fired for
        # THIS exact fact state, a Re-Block (which starts a fresh Blocked entry, and
        # under the old anchoring would have re-armed the release) must NOT re-fire:
        # the fingerprint is unanchored, so it survives the re-block and the loop
        # ends. It re-fires only after a dependency fact changes (a new fingerprint).
        local fp
        fp="$(blocked_release_fact_fingerprint "$deps")"
        has_blocked_auto_release_marker "$dump" "$fp" && continue

        # Re-evaluate via the existing depends_unmet() predicate (same parent/
        # cross-epic logic, same error-as-unmet discipline). Pass "Ready for
        # Development" as the target so depends_unmet's status-filter matches;
        # the actual current status (Blocked) is irrelevant to the dep check.
        # Note: ABS-296 calls depends_unmet out-of-band (not from a RfD/Design
        # dispatch path); "Ready for Development" is used only to satisfy the
        # internal status-class filter inside depends_unmet.
        # depends_unmet returns 0 (true) when ANY dep is unmet — skip release.
        depends_unmet "$id" "Ready for Development" && continue

        # PILOT-72 AC3 — churn cap. The fingerprint gate above already stops the
        # no-change loop; this bounds the residual case where the dependency facts
        # DO keep changing yet the ticket keeps returning to Blocked. After
        # ORCH_BLOCKED_RELEASE_CHURN_CAP release episodes, stop releasing and raise
        # ONE visible Attention-Event (deduped) instead of churning silently.
        local rel_n
        rel_n="$(blocked_auto_release_count "$dump")"
        if [ "${rel_n:-0}" -ge "$ORCH_BLOCKED_RELEASE_CHURN_CAP" ]; then
            runlog BLOCKED-RELEASE-CHURN-CAP "$id" - "$origin" "releases=$rel_n cap=$ORCH_BLOCKED_RELEASE_CHURN_CAP"
            intent BLOCKED-RELEASE-CHURN-CAP "$id" - "$origin" "releases=$rel_n cap=$ORCH_BLOCKED_RELEASE_CHURN_CAP"
            [ "$MODE" = "live" ] || continue
            if ! blocker_notified "$id" "blocked-release-churn"; then
                notify "${ORCH_NOTIFY_TICKET:-$id}" "blocked-auto-release churn cap: $id has been auto-released $rel_n times (cap=$ORCH_BLOCKED_RELEASE_CHURN_CAP) and keeps returning to Blocked; leaving it Blocked with no further auto-release — operator action needed (PILOT-72)."
                mark_blocker_notified "$id" "blocked-release-churn"
            fi
            continue
        fi

        # All dependencies satisfied (merge-fact or Done, PILOT-19) -> release to origin.
        runlog BLOCKED-AUTO-RELEASE "$id" - "$origin" "deps=$deps"
        intent BLOCKED-AUTO-RELEASE "$id" - "$origin" "deps=$deps"

        [ "$MODE" = "live" ] || continue
        # Marker posted AFTER a successful transition: a failed transition (transient
        # adapter error) retries next sweep rather than permanently stranding the ticket.
        if tracker transition "$id" "$origin" --actor orchestrator \
            --reason "blocked-auto-release: all depends_on satisfied — merge-fact or Done ($deps); resuming to origin (ABS-296; PILOT-19)" \
            >/dev/null 2>&1; then
            runlog BLOCKED-AUTO-RELEASE-DONE "$id" - "$origin" "released"
            tracker comment "$id" --kind gate-results --actor orchestrator \
                --body "$(blocked_auto_release_marker "$origin" "$fp"): all depends_on satisfied — merge-fact or Done ($deps); releasing to pre-blocked origin (ABS-296; PILOT-19; fact-keyed idempotency PILOT-72)." \
                >/dev/null 2>&1 || log "blocked-auto-release marker comment failed on $id"
            # ABS-451: the ticket just ARRIVED at its (possibly In Progress)
            # origin — restart its heal rest-clock so it gets a fresh grace
            # window before the In-Progress orphan heal considers it stuck.
            clear_stuck_row "$id"
        else
            log "blocked-auto-release transition $id -> $origin failed"
        fi
    done <<EOF
$(tracker search 2>/dev/null || true)
EOF
}

# =============================================================================
# v3 Follow-up watcher + containment (ABS-75, spec §3.4)
# =============================================================================
# Replaces the v1/v2 paper hand-off ("reviewing agent hands off to the BSA") —
# no agent-to-agent spawn exists (ADR-A-0002). Instead the sweep scans every
# ticket for `kind: follow-up` comments with NO `kind: bsa-decision` reply
# (followup_pending_count, below the JOIN section) and spawns the bsa on that
# ticket, exactly once per unanswered follow-up. The bsa's `kind: bsa-decision`
# reply is what disarms the watcher (create/in-scope/discard, see
# docs/sop/FOLLOW_UP_TICKET_SOP.md) — the watcher itself never decides.
#
# Runs FIRST in reconcile(), before join_check_epic (spec §3.6 quiescence
# ordering): an AC-blocking follow-up filed the same cycle the last story
# finishes must be seen by the watcher before JOIN re-evaluates, or it loses
# the race.
#
# Per-epic budget (spec §3.4, S7/S9): each epic tolerates ORCH_FOLLOWUP_BUDGET
# (default 5) `kind: follow-up` comments across its own ticket + all children.
# The 6th (and any beyond) does NOT spawn the bsa — the epic is raised to
# "Needs PO Decision" instead (mirrors escalate_rework/record_spawn_crash: a
# mechanical cap escalates rather than spawning). Budgets are isolated per
# epic (S9) because the count is scoped to one epic's own tree.

# followup_marker <ordinal> — the greppable per-follow-up spawn marker, keyed
# on the follow-up comment's 1-based ORDINAL position within its ticket (NOT
# the comment timestamp — the mock adapter's second-resolution `at` collides
# when several follow-ups land in the same sweep/second, e.g. a "storm" of 6
# posted back-to-back; ordinal is always unique per ticket). Mirrors
# stall_marker's rule-keyed shape.
followup_marker() { printf 'FOLLOWUP-SPAWN n=%s (orchestrator)' "$1"; }

# followup_budget_marker <epic> — the greppable per-epic budget-overflow
# marker. One epic never re-raises Needs PO Decision on every sweep once the
# overflow has already been flagged (same re-raise-guard shape as ABS-62).
followup_budget_marker() { printf 'FOLLOWUP-BUDGET epic=%s (orchestrator)' "$1"; }

# has_followup_marker <ticket-dump> <ordinal> — 0 (true) when a bsa spawn was
# already recorded for the follow-up comment at 1-based position <ordinal> in
# this ticket. Scoped to `kind: gate-results` / actor orchestrator blocks, same
# anchoring as has_orchestrator_stall_marker (a comment merely quoting the
# marker text must not disarm the guard).
has_followup_marker() {
    printf '%s\n' "$1" | awk -v marker="$(followup_marker "$2")" '
        /^### / {
            hdr = $0
            in_orch = (hdr ~ /kind: gate-results/ && hdr ~ /actor: orchestrator/)
            next
        }
        in_orch && index($0, marker) > 0 { found = 1 }
        END { exit(found ? 0 : 1) }
    '
}

# has_followup_budget_marker <ticket-dump> <epic> — 0 (true) when the budget
# overflow for <epic> was already raised (so a resting/parked epic is not
# re-flagged every sweep).
has_followup_budget_marker() {
    [ "$(followup_budget_marker_count "$1" "$2")" -gt 0 ]
}

# followup_budget_marker_count <ticket-dump> <epic> — how many budget-overflow
# escalations <epic> already carries. Feeds the generation-aware re-raise
# guard (ABS-293): one escalation per budget generation (base + each declared
# FOLLOWUP-BUDGET-RESET), instead of a permanent once-ever latch.
followup_budget_marker_count() {
    printf '%s\n' "$1" | awk -v marker="$(followup_budget_marker "$2")" '
        /^### / {
            hdr = $0
            in_orch = (hdr ~ /kind: decision/ && hdr ~ /actor: orchestrator/)
            next
        }
        in_orch && index($0, marker) > 0 { found++ }
        END { print found + 0 }
    '
}

# followup_stranded_marker <ordinal> — the per-comment stranded-by-budget
# marker (ABS-293). Same per-ordinal keying as followup_marker so the sweep
# marks each stranded follow-up exactly once.
followup_stranded_marker() { printf 'FOLLOWUP-STRANDED n=%s (orchestrator)' "$1"; }

# mark_followup_stranded <ticket> <ordinal> <at> <epic> — make budget-stranding
# VISIBLE on the ticket that carries the follow-up (ABS-293 AC1): without this,
# a follow-up arriving after exhaustion got no bsa, no second escalation
# (re-raise guard) and no trace — only a JOIN deadlock much later. Live only;
# deduped per ordinal.
mark_followup_stranded() {
    local ticket="$1" ordinal="$2" at="$3" epic="$4" dump
    intent FOLLOWUP-STRANDED "$ticket" - - "n=$ordinal epic=$epic budget-exhausted"
    [ "$MODE" = "live" ] || return 0
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    printf '%s\n' "$dump" | grep -qF "$(followup_stranded_marker "$ordinal")" && return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(followup_stranded_marker "$ordinal"): follow-up #$ordinal (posted at $at) gets NO bsa spawn — epic $epic's follow-up budget is exhausted. Recovery: a PO posts the disposition as a 'kind: bsa-decision' comment (lowers the pending count), and/or re-arms the budget with a 'kind: decision' comment on the epic containing [$(followup_budget_reset_marker)] (ABS-293)." \
        >/dev/null 2>&1 || log "followup-stranded marker failed on $ticket"
}

# followup_comment_ordinals <ticket-dump> — one line per `kind: follow-up`
# comment in the ticket: "<ordinal><TAB><at>", 1-based, in document order. The
# ordinal is the stable per-comment key (see followup_marker); <at> is carried
# along only for human-readable marker/log text.
followup_comment_ordinals() {
    printf '%s\n' "$1" | awk '
        /^### / && $0 ~ /kind: follow-up \|/ {
            n = split($0, f, " ")
            at = (n >= 2 ? f[2] : "?")
            print ++seen "\t" at
        }
    '
}

# followup_comment_has_decision <ticket-dump> <ordinal> — 0 (true) when the
# follow-up comment at 1-based position <ordinal> already has a matching
# `kind: bsa-decision` reply anywhere in the ticket (mirrors
# followup_pending_count's fu/bd tally, but resolved to ONE specific follow-up
# so the watcher can guard per-comment rather than only per-ticket).
followup_comment_has_decision() {
    printf '%s\n' "$1" | awk -v target="$2" '
        /^### / {
            kind = ($0 ~ /kind: follow-up \|/) ? "fu" : (($0 ~ /kind: bsa-decision \|/) ? "bd" : "")
            if (kind == "fu") seen_fu++
            if (kind == "bd") answered++
            next
        }
        END {
            # A follow-up is "answered" once at least as many bsa-decision
            # replies exist as follow-ups up to and including this one — same
            # net-count semantics as followup_pending_count, applied at this
            # comment'"'"'s ordinal position in the sequence.
            exit (answered >= target ? 0 : 1)
        }
    '
}

# epic_followup_spawned_count <epic-id> — how many kind:follow-up comments
# across the epic's own ticket + all children ALREADY carry a FOLLOWUP-SPAWN
# marker (i.e. already consumed budget by getting a bsa spawn). This is the
# "budget consumed so far" tally the watcher checks before spawning for a NEW
# unanswered, unmarked follow-up (spec §3.4, S7): 5 tolerated, the 6th
# escalates instead of spawning.
epic_followup_spawned_count() {
    local epic="$1" dump total=0 id ord at
    dump="$(tracker get "$epic" 2>/dev/null || true)"
    while IFS="$(printf '\t')" read -r ord at; do
        [ -n "$ord" ] || continue
        has_followup_marker "$dump" "$ord" && total=$((total + 1))
    done <<EOF
$(followup_comment_ordinals "$dump")
EOF
    local rows
    rows="$(epic_children_rows "$epic")"
    if [ -n "$rows" ]; then
        while IFS= read -r line; do
            id="$(printf '%s' "$line" | awk -F'\t' '{print $1}')"
            [ -n "$id" ] || continue
            dump="$(tracker get "$id" 2>/dev/null || true)"
            while IFS="$(printf '\t')" read -r ord at; do
                [ -n "$ord" ] || continue
                has_followup_marker "$dump" "$ord" && total=$((total + 1))
            done <<INNER
$(followup_comment_ordinals "$dump")
INNER
        done <<EOF
$rows
EOF
    fi
    echo "$total"
}

# followup_budget_state_file — the optional runtime-override file for the
# per-epic follow-up budget (ABS-298). A raise here takes effect on the NEXT
# sweep with NO runner restart (a restart orphans live seats — the 2026-07-13
# cascade this story exists to avoid).
followup_budget_state_file() { echo "$ORCH_STATE_DIR/followup-budget"; }

# reload_followup_budget — re-read the effective per-epic follow-up budget from
# followup_budget_state_file each sweep and publish it into ORCH_FOLLOWUP_BUDGET
# (the single global every downstream reference reads: followup_effective_budget,
# escalate_followup_budget, the JOIN-WAIT text). Only a positive integer in the
# file overrides; an absent file / empty / non-numeric line leaves the env value
# untouched, so today's behaviour is exactly preserved (ABS-298 AC2). Emits one
# greppable FOLLOWUP-BUDGET-RELOAD audit line the first sweep a new value takes
# effect (subsequent sweeps see ORCH_FOLLOWUP_BUDGET already == the file value
# and stay silent — no per-sweep log spam).
reload_followup_budget() {
    local f v
    f="$(followup_budget_state_file)"
    [ -f "$f" ] || return 0
    v="$(head -n1 "$f" 2>/dev/null | tr -dc '0-9')"
    [ -n "$v" ] || return 0
    if [ "$v" != "$ORCH_FOLLOWUP_BUDGET" ]; then
        intent FOLLOWUP-BUDGET-RELOAD - - - "budget=$v (was $ORCH_FOLLOWUP_BUDGET, from $f)"
        ORCH_FOLLOWUP_BUDGET="$v"
    fi
}

# followup_marker_age <ticket-dump> <ordinal> — seconds since the FOLLOWUP-SPAWN
# marker for <ordinal> was posted (most recent, last-wins). Empty output when no
# marker is present or the timestamp is unparseable, so callers fail closed
# (treat as "not yet old enough" → no repair). Same gate-results/orchestrator
# anchoring as has_followup_marker.
followup_marker_age() {
    local dump="$1" ordinal="$2" at ep
    at="$(printf '%s\n' "$dump" | awk -v marker="$(followup_marker "$ordinal")" '
        /^### / {
            n = split($0, f, " ")
            cur = (n >= 2 ? f[2] : "")
            in_orch = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/)
            next
        }
        in_orch && index($0, marker) > 0 { last = cur }
        END { if (last != "") print last }')"
    [ -n "$at" ] || return 0
    ep="$(iso_to_epoch "$at")"
    [ -n "$ep" ] || return 0
    echo $(( $(now_epoch) - ep ))
}

# followup_needs_repair <ticket> <ordinal> <ticket-dump> — 0 (true) when a
# FOLLOWUP-SPAWN marker for <ordinal> should be REPAIRED by re-spawning the bsa
# (ABS-298 part b). The caller has already established that the marker exists AND
# no matching kind:bsa-decision reply exists (the re-raise guard). This function
# adds the two remaining gates, mirroring check_crash_repair's shape:
#   - ORCH_FOLLOWUP_REPAIR_SECONDS > 0 (0 = off = today's dedupe-forever).
#   - No LIVE seat lock holds the ticket (a still-live bsa may yet post its
#     decision; stale lock, age >= ORCH_LOCK_TTL, does not block — dead seat).
#   - Marker older than the repair threshold (a bsa spawned THIS sweep is given
#     time to post its decision before we conclude it died).
followup_needs_repair() {
    local ticket="$1" ordinal="$2" dump="$3" age
    [ "${ORCH_FOLLOWUP_REPAIR_SECONDS:-300}" -gt 0 ] || return 1
    if [ -d "$(lock_dir_for "$ticket")" ]; then
        local lage
        lage="$(lock_age_for "$ticket" 2>/dev/null || echo 0)"
        [ "$lage" -ge "$ORCH_LOCK_TTL" ] || return 1
    fi
    age="$(followup_marker_age "$dump" "$ordinal")"
    [ -n "$age" ] || return 1
    [ "$age" -ge "${ORCH_FOLLOWUP_REPAIR_SECONDS:-300}" ] || return 1
    return 0
}

# followup_watcher — the ABS-75 sweep pass. Scans every ticket returned by
# `tracker search`, spawns bsa once per unanswered follow-up (comment-keyed
# idempotency guard, the ABS-62 stall-marker pattern), and enforces the
# per-epic budget by escalating instead of spawning past ORCH_FOLLOWUP_BUDGET.
# The per-epic "consumed" count starts from the markers already on disk and is
# bumped in-memory as this pass spawns more, so a storm of N follow-ups
# arriving in one sweep is capped correctly (first ORCH_FOLLOWUP_BUDGET spawn,
# the rest escalate) rather than comparing a static snapshot against every one.
followup_watcher() {
    # ABS-298 part (a): re-read the effective per-epic budget from the optional
    # state file BEFORE this sweep evaluates any epic, so an operator's mid-run
    # raise reaches followup_effective_budget/escalate_followup_budget/JOIN in
    # THIS cycle — no runner restart. Absent the file, ORCH_FOLLOWUP_BUDGET is
    # left exactly as configured.
    reload_followup_budget
    local id type status _title
    while IFS="$(printf '\t')" read -r id type status _title; do
        [ -n "$id" ] || continue
        local dump pending
        dump="$(tracker get "$id" 2>/dev/null || true)"
        [ -n "$dump" ] || continue
        pending="$(followup_pending_count "$dump")"
        [ "$pending" -gt 0 ] || continue

        # The epic that owns the budget: this ticket if it IS the epic,
        # otherwise its parent (a story's follow-up counts against its epic).
        local epic
        if [ "$type" = "epic" ]; then
            epic="$id"
        else
            epic="$(fm_field "$dump" parent)"
        fi
        [ -n "$epic" ] || epic="$id"   # orphaned ticket: budget scoped to itself

        local consumed=""
        local ord at
        while IFS="$(printf '\t')" read -r ord at; do
            [ -n "$ord" ] || continue
            # Re-fetch this ticket's dump each iteration: a spawn above may
            # have just added a FOLLOWUP-SPAWN marker to it.
            dump="$(tracker get "$id" 2>/dev/null || true)"
            followup_comment_has_decision "$dump" "$ord" && continue

            # Re-raise guard: this exact follow-up comment already spawned bsa,
            # so the sweep normally never re-spawns it (idempotency anchor).
            # ABS-298 part (b) repair exception: if that bsa died BEFORE posting
            # its kind:bsa-decision (no decision exists — checked immediately
            # above), no LIVE seat lock holds the ticket, and the marker is older
            # than ORCH_FOLLOWUP_REPAIR_SECONDS, re-spawn the bsa for THIS ordinal
            # instead of de-duping it away forever while the JOIN waits. The
            # re-spawn routes through the same spawn_dispatch gates (lock →
            # concurrency → crash/respawn limits), so a repair that keeps dying is
            # bounded by ORCH_CRASH_LIMIT / ORCH_RESPAWN_LIMIT — never a loop. No
            # fresh budget is consumed: the ordinal's slot was already spent when
            # it first spawned (its marker is still on the ticket).
            if has_followup_marker "$dump" "$ord"; then
                if followup_needs_repair "$id" "$ord" "$dump"; then
                    intent FOLLOWUP-REPAIR "$id" bsa "$status" "n=$ord marker-without-decision re-spawn"
                    spawn_followup_bsa "$id" "$ord" "$at" "$status" || true
                fi
                continue
            fi

            if [ -z "$consumed" ]; then
                consumed="$(epic_followup_spawned_count "$epic")"
            fi
            # ABS-293: the budget is the EFFECTIVE one (base + declared
            # FOLLOWUP-BUDGET-RESET re-arms), so a PO disposition can re-open
            # the pipeline after exhaustion without an env change mid-run.
            if [ "$consumed" -ge "$(followup_effective_budget "$epic")" ]; then
                local epic_dump
                epic_dump="$(tracker get "$epic" 2>/dev/null || true)"
                # Re-raise guard, generation-aware (ABS-293): one escalation
                # per budget generation — a re-armed budget that exhausts AGAIN
                # escalates once more instead of never (the old guard was
                # permanent, so every later follow-up stranded in silence).
                if [ "$(followup_budget_marker_count "$epic_dump" "$epic")" -le "$(followup_budget_reset_count "$epic")" ]; then
                    escalate_followup_budget "$epic"
                fi
                # No silent stranding (ABS-293): mark THIS follow-up as
                # stranded-by-budget on its ticket, once per ordinal, so the
                # state is visible where a PO looks — the re-raise guard must
                # not confuse visibility with repetition.
                mark_followup_stranded "$id" "$ord" "$at" "$epic"
                continue
            fi

            local spawn_rc=0
            spawn_followup_bsa "$id" "$ord" "$at" "$status" || spawn_rc=$?
            # Only a REAL spawn (rc 0) consumes budget; a concurrency-cap
            # defer (rc 3) leaves this follow-up for the next sweep untouched.
            [ "$spawn_rc" -eq 0 ] && consumed=$((consumed + 1))
        done <<EOF
$(followup_comment_ordinals "$dump")
EOF
    done <<EOF
$(tracker search 2>/dev/null || true)
EOF
}

# spawn_followup_bsa <ticket> <ordinal> <at> <status> — realize one watcher
# spawn: log the intent, route through the SAME safety-gated path as a
# status-driven dispatch (spawn_dispatch: kill-switch -> budget -> lock ->
# concurrency -> live_spawn), then (live only) record the per-comment marker
# (keyed on <ordinal>) so the sweep never re-spawns for this follow-up again.
# Returns spawn_dispatch's own rc: 3 = deferred by the concurrency cap (§5.1),
# in which case NO marker is posted and NO budget is consumed — the sweep
# retries this same follow-up next cycle exactly like any other deferred spawn.
spawn_followup_bsa() {
    local ticket="$1" ordinal="$2" at="$3" status="$4"
    if [ "$MODE" != "live" ]; then
        intent SPAWN "$ticket" bsa "$status" "follow-up-watcher n=$ordinal at=$at"
        return 0
    fi
    # spawn_dispatch logs its own INTENT SPAWN (and any safety-gate intent
    # that preempts it, e.g. SKIP-BUDGET/SKIP-LOCKED) — do not double-log here.
    local rc=0
    spawn_dispatch "$ticket" "$status" bsa SPAWN "follow-up-watcher n=$ordinal at=$at" || rc=$?
    if [ "$rc" -eq 3 ]; then
        pending_add "$ticket" "$status"
        return 3
    fi
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "$(followup_marker "$ordinal"): spawned bsa to decide the follow-up (#$ordinal, posted at $at) (ABS-75, spec §3.4)." \
        >/dev/null 2>&1 || log "followup-watcher marker comment failed on $ticket"
    return 0
}

# escalate_followup_budget <epic> — realize the budget overflow (spec §3.4,
# S7): the epic is raised to "Needs PO Decision" instead of spawning the bsa
# on the (budget+1)th follow-up, with a re-raise guard so the sweep does not
# re-flag an epic already parked on this decision.
escalate_followup_budget() {
    local epic="$1"
    intent FOLLOWUP-BUDGET "$epic" - "Needs PO Decision" "budget=$ORCH_FOLLOWUP_BUDGET"
    [ "$MODE" = "live" ] || return 0
    tracker comment "$epic" --kind decision --actor orchestrator \
        --body "Follow-up budget reached: more than $ORCH_FOLLOWUP_BUDGET kind:follow-up comments on this epic. Escalating to Needs PO Decision instead of another bsa spawn (ABS-75, spec §3.4, [$(followup_budget_marker "$epic")])." \
        >/dev/null 2>&1 || log "followup-budget comment failed on $epic"
    if ticket_still_in "$epic" "Needs PO Decision"; then
        return 0
    fi
    tracker transition "$epic" "Needs PO Decision" --actor orchestrator \
        --reason "follow-up budget of $ORCH_FOLLOWUP_BUDGET exceeded (ABS-75)" \
        >/dev/null 2>&1 || log "followup-budget transition failed on $epic"
}

# =============================================================================
# v3 JOIN rule — fan-in "all stories done" (ABS-73, spec §3.1 + §3.6 guards)
# =============================================================================
# Mechanical, bash-only (ADR-A-0009): an epic resting in "Stories In Flight"
# advances to "Epic Integration" when ALL its children (original stories plus
# AC-blocking follow-up additions — both are adapter children) are Done.
# Guards:
#   - quiescence: never JOIN while the epic tree carries an unprocessed
#     follow-up comment (a kind: follow-up without a kind: bsa-decision reply);
#     the watcher (ABS-75) runs BEFORE the JOIN re-check in the same sweep.
#   - empty-epic: zero children at evaluation -> Needs PO Decision, never a
#     vacuous ready-to-test.
# Fires from two places: the reconciliation sweep (per epic row) and a child's
# Done event (dispatch), so the last story completing advances the epic without
# waiting a full reconcile cadence. Idempotent: once the epic left "Stories In
# Flight" the re-read guard makes every further call a no-op.

# followup_pending_count <ticket-dump> — unanswered follow-up comments in ONE
# ticket: count(kind: follow-up) - count(kind: bsa-decision), floored at 0.
followup_pending_count() {
    printf '%s\n' "$1" | awk '
        /^### / {
            if ($0 ~ /kind: follow-up \|/) fu++
            else if ($0 ~ /kind: bsa-decision \|/) bd++
        }
        END { n = fu - bd; print (n > 0 ? n : 0) }'
}

# epic_children_rows <epic-id> — the adapter children rows (id<TAB>[status]<TAB>title).
epic_children_rows() {
    tracker children "$1" 2>/dev/null || true
}

# epic_has_unprocessed_followups <epic-id> — 0 (true) when the epic or any
# child carries an unanswered follow-up comment (quiescence guard input; the
# ABS-75 watcher consumes the same marker).
epic_has_unprocessed_followups() {
    local epic="$1" dump id
    dump="$(tracker get "$epic" 2>/dev/null || true)"
    [ "$(followup_pending_count "$dump")" -gt 0 ] && return 0
    local rows
    rows="$(epic_children_rows "$epic")"
    [ -n "$rows" ] || return 1
    while IFS= read -r line; do
        id="$(printf '%s' "$line" | awk -F'\t' '{print $1}')"
        [ -n "$id" ] || continue
        dump="$(tracker get "$id" 2>/dev/null || true)"
        [ "$(followup_pending_count "$dump")" -gt 0 ] && return 0
    done <<EOF
$rows
EOF
    return 1
}

# followup_budget_reset_marker — the declared budget-re-arm token (ABS-293).
# A PO/human triage act, never invented by the runner: the token MUST appear
# in the BODY of a `kind: decision` comment on the EPIC (same anchoring as
# JOIN-EXEMPT — a mere quote elsewhere cannot re-arm the budget). Each reset
# grants the epic one further full ORCH_FOLLOWUP_BUDGET, so a PO who has
# cleared the backlog of dispositions can re-open the pipeline without the
# operator touching env vars mid-run.
followup_budget_reset_marker() { printf 'FOLLOWUP-BUDGET-RESET (triage)'; }

# followup_budget_reset_count <epic> — how many declared budget re-arms the
# epic carries (0 when none).
followup_budget_reset_count() {
    local dump
    dump="$(tracker get "$1" 2>/dev/null || true)"
    printf '%s\n' "$dump" | awk -v marker="$(followup_budget_reset_marker)" '
        /^### / { in_decision = ($0 ~ /kind: decision/); next }
        in_decision && index($0, marker) { found++ }
        END { print found + 0 }'
}

# followup_effective_budget <epic> — ORCH_FOLLOWUP_BUDGET plus one further full
# budget per declared FOLLOWUP-BUDGET-RESET (ABS-293).
followup_effective_budget() {
    local resets
    resets="$(followup_budget_reset_count "$1")"
    echo $(( ORCH_FOLLOWUP_BUDGET * (1 + ${resets:-0}) ))
}

# followup_budget_exhausted <epic> — 0 (true) when this epic has already consumed
# its EFFECTIVE budget (base ORCH_FOLLOWUP_BUDGET + declared re-arms, ABS-293),
# i.e. the watcher will spawn no more bsa for its follow-ups (ABS-199 /
# ADR-A-0018 §d).
followup_budget_exhausted() {
    local spent; spent="$(epic_followup_spawned_count "$1")"
    [ "${spent:-0}" -ge "$(followup_effective_budget "$1")" ]
}

# join_budget_deadlock <epic> — the §e naming one-shot escalation for a JOIN
# stalled by an EXHAUSTED follow-up budget. Emits exactly one operator NOTIFY
# naming the epic, gate, and budget, deduped by a JOIN-BUDGET-DEADLOCK marker
# comment so the sweep never re-notifies. Replaces the silent >1h wait (ABS-164).
join_budget_deadlock() {
    local epic="$1" dump
    [ "$MODE" = "live" ] || return 0
    dump="$(tracker get "$epic" 2>/dev/null || true)"
    printf '%s\n' "$dump" | grep -qF "JOIN-BUDGET-DEADLOCK (orchestrator)" && return 0
    tracker comment "$epic" --kind gate-results --actor orchestrator \
        --body "JOIN-BUDGET-DEADLOCK (orchestrator): the JOIN gate for epic $epic is blocked by unprocessed follow-ups the exhausted follow-up budget ($ORCH_FOLLOWUP_BUDGET) will never process — a silent dead-end. Emitting one naming operator NOTIFY instead of waiting (ADR-A-0018 §d/§e, ABS-199)." \
        >/dev/null 2>&1 || log "join budget-deadlock marker failed on $epic"
    notify "${ORCH_NOTIFY_TICKET:-$epic}" "budget dead-end: epic $epic cannot JOIN — its follow-up budget ($ORCH_FOLLOWUP_BUDGET) is exhausted yet unprocessed follow-ups still block the gate. Operator action required; the runner will not wait silently (ADR-A-0018 §d/§e, ABS-199)."
}

# join_exempt_marker — the deliberate JOIN exemption token a TDM/PO triage
# declares on a purposely-parked optional/external-dependency child (ABS-210).
# It is an ADR-A-0019-style *declared* marker: the exemption is a human/agent
# triage act, never invented by the runner. The token MUST appear in the BODY
# of a `kind: decision` comment on the CHILD (same body-of-a-decision anchoring
# as the stall-raise marker), so a mere quote in some other comment cannot
# silently exempt a child. Scope note (ABS-210): this changes ONLY the JOIN
# evaluation — it does not alter Blocked/TDM-triage semantics (ABS-76).
join_exempt_marker() { printf 'JOIN-EXEMPT (triage)'; }

# child_join_exempt <child-id> — 0 (true) when the child carries a declared
# JOIN exemption marker (join_exempt_marker) in the body of a `kind: decision`
# comment. Lets the JOIN gate exclude a deliberately-parked optional/external
# child from the pending set so it can never hold the epic SILENTLY in Stories
# In Flight (the ABS-181/ABS-189 dead-end). No marker -> the child is a genuine
# blocker and keeps holding the gate (AC2).
child_join_exempt() {
    local dump
    dump="$(tracker get "$1" 2>/dev/null || true)"
    printf '%s\n' "$dump" | awk -v marker="$(join_exempt_marker)" '
        /^### / { in_decision = ($0 ~ /kind: decision/); next }
        in_decision && index($0, marker) { found = 1 }
        END { exit (found ? 0 : 1) }'
}

# join_check_epic <epic-id> — evaluate the JOIN rule for one epic.
# epic_branch_names <epic> — ABS-316 + ABS-597. The DISTINCT epic integration
# branch names for an epic ON THE ACTIVE PUSH REMOTE, one per line. AC1: only
# branches on the active push remote count — a LOCAL ref is a work trace, not a
# split of the epic (Pilot 8: a tech-writer left a local-only
# epic/PILOT-71-...-tw-docs-4568 that fully lived inside the real remote epic
# branch; counting it froze a finished epic 2 h in Needs PO Decision). The
# active remote is resolved through the pin (active_remote_name / ADR-A-0030),
# never a hardcoded origin. The tracking refs are refreshed best-effort first so
# a stale local mirror neither hides nor invents a remote branch. A branch
# mirrored under the base name counts once. Best-effort: absent git or no
# matching refs -> empty (the guard then no-ops).
epic_branch_names() {
    local epic="$1" remote repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    command -v git >/dev/null 2>&1 || return 0
    remote="$(active_remote_name)"; [ -n "$remote" ] || remote="origin"
    _bounded_git "${ORCH_REMOTE_PROBE_TIMEOUT:-12}" "$repo" fetch -q "$remote" \
        "refs/heads/epic/$epic-*:refs/remotes/$remote/epic/$epic-*" >/dev/null 2>&1 || true
    git -C "$repo" for-each-ref --format='%(refname:short)' \
        "refs/remotes/$remote/epic/$epic-*" 2>/dev/null \
        | sed "s#^$remote/##" | LC_ALL=C sort -u
}

# epic_branch_split_class <epic> — ABS-597. Classify the epic's integration
# branches ON THE ACTIVE PUSH REMOTE (epic_branch_names; local refs never count)
# by CONTENT, so a stale pointer is not mistaken for a split. Prints exactly one
# tab-separated verdict:
#   SINGLE                            0 or 1 branch -> no split, JOIN proceeds.
#   ANCESTRY<TAB>winner<TAB>names     >1 branch but one CONTAINS every other (AC2:
#                                     a stale pointer, not a divergence) -> the
#                                     descendant `winner` wins; caller auto-
#                                     resolves + logs instead of escalating.
#   SPLIT<TAB>names<TAB>detail        >1 branch with commits diverging on both
#                                     sides (AC3) -> a real split; `detail` names
#                                     the diverging commits per branch (short
#                                     SHAs beyond their common merge-base), not
#                                     just branch names. `names` is the CSV set.
# git ancestry ops use the remote-prefixed tracking ref. Best-effort: absent git
# -> SINGLE (guard no-ops).
epic_branch_split_class() {
    local epic="$1" remote repo="${ORCH_STATE_ROOT:-$REPO_ROOT}"
    command -v git >/dev/null 2>&1 || { printf 'SINGLE\n'; return 0; }
    remote="$(active_remote_name)"; [ -n "$remote" ] || remote="origin"
    local names count
    names="$(epic_branch_names "$epic")"
    count="$(printf '%s\n' "$names" | grep -c . || true)"
    [ "$count" -gt 1 ] 2>/dev/null || { printf 'SINGLE\n'; return 0; }

    local csv cand other winner="" contains_all
    csv="$(printf '%s' "$names" | tr '\n' ',' | sed 's/,$//')"
    # AC2: does one candidate contain EVERY other (equal counts as contained)?
    # Then the others are stale pointers into it — resolve to that descendant.
    while IFS= read -r cand; do
        [ -n "$cand" ] || continue
        contains_all=1
        while IFS= read -r other; do
            [ -n "$other" ] || continue
            [ "$other" = "$cand" ] && continue
            if ! git -C "$repo" merge-base --is-ancestor "$remote/$other" "$remote/$cand" 2>/dev/null; then
                contains_all=0; break
            fi
        done <<EOF
$names
EOF
        if [ "$contains_all" = "1" ]; then winner="$cand"; break; fi
    done <<EOF
$names
EOF
    if [ -n "$winner" ]; then
        printf 'ANCESTRY\t%s\t%s\n' "$winner" "$csv"
        return 0
    fi

    # AC3: genuine divergence — name the diverging commits per branch (commits
    # each branch carries beyond the common merge-base), not just the names.
    local refs="" base detail=""
    while IFS= read -r cand; do
        [ -n "$cand" ] && refs="$refs $remote/$cand"
    done <<EOF
$names
EOF
    # shellcheck disable=SC2086
    base="$(git -C "$repo" merge-base $refs 2>/dev/null || true)"
    while IFS= read -r cand; do
        [ -n "$cand" ] || continue
        local uniq=""
        [ -n "$base" ] && uniq="$(git -C "$repo" log --format='%h' "$base..$remote/$cand" 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
        detail="$detail ${cand}[$uniq]"
    done <<EOF
$names
EOF
    printf 'SPLIT\t%s\t%s\n' "$csv" "${detail# }"
}

join_check_epic() {
    local epic="$1"
    # Re-read guard: only epics resting in "Stories In Flight" are candidates.
    ticket_still_in "$epic" "Stories In Flight" || return 0

    # Quiescence guard (§3.6): an unprocessed follow-up may still become an
    # AC-blocking child — JOIN must lose that race on purpose.
    if epic_has_unprocessed_followups "$epic"; then
        # ABS-199 / ADR-A-0018 §d/§e: once the follow-up budget is exhausted the
        # watcher will spawn no more bsa, so those follow-ups will NEVER be
        # processed and JOIN would WAIT forever — the silent >1h dead-end ABS-164
        # hit. Name the budget state in the WAIT intent and escalate exactly once
        # (deduped) instead of waiting silently.
        if followup_budget_exhausted "$epic"; then
            intent JOIN-WAIT "$epic" - "Stories In Flight" "followup-budget-exhausted budget=$ORCH_FOLLOWUP_BUDGET"
            join_budget_deadlock "$epic"
            return 0
        fi
        intent JOIN-WAIT "$epic" - "Stories In Flight" "unprocessed-followups"
        return 0
    fi

    local rows
    rows="$(epic_children_rows "$epic")"

    # Empty-epic guard (§3.6): zero children -> Needs PO Decision, never a
    # vacuous integration + ready-to-test NOTIFY.
    if [ -z "$rows" ]; then
        intent JOIN-EMPTY "$epic" - "Needs PO Decision"
        if [ "$MODE" = "live" ]; then
            tracker comment "$epic" --kind decision --actor orchestrator \
                --body "JOIN empty-epic guard: epic is in Stories In Flight with zero children; escalating instead of integrating nothing (ABS-73, spec §3.6)." \
                >/dev/null 2>&1 || log "join empty-epic comment failed on $epic"
            tracker transition "$epic" "Needs PO Decision" --actor orchestrator \
                --reason "empty epic at JOIN evaluation (ABS-73)" \
                >/dev/null 2>&1 || log "join empty-epic transition failed on $epic"
        fi
        return 0
    fi

    # All children Done? — with the ABS-210 JOIN exemption. Partition the
    # not-Done children into genuine blockers (pending) and deliberately-parked
    # ones that carry a declared JOIN-EXEMPT triage marker (exempt).
    local id status pending="" exempt=""
    while IFS=$'\t' read -r id status _; do
        [ -n "$id" ] || continue
        [ "$status" = "[Done]" ] && continue
        if child_join_exempt "$id"; then
            exempt="$exempt $id"
        else
            pending="$pending $id"
        fi
    done <<EOF
$rows
EOF

    # AC2: any not-Done child WITHOUT an exemption is a real blocker — JOIN keeps
    # waiting (no silent skipping) but NAMES the still-pending child(ren) once
    # instead of hanging silently in Stories In Flight.
    if [ -n "$pending" ]; then
        intent JOIN-WAIT "$epic" - "Stories In Flight" "pending-children:${pending# }"
        return 0
    fi

    # ABS-316 + ABS-597: fail fast on a DIVERGENT epic-integration branch. All
    # children are Done and JOIN is about to fire — but if two branch names on the
    # active push remote CARRY DIVERGENT COMMITS, story merges sit off-canonical
    # and the epic PR would be incomplete (the ABS-217/ABS-220 strand). ABS-597
    # narrows this to real splits: only REMOTE branches count (a local work trace
    # is not a split, AC1) and a branch that is merely an ancestor of another is a
    # stale pointer, auto-resolved to the descendant instead of escalated (AC2) —
    # the two defects that froze a finished PILOT-71 for 2 h in Pilot 8. A genuine
    # divergence still routes to Needs PO Decision and NAMES the diverging commits,
    # not only the branches (AC3). Kill switch: ORCH_EPIC_SPLIT_GUARD=0.
    if [ "${ORCH_EPIC_SPLIT_GUARD:-1}" != "0" ]; then
        local ebclass ebkind
        ebclass="$(epic_branch_split_class "$epic")"
        ebkind="${ebclass%%$'\t'*}"
        if [ "$ebkind" = "ANCESTRY" ]; then
            # AC2: stale pointer, not a split — the descendant wins. Log and fall
            # through to the ordinary JOIN; no escalation, nothing to decide.
            local ebwinner ebcsv
            ebwinner="$(printf '%s' "$ebclass" | cut -f2)"
            ebcsv="$(printf '%s' "$ebclass" | cut -f3)"
            intent JOIN-SPLIT-RESOLVED "$epic" - - "descendant:$ebwinner contained-stale-of:$ebcsv"
        elif [ "$ebkind" = "SPLIT" ]; then
            local ebcsv ebdetail
            ebcsv="$(printf '%s' "$ebclass" | cut -f2)"
            ebdetail="$(printf '%s' "$ebclass" | cut -f3)"
            intent JOIN-SPLIT "$epic" - "Needs PO Decision" \
                "epic-branches:$ebcsv diverging:$ebdetail"
            if [ "$MODE" = "live" ]; then
                tracker comment "$epic" --kind decision --actor orchestrator \
                    --body "JOIN branch-split guard: divergent epic integration branches on the active push remote match epic/$epic-* ($ebcsv). They carry commits on BOTH sides — diverging: $ebdetail — so story merges are stranded off-canonical and the epic PR would be incomplete. Consolidate onto ONE canonical branch and retire the duplicate(s) before integrating (ABS-316/ABS-597) — not firing JOIN into an incomplete epic PR." \
                    >/dev/null 2>&1 || log "join branch-split comment failed on $epic"
                tracker transition "$epic" "Needs PO Decision" --actor orchestrator \
                    --reason "divergent epic integration branches at JOIN (ABS-316/ABS-597)" \
                    >/dev/null 2>&1 || log "join branch-split transition failed on $epic"
            fi
            return 0
        fi
    fi

    # AC1: every not-Done child is a declared exemption -> JOIN fires; the log
    # NAMES which child(ren) the gate excluded (ADR-A-0018 §d naming discipline).
    [ -n "$exempt" ] && intent JOIN-EXEMPT "$epic" - "Stories In Flight" "exempt-children:${exempt# }"
    intent JOIN "$epic" - "Epic Integration"
    [ "$MODE" = "live" ] || return 0
    if tracker transition "$epic" "Epic Integration" --actor orchestrator \
        --reason "JOIN: all children Done (ABS-73, spec §3.1)" \
        >/dev/null 2>&1; then
        # ABS-301 §d ratchet fix: call escalation_note_progress so the high-water
        # mark tracks the epic's forward progress and the stall counter resets
        # (Epic Integration chain_index 27 > Stories In Flight 26).
        escalation_note_progress "$epic" "Epic Integration"
    else
        log "join transition failed on $epic"
    fi
}

# =============================================================================
# §2.2 Role selection for Ready for Development
# =============================================================================
# Reads the ticket's `role` frontmatter via the adapter `get`; falls back to
# ORCH_DEFAULT_ROLE and records a #PLAN_UNCERTAINTY note when absent.
# Sets globals: resolved_role, role_note.
resolve_implementer_role() {
    local ticket="$1" dump role
    role_note=""
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    role="$(printf '%s\n' "$dump" | awk -F': ' '
        /^---$/ { fm++; next }
        fm == 1 && $1 == "role" { print $2; exit }
        fm >= 2 { exit }
    ')"
    if [ -n "$role" ]; then
        resolved_role="$role"
    else
        resolved_role="$ORCH_DEFAULT_ROLE"
        role_note="no-role-frontmatter-defaulting-to-$ORCH_DEFAULT_ROLE"
    fi
    # ABS-213 / ADR-A-0020: design-first in-place role switch (Operator Option B).
    # A ticket labelled `design-first` and not yet `design-first-done` routes its
    # FIRST Ready-for-Development spawn to system-architect for proposed-ADR
    # authoring; the architect's terminal handoff appends `design-first-done`, so
    # the NEXT sweep re-resolves to the dev role (latch consumed). Only dev-implementer
    # base roles switch — a review/decision seat is never re-pointed. Kill-switch:
    # ORCH_DESIGN_FIRST_ROUTING=0 restores the legacy (label-blind) behavior.
    if [ "${ORCH_DESIGN_FIRST_ROUTING:-1}" = "1" ] \
        && is_implementer_role "$resolved_role" \
        && ticket_has_label "$dump" "design-first" \
        && ! ticket_has_label "$dump" "design-first-done"; then
        role_note="design-first-adr-authoring:$resolved_role->system-architect"
        resolved_role="system-architect"
    fi
    # ABS-322 fastlane Solo-Seat: a `lane=fastlane` implementer spawn is the
    # single Solo-Seat — dev + scoped (ticket-local) tests + self-review in one
    # spawn (the QAS/PO tail is folded away by fastlane_skip). The mark rides in
    # the packet note so the seat knows its expanded duties; the role stays the
    # ticket's dev role. Kill-switch: ORCH_FASTLANE_COLLAPSE=0. Design-first and
    # fastlane are mutually exclusive in practice (fastlane eligibility excludes
    # design/security/schema, ABS-320), so this never overrides the switch above.
    if [ "${ORCH_FASTLANE_COLLAPSE:-1}" = "1" ] \
        && is_implementer_role "$resolved_role" \
        && [ "$(ticket_lane "$dump")" = "fastlane" ]; then
        role_note="fastlane-solo-seat:dev+scoped-tests+self-review"
    fi
}

# =============================================================================
# Event parsing (§1.3) — tolerant of spaces in values (e.g. "Ready for Dev.")
# =============================================================================
# parse_event <line> sets globals ev_ticket, ev_from, ev_to, ev_at from a line
# of the form: {ticket_id: X, from: Y, to: Z, at: T}. Splits on the labels, not
# on whitespace, so multi-word statuses survive.
parse_event() {
    local line="$1"
    ev_ticket=""; ev_from=""; ev_to=""; ev_at=""
    case "$line" in
        *"{ticket_id:"*"to:"*) ;;
        *) return 1 ;;
    esac
    ev_ticket="$(printf '%s' "$line" | sed -n 's/.*ticket_id:[[:space:]]*\(.*\), from:.*/\1/p')"
    ev_from="$(printf '%s' "$line"   | sed -n 's/.*, from:[[:space:]]*\(.*\), to:.*/\1/p')"
    ev_to="$(printf '%s' "$line"     | sed -n 's/.*, to:[[:space:]]*\(.*\), at:.*/\1/p')"
    ev_at="$(printf '%s' "$line"     | sed -n 's/.*, at:[[:space:]]*\(.*\)}.*/\1/p')"
    [ -n "$ev_ticket" ] && [ -n "$ev_to" ]
}

# =============================================================================
# §5.4 Idempotency re-read guard
# =============================================================================
# True when the ticket still sits in the event's `to` status (stale events and
# already-advanced tickets skip the spawn). Makes every dispatch path safe to
# re-attempt (first attempt, pending retry, reconciliation).
ticket_still_in() {
    # Reuses ticket_status (ABS-132) so the frontmatter-status read lives once.
    [ "$(ticket_status "$1")" = "$2" ]
}

# =============================================================================
# §2.4 Intake classification — three-way route at the orchestrator head
#      (v3.1, ABS-102 / spec ABS-103 §4; ADR-A-0009 bash-only, no LLM)
# =============================================================================
# A top-level Backlog ticket is classified from two adapter signals — its
# parent-epic link (`parent <id>`) and child count (`child-count <id>`) — plus
# its type, into exactly one intake class, then routed to the matching pipeline
# head. Purely additive (ADR-A-0010): the empty-epic route IS the unchanged v3.0
# flow, and the two new heads (Path-A / Path-B) are entry routes onto the existing
# pipeline, built out by sibling stories ABS-105 / ABS-107. All reads go through
# the adapter only (ADR-A-0007), never a direct work/tickets/*.md read.

# classify_intake <ticket> — print exactly one intake class (spec ABS-103 §4):
#   empty-epic | epic-with-children | parentless-ticket | child-of-epic
# A present parent-link short-circuits to child-of-epic (row 4); among the
# parentless, child-count selects row 2 and type discriminates rows 1 vs 3, so
# every (type, parent, count) tuple resolves to exactly one class.
classify_intake() {
    local ticket="$1" parent type count
    parent="$(tracker parent "$ticket" 2>/dev/null || true)"
    if [ -n "$parent" ]; then
        echo "child-of-epic"          # row 4: a normal child story — no intake head
        return 0
    fi
    type="$(fm_field "$(tracker get "$ticket" 2>/dev/null || true)" type)"
    if [ "$type" = "epic" ]; then
        count="$(tracker child-count "$ticket" 2>/dev/null || echo 0)"
        case "$count" in ''|*[!0-9]*) count=0 ;; esac
        if [ "$count" -gt 0 ]; then
            echo "epic-with-children"  # row 2 -> Path-B entry gate
        else
            echo "empty-epic"          # row 1 -> unchanged v3.0 decomposition
        fi
    else
        echo "parentless-ticket"       # row 3 -> Path-A head
    fi
}

# intake_head <class> — the named pipeline head each class routes to (spec §4).
intake_head() {
    case "$1" in
        empty-epic)         echo "v3.0 Grooming path" ;;
        # ABS-271: names the station the epic actually owes and actually reaches.
        # It used to read "Path-B entry gate" — a head that existed in the audit
        # comment only: nothing routed the epic there and no status edge led there.
        epic-with-children) echo "Ticket Review (DoR gate)" ;;
        parentless-ticket)  echo "Path-A head" ;;
        child-of-epic)      echo "normal child story" ;;
        *)                  echo "unknown" ;;
    esac
}

# intake_mechanic <class> — the sentence that makes the audit comment HONEST about
# what the classification does and does not do (ABS-271 AC2). route_intake CLASSIFIES;
# it does not transition. For a pre-filled epic the DoR gate is reached by
# STATION-GUARD on the epic's first forward hop, not by this function — so the
# comment says exactly that instead of claiming a routing it never performed.
intake_mechanic() {
    case "$1" in
        epic-with-children)
            printf '%s' " Children already exist, so Grooming/Enrichment (which exist to CREATE children) are satisfied by construction and are skipped. The Definition-of-Ready gate at 'Ticket Review' is still owed: this classification does NOT transition the epic there — STATION-GUARD enforces it on the epic's first forward hop, redirecting any landing past the gate back to it (ABS-271)." ;;
        *) printf '' ;;
    esac
}

# has_intake_marker <ticket-dump> — 0 (true) when the ticket already carries an
# orchestrator INTAKE-CLASS audit comment, so route_intake posts it at most once
# (comment-keyed guard, same idiom as has_blocked_marker). Scoped to a
# kind:gate-results + actor:orchestrator block so a comment merely quoting the
# marker text cannot disarm it.
has_intake_marker() {
    printf '%s\n' "$1" | awk '
        /^### / { in_orch = ($0 ~ /kind: gate-results/ && $0 ~ /actor: orchestrator/); next }
        in_orch && /INTAKE-CLASS=/ { found = 1 }
        END { exit(found ? 0 : 1) }
    '
}

# route_intake <ticket> — classify a top-level Backlog ticket and record its
# routing decision. ADDITIVE: runs alongside (never replaces) the existing Backlog
# PO dispatch — for empty-epic the named head IS the unchanged v3.0 PO-Triage seat.
# Dry-run logs the routing intent; live additionally posts a one-time
# kind:gate-results audit comment naming the chosen head (AC: bash-only, no LLM,
# audit comment names the path). A child-of-epic ticket is a no-op — classification
# runs on top-level tickets only (spec §2): its intent is logged for observability
# but it gets no intake-head audit comment.
#
# ABS-271: this function CLASSIFIES, it does not transition — and the comment now
# says so (intake_mechanic). The pre-filled epic's DoR gate is enforced downstream
# by STATION-GUARD (prefilled_epic_entry_index), which is what makes the named head
# reachable in mechanism and not just in prose.
route_intake() {
    local ticket="$1" dump class head
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    # Only classify a ticket actually resting in Backlog: reconcile re-derives
    # with a stale status and the same sweep may already have stall-raised it.
    case "$(fm_field "$dump" status)" in
        Backlog) ;;
        *) return 0 ;;
    esac
    class="$(classify_intake "$ticket")"
    head="$(intake_head "$class")"
    intent INTAKE-CLASSIFY "$ticket" - "$head" "class=$class"
    [ "$class" = "child-of-epic" ] && return 0   # not an intake head -> no audit comment
    [ "$MODE" = "live" ] || return 0
    has_intake_marker "$dump" && return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "INTAKE-CLASS=$class: intake classification routed $ticket to '$head' (bash-only, no LLM; spec ABS-103 §4, ABS-104).$(intake_mechanic "$class")" \
        >/dev/null 2>&1 || log "intake-class comment failed on $ticket"
}

# =============================================================================
# NOTIFY — human-facing notification comment via the adapter
# =============================================================================
notify() {
    local ticket="$1" body="$2"
    [ -n "$ticket" ] || { log "notify skipped (no notify ticket): $body"; return 0; }
    if [ "$MODE" = "live" ]; then
        tracker comment "$ticket" --kind notification --actor orchestrator --body "$body" >/dev/null 2>&1 \
            || log "notify comment failed on $ticket"
    fi
    intent NOTIFY "$ticket" - - "$body"
}

# =============================================================================
# §5 Safety controls
# =============================================================================

# --- §5.2 Per-ticket single-flight lock (mkdir; atomic on macOS+Linux) --------
lock_dir_for() { echo "$LOCKS_DIR/$1"; }

# ABS-300: the lock's OWNER token, recorded as a SIBLING file (never inside the
# lock dir — release_lock's rmdir needs the dir empty, else the ticket deadlocks).
# The token identifies the seat that acquired the lock; handoff_followthrough
# compares it against the current handoff author ($ORCH_SEAT_TOKEN) to refuse a
# foreign handoff that races a still-live seat.
lock_owner_file() { echo "$(lock_dir_for "$1").owner"; }
seat_lock_owner() { cat "$(lock_owner_file "$1")" 2>/dev/null || true; }
record_lock_owner() { printf '%s' "${ORCH_SEAT_TOKEN:-}" > "$(lock_owner_file "$1")" 2>/dev/null || true; }

# lock_age_for <ticket> — prints the lock dir's age in seconds; non-zero exit
# (no output) when no lock dir exists. Shared by acquire_lock (stale reclaim on
# the spawn path) and reconcile (orphan-lock skip guard, ABS-150) so the TTL
# staleness rule lives in exactly one place.
lock_age_for() {
    local dir now mtime
    dir="$(lock_dir_for "$1")"
    [ -d "$dir" ] || return 1
    now="$(date -u +%s)"
    # GNU `stat -c %Y` first, BSD `stat -f %m` fallback (ABS-246). GNU-first is
    # load-bearing: on GNU coreutils `stat -f %m` SUCCEEDS as a filesystem
    # query (prints the mount point), so a BSD-first chain feeds text into the
    # arithmetic below and crashes the runner (consumer Befund, GNU/MSYS).
    mtime="$(stat -c %Y "$dir" 2>/dev/null || stat -f %m "$dir" 2>/dev/null || echo "$now")"
    case "$mtime" in ''|*[!0-9]*) mtime="$now" ;; esac
    echo $((now - mtime))
}

# acquire_lock <ticket> — 0 if acquired, 1 if already held (single-flight).
# Reclaims a lock dir older than ORCH_LOCK_TTL (crashed runner) with a warning.
acquire_lock() {
    local ticket="$1" dir
    dir="$(lock_dir_for "$ticket")"
    # ABS-355 AC3: never fail-CLOSED on a vanished lock parent. If $LOCKS_DIR was
    # wiped mid-run (the 2026-07-16 state-dir wipe), a non-recursive mkdir of the
    # per-ticket lock dir hits ENOENT and returns 1 — read as "already held", so
    # EVERY ticket looked locked and the runner spun locking nothing. Recreate the
    # parent first; cheap and idempotent on the normal path.
    [ -d "$LOCKS_DIR" ] || mkdir -p "$LOCKS_DIR" 2>/dev/null || true
    if mkdir "$dir" 2>/dev/null; then
        record_lock_owner "$ticket"        # ABS-300: stamp the acquiring seat
        return 0
    fi
    # Existing lock: reclaim if stale.
    if [ -d "$dir" ]; then
        local age
        age="$(lock_age_for "$ticket" || echo 0)"
        if [ "$age" -ge "$ORCH_LOCK_TTL" ]; then
            log "reclaiming stale lock for $ticket (age ${age}s >= ${ORCH_LOCK_TTL}s)"
            rm -f "$(lock_owner_file "$ticket")" 2>/dev/null || true
            rmdir "$dir" 2>/dev/null || true
            if mkdir "$dir" 2>/dev/null; then record_lock_owner "$ticket"; return 0; fi
        fi
    fi
    return 1
}

release_lock() {
    local dir
    dir="$(lock_dir_for "$1")"
    rm -f "$(lock_owner_file "$1")" 2>/dev/null || true   # ABS-300: drop the owner stamp
    rmdir "$dir" 2>/dev/null || true
}

# --- §5.7 Per-epic merge token (ABS-256, ADR-A-0025) --------------------------
# ADR-A-0014 part 2 decided story PRs merge onto the epic branch "sequentially per
# epic", but nothing ever ENFORCED it: the §5.2 lock is keyed per TICKET, and
# ORCH_MAX_CONCURRENT lets sibling stories of one epic hold `Merging` and spawn
# `rte` at the same time, racing the same epic-branch tip. Compounding that, a
# rebase-bounced story re-walks the whole gate chain (rte.md step 5 prices a
# mechanical rebase conflict like a code defect). While the bounced story re-gates,
# a sibling merges and moves the tip under it, so it conflicts and bounces AGAIN —
# the five-bounce LIVELOCK of the ABS-245 consumer run (a livelock, not a race:
# the re-gate walk is slower than the sibling merge rate, so it never catches up).
#
# The token: at most ONE story per epic may occupy the Merging seat, and it KEEPS
# the token across a merge-bounce — through `Ready for Development` and the whole
# re-gate walk — until it leaves the merge path for good. Freezing the epic tip
# while its holder fixes the rebase (not the serialization itself) is what makes
# the SECOND bounce impossible: the story returns to the same tip it already
# resolved against. Siblings that cannot take the token are simply NOT spawned and
# rest in `Merging` — a reconcilable status, so the next sweep retries them. The
# status IS the queue; the lock dir IS the token (no new status, no new store).
#
# Staleness is decided by the HOLDER'S LIVENESS, never by a wall clock. A
# legitimate hold spans a full re-gate walk, which can outlast any sane
# ORCH_LOCK_TTL, so a TTL reclaim would steal the token from a story mid-fix and
# silently reopen the very cascade this closes. A token is stale iff its holder is
# gone or no longer anywhere on the story merge path (chain 1..10) — e.g. a human
# parked it in Backlog/Blocked. A crashed `rte` leaves the story resting in
# `Merging`, which re-enters its own token on the next sweep (no reclaim needed).
merge_token_dir_for() { echo "$LOCKS_DIR/merge/$1"; }

# merge_token_holder <epic> — the story id currently holding the epic's token ('').
merge_token_holder() { cat "$(merge_token_dir_for "$1")/holder" 2>/dev/null || true; }

# merge_token_epic_of <ticket> — the epic whose token <ticket> holds; non-zero exit
# when it holds none. Filesystem-only, so the hot dispatch path costs no tracker call.
merge_token_epic_of() {
    local ticket="$1" f dir
    for f in "$LOCKS_DIR"/merge/*/holder; do
        [ -f "$f" ] || continue
        [ "$(cat "$f" 2>/dev/null || true)" = "$ticket" ] || continue
        dir="${f%/holder}"
        echo "${dir##*/}"
        return 0
    done
    return 1
}

# merge_token_stale <holder> — 0 (true) when the recorded holder is gone or has
# left the story merge path, so its token may be reclaimed.
merge_token_stale() {
    local holder="$1" dump status idx
    [ -n "$holder" ] || return 0
    dump="$(tracker get "$holder" 2>/dev/null || true)"
    [ -n "$dump" ] || return 0
    status="$(fm_field "$dump" status)"
    idx="$(chain_index "$status")"
    [ "$idx" -ge 1 ] && [ "$idx" -le "$(chain_index "Merging")" ] && return 1
    return 0
}

# acquire_merge_token <ticket> <epic> — 0 acquired (or re-entered as the incumbent
# holder, the post-bounce case), 1 when a live sibling holds it. Atomic mkdir, the
# same primitive as acquire_lock.
acquire_merge_token() {
    local ticket="$1" epic="$2" dir holder
    dir="$(merge_token_dir_for "$epic")"
    mkdir -p "$LOCKS_DIR/merge" 2>/dev/null || true
    if mkdir "$dir" 2>/dev/null; then
        printf '%s\n' "$ticket" > "$dir/holder"
        return 0
    fi
    holder="$(merge_token_holder "$epic")"
    [ "$holder" = "$ticket" ] && return 0
    if merge_token_stale "$holder"; then
        log "reclaiming stale merge token for epic $epic (holder ${holder:-<none>} is off the merge path)"
        release_merge_token "$epic"
        if mkdir "$dir" 2>/dev/null; then
            printf '%s\n' "$ticket" > "$dir/holder"
            return 0
        fi
    fi
    return 1
}

release_merge_token() {
    local dir
    dir="$(merge_token_dir_for "$1")"
    rm -f "$dir/holder" 2>/dev/null || true
    rmdir "$dir" 2>/dev/null || true
}

# merge_topo_predecessor_pending <ticket> <dump> — 0 (true) when this story has a
# depends_on predecessor that is ITSELF still on the merge path (resting in
# `Merging`, i.e. contending for or holding the epic token). ADR-A-0014's queue
# grants the token to whichever contender the sweep reaches first (arrival/FIFO);
# this defers a dependent so its predecessor takes the token FIRST, independent of
# sweep order (ABS-396). The dependent must rebase onto the predecessor's merged
# tip — never the reverse — so the epic-end rebase conflict never forms. Sets
# MERGE_TOPO_BLOCKER for the intent note.
#
# Degrades to FIFO, never to a wedge: an absent/empty depends_on, an unreadable
# predecessor, or a predecessor NOT resting in Merging is simply not a blocker, so
# an independent set keeps its deterministic tiebreak (prioritize_rows order —
# canonical priority, then adapter age). A direct 2-cycle (a depends_on data error
# that cannot actually reach Merging, since depends_unmet already wedges it at
# development entry) is broken deterministically by id order: the lower id wins the
# token, the higher defers — so even malformed links never dead-wait both siblings.
MERGE_TOPO_BLOCKER=""
merge_topo_predecessor_pending() {
    MERGE_TOPO_BLOCKER=""
    [ "${ORCH_MERGE_TOPO:-1}" = "1" ] || return 1
    local ticket="$1" dump="$2" deps dep dep_dump dstat dep_deps
    deps="$(printf '%s\n' "$dump" | sed -n 's/^depends_on: \[\(.*\)\]/\1/p' | head -1 | tr -d ' ' | tr ',' ' ')"
    [ -n "$deps" ] || return 1
    for dep in $deps; do
        [ "$dep" = "$ticket" ] && continue          # self-loop: never blocks itself
        dep_dump="$(tracker get "$dep" 2>/dev/null || true)"
        [ -n "$dep_dump" ] || continue              # unreadable predecessor -> FIFO
        dstat="$(fm_field "$dep_dump" status)"
        [ "$dstat" = "Merging" ] || continue        # predecessor not queueing -> FIFO
        # Cycle guard: if the predecessor ALSO directly depends on us, break the tie
        # by id order so the epic never dead-waits both siblings.
        dep_deps="$(printf '%s\n' "$dep_dump" | sed -n 's/^depends_on: \[\(.*\)\]/\1/p' | head -1 | tr -d ' ' | tr ',' ' ')"
        case " $dep_deps " in
            *" $ticket "*) [ "$ticket" \< "$dep" ] && continue ;;  # we sort first: don't defer
        esac
        MERGE_TOPO_BLOCKER="$dep"
        return 0
    done
    return 1
}

# merge_token_gate <ticket> <to> — the dispatch hook. Returns 1 when the caller must
# NOT spawn (a live sibling holds this epic's merge token); 0 otherwise. Also owns
# the RELEASE edges and the AC3 bounce telemetry.
merge_token_gate() {
    local ticket="$1" to="$2" epic dump parent bounces
    [ "${ORCH_MERGE_QUEUE:-1}" = "1" ] || return 0

    epic="$(merge_token_epic_of "$ticket" || true)"

    # RELEASE — the holder has left the merge path for good: merged (`Docs`, and
    # `Done` defensively for a Path-A story) or come to rest at a human/PO gate
    # (`Ready for Merge`, `Needs PO Decision` — the ABS-74 rework bound). Pointedly
    # NOT on a bounce to `Ready for Development`: holding the token across that is
    # the load-bearing rule (ADR-A-0025 §3).
    if [ -n "$epic" ]; then
        case "$to" in
            "Docs"|"Done"|"Ready for Merge"|"Needs PO Decision")
                release_merge_token "$epic"
                intent MERGE-TOKEN-RELEASE "$ticket" - "$to" "epic=$epic"
                return 0
                ;;
        esac
    fi

    # Only the Merging edge contends for (or re-enters) a token. Every other status
    # of a holder just carries the token along, un-touched — that IS the hold.
    [ "$to" = "Merging" ] || return 0

    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    bounces="$(merge_bounce_count "$dump")"

    # Re-entry: this story already holds its epic's token (it was bounced and has
    # now re-gated back to Merging). The tip has not moved, so its rebase is clean.
    if [ -n "$epic" ]; then
        intent MERGE-TOKEN-HOLD "$ticket" rte "$to" "epic=$epic bounces=$bounces"
        return 0
    fi

    parent="$(fm_field "$dump" parent)"
    [ -n "$parent" ] || return 0   # parentless story: no epic branch, nothing to serialize

    # ABS-396: grant the token in depends_on TOPOLOGICAL order, not arrival/FIFO.
    # If a predecessor this story depends on is itself still resting in Merging,
    # defer so it merges FIRST — the dependent rebases onto the predecessor's tip.
    # Independent siblings fall through to the atomic acquire below (FIFO tiebreak).
    if merge_topo_predecessor_pending "$ticket" "$dump"; then
        intent MERGE-QUEUE-WAIT "$ticket" rte "$to" "epic=$parent predecessor=$MERGE_TOPO_BLOCKER topo=depends_on"
        return 1
    fi

    if acquire_merge_token "$ticket" "$parent"; then
        intent MERGE-TOKEN-ACQUIRE "$ticket" rte "$to" "epic=$parent bounces=$bounces"
        return 0
    fi
    intent MERGE-QUEUE-WAIT "$ticket" rte "$to" "epic=$parent holder=$(merge_token_holder "$parent")"
    return 1
}

# --- §5.6 Distributed whole-ticket remote claim (ABS-184, spec §4.3–4.4) ------
# The mkdir lock (§5.2) is single-machine only. When two runners share one
# tracker service account across machines, the CLAIM is the cross-machine
# single-flight primitive: stake -> settle -> adjudicate by server comment order.
# Adapter-only (ADR-A-0007): reads the `get` dump, stakes with `comment --kind
# claim`. Zero-dep (ADR-A-0009). NOT wired into dispatch here (that is ABS-185).

# claim_blocks <dump> — emit "<server-at>\t<instance-id>" for every `kind: claim`
# comment, in dump order (= server creation order). Correlates each comment's
# server-assigned `### <at>` header with the `instance:` field of its body — the
# server header, NEVER the body `at:`, is authoritative for age (immune to
# cross-machine clock skew; spec §4.3). One line per claim (first body line only).
# Pure awk over the adapter dump (same block-parse idiom as last_po_park_epoch).
claim_blocks() {
    printf '%s\n' "$1" | awk '
        /^### / {
            n = split($0, f, " ")
            cur_at = (n >= 2 ? f[2] : "")
            is_claim = ($0 ~ /kind: claim/)
            next
        }
        is_claim && /^instance:/ {
            line = $0
            sub(/^instance:[ \t]*/, "", line)
            idx = index(line, " |")
            id = (idx > 0 ? substr(line, 1, idx - 1) : line)
            print cur_at "\t" id
            is_claim = 0
        }
    '
}

# first_live_claim <dump> — print the instance-id of the FIRST live claim in dump
# order: the adjudicated winner (spec §4.4). "Live" = the claim's server `### <at>`
# header is younger than ORCH_CLAIM_TTL. Adjudication is by dump order alone (the
# earliest-created live claim wins) — NOT by any `at:` timestamp. A terminal-status
# ticket has no holder (its claims are ignored). Empty output = no live claim.
first_live_claim() {
    local dump="$1" now ttl at id epoch age status
    status="$(fm_field "$dump" status)"
    case "$status" in "Done"|"Epic Done"|"Canceled"|"Rejected") return 0 ;; esac
    now="$(now_epoch)"
    ttl="$ORCH_CLAIM_TTL"
    while IFS="$(printf '\t')" read -r at id; do
        [ -n "$id" ] || continue
        epoch="$(iso_to_epoch "$at")"
        # Unparseable header time -> treat as stale, never as a live holder.
        [ -n "$epoch" ] || continue
        age=$(( now - epoch ))
        if [ "$age" -lt "$ttl" ]; then
            printf '%s\n' "$id"
            return 0
        fi
    done <<EOF
$(claim_blocks "$dump")
EOF
    return 0
}

# own_latest_claim_age <dump> — age in seconds of THIS instance's most recent claim
# (largest server `### <at>` among its own claim comments). Empty when it holds
# none. Powers the refresh throttle (spec §4.4).
own_latest_claim_age() {
    local dump="$1" now at id epoch latest=""
    now="$(now_epoch)"
    while IFS="$(printf '\t')" read -r at id; do
        [ "$id" = "$ORCH_INSTANCE_ID" ] || continue
        epoch="$(iso_to_epoch "$at")"
        [ -n "$epoch" ] || continue
        if [ -z "$latest" ] || [ "$epoch" -gt "$latest" ]; then latest="$epoch"; fi
    done <<EOF
$(claim_blocks "$dump")
EOF
    [ -n "$latest" ] || return 0
    echo $(( now - latest ))
}

# stake_claim <ticket> — post one `kind: claim` comment for this instance. Body
# carries the instance-id (adjudication key) and a human-readable stake time.
stake_claim() {
    tracker comment "$1" --kind claim --actor orchestrator \
        --body "instance: $ORCH_INSTANCE_ID | at: $(timestamp)" >/dev/null 2>&1
}

# claim_settle_sleep — wait ORCH_CLAIM_SETTLE_MS + random 0..ORCH_CLAIM_JITTER_MS
# milliseconds so near-simultaneous stakes are all visible before adjudication,
# and so two racing runners do not adjudicate in lockstep (spec §4.3). Zero-dep:
# fractional `sleep`. A zero total (test injection) skips the sleep entirely.
claim_settle_sleep() {
    local jitter total_ms
    jitter=$(( RANDOM % (ORCH_CLAIM_JITTER_MS + 1) ))
    total_ms=$(( ORCH_CLAIM_SETTLE_MS + jitter ))
    [ "$total_ms" -gt 0 ] || return 0
    sleep "$(awk -v ms="$total_ms" 'BEGIN { printf "%.3f", ms / 1000 }')"
}

# refresh_claim <ticket> — heartbeat re-stake by the current holder, throttled to
# ~ORCH_CLAIM_TTL/3 to bound comment noise (spec §4.4). Re-stakes only when this
# instance's most recent claim is older than the throttle window (or it holds
# none yet); otherwise a no-op. Always returns 0 — the holder keeps the claim
# either way. Re-staking well inside the TTL is what stops a peer reclaiming a
# still-live holder mid-spawn.
refresh_claim() {
    local ticket="$1" dump age throttle
    throttle=$(( ORCH_CLAIM_TTL / 3 ))
    dump="$(tracker get "$ticket" 2>/dev/null)"
    age="$(own_latest_claim_age "$dump")"
    if [ -z "$age" ] || [ "$age" -ge "$throttle" ]; then
        stake_claim "$ticket"
    fi
    return 0
}

# acquire_remote_claim <ticket> — the whole-ticket remote claim (spec §4.3).
# Returns 0 (win) / 1 (loss); emits CLAIM / CLAIM-WON / SKIP-CLAIMED intents.
#   1. Pre-check: a live holder already exists? mine -> throttled refresh + win
#      (idempotent re-dispatch, no second stake); someone else's -> loss.
#   2. Stake a claim comment.
#   3. Settle (fixed + jitter) so every near-simultaneous stake is visible.
#   4. Adjudicate: re-read; the first live claim in server-creation order wins.
acquire_remote_claim() {
    local ticket="$1" dump holder
    dump="$(tracker get "$ticket" 2>/dev/null)"
    holder="$(first_live_claim "$dump")"
    if [ -n "$holder" ]; then
        if [ "$holder" = "$ORCH_INSTANCE_ID" ]; then
            refresh_claim "$ticket"
            intent CLAIM-WON "$ticket" - - "reclaim=own idempotent"
            return 0
        fi
        intent SKIP-CLAIMED "$ticket" - - "holder=$holder"
        return 1
    fi
    intent CLAIM "$ticket" - - "instance=$ORCH_INSTANCE_ID"
    stake_claim "$ticket"
    claim_settle_sleep
    dump="$(tracker get "$ticket" 2>/dev/null)"
    holder="$(first_live_claim "$dump")"
    if [ "$holder" = "$ORCH_INSTANCE_ID" ]; then
        intent CLAIM-WON "$ticket" - - "adjudicated"
        return 0
    fi
    intent SKIP-CLAIMED "$ticket" - - "holder=$holder"
    return 1
}

# claim_assign <ticket> <role> <to> — ABS-186 optional human-visibility layer.
# Called by dispatch AFTER a WON remote claim to stamp the ticket assignee so it
# visibly shows which operator/machine is working it. COSMETIC ONLY: the claim
# comment stays the sole claim of record and the assignee is NEVER read back to
# decide claim ownership (spec §3). No-op unless ORCH_CLAIM_ASSIGN=1. Reuses the
# ABS-126 resolution (ORCH_ASSIGNEE_<ROLE> beats ORCH_ASSIGNEE; empty = skip).
# Logs a CLAIM-ASSIGN intent in every mode; performs the real adapter write only
# in --live. A failed assign logs a warning and is NON-FATAL (always returns 0 so
# the spawn continues).
claim_assign() {
    local ticket="$1" role="$2" to="$3" assignee
    [ "$ORCH_CLAIM_ASSIGN" = "1" ] || return 0
    assignee="$(role_env "$role" ASSIGNEE)"; [ -n "$assignee" ] || assignee="${ORCH_ASSIGNEE:-}"
    [ -n "$assignee" ] || return 0
    intent CLAIM-ASSIGN "$ticket" "$role" "$to" "assignee=$assignee"
    [ "$MODE" = "dry-run" ] && return 0
    tracker assign "$ticket" "$assignee" >/dev/null 2>&1 \
        || log "claim-assign $ticket to $assignee failed (non-fatal)"
    return 0
}

# --- ABS-111 A1: async spawn bookkeeping ---------------------------------------
# live_spawn_count — number of still-running background spawns; prunes dead pids.
# Relies on the shell reaping exited background children so `kill -0` reports them
# dead (ESRCH) once finished — verified on bash 3.2 (macOS) and 4/5. A spawn that
# finishes between cycles is therefore pruned here on the next call and frees its
# concurrency slot; no explicit `wait` is needed outside the drain paths.
# Edge (accepted): if the OS recycles a reaped spawn's PID onto an unrelated
# process before the next prune, `kill -0` reads it "alive" and one slot is
# over-counted until the next `wait_for_spawns` drain clears SPAWN_PIDS —
# vanishingly unlikely and self-healing, never a stuck cap.
live_spawn_count() {
    local n=0 pid rest=""
    for pid in $SPAWN_PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            n=$((n + 1)); rest="$rest $pid"
        fi
    done
    SPAWN_PIDS="$rest"
    echo "$n"
}

# wait_for_spawns — drain all in-flight background spawns (loop exit paths and
# --once, so the test tier keeps its synchronous post-conditions).
wait_for_spawns() {
    local pid
    [ -n "${SPAWN_PIDS// /}" ] && log "draining in-flight spawns before exit"
    for pid in $SPAWN_PIDS; do
        wait "$pid" 2>/dev/null || true
    done
    SPAWN_PIDS=""
}

# --- ABS-111 C9: runner-provisioned worktree isolation -------------------------
# One git worktree per ticket under <target>/tmp/, created by the RUNNER and
# handed to the spawn via ORCH_SPAWN_CWD — isolation is infrastructure, not
# agent discipline (live run 1: agents switched the main checkout's branch).
# In-repo location is required by the headless file-tool sandbox (LIVE-3).
worktree_for() { echo "$ORCH_STATE_ROOT/tmp/$1-work"; }

# worktree_eligible_status <to> — the spawn statuses that receive a runner-
# provisioned worktree cwd under C9 (ABS-111). Single source shared by the
# live_spawn provisioning gate and the ABS-194 run_spawn_cmd cwd re-derivation,
# so both agree on exactly which seats are worktree-isolated.
# ABS-207: "In Progress" is here for the ABS-116 BOUNCE-REROUTE ONLY. A forward
# or neutral "In Progress" transition maps to NOOP (§2, map_action) and never
# reaches a spawn, so the only seat that spawns at In Progress is the reviewer/
# gate backward bounce that re-routes to the implementer (mapping "SPAWN -",
# role from ticket). Without this that reconcile deadlock-recovery resume was
# not worktree-eligible, so it ran in the MAIN checkout — the residual ABS-166
# cwd-loss (write-refused / wasted-escalation) class this ticket closes. It
# reuses the fail-closed provisioning + resume re-derivation unchanged.
worktree_eligible_status() {
    case "$1" in
        "Ready for Development"|"In Progress"|"In Review"|"In Test") return 0 ;;
        *) return 1 ;;
    esac
}

# resolve_seat_cwd <ticket> <to> — the effective working directory for a spawn,
# RE-DERIVED identically to the first spawn (ABS-194). Returns the SPAWN_CWD the
# caller already resolved when it is set; otherwise, on a resume / salvage-resume
# / handoff-repair path where that global was never populated, it re-derives the
# ticket worktree via worktree_for WHEN worktree spawns are on, the status is
# worktree-eligible, and the worktree already exists on disk. It NEVER provisions
# a missing worktree (provisioning stays fail-closed in live_spawn) — it only
# reconnects an EXISTING one so a resume lands in the same tree as the first
# spawn (ABS-166: a be-developer resume ran in the main checkout and its edits
# were denied) instead of falling back to the main checkout. Prints the path
# (empty = main checkout).
resolve_seat_cwd() {
    local ticket="$1" to="$2" cwd="${SPAWN_CWD:-}"
    if [ -z "$cwd" ] && [ "$ORCH_WORKTREE_SPAWNS" = "1" ] && worktree_eligible_status "$to"; then
        local wt
        wt="$(worktree_for "$ticket")"
        [ -d "$wt" ] && cwd="$wt"
    fi
    printf '%s' "$cwd"
}

# provision_seat_worktree <ticket> <role> <to> — PILOT-63: the single C9
# worktree-provisioning point for an isolated seat. On success sets SPAWN_CWD to
# the ticket worktree and returns 0; on failure emits the fail-closed
# SKIP-NOWORKTREE intent + log and returns 1, leaving SPAWN_CWD empty. The caller
# gates eligibility (ORCH_WORKTREE_SPAWNS + worktree_eligible_status) and decides
# how to rest the ticket: spawn_dispatch calls it BEFORE charging a budget unit so
# a provisioning failure costs nothing; live_spawn calls it only as
# defense-in-depth for a direct/resume caller that reached it with SPAWN_CWD unset.
provision_seat_worktree() {
    local ticket="$1" role="$2" to="$3"
    if ensure_worktree "$ticket"; then
        SPAWN_CWD="$(worktree_for "$ticket")"
        return 0
    fi
    intent SKIP-NOWORKTREE "$ticket" "$role" "$to"
    log "worktree provisioning failed for $ticket; refusing to spawn in the main checkout (C9 fail-closed)"
    return 1
}

# provision_worktree_settings <worktree-dir> — ABS-131. Make the operator's local
# permission grants travel into the freshly-created worktree. settings.local.json
# is gitignored/untracked, so `git worktree add` never carries it; without this a
# headless implementer spawn inherits no Write/Edit allows and fails closed on the
# first file edit (Befund 1, run ABS-126). Two parts, both best-effort:
#   1) copy $ORCH_STATE_ROOT/.claude/settings.local.json -> <wt>/.claude/ (no-op +
#      log event when the source is absent — never a crash).
#   2) merge ORCH_WORKTREE_EXTRA_ALLOW into the copy's permissions.allow so seats
#      get sufficient grants inside the ISOLATED tree without widening the
#      main-checkout allowlist. ABS-154 default = bare Bash/Write/Edit so the
#      seat can read/write/commit/push reliably instead of depending on the
#      (possibly restrictive) copied target allowlist. Needs jq; absent jq is a
#      logged no-op.
# The copy stays gitignored in the worktree (settings.local.json is in .gitignore),
# so it is never committed and is discarded with the worktree on cleanup.
provision_worktree_settings() {
    local wt="$1" src dst
    src="$ORCH_STATE_ROOT/.claude/settings.local.json"
    dst="$wt/.claude/settings.local.json"
    mkdir -p "$wt/.claude"
    if [ -f "$src" ]; then
        cp "$src" "$dst" && log "worktree provisioning: copied settings.local.json into $wt/.claude"
    else
        log "worktree provisioning: no settings.local.json in main checkout ($src); skipping copy (no-op)"
    fi
    merge_allow_grants "$dst" "worktree provisioning"
    merge_deny_rules "$dst" "worktree provisioning"
}

# merge_deny_rules <settings-file> <log-prefix> — ABS-272. Inject the shared-stash
# deny rule into the SEAT's generated settings.local.json, so a seat's `git stash`
# is refused by the same permission surface that already gates its tools (no new
# mechanism, per the ticket's #PATH_DECISION). Same jq set-union shape as
# merge_allow_grants: idempotent, needs jq, absent jq is a logged no-op. Applied to
# WORKTREE settings only — the main checkout's file belongs to the operator, whose
# own shell must keep full stash authority. The hook
# (.claude/hooks/pre-bash-stash-guard.sh) is the second layer and carries the
# stash-free recipe in its refusal message. Kill switch: ORCH_STASH_GUARD=0.
merge_deny_rules() {
    local dst="$1" what="${2:-deny-rule merge}"
    if [ "${ORCH_STASH_GUARD:-1}" != "1" ]; then
        log "$what: ORCH_STASH_GUARD=0 -> no git-stash deny rule injected (legacy behavior)"
        return 0
    fi
    [ -n "${ORCH_WORKTREE_DENY:-}" ] || return 0
    if ! command -v jq >/dev/null 2>&1; then
        log "$what: jq not found; skipping deny-rule injection"
        return 0
    fi
    local base='{}'
    [ -f "$dst" ] && base="$(cat "$dst")"
    if printf '%s' "$base" | jq --arg deny "$ORCH_WORKTREE_DENY" \
        '.permissions.deny = ((.permissions.deny // []) + ($deny | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length > 0))) | unique)' \
        > "$dst.tmp" 2>/dev/null && mv "$dst.tmp" "$dst"; then
        log "$what: merged deny rules ($ORCH_WORKTREE_DENY)"
    else
        rm -f "$dst.tmp" 2>/dev/null || true
        log "$what: deny-rule injection failed (jq merge); left settings.local.json as-is"
    fi
}

# merge_allow_grants <settings-file> <log-prefix> — idempotently merge
# ORCH_WORKTREE_EXTRA_ALLOW into the file's permissions.allow (jq set-union;
# a second run with the same grants is a byte-level no-op). Extracted from
# provision_worktree_settings so target-checkout provisioning shares the exact
# same merge — the single source that retro 2026-07-10 demanded.
merge_allow_grants() {
    local dst="$1" what="${2:-allow-grant merge}"
    [ -n "${ORCH_WORKTREE_EXTRA_ALLOW:-}" ] || return 0
    if ! command -v jq >/dev/null 2>&1; then
        log "$what: jq not found; skipping extra-allow injection"
        return 0
    fi
    local base='{}'
    [ -f "$dst" ] && base="$(cat "$dst")"
    if printf '%s' "$base" | jq --arg extra "$ORCH_WORKTREE_EXTRA_ALLOW" \
        '.permissions.allow = ((.permissions.allow // []) + ($extra | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length > 0))) | unique)' \
        > "$dst.tmp" 2>/dev/null && mv "$dst.tmp" "$dst"; then
        log "$what: merged extra allow grants ($ORCH_WORKTREE_EXTRA_ALLOW)"
    else
        rm -f "$dst.tmp" 2>/dev/null || true
        log "$what: extra-allow injection failed (jq merge); left settings.local.json as-is"
    fi
}

# provision_target_settings — retro 2026-07-10: NON-worktree seats (docs, PO,
# BSA, TDM) run with cwd = the TARGET checkout, whose .claude/settings.local.json
# historically drifted from the worktree copies (worktrees got the
# ORCH_WORKTREE_EXTRA_ALLOW merge, the main checkout did not) — every
# non-worktree seat then hit dontAsk write-denials (ABS-179 tech-writer 3x,
# ABS-181 enrichment, ABS-168 escalations). Apply the SAME merge to the target
# checkout once at startup so both run from one source. Idempotent (set-union);
# live mode only (dry-run must not write); opt out with
# ORCH_SYNC_TARGET_ALLOWLIST=0. The file is gitignored — never committed.
provision_target_settings() {
    [ "$MODE" = "live" ] || return 0
    [ "${ORCH_SYNC_TARGET_ALLOWLIST:-1}" = "1" ] || return 0
    mkdir -p "$ORCH_STATE_ROOT/.claude" 2>/dev/null || true
    merge_allow_grants "$ORCH_STATE_ROOT/.claude/settings.local.json" "target-checkout provisioning"
}

# provision_local_main_guard — ABS-224 AC1. Install the pre-commit guard that
# aborts a SEAT commit landing on the local main branch. The hook goes into the
# checkout's SHARED hooks dir (git-common-dir/hooks); worktrees share it, so one
# install covers the main checkout and every worktree. The guard lives here (and
# in .git/hooks), NOT in .claude/ — .claude/ is governor-generated and would be
# overwritten (scope candidate 1). Live mode only; best-effort (never crashes the
# run). Idempotent: detects its own install via the ABS-224-local-main-guard
# marker. Fail-open safety: an EXISTING foreign pre-commit hook is left untouched
# (we never clobber an operator's hook) with a logged skip. Kill switch: with
# ORCH_PROTECT_LOCAL_MAIN=0 the guard is removed (our marker only) and not
# installed, so toggling the switch off truly disables enforcement.
provision_local_main_guard() {
    [ "$MODE" = "live" ] || return 0
    command -v git >/dev/null 2>&1 || return 0
    local common hooks dst src marker="ABS-224-local-main-guard"
    common="$(git -C "$ORCH_STATE_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -z "$common" ]; then
        # Older git without --path-format: resolve the (possibly relative) dir.
        common="$(git -C "$ORCH_STATE_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
        case "$common" in ""|/*) : ;; *) common="$ORCH_STATE_ROOT/$common" ;; esac
    fi
    [ -n "$common" ] && [ -d "$common" ] || { log "local-main guard: no git-common-dir at $ORCH_STATE_ROOT; skipping install"; return 0; }
    hooks="$common/hooks"
    dst="$hooks/pre-commit"
    src="$SCRIPT_DIR/hooks/pre-commit-local-main-guard.sh"
    if [ "$ORCH_PROTECT_LOCAL_MAIN" = "0" ]; then
        # Kill switch off: remove ONLY our own guard (leave foreign hooks alone).
        if [ -f "$dst" ] && grep -q "$marker" "$dst" 2>/dev/null; then
            rm -f "$dst" 2>/dev/null && log "local-main guard: removed (ORCH_PROTECT_LOCAL_MAIN=0)"
        fi
        return 0
    fi
    [ -f "$src" ] || { log "local-main guard: source hook missing ($src); skipping install"; return 0; }
    mkdir -p "$hooks" 2>/dev/null || true
    if [ -f "$dst" ] && ! grep -q "$marker" "$dst" 2>/dev/null; then
        log "local-main guard: a foreign pre-commit hook already exists at $dst; leaving it untouched (fail-open)"
        return 0
    fi
    if cp "$src" "$dst" 2>/dev/null && chmod +x "$dst" 2>/dev/null; then
        log "local-main guard: installed pre-commit guard at $dst (ABS-224)"
    else
        log "local-main guard: install failed ($dst); continuing without the guard"
    fi
    return 0
}

# provision_main_head_guard — PILOT-66 AC3. Install the post-checkout guard that
# keeps a SEAT from leaving the MAIN checkout's HEAD moved off the protected
# branch (the root cause of the unbounded SKIP-NOWORKTREE retries: a work branch
# left checked out in the main checkout blocks `git worktree add`). Sibling of
# provision_local_main_guard — same shared-hooks-dir install, same marker/foreign-
# hook/kill-switch discipline, but the post-checkout hook name (a fresh slot, no
# chaining). Live mode only; best-effort; idempotent. Kill switch:
# ORCH_PROTECT_LOCAL_MAIN=0 removes (our marker only) and skips the install.
provision_main_head_guard() {
    [ "$MODE" = "live" ] || return 0
    command -v git >/dev/null 2>&1 || return 0
    local common hooks dst src marker="PILOT-66-main-head-guard"
    common="$(git -C "$ORCH_STATE_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -z "$common" ]; then
        common="$(git -C "$ORCH_STATE_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
        case "$common" in ""|/*) : ;; *) common="$ORCH_STATE_ROOT/$common" ;; esac
    fi
    [ -n "$common" ] && [ -d "$common" ] || { log "main-head guard: no git-common-dir at $ORCH_STATE_ROOT; skipping install"; return 0; }
    hooks="$common/hooks"
    dst="$hooks/post-checkout"
    src="$SCRIPT_DIR/hooks/post-checkout-main-head-guard.sh"
    if [ "$ORCH_PROTECT_LOCAL_MAIN" = "0" ]; then
        if [ -f "$dst" ] && grep -q "$marker" "$dst" 2>/dev/null; then
            rm -f "$dst" 2>/dev/null && log "main-head guard: removed (ORCH_PROTECT_LOCAL_MAIN=0)"
        fi
        return 0
    fi
    [ -f "$src" ] || { log "main-head guard: source hook missing ($src); skipping install"; return 0; }
    mkdir -p "$hooks" 2>/dev/null || true
    if [ -f "$dst" ] && ! grep -q "$marker" "$dst" 2>/dev/null; then
        log "main-head guard: a foreign post-checkout hook already exists at $dst; leaving it untouched (fail-open)"
        return 0
    fi
    if cp "$src" "$dst" 2>/dev/null && chmod +x "$dst" 2>/dev/null; then
        log "main-head guard: installed post-checkout guard at $dst (PILOT-66)"
    else
        log "main-head guard: install failed ($dst); continuing without the guard"
    fi
    return 0
}

# provision_ticket_tag_guard — PILOT-79. Install the commit-msg guard that aborts a
# SEAT commit on a STORY branch whose message is missing its [PREFIX-XXX] ticket tag
# (the tag the RTE Epic-Integration bisect maps a culprit commit to its story with).
# Sibling of provision_main_head_guard — same shared-hooks-dir install, same marker/
# foreign-hook/kill-switch discipline, but the commit-msg hook name (a fresh slot, no
# chaining). Live mode only; best-effort; idempotent. Kill switch:
# ORCH_TICKET_TAG_GUARD=0 removes (our marker only) and skips the install.
provision_ticket_tag_guard() {
    [ "$MODE" = "live" ] || return 0
    command -v git >/dev/null 2>&1 || return 0
    local common hooks dst src marker="PILOT-79-ticket-tag-guard"
    common="$(git -C "$ORCH_STATE_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -z "$common" ]; then
        common="$(git -C "$ORCH_STATE_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
        case "$common" in ""|/*) : ;; *) common="$ORCH_STATE_ROOT/$common" ;; esac
    fi
    [ -n "$common" ] && [ -d "$common" ] || { log "ticket-tag guard: no git-common-dir at $ORCH_STATE_ROOT; skipping install"; return 0; }
    hooks="$common/hooks"
    dst="$hooks/commit-msg"
    src="$SCRIPT_DIR/hooks/commit-msg-ticket-tag-guard.sh"
    if [ "${ORCH_TICKET_TAG_GUARD:-1}" = "0" ]; then
        # Kill switch off: remove ONLY our own guard (leave foreign hooks alone).
        if [ -f "$dst" ] && grep -q "$marker" "$dst" 2>/dev/null; then
            rm -f "$dst" 2>/dev/null && log "ticket-tag guard: removed (ORCH_TICKET_TAG_GUARD=0)"
        fi
        return 0
    fi
    [ -f "$src" ] || { log "ticket-tag guard: source hook missing ($src); skipping install"; return 0; }
    mkdir -p "$hooks" 2>/dev/null || true
    if [ -f "$dst" ] && ! grep -q "$marker" "$dst" 2>/dev/null; then
        log "ticket-tag guard: a foreign commit-msg hook already exists at $dst; leaving it untouched (fail-open)"
        return 0
    fi
    if cp "$src" "$dst" 2>/dev/null && chmod +x "$dst" 2>/dev/null; then
        log "ticket-tag guard: installed commit-msg guard at $dst (PILOT-79)"
    else
        log "ticket-tag guard: install failed ($dst); continuing without the guard"
    fi
    return 0
}

# check_harness_release — PILOT-81. Fail-close a LIVE start unless the governing
# harness checkout ($ORCH_HARNESS_HOME) is EXACTLY on an annotated release tag with
# a clean tree, and record the resolved harness version (tag+SHA) into the run.log
# head so a run's provenance is MEASURED, not merely asserted (AC6). Gated on
# MODE=live: a dry-run spawns nothing, so no unpublished code executes; and on the
# kill switch. Fail-open only when git or the checkout is genuinely unavailable
# (never silently on a version mismatch). Called once in main() after init_run_id.
check_harness_release() {
    [ "$MODE" = "live" ] || return 0
    [ "$ORCH_HARNESS_RELEASE_GUARD" = "1" ] || return 0
    command -v git >/dev/null 2>&1 || { log "harness-release guard: git not available; skipping (fail-open)"; return 0; }
    local h="$ORCH_HARNESS_HOME"
    if ! git -C "$h" rev-parse --git-dir >/dev/null 2>&1; then
        log "harness-release guard: $h is not a git checkout; skipping (fail-open)"
        return 0
    fi
    local sha tag dirty
    sha="$(git -C "$h" rev-parse --short HEAD 2>/dev/null || echo "?")"
    # AC1: EXACT tag only. `describe --exact-match` fails (empty) when HEAD is not
    # itself a tagged commit — unlike the prefix-matchable `describe --tags` the
    # launcher used, which happily returns "v2.32.0-4-g<sha>" four commits past.
    tag="$(git -C "$h" describe --exact-match --tags HEAD 2>/dev/null || true)"
    # AC2: any uncommitted OR untracked change to a versioned path means the runner
    # is not executing the release. --porcelain covers both in one shot.
    dirty="$(git -C "$h" status --porcelain 2>/dev/null)"
    # AC6: telemetry FIRST — record what was actually on HEAD, pass or fail, so a
    # refused start is as auditable as an accepted one.
    runlog HARNESS-VERSION - - - "tag=${tag:-none} sha=${sha} dirty=$([ -n "$dirty" ] && echo yes || echo no)"
    log "harness version: tag=${tag:-none} sha=${sha} (harness=$h)"
    if [ -z "$tag" ]; then
        die "harness-release guard (PILOT-81): $h HEAD is not exactly on an annotated release tag (sha=$sha). A live run executes the harness checkout's code, so it must BE a published release. A prefix match (git describe --tags -> 'vX-N-g...') is INSUFFICIENT and is exactly what let unpublished code run on 2026-07-26. Check out a release tag (git -C '$h' checkout <tag>) or set ORCH_HARNESS_RELEASE_GUARD=0 to override."
    fi
    if [ -n "$dirty" ]; then
        die "harness-release guard (PILOT-81): $h is on tag '$tag' but its working tree is DIRTY (uncommitted or untracked changes) — the runner would not execute the clean release. Clean the checkout (git -C '$h' status) or set ORCH_HARNESS_RELEASE_GUARD=0 to override."
    fi
    log "harness-release guard: OK — harness on release tag '$tag', tree clean"
    return 0
}

# resolve_active_main_ref <branch> <repo> — the remote-tracking ref that local
# <branch> should be compared against: the ACTIVE push remote's copy of it, NOT a
# hardcoded origin (PILOT-3 / ABS-493). origin goes stale the moment the primary
# host is unreachable — origin=Bitbucket has been down since 2026-07-16, so its
# cached origin/main froze while local main kept advancing with every merge, and
# the old hardcoded comparison shouted a phantom ahead=287 every sweep. Resolution
# order (first hit wins), all offline/config-based so the sweep stays network-free:
#   1. $ORCH_MAIN_REMOTE (explicit operator override) -> "<that>/<branch>".
#   2. git's own push target for the branch (branch.<br>.pushRemote /
#      remote.pushDefault / branch.<br>.remote) via "<br>@{push}" — literally the
#      remote `git push` and the git-host adapter use.
#   3. remote.pushDefault, else the SOLE configured remote — the active push
#      remote per the PILOT-25 doctrine (PILOT-67 AC3).
#   4. "origin/<branch>" ONLY when origin is genuinely that sole/default remote
#      (single-remote repos, unchanged).
# PILOT-67 AC3: the old step 3 was an UNCONDITIONAL "origin/<branch>" fallback.
# Under the PILOT-25 remote doctrine origin is Bitbucket — it carries no epic
# branches and froze when it went down 2026-07-16 — so falling back to it read a
# stale/absent ref as the comparison base. The active PUSH remote is the only
# source, so the fallback now resolves it from config instead of hardcoding origin.
# Prints the resolved remote-tracking ref name (never empty).
resolve_active_main_ref() {
    local br="$1" repo="$2" ref rname remotes n
    if [ -n "${ORCH_MAIN_REMOTE:-}" ]; then
        printf '%s/%s' "$ORCH_MAIN_REMOTE" "$br"; return 0
    fi
    ref="$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name "$br@{push}" 2>/dev/null || true)"
    if [ -n "$ref" ]; then printf '%s' "$ref"; return 0; fi
    # AC3: NO hardcoded origin. Resolve the active push remote from config —
    # remote.pushDefault, else the single configured remote — and only mention
    # origin when it genuinely IS that sole/default remote (single-remote repos).
    rname="$(git -C "$repo" config --get remote.pushDefault 2>/dev/null || true)"
    if [ -z "$rname" ]; then
        remotes="$(git -C "$repo" remote 2>/dev/null || true)"
        n="$(printf '%s\n' "$remotes" | grep -c '[^[:space:]]' || true)"
        [ "$n" = "1" ] && rname="$(printf '%s\n' "$remotes" | grep '[^[:space:]]' | head -1)"
    fi
    [ -n "$rname" ] || rname="origin"
    printf '%s/%s' "$rname" "$br"
}

# active_remote_name — the NAME of the active push remote (PILOT-75 / ADR-A-0030),
# derived from resolve_active_main_ref by stripping the trailing "/<main-branch>".
# Never a hardcoded origin: it inherits the same resolution order (ORCH_MAIN_REMOTE
# pin -> branch@{push} -> remote.pushDefault -> sole remote). Empty only when git or
# the repo is unavailable. Used by push_verify_failures to name the refs/remotes/
# namespace the pushed commits must live under.
active_remote_name() {
    local ref
    ref="$(resolve_active_main_ref "$ORCH_LOCAL_MAIN_BRANCH" "$ORCH_STATE_ROOT")"
    [ -n "$ref" ] || return 0
    printf '%s' "${ref%/"$ORCH_LOCAL_MAIN_BRANCH"}"
}

# check_local_main_drift — ABS-224 AC3 / PILOT-3. Once per RUN, WARN (intent +
# notification) when the local main branch is ahead of the ACTIVE push remote's
# copy of it (resolve_active_main_ref, not hardcoded origin): the detection path
# for a guard bypass (a seat that still slipped a commit onto local main). WARN-
# only, never a transition. Throttled to exactly one WARN per run (state file keyed
# on $ORCH_RUN_ID) so a standing drift stops spamming one intent line PER SWEEP
# (PILOT-3); when run-id separation is off (ORCH_RUN_ID empty, e.g. legacy/tests)
# it falls back to the local-main head so a standing drift still isn't re-notified.
# Honors the kill switch. Best-effort; a missing branch/tracking-ref or absent git
# is a silent no-op.
check_local_main_drift() {
    [ "$ORCH_PROTECT_LOCAL_MAIN" = "0" ] && return 0
    command -v git >/dev/null 2>&1 || return 0
    local br="$ORCH_LOCAL_MAIN_BRANCH" active ahead head sf key
    active="$(resolve_active_main_ref "$br" "$ORCH_STATE_ROOT")"
    ahead="$(git -C "$ORCH_STATE_ROOT" rev-list --count "$active..$br" 2>/dev/null || true)"
    [ -n "$ahead" ] || return 0                 # branch or active tracking-ref missing
    [ "$ahead" -gt 0 ] 2>/dev/null || return 0  # in sync with active remote -> nothing to warn
    head="$(git -C "$ORCH_STATE_ROOT" rev-parse "$br" 2>/dev/null || echo unknown)"
    sf="$ORCH_STATE_DIR/local-main-drift"
    key="${ORCH_RUN_ID:-$head}"                 # one WARN per run; per-head when run-id off
    if [ "$(cat "$sf" 2>/dev/null || true)" != "$key" ]; then
        intent LOCAL-MAIN-DRIFT - - - "ahead=$ahead branch=$br remote=$active head=$head"
        notify "${ORCH_NOTIFY_TICKET:-}" \
            "local '$br' is $ahead commit(s) ahead of $active (head $head): a seat may have committed to the local main outside a story branch/PR (ABS-224). These commits are in no PR and not on the active remote — investigate and either land them on a branch or discard."
        printf '%s\n' "$key" > "$sf" 2>/dev/null || true
    fi
    return 0
}

# check_claim_protocol <ticket> <status> — ABS-224 AC6. WARN when a ticket sits
# in "Ready for Development" WITH an active seat lock for longer than
# ORCH_CLAIM_WARN_MINUTES: a seat is demonstrably working (lock held) but never
# pulled the ticket to "In Progress" (claim protocol skipped, ABS-213 Befund).
# WARN-only — no auto-transition (the status chain stays seat-led). One NOTIFY
# per episode (per-ticket marker), cleared when the status/lock changes so a
# later re-entry warns afresh. Runs for EVERY ticket in the sweep, BEFORE the
# lock-skip continue (mirrors check_stuck). Always returns 0 (set -e safe).
check_claim_protocol() {
    local ticket="$1" status="$2" marker="$ORCH_STATE_DIR/claim-warn-$1"
    [ "$ORCH_CLAIM_WARN_MINUTES" -gt 0 ] 2>/dev/null || return 0
    if [ "$status" != "Ready for Development" ] || [ ! -d "$(lock_dir_for "$ticket")" ]; then
        rm -f "$marker" 2>/dev/null || true    # episode over -> re-arm
        return 0
    fi
    local age threshold
    age="$(lock_age_for "$ticket" || echo 0)"
    threshold=$(( ORCH_CLAIM_WARN_MINUTES * 60 ))
    if [ "$age" -ge "$threshold" ] && [ ! -f "$marker" ]; then
        intent CLAIM-PROTOCOL "$ticket" - "$status" "lock_age=${age}s threshold=${threshold}s"
        notify "${ORCH_NOTIFY_TICKET:-$ticket}" \
            "claim-protocol WARN: $ticket has an active seat lock (${age}s) but still rests in 'Ready for Development' — a seat is working without pulling the ticket to 'In Progress' (ABS-224 AC6). WARN only; move the ticket to reflect the work."
        : > "$marker" 2>/dev/null || true
    fi
    return 0
}

# resolve_fresh_base <repo> <mainbranch> — ABS-355 AC1: echo the SHA of the
# FRESHEST REACHABLE remote <mainbranch>, or "" when no remote is reachable.
#
# THE DEFECT THIS CLOSES (live incident 2026-07-16, second live-state wipe):
# origin (Bitbucket) was frozen at a stale tip during an outage while
# gitlab/main was current. ensure_worktree based new seat branches on
# origin/<main> UNCONDITIONALLY, so seats were provisioned on pre-release code
# (missing the ABS-335 guard) and their test teardown wiped the live state dir.
#
# SELECTION: among remotes we can actually REACH (`ls-remote` succeeds — this is
# the "fetch success" verification the AC asks for; a dead/frozen-unreachable
# origin returns nothing and is skipped), pick the one whose <main> tip has the
# newest commit timestamp. This is the SAME remote the RTE/merge path uses under
# the GitLab-fallback doctrine (during an origin outage only gitlab is reachable
# AND freshest), so provisioning and merge agree on the base. The tip object is
# fetched only when not already local.
#
# HANG GUARD (ABS-355 review iteration 1): every remote probe runs under a HARD
# wall-clock ceiling via _bounded_git — GIT_SSH_COMMAND's ConnectTimeout only
# bounds SSH, but the GitLab fallback remote is HTTPS (Keychain PAT) and a
# down/half-open HTTPS host has NO such bound, so provisioning could hang on the
# very outage this fix exists to survive. The wrapper is portable (no
# timeout(1)/gtimeout — absent on stock macOS) and also passes
# http.lowSpeedLimit/Time so a stalled (not merely unopened) transfer aborts.

# _bounded_git <secs> <repo> <git-args...> — run a git remote op under a hard
# wall-clock timeout. Returns git's rc, or a plain non-zero (124) when the ceiling
# fires (caller treats that as "remote unreachable" and skips it).
#
# ABS-371 HARDENING (latent SIGTERM-the-caller trap in the ABS-355 watcher):
#   1. Prefer timeout(1)/gtimeout(1) when present — they bound + kill git in their
#      OWN child process group, so no hand-rolled signal can ever reach the caller.
#   2. Portable fallback (stock macOS has neither): the sleep-then-kill watcher runs
#      in its own subshell and only ever signals the SPECIFIC git pid. The instant
#      git returns we cancel AND fully `wait`-reap the watcher, closing the window
#      in which its delayed `kill` could land on a reused pid — so the function is
#      safe whether invoked as a plain statement or in command-substitution.
#   3. A signal-kill exit (128+n, e.g. 143=SIGTERM) is normalised to a plain 124 so
#      a plain-statement caller never sees a propagated signal/143.
_bounded_git() {
    local secs="$1" repo="$2"; shift 2
    local _to=""
    if command -v timeout >/dev/null 2>&1; then _to="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then _to="gtimeout"; fi

    local _rc=0
    if [ -n "$_to" ]; then
        # -k 1: if TERM at the deadline is ignored, KILL 1s later. timeout owns the
        # child pgid, so the caller shell is untouched regardless of call context.
        GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=8' \
            "$_to" -k 1 "$secs" \
            git -C "$repo" -c "http.lowSpeedLimit=1000" -c "http.lowSpeedTime=$secs" "$@" || _rc=$?
    else
        GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=8' \
            git -C "$repo" -c "http.lowSpeedLimit=1000" -c "http.lowSpeedTime=$secs" "$@" &
        local _gpid=$!
        # Watcher: bounded sleep, then TERM/KILL the SPECIFIC git pid only — never
        # $$ (the caller). Its own subshell scope guarantees the kill target.
        ( sleep "$secs"; kill -TERM "$_gpid" 2>/dev/null; sleep 1; kill -KILL "$_gpid" 2>/dev/null ) &
        local _wpid=$!
        wait "$_gpid" 2>/dev/null || _rc=$?
        # Self-cancel + REAP the watcher the instant git returns: no stray delayed
        # kill can outlive the call and hit a reused pid / the caller (ABS-371).
        kill -TERM "$_wpid" 2>/dev/null
        wait "$_wpid" 2>/dev/null || true
    fi
    # Normalise a signal-kill (128+n) into a plain non-zero — the caller only needs
    # "unreachable", and a raw 143 read as a propagated signal is the trap we close.
    if [ "$_rc" -gt 128 ]; then _rc=124; fi
    return "$_rc"
}

resolve_fresh_base() {
    local repo="$1" mainbranch="$2" r tip ts best_sha="" best_ts=-1
    local probe_to="${ORCH_REMOTE_PROBE_TIMEOUT:-12}"
    for r in $(git -C "$repo" remote 2>/dev/null || true); do
        tip="$(_bounded_git "$probe_to" "$repo" ls-remote --heads "$r" "$mainbranch" 2>/dev/null \
            | awk 'NR==1{print $1}' || true)"
        [ -n "$tip" ] || continue
        if ! git -C "$repo" cat-file -e "${tip}^{commit}" 2>/dev/null; then
            _bounded_git "$probe_to" "$repo" fetch --quiet --no-tags "$r" "$mainbranch" 2>/dev/null || continue
            git -C "$repo" cat-file -e "${tip}^{commit}" 2>/dev/null || continue
        fi
        ts="$(git -C "$repo" log -1 --format=%ct "$tip" 2>/dev/null || true)"
        [ -n "$ts" ] || continue
        if [ "$ts" -gt "$best_ts" ]; then best_ts="$ts"; best_sha="$tip"; fi
    done
    printf '%s' "$best_sha"
}

# ENSURE_WORKTREE_STDERR — PILOT-66 AC2: the LAST failing `git worktree add`'s own
# stderr, captured by _worktree_add and surfaced by the failure log + the
# provisioning-failure record. Before this the runlog carried only a bare
# "(git worktree add)" with no git error text, so diagnosing a failure needed
# git-reflog archaeology. Reset at the top of every ensure_worktree call.
ENSURE_WORKTREE_STDERR=""

# _worktree_add <args…> — `git -C "$ORCH_STATE_ROOT" worktree add <args…>`, but
# capturing git's stderr into ENSURE_WORKTREE_STDERR on failure (PILOT-66 AC2).
# `2>&1 1>/dev/null` inside $() sends stderr to the capture pipe and discards
# stdout, so a success is silent (unchanged) and a failure names the real cause
# ("… is already checked out at …"). Returns git's own exit status.
_worktree_add() {
    local err rc
    err="$(git -C "$ORCH_STATE_ROOT" worktree add "$@" 2>&1 1>/dev/null)"; rc=$?
    [ "$rc" -eq 0 ] || ENSURE_WORKTREE_STDERR="$err"
    return "$rc"
}

# ensure_worktree <ticket> — create (or reuse) the ticket worktree on branch
# <ticket>-auto. `git worktree add` calls are serialized via a global mkdir
# lock: concurrent adds against one .git can race; concurrent COMMITS in
# separate worktrees are safe (per-worktree index).
ensure_worktree() {
    local ticket="$1" wt wlock tries=0
    ENSURE_WORKTREE_STDERR=""
    wt="$(worktree_for "$ticket")"
    if [ -d "$wt" ]; then
        # ABS-377: a worktree REUSED from before the settings.local.json
        # provisioning fix (v2.26.1) carries only settings.template.json, so every
        # mutation tool-call in the dispatched seat is denied under
        # --permission-mode dontAsk (ABS-348 burned two NOMOVE->NPD escalation
        # rounds on exactly this, operator hand-copied the file). The fresh-create
        # path below provisions via provision_worktree_settings, but the existing-
        # worktree early return never did — so re-provision here via the SAME
        # mechanism when the file is missing. Keyed on absence => no-op on an
        # already-provisioned reuse; best-effort (provision_worktree_settings never
        # crashes).
        if [ ! -f "$wt/.claude/settings.local.json" ]; then
            runlog SEAT-SETTINGS-HEAL "$ticket" - - "reused worktree missing .claude/settings.local.json; re-provisioning ($wt)"
            provision_worktree_settings "$wt"
        fi
        return 0
    fi
    wlock="$ORCH_STATE_DIR/worktree.lock"
    while ! mkdir "$wlock" 2>/dev/null; do
        tries=$((tries + 1))
        [ "$tries" -gt 60 ] && { log "worktree lock timeout for $ticket"; return 1; }
        sleep 1
    done
    local rc=0
    if [ ! -d "$wt" ]; then
        # Clear stale worktree metadata first: if a previous tmp/<ticket>-work was
        # removed with `rm -rf` (not `git worktree remove`), git still believes
        # <ticket>-auto is checked out elsewhere and the add below fails "already
        # checked out" — which would fail-closed and rest the ticket forever. Prune
        # drops those dangling administrative entries so provisioning can recover.
        git -C "$ORCH_STATE_ROOT" worktree prune >/dev/null 2>&1 || true
        # Branch selection (ABS-111 hotfix): prefer the ticket's EXISTING work
        # branch — the implementing seat may have named it freely (e.g.
        # <ticket>-<slug>) — so review/test worktrees contain the story's work
        # and a re-derived implementer resumes its own branch. A non "-auto"
        # branch wins over the runner's own; with none, create <ticket>-auto.
        local br
        br="$(git -C "$ORCH_STATE_ROOT" for-each-ref --format='%(refname:short)' "refs/heads/$ticket-*" \
            | awk 'BEGIN{pick=""} { if ($0 !~ /-auto$/ && pick=="") pick=$0; if (auto=="") { if ($0 ~ /-auto$/) auto=$0 } } END{ if (pick!="") print pick; else if (auto!="") print auto }')"
        if [ -n "$br" ]; then
            _worktree_add "$wt" "$br" || rc=1
        else
            # ABS-119: a BRAND-NEW work branch for an epic child bases on the
            # epic integration branch tip (epic/<parent>-*) — a dependent
            # released at Docs entry must see the dependency's merged code.
            # Deterministic pick (lexicographically first) + warning when more
            # than one branch matches; fallback = current HEAD as before.
            local parent base=""
            parent="$(tracker get "$ticket" 2>/dev/null | sed -n 's/^parent: //p' | head -1 || true)"
            if [ -n "$parent" ]; then
                local ebrs
                ebrs="$(git -C "$ORCH_STATE_ROOT" for-each-ref --format='%(refname:short)' "refs/heads/epic/$parent-*" 2>/dev/null | LC_ALL=C sort)"
                base="$(printf '%s\n' "$ebrs" | head -1)"
                [ "$(printf '%s\n' "$ebrs" | grep -c . || true)" -gt 1 ] \
                    && log "multiple epic branches match epic/$parent-*; basing $ticket on '$base' (lexicographic pick)"
            fi
            if [ -n "$base" ]; then
                _worktree_add "$wt" -b "$ticket-auto" "$base" || rc=1
            else
                # ABS-355 (supersedes the ABS-299 origin-only base): base on the
                # FRESHEST REACHABLE remote main — never a hardcoded origin/<main>
                # that can be frozen at a stale tip during a remote outage (the
                # 2026-07-16 second live-state wipe). resolve_fresh_base also
                # guards the ABS-299 concern: it returns a remote tip, never the
                # checkout's current HEAD, so a sibling runner's unreviewed HEAD
                # commit is not dragged into the new branch. Fall back to HEAD only
                # when NO remote is reachable (logged so the operator sees it).
                local _fresh_base
                _fresh_base="$(resolve_fresh_base "$ORCH_STATE_ROOT" "$ORCH_LOCAL_MAIN_BRANCH")"
                if [ -n "$_fresh_base" ]; then
                    _worktree_add "$wt" -b "$ticket-auto" "$_fresh_base" || rc=1
                else
                    log "ensure_worktree: no reachable remote $ORCH_LOCAL_MAIN_BRANCH did not resolve;" \
                        "basing $ticket-auto on HEAD (fallback)"
                    _worktree_add "$wt" -b "$ticket-auto" || rc=1
                fi
            fi
        fi
    fi
    # ABS-131: carry the operator's local permissions into the new worktree so the
    # implementer spawn can Write/Edit (settings.local.json does not travel with
    # `git worktree add`). Only on a freshly-provisioned tree; best-effort.
    [ "$rc" -eq 0 ] && provision_worktree_settings "$wt"
    rmdir "$wlock" 2>/dev/null || true
    # PILOT-66 AC2: name git's own error, not a bare "(git worktree add)".
    [ "$rc" -eq 0 ] || log "worktree provisioning failed for $ticket (git worktree add)${ENSURE_WORKTREE_STDERR:+: $ENSURE_WORKTREE_STDERR}"
    return "$rc"
}

# --- PILOT-66: bounded worktree-provisioning failure (count → backoff → escalate)
# The fail-closed decision (never spawn a write-capable seat in the main checkout)
# is correct; the DEFECT was the unbounded, alarmless, budget-draining retry. These
# helpers give the failure a counter, a backoff, and — after N attempts — a visible
# escalation with an Attention-Event, instead of silently re-deriving every sweep.
worktree_fail_file() { echo "$ORCH_STATE_DIR/wtfail-$1"; }

# worktree_fail_count <ticket> — this ticket's consecutive provisioning failures.
worktree_fail_count() { cat "$(worktree_fail_file "$1")" 2>/dev/null || echo 0; }

# clear_worktree_fail <ticket> — a SUCCESSFUL provision resets the ladder.
clear_worktree_fail() { rm -f "$(worktree_fail_file "$1")" 2>/dev/null || true; }

# record_worktree_provision_failure <ticket> <to> <role> — count this failure,
# emit the fail-closed intent (with git's stderr, AC2), and either back off
# (AC1) or, at ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS, escalate (AC1). Always 0.
record_worktree_provision_failure() {
    local ticket="$1" to="$2" role="$3" f n git_note=""
    f="$(worktree_fail_file "$ticket")"
    n="$(worktree_fail_count "$ticket")"; n=$(( ${n:-0} + 1 ))
    printf '%s\n' "$n" > "$f" 2>/dev/null || true
    [ -n "${ENSURE_WORKTREE_STDERR:-}" ] && git_note=" git: $ENSURE_WORKTREE_STDERR"
    # Keep the frozen SKIP-NOWORKTREE intent (tests + fail-closed contract), now
    # carrying the attempt index and git's own error text.
    intent SKIP-NOWORKTREE "$ticket" "$role" "$to" "attempt=$n/${ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS}${git_note}"
    log "worktree provisioning failed for $ticket (attempt $n/${ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS}); refusing to spawn in the main checkout (C9 fail-closed)${git_note}"
    if [ "$ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS" -gt 0 ] && [ "$n" -ge "$ORCH_WORKTREE_PROVISION_MAX_ATTEMPTS" ]; then
        escalate_worktree_provision "$ticket" "$to" "$role" "$n"
    else
        # AC1: back off so the next sweep skips this ticket for free (no budget,
        # no lock) via the existing spawn_dispatch backoff_active gate.
        record_backoff "$ticket" "$to"
    fi
    return 0
}

# escalate_worktree_provision <ticket> <to> <role> <attempts> — realize AC1's
# "escalate after N attempts, visibly": gate-results comment + Blocked transition
# + NOTIFY (the Attention-Event). Mirrors escalate_rework/record_spawn_crash.
# Blocked is a human-attention status that is NOT reconciled, so the silent retry
# loop stops here (no budget consumed — the gate fail-closes BEFORE the spend).
escalate_worktree_provision() {
    local ticket="$1" to="$2" role="$3" n="$4" git_note=""
    [ -n "${ENSURE_WORKTREE_STDERR:-}" ] && git_note=" Last git error: $ENSURE_WORKTREE_STDERR."
    intent WORKTREE-PROVISION-ESCALATE "$ticket" "$role" "Blocked" "attempts=$n at=$to"
    clear_worktree_fail "$ticket"   # episode escalated → re-arm for a future re-entry
    [ "$MODE" = "live" ] || return 0
    tracker comment "$ticket" --kind gate-results --actor orchestrator \
        --body "Worktree provisioning failed $n consecutive times at '$to' (PILOT-66). The runner fail-closes rather than spawn a write-capable seat in the main checkout, but $n attempts is a standing blocker — escalating to Blocked instead of retrying silently.${git_note} Common root cause: a seat running in the main checkout left a work branch checked out, so 'git worktree add' cannot check out the same branch (ABS-224 branch discipline / PILOT-66 AC3 head-move guard). Free the branch in the main checkout (git -C <main> checkout $ORCH_LOCAL_MAIN_BRANCH) or remove the stale worktree, then re-open." \
        >/dev/null 2>&1 || log "worktree-provision escalate comment failed on $ticket"
    tracker transition "$ticket" "Blocked" --actor orchestrator \
        --reason "worktree provisioning failed $n times at $to (PILOT-66); escalating for human attention" \
        >/dev/null 2>&1 || log "worktree-provision escalate transition failed on $ticket"
    notify "${ORCH_NOTIFY_TICKET:-$ticket}" \
        "worktree provisioning for $ticket failed $n times at '$to' and is now Blocked (PILOT-66).${git_note} Likely a work branch left checked out in the main checkout blocks 'git worktree add'. Free it (git checkout $ORCH_LOCAL_MAIN_BRANCH in the main checkout) or clear the stale worktree, then re-open."
}

# --- §5.5 Iteration-guard integration ----------------------------------------
# iteration_guard_blocks <ticket> — 0 (true) when the guard reports at-cap
# (exit 2) for a bounce-capable spawn. Fail-open: any other outcome -> false.
iteration_guard_blocks() {
    local ticket="$1" rc=0
    ITERATION_GUARD_DETAIL=""
    [ -f "$ORCH_ITERATION_GUARD" ] || return 1
    # PILOT-49: keep the guard's block reason (functional-vs-infra-abort breakdown,
    # AC5) so block_for_iteration_cap can name it on the park comment.
    ITERATION_GUARD_DETAIL="$(TRACKER_CMD="$TRACKER_CMD" bash "$ORCH_ITERATION_GUARD" "$ticket" 2>&1 >/dev/null)" || rc=$?
    [ "$rc" -eq 2 ]
}

# block_for_iteration_cap <ticket> <to> — realize §5.5: record a gate-results
# comment and escalate to Needs PO Decision instead of spawning (ABS-115;
# consistent with escalate_rework and record_spawn_crash).
block_for_iteration_cap() {
    local ticket="$1" to="$2" target
    local detail="${ITERATION_GUARD_DETAIL:-}"
    # PILOT-69 AC1: a demonstrably-finished ticket (reached the acceptance/merge
    # tier) parks to Blocked, whose resume-to-origin list includes Merging, so the
    # merge path stays reachable; else Needs PO Decision (a fresh product decision).
    target="$(escalation_park_target "$ticket")"
    intent BLOCK-ITERATION-CAP "$ticket" - "$target" "at=$to"
    if [ "$MODE" = "live" ]; then
        # PILOT-49/ABS-555: only FUNCTIONAL bounces (gate reject -> rework) are
        # counted toward the cap; infrastructure aborts (crash, error_max_turns,
        # timeout, rate-limit, session-poison) are excluded. Name the breakdown
        # (AC5) so the operator does not have to reconstruct it by hand.
        local escape
        if [ "$target" = "Blocked" ]; then
            escape="This ticket already reached the acceptance/merge tier — its work is finished — so it parks in Blocked (resume-to-origin includes Merging) to keep the merge path one human/TDM hop away, not Needs PO Decision (PILOT-69 AC1)."
        else
            escape="If the work is already approved (gate verdicts on the ticket, merge_readiness clean) the PO may route it forward to Merging (PILOT-49/ABS-555)."
        fi
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "Iteration cap reached at $to; escalating to $target instead of another implement/validate loop (ABS-12 / ABS-115 / spec §5.5). Only FUNCTIONAL bounces count; infrastructure aborts are excluded (PILOT-49/ABS-555).${detail:+ Guard: ${detail}} $escape" \
            >/dev/null 2>&1 || log "iteration-cap comment failed on $ticket"
        tracker transition "$ticket" "$target" --actor orchestrator \
            --reason "iteration cap reached at $to (ABS-12/ABS-115); parked to $target (PILOT-69 AC1)" \
            >/dev/null 2>&1 || log "iteration-cap transition failed on $ticket"
    fi
}

# --- §5.4 Per-run spawn budget (ADR-A-0009) ----------------------------------
# budget_exhausted — 0 (true) when the per-run SOFT cap is spent. No longer a
# hard stop (PILOT-47): it triggers the drain/auto-extend decision instead.
budget_exhausted() { [ "$SPAWN_BUDGET" -le 0 ]; }

# --- PILOT-47 progress-aware spawn budget (extends ADR-A-0009) ----------------
# The per-run soft cap (ORCH_MAX_SPAWNS_PER_RUN) no longer HARD-STOPS a healthy
# run. At the soft cap the runner (1) tries a progress-aware auto-extend, then
# (2) enters DRAIN mode — no new intake, in-flight tickets finish — and ends the
# run cleanly once nothing is in-flight. A per-ticket spawn cap breaks a single
# cyclically-respawning ticket, and a hard backstop (soft cap x
# ORCH_SPAWN_BUDGET_HARD_MULTIPLE, or the per-day ledger) still fail-closes to the
# ABS-455 exit-75 handshake.

# spawn_budget_hard_max — absolute per-run ceiling (AC4).
spawn_budget_hard_max() { echo $(( ORCH_MAX_SPAWNS_PER_RUN * ORCH_SPAWN_BUDGET_HARD_MULTIPLE )); }

# hard_backstop_reached — 0 (true) at/above the absolute per-run ceiling. Uses
# the monotonic SPAWNS_USED so an auto-extended budget can never slip past it
# (fail-closed against a progress-sensor error). ORCH_MAX_SPAWNS_PER_RUN=0 makes
# the ceiling 0, preserving the ABS-455 "starve the budget" test path (exit 75).
hard_backstop_reached() { [ "$SPAWNS_USED" -ge "$(spawn_budget_hard_max)" ]; }

# ticket_spawn_count <ticket> — spawns emitted for this ticket THIS run (AC3).
ticket_spawn_count() {
    local key="$1" v
    case "$TICKET_SPAWNS" in
        *"[$key|"*) v="${TICKET_SPAWNS#*"[$key|"}"; v="${v%%]*}"; echo "${v:-0}" ;;
        *) echo 0 ;;
    esac
}

# ticket_spawn_incr <ticket> — bump this ticket's per-run spawn tally (string
# accumulator, same idiom as the §5.1 PENDING set — no assoc arrays for bash 3.2).
ticket_spawn_incr() {
    local key="$1" cur head tail
    cur="$(ticket_spawn_count "$key")"; cur=$((cur + 1))
    case "$TICKET_SPAWNS" in
        *"[$key|"*)
            head="${TICKET_SPAWNS%%"[$key|"*}"
            tail="${TICKET_SPAWNS#*"[$key|"}"; tail="${tail#*]}"
            TICKET_SPAWNS="${head}${tail}" ;;
    esac
    TICKET_SPAWNS="${TICKET_SPAWNS}[$key|$cur]"
}

# count_done_tickets — number of tickets currently at Done (progress watermark).
# Best-effort; a tracker read failure returns 0 and the watermark comparison then
# reports NO progress, so a broken sensor never fabricates an extension (AC4).
# awk (not `grep -c`) so an empty result prints a clean single "0" and exits 0 —
# `grep -c` exits 1 on no match, which would double via a `|| echo 0` fallback.
count_done_tickets() { tracker search --status Done 2>/dev/null | awk 'END{print NR+0}'; }

# run_made_progress — 0 (true) if the Done count rose since the last checkpoint,
# advancing the watermark so each extension needs FRESH forward movement (AC2).
run_made_progress() {
    local cur
    cur="$(count_done_tickets)"; case "$cur" in ''|*[!0-9]*) cur=0 ;; esac
    [ "$DONE_AT_LAST_CHECK" -ge 0 ] || DONE_AT_LAST_CHECK="$cur"
    if [ "$cur" -gt "$DONE_AT_LAST_CHECK" ]; then DONE_AT_LAST_CHECK="$cur"; return 0; fi
    return 1
}

# spawn_budget_health — a one-line "x/y Done, spawns=N, cost=$Z" picture for the
# extend/drain runlog + operator push (AC2 Gesundheitsbild). Cost is summed from
# the SPAWN-USAGE cost_usd fields already in run.log; best-effort (n/a if absent).
spawn_budget_health() {
    local done total cost
    done="$(count_done_tickets)"
    total="$(tracker search 2>/dev/null | awk 'END{print NR+0}')"
    cost="$(awk -F'\t' '$2=="SPAWN-USAGE"{ if (match($6,/cost_usd=[0-9.]+/)) { s+=substr($6,RSTART+9,RLENGTH-9) } } END{ if (s>0) printf "$%.2f", s; else printf "n/a" }' "$ORCH_RUN_LOG" 2>/dev/null || echo 'n/a')"
    printf 'health=%s/%s Done, spawns=%s, cost=%s' "$done" "$total" "$SPAWNS_USED" "$cost"
}

# budget_event_push <text> — wake the operator over the ABS-455 push channel for a
# drain/auto-extend event (same suppress knob as the pause push).
budget_event_push() { [ "${ORCH_BUDGET_PUSH:-1}" = "0" ] && return 0; operator_push "$1"; }

# try_autoextend_budget — AC2: while the run shows progress, grow the soft cap in
# increments (never past the hard backstop) and wake the operator with a health
# picture instead of stopping. Returns 0 iff the budget was extended.
try_autoextend_budget() {
    [ "$ORCH_SPAWN_BUDGET_AUTOEXTEND" = "0" ] && return 1
    run_made_progress || return 1
    local inc hm room health
    inc=$(( ORCH_MAX_SPAWNS_PER_RUN * ORCH_SPAWN_BUDGET_AUTOEXTEND_PCT / 100 ))
    [ "$inc" -ge 1 ] || inc=1
    hm="$(spawn_budget_hard_max)"; room=$(( hm - SPAWNS_USED ))
    [ "$room" -gt 0 ] || return 1            # at the hard ceiling — cannot extend
    [ "$inc" -gt "$room" ] && inc="$room"    # never cross the hard backstop
    SPAWN_BUDGET=$(( SPAWN_BUDGET + inc ))
    SPAWN_BUDGET_EXTENDS=$(( SPAWN_BUDGET_EXTENDS + 1 ))
    health="$(spawn_budget_health)"
    runlog SPAWN-BUDGET-EXTEND - - - "increment=$inc used=$SPAWNS_USED soft_cap_now=$(( SPAWNS_USED + SPAWN_BUDGET )) hard_max=$hm extends=$SPAWN_BUDGET_EXTENDS $health"
    log "spawn budget auto-extended (+$inc, extend #$SPAWN_BUDGET_EXTENDS) — run is healthy: $health"
    budget_event_push "Orchestrator spawn budget auto-extended (+$inc, #$SPAWN_BUDGET_EXTENDS); run healthy: $health (PILOT-47)."
    return 0
}

# enter_drain_mode — AC1: reached the soft cap without an extension. Hold new
# intake; in-flight tickets finish their pipeline. Logs ONCE (in-memory flag; no
# new marker file under work/.orchestrator*, AC5).
enter_drain_mode() {
    [ "$DRAIN_MODE" -eq 1 ] && return 0
    DRAIN_MODE=1
    local health; health="$(spawn_budget_health)"
    runlog SPAWN-BUDGET-DRAIN - - - "soft cap reached (used=$SPAWNS_USED cap=$ORCH_MAX_SPAWNS_PER_RUN); DRAIN — no new intake, in-flight tickets finish (PILOT-47). $health"
    log "spawn budget soft cap reached; entering DRAIN — holding new intake, letting in-flight work finish (PILOT-47): $health"
    budget_event_push "Orchestrator spawn budget soft cap reached; DRAINING (no new intake, in-flight finishes): $health (PILOT-47)."
}

# block_for_ticket_spawn_cap <ticket> <to> <n> — AC3 loop-breaker: a single
# cyclically-respawning ticket is escalated to Needs PO Decision (mirrors
# block_for_iteration_cap); the run continues for every other ticket.
block_for_ticket_spawn_cap() {
    local ticket="$1" to="$2" n="$3"
    intent BLOCK-TICKET-SPAWN-CAP "$ticket" - "Needs PO Decision" "spawns=$n/$ORCH_MAX_SPAWNS_PER_TICKET at=$to"
    if [ "$MODE" = "live" ]; then
        tracker comment "$ticket" --kind gate-results --actor orchestrator \
            --body "Per-ticket spawn cap reached: this ticket consumed $n spawns this run (cap ORCH_MAX_SPAWNS_PER_TICKET=$ORCH_MAX_SPAWNS_PER_TICKET) — a cyclic respawn loop. Escalating to Needs PO Decision instead of respawning again; the run continues for other tickets (PILOT-47, ADR-A-0009 §5.4 loop-breaker)." \
            >/dev/null 2>&1 || log "ticket-spawn-cap comment failed on $ticket"
        tracker transition "$ticket" "Needs PO Decision" --actor orchestrator \
            --reason "per-ticket spawn cap $n/$ORCH_MAX_SPAWNS_PER_TICKET reached at $to (PILOT-47 loop-breaker)" \
            >/dev/null 2>&1 || log "ticket-spawn-cap transition failed on $ticket"
    fi
}

# --- v3 per-day spawn budget (ABS-74, spec §3.9) -------------------------------
# Recalibrated from real runs (PILOT-63 AC3). The original 200 was a sim-pin guess
# (~2 epics/day: 27 spawns per 3-story epic, 80-100 for a 10-story epic); measured
# runs overran it — Pilot 4 consumed 161, Pilot 5 consumed 251, so a SINGLE epic
# wave already exceeded the shipped default and hard-stopped a healthy run on
# 2026-07-25. Set to 400: above the largest observed single-run consumption (251)
# with headroom for a larger wave, and roughly the design-intent ~2 epics/day now
# that PILOT-63 AC1 stops charging worktree-provisioning non-spawns (62.5% of that
# 2026-07-25 pause was INTENT-SKIP-NOWORKTREE waste that no longer counts).
# Persisted as a dated ledger file under the state dir so it survives restarts
# and applies ACROSS runs (the per-run budget above still applies within one).
# 0 disables the daily cap.
ORCH_MAX_SPAWNS_PER_DAY="${ORCH_MAX_SPAWNS_PER_DAY:-400}"

daily_ledger() { echo "$ORCH_STATE_DIR/spawn-ledger-$(date -u +%Y%m%d)"; }

daily_budget_exhausted() {
    [ "$ORCH_MAX_SPAWNS_PER_DAY" -gt 0 ] || return 1
    local f
    f="$(daily_ledger)"
    [ -f "$f" ] || return 1
    [ "$(wc -l < "$f" | tr -d ' ')" -ge "$ORCH_MAX_SPAWNS_PER_DAY" ]
}

# record_daily_spawn <ticket> <role> <to> — one ledger line per spawn intent
# (dry-run included, mirroring the per-run budget's accounting).
record_daily_spawn() {
    echo "$(timestamp)${ORCH_RUN_ID:+ run_id=${ORCH_RUN_ID}} $1 $2 $3" >> "$(daily_ledger)" 2>/dev/null || true
    # ABS-312: single spawn chokepoint — count spawns emitted in the current
    # reconcile sweep so the liveness watchdog can tell "the queue is moving"
    # from "nothing spawned this sweep".
    SWEEP_SPAWN_COUNT=$((${SWEEP_SPAWN_COUNT:-0} + 1))
}

# rebuild_daily_ledger <ledger-file> — ABS-393 AC4: after a state-dir wipe zeroed
# today's spawn-ledger, reconstruct its line count from run.log so the daily budget
# brake is NOT silently re-opened (a wiped ledger reads as 0 spawns → the full daily
# budget reappears — the 2026-07-17 incident, where the operator hand-rebuilt 168
# entries from run.log). run.log is the append-only event stream that survives a
# state-dir wipe (default lives in the state dir, but is commonly pinned elsewhere via
# ORCH_RUN_LOG, as in the incident). Count today's INTENT-SPAWN events — emitted at the
# very chokepoint that appends a ledger line — and re-seed the ledger with that many
# placeholder lines so daily_budget_exhausted() (a wc -l) is accurate again. Prints the
# number of reconstructed entries (0 when run.log is unavailable — no worse than today).
rebuild_daily_ledger() {
    local ledger="$1" day n
    day="$(date -u +%Y-%m-%d)"
    if [ -z "${ORCH_RUN_LOG:-}" ] || [ ! -f "$ORCH_RUN_LOG" ]; then echo 0; return 0; fi
    # run.log is TSV: <timestamp>\t<event>\t<ticket>\t<role>\t<to>\t<note>. Count
    # today's INTENT-SPAWN rows (timestamp begins with the UTC date).
    n="$(awk -F'\t' -v d="$day" '$1 ~ ("^" d) && $2 == "INTENT-SPAWN" { c++ } END { print c + 0 }' "$ORCH_RUN_LOG" 2>/dev/null)"
    [ -n "$n" ] || n=0
    if [ "$n" -gt 0 ]; then
        : > "$ledger" 2>/dev/null || true
        local i=0
        while [ "$i" -lt "$n" ]; do
            echo "reconstructed-from-run.log $day" >> "$ledger" 2>/dev/null || true
            i=$((i + 1))
        done
    fi
    echo "$n"
}

pause_for_daily_budget() {
    local body
    body="orchestrator per-day spawn budget exhausted ($ORCH_MAX_SPAWNS_PER_DAY spawns today); paused, human review needed (ADR-A-0009 / ABS-74)."
    log "$body"
    notify "${ORCH_NOTIFY_TICKET:-}" "$body"
    budget_pause_push "$body"        # ABS-455 AC1: wake the operator, don't just comment
    BUDGET_HALT=1
    BUDGET_HALT_REASON="per-day spawn budget exhausted ($ORCH_MAX_SPAWNS_PER_DAY/day, ABS-74)"
}

# pause_for_budget — the HARD per-run backstop (PILOT-47 AC4): the soft cap drains
# rather than stopping, but the absolute ceiling (soft cap x
# ORCH_SPAWN_BUDGET_HARD_MULTIPLE) fail-closes to the ABS-455 exit-75 handshake.
pause_for_budget() {
    local body hm
    hm="$(spawn_budget_hard_max)"
    body="orchestrator HARD spawn backstop reached ($SPAWNS_USED spawns >= ${hm} = ${ORCH_SPAWN_BUDGET_HARD_MULTIPLE}x soft cap $ORCH_MAX_SPAWNS_PER_RUN); paused, human review needed (ADR-A-0009 / PILOT-47 fail-closed backstop)."
    log "$body"
    notify "${ORCH_NOTIFY_TICKET:-}" "$body"
    budget_pause_push "$body"        # ABS-455 AC1: wake the operator, don't just comment
    BUDGET_HALT=1
    BUDGET_HALT_REASON="hard spawn backstop reached ($SPAWNS_USED>=$hm, ${ORCH_SPAWN_BUDGET_HARD_MULTIPLE}x/run)"
}

# budget_pause_push <body> — ABS-455 AC1: wake the operator over the same push
# channel the standstill watchdog uses (a tracker comment is missable at 03:00).
# Best-effort, live-only, never fatal; ORCH_BUDGET_PUSH=0 suppresses it.
budget_pause_push() {
    [ "${ORCH_BUDGET_PUSH:-1}" = "0" ] && return 0
    operator_push "Orchestrator BUDGET PAUSE: $1 Restart after cost review (ADR-A-0009)."
}

# exit_budget_pause — ABS-455 AC1/AC3: the run-end chokepoint for a budget halt.
# Emits ONE unambiguous exit line (reason + residual state), bumps the persisted
# restart counter (the ADR-A-0009 review point — a supervisor's auto-restarts map
# 1:1 to these pauses, so the human sees the frequency and the cost gate is NOT
# auto-lifted), then exits with the DISTINCT handshake code so a supervisor wrapper
# can tell "budget pause, restart wanted" from a clean stop (0) or a crash.
exit_budget_pause() {
    local cf cnt reason
    cf="$ORCH_STATE_DIR/budget-restart-count"
    cnt="$(cat "$cf" 2>/dev/null || echo 0)"; case "$cnt" in ''|*[!0-9]*) cnt=0 ;; esac
    cnt=$((cnt + 1))
    echo "$cnt" > "$cf" 2>/dev/null || true
    reason="${BUDGET_HALT_REASON:-spawn budget exhausted}"
    log "BUDGET-PAUSE exit: $reason; run stopped for human cost review (ADR-A-0009). restart-count=$cnt exit-code=$ORCH_BUDGET_PAUSE_EXIT_CODE — a supervisor may restart on this code; the cost gate is NOT auto-lifted."
    runlog BUDGET-PAUSE - - - "reason=$reason restart-count=$cnt exit-code=$ORCH_BUDGET_PAUSE_EXIT_CODE"
    exit "$ORCH_BUDGET_PAUSE_EXIT_CODE"
}

# --- §5.1 In-memory pending set (cap-deferred events) -------------------------
# pending_add <ticket> <to> [from] — record a cap-deferred event (dedup on
# ticket|to). `from` rides along so a deferred ABS-116 backward-bounce keeps
# its direction across the retry (a bare "ticket|to" retry would NOOP it).
pending_add() {
    local key="$1|$2"
    case "$PENDING" in
        *"[$key|"*|*"[$key]"*) return 0 ;;
    esac
    PENDING="${PENDING}[$key|${3:-}]"
}

# drain_pending — retry cap-deferred events at the START of the cycle, ahead of
# newly polled events, until a concurrency slot is free (§5.1). Entries that
# still cannot run stay pending for the next cycle.
drain_pending() {
    [ -n "$PENDING" ] || return 0
    local entries key ticket to from rest drc
    # Extract "[ticket|to|from]" tokens (from may be empty; legacy 2-field
    # entries parse with from="").
    entries="$(printf '%s' "$PENDING" | grep -oE '\[[^]]+\]' | sed 's/^\[//; s/\]$//' || true)"
    PENDING=""   # rebuild as we go: re-defer whatever still can't run
    # ABS-246: split entries into positionals under a newline-only IFS, then
    # RESTORE the ambient IFS BEFORE dispatching — dispatch's callees
    # (depends_unmet et al.) rely on default word splitting; a leaked newline
    # IFS kept multi-ticket depends_on lists as ONE token, so the dep read
    # failed and the ticket parked as ':unreadable' in DEPENDS-WAIT forever
    # (consumer Befund BUSCH-58).
    local IFS_save="$IFS"
    IFS='
'
    # shellcheck disable=SC2086 — splitting on newlines is the point here
    set -- $entries
    IFS="$IFS_save"
    for key in "$@"; do
        ticket="${key%%|*}"
        rest="${key#*|}"
        to="${rest%%|*}"
        from=""
        case "$rest" in *"|"*) from="${rest#*|}" ;; esac
        drc=0
        dispatch "$ticket" "$to" "$from" || drc=$?
        if [ "$drc" -eq 3 ]; then
            pending_add "$ticket" "$to" "$from"
        fi
        if [ "$BUDGET_HALT" -eq 1 ]; then break; fi
    done
}

# --- §5.1 Reconciliation sweep (crash-safe net) ------------------------------
# reconcile — scan current ticket statuses via the adapter `search` and re-derive
# actionable state: any ticket resting in a *reconcilable* (transient work)
# status with no live lock is dispatched as if freshly observed. Runs every
# ORCH_RECONCILE_EVERY_N_CYCLES cycles and once on startup. The re-read guard
# (§5.4) + single-flight lock make a reconciliation dispatch a safe no-op when
# nothing was actually lost.
# =============================================================================
# ABS-406 wait-state-watchdog — degraded adapter-lane invariant sweep
# =============================================================================
# ABS-391 shipped a wait-state watchdog, but it is v3-backend-native (it queries
# work_item x pr_mirror x seat_spawn in Postgres), so on the jira/mock profiles —
# where the DAILY ABS work runs — the same silent wait-state mis-booking class
# stayed UNGUARDED (ABS-354: `Ready for Merge` with no branch/PR; ABS-333: `Docs`
# released before the human merge). This is the degraded PARITY port: same
# declarative rule table (ORCH_INVARIANT_RULES, mirroring WAIT_STATE_INVARIANTS),
# evaluated over the channels the adapter lane has — status from the sweep
# snapshot / `$TRACKER_CMD`, PR state from the forge seam (story_pr_state, i.e.
# glab on the live profile), seat evidence from the lock dir.
#
# DETECTION ONLY (AC5 / ADR-A-0004): a violation raises a LOUD, operator-visible
# signal (a `kind: invariant-violation` tracker comment, actor `watchdog`) and
# NOTHING else — it NEVER transitions, writes status, or merges. It is idempotent
# per status episode (AC6): one signal per violation episode, not per sweep.
# Fail-OPEN in the placeholder case (no $FORGE_CMD -> the forge-evidence rules
# cannot be judged, so the sweep no-ops), exactly like done_pr_gate/docs_pr_gate,
# so a profile with no forge configured is never spammed with false positives.

# invariant_last_kind_epoch <ticket-dump> <kind> — unix-seconds of the MOST
# RECENT comment whose header is `### <ts> | kind: <kind> | ...`. Empty when the
# ticket carries no such comment. Same header-anchored parse as
# last_po_park_epoch (reuse, not reinvent); BSD/GNU-safe via iso_to_epoch.
invariant_last_kind_epoch() {
    local at
    at="$(printf '%s\n' "$1" | awk -v kind="$2" '
        /^### / {
            n = split($0, f, " ")
            if (index($0, "kind: " kind " |") > 0) last = (n >= 2 ? f[2] : "")
        }
        END { if (last != "") print last }')"
    [ -n "$at" ] || return 0
    iso_to_epoch "$at"
}

# invariant_evidence_reason <evidence> <ticket> — prints the human "why" and
# returns 0 when the required evidence is MISSING (a violation), 1 when it holds
# (satisfied). Mirrors ABS-391's violationReason: `open-mr`/`mr-merged` are
# point-in-time forge state; `branch-or-seat` is satisfied by ANY live PR/branch
# (forge state != NONE) OR an open seat lock. Grace is applied by the caller (it
# needs the status age). Evidence-source parity: v3 reads pr_mirror; here the
# forge seam (story_pr_state) is the adapter-lane equivalent.
invariant_evidence_reason() {
    local evidence="$1" ticket="$2" state
    state="$(story_pr_state "$ticket")"; state="${state%%$'\t'*}"
    case "$evidence" in
        open-mr)
            [ "$state" = "OPEN" ] && return 1
            [ "$state" = "NONE" ] && { printf 'no PR mirrored for the item'; return 0; }
            printf 'mirrored PR is %s, not open' "$state"; return 0 ;;
        mr-merged)
            [ "$state" = "MERGED" ] && return 1
            [ "$state" = "NONE" ] && { printf 'no PR mirrored for the item'; return 0; }
            printf 'mirrored PR is %s, not merged' "$state"; return 0 ;;
        branch-or-seat)
            [ "$state" != "NONE" ] && return 1              # a PR/branch exists
            [ -d "$(lock_dir_for "$ticket")" ] && return 1  # an active seat
            printf 'no branch (PR) and no active seat'; return 0 ;;
    esac
    return 1
}

# invariant_sweep <rows> — called at the end of reconcile() with the sweep's
# ticket rows (id<TAB>type<TAB>status<TAB>title). For each ticket whose status
# matches a rule in the declarative table, judge the required evidence; on a
# NEW violation (idempotent per status episode) raise ONE loud operator-visible
# signal. DETECTION + AUDIT ONLY — never transitions (AC5).
invariant_sweep() {
    [ "$ORCH_INVARIANT_SWEEP" = "0" ] && return 0
    [ -n "$FORGE_CMD" ] || return 0    # no forge -> fail-open placeholder (parity with the PR gates)
    local rows="$1" id type status _title
    while IFS="$(printf '\t')" read -r id type status _title; do
        [ -n "$id" ] || continue
        local rule ev grace desc reason dump t_epoch v_epoch age
        # Look up THIS status in the shared declarative table (data, not logic).
        rule="$(printf '%s\n' "$ORCH_INVARIANT_RULES" | awk -F'|' -v s="$status" '$1==s{print;exit}')"
        [ -n "$rule" ] || continue
        ev="$(printf '%s' "$rule" | cut -d'|' -f2)"
        grace="$(printf '%s' "$rule" | cut -d'|' -f3)"
        desc="$(printf '%s' "$rule" | cut -d'|' -f4-)"
        reason="$(invariant_evidence_reason "$ev" "$id")" || continue   # rc 1 = satisfied
        dump="$(tracker get "$id" 2>/dev/null || true)"
        t_epoch="$(invariant_last_kind_epoch "$dump" transition-reason)"
        # branch-or-seat grace: a just-entered story legitimately has neither yet.
        if [ "$ev" = "branch-or-seat" ] && [ "${grace:-0}" -gt 0 ] && [ -n "$t_epoch" ]; then
            age=$(( $(now_epoch) - t_epoch ))
            [ "$age" -lt "$grace" ] && continue
        fi
        # Idempotency (AC6): skip when a violation was already recorded in THIS
        # status episode — a violation comment at/after the last transition.
        v_epoch="$(invariant_last_kind_epoch "$dump" invariant-violation)"
        if [ -n "$v_epoch" ] && { [ -z "$t_epoch" ] || [ "$v_epoch" -ge "$t_epoch" ]; }; then
            continue
        fi
        intent INVARIANT-VIOLATION "$id" watchdog "$status" "$reason ($desc)"
        [ "$MODE" = "live" ] || continue
        tracker comment "$id" --kind invariant-violation --actor watchdog \
            --body "WAIT-STATE-INVARIANT: $id rests in '$status' but $reason ($desc). Detection-only (ABS-406, degraded mirror of the ABS-391 v3 watchdog): the runner NEVER transitions or merges here — a human/TDM must correct the booking or supply the missing evidence (ADR-A-0004)." \
            >/dev/null 2>&1 || log "invariant-sweep comment failed on $id"
    done <<EOF
$rows
EOF
}

# =============================================================================
# ABS-312 liveness watchdog — full-standstill detection + one-shot self-heal
# =============================================================================
# STUCK-DETECT (ABS-116) is per-ticket and NOTIFY-only; backoffs are silent;
# parked tickets rest by design. None of them sees the WHOLE-runner state where
# 0 seats run while actionable work waits (the 2026-07-14/15 ~4h dead run: 2
# SPAWN-CRASH backoffs + 1 orphan + 1 blocked-park + 1 budget brake composed
# into a total standstill no single mechanism detected). This watchdog closes
# that gap: it runs at the END of every reconcile sweep, counts consecutive
# standstill sweeps, and at ORCH_STANDSTILL_SWEEPS self-heals ONCE per episode
# then escalates loudly. It never lifts a budget brake or a human gate.

standstill_state_file()   { echo "$ORCH_STATE_DIR/standstill-state"; }
standstill_episode_file() { echo "$ORCH_STATE_DIR/standstill-episode"; }

# status_is_human_gated <status> — a status a human (not the runner) must move.
# The watchdog names these as blockers but NEVER moves them (ADR-A-0004/0009).
status_is_human_gated() {
    case "$1" in
        "Ready for Merge"|"Ready for Human Acceptance"|"Ready for Epic Acceptance"|"Blocked") return 0 ;;
        *) return 1 ;;
    esac
}

# liveness_watchdog <rows> — called at the end of reconcile() with the sweep's
# ticket rows as $1 (id<TAB>type<TAB>status<TAB>title lines). Pure counting +
# bounded self-heal; all writes go through the existing MODE-guarded helpers.
liveness_watchdog() {
    [ "$ORCH_LIVENESS_WATCHDOG" = "0" ] && return 0
    local rows="$1" sfile efile count
    sfile="$(standstill_state_file)"; efile="$(standstill_episode_file)"

    # Progress this sweep? Live seats OR a spawn emitted -> the runner is alive.
    if [ "$(live_spawn_count)" -gt 0 ] || [ "${SWEEP_SPAWN_COUNT:-0}" -gt 0 ]; then
        rm -f "$sfile" "$efile" 2>/dev/null || true
        return 0
    fi

    # Classify the fenced tickets. `actionable` = a ticket reconcile would try to
    # dispatch (its status is reconcilable, or it is a labelled Backlog ticket)
    # yet nothing spawned — i.e. it is gated by a backoff / lock / budget. `gated`
    # = an open, non-terminal ticket a human must move (human gate). Terminal and
    # depends-waiting tickets are neither.
    local line id type status actionable=0 gated=0 gate_names="" first_epic=""
    while IFS="$(printf '\t')" read -r id type status _t; do
        [ -n "$id" ] || continue
        if is_reconcilable_status "$status" || reconcilable_labelled_backlog "$id" "$status"; then
            actionable=$((actionable + 1))
            [ -n "$first_epic" ] || first_epic="$(standstill_epic_for "$id")"
        elif status_is_human_gated "$status"; then
            gated=$((gated + 1))
            case "$gate_names" in *"$status"*) : ;; *) gate_names="${gate_names:+$gate_names, }$status" ;; esac
            [ -n "$first_epic" ] || first_epic="$(standstill_epic_for "$id")"
        fi
    done <<EOF
$rows
EOF

    # No actionable work AND nothing human-gated waiting -> not a standstill
    # (an all-Done board, or an empty fence). Clear and return.
    if [ "$actionable" -eq 0 ] && [ "$gated" -eq 0 ]; then
        rm -f "$sfile" "$efile" 2>/dev/null || true
        return 0
    fi

    # A standstill sweep: 0 seats, 0 spawns, and work is waiting. Count it.
    count="$(cat "$sfile" 2>/dev/null || echo 0)"
    case "$count" in ''|*[!0-9]*) count=0 ;; esac
    count=$((count + 1))
    echo "$count" > "$sfile" 2>/dev/null || true
    runlog STANDSTILL-SWEEP - - - "count=$count/$ORCH_STANDSTILL_SWEEPS actionable=$actionable human-gated=$gated"
    [ "$count" -ge "$ORCH_STANDSTILL_SWEEPS" ] || return 0

    # ABS-455 AC2: eliminate the standstill-WITHOUT-exit path. A standstill whose
    # actionable work is blocked SOLELY by an exhausted spawn budget is not a wait
    # state — no seat will EVER spawn this run, so holding forever in STANDSTILL-HELD
    # (the 2026-07-19 ~05:50 incident) is wrong. Convert it to a CLEAN budget-pause
    # exit: same push + exit line + restart counter as the dispatch-time brake, one
    # consistent behaviour (ADR-A-0009 review point preserved, gate NOT auto-lifted).
    # Human gates are NEVER converted — those legitimately wait and remain the loud,
    # distinguishable held-standstill below.
    # PILOT-47: only the HARD backstops (per-day ledger, absolute per-run ceiling)
    # convert a standstill to the exit-75 handshake. A plain SOFT-cap exhaustion is
    # drain, not a stop — its clean run-end is handled by the drain-settle check in
    # one_cycle (exit 0), so it must NOT be force-converted here.
    if [ "$actionable" -gt 0 ] && { daily_budget_exhausted || hard_backstop_reached; }; then
        runlog STANDSTILL-BUDGET-EXIT - - - "actionable=$actionable blocked by a HARD spawn backstop; clean budget-pause exit (ADR-A-0009), not a forever hold"
        if daily_budget_exhausted; then pause_for_daily_budget; else pause_for_budget; fi
        return 0
    fi

    # --- Threshold reached. Act ONCE per episode, in two ordered stages recorded
    #     in the episode marker (AC d — the credit is not re-granted per sweep):
    #       (stage 1) self-heal — reset expired/exhausted backoffs, reclaim
    #                 orphaned locks. Only when there is actionable (runner-owned)
    #                 work; human gates are NEVER touched.
    #       (stage 2) if still stuck (heal produced nothing, or already spent, or
    #                 nothing runner-owned to heal): escalate loudly.
    #     A genuine spawn/seat in a later sweep clears the marker (progress path
    #     above), ending the episode.
    local stage=""
    [ -f "$efile" ] && stage="$(cat "$efile" 2>/dev/null || true)"

    if [ "$stage" = "escalated" ]; then
        runlog STANDSTILL-HELD - - - "episode already healed+escalated; count=$count (awaiting operator / progress)"
        return 0
    fi

    if [ "$stage" != "healed" ] && [ "$actionable" -gt 0 ]; then
        local healed=0
        healed=$((healed + $(standstill_reset_backoffs)))
        healed=$((healed + $(standstill_reclaim_orphan_locks)))
        if [ "$healed" -gt 0 ]; then
            echo "healed" > "$efile" 2>/dev/null || true
            runlog STANDSTILL-SELFHEAL - - - "reset $healed blocker(s) (backoff/orphan-lock); one retry credit spent this episode"
            echo 0 > "$sfile" 2>/dev/null || true   # give the heal a sweep to spawn
            return 0
        fi
    fi

    # --- Still stuck (heal exhausted or nothing runner-owned to heal). Escalate
    #     loudly — INTENT-STANDSTILL, an epic comment naming the blockers, and an
    #     operator push. Budget brakes / human gates are NAMED, never lifted.
    echo "escalated" > "$efile" 2>/dev/null || true
    local blockers=""
    [ "$actionable" -gt 0 ] && blockers="${actionable} actionable ticket(s) not spawning (budget/backoff — NOT auto-lifted)"
    [ "$gated" -gt 0 ] && blockers="${blockers:+$blockers; }${gated} behind human gate(s): ${gate_names}"
    runlog INTENT-STANDSTILL - - - "0 seats, 0 spawns for ${count} sweeps; blockers: ${blockers}"
    intent STANDSTILL - - - "$blockers"
    if [ -n "$first_epic" ]; then
        notify "$first_epic" "STANDSTILL (orchestrator): 0 live seats and 0 spawns for ${count} sweeps while work waits — ${blockers}. The watchdog does NOT lift budget brakes (ADR-A-0009) or human gates; operator action needed."
    fi
    standstill_operator_push "$blockers"
    return 0
}

# standstill_epic_for <ticket> — the ticket's parent epic id (for the escalation
# comment), or the ticket itself when it has no parent.
standstill_epic_for() {
    local p
    p="$(fm_field "$(tracker get "$1" 2>/dev/null || true)" parent)"
    [ -n "$p" ] && printf '%s' "$p" || printf '%s' "$1"
}

# standstill_reset_backoffs — clear a backoff marker that is EXPIRED (its delay
# has elapsed) OR EXHAUSTED (grown to ORCH_BACKOFF_MAX_SECONDS — the retry pacing
# has run its course and the ticket would otherwise wait out a full max delay
# with no seat alive). Echoes the count reset. A fresh, still-ramping backoff
# (delay < max and not yet elapsed) is left alone so ordinary crash-backoff
# pacing is untouched outside a standstill. Format: status<TAB>until<TAB>delay.
standstill_reset_backoffs() {
    local f n=0 now until delay
    now="$(now_epoch)"
    for f in "$ORCH_STATE_DIR"/backoff-*; do
        [ -e "$f" ] || continue
        until="$(cut -f2 "$f" 2>/dev/null | head -1 || echo 0)"
        delay="$(cut -f3 "$f" 2>/dev/null | head -1 || echo 0)"
        case "$until" in ''|*[!0-9]*) until=0 ;; esac
        case "$delay" in ''|*[!0-9]*) delay=0 ;; esac
        if [ "$now" -ge "$until" ] || [ "$delay" -ge "$ORCH_BACKOFF_MAX_SECONDS" ]; then
            rm -f "$f" 2>/dev/null && n=$((n + 1))
        fi
    done
    echo "$n"
}

# standstill_reclaim_orphan_locks — release seat locks with no live process (an
# orphan from a crashed/killed runner) so reconcile re-derives the ticket next
# sweep. Echoes the count reclaimed. This is the bounded, standstill-only
# "reroute a ticket with no owning seat" action (a deliberate, narrow exception
# to ABS-116's never-route rule — it only fires inside a confirmed standstill).
standstill_reclaim_orphan_locks() {
    local d id n=0
    for d in "$LOCKS_DIR"/*; do
        [ -d "$d" ] || continue
        id="$(basename "$d")"
        # A lock older than the TTL has no live owner (same criterion reconcile
        # uses); reclaim it. live_spawn_count()==0 here, so any lock is an orphan.
        release_lock "$id" 2>/dev/null && n=$((n + 1))
    done
    echo "$n"
}

# operator_push <message> — wake the operator over the push channel (ABS-455).
# macOS `display dialog` (operator convention — a banner is missable), best
# effort and live-only, never fatal. No-op off-macOS or when osascript is absent.
# Shared by the standstill watchdog and the budget-pause exit.
#
# BACKGROUNDED (`&`, fds detached to /dev/null): `display dialog` is a MODAL that
# blocks until the operator clicks OK. A foreground call would stall the run at the
# dialog — for a budget pause that means never reaching the clean handshake exit
# (ABS-455 AC1/AC3), and it hangs command-substitution test harnesses. The wake is
# fire-and-forget: the dialog stays up until dismissed, the run proceeds/exits.
operator_push() {
    [ "$MODE" = "live" ] || return 0
    command -v osascript >/dev/null 2>&1 || return 0
    osascript -e 'display dialog "'"$(printf '%s' "$1" | tr '"' "'")"'" buttons {"OK"} with title "Orchestrator"' >/dev/null 2>&1 &
}

# standstill_operator_push <blockers> — wake the operator on a full standstill.
standstill_operator_push() {
    [ "${ORCH_STANDSTILL_PUSH:-1}" = "0" ] && return 0
    operator_push "Orchestrator STANDSTILL: 0 live seats, work waiting. $1"
}

# =============================================================================
# PILOT-42 — cadence-triggered TDM ops-sweep (time-driven, ticket-overarching)
# =============================================================================
# The recurring stuck-classes an operator resolves by hand (worktree-HEAD trap,
# missed dep-release, NOMOVE-with-finished-work, stale locks/markers, …) have a
# mechanical signature. Once per ORCH_OPS_SWEEP_INTERVAL the reconcile sweep spawns
# ONE TDM seat (reason 'ops-sweep') to DIAGNOSE them. PHASE 0 = SHADOW: the seat
# writes a report and executes NOTHING (no transition, no comment, no git write, no
# lock/marker change) — the report is validated against the operator's real
# interventions before any tier is activated. Plan + change-contract:
#   work/improvement-proposals/2026-07-25-hourly-ops-sweep-janitor.md
# Cadence state marker (ABS-522 inventory: docs/sop/ORCHESTRATOR_STATE_MARKERS.md).
ops_sweep_last_file() { echo "$ORCH_STATE_DIR/ops-sweep-last"; }

# PILOT-73 — durable ops-sweep report store. In Phase 0 (shadow) the sweep executes
# NOTHING; the report IS its only work product, so the Phase-0 acceptance ("does the
# report cover the operator's real interventions?") is impossible unless the report
# outlives both the next sweep and the runner exit. run_spawn_cmd's stdout capture
# lives under packets/ and is deleted on the success path (ABS-265) — the exact
# evidence loss PILOT-73 fixes. This store is NOT under packets/ (never swept clean).
# ABS-522 inventory: docs/sop/ORCHESTRATOR_STATE_MARKERS.md.
ops_sweep_report_dir() { echo "$ORCH_STATE_DIR/ops-sweep-reports"; }

# ops_sweep_result_text <spawn-stdout> — the seat's final message: the decoded JSON
# `result` field (default Claude binding), or the raw stdout when a stub printed no
# JSON envelope. Unlike extract_handoff_from_result this does NOT require the word
# "handoff" — a Phase-0 sweep emits bare findings lines, not a handoff block.
ops_sweep_result_text() {
    local raw
    raw="$(_json_result_field "$1")"
    if [ -n "$raw" ]; then printf '%s' "$raw" | json_unescape; else printf '%s' "$1"; fi
}

# ops_sweep_persist_report <spawn-stdout-file> — store the report durably and emit
# ONE greppable runlog summary line (AC1/AC2). Findings are counted per class from the
# finding-line shape "<class> <ticket|-> <evidence> <suggestion>" that the sensors emit
# and the Phase-0 packet requests — class-agnostic, so a new sensor class needs no edit
# here. AC3: a sweep that finds nothing (or produced no output) says so EXPLICITLY, so
# silence never reads as "did not run". Never fails the caller.
ops_sweep_persist_report() {
    local src="$1" dir report body sum total counts
    dir="$(ops_sweep_report_dir)"
    mkdir -p "$dir" 2>/dev/null || true
    report="$dir/ops-sweep.$(date -u +%Y%m%dT%H%M%SZ).$$.txt"
    body="$(ops_sweep_result_text "$(cat "$src" 2>/dev/null)")"
    printf '%s\n' "$body" > "$report" 2>/dev/null || true
    sum="$(printf '%s\n' "$body" | awk '
        $1 ~ /^[A-Za-z][A-Za-z0-9-]+$/ && ($2 ~ /^[A-Za-z][A-Za-z0-9]*-[0-9]+$/ || $2 == "-") {
            c[$1]++; total++
        }
        END { out=""; for (k in c) out = out " " k "=" c[k]; printf "%d%s", total+0, out }
    ')"
    total="${sum%% *}"
    case "$sum" in *" "*) counts=" ${sum#* }" ;; *) counts="" ;; esac
    if [ -z "$body" ]; then
        runlog OPS-SWEEP-REPORT "$ORCH_OPS_SWEEP_TICKET" "$ORCH_OPS_SWEEP_ROLE" - "total=0 report-empty (seat produced no output) file=$report"
        log "ops-sweep report: EMPTY — seat produced no output -> $report"
    elif [ "${total:-0}" -eq 0 ] 2>/dev/null; then
        runlog OPS-SWEEP-REPORT "$ORCH_OPS_SWEEP_TICKET" "$ORCH_OPS_SWEEP_ROLE" - "total=0 no-findings (all sensors clean) file=$report"
        log "ops-sweep report: no findings (all sensors clean) -> $report"
    else
        runlog OPS-SWEEP-REPORT "$ORCH_OPS_SWEEP_TICKET" "$ORCH_OPS_SWEEP_ROLE" - "total=$total$counts file=$report"
        log "ops-sweep report: $total finding(s)$counts -> $report"
    fi
}

# ops_sweep_due — 0 (true) when >= ORCH_OPS_SWEEP_INTERVAL elapsed since the last
# sweep. On the FIRST call of a run (marker absent) it SEEDS the marker to now and
# returns 1 (not due) — so a fresh run waits a full interval before its first sweep
# instead of firing on startup. Uses now_epoch (ORCH_NOW-injectable for tests).
ops_sweep_due() {
    local f last now
    f="$(ops_sweep_last_file)"
    now="$(now_epoch)"
    if [ ! -f "$f" ]; then
        printf '%s\n' "$now" > "$f" 2>/dev/null || true
        return 1
    fi
    last="$(cat "$f" 2>/dev/null || echo 0)"
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
    [ "$(( now - last ))" -ge "$ORCH_OPS_SWEEP_INTERVAL" ]
}

# ops_sweep_phase — derive "<phase> <normalized-tiers>" from ORCH_OPS_SWEEP_TIERS
# (PILOT-43). Empty/unset => "0 -" (Phase-0 shadow, the default). Any A (no B) =>
# "1 A"; any B => "2 <tiers>" (Phase 2 is Tier A+B — B is the higher tier). Input is
# lower/upper tolerant; letters other than A/B are dropped, so a typo degrades to
# shadow rather than mis-activating. Pure; used by the intent line and the packet.
ops_sweep_phase() {
    local t
    t="$(printf '%s' "${ORCH_OPS_SWEEP_TIERS:-}" | tr 'ab' 'AB' | tr -cd 'AB')"
    case "$t" in
        *B*) printf '2 %s\n' "$t" ;;
        *A*) printf '1 %s\n' "$t" ;;
        *)   printf '0 -\n' ;;
    esac
}

# ops_sweep_packet <phase> <tiers> — the trigger written to the seat's stdin packet.
# The duties live in the TDM role definition's "Ops-Sweep" section (DRY); this names
# the reason, the active phase/tiers and the runaway cap. PHASE 0 (default) emits the
# unchanged shadow constraint — report only. PHASE 1/2 hands the seat the ACTIVE tiers
# and re-states the top prohibitions inline (defence in depth); the full tier protocol,
# evidence+idempotency rules and fail-closed checks stay in the role definition.
ops_sweep_packet() {
    local phase="${1:-0}" tiers="${2:--}"
    if [ "$phase" = "0" ]; then
        cat <<'PKT'
=== OPS-SWEEP (reason: ops-sweep, phase: 0 / shadow) ===
You are spawned as a TIME-TRIGGERED ops-sweep, not tied to any one ticket. Follow
the "Ops-Sweep (cadence-triggered janitor)" section of your role definition.

PHASE 0 — SHADOW: diagnosis and REPORT ONLY. Execute NO action: no transition, no
ticket comment, no git write (no commit/push/branch/worktree change), no lock or
marker change. Run the read-only sensors (scripts/ops-sweep-sensors.sh if present,
else diagnose the classes you can observe read-only), then emit your findings as
your final message — one line per finding: <class> <ticket|-> <evidence> <proposal>.
Report what an operator WOULD need to do; do not do it.
PKT
        return 0
    fi
    cat <<PKT
=== OPS-SWEEP (reason: ops-sweep, phase: $phase / tiers: $tiers) ===
You are spawned as a TIME-TRIGGERED ops-sweep, not tied to any one ticket. Follow
the "Ops-Sweep (cadence-triggered janitor)" section of your role definition.

ACTIVE TIERS: $tiers  (A = mechanical/reversible worktree-lock-marker hygiene;
B = evidence-bound tracker resolution: dep-release + NOMOVE completion). Tiers NOT
listed here — and Tier C/D always — remain REPORT-ONLY: diagnose and escalate, never act.

MANDATORY for EVERY action: first run the read-only sensors, act ONLY on a finding the
sensor backs with evidence ("what the sensor does not see does not exist"); then post an
evidence comment (class + sensor evidence + action) AND write the idempotency marker so
the same finding is never fixed twice — skip any finding already carrying its marker.

HARD PROHIBITIONS (fail-closed — on any doubt, escalate instead of acting): no merge or
push to a protected branch (the PILOT-11 chokepoint binds this seat too); no --force; no
delete without a backup; no force-transition without sensor evidence; no intervention on a
ticket that has a LIVE seat. Never release a Blocked whose dependency head is NOT in the
target branch. RUNAWAY CAP: more than $ORCH_OPS_SWEEP_MAX_PER_CLASS findings of one class in
this sweep => escalate the class (human attention), do NOT apply that many actions.
PKT
}

# ops_sweep_dispatch — cadence gate + spawn, called once at the end of reconcile().
# Guardrails (proposal §2): knob 0 => off/byte-identical; never while the run is
# unhealthy (kill-switch / outage-probe / budget drain — don't fight recovery);
# never parallel to itself (own single-flight lock via the locks/ class); its own
# small per-run budget, separate from the story/daily spawn budget.
ops_sweep_dispatch() {
    # Knob OFF => return before ANY observable side effect (AC1: byte-identical).
    [ "${ORCH_OPS_SWEEP_INTERVAL:-0}" -gt 0 ] 2>/dev/null || return 0
    # Never fight the recovery mechanics: skip while the run is unhealthy.
    [ -f "$ORCH_STOP_FILE" ] && return 0
    [ "$BUDGET_HALT" -eq 1 ] && return 0
    [ -f "$(outage_file)" ] && return 0
    [ -f "$(probe_inflight_file)" ] && return 0
    # Own small budget, separate from the story/daily spawn budget.
    [ "${OPS_SWEEP_COUNT:-0}" -lt "$ORCH_OPS_SWEEP_MAX_PER_RUN" ] 2>/dev/null || return 0
    # Cadence gate (seeds the marker + waits a full interval on the first run).
    ops_sweep_due || return 0
    # Own single-flight lock — never parallel to itself. locks/ class => no new marker.
    if ! acquire_lock "$ORCH_OPS_SWEEP_TICKET"; then
        intent SKIP-LOCKED "$ORCH_OPS_SWEEP_TICKET" "$ORCH_OPS_SWEEP_ROLE" ops-sweep
        return 0
    fi
    # Admission: stamp cadence + count NOW so a long-running seat is not re-dispatched
    # next sweep (the lock covers the in-flight window; the marker covers after release).
    printf '%s\n' "$(now_epoch)" > "$(ops_sweep_last_file)" 2>/dev/null || true
    OPS_SWEEP_COUNT=$(( ${OPS_SWEEP_COUNT:-0} + 1 ))
    # PILOT-78: the ops-sweep has a constant ticket/role/attempt, so its
    # run_id:ticket:role:attempt would collide across every dispatch of a run.
    # Feed the per-run monotonic dispatch count into seat_spawn_id as SPAWN_SEQ so
    # each dispatch gets a unique spawn_id (…:1#1, …:1#2). `local` (bash dynamic
    # scoping) keeps it visible to run_spawn_cmd/seat_spawn_id below — including the
    # async subshell that inherits it — yet confined to this function, so a normal
    # ticket dispatch in a later sweep never inherits a stale seq.
    local SPAWN_SEQ="$OPS_SWEEP_COUNT"
    # PILOT-43: phase/tiers derived from ORCH_OPS_SWEEP_TIERS ("0 -" = shadow default).
    local sweep_pt sweep_phase sweep_tiers
    sweep_pt="$(ops_sweep_phase)"
    sweep_phase="${sweep_pt%% *}"; sweep_tiers="${sweep_pt##* }"
    intent OPS-SWEEP "$ORCH_OPS_SWEEP_TICKET" "$ORCH_OPS_SWEEP_ROLE" ops-sweep "phase=$sweep_phase tiers=$sweep_tiers interval=${ORCH_OPS_SWEEP_INTERVAL}s"

    if [ "$MODE" = "dry-run" ]; then
        release_lock "$ORCH_OPS_SWEEP_TICKET"
        return 0
    fi

    local pf
    pf="$PACKETS_DIR/$ORCH_OPS_SWEEP_TICKET.$(date -u +%Y%m%dT%H%M%SZ).$$.txt"
    mkdir -p "$PACKETS_DIR" 2>/dev/null || true
    ops_sweep_packet "$sweep_phase" "$sweep_tiers" > "$pf" 2>/dev/null || true

    # Reuse the raw spawn seam (run_spawn_cmd) directly — like the salvage/repair
    # resume paths — NOT the ticket-centric spawn_dispatch/live_spawn chain: there is
    # no ticket to transition and no handoff to apply back. Async so the reconcile
    # loop never blocks on the seat; the lock is held for the subshell's lifetime and
    # released there (mirrors spawn_dispatch's async release). SPAWN_CWD is cleared so
    # the read-only seat resolves to the main checkout (no worktree for this key).
    if [ "$ORCH_ASYNC_SPAWNS" = "1" ]; then
        (
            SPAWN_CWD=""
            run_spawn_cmd "$ORCH_OPS_SWEEP_ROLE" "$ORCH_OPS_SWEEP_TICKET" "$pf" "" >/dev/null 2>&1 || true
            rm -f "$pf" "$pf".* 2>/dev/null || true
            release_lock "$ORCH_OPS_SWEEP_TICKET"
        ) &
        SPAWN_PIDS="$SPAWN_PIDS $!"
        return 0
    fi
    SPAWN_CWD=""
    run_spawn_cmd "$ORCH_OPS_SWEEP_ROLE" "$ORCH_OPS_SWEEP_TICKET" "$pf" "" >/dev/null 2>&1 || true
    rm -f "$pf" "$pf".* 2>/dev/null || true
    release_lock "$ORCH_OPS_SWEEP_TICKET"
    return 0
}

reconcile() {
    log "reconciliation sweep (cycle $CYCLE)"
    SWEEP_SPAWN_COUNT=0   # ABS-312: reset the per-sweep spawn counter
    # ABS-117: one hash per sweep (ticket constraint) — an operator's mid-run
    # settings/agent-def edit reaches fresh spawns immediately, so the stamp
    # must notice it without a runner restart. Unchanged inputs = same value.
    refresh_config_generation
    # ABS-75: the follow-up watcher runs FIRST, before join_check_epic below —
    # an unprocessed follow-up must be seen (and, once answered, cleared) by
    # the watcher before JOIN re-evaluates the same epic in this sweep (spec
    # §3.6 quiescence ordering: watcher -> JOIN).
    followup_watcher
    # ABS-296: dependency-caused Blocked entries return to their BLOCKED-FROM
    # origin once all depends_on are Done. Runs after followup_watcher (so a
    # follow-up filed in the same cycle is visible first) and before the per-
    # ticket dispatch loop (so a just-released ticket is re-dispatched cleanly
    # in this sweep without waiting a full cadence).
    blocked_auto_release_sweep
    # ABS-224 AC3 / PILOT-3: drift check — local main ahead of the ACTIVE push
    # remote means a seat may have bypassed the pre-commit guard and committed to
    # local main. WARN-only; runs outside the per-ticket loop. Throttled to one
    # WARN per run (was one intent line per sweep vs stale origin — ABS-493 spam).
    check_local_main_drift
    local line id type status drc reconcile_rows
    # search with no filter lists all tickets: id<TAB>type<TAB>status<TAB>title.
    # Captured once so the ABS-312 liveness watchdog reuses the same snapshot.
    reconcile_rows="$(tracker search 2>/dev/null || true)"
    # ABS-261: offer free slots in canonical-priority order (hotfix first) instead
    # of the adapter's arrival/key order, BEFORE the per-ticket dispatch loop hits
    # the concurrency cap. Kill-switch OFF (=0) restores the legacy order verbatim.
    if [ "$ORCH_PRIORITY_DISPATCH" != "0" ]; then
        reconcile_rows="$(printf '%s\n' "$reconcile_rows" | prioritize_rows)"
    fi
    while IFS="$(printf '\t')" read -r id type status _title; do
        [ -n "$id" ] || continue
        # ABS-62: mechanical stall detection runs on every ticket in the sweep
        # (it inspects resting Backlog tickets the reconcilable-status filter
        # below deliberately skips). A fired rule raises "Needs PO Decision",
        # which the next sweep/poll routes to a fresh PO-Agent (ADR-A-0009).
        check_stall_rules "$id" "$type" "$status"
        # ABS-116: the stuck detector also runs on every ticket — it filters
        # its own candidates (unowned resting statuses) and clears finished
        # episodes, so it must see non-candidates too.
        check_stuck "$id" "$status"
        # ABS-224 AC6: claim-protocol WARN — a ticket working under an active
        # seat lock but still resting in "Ready for Development". Runs before the
        # lock-skip continue below (mirrors check_stuck).
        check_claim_protocol "$id" "$status"
        # ABS-295 CRASH-REPAIR: route orphaned In Progress tickets back to their
        # origin station when the runner's own crash record proves the seat is
        # dead. It filters its own candidates (In Progress + own SPAWN-CRASH
        # marker + no live lock + crash age > threshold + own instance id) and
        # returns 1 on every non-candidate. If repair fires, skip dispatch for
        # the stale In Progress status.
        if check_crash_repair "$id" "$status"; then continue; fi
        # ABS-270: release a story docs_pr_gate parked at the human-owned merge
        # gate once its PR is merged (-> Docs, tech-writer, Done). Must run HERE,
        # before the reconcilable-status filter: `Ready for Merge` is deliberately
        # not reconcilable (that is what makes the rest free), so dispatch never
        # re-derives it. No-op for every other ticket.
        merge_wait_release "$id" "$status" || true
        # PILOT-18: a story resting at the human merge gate whose OPEN MR was
        # CONFLICTED by a foreign merge (migration-number collision !159 after
        # !158, v3-pilot #3) is invisible to the merged-ness release above — it
        # checks ancestry only, never mergeability. Redirect it back to Merging
        # with a resolution recipe so a seat rebases + resolves. No-op on a clean
        # or merged MR (AC2/AC4); once-per-conflict fingerprint guard (AC3).
        merge_conflict_redirect "$id" "$status" || true
        # ABS-454: self-heal a story resting at `Ready for Merge` with NO MR (the
        # ABS-416 restart case: push + MR lost, so the ticket is already parked
        # here and dispatch never re-derives it — `Ready for Merge` is not
        # reconcilable). Redirects it back to Merging so the RTE respawn creates the
        # MR. No-op on an OPEN merge-wait park (ABS-270) or a MERGED PR, and on
        # every non-`Ready for Merge` ticket.
        ready_for_merge_mr_gate "$id" "$status" || true
        # PILOT-20: a story parked at `Ready for Merge` whose PR is later DECLINED /
        # closed-without-merge can never be released by merge_wait_release (fires only
        # on MERGED) nor self-healed by ready_for_merge_mr_gate (fires only when NO MR
        # exists — a declined PR still exists). Without this it rests silently forever.
        # Emits ONE human notification naming the declined PR; idempotent, no-op on an
        # OPEN merge-wait park (ABS-270) or a MERGED PR, and on every other ticket.
        merge_wait_declined_gate "$id" "$status" || true
        # v3 JOIN rule (ABS-73): epics resting in "Stories In Flight" advance
        # when all children are Done. Runs AFTER the follow-up watcher pass at
        # the top of the sweep (quiescence ordering, spec §3.6).
        if [ "$type" = "epic" ] && [ "$status" = "Stories In Flight" ]; then
            join_check_epic "$id"
        fi
        # ABS-208: on every sweep, pull the epic's start label onto any non-Done
        # child still missing it (restart/laggard catch-up, AC2). Skips terminal
        # epics — their children are Done, so nothing to propagate. Runs before
        # the reconcilable-status filter below so a labelled epic RESTING in any
        # non-terminal status (e.g. Stories In Flight) is still swept.
        if [ "$type" = "epic" ] && [ "$status" != "Epic Done" ]; then
            propagate_start_label_to_children "$id"
        fi
        # Only re-derive transient work states (see is_reconcilable_status);
        # skip resting entry/terminal/human states so reconcile never mass-spawns
        # a backlog or loops on Done/Blocked tickets (§5.1). The one exception is
        # a Backlog ticket the human labelled orchestrator-ready (ABS-101), which
        # reconcile re-derives so a runtime label add is picked up without restart.
        is_reconcilable_status "$status" || reconcilable_labelled_backlog "$id" "$status" || continue
        # Skip if a FRESH spawn is already in flight for this ticket. A lock
        # older than ORCH_LOCK_TTL is an orphan from a crashed/killed runner
        # (e.g. the session interrupted mid-spawn); reclaim it so reconcile
        # re-derives the dispatch instead of deadlocking forever. Previously the
        # TTL reclaim lived only in acquire_lock, which a locked ticket never
        # reached from here — an orphaned lock froze the ticket permanently
        # (ABS-150, ABS-129 live run).
        if [ -d "$(lock_dir_for "$id")" ]; then
            lock_age="$(lock_age_for "$id" || echo 0)"
            if [ "$lock_age" -lt "$ORCH_LOCK_TTL" ]; then continue; fi
            log "reconcile: reclaiming stale lock for $id (age ${lock_age}s >= ${ORCH_LOCK_TTL}s)"
            release_lock "$id"
        fi
        drc=0
        dispatch "$id" "$status" || drc=$?
        if [ "$drc" -eq 3 ]; then
            pending_add "$id" "$status"
        fi
        if [ "$BUDGET_HALT" -eq 1 ]; then break; fi
    done <<EOF
$reconcile_rows
EOF
    # ABS-312: after the sweep, judge the WHOLE-runner aliveness against the same
    # snapshot (0 seats + 0 spawns + actionable work waiting => standstill).
    liveness_watchdog "$reconcile_rows"
    # ABS-406: degraded wait-state invariant check over the same snapshot —
    # detection-only parity of the ABS-391 v3 watchdog on the jira/mock lane.
    invariant_sweep "$reconcile_rows"
    # PILOT-42: time-triggered ops-sweep — runs LAST, outside the per-ticket loop.
    # Knob 0 => no-op (byte-identical); otherwise cadence-gated + fully self-guarded.
    ops_sweep_dispatch
}

# =============================================================================
# dispatch(event) — §2 mapping applied to one parsed event
# =============================================================================
# Returns 0 normally; returns 3 to signal "deferred by concurrency cap" so the
# caller re-queues into the pending set (§5.1).
# $3 (from, optional): the event's source status. Only process_events passes it
# (reconcile derives from RESTING tickets — no direction exists there). It
# feeds the ABS-116 backward-bounce override below and nothing else.
dispatch() {
    local ticket="$1" to="$2" from="${3:-}"
    # ABS-324: clear any bundle roster left by a prior dispatch; only a fastlane
    # bundle LEAD at Ready for Development re-sets it below (read in do_spawn_action).
    FL_BUNDLE_ROSTER=""
    # ABS-111 A2: entering Merging/Done means acceptance passed — the resume
    # scope ("same session until acceptance", ADR-A-0002 interpretation) ends
    # here; stored sessions for the ticket are dropped.
    case "$to" in
        "Merging"|"Done") clear_sessions "$ticket" ;;
    esac
    # Backlog opt-in gate (ABS-101): the PO prioritization sweep only picks up a
    # Backlog ticket the human released via $ORCH_START_LABEL. An unlabelled
    # ticket rests untouched — the fail-safe default that keeps a migrated,
    # un-groomed backlog inert until each ticket is explicitly labelled.
    if [ "$to" = "Backlog" ] && ! orchestrator_ready "$ticket"; then
        # D12: emit the skip intent once per ticket per run — every reconcile
        # sweep re-derives resting Backlog tickets and used to spam one line
        # per ticket per sweep (run 1). The run.log keeps every occurrence.
        case "$SKIPPED_UNLABELLED" in
            *"[$ticket]"*)
                runlog INTENT-SKIP-UNLABELLED "$ticket" - "$to" throttled
                return 0 ;;
        esac
        SKIPPED_UNLABELLED="${SKIPPED_UNLABELLED}[$ticket]"
        intent SKIP-UNLABELLED "$ticket" - "$to"
        return 0
    fi
    # PILOT-22 delegation hard-stop (defense in depth for the ABS-492 double-
    # dispatch): a ticket carrying a machine-readable delegation marker is owned by
    # an EXTERNAL system of record and must NEVER spawn an orchestrator seat,
    # however it reached a dispatchable status. The orphan-heal runs BELOW the
    # Backlog opt-in gate, so a delegated ticket can arrive at Ready for Development
    # without ever passing the gate — re-check here so there is no below-the-gate
    # dispatch path. Scoped to the implementer entry (Ready for Development): a
    # delegation marker never appears on an in-pipeline factory ticket, so this
    # touches no legitimate dispatch. Throttled once per ticket per run (D12).
    if [ "$to" = "Ready for Development" ] \
        && ticket_is_delegated "$(tracker get "$ticket" 2>/dev/null || true)"; then
        case "$SKIPPED_DELEGATED" in
            *"[$ticket]"*)
                runlog INTENT-SKIP-DELEGATED "$ticket" - "$to" throttled
                return 0 ;;
        esac
        SKIPPED_DELEGATED="${SKIPPED_DELEGATED}[$ticket]"
        intent SKIP-DELEGATED "$ticket" - "$to"
        return 0
    fi
    # ABS-304: a labelled Backlog child of an epic still in the epic pipeline
    # before Stories In Flight is architect-released, not PO-released — a po-agent
    # here can only score-and-park (guaranteed HANDOFF-NOMOVE). Suppress the spawn
    # and emit SKIP-EPIC-CHILD, throttled once per ticket per run (like
    # SKIP-UNLABELLED); no seat spawns, so no no-move/escalation budget is charged.
    if [ "$to" = "Backlog" ]; then
        local _epic_parent
        if _epic_parent="$(backlog_epic_child_parent "$ticket")"; then
            case "$SKIPPED_EPIC_CHILD" in
                *"[$ticket]"*)
                    runlog INTENT-SKIP-EPIC-CHILD "$ticket" - "$to" "throttled parent=$_epic_parent"
                    return 0 ;;
            esac
            SKIPPED_EPIC_CHILD="${SKIPPED_EPIC_CHILD}[$ticket]"
            intent SKIP-EPIC-CHILD "$ticket" - "$to" "parent=$_epic_parent"
            return 0
        fi
    fi
    # Intake classification (v3.1, ABS-104): classify a top-level Backlog ticket
    # and record its routing head. Additive — the existing Backlog dispatch below
    # (SPAWN po-agent = the v3.0 PO-Triage head) still runs unchanged, so a
    # labelled parentless Backlog ticket keeps spawning po-agent.
    if [ "$to" = "Backlog" ]; then
        route_intake "$ticket"
    fi
    # ABS-325 fastlane EJECTION (Auswurf statt Parkung): a `lane=fastlane` ticket
    # that tripped a safety trigger (red tests from iteration >=2, diff-budget
    # overrun, protected path touched, or a firing station guard) is DEMOTED to
    # the normal lane and resumed at Ready for Development — never Blocked, never a
    # human-wait. Placed BEFORE station_guard so a fastlane guard-fire EJECTS
    # instead of being redirected in-lane; an ejected ticket (now lane=normal)
    # falls through to the full chain. Kill-switch ORCH_FASTLANE_EJECT=0.
    if fastlane_eject_gate "$ticket" "$to"; then
        return 0
    fi
    # ABS-136 station-machine guard (Befund 6, run ABS-126): a seat that jumps a
    # mandatory chain seat in one hop (e.g. In Test -> Done, skipping Story
    # Acceptance / Merging / Docs) is redirected to the first skipped mandatory
    # station so that seat runs. Reads the ticket's ACTUAL last transition from
    # the adapter dump (not the collapsed polling net event), so a legit
    # multi-step traversal seen as one net event is never mis-flagged, and
    # conditional stages (ABS-84 SKIP-FORWARD) and backward bounces are exempt.
    if station_guard "$ticket" "$to"; then
        return 0
    fi
    # §5.7 per-epic merge token (ABS-256 / ADR-A-0025): serialize the Merging seat
    # per EPIC and hold the token across a merge-bounce, so the epic tip cannot move
    # under a story that is fixing its rebase against it. A sibling that cannot take
    # the token is NOT spawned and rests in Merging (reconcilable), so a later sweep
    # retries it — the status is the queue. Placed AFTER station_guard (a
    # station-jumping ticket is redirected, never handed a token) and BEFORE the
    # action mapping, so the release edges still fire on statuses that map to NOOP
    # (`Ready for Merge`) as well as on spawning ones (`Docs`, `Needs PO Decision`).
    if ! merge_token_gate "$ticket" "$to"; then
        return 0
    fi
    local action role mapping
    mapping="$(map_action "$to")"
    # ABS-116: a BACKWARD transition into In Progress is a reviewer/gate bounce
    # that would otherwise NOOP-deadlock (In Progress is neither mapped nor
    # reconcilable — observed live on ABS-108, In Review -> In Progress).
    # Treat it like Ready for Development: spawn/resume the implementer (role
    # from ticket, §2.2). Direction comes from the event's `from`: only a
    # chain status LATER than In Progress qualifies — forward entry (Ready for
    # Development -> In Progress), creation events (from null) and neutral
    # returns (Blocked/Needs PO Decision -> In Progress, chain_index 0) all
    # keep the NOOP row. statuses.yaml is untouched (option b, ABS-116).
    if [ "$to" = "In Progress" ] && [ -n "$from" ]; then
        local from_idx
        from_idx="$(chain_index "$from")"
        # Epic-range indices (21-29) would also compare > 3, but no epic status
        # has an In Progress edge in statuses.yaml — unreachable, noted defensively.
        if [ "$from_idx" -gt "$(chain_index "In Progress")" ]; then
            mapping="SPAWN -"
            runlog BOUNCE-REROUTE "$ticket" - "$to" "from=$from"
        fi
    fi
    action="${mapping%% *}"
    role="${mapping#* }"

    # ABS-270 merge-wait: a story lands in Docs only with a MERGED implementation
    # PR. With the PR still open the tech-writer could only refuse the Done
    # transition (done_pr_gate) and rest — which the runner then misread as an
    # ABS-132 stuck loop and escalated to the PO, who has no merge authority. Rest
    # the story at the human-owned `Ready for Merge` gate instead and spawn NOBODY;
    # merge_wait_release (reconcile) resumes it at Docs once the merge lands.
    # Fail-open in the placeholder case (no $FORGE_CMD / no PR -> Docs proceeds).
    if [ "$to" = "Docs" ] && docs_pr_gate "$ticket" "$to"; then
        return 0
    fi

    # ABS-454 ready-for-merge MR-existence gate: a story enters `Ready for Merge`
    # (the human merge gate) only with an MR that EXISTS (open OR merged). Three
    # 2026-07-18 stories rested there with NO MR (MR-create failed / push lost in a
    # restart) and stalled human-invisibly. Redirect a no-MR entry back to `Merging`
    # so the RTE respawn creates the MR — self-heal instead of stall. No-op on an
    # OPEN MR (the ABS-270 merge-wait park) or a MERGED one, and fail-open in the
    # placeholder case (no $FORGE_CMD / no MR platform -> unchanged).
    if [ "$to" = "Ready for Merge" ] && ready_for_merge_mr_gate "$ticket" "$to"; then
        return 0
    fi

    # v3 Done handling (ABS-72/ABS-73/ABS-137): a Done event never spawns
    # tech-writer — as of ABS-137 the `Done` row maps to NOOP because docs come
    # solely from the `Docs` station before the human merge gate (no post-merge
    # tech-writer spawn). Two Done-only side effects must still run regardless of
    # the NOOP mapping, so they are handled here, ahead of the action switch:
    #   1. JOIN trigger (ABS-73): a child's Done advances its parent epic right
    #      here, so the last story completing advances the epic without waiting a
    #      reconcile cadence.
    #   2. SKIP-DOCS-DONE audit (ABS-72): the `Docs -> Done` transition is
    #      recorded as an explicit no-op; sim S4 pins a plain story at exactly 6
    #      spawns. A non-Docs Done (e.g. Path-A Ready for Merge -> Done) falls
    #      through to the NOOP row below.
    if [ "$to" = "Done" ]; then
        # ABS-211 done-gate: a story reaches Done only with a MERGED implementation
        # PR. An open-PR Done is a FALSE signal for the epic JOIN (ABS-192 PR #133,
        # ABS-202 PR #129) — refuse it and redirect back to Merging BEFORE the JOIN
        # trigger below can fire. Fail-open in the placeholder case (no $FORGE_CMD /
        # no PR -> passes). This also covers the guard/repair chain (AC3): however a
        # ticket reaches Done, an unmerged PR routes it back through Merging.
        if done_pr_gate "$ticket" "$to"; then
            return 0
        fi
        local done_dump done_parent
        done_dump="$(tracker get "$ticket" 2>/dev/null || true)"
        done_parent="$(fm_field "$done_dump" parent)"
        [ -n "$done_parent" ] && join_check_epic "$done_parent"
        if printf '%s\n' "$done_dump" | awk '
                /^Transition: .* -> Done\./ { last = $0 }
                END { exit(last ~ /^Transition: Docs -> Done\./ ? 0 : 1) }'; then
            intent SKIP-DOCS-DONE "$ticket" - "$to"
            DISPATCHED_CYCLE="$DISPATCHED_CYCLE[$ticket|$to]"
            return 0
        fi
    fi

    case "$action" in
        NOOP)
            intent NOOP "$ticket" - "$to"
            return 0
            ;;
        NOTIFY)
            # v3: entering "Ready for Epic Acceptance" is THE human touchpoint —
            # the ready-to-test signal the whole epic pipeline exists to fire
            # (spec §1.1, ABS-71/ABS-90). Everything else keeps the generic text.
            if [ "$to" = "Ready for Epic Acceptance" ]; then
                notify "${ORCH_NOTIFY_TICKET:-$ticket}" "ready-to-test: epic $ticket is deployed to staging and ready for human acceptance"
            else
                notify "${ORCH_NOTIFY_TICKET:-$ticket}" "orchestrator notify for $ticket ($to)"
            fi
            return 0
            ;;
        SPAWN|SPAWN-NOTIFY)
            # Per-cycle guard: reconcile() and process_events() must not both act
            # on the same (ticket, to) in one cycle (would double-spawn a ticket
            # the poll surfaced AND reconciliation re-derived). Idempotent across
            # cycles is still handled by the re-read guard + single-flight lock.
            local dkey="$ticket|$to"
            case "$DISPATCHED_CYCLE" in
                *"[$dkey]"*) return 0 ;;
            esac
            # ABS-322 fastlane collapse: a `lane=fastlane` ticket folds its
            # QAS (In Test) and PO (Story Acceptance) tail into the combined
            # gate / merge-queue. On entry to a folded-away station the runner
            # re-transitions forward — no spawn, no budget — like the ABS-84 /
            # ABS-124 skips. Gated first on the status (cheap) so a normal-lane
            # or non-folded station never pays the extra `get`; then on the lane.
            if [ "${ORCH_FASTLANE_COLLAPSE:-1}" = "1" ] \
                && [ -n "$(fastlane_collapse_target "$to")" ] \
                && ticket_still_in "$ticket" "$to"; then
                local fl_dump
                fl_dump="$(tracker get "$ticket" 2>/dev/null || true)"
                if [ "$(ticket_lane "$fl_dump")" = "fastlane" ]; then
                    fastlane_skip "$ticket" "$to"
                    DISPATCHED_CYCLE="${DISPATCHED_CYCLE}[$dkey]"
                    return 0
                fi
            fi
            # ABS-324 fastlane bundling: several eligible lane=fastlane tickets
            # waiting at Ready for Development share ONE Solo-Seat run / branch /
            # PR. At the Solo-Seat entry the runner computes the deterministic,
            # capped bundle roster; the lexicographically-first member is the
            # LEAD. A NON-lead member folds here (no separate spawn/branch/PR) —
            # its work rides the lead's run. The lead falls through to the spawn
            # with the roster stashed in FL_BUNDLE_ROSTER so the seat_note carries
            # the whole bundle. Status-gated first (cheap); kill-switch
            # ORCH_FASTLANE_BUNDLE=0; lane=normal never bundles (fastlane_bundle_
            # eligible gates it). Placed after the ABS-322 collapse fold so it only
            # sees fresh Ready-for-Development Solo-Seat entries.
            if [ "${ORCH_FASTLANE_BUNDLE:-1}" = "1" ] && [ "$to" = "Ready for Development" ] \
                && ticket_still_in "$ticket" "$to"; then
                local bl_dump
                bl_dump="$(tracker get "$ticket" 2>/dev/null || true)"
                if fastlane_bundle_eligible "$bl_dump"; then
                    local roster lead
                    roster="$(fastlane_bundle_roster "$ticket")"
                    if [ "$(printf '%s\n' "$roster" | grep -c . || true)" -ge 2 ]; then
                        lead="$(printf '%s\n' "$roster" | head -1)"
                        if [ "$ticket" != "$lead" ]; then
                            case "$BUNDLE_FOLDED" in
                                *"[$ticket]"*)
                                    runlog INTENT-FASTLANE-BUNDLE-FOLD "$ticket" - "$to" "throttled lead=$lead" ;;
                                *)
                                    BUNDLE_FOLDED="${BUNDLE_FOLDED}[$ticket]"
                                    fastlane_bundle_fold "$ticket" "$lead" ;;
                            esac
                            DISPATCHED_CYCLE="${DISPATCHED_CYCLE}[$dkey]"
                            return 0
                        fi
                        FL_BUNDLE_ROSTER="$(printf '%s\n' "$roster" | paste -sd, -)"
                    fi
                fi
            fi
            # v3 SKIP-FORWARD (ABS-84): a conditional stage on an unflagged
            # ticket is skipped by the RUNNER — audit comment + re-transition,
            # never a spawn. Checked before every safety gate because it
            # replaces the spawn entirely (no budget, no lock).
            local skip_flag
            skip_flag="$(conditional_flag_for "$to")"
            if [ -n "$skip_flag" ] && ticket_still_in "$ticket" "$to"; then
                local skip_dump
                skip_dump="$(tracker get "$ticket" 2>/dev/null || true)"
                if ! ticket_has_flag "$skip_dump" "$skip_flag"; then
                    skip_forward "$ticket" "$to" "$skip_flag"
                    DISPATCHED_CYCLE="$DISPATCHED_CYCLE[$dkey]"
                    return 0
                fi
            fi
            # ABS-124 review-gate sizing: the always-on gates become sizable
            # via opt-OUT flags per the architect-approved skip matrix.
            # Fail-safe: contradictory/ineligible flag combinations fall
            # through and every gate runs (gate_skip_blocked logs why).
            local gate_flag=""
            case "$to" in
                "In Review") gate_flag="skip-review" ;;
                "In Test")   gate_flag="skip-test" ;;
            esac
            if [ -n "$gate_flag" ] && ticket_still_in "$ticket" "$to"; then
                local gs_dump
                gs_dump="$(tracker get "$ticket" 2>/dev/null || true)"
                if ticket_has_flag "$gs_dump" "$gate_flag" \
                    && ! gate_skip_blocked "$gs_dump" "$gate_flag" "$ticket" "$to"; then
                    gate_skip "$ticket" "$to" "$gate_flag"
                    DISPATCHED_CYCLE="${DISPATCHED_CYCLE}[$dkey]"
                    return 0
                fi
            fi
            # v3 rework guard (ABS-74, spec §3.2): a ticket at the cross-stage
            # bounce limit is escalated to the PO instead of re-spawned. Only
            # chain statuses are guarded (Needs PO Decision / Blocked / Backlog
            # dispatches must always proceed).
            if [ "$(chain_index "$to")" -gt 0 ] && ticket_still_in "$ticket" "$to" \
               && rework_blocks "$ticket"; then
                escalate_rework "$ticket" "$to"
                DISPATCHED_CYCLE="$DISPATCHED_CYCLE[$dkey]"
                return 0
            fi
            # v3 Blocked -> TDM triage (ABS-76, spec §1.3/§3.7): spawn tdm at
            # most once per Blocked ENTRY (comment-keyed guard, ABS-62/ABS-75
            # pattern). Record the pre-blocked status BEFORE the spawn so the
            # marker survives even if the spawn attempt fails; TDM reads it
            # rather than recomputing it. A ticket re-entering Blocked later
            # (a fresh "-> Blocked" transition) has no marker newer than that
            # entry, so it gets a fresh spawn.
            if [ "$to" = "Blocked" ] && ticket_still_in "$ticket" "$to"; then
                local blocked_dump blocked_from
                blocked_dump="$(tracker get "$ticket" 2>/dev/null || true)"
                if has_blocked_marker "$blocked_dump"; then
                    intent SKIP-BLOCKED-MARKED "$ticket" - "$to"
                    DISPATCHED_CYCLE="$DISPATCHED_CYCLE[$dkey]"
                    return 0
                fi
                blocked_from="$(last_transition_into_blocked_from "$blocked_dump")"
                record_blocked_from "$ticket" "${blocked_from:-unknown}"
                # ABS-336 / ADR-A-0014: integration-conflict forward-fix route.
                # When the epic blocked FROM Epic Integration on a sync-rebase
                # conflict, route a forward-fix implementer (role from the failing
                # commit's ticket, default be-developer) with a MERGE-not-rebase
                # packet note — instead of the tdm/human triage. On its clean
                # handoff the runner routes the epic to Architecture Review
                # (escalation_resume_target), not back to Epic Integration.
                if [ "$ORCH_INTEGRATION_CONFLICT_ROUTE" = "1" ] \
                    && is_integration_conflict "$blocked_dump"; then
                    local fx_role
                    fx_role="$(failing_commit_role "$blocked_dump")"
                    intent INTEGRATION-CONFLICT "$ticket" "$fx_role" "$to" "forward-fix:sync-rebase-conflict"
                    record_integration_conflict_note "$ticket" "$fx_role"
                    role="$fx_role"
                fi
            fi
            do_spawn_action "$ticket" "$to" "$role" "$action" "$from"
            local rc=$?
            # ABS-208: the issue-enrichment seat creates the epic's children in
            # this spawn — propagate the epic's start label onto them right away
            # (AC1, "immediately after creation") so a mid-flight child is never
            # dropped from the Backlog opt-in sweep. Only when the spawn actually
            # acted (rc != 3 = not deferred by the concurrency cap). The reconcile
            # sweep re-covers the async case where the seat is still running when
            # do_spawn_action returns.
            if [ "$to" = "Enrichment" ] && [ "$rc" -ne 3 ]; then
                propagate_start_label_to_children "$ticket"
            fi
            # Only mark as dispatched when it actually acted (not deferred).
            if [ "$rc" -ne 3 ]; then DISPATCHED_CYCLE="$DISPATCHED_CYCLE[$dkey]"; fi
            return $rc
            ;;
    esac
    return 0
}

# depends_unmet <ticket> <to> — 0 (true) when a ticket the dependent depends_on
# is not yet SATISFIED (ABS-111 C8). Gated to the pre-implementation resting
# statuses only: resting there is cheap and the reconcile sweep re-derives the
# spawn once the dependency lands — no marker, no crash. Sets DEPENDS_BLOCKER to
# "<dep>:<status>" for the intent note.
#
# PILOT-37 — Backlog is a gated resting status too: a dependency-waiting ticket
# is held in Backlog (never triaged, never dispatched) rather than moved forward
# and parked. A dependency-wait is a MACHINE state, so it must never become
# Blocked (a human-attention status); it simply rests in its current status and
# is re-derived automatically once the dependency is satisfied (ABS-495 twin).
#
# PILOT-19 — a blocker gates the dependent because its ARTIFACT (code on the
# target branch) is not there yet, NOT because its docs tail is unfinished. So a
# blocker counts as SATISFIED the instant that artifact has landed, proven the
# only way that is TRUTH rather than a claim: mechanically, via story_merge_state
# (git merge-base --is-ancestor of the blocker's story head into its merge
# target — the PILOT-4/ABS-494 forge-less probe, and the ABS-513 "verify, don't
# trust the label" doctrine). A blocker is satisfied when
#   * it is Done (terminal; done_pr_gate guarantees Done implies a merged PR), OR
#   * story_merge_state reports MERGED (its head is an ancestor of the target), OR
#   * it rests in 'Docs' (PILOT-44 — see below).
#
# PILOT-44 — 'Docs' is a POST-MERGE exit (ABS-266): a story reaches it only AFTER
# its code is merged; only the documentation tail then runs. So a blocker in
# 'Docs' has ALREADY satisfied the artifact condition, and is treated as
# SATISFIED without re-proving it through the ancestry probe. This is NOT the old
# ABS-119 "trust an arbitrary label" shortcut: the label 'Docs' IS the merge fact
# (ABS-266 makes it post-merge-only), and the merge-fact probe stays in force for
# every OTHER non-Done status. It closes the v3-pilot #5 stall where the whole
# downstream wave idled 10-20 min on the Docs seat of a dependency whose code was
# long merged, because the ancestry probe (remote-dependent, timing-flaky) had not
# yet confirmed the merge. The Epic-completion gate is UNAFFECTED (join_check_epic
# waits on real Done of every child; a child in 'Docs' still blocks the JOIN).
#
# Declarable exception (AC3): a dependent that itself needs the blocker's OWN
# finished artifact (e.g. the merged documentation) carries the 'depends-strict'
# label; for it, only Done satisfies — both the merge-fact AND the 'Docs' early
# release are suppressed (the strict check runs first, below).
DEPENDS_BLOCKER=""
depends_unmet() {
    [ "$ORCH_DEPENDS_GATING" = "1" ] || return 1
    case "$2" in
        "Backlog"|"Ready for Development"|"Design") ;;
        *) return 1 ;;
    esac
    local dump deps dep dstat dep_dump strict=0 ms
    dump="$(tracker get "$1" 2>/dev/null || true)"
    deps="$(printf '%s\n' "$dump" | sed -n 's/^depends_on: \[\(.*\)\]/\1/p' | head -1 | tr -d ' ' | tr ',' ' ')"
    [ -n "$deps" ] || return 1
    ticket_has_label "$dump" "depends-strict" && strict=1
    for dep in $deps; do
        # ABS-111 hotfix: an UNREADABLE dependency (transient adapter/API error)
        # means WAIT, not "satisfied" — the same error-vs-empty discipline as
        # the JOIN guard. The reconcile sweep re-derives the dispatch, so a
        # transient failure clears on its own; a permanently dead reference is
        # an operator fix (edit the ticket's depends_on), visible via the note.
        if ! dep_dump="$(tracker get "$dep" 2>/dev/null)" || [ -z "$dep_dump" ]; then
            DEPENDS_BLOCKER="$dep:unreadable"
            return 0
        fi
        dstat="$(printf '%s\n' "$dep_dump" | sed -n 's/^status: //p' | head -1)"
        if [ -z "$dstat" ]; then
            DEPENDS_BLOCKER="$dep:unreadable"
            return 0
        fi
        # Done is terminal satisfaction; a status change to Done never re-blocks
        # a dependent that already released on the merge fact (AC1).
        [ "$dstat" = "Done" ] && continue
        # AC3: a 'depends-strict' dependent waits for Done, nothing earlier.
        if [ "$strict" = "1" ]; then
            DEPENDS_BLOCKER="$dep:$dstat"
            return 0
        fi
        # PILOT-44: 'Docs' is a POST-MERGE status (ABS-266) — the blocker's code is
        # already merged and only its docs tail runs. Treat it as SATISFIED without
        # the (remote-dependent, timing-flaky) ancestry probe, so the downstream
        # wave is not held for the 10-20 min Docs seat (v3-pilot #5: PILOT-30/PILOT-32
        # blocked on PILOT-29-in-Docs). Runs AFTER the strict check, so a
        # 'depends-strict' dependent still waits for Done.
        [ "$dstat" = "Docs" ] && continue
        # AC1/AC2: MERGE-FACT release — satisfied the instant the blocker's head
        # is an ancestor of its merge target, established mechanically (never a
        # status-label match). NONE/OPEN (no branch, or not yet merged) keeps the
        # gate closed — e.g. 'Docs' before the human merge lands. story_merge_state
        # prints "STATE\tREF"; take the STATE field (same split as done_pr_gate).
        ms="$(story_merge_state "$dep" 2>/dev/null)"
        [ "${ms%%$'\t'*}" = "MERGED" ] && continue
        DEPENDS_BLOCKER="$dep:$dstat"
        return 0
    done
    return 1
}

# epic_review_owed <ticket> <to> — 0 (true) when the ticket is a CHILD of a
# PRE-FILLED epic (has children but never visited Grooming — same class test
# as prefilled_epic_entry_index) that has not yet visited "Architecture
# Review", the station that releases stories on the decomposed path. Holding
# the child restores the decomposed-path ordering for pre-filled epics: the
# ABS-392 incident (2026-07-18 proposal) showed the epic's Ticket Review +
# Architecture Review degrade to rubber-stamps when children dispatch first.
# Gated to implementation ENTRY statuses like depends_unmet: resting is cheap,
# the reconcile sweep re-derives the spawn once the epic clears the station —
# no marker, no crash. An UNREADABLE parent means WAIT, not "satisfied" (the
# depends_unmet error-vs-empty discipline). Sets EPIC_REVIEW_EPIC for the
# intent note. Kill-switch: ORCH_EPIC_REVIEW_GATING=0.
EPIC_REVIEW_EPIC=""
epic_review_owed() {
    [ "$ORCH_EPIC_REVIEW_GATING" = "1" ] || return 1
    case "$2" in
        "Ready for Development"|"Design") ;;
        *) return 1 ;;
    esac
    local dump parent pdump
    dump="$(tracker get "$1" 2>/dev/null || true)"
    [ -n "$dump" ] || return 1
    [ "$(fm_field "$dump" type)" = "epic" ] && return 1
    parent="$(printf '%s\n' "$dump" | sed -n 's/^parent: //p' | head -1)"
    [ -n "$parent" ] || return 1
    if ! pdump="$(tracker get "$parent" 2>/dev/null)" || [ -z "$pdump" ]; then
        EPIC_REVIEW_EPIC="$parent:unreadable"
        return 0
    fi
    [ "$(fm_field "$pdump" type)" = "epic" ] || return 1
    epic_visited_grooming "$pdump" && return 1               # DECOMPOSED epic: BSA path already gates children
    epic_visited_station "$pdump" "Architecture Review" && return 1  # reviews cleared: children are released
    # v1-plain CONTAINER epics (epic as a grouping shell, children dispatched
    # directly — the v1 happy path, still supported) are untouched: the hold
    # applies only to a PIPELINE-ARMED epic — it carries the Backlog opt-in
    # label (ABS-101) or has demonstrably entered the epic pipeline. Without
    # this, the gate would deadlock every v1-style epic+child fixture forever
    # (caught by the ABS-180 packet test on first run).
    if ! ticket_has_label "$pdump" "$ORCH_START_LABEL" \
        && ! epic_visited_station "$pdump" "PO Triage" \
        && ! epic_visited_station "$pdump" "Enrichment" \
        && ! epic_visited_station "$pdump" "Ticket Review"; then
        return 1
    fi
    EPIC_REVIEW_EPIC="$parent"
    return 0
}

# do_spawn_action — resolve the role, honor safety gates, emit the intent, and
# (in --live) route to the spawn adapter. Commit 2 implements dry-run intent
# logging + role selection; commits 3/4 layer the spawn seam and safety in.
do_spawn_action() {
    # ABS-135: `from` ($5) is threaded explicitly from dispatch (the parsed
    # event's source status), NOT read via the process-global $ev_from — that
    # global holds the LAST parsed event and leaked a different ticket's status
    # into the packet (Befund 2). reconcile omits it -> "".
    local ticket="$1" to="$2" role="$3" action="$4" from="${5:-}"
    local note=""

    # Role selection for the ticket-derived implementer (§2.2).
    if [ "$role" = "-" ]; then
        resolve_implementer_role "$ticket"
        role="$resolved_role"
        note="$role_note"
    fi

    # ABS-324 fastlane bundle Solo-Seat: when this Ready-for-Development spawn is
    # the bundle LEAD (roster stashed by dispatch), the note carries the roster +
    # shared-branch directive so the ONE Solo-Seat implements every bundle ticket,
    # commits each atomically ([ABS-XXX]) on the shared branch ($ticket-auto), and
    # opens ONE PR referencing all ids (AC1/AC2). Persist the roster so the In
    # Review combined gate can attribute pass/fail per ticket (AC3). Overrides the
    # single-ticket fastlane-solo-seat note set by resolve_implementer_role.
    if [ -n "${FL_BUNDLE_ROSTER:-}" ] && [ "$to" = "Ready for Development" ]; then
        note="fastlane-bundle-solo-seat:dev+scoped-tests+self-review bundle=$FL_BUNDLE_ROSTER branch=$ticket-auto"
        printf '%s\n' "$FL_BUNDLE_ROSTER" > "$ORCH_STATE_DIR/fastlane-bundle-$ticket" 2>/dev/null || true
    fi

    # ABS-322 fastlane combined gate: In Review is the SINGLE review/test gate
    # for a fastlane ticket (the QAS station is folded away by fastlane_skip).
    # Mark the spawn so the reviewer verifies the Solo-Seat's scoped tests as
    # well as the code — one gate, then the merge-queue. Read gated on the
    # status so normal-lane spawns pay no extra adapter call.
    if [ "${ORCH_FASTLANE_COLLAPSE:-1}" = "1" ] && [ "$to" = "In Review" ]; then
        if [ "$(ticket_lane "$(tracker get "$ticket" 2>/dev/null || true)")" = "fastlane" ]; then
            note="fastlane-combined-gate:review+scoped-tests"
            # ABS-324: a bundle lead's combined gate evaluates the WHOLE bundle and
            # attributes pass/fail PER TICKET — a failure on one member must not
            # silently pass the others (AC3). The roster was persisted at the
            # Solo-Seat spawn above.
            if [ -f "$ORCH_STATE_DIR/fastlane-bundle-$ticket" ]; then
                note="fastlane-combined-gate:review+scoped-tests bundle=$(paste -sd, - < "$ORCH_STATE_DIR/fastlane-bundle-$ticket") per-ticket-attribution"
            fi
        fi
    fi

    # Re-read guard (§5.4): skip stale events / already-advanced tickets.
    if ! ticket_still_in "$ticket" "$to"; then
        intent SKIP-STALE "$ticket" "$role" "$to"
        return 0
    fi

    # ABS-111 C8: hold work whose declared dependencies are not Done yet
    # (live run 1: the E2E story was spawned before any prerequisite existed).
    if depends_unmet "$ticket" "$to"; then
        intent DEPENDS-WAIT "$ticket" "$role" "$to" "unmet=$DEPENDS_BLOCKER"
        return 0
    fi

    # ABS-518 (epic ABS-514): children of a pre-filled epic rest until the
    # epic has cleared its review stations — otherwise the epic-level DoR /
    # Architecture gates run after the children are in flight and cannot
    # block or reshape anything (ABS-392: "noted for the record only").
    if epic_review_owed "$ticket" "$to"; then
        intent EPIC-REVIEW-WAIT "$ticket" "$role" "$to" "epic=$EPIC_REVIEW_EPIC owes-review-stations"
        return 0
    fi

    # ABS-135: thread the event's `from` through so the packet's from_status
    # reflects THIS ticket's source status, never a process-global leftover.
    spawn_dispatch "$ticket" "$to" "$role" "$action" "$note" "$from"
    return $?
}

# spawn_dispatch — the safety-gated spawn path (§5). Ordering:
#   kill-switch -> budget -> iteration-guard(bounce) -> single-flight lock ->
#   concurrency cap (defer) -> spawn.
# Returns 0 normally; 3 = deferred, caller re-queues into the pending set (§5.1)
# — the concurrency cap (DEFER-CAP) and a held single-flight lock (SKIP-LOCKED,
# ABS-133 Befund 5) both use rc 3 so a lock-skipped dispatch is retried, not lost.
spawn_dispatch() {
    # ABS-135: `from` ($6) is threaded from dispatch (the parsed event's source
    # status) and passed on to live_spawn -> build_packet. reconcile / follow-up
    # callers omit it (no direction from a resting ticket) -> "".
    local ticket="$1" to="$2" role="$3" action="$4" note="$5" from="${6:-}"

    # Kill-switch is also checked before every spawn (§5.3).
    if [ -f "$ORCH_STOP_FILE" ]; then
        intent SKIP-KILLSWITCH "$ticket" "$role" "$to"
        return 0
    fi

    # ABS-118 outage pause: while the outage marker exists, only probes run —
    # and only in auto mode, one at a time (the probe claim advances the
    # schedule and takes the inflight slot SYNCHRONOUSLY in the parent before
    # the possibly-async spawn launches; architect F1). Manual mode: hard
    # pause until the operator removes the outage file.
    if [ -f "$(outage_file)" ]; then
        local admit_probe=0
        if [ "$ORCH_OUTAGE_RESUME" = "auto" ] && [ ! -f "$(probe_inflight_file)" ]; then
            local o_paused o_count o_next o_now
            o_paused="$(cut -f1 "$(outage_file)" 2>/dev/null | head -1 || true)"
            o_count="$(cut -f2 "$(outage_file)" 2>/dev/null | head -1 || true)"
            o_next="$(cut -f3 "$(outage_file)" 2>/dev/null | head -1 || true)"
            o_now="$(now_epoch)"
            if [ "$o_now" -ge "${o_next:-0}" ] 2>/dev/null; then
                o_count=$(( ${o_count:-0} + 1 ))
                printf '%s\t%s\t%s\n' "${o_paused:-$o_now}" "$o_count" \
                    "$(( o_now + $(probe_interval_for $((o_count + 1))) ))" > "$(outage_file)" 2>/dev/null || true
                printf '%s' "$ticket" > "$(probe_inflight_file)" 2>/dev/null || true
                runlog PROBE "$ticket" "$role" "$to" "n=$o_count"
                admit_probe=1
            fi
        fi
        if [ "$admit_probe" -eq 0 ]; then
            intent SKIP-OUTAGE "$ticket" "$role" "$to"
            return 0
        fi
    fi

    # ABS-118 escalation halt: a crashed Needs-PO-Decision seat stays down
    # until the operator removes the marker (NOTIFY already sent).
    if [ -f "$(halt_file "$ticket")" ]; then
        intent SKIP-HALT "$ticket" "$role" "$to"
        return 0
    fi

    # ABS-118 per-(ticket,status) crash backoff: inside the delay window the
    # dispatch is skipped for free (no budget, no lock); the sweep simply
    # passes the ticket over until the delay expires.
    if backoff_active "$ticket" "$to"; then
        intent SKIP-BACKOFF "$ticket" "$role" "$to"
        return 0
    fi

    # PILOT-66 worktree-provisioning gate: fail-closed BEFORE spending budget.
    # C9 forbids a write-capable seat in the main checkout; if the isolated
    # worktree cannot be provisioned we must not spawn — but the pre-fix path
    # burned a budget slot per silent retry (budget is decremented below), so an
    # unprovisionable branch drained the whole run. Provisioning here (idempotent
    # in live_spawn's re-check) means a failure returns with NO budget/lock/seam
    # cost — count + backoff + escalate-after-N (AC1/AC4), and git's own stderr in
    # the runlog (AC2). Worktree-ineligible statuses (docs/PO/… seats) skip this.
    if [ "$MODE" = "live" ] && [ "$ORCH_WORKTREE_SPAWNS" = "1" ] && worktree_eligible_status "$to"; then
        if ! ensure_worktree "$ticket"; then
            record_worktree_provision_failure "$ticket" "$to" "$role"
            return 0
        fi
        clear_worktree_fail "$ticket"   # provisioned → reset the failure ladder
    fi

    # §5.4 progress-aware spawn budget (PILOT-47, extends ADR-A-0009). Order:
    #   (AC4) per-day ledger + hard backstop — fail-closed, keep the ABS-455
    #         exit-75 restart handshake.
    #   (AC3) per-ticket cap — a single cyclic ticket -> Needs PO Decision; run on.
    #   (AC1/AC2) per-run soft cap — an in-flight ticket (already spawned this run)
    #         always finishes; NEW intake triggers a progress-aware auto-extend,
    #         else DRAIN (hold this intake; in-flight work still drains).
    local _pt_spawns
    _pt_spawns="$(ticket_spawn_count "$ticket")"

    # v3 per-day budget (ABS-74): the dated ledger caps spawns ACROSS runs.
    if daily_budget_exhausted; then
        pause_for_daily_budget
        intent SKIP-BUDGET-DAY "$ticket" "$role" "$to"
        return 0
    fi
    # AC4 hard backstop: absolute per-run ceiling — fail-closed (exit 75).
    if hard_backstop_reached; then
        pause_for_budget
        intent SKIP-BUDGET "$ticket" "$role" "$to"
        return 0
    fi
    # AC3 per-ticket cap: a single cyclically-respawning ticket -> Needs PO Decision.
    if [ "$ORCH_MAX_SPAWNS_PER_TICKET" -gt 0 ] && [ "$_pt_spawns" -ge "$ORCH_MAX_SPAWNS_PER_TICKET" ]; then
        block_for_ticket_spawn_cap "$ticket" "$to" "$_pt_spawns"
        return 0
    fi
    # AC1/AC2 per-run soft cap: extend on healthy progress, else drain new intake.
    if budget_exhausted; then
        if [ "$_pt_spawns" -eq 0 ]; then
            if ! try_autoextend_budget; then
                enter_drain_mode
                intent SKIP-DRAIN-INTAKE "$ticket" "$role" "$to"
                return 0
            fi
        fi
        # _pt_spawns>0 -> an in-flight continuation: fall through and spawn so the
        # pipeline drains to completion (AC1), regardless of the exhausted soft cap.
    fi

    # §5.5 iteration guard for bounce-capable loops (In Review, In Test).
    if is_bounce_status "$to" && iteration_guard_blocks "$ticket"; then
        block_for_iteration_cap "$ticket" "$to"
        return 0
    fi

    # §5.2 single-flight lock: one in-flight spawn per ticket.
    # ABS-133 (Befund 5): re-queue the skipped dispatch into the pending set
    # (rc 3, same path as a concurrency defer) so it is retried once the lock
    # releases. Without this a dispatch skipped while a DIFFERENT spawn held the
    # lock is lost whenever the ticket rests in a status reconcile does not
    # re-derive (a legit-rest status like Done -> tech-writer): the crash-safe
    # net only covers reconcilable statuses. The re-read guard makes the retry a
    # no-op if the ticket has since moved on, so this never double-spawns.
    # ABS-300: mint this dispatch's seat token BEFORE acquiring the lock so the
    # lock records which seat owns the station. The `( … ) &` async spawn subshell
    # inherits this frozen value, so handoff_followthrough (inside it) can tell its
    # own lock from a foreign one and refuse a racing handoff.
    ORCH_SEAT_TOKEN="${ORCH_INSTANCE_ID:-local}:${role}:${to}:$$:$(now_epoch):${RANDOM}"
    if ! acquire_lock "$ticket"; then
        intent SKIP-LOCKED "$ticket" "$role" "$to"
        return 3
    fi

    # §5.1 concurrency cap: over cap -> release lock and defer to the pending set.
    # ABS-111 A1: with async spawns the live count is the number of running
    # background jobs — ORCH_MAX_CONCURRENT finally has real effect (the legacy
    # synchronous path kept at most one spawn in flight).
    # ABS-261: a priority=hotfix ticket may claim ORCH_HOTFIX_CAP_BONUS slots over
    # the cap so it passes wartende Feature-Arbeit — but this only RAISES the
    # admission ceiling for the new spawn; a running seat is never killed (no
    # preemption; the idle watchdog stays the only seat-beender, AC2). DEFER-CAP
    # names the priority so an operator sees who was preferred (AC4). Kill-switch
    # OFF => no priority read, base cap, and a note-less legacy DEFER-CAP line (AC5).
    local eff_cap="$ORCH_MAX_CONCURRENT" cap_prio="normal" cap_note=""
    if [ "$ORCH_PRIORITY_DISPATCH" != "0" ]; then
        cap_prio="$(ticket_priority "$ticket")"
        cap_note="priority=$cap_prio"
        [ "$cap_prio" = "hotfix" ] && eff_cap=$((ORCH_MAX_CONCURRENT + ORCH_HOTFIX_CAP_BONUS))
    fi
    if [ "$ORCH_ASYNC_SPAWNS" = "1" ]; then
        if [ "$(live_spawn_count)" -ge "$eff_cap" ]; then
            release_lock "$ticket"
            intent DEFER-CAP "$ticket" "$role" "$to" "$cap_note"
            return 3
        fi
    elif [ "$LIVE_SPAWNS" -ge "$eff_cap" ]; then
        release_lock "$ticket"
        intent DEFER-CAP "$ticket" "$role" "$to" "$cap_note"
        return 3
    fi

    # §5.6 distributed remote claim (ABS-185): stake the cross-machine claim only
    # once local admission is granted (lock held + under cap). Placement is
    # load-bearing — a ticket deferred for cap ABOVE is never claimed, so it stays
    # free for peers (no backlog hogging; spec §4.6). Default-off (ORCH_CLAIM_MODE=
    # off) short-circuits before acquire_remote_claim, keeping the single-runner
    # path byte-for-byte unchanged (ADR-A-0010). A LOST claim hands the slot
    # straight back: release the lock and return 3 (re-queued, like DEFER-CAP)
    # BEFORE the LIVE_SPAWNS/budget increment below, so it consumes no slot/budget.
    if [ "$ORCH_CLAIM_MODE" != "off" ] && ! acquire_remote_claim "$ticket"; then
        release_lock "$ticket"
        intent SKIP-CLAIMED "$ticket" "$role" "$to"
        return 3
    fi

    # ABS-186: on a WON remote claim, optionally stamp the assignee (cosmetic
    # human-visibility layer). mode=off means no claim was staked, so there is
    # nothing won to stamp; claim_assign itself is a no-op unless ORCH_CLAIM_ASSIGN=1.
    if [ "$ORCH_CLAIM_MODE" != "off" ]; then
        claim_assign "$ticket" "$role" "$to"
    fi

    # PILOT-63 AC1: provision the seat's worktree BEFORE charging a budget unit,
    # so a spawn that never reaches a model (worktree provisioning failure) costs
    # NO budget. Every other "never reached a model" case — kill-switch, outage,
    # halt, backoff, single-flight lock, concurrency cap, lost remote claim —
    # already returns ABOVE this point, before the decrement. Worktree failure was
    # the sole exception: live_spawn's fail-closed gate ran AFTER the decrement, so
    # each INTENT-SKIP-NOWORKTREE still cost a unit (125 of 200 on the 2026-07-25
    # pause). Under async spawns the counters live in this parent process and cannot
    # be refunded from the background subshell, so the gate must run here, ahead of
    # the decrement — not inside live_spawn. ensure_worktree is idempotent, so
    # live_spawn reuses this provisioned tree (SPAWN_CWD). dry-run never provisions
    # (it does not call live_spawn), so it is skipped. On failure: release the lock
    # and rest the ticket in place (rc 0, reconcile re-derives and retries next
    # sweep) — exactly the pre-PILOT-63 resting behaviour, now without the charge.
    SPAWN_CWD=""
    if [ "$MODE" != "dry-run" ] && [ "$ORCH_WORKTREE_SPAWNS" = "1" ] && worktree_eligible_status "$to"; then
        if ! provision_seat_worktree "$ticket" "$role" "$to"; then
            release_lock "$ticket"
            return 0
        fi
    fi

    LIVE_SPAWNS=$((LIVE_SPAWNS + 1))
    SPAWN_BUDGET=$((SPAWN_BUDGET - 1))
    SPAWNS_USED=$((SPAWNS_USED + 1))         # PILOT-47: monotonic hard-backstop counter
    ticket_spawn_incr "$ticket"              # PILOT-47 AC3: per-ticket spawn tally
    record_daily_spawn "$ticket" "$role" "$to"

    if [ "$MODE" = "dry-run" ]; then
        intent SPAWN "$ticket" "$role" "$to" "$note"
        # ABS-128: surface the model:-label decision (MODEL-LABEL / -SKIP) in a
        # --dry-run so an operator sees which seats the label would (not) move.
        resolve_spawn_model "$ticket" "$role" "$to" >/dev/null
        # ABS-126: log assign intention in dry-run (live path executes in live_spawn).
        local _dr_assignee
        _dr_assignee="$(role_env "$role" ASSIGNEE)"; [ -n "$_dr_assignee" ] || _dr_assignee="${ORCH_ASSIGNEE:-}"
        [ -n "$_dr_assignee" ] && intent ASSIGN "$ticket" "$role" "$to" "assignee=$_dr_assignee" || true
        [ "$action" = "SPAWN-NOTIFY" ] && notify "${ORCH_NOTIFY_TICKET:-$ticket}" "$role check complete for $ticket ($to)" || true
        release_lock "$ticket"
        return 0
    fi

    # --live: real spawn seam (§3) with the watchdog (§6.1). Async (A1): the
    # whole attempt->retry->record sequence runs in a background subshell that
    # holds the single-flight lock for its lifetime; budget/dedupe/pending
    # bookkeeping stays in the parent (this function, above).
    if [ "$ORCH_ASYNC_SPAWNS" = "1" ]; then
        (
            live_spawn "$ticket" "$to" "$role" "$action" "$note" "$from" || true
            release_lock "$ticket"
        ) &
        SPAWN_PIDS="$SPAWN_PIDS $!"
        return 0
    fi
    live_spawn "$ticket" "$to" "$role" "$action" "$note" "$from" || true
    release_lock "$ticket"
    return 0
}

# =============================================================================
# §4 Context packet — minimal, adapter-sourced (ADR-A-0003)
# =============================================================================
# extract_latest_handoff <ticket-dump> — the body of the LAST `kind: handoff`
# comment block in the ticket (the §22 resume signal). Empty when none.
extract_latest_handoff() {
    printf '%s\n' "$1" | awk '
        /^### / {
            if ($0 ~ /kind: handoff/) { grab = 1; buf = ""; have = 1 }
            else { grab = 0 }
            next
        }
        grab { buf = buf $0 "\n" }
        END { if (have) printf "%s", buf }
    '
}

# build_packet <ticket> <from> <to> <role> <packet-file> — write the packet
# (header + ticket body + latest handoff) to <packet-file>, truncating the
# ticket body tail over ORCH_PACKET_MAX_BYTES while keeping header + full
# handoff (ADR-A-0003 "declare overruns"). Prints nothing.
#
# ABS-176: the packet is cached byte-stable per ticket at $PACKETS_DIR/<ticket>.md
# so same-seat re-spawns (rework bounce / salvage / crash retry) resend a
# byte-identical prompt and hit the provider prompt cache (cache_read_input_tokens
# at ~10% price) instead of paying for the packet again. The cache is keyed on the
# tracker `updated` field plus the header-bearing spawn coordinates (from/to/role/
# resume) and the two content-shaping env inputs TRACKER_CMD + ORCH_PACKET_MAX_BYTES
# (ABS-202); a matching key reuses the file verbatim, and ANY ticket edit bumps
# `updated` and invalidates it (the next packet carries the new state). Content
# stays ticket-facts-only (dump + handoff) — workflow rules live in the role-def/
# commons, not the packet (dedup). The effect is same-role only: cross-role has a
# different role systemprompt before the packet, so no shared cache prefix.
# probe_packet_capability — resolve whether the active adapter offers a server-
# composed `packet` op, memoizing the answer in the PROCESS-GLOBAL
# $_ORCH_PKT_CAP_RESOLVED so the probe fires at most ONCE per orchestrator run
# (ABS-238). Sets it to "packet" when the adapter's `capabilities` op lists
# `packet`, else "full". Assigns the global directly (NOT via stdout/$()) so the
# memo survives — a command substitution would resolve it in a throwaway subshell.
# Never called when ORCH_PACKET_MODE=full (the legacy path is forced, unprobed).
# Adapters without a `capabilities` op (mock, jira) exit non-zero -> "full".
probe_packet_capability() {
    [ -n "${_ORCH_PKT_CAP_RESOLVED:-}" ] && return
    _ORCH_PKT_CAP_RESOLVED="full"
    if tracker capabilities 2>/dev/null | grep -qx "packet" 2>/dev/null; then
        _ORCH_PKT_CAP_RESOLVED="packet"
    fi
}

# probe_events_wait_capability — resolve whether the active adapter+backend offer
# the S4/PILOT-30 `events-wait` long-poll, memoizing in the process-global
# $EVENTS_WAIT_ACTIVE so the probe fires at most ONCE per run (mirrors the ABS-238
# packet probe). 1 = use the blocking long-poll between cycles; 0 = interval-poll.
# Off when the kill switch ORCH_EVENTS_WAIT=0, when the adapter has no `capabilities`
# op (mock/jira exit non-zero), or when it does not list `events-wait`. Assigns the
# global directly (not via $()) so the memo survives a subshell.
probe_events_wait_capability() {
    [ -n "${EVENTS_WAIT_ACTIVE:-}" ] && return
    EVENTS_WAIT_ACTIVE=0
    [ "${ORCH_EVENTS_WAIT:-1}" = "1" ] || return
    if tracker capabilities 2>/dev/null | grep -qx "events-wait" 2>/dev/null; then
        EVENTS_WAIT_ACTIVE=1
        log "events-wait long-poll active (cap=${EVENT_WAIT_CAP_SECONDS}s) — event-driven dispatch (S4/PILOT-30)"
    fi
}

# poll_events — read the event feed for one cycle. Assigns the raw feed to the
# process-global $POLL_RAW and the pacing signal to $POLL_DID_WAIT DIRECTLY (never
# via stdout/$()), so both survive — a command substitution would resolve them in a
# throwaway subshell (same reason as the packet-probe memo). $POLL_DID_WAIT tells the
# main loop whether a blocking long-poll already provided the between-cycle pacing
# (1 = skip the sleep) or an interval sleep is still owed (0). In wait-mode
# (capability present, not --once) it BLOCKS up to the cap in a single
# `tracker events --wait` request: the wake returns instantly on a real event
# (<1s dispatch) or empty at the cap. A failed wait (curl timeout/net/proxy — the
# adapter die()s, non-zero) degrades THIS cycle to an immediate interval read + sleep
# so a persistent proxy fault never busy-loops (AC4).
# reconcile_due — decide whether THIS cycle runs the reconciliation sweep (§5.1).
# Returns 0 (run) / 1 (skip). Startup (cycle 1) always sweeps. Thereafter the
# cadence is WALL-CLOCK in events-wait mode — where the cycle time is variable (up
# to ~cap at rest, sub-second under an event storm), a fixed cycle-count would drift
# 5x too slow at rest / too fast under a storm — so it sweeps when at least
# ORCH_RECONCILE_EVERY_SEC has elapsed since the last sweep (today's wall-clock
# frequency preserved in BOTH load cases, AC7). In interval-poll mode the cycle time
# is ~fixed, so the legacy CYCLE-count modulo is kept byte-identical (AC3).
reconcile_due() {
    [ "$CYCLE" -eq 1 ] && [ "${ORCH_RECONCILE_ON_STARTUP:-1}" -eq 1 ] && return 0
    if [ "${EVENTS_WAIT_ACTIVE:-0}" -eq 1 ]; then
        [ "$ORCH_RECONCILE_EVERY_SEC" -gt 0 ] \
            && [ $(( $(date +%s) - ${LAST_RECONCILE_TS:-0} )) -ge "$ORCH_RECONCILE_EVERY_SEC" ]
        return
    fi
    [ "$ORCH_RECONCILE_EVERY_N_CYCLES" -gt 0 ] && [ $((CYCLE % ORCH_RECONCILE_EVERY_N_CYCLES)) -eq 0 ]
}

poll_events() {
    POLL_DID_WAIT=0
    POLL_RAW=""
    if [ "${EVENTS_WAIT_ACTIVE:-0}" -eq 1 ] && [ "$ONCE" -eq 0 ]; then
        local rc=0
        POLL_RAW="$(tracker events --wait "$EVENT_WAIT_CAP_SECONDS" 2>/dev/null)" || rc=$?
        if [ "$rc" -eq 0 ]; then
            POLL_DID_WAIT=1
            return 0
        fi
        POLL_RAW=""
        log "WARN events-wait request failed (rc=$rc); interval-poll fallback this cycle (S4/PILOT-30)"
        runlog WARN - - - "events-wait failed rc=$rc — interval-poll fallback (S4/PILOT-30)"
    fi
    POLL_RAW="$(tracker events 2>/dev/null || true)"
}

build_packet() {
    # ABS-322: $6 (seat_note) is the per-spawn orchestrator directive — the
    # expanded duties a collapsed-chain seat must perform beyond its base role
    # (fastlane Solo-Seat: dev+scoped-tests+self-review; combined gate:
    # review+scoped-tests). It is threaded from do_spawn_action's `note` through
    # attempt_spawn and rendered as a `seat_note:` header line so it actually
    # reaches the seat's stdin packet (the intent-SPAWN run.log line alone never
    # did — ABS-66 "output lands WHERE?"). Empty for normal-lane spawns, which
    # keep a byte-identical header.
    local ticket="$1" from="$2" to="$3" role="$4" pf="$5" seat_note="${6:-}"
    local dump handoff resume header updated cache meta sig pkt_mode
    dump="$(tracker get "$ticket" 2>/dev/null || true)"
    handoff="$(extract_latest_handoff "$dump")"
    if [ -n "$handoff" ]; then resume="true"; else resume="false"; fi

    # ABS-238 token lever: use the server-composed packet when the adapter offers it
    # (probed once per run), else the legacy full-dump. ORCH_PACKET_MODE=full forces
    # the legacy path byte-identically (ABS-111 default-on + ORCH_* escape).
    if [ "${ORCH_PACKET_MODE:-}" = "full" ]; then
        pkt_mode="full"
    else
        probe_packet_capability
        pkt_mode="$_ORCH_PKT_CAP_RESOLVED"
    fi

    # ABS-382: revision-pinned policy injection (SECOND opt-in orchestrator edit
    # after the ABS-238 packet probe). Call the `policies` adapter op (S4/ABS-381)
    # ONCE per build for this seat's role and prepend the rendered effective-policy
    # text as a `=== POLICY (policy_rev: <hash>) ===` block before `=== TICKET ===`
    # (assembled below). Default-safe: an adapter without `policies` (mock/jira)
    # exits non-zero -> empty policy_out/policy_rev -> policy_section stays empty ->
    # a BYTE-IDENTICAL legacy packet. ORCH_POLICY_INJECT=off forces that legacy path
    # even on a capable adapter. The op prints the rendered text followed by a
    # trailing `policy_rev: <sha256>` line (S4: `${rendered}policy_rev: ${rev}\n`);
    # the hash rides in the block header, so that trailing line is stripped from the
    # body. Injection is context only — it grants the seat no new authority.
    local policy_out="" policy_rev="" policy_body="" policy_section=""
    if [ "${ORCH_POLICY_INJECT:-on}" != "off" ]; then
        policy_out="$(tracker policies --audience "$role" 2>/dev/null)" || policy_out=""
        if [ -n "$policy_out" ]; then
            policy_rev="$(printf '%s\n' "$policy_out" | sed -n 's/^policy_rev: *//p' | tail -1)"
        fi
        if [ -n "$policy_rev" ]; then
            policy_body="$(printf '%s\n' "$policy_out" | sed '/^policy_rev: /d')"
            policy_section="=== POLICY (policy_rev: $policy_rev) ===
$policy_body
"
        fi
    fi

    # Byte-stable per-ticket cache: reuse when the tracker `updated` frontmatter
    # field and the header coordinates are unchanged (works for the mock and jira
    # adapter dumps alike via the shared fm_field reader).
    updated="$(fm_field "$dump" updated)"
    cache="$PACKETS_DIR/$ticket.md"
    meta="$PACKETS_DIR/$ticket.meta"
    # ABS-203: hand the issue-enrichment seat a deterministic write-mode hint so a
    # re-visit whose children already exist knows to short-circuit dedup to a
    # write-light completion (skip no-op child-creation writes, emit only the
    # completion signal). Only computed for that seat; part of the cache sig so a
    # child appearing between visits re-derives the packet.
    local wmode=""
    [ "$role" = "issue-enrichment" ] && wmode="$(enrichment_write_mode "$ticket")"
    # ABS-202: fold TRACKER_CMD (written verbatim into the header) and
    # ORCH_PACKET_MAX_BYTES (drives the body-truncation budget below) into the
    # signature too — both shape packet content, so a cross-run change to either
    # on an otherwise-unchanged ticket (same `updated`) must invalidate the cache
    # rather than serve a packet built under the old values.
    # ABS-382: fold policy_rev into the signature so a policy change bumps the hash
    # and invalidates the cache (a fresh packet is built) exactly like a ticket
    # `updated` change; an unchanged policy set re-hits the cache.
    sig="updated=$updated|from=$from|to=$to|role=$role|resume=$resume|wmode=$wmode|seat_note=$seat_note|tracker_cmd=$TRACKER_CMD|max_bytes=$ORCH_PACKET_MAX_BYTES|pkt_mode=$pkt_mode|policy_rev=$policy_rev"
    # ABS-382 audit: one run.log line per spawn recording the policy_rev the seat was
    # spawned against (spawn <-> exact policy text). Fires on both cache hit and miss
    # — placed before the cache-hit early return below so it is never skipped.
    runlog POLICY-INJECT "$ticket" "$role" "$to" "policy_rev=${policy_rev:-none}"
    mkdir -p "$PACKETS_DIR" 2>/dev/null || true
    if [ -f "$cache" ] && [ -f "$meta" ] && [ "$(cat "$meta" 2>/dev/null)" = "$sig" ]; then
        [ "$pf" = "$cache" ] || cp "$cache" "$pf"
        return 0
    fi

    header="role: $role
ticket_id: $ticket
from_status: $from
to_status: $to
resume: $resume
tracker_cmd: $TRACKER_CMD${wmode:+
write_mode: $wmode}${seat_note:+
seat_note: $seat_note
seat_note_directive: the seat_note above is an orchestrator directive for THIS spawn — MANDATORY additional duties beyond your base role. Perform them in this spawn and record the evidence as ticket comments before you hand off. For a fastlane Solo-Seat (dev+scoped-tests+self-review): implement, run the ticket-scoped tests YOURSELF, and post a self-review record — there is no separate QAS or review seat behind you except the single combined gate. For the combined gate (review+scoped-tests): run the ticket-scoped tests as part of your review — this ONE gate replaces both the QAS and review seats, so the tests must actually execute here before the ticket enters the merge-queue. For a fastlane BUNDLE Solo-Seat (bundle=<ids> branch=<lead>-auto, ABS-324): you are implementing EVERY ticket in the bundle= roster in THIS one run, all on the single shared branch <lead>-auto. Commit each ticket's changes as a SEPARATE atomic commit tagged with that ticket's id ([ABS-XXX]) so the combined gate and merge-queue can reason per ticket; open ONE PR whose body references ALL bundle ids; and transition each roster member forward as you complete it. For a bundle combined gate (bundle=<ids> per-ticket-attribution): evaluate every bundle ticket and attribute pass/fail PER TICKET — a failure on one ticket must NOT silently pass the others; bounce the failing ticket(s) back and let the passing ones proceed. The bundle still ends at the merge-queue — never self-merge, never issue a merge token.}
note: use tracker_cmd above (NOT the agent-def example adapter) for ALL tracker ops, invoked VERBATIM as printed — do NOT prepend ./ and do NOT wrap it in bash (the Bash allowlist matches the exact path, not a ./-prefixed form, so ./scripts/... is denied under --permission-mode dontAsk); posting your gate-results/decision comment AND performing your exit transition are YOUR duty — the runner does not transition for you"

    # Assemble into the cache (the byte-stable source of truth), then copy to the
    # attempt file.
    if [ "$pkt_mode" = "packet" ]; then
        # ABS-238: the server composes the packet (frontmatter + body + selected
        # comment slots per spec §6). It already carries the latest handoff, so
        # there is NO separate === LATEST HANDOFF === section and NO byte cap —
        # composition replaces truncation, so the ACs are never dropped.
        local pkt
        pkt="$(tracker packet "$ticket" 2>/dev/null || true)"
        {
            printf '%s\n\n%s=== TICKET ===\n' "$header" "$policy_section"
            printf '%s\n' "$pkt"
        } > "$cache"
    else
        # Legacy full-dump path (ORCH_PACKET_MODE=full or an adapter without the
        # packet op). Enforce the soft cap by truncating the ticket-body tail.
        {
            printf '%s\n\n%s=== TICKET ===\n' "$header" "$policy_section"
            # ticket body under cap: keep header (~small) + full handoff, trim body.
            local budget avail body_bytes
            budget="$ORCH_PACKET_MAX_BYTES"
            avail=$((budget - ${#header} - ${#handoff} - 64))
            if [ "$avail" -lt 0 ]; then avail=0; fi
            body_bytes="$(printf '%s' "$dump" | wc -c | tr -d ' ')"
            if [ "$body_bytes" -le "$avail" ]; then
                printf '%s\n' "$dump"
            else
                # BSD/macOS head rejects `-c 0` ("illegal byte count") — an avail of
                # 0 means the header+handoff already fill the budget: emit no body.
                [ "$avail" -gt 0 ] && printf '%s' "$dump" | head -c "$avail"
                printf '\n[packet truncated: over ORCH_PACKET_MAX_BYTES]\n'
            fi
            if [ -n "$handoff" ]; then
                printf '\n=== LATEST HANDOFF ===\n%s\n' "$handoff"
            fi
        } > "$cache"
    fi
    printf '%s' "$sig" > "$meta"
    [ "$pf" = "$cache" ] || cp "$cache" "$pf"
}

# =============================================================================
# Spawn seam invocation (§3.1) + handoff capture (§3.3, §6)
# =============================================================================
# Resolve $ORCH_SPAWN_CMD like the tracker: run a script path via bash.
# =============================================================================
# ABS-225 progress-based watchdog — activity detection helpers
# =============================================================================
# The seat is killed on proven INACTIVITY (ORCH_AGENT_IDLE_TIMEOUT), with an
# absolute MAX_LIFETIME backstop, instead of a static wall-time ceiling every
# larger ticket outgrows (ABS-151 turn-caps, ABS-157 static right-sizing,
# ABS-213 killed at min 60 mid-green pre-release-check). A long ACTIVE verify
# phase survives on its own; a hung seat still dies — sooner than the old wall.
#
# ACTIVITY SOURCE (Design + AC4). The seat is "active" at time T if EITHER:
#   (a) its session-transcript JSONL was written since spawn start — the CLI
#       appends per tool_use/result AND per assistant message, so this advances
#       on ANY tool (Read/Edit/Grep/Bash-start/Bash-result) or model turn; OR
#   (b) the spawn's process tree has a live DESCENDANT — the seam `exec`s
#       `claude` (spawn_pid IS claude), so an idle claude has NO children while a
#       running Bash tool (e.g. a 10-min test suite) appears as a child.
# Signal (b) is the AC4 answer: a single long Bash call writes NO transcript line
# between start and end (a), but its child process IS the activity (b) — so the
# idle threshold need NOT exceed the longest legitimate call (the Design's
# "Prozess-Check ODER Idle-Schwelle > längster Call": we chose the process-check).
# The post-mortem telemetry `.seq` writer (record_spawn_telemetry) is a
# per-tool-call sequence written AFTER the spawn ends — NOT a live signal — so it
# is intentionally not used here. Everything is state-dir/OS-local: no tracker
# comment, no tracker poll (ABS-189). Conservative bias: a persistent child
# (e.g. an MCP daemon under the seat) reads as "active" — the seat then relies on
# MAX_LIFETIME, matching the ticket's "kill only on PROVEN inactivity" thesis.

# file_mtime_epoch <path> — file mtime as epoch seconds, empty/non-zero on miss.
# GNU `stat -c %Y` first, BSD `stat -f %m` fallback, numeric-guarded (same
# portability idiom as lock_age_for, ABS-246).
file_mtime_epoch() {
    [ -e "$1" ] || return 1
    local m
    m="$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null)" || return 1
    case "$m" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$m"
}

# seat_has_live_descendant <pid> — 0 (true) if <pid> has ANY live child process.
# The seam execs `claude`, so <pid> is claude itself: no children when idle, >=1
# while a tool child (a Bash-tool shell / test runner) runs. Direct children are
# enough — a tool's own grandchildren keep the tool shell (a direct child) alive.
seat_has_live_descendant() {
    local kids
    kids="$(pgrep -P "$1" 2>/dev/null)" || return 1
    [ -n "$kids" ]
}

# seat_last_transcript_write <marker> — epoch of the most recent write to ANY CLI
# session transcript since <marker> (a file touched at spawn start), else empty.
# `-newer` is POSIX-portable (avoids the non-portable `-newermt`). Under async
# concurrency the candidate set may include a SIBLING seat's transcript; reading
# a sibling's fresh write only makes THIS seat look active (conservative — capped
# by MAX_LIFETIME), never idle-kills an active seat.
seat_last_transcript_write() {
    local marker="$1" f m best=""
    [ -d "$ORCH_TRANSCRIPT_DIR" ] || return 1
    [ -e "$marker" ] || return 1
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        m="$(file_mtime_epoch "$f" 2>/dev/null || true)"
        [ -n "$m" ] || continue
        if [ -z "$best" ] || [ "$m" -gt "$best" ]; then best="$m"; fi
    done <<EOF
$(find "$ORCH_TRANSCRIPT_DIR" -maxdepth 4 -type f -name '*.jsonl' -newer "$marker" 2>/dev/null)
EOF
    [ -n "$best" ] && echo "$best"
}

# seat_activity_epoch <pid> <marker> <since_epoch> — epoch of the seat's most
# recent detected activity, as MAX(<since_epoch> floor, transcript write, and
# now if a live tool child is present). The <since_epoch> floor makes a seat that
# NEVER shows activity read as idle from spawn start (not from epoch 0).
seat_activity_epoch() {
    local pid="$1" marker="$2" since="$3" best m
    best="$since"
    if seat_has_live_descendant "$pid"; then
        date -u +%s; return 0
    fi
    m="$(seat_last_transcript_write "$marker" 2>/dev/null || true)"
    [ -n "$m" ] && [ "$m" -gt "$best" ] 2>/dev/null && best="$m"
    echo "$best"
}

# watchdog_verdict <waited> <idle_secs> <idle_timeout> <max_lifetime> — the
# progress-watchdog decision as one token: lifetime-kill | idle-kill | continue.
# MAX_LIFETIME is checked FIRST so it beats idle (a looping seat is "active" and
# must still be reaped — ABS-132/151). A threshold <=0 disables that limit.
watchdog_verdict() {
    local waited="$1" idle="$2" idle_to="$3" maxlife="$4"
    if [ "$maxlife" -gt 0 ] && [ "$waited" -ge "$maxlife" ]; then
        echo "lifetime-kill"; return 0
    fi
    if [ "$idle_to" -gt 0 ] && [ "$idle" -ge "$idle_to" ]; then
        echo "idle-kill"; return 0
    fi
    echo "continue"
}

# Wraps the spawn in a hand-rolled watchdog (§6.1): background the spawn, then a
# parallel sleep-then-kill subshell enforces ORCH_AGENT_TIMEOUT. Portable — no
# timeout(1)/gtimeout (not on stock macOS). Stdout is captured to a temp file so
# the caller reads it; a timeout returns non-zero (treated as a spawn failure).
run_spawn_cmd() {
    local role="$1" ticket="$2" pf="$3" to="${4:-}"
    # ABS-122: per-role spawn PROVIDER override (ORCH_SPAWN_CMD_<ROLE>, analog
    # ORCH_MODEL_<ROLE>) — lets individual seats run on an alternative provider
    # adapter (e.g. orchestrator-spawn-cursor.sh) while Claude stays the
    # default. Same seam contract: <role> <ticket> <packet-file>, packet on
    # stdin, handoff on stdout, exit code.
    local spawn_cmd
    spawn_cmd="$(role_env "$role" SPAWN_CMD)"; [ -n "$spawn_cmd" ] || spawn_cmd="$ORCH_SPAWN_CMD"
    # shellcheck disable=SC2206
    local words=($spawn_cmd)
    local cmd="${words[0]:-}"
    [ -n "$cmd" ] || die "ORCH_SPAWN_CMD is empty"

    # Read-only review gate (ABS-57): narrow the spawn's toolset for In Review so
    # the reused system-architect role can review but not edit. Empty for all
    # other spawns -> the seam falls back to the role's own `tools:` frontmatter.
    local tools_env=""
    is_readonly_review_status "$to" && tools_env="$ORCH_REVIEW_TOOLS"

    # Per-seat overrides (ABS-111 A3/B6): ORCH_MAX_TURNS_<ROLE> / ORCH_MODEL_<ROLE>
    # beat the globals; SPAWN_MAX_TURNS_OVERRIDE (handoff-repair, tiny budget)
    # beats everything.
    # Turn-ceiling precedence (highest first): handoff-repair override >
    # per-seat ORCH_MAX_TURNS_<ROLE> > explicit operator-wide ORCH_MAX_TURNS >
    # ABS-156 implementer built-in default > global built-in default.
    local turns model timeout_s
    turns="$(role_env "$role" MAX_TURNS)"
    # retro 2026-07-10: built-in per-seat ceilings sit below the explicit
    # operator-wide cap (a deliberate all-seats cap still wins) but above the
    # ABS-156 tiers, so known-hungry seats stop dying at lean defaults.
    if [ -z "$turns" ] && [ -z "$ORCH_MAX_TURNS_SET" ]; then
        turns="$(builtin_role_max_turns "$role")"
    fi
    if [ -z "$turns" ]; then
        # ABS-156: implementer seats get the higher built-in default UNLESS the
        # operator set an explicit operator-wide cap (that deliberate all-seats
        # cap wins). PILOT-65 AC2: a non-implementer role WITHOUT a measured
        # built-in resolves to the explicit ORCH_MAX_TURNS_DEFAULT_ROLE, NOT a
        # silent fall to the lean 25. An explicit operator-wide ORCH_MAX_TURNS
        # still wins for every seat.
        if [ -n "$ORCH_MAX_TURNS_SET" ]; then
            turns="$ORCH_MAX_TURNS"
        elif is_implementer_role "$role"; then
            turns="$ORCH_MAX_TURNS_IMPLEMENTER"
        else
            turns="$ORCH_MAX_TURNS_DEFAULT_ROLE"
        fi
    fi
    [ -n "${SPAWN_MAX_TURNS_OVERRIDE:-}" ] && turns="$SPAWN_MAX_TURNS_OVERRIDE"
    # ABS-157: per-seat watchdog override ORCH_AGENT_TIMEOUT_<ROLE> beats the
    # global ORCH_AGENT_TIMEOUT (same naming as MAX_TURNS/MODEL). Lets a
    # long-running seat (qas on the full suite) get more room WITHOUT inflating
    # every seat's watchdog and delaying detection of a genuine hang.
    # retro 2026-07-10: built-in per-seat timeouts fill the same slot as the
    # turn ceilings — below an explicit operator-wide watchdog, above the 900
    # built-in default.
    timeout_s="$(role_env "$role" AGENT_TIMEOUT)"
    if [ -z "$timeout_s" ] && [ -z "$ORCH_AGENT_TIMEOUT_SET" ]; then
        timeout_s="$(builtin_role_timeout "$role")"
    fi
    [ -n "$timeout_s" ] || timeout_s="$ORCH_AGENT_TIMEOUT"
    # ABS-225: resolve the progress-watchdog limits. IDLE_TIMEOUT is the
    # inactivity cap; MAX_LIFETIME the absolute backstop — an explicit
    # ORCH_AGENT_MAX_LIFETIME wins, else 2x the resolved role timeout (timeout_s
    # already honors ORCH_AGENT_TIMEOUT_<ROLE> > global, ABS-157), so the legacy
    # timeout knobs keep meaning.
    local idle_timeout max_lifetime
    idle_timeout="$ORCH_AGENT_IDLE_TIMEOUT"
    if [ -n "$ORCH_AGENT_MAX_LIFETIME" ]; then
        max_lifetime="$ORCH_AGENT_MAX_LIFETIME"
    else
        max_lifetime=$(( timeout_s * 2 ))
    fi
    # ABS-121/ABS-128 per-ticket model hint: precedence Env > role-filtered
    # ticket label > role frontmatter > CLI default (the env is the emergency
    # lever and ALWAYS wins; a model:-label downsize only reaches mechanical
    # seats — resolve_spawn_model owns the filter and the run.log event).
    model="$(resolve_spawn_model "$ticket" "$role" "$to")"

    local outfile errfile spawn_pid rc waited
    outfile="$pf.out.$$"
    # D11: spawn stderr is captured, never discarded; kept on failure for diagnosis.
    errfile="$pf.stderr.$$"

    # ABS-194: RE-DERIVE the effective seat cwd here — run_spawn_cmd is the single
    # choke point EVERY spawn passes through (first spawn, ABS-175 salvage-resume,
    # handoff-repair resume). The first-spawn path sets the SPAWN_CWD global in
    # live_spawn; resolve_seat_cwd returns it when set, and otherwise re-derives
    # the ticket worktree identically (worktree_for) so a resume that reached here
    # WITHOUT live_spawn's provisioning still lands in the same tree instead of the
    # main checkout (ABS-166: a be-developer resume ran in the main checkout and
    # its edits were denied). Diagnostic-logged per spawn (structured SEAT-CWD
    # run.log event + human stderr line, mirroring the SESSION-INVALIDATED pattern)
    # so a Cwd loss is immediately visible in run.log.
    local seat_cwd
    seat_cwd="$(resolve_seat_cwd "$ticket" "$to")"
    runlog SEAT-CWD "$ticket" "$role" "$to" "cwd=${seat_cwd:-<main-checkout>}"
    log "spawn cwd for $ticket ($role -> ${to:-?}): ${seat_cwd:-<main-checkout>}"

    # PILOT-26: PRIMARY Live-Spawns emit — the seat OPENS here, at the spawn
    # moment (well under the AC's <2s), before the watchdog wait below. The
    # SEAT-SPAWN marker carries the full identity so the shipper reconcile can
    # heal a missed POST 1:1. Emit BEFORE launching so the panel reflects the
    # seat even if the launch itself is slow.
    local seat_sid seat_started
    seat_sid="$(seat_spawn_id "$ticket" "$role")"
    seat_started="$(timestamp)"
    runlog SEAT-SPAWN "$ticket" "$role" "$to" "phase=open spawn_id=$seat_sid attempt=${SPAWN_ATTEMPT:-1} started_at=$seat_started"
    # PILOT-27 / AC3: on a resume (salvage, REPAIR-HANDOFF, rework) SPAWN_RESUME_ID
    # is the session being resumed — carry it at OPEN so the row records the session
    # even for the repair-respawn path ABS-499 flagged as writing no close-marker.
    # Empty on a first spawn (no session yet) -> null. session_stored is unknown
    # until reap, so it stays null here and is set at the CLOSE below.
    emit_seat_upsert open "$seat_sid" "$ticket" "$role" "$seat_started" "" "" "" "${SPAWN_RESUME_ID:-}" ""

    # ABS-355 AC2: SCRUB the runner's LIVE-STATE env from the seat. These vars
    # (operator-exported at launch) all point INTO the runner's live state dir;
    # if a seat inherits them, its `tests/test-orchestrator.sh` run drives the
    # orchestrator against the LIVE state and its teardown traps rm -rf the live
    # dir — the 2026-07-16 wipes. `env -u` strips them from the child ONLY (the
    # runner's own env is untouched); the spawn adapters do not read any of them,
    # and the seat's tracker falls back to its own worktree snapshot. This is
    # defense-in-depth: the ABS-335 fail-closed guard is then the second line, not
    # the only one. ORCH_ROLE/TICKET/... are set BELOW the scrub so they survive.
    local _scrub=(env -u ORCH_STATE_DIR -u ORCH_STOP_FILE -u ORCH_RUN_LOG \
        -u ORCH_INSTANCE_ID_FILE -u JIRA_TRACKER_STATE)
    # ABS-601 AC5: launch the seat in its OWN process group (bash monitor mode) so
    # any background children it starts (run_in_background / a `&`-detached job) can
    # be reaped as a GROUP at spawn end — even after they reparent to init when the
    # seat's turn ends (reparenting does NOT change the pgid). Without this a seat
    # that backgrounds a long task and exits leaks orphaned processes (ABS-601: an
    # RTE backgrounded the ~15-min suite and awaited a completion notification a
    # one-shot spawn never delivers). `set -m` here affects ONLY this command-
    # substitution subshell; it is restored right after `$!` is captured. If job
    # control is unavailable the child shares the runner's group and the group-reap
    # below simply matches nothing (no live group has id == spawn_pid) — no process
    # outside this spawn is ever targeted (Common Rule 8). Kill-switch: ORCH_REAP_SPAWN_CHILDREN=0.
    local _reap_children="${ORCH_REAP_SPAWN_CHILDREN:-1}"
    [ "$_reap_children" = "1" ] && set -m 2>/dev/null || true
    if [ -f "$cmd" ]; then
        ORCH_ROLE="$role" ORCH_TICKET="$ticket" ORCH_PACKET_FILE="$pf" ORCH_MAX_TURNS="$turns" ORCH_MODEL="$model" ORCH_TOOLS="$tools_env" \
        ORCH_AGENT_TIMEOUT="$timeout_s" ORCH_AGENT_MAX_LIFETIME="$max_lifetime" \
        ORCH_RESUME_SESSION_ID="${SPAWN_RESUME_ID:-}" ORCH_SPAWN_CWD="$seat_cwd" \
            "${_scrub[@]}" bash "${words[@]}" "$role" "$ticket" "$pf" < "$pf" > "$outfile" 2> "$errfile" &
    else
        ORCH_ROLE="$role" ORCH_TICKET="$ticket" ORCH_PACKET_FILE="$pf" ORCH_MAX_TURNS="$turns" ORCH_MODEL="$model" ORCH_TOOLS="$tools_env" \
        ORCH_AGENT_TIMEOUT="$timeout_s" ORCH_AGENT_MAX_LIFETIME="$max_lifetime" \
        ORCH_RESUME_SESSION_ID="${SPAWN_RESUME_ID:-}" ORCH_SPAWN_CWD="$seat_cwd" \
            "${_scrub[@]}" "${words[@]}" "$role" "$ticket" "$pf" < "$pf" > "$outfile" 2> "$errfile" &
    fi
    spawn_pid=$!
    [ "$_reap_children" = "1" ] && set +m 2>/dev/null || true

    # Hand-rolled watchdog (§6.1, ABS-225): poll the spawn's liveness on a 1s
    # base tick. Under the default idle watchdog (ORCH_WATCHDOG_IDLE=1) the kill
    # criterion is INACTIVITY (idle >= ORCH_AGENT_IDLE_TIMEOUT) with an absolute
    # MAX_LIFETIME backstop; the legacy path (=0) keeps the pure wall-time kill at
    # $timeout_s. Liveness + MAX_LIFETIME run every tick; the heavier activity
    # probe (process + transcript scan) is throttled to ORCH_WATCHDOG_POLL. No
    # long-lived `sleep N` subshell and no timeout(1)/gtimeout (not on stock
    # macOS). Portable across BSD + GNU.
    local wd_start wd_marker last_activity next_probe now idle verdict wd_reason wd_extended
    wd_start="$(date -u +%s)"
    wd_marker="$pf.wdstart.$$"
    : > "$wd_marker" 2>/dev/null || true
    last_activity="$wd_start"
    next_probe=0
    wd_extended=""
    waited=0
    while kill -0 "$spawn_pid" 2>/dev/null; do
        now="$(date -u +%s)"
        waited=$(( now - wd_start ))
        if [ "$ORCH_WATCHDOG_IDLE" = "1" ]; then
            # Throttle the activity probe; MAX_LIFETIME is still enforced per tick.
            if [ "$now" -ge "$next_probe" ]; then
                last_activity="$(seat_activity_epoch "$spawn_pid" "$wd_marker" "$wd_start")"
                next_probe=$(( now + ORCH_WATCHDOG_POLL ))
            fi
            idle=$(( now - last_activity )); [ "$idle" -lt 0 ] && idle=0
            verdict="$(watchdog_verdict "$waited" "$idle" "$idle_timeout" "$max_lifetime")"
            case "$verdict" in
                idle-kill)     wd_reason="idle ${idle}s >= ${idle_timeout}s (no activity)" ;;
                lifetime-kill) wd_reason="lifetime ${waited}s >= ${max_lifetime}s (absolute cap)" ;;
                continue)
                    # AC5 third decision — "Verlängerung": the seat is being kept
                    # alive past what the legacy wall-time ($timeout_s) would have
                    # killed it at, because it is still ACTIVE. Log ONCE (not per
                    # tick) so the operator sees the watchdog deliberately extended
                    # it rather than hanging.
                    if [ -z "$wd_extended" ] && [ "$waited" -ge "$timeout_s" ]; then
                        wd_extended=1
                        log "spawn watchdog: extended $ticket ($role) — active ${waited}s past legacy wall-time ${timeout_s}s (idle ${idle}s, cap ${max_lifetime}s)"
                        runlog WATCHDOG "$ticket" "$role" "${to:-}" "extended: active ${waited}s past legacy ${timeout_s}s (idle ${idle}s < ${idle_timeout}s)"
                    fi
                    ;;
            esac
        else
            if [ "$waited" -ge "$timeout_s" ]; then
                verdict="lifetime-kill"; wd_reason="wall-time ${waited}s >= ${timeout_s}s (legacy)"
            else
                verdict="continue"
            fi
        fi
        if [ "$verdict" != "continue" ]; then
            # AC5: the WHY is visible in run.log (idle-kill vs lifetime-kill).
            log "spawn watchdog: $verdict $ticket ($role) — $wd_reason"
            runlog WATCHDOG "$ticket" "$role" "${to:-}" "$verdict: $wd_reason"
            # TERM the spawn AND any children it forked (a bash wrapper won't
            # forward the signal to e.g. a `claude`/`sleep` child, orphaning it),
            # then escalate to KILL if it ignores TERM. pkill -P is on macOS+Linux.
            kill -TERM "$spawn_pid" 2>/dev/null || true
            pkill -TERM -P "$spawn_pid" 2>/dev/null || true
            sleep 1
            kill -KILL "$spawn_pid" 2>/dev/null || true
            pkill -KILL -P "$spawn_pid" 2>/dev/null || true
            break
        fi
        sleep 1
    done
    rm -f "$wd_marker" 2>/dev/null || true

    rc=0
    wait "$spawn_pid" 2>/dev/null || rc=$?

    # ABS-601 AC5: reap any background process the seat left running. With monitor
    # mode above, the spawn led its own process group (pgid == spawn_pid); an
    # orphaned descendant keeps that pgid after it reparents to init, so a
    # group-scoped signal catches it where a parent-scoped `pkill -P` (the children
    # have already reparented) would not. Group-scoped only — never by name/pattern
    # (Common Rule 8); spawn_pid is a pgid this spawn created, so nothing outside the
    # spawn tree is signalled (a stale/no-op set -m leaves no group with this id, so
    # pgrep matches nothing). TERM, brief grace, then KILL.
    if [ "$_reap_children" = "1" ] && pgrep -g "$spawn_pid" >/dev/null 2>&1; then
        runlog SPAWN-REAP "$ticket" "$role" "${to:-}" "orphaned background process(es) survived the seat; TERM/KILL process group $spawn_pid"
        log "spawn reap: $ticket ($role) left background process(es) in group $spawn_pid; terminating"
        pkill -TERM -g "$spawn_pid" 2>/dev/null || true
        sleep 1
        pkill -KILL -g "$spawn_pid" 2>/dev/null || true
    fi

    cat "$outfile" 2>/dev/null || true
    # ABS-151 ROOT CAUSE: run_spawn_cmd runs in the caller's command-substitution
    # subshell (out="$(run_spawn_cmd ...)"), so it CANNOT hand the exit code /
    # captured stderr back through a global. Before this fix the stderr was logged
    # to run.log only (line above) and DISCARDED on the clean-exit-no-handoff path
    # (the `else rm -f "$errfile"`), so record_spawn_crash's marker was opaque —
    # a caller could not distinguish a transient non-zero exit from a permanent
    # empty/unparseable handoff. Persist exit code + stderr tail to a diag file
    # keyed to the packet path (deterministic — both the subshell and the parent
    # attempt_spawn derive it from $pf) so the caller can surface a diagnostic.
    local stderr_tail=""
    [ -s "$errfile" ] && stderr_tail="$(tail -n 5 "$errfile" 2>/dev/null | tr '\n' ' ' | head -c 500)"
    # ABS-265: also persist the Result-JSON error SUBTYPE (error_max_turns,
    # error_during_execution, …) when the CLI's --output-format json stdout is
    # parseable. Before this the subtype survived only in the caller's ephemeral
    # command-substitution buffer; on the idle-kill crash class (ABS-251/254/255)
    # the stderr was empty, so the failure CLASS was lost and diagnosis fell back
    # to lsof/ps on the live process (ABS-245 proxy-stall Befund).
    local result_subtype=""
    result_subtype="$(tr '\n' ' ' < "$outfile" 2>/dev/null \
        | sed -n 's/.*"subtype"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
    {
        printf 'exit=%s\nstderr=%s\n' "$rc" "$stderr_tail"
        [ -n "$result_subtype" ] && printf 'subtype=%s\n' "$result_subtype"
    } > "$pf.diag" 2>/dev/null || true

    # PILOT-26: PRIMARY Live-Spawns emit — the seat CLOSES here, at reap, with the
    # real process exit code + a diagnostic (subtype/stderr). Same spawn_id as the
    # open above, so the endpoint upserts the existing row to completed. A SEAT-SPAWN
    # close marker mirrors it so the shipper reconcile can heal a missed POST.
    local seat_completed seat_diag
    seat_completed="$(timestamp)"
    seat_diag="${result_subtype:-}"
    [ "$rc" -ne 0 ] && seat_diag="exit=$rc${result_subtype:+ subtype=$result_subtype}${stderr_tail:+ stderr: $stderr_tail}"
    # PILOT-27 / AC1+AC2: carry the spawn result's own session_id, and record
    # store_session's AUTHORITATIVE keep/drop verdict in session_stored (via the
    # shared session_stored_verdict predicate), keeping "how many sessions do we
    # lose?" — the SQL query PILOT-24 enabled — exact. PILOT-38: SPAWN_FORCE_POISON
    # carries the birth spawn's denial state into a salvage resume whose OWN output
    # is clean (ABS-254 / ADR-A-0023 rule 3), so the salvage's CLOSE row records the
    # drop store_session actually performs instead of an optimistic "true".
    local seat_out seat_session_id seat_session_stored
    seat_out="$(cat "$outfile" 2>/dev/null)"
    seat_session_id="$(extract_session_id "$seat_out")"
    seat_session_stored="$(session_stored_verdict "$seat_out" "${SPAWN_FORCE_POISON:-0}")"
    runlog SEAT-SPAWN "$ticket" "$role" "$to" "phase=close spawn_id=$seat_sid attempt=${SPAWN_ATTEMPT:-1} started_at=$seat_started completed_at=$seat_completed exit=$rc session_stored=$seat_session_stored"
    emit_seat_upsert close "$seat_sid" "$ticket" "$role" "$seat_started" "$seat_completed" "$rc" "$seat_diag" "$seat_session_id" "$seat_session_stored"
    # PILOT-73: the cadence ops-sweep's report is its ONLY Phase-0 deliverable —
    # persist it to the durable store and emit a greppable summary BEFORE the volatile
    # stdout capture below is (on the success path) deleted. Gated on the synthetic
    # sweep key, so no normal ticket spawn is affected.
    if [ "$ticket" = "$ORCH_OPS_SWEEP_TICKET" ]; then
        ops_sweep_persist_report "$outfile"
    fi
    # ABS-265: keep the stdout (Result-JSON) as evidence on a crash — rc!=0 OR no
    # parseable handoff — mirroring the D11 stderr-kept rule below. The Result-JSON
    # carries subtype/session_id/usage/last-message; retaining it turns an opaque
    # spawn crash into classified evidence (ABS-245). The success path (rc=0 WITH a
    # handoff) still removes it, so a healthy run leaves no *.out.* packet litter.
    if { [ "$rc" -ne 0 ] || [ -z "$(extract_handoff_from_result "$(cat "$outfile" 2>/dev/null)")" ]; } && [ -s "$outfile" ]; then
        log "spawn stdout kept: $outfile (subtype: ${result_subtype:-<none>})"
    else
        rm -f "$outfile" 2>/dev/null || true
    fi
    # D11: on failure keep the captured stderr for diagnosis (was 2>/dev/null
    # before ABS-111 — spawn failures were undiagnosable); log the last line.
    if [ "$rc" -ne 0 ] && [ -s "$errfile" ]; then
        log "spawn stderr kept: $errfile (last: $(tail -1 "$errfile" 2>/dev/null | head -c 200))"
    else
        rm -f "$errfile" 2>/dev/null || true
    fi
    return "$rc"
}

# _json_result_field <stdout> — the raw (still-escaped) JSON `result` string value
# emitted by the default Claude binding, empty when absent. Extracted non-greedily:
# a `sed 's/.*"\(.*\)".*/\1/'` matches to the LAST quote on the line and would
# swallow trailing fields ("session_id" etc.); instead strip up to the opening
# quote, then walk to the first UNescaped closing quote (an embedded \" survives).
# awk = BSD/GNU safe. Shared by extract_handoff_from_result and ops_sweep_result_text.
_json_result_field() {
    printf '%s' "$1" | tr '\n' ' ' \
        | sed -n 's/.*"result"[[:space:]]*:[[:space:]]*"//p' \
        | awk '{
            out = ""; n = length($0)
            for (i = 1; i <= n; i++) {
                c = substr($0, i, 1)
                if (c == "\\") { out = out substr($0, i, 2); i++; continue }
                if (c == "\"") break
                out = out c
            }
            print out
        }' | head -1
}

# extract_handoff_from_result <stdout> — pull the handoff record out of the
# spawn's stdout. The default Claude binding returns --output-format json whose
# `result` field carries the agent's final message; a stub may print the handoff
# directly. We accept either: prefer a `## Handoff` / `kind: handoff` section,
# else the JSON `result` field. Empty when no handoff is present (§6 miss path).
extract_handoff_from_result() {
    local out="$1" section result
    # 1. A handoff section printed directly (## Handoff ... or a kind: handoff block).
    section="$(printf '%s\n' "$out" | awk '
        /^(## Handoff|### .*kind: handoff|kind: handoff)/ { grab = 1 }
        grab { print }
    ')"
    if [ -n "$section" ]; then
        printf '%s' "$section"
        return 0
    fi
    # 2. Fall back to the JSON `result` field (default Claude binding), extracted
    #    non-greedily by _json_result_field (shared with the ops-sweep report).
    result="$(_json_result_field "$out")"
    if printf '%s' "$result" | grep -qiE 'handoff'; then
        # ABS-111 C10 root-cause fix: the value was extracted from a JSON string
        # and still carries \n / \" escapes — decode before it is posted as a
        # tracker comment (this produced literal "\n" in Jira in live run 1).
        printf '%s' "$result" | json_unescape
        return 0
    fi
    return 0
}

# result_is_max_turns <spawn-stdout> — 0 (true) when the CLI result JSON signals
# the spawn ended at the turn cap (subtype=error_max_turns). The trigger for the
# ABS-175 salvage resume: a cap exit is NOT a crash, the work in the session is
# still there to be committed. Robust to exit code (the CLI may exit 0 or !=0 on
# a cap) — we key on the JSON subtype, not on rc.
result_is_max_turns() {
    printf '%s' "$1" | tr '\n' ' ' \
        | grep -q '"subtype"[[:space:]]*:[[:space:]]*"error_max_turns"'
}

# ABS-598: the MUTATING tool set. A denied call to one of these can leave the
# working tree / process state inconsistent with what the model believes it did,
# so resuming the session would build on false assumptions — the session must be
# dropped. A denied READ-only tool (Read, Grep, Glob, …) leaves NOTHING
# inconsistent: the model simply did not see a file. Classifying by the tool's
# mutation property (not by "a denial occurred at all") is what keeps a single
# refused Read from discarding a whole session's context (ABS-598 AC1/AC2).
ORCH_MUTATING_DENIAL_TOOLS="${ORCH_MUTATING_DENIAL_TOOLS:-Write Edit MultiEdit NotebookEdit Bash}"

# result_denied_tools <spawn-stdout> — the `tool_name` of every entry in the CLI
# result JSON's `permission_denials` array, one per line (empty when none were
# denied). The CLI emits `"permission_denials": []` on a clean spawn and a
# non-empty array of `{tool_name, tool_use_id, tool_input}` objects when calls
# were refused.
result_denied_tools() {
    printf '%s' "$1" | tr '\n' ' ' \
        | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | sed -E 's/.*"([^"]*)"[[:space:]]*$/\1/'
}

# result_has_mutating_denial <spawn-stdout> — 0 (true) when at least one DENIED
# tool is a mutating tool (ABS-598). Read-only denials (Read/Grep/Glob/…) and an
# empty array return non-zero: they do NOT poison the session. This replaces the
# old "any non-empty permission_denials array poisons" test.
result_has_mutating_denial() {
    local t
    for t in $(result_denied_tools "$1"); do
        case " $ORCH_MUTATING_DENIAL_TOOLS " in
            *" $t "*) return 0 ;;
        esac
    done
    return 1
}

# result_denial_summary <spawn-stdout> — "tool=<Tool> target=<target>" for the
# FIRST mutating denial in the result JSON, for the SESSION-POISONED log so the
# diagnosis no longer requires reading the packet JSON (ABS-598 AC3). Empty when
# no denied tool is mutating. `target` is the denied call's file_path/command/path
# when present. Runs on the poison path only (rare), so a python3 parse is fine.
result_denial_summary() {
    printf '%s' "$1" | ORCH_MUTATING_DENIAL_TOOLS="$ORCH_MUTATING_DENIAL_TOOLS" python3 -c '
import sys, json, os
mut = set(os.environ.get("ORCH_MUTATING_DENIAL_TOOLS","").split())
raw = sys.stdin.read()
denials = None
for line in raw.splitlines():
    line = line.strip()
    if "permission_denials" not in line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if isinstance(obj, dict) and obj.get("permission_denials"):
        denials = obj["permission_denials"]
        break
if denials is None:
    # single-line result JSON that also carried other fields
    try:
        obj = json.loads(raw)
        denials = obj.get("permission_denials")
    except Exception:
        denials = None
for e in (denials or []):
    if not isinstance(e, dict):
        continue
    t = e.get("tool_name","")
    if t in mut:
        ti = e.get("tool_input") or {}
        tgt = ti.get("file_path") or ti.get("command") or ti.get("path") or ""
        print("tool=%s target=%s" % (t, tgt))
        break
' 2>/dev/null
}

# session_stored_verdict <spawn-stdout> [force_poison] — the AUTHORITATIVE keep/drop
# verdict for a session as the literal "true"/"false", mirroring store_session's
# decision EXACTLY. PILOT-38: the CLOSE seat_spawn recompute must record the SAME
# verdict store_session acts on, so both derive it from this one predicate instead
# of the recompute re-deriving it from its own (salvage) output. `force_poison`=1
# (default 0) forces the drop even when the output itself is clean — the ABS-254 /
# ADR-A-0023 rule-3 salvage+birth-denials corner: a clean salvage resumes a session
# the birth spawn's denials already poisoned, so its OWN output reads "true" while
# store_session drops it. Carrying force_poison in makes the CLOSE row record the
# true drop instead of an optimistic "session_stored=true" that undercounts lost
# sessions (AC2's forensics query). Stored only when session-resume is on, the
# result carries a session id, and the poison guard did not drop it.
session_stored_verdict() {
    local out="$1" force_poison="${2:-0}"
    if [ -z "$(extract_session_id "$out")" ] || [ "${ORCH_SESSION_RESUME:-1}" != "1" ]; then
        printf 'false'; return
    fi
    if [ "${ORCH_SESSION_POISON_GUARD:-1}" = "1" ] \
            && { [ "$force_poison" = "1" ] || result_has_mutating_denial "$out"; }; then
        printf 'false'; return
    fi
    printf 'true'
}

# store_session <spawn-stdout> <session-id> <ticket> <role> <to> — persist the
# session for a later resume, stamped with the active config generation (ABS-117).
#
# ABS-254 / ADR-A-0023 rule 3 — the poison guard. A resume re-reads the live
# permission surface (proven: deny Bash(echo:*) -> spawn -> denied; flip to allow
# -> resume the SAME session -> the call succeeds), but it CANNOT re-read its own
# transcript. A session that hit permission denials carries a history of `denied`
# tool errors and its own conclusion that the environment is broken, so it keeps
# reporting the phantom blocker long after the settings were fixed underneath it
# (consumer report: 6+ spawns, escalating into a demand for blanket write grants).
# No config-generation input can catch this — the poisoned session's config inputs
# are identical to a healthy one's. So: drop the session instead. The next spawn
# for this (ticket, role, status) starts fresh against the fixed permission surface
# with no denial history to inherit; blast radius is exactly the affected sessions,
# and a healthy store is never cold-started (retro 2026-07-10 cost concern upheld).
# Deleting any PREVIOUSLY stored session for the key matters: skipping the write
# alone would leave an older file behind for the next spawn to resume.
#
# The 6th arg `force_poison` (default 0) forces the drop even when `out` itself is
# clean. The ABS-175 salvage resume needs this: it resumes the SAME session id, so
# it inherits the birth spawn's poisoned transcript, but the salvage's OWN result
# carries no new denials — inspecting only the salvage output would re-admit the
# session the birth-spawn store already dropped. The caller captures the birth
# denial state before reassigning `out` and passes it in.
# Kill-switch: ORCH_SESSION_POISON_GUARD=0.
store_session() {
    local out="$1" sid="$2" ticket="$3" role="$4" to="$5" force_poison="${6:-0}"
    if [ "$ORCH_SESSION_POISON_GUARD" = "1" ] && { [ "$force_poison" = "1" ] || result_has_mutating_denial "$out"; }; then
        rm -f "$(session_file "$ticket" "$role" "$to")" 2>/dev/null || true
        # ABS-598 AC3: name the triggering mutating tool + target so the diagnosis
        # does not require reading the packet JSON. On the salvage carry
        # (force_poison=1) the poison lives in the birth transcript, not in this
        # (clean) salvage output, so summarise the birth denial generically.
        local detail
        if [ "$force_poison" = "1" ]; then
            detail="birth-spawn mutating-tool denial (salvage carry)"
        else
            detail="$(result_denial_summary "$out")"
        fi
        runlog SESSION-POISONED "$ticket" "$role" "$to" "mutating-tool denial [${detail:-tool=unknown}]; session not stored (next spawn starts fresh)"
        return 0
    fi
    [ -n "$sid" ] || return 0
    printf '%s\n%s\n' "$sid" "$CONFIG_GENERATION" > "$(session_file "$ticket" "$role" "$to")" 2>/dev/null || true
}

# =============================================================================
# ABS-302: account-switch session invalidation
# =============================================================================
# current_claude_account — the active Claude CLI account identity.
# The CLI writes .claude.json inside the active config directory
# (${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json). Primary identity: the
# oauthAccount.accountUuid field from that file — stable across restarts, changes
# on /login as a different user. Composed as "uuid@configdir" so a same-uuid
# account in a different config dir is also detected. Falls back to the config-dir
# path when .claude.json is absent or has no UUID (pre-login / enterprise-SSO).
current_claude_account() {
    local cfg_dir="${CLAUDE_CONFIG_DIR:-$HOME}"
    local cfg="$cfg_dir/.claude.json"
    if [ -f "$cfg" ]; then
        local uuid
        uuid="$(python3 -c "
import sys, json
try:
    d = json.load(open(sys.argv[1]))
    u = (d.get('oauthAccount') or {}).get('accountUuid','')
    print(u)
except Exception:
    pass
" "$cfg" 2>/dev/null || true)"
        if [ -n "$uuid" ]; then
            echo "${uuid}@${cfg_dir}"
            return
        fi
    fi
    echo "$cfg_dir"
}

# check_account_switch — compare the Claude account stored in the last runner
# run with the current account. If they differ, all cached session ids are
# invalid (the new account cannot resume the old account's sessions — "No
# conversation found with session ID"), so they are deleted and the change is
# recorded in the runlog. Must be called AFTER the session dir is created.
# Kill-switch: ORCH_SESSION_RESUME=0 (sessions disabled → nothing to guard).
check_account_switch() {
    [ "$ORCH_SESSION_RESUME" = "1" ] || return 0
    local acct_file="$SESSIONS_DIR/.account-id"
    local current stored
    current="$(current_claude_account)"
    stored="$(cat "$acct_file" 2>/dev/null || true)"
    if [ -n "$stored" ] && [ "$stored" != "$current" ]; then
        runlog ACCOUNT-SWITCH - - - "stored-account=$stored current-account=$current; invalidating all cached sessions"
        log "Claude account changed ($stored -> $current); cached sessions invalidated (ABS-302)"
        # Remove every session file except the account-id marker itself.
        find "$SESSIONS_DIR" -maxdepth 1 -type f ! -name '.account-id' -delete 2>/dev/null || true
    fi
    printf '%s\n' "$current" > "$acct_file" 2>/dev/null || true
}

# hit_turn_ceiling <stdout> — ABS-151 ROOT CAUSE (operator Befund 2026-07-09):
# the dominant "no parseable handoff" failure is NOT a process crash but the
# CLI hitting the --max-turns ceiling (orchestrator-spawn-claude.sh:203) and
# aborting mid-work. The Claude CLI's --output-format json result reports this
# as `"subtype":"error_max_turns"` (observed: transcript stops after exactly
# ORCH_MAX_TURNS assistant messages, empty result, tokens_out truncated). This
# is a TRANSIENT, actionable fault (raise ORCH_MAX_TURNS_<ROLE> or rely on
# session-resume) — categorically different from a genuine empty handoff, so
# the crash diagnostic must name it. Returns 0 when the ceiling was hit.
hit_turn_ceiling() {
    printf '%s' "$1" | tr '\n' ' ' | grep -qiE '"subtype"[[:space:]]*:[[:space:]]*"error_max_turns"'
}

# attempt_spawn <ticket> <from> <to> <role> <extra-note> — one spawn attempt.
# Sets global attempt_handoff to the extracted handoff. Returns 0 on a clean
# spawn WITH a parseable handoff; non-zero on spawn failure or a missing handoff.
attempt_spawn() {
    # ABS-322: $6 (seat_note) is the per-spawn orchestrator directive, threaded
    # from live_spawn's `note` into build_packet so a collapsed-chain seat's
    # expanded duties actually reach its stdin packet. Empty for normal spawns.
    local ticket="$1" from="$2" to="$3" role="$4" extra="$5" seat_note="${6:-}"
    local pf out rc spawn_exit spawn_stderr spawn_subtype
    attempt_handoff=""
    attempt_diag=""   # ABS-151: failure diagnostic (exit code + stderr) for the crash marker
    pf="$PACKETS_DIR/$ticket.$(date -u +%Y%m%dT%H%M%SZ).$$.txt"
    build_packet "$ticket" "$from" "$to" "$role" "$pf" "$seat_note"
    [ -n "$extra" ] && printf '\n=== PRIOR ATTEMPT ===\n%s\n' "$extra" >> "$pf" || true

    rc=0
    out="$(run_spawn_cmd "$role" "$ticket" "$pf" "$to")" || rc=$?
    # ABS-151: recover the exit code + stderr tail the spawn persisted (keyed to
    # $pf, since run_spawn_cmd ran in the command-substitution subshell above).
    spawn_exit="$(sed -n 's/^exit=//p' "$pf.diag" 2>/dev/null | head -1)"
    spawn_stderr="$(sed -n 's/^stderr=//p' "$pf.diag" 2>/dev/null | head -1)"
    # ABS-265: the Result-JSON error subtype the crash-path persisted (when the
    # CLI stdout was parseable) — name the failure CLASS in the crash marker.
    spawn_subtype="$(sed -n 's/^subtype=//p' "$pf.diag" 2>/dev/null | head -1)"
    rm -f "$pf" "$pf.diag" 2>/dev/null || true

    # ABS-120: cost/usage accounting — one SPAWN-USAGE line per attempt, also
    # on failure paths (fields degrade to empty; the report skips blanks).
    runlog SPAWN-USAGE "$ticket" "$role" "$to" "$(extract_usage_note "$out")"
    # ABS-125: tool/MCP/skill usage telemetry (names only; graceful when the
    # transcript is unreachable — crash, foreign provider, CLI change).
    record_spawn_telemetry "$ticket" "$role" "$to" "$out"

    # A2: remember the session for rework/re-review resume until acceptance —
    # also on failure paths, so handoff-repair below and later bounces can
    # resume instead of paying a cold start.
    local sid
    sid="$(extract_session_id "$out")"
    if [ "$ORCH_SESSION_RESUME" = "1" ]; then
        # ABS-117 stamps the generation; ABS-254 drops a denial-poisoned session.
        store_session "$out" "$sid" "$ticket" "$role" "$to"
    fi

    # ABS-175 turn-cap salvage: the spawn ended AT the turn cap (result JSON
    # subtype=error_max_turns). Do NOT discard the session's work (ABS-129 lost
    # $2.01 that way). Resume the SAME session ONCE with a tiny cap and a fixed
    # "commit + handoff + stop" prompt, then feed the salvage output into the
    # normal handoff extraction below. Guards: needs a session id to resume,
    # ORCH_SESSION_RESUME on, and live mode. Structurally at most ONE salvage per
    # spawn attempt — this is straight-line code (no loop, no re-entry: the
    # resume calls run_spawn_cmd directly, never attempt_spawn), so a salvage
    # that itself caps out is not salvaged again; it falls through to the crash
    # path. A salvage is not a rework bounce (it drives no backward transition,
    # so the rework counter never sees it).
    if result_is_max_turns "$out" && [ "$ORCH_SESSION_RESUME" = "1" ] \
            && [ -n "$sid" ] && [ "$MODE" = "live" ]; then
        # ABS-254 / ADR-A-0023 rule 3: the birth spawn can hit the turn cap AND
        # carry permission denials in the SAME result JSON (a denial loop that
        # burns turns to the ceiling). The salvage resumes the SAME session id, so
        # that poisoned transcript rides into the salvaged session even though the
        # salvage's own output is clean. Capture the birth denial state now, before
        # `out` is reassigned to `out_s` below, and force the drop at the salvage
        # store — otherwise the earlier birth-spawn drop is undone by the re-store.
        local birth_denials=0
        result_has_mutating_denial "$out" && birth_denials=1
        # ABS-605: the salvage budget is STATION-AWARE — the rte/epic-integration
        # station's hard exit is a full suite that the default 5 cannot run.
        local salvage_cap
        salvage_cap="$(salvage_max_turns "$role")"
        intent SALVAGE-RESUME "$ticket" "$role" "$to" "session=$sid cap=$salvage_cap"
        local sp out_s rc_s=0 sid_s
        sp="$PACKETS_DIR/$ticket.salvage.$$.txt"
        printf '%s\n' 'Turn-Limit erreicht — committe was fertig ist, schreibe deinen Handoff, stoppe. Do no further work beyond committing what already exists and emitting your `## Handoff` block.' > "$sp"
        # PILOT-38: carry the birth denials into the salvage's CLOSE recompute so
        # its session_stored records store_session's drop, not the clean salvage's "true".
        out_s="$(SPAWN_RESUME_ID="$sid" SPAWN_MAX_TURNS_OVERRIDE="$salvage_cap" SPAWN_FORCE_POISON="$birth_denials" run_spawn_cmd "$role" "$ticket" "$sp" "$to")" || rc_s=$?
        rm -f "$sp" 2>/dev/null || true
        # ABS-120: the salvage resume is its own billable attempt — account it.
        runlog SPAWN-USAGE "$ticket" "$role" "$to" "$(extract_usage_note "$out_s")"
        # Adopt the salvage result as THE spawn result for the flow below: a
        # salvage that produced a handoff succeeds normally; a salvage that
        # crashed (rc_s!=0) or emitted nothing falls through to the crash path.
        out="$out_s"; rc="$rc_s"
        sid_s="$(extract_session_id "$out_s")"
        [ -n "$sid_s" ] && sid="$sid_s"
        store_session "$out_s" "$sid" "$ticket" "$role" "$to" "$birth_denials"
    fi

    if [ "$rc" -ne 0 ]; then
        # ABS-151: transient-class failure — the spawn process itself exited
        # non-zero (or was killed by the §6.1 watchdog). Surface the exit code +
        # stderr tail so the crash marker distinguishes this from a permanent
        # empty-handoff fault.
        attempt_diag="non-zero exit (exit=${spawn_exit:-$rc})${spawn_subtype:+; result subtype=$spawn_subtype}; stderr: ${spawn_stderr:-<none captured>}"
        return "$rc"
    fi
    attempt_handoff="$(extract_handoff_from_result "$out")"

    # C7/A2c handoff-repair: the spawn exited cleanly but emitted no parseable
    # handoff. Resume the SAME session with a tiny turn budget and ask for just
    # the handoff block — replaces the pre-ABS-111 full duplicate re-spawn.
    if [ -z "$attempt_handoff" ] && [ "$ORCH_SESSION_RESUME" = "1" ] && [ -n "$sid" ] && [ "$MODE" = "live" ]; then
        intent REPAIR-HANDOFF "$ticket" "$role" "$to" "session=$sid"
        local rp out2
        rp="$PACKETS_DIR/$ticket.repair.$$.txt"
        printf 'Your previous reply did not end with the required handoff record. Emit ONLY the `## Handoff` block (From/role, Ticket, commits, summary, status, next) for the work you already completed in this session. If you created commits, name their real hashes on a `commits: <sha> [<sha> ...]` line — the runner verifies every hash you claim and refuses a handoff whose commits do not exist or are contained in no ref (ABS-255). Omit the line if you created no commits. Do no further work or tool calls beyond what is needed to print it.\n' > "$rp"
        out2="$(SPAWN_RESUME_ID="$sid" SPAWN_MAX_TURNS_OVERRIDE=4 run_spawn_cmd "$role" "$ticket" "$rp" "$to")" || true
        rm -f "$rp" "$rp.diag" 2>/dev/null || true
        attempt_handoff="$(extract_handoff_from_result "$out2")"
    fi

    # C7 status evidence: no handoff, but the agent demonstrably advanced the
    # ticket out of the spawned status — that is completed work, not a crash
    # (live run 1: committed work was recorded as SPAWN-CRASH). Synthesize.
    if [ -z "$attempt_handoff" ] && ! ticket_still_in "$ticket" "$to"; then
        attempt_handoff="(runner-synthesized handoff, ABS-111 C7) The $role spawn completed and the ticket advanced out of '$to', but no parseable handoff block was emitted. Success derived from status evidence; see the agent's own comments above for the work record."
        intent SYNTH-HANDOFF "$ticket" "$role" "$to"
    fi

    if [ -z "$attempt_handoff" ]; then
        # ABS-151: no parseable handoff after the C7 repair/synthesis paths.
        # Classify WHY so the crash marker distinguishes a transient hiccup from a
        # permanent fault (the ticket's core goal):
        #   - turn-ceiling exhaustion (operator root cause) -> TRANSIENT: the CLI
        #     hit --max-turns and aborted mid-work; raise ORCH_MAX_TURNS_<ROLE>.
        #   - otherwise -> a genuine empty/unparseable handoff (content/agent fault).
        if hit_turn_ceiling "$out"; then
            attempt_diag="clean exit (exit=${spawn_exit:-0}) but NO parseable handoff — TURN CEILING reached (CLI error_max_turns at --max-turns; transient, raise ORCH_MAX_TURNS_${role} / rely on session-resume). stderr: ${spawn_stderr:-<none captured>}"
        else
            attempt_diag="clean exit (exit=${spawn_exit:-0}) but no parseable handoff (repair/synthesis produced none); stderr: ${spawn_stderr:-<none captured>}"
        fi
        return 1
    fi
    return 0
}

# live_spawn — spawn with retry-once-then-escalate (§6). On success, post the
# handoff back as a kind:handoff comment (open-C: reuse kind:handoff). On a
# second failure/miss, escalate: comment the failure + transition to Blocked.
live_spawn() {
    # ABS-135 ROOT CAUSE: `from` is THREADED in as $6 (dispatch -> spawn_dispatch
    # -> here), NOT read from the process-global $ev_from. $ev_from holds the LAST
    # event parse_event saw; a spawn not immediately preceded by its own parse
    # (the reconcile sweep, drain_pending, a cross-cycle or async spawn) inherited
    # a DIFFERENT ticket's status into its packet from_status (Befund 2, run
    # ABS-126: a story packet carried the epic status "Ready for Epic Acceptance").
    # reconcile derives from RESTING tickets and passes from="" (no direction).
    local ticket="$1" to="$2" role="$3" action="$4" note="$5" from="${6:-}"
    local spawn_started
    # ABS-118: real wall-clock (not ORCH_NOW) — classifies fast-fail crashes.
    spawn_started="$(date -u +%s)"

    # C9: implementer AND review/test seats get a runner-provisioned worktree
    # as cwd — the agent physically cannot touch the main checkout. Scope
    # widened from "Ready for Development"-only after the ABS-102 resume run
    # (ABS-111 hotfix): the In Test qas seat switched the MAIN checkout to the
    # story branch to inspect the work, swapping the running adapter/runner
    # under the live loop. Review/test worktrees carry the ticket's EXISTING
    # work branch (see ensure_worktree branch selection), so reviewers see the
    # story's changes without touching the main checkout.
    # PILOT-63 AC1: spawn_dispatch provisions the worktree BEFORE charging a budget
    # unit and sets SPAWN_CWD, so a provisioning failure there costs no budget. Reuse
    # that result; only (re)provision here when SPAWN_CWD was not pre-set — a direct
    # or resume caller — keeping the C9 fail-closed guarantee as defense-in-depth.
    # FAIL CLOSED (C9): a provisioning failure must NOT fall through to the main
    # checkout — a write-capable implementer under `--permission-mode dontAsk` in
    # the running loop's own tree is exactly live run 1's failure. provision_seat_
    # worktree rests the ticket (SKIP-NOWORKTREE) so the reconcile sweep re-derives
    # and retries next sweep; ORCH_WORKTREE_SPAWNS=0 opts out of isolation.
    if [ -z "${SPAWN_CWD:-}" ] && [ "$ORCH_WORKTREE_SPAWNS" = "1" ] && worktree_eligible_status "$to"; then
        provision_seat_worktree "$ticket" "$role" "$to" || return 1
    fi

    # A2: resume the stored session for this (ticket, role, status) when one
    # exists — rework bounces and re-reviews continue with warm context.
    # ABS-117: only within the SAME config generation. A stored session whose
    # stamp differs (or is missing — legacy pre-ABS-117 file, unknown context)
    # is invalidated and the spawn proceeds fresh; a resumed session would keep
    # its stale permission surface forever.
    SPAWN_RESUME_ID=""
    if [ "$ORCH_SESSION_RESUME" = "1" ]; then
        local sf stored_gen
        sf="$(session_file "$ticket" "$role" "$to")"
        if [ -f "$sf" ]; then
            SPAWN_RESUME_ID="$(sed -n '1p' "$sf" 2>/dev/null || true)"
            stored_gen="$(sed -n '2p' "$sf" 2>/dev/null || true)"
            if [ "$stored_gen" != "$CONFIG_GENERATION" ]; then
                runlog SESSION-INVALIDATED "$ticket" "$role" "$to" "stored=${stored_gen:-none} current=$CONFIG_GENERATION"
                log "session for $ticket/$role/$to invalidated (config generation changed); spawning fresh"
                rm -f "$sf" 2>/dev/null || true
                SPAWN_RESUME_ID=""
            elif [ -n "$SPAWN_RESUME_ID" ]; then
                intent RESUME "$ticket" "$role" "$to" "session=$SPAWN_RESUME_ID"
            fi
        fi
    fi

    intent SPAWN "$ticket" "$role" "$to" "$note"

    # ABS-126: set assignee at spawn start per ORCH_ASSIGNEE_<ROLE> / ORCH_ASSIGNEE.
    # accountIds are never hardcoded — always via env (ADR-A-0010). Graceful no-op
    # when unset. Failure is non-fatal (log + continue spawn).
    local _assignee
    _assignee="$(role_env "$role" ASSIGNEE)"; [ -n "$_assignee" ] || _assignee="${ORCH_ASSIGNEE:-}"
    if [ -n "$_assignee" ]; then
        tracker assign "$ticket" "$_assignee" >/dev/null 2>&1 \
            || log "assign $ticket to $_assignee failed (non-fatal)"
    fi

    # PILOT-26: attempt index feeds the deterministic seat spawn_id
    # (run_id:ticket:role:attempt). The birth spawn is attempt 1; the retry below
    # is attempt 2, so a genuine respawn is a distinct row (no phantom).
    SPAWN_ATTEMPT=1
    if attempt_spawn "$ticket" "$from" "$to" "$role" "" "$note"; then
        tracker comment "$ticket" --kind handoff --actor orchestrator --body "$attempt_handoff" >/dev/null 2>&1 \
            || log "failed to post handoff comment on $ticket"
        intent HANDOFF "$ticket" "$role" "$to"
        # ABS-132: the runner applies the handoff's declared target transition
        # itself (idempotent when the seat already moved the ticket), then
        # loop-guards a parsed-but-unmoved handoff toward respawn escalation.
        handoff_followthrough "$ticket" "$to" "$role" "$attempt_handoff"
        [ "$action" = "SPAWN-NOTIFY" ] && notify "${ORCH_NOTIFY_TICKET:-$ticket}" "$role check complete for $ticket ($to)" || true
        record_spawn_result "$ticket" "$to" 0 $(( $(date -u +%s) - spawn_started ))
        return 0
    fi

    # First attempt failed — retry once with the failure noted in the packet (§6).
    # The retry is always a FRESH session: resuming the session that just
    # failed/timed out would repeat the failure mode (A2 scope note).
    SPAWN_RESUME_ID=""
    log "spawn attempt 1 failed for $ticket (role=$role); retrying once"
    intent RETRY "$ticket" "$role" "$to"
    SPAWN_ATTEMPT=2   # PILOT-26: retry is a distinct seat spawn_id
    if attempt_spawn "$ticket" "$from" "$to" "$role" "attempt 1 failed (spawn non-zero or missing handoff); retrying" "$note"; then
        tracker comment "$ticket" --kind handoff --actor orchestrator --body "$attempt_handoff" >/dev/null 2>&1 \
            || log "failed to post handoff comment on $ticket"
        intent HANDOFF "$ticket" "$role" "$to"
        # ABS-132: the runner applies the handoff's declared target transition
        # itself (idempotent when the seat already moved the ticket), then
        # loop-guards a parsed-but-unmoved handoff toward respawn escalation.
        handoff_followthrough "$ticket" "$to" "$role" "$attempt_handoff"
        [ "$action" = "SPAWN-NOTIFY" ] && notify "${ORCH_NOTIFY_TICKET:-$ticket}" "$role check complete for $ticket ($to)" || true
        record_spawn_result "$ticket" "$to" 0 $(( $(date -u +%s) - spawn_started ))
        return 0
    fi

    # Second failure — v3 crash path (ABS-74, replaces the §6 escalate-to-
    # Blocked: in v3 Blocked spawns the TDM, which is the wrong seat for a
    # crashing spawn, and leaving Blocked would also stop the sweep from
    # retrying). The ticket RESTS in place; the sweep re-derives; the marker
    # comments accumulate into the consecutive-crash escalation.
    # ABS-203: before treating this as a crash, try the write-light Path-B
    # enrichment completion. When the epic's children already exist (child-count
    # > 0) the re-visit's dedup is a no-op and the observed ABS-181 failure is a
    # tracker-write DENIAL on the seat's own exit transition — the runner emits
    # the completion signal itself (lightest path) rather than crash-and-re-cycle.
    # A full-write first enrichment (child-count == 0) is NOT eligible and follows
    # the crash path so no children are dropped (AC3).
    if writelight_enrichment_complete "$ticket" "$to" "$role"; then
        record_spawn_result "$ticket" "$to" 0 $(( $(date -u +%s) - spawn_started ))
        return 0
    fi
    log "spawn failed twice for $ticket (role=$role); recording crash marker (ABS-74)"
    # ABS-118: one fast-fail/backoff bookkeeping entry per CRASH (attempt+retry
    # count once, architect F2), measured over the whole live_spawn.
    record_spawn_result "$ticket" "$to" 1 $(( $(date -u +%s) - spawn_started ))
    # ABS-151: pass the last attempt's diagnostic (exit code + stderr, or the
    # empty-handoff classification) so the crash marker distinguishes a transient
    # hiccup from a permanent fault instead of an opaque "spawn failed twice".
    record_spawn_crash "$ticket" "$to" "$role" "$attempt_diag"
    return 1
}

# =============================================================================
# Poll cycle
# =============================================================================
# process_events — parse & dispatch one batch of adapter `events` output.
process_events() {
    local raw="$1" line key
    # Read line by line without a subshell (so pending-set/budget mutations
    # persist). bash 3.2 safe.
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        parse_event "$line" || continue
        key="$ev_ticket|$ev_to|$ev_at"
        case "$SEEN_EVENTS" in
            *"[$key]"*) continue ;;   # dedupe by (ticket_id, to, at) §1.4
        esac
        SEEN_EVENTS="$SEEN_EVENTS[$key]"
        # ABS-308: phantom-event guard. A resting ticket can re-surface from the
        # adapter's snapshot diff as a bogus status-change event whose `from`
        # oscillates over the ticket's PAST statuses (blank -> Ready for
        # Development -> In Review -> Needs PO Decision -> ...) while its REAL
        # status never moved — e.g. an events-snapshot drift (two runners sharing
        # JIRA_TRACKER_STATE, or a lagging JQL sweep). Each such phantom used to
        # spawn a paid no-op seat and stamp an oscillating from_status into the
        # packet (consumer BUSCH-54: 17 po-agent spawns in 24h on one resting
        # Backlog story). Cross-check a non-creation event against the ticket's
        # ACTUAL last recorded transition: if no real transition landed in `to`,
        # the claimed change never happened — drop it (no spawn, no oscillation).
        # Creation events (from=null) and real transitions (incl. collapsed
        # multi-step, whose net `to` == the last real transition's `to`) pass.
        if [ "$ORCH_PHANTOM_EVENT_GUARD" != "0" ] \
           && [ "$ev_from" != "null" ] && [ -n "$ev_from" ]; then
            local _ph_pair _ph_lt
            _ph_pair="$(last_transition_pair "$(tracker get "$ev_ticket" 2>/dev/null || true)")"
            _ph_lt="${_ph_pair##*$'\t'}"
            if [ "$_ph_lt" != "$ev_to" ]; then
                runlog SKIP-PHANTOM-EVENT "$ev_ticket" - "$ev_to" "from=$ev_from no real transition into '$ev_to' (dump last='$_ph_pair')"
                continue
            fi
        fi
        local drc=0
        dispatch "$ev_ticket" "$ev_to" "$ev_from" || drc=$?
        if [ "$drc" -eq 3 ]; then
            pending_add "$ev_ticket" "$ev_to" "$ev_from"
        fi
        if [ "$BUDGET_HALT" -eq 1 ]; then break; fi
    done <<EOF
$raw
EOF
}

# heal_state_dir — ABS-355 AC3: self-heal a state dir that vanished mid-run.
# The 2026-07-16 incident wiped $ORCH_STATE_DIR from under a running runner (a
# stale seat checkout's test teardown rm -rf'd the inherited dir). Every
# subsequent acquire_lock/run.log write then silently no-op'd or fail-closed and
# the runner spun forever owning nothing. Detect the loss (the dir OR our own
# instance-id marker is gone), recreate the base structure, re-stamp OUR marker
# (we own it — it was wiped, not taken; the ABS-335 mismatch guard only fires on
# a DIFFERING persisted id, never on an absent one), and emit a WARN event.
# Idempotent and cheap: a no-op on the normal path.
heal_state_dir() {
    # ABS-183: an operator override never persists a marker — for source=override
    # only the DIRECTORY is heal-worthy; an absent marker file is the normal state.
    if [ "${ORCH_INSTANCE_ID_SOURCE:-}" = "override" ]; then
        [ -d "$ORCH_STATE_DIR" ] && return 0
    elif [ -d "$ORCH_STATE_DIR" ] && [ -f "$ORCH_INSTANCE_ID_FILE" ]; then
        return 0
    fi
    # ABS-393 AC3: forensic accounting — record WHICH components are missing BEFORE we
    # recreate them, and whether the WHOLE dir vanished (full wipe) or only parts of its
    # substructure (partial wipe — the 2026-07-17 incident: locks/sessions/packets/
    # instance-id/spawn-ledger gone, run.log survived). A blanket "was missing" WARN hid
    # exactly which live subtrees were lost; this emits a per-component forensic line.
    local _scope _missing="" _ledger
    if [ -d "$ORCH_STATE_DIR" ]; then _scope="partial"; else _scope="full"; fi
    _ledger="$(daily_ledger)"
    [ -d "$ORCH_STATE_DIR" ]         || _missing="$_missing state-dir"
    [ -d "$LOCKS_DIR" ]              || _missing="$_missing locks/"
    [ -d "$PACKETS_DIR" ]           || _missing="$_missing packets/"
    [ -d "$SESSIONS_DIR" ]          || _missing="$_missing sessions/"
    [ -f "$ORCH_INSTANCE_ID_FILE" ] || _missing="$_missing instance-id"
    [ -f "$_ledger" ]               || _missing="$_missing spawn-ledger"

    mkdir -p "$ORCH_STATE_DIR" "$LOCKS_DIR" "$PACKETS_DIR" "$SESSIONS_DIR" 2>/dev/null || true
    if [ ! -f "$ORCH_INSTANCE_ID_FILE" ] && [ -n "${ORCH_INSTANCE_ID:-}" ] \
        && [ "${ORCH_INSTANCE_ID_SOURCE:-}" != "override" ]; then
        printf '%s\n' "$ORCH_INSTANCE_ID" > "$ORCH_INSTANCE_ID_FILE" 2>/dev/null || true
    fi

    # ABS-393 AC4: the spawn-ledger is budget-critical — recreating it EMPTY would reset
    # the day counter to 0 and silently re-open the full daily spawn budget. Reconstruct
    # it from run.log instead of letting it fall to 0.
    local _rebuilt=""
    if [ ! -f "$_ledger" ]; then
        _rebuilt="$(rebuild_daily_ledger "$_ledger")"
    fi

    local _msg="state-dir self-heal ($_scope wipe): recreated${_missing:- (nothing missing)}"
    if [ -n "$_rebuilt" ] && [ "$_rebuilt" -gt 0 ] 2>/dev/null; then
        _msg="$_msg; spawn-ledger reconstructed from run.log ($_rebuilt entries — budget preserved)"
    fi
    log "WARN $_msg (ABS-355/ABS-393)"
    runlog WARN - - - "$_msg (ABS-355/ABS-393)"
}

# one_cycle — a single poll pass: kill-switch check, drain pending (§5.1),
# poll events, reconciliation sweep on cadence (§5.1). <return 10> tells the
# caller to stop the loop (kill-switch or budget halt).
one_cycle() {
    CYCLE=$((CYCLE + 1))
    LIVE_SPAWNS=0        # legacy synchronous cap counter (per-cycle). Under async
                         # spawns (A1) the real cap is live_spawn_count() over
                         # SPAWN_PIDS, which spans cycles; this stays for the
                         # ORCH_ASYNC_SPAWNS=0 path.
    DISPATCHED_CYCLE=""  # reset the per-cycle double-act guard

    heal_state_dir       # ABS-355 AC3: recreate a state dir wiped from under us

    if [ -f "$ORCH_STOP_FILE" ]; then
        log "kill-switch present ($ORCH_STOP_FILE); finishing, no new spawns; exit 0"
        return 10
    fi

    # Retry cap-deferred events first (§5.1), then reconciliation on cadence,
    # then the fresh poll.
    drain_pending

    # Reconciliation sweep: once on startup, then on cadence (§5.1). The startup
    # sweep is the crash-safe net when a prior runner consumed the events but died
    # before spawning. reconcile_due() picks the cadence (wall-clock vs cycle-count).
    local reconciled=0
    if [ "$BUDGET_HALT" -eq 0 ] && reconcile_due; then
        LAST_RECONCILE_TS="$(date +%s)"
        reconcile
        reconciled=1
    fi

    if [ "$BUDGET_HALT" -eq 0 ]; then
        # poll_events blocks up to the cap in wait-mode (event-driven dispatch),
        # else an immediate read; it assigns $POLL_RAW + $POLL_DID_WAIT (globals,
        # so the main-loop sleep decision survives — no $() subshell).
        poll_events
        process_events "$POLL_RAW"
    fi

    if [ "$BUDGET_HALT" -eq 1 ]; then return 10; fi

    # PILOT-47 AC1: in DRAIN mode, end the run cleanly (exit 0, NOT the exit-75
    # budget-pause) once nothing is in-flight. A completed reconcile sweep that
    # dispatched no spawn (SWEEP_SPAWN_COUNT reset at the sweep's start, bumped by
    # every reconcile+poll spawn since), with no live seat and an empty retry set,
    # means the pipeline has drained — only held intake remains. Gated on a real
    # sweep this cycle so a between-cadence cycle cannot declare a false settle.
    if [ "$DRAIN_MODE" -eq 1 ] && [ "$reconciled" -eq 1 ] \
        && [ "${SWEEP_SPAWN_COUNT:-0}" -eq 0 ] && [ "$(live_spawn_count)" -eq 0 ] \
        && [ -z "${PENDING// /}" ]; then
        DRAIN_COMPLETE=1
        runlog DRAIN-COMPLETE - - - "spawn budget drained; no in-flight work remains — clean run end (PILOT-47). $(spawn_budget_health) extends=$SPAWN_BUDGET_EXTENDS"
        log "drain complete: in-flight work finished after the soft spawn cap; ending run cleanly (PILOT-47)"
        return 10
    fi
    return 0
}

# =============================================================================
# ABS-183 — stable per-run instance identity (spec §4.1)
# =============================================================================
# Give each runner a unique id so competing claims can be told apart even when
# machines share one tracker service account. Zero external deps (ADR-A-0009):
# hostname + pid + a short random from /dev/urandom (bash $RANDOM fallback).
mint_instance_id() {
    local host rand
    host="${HOSTNAME:-$(hostname 2>/dev/null || echo unknown)}"
    if [ -r /dev/urandom ]; then
        rand="$(LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom 2>/dev/null | head -c 8)"
    fi
    [ -n "${rand:-}" ] || rand="$(printf '%04x%04x' "$RANDOM" "$RANDOM")"
    printf '%s-%s-%s' "$host" "$$" "$rand"
}

# mint_run_id — unique run identifier for per-run artifact separation (ABS-347).
# Format: YYYYMMDDTHHmmss-<pid>-<rand4>  (URL-safe, time-sortable, human-readable)
mint_run_id() {
    printf '%s-%s-%04d' "$(date -u +%Y%m%dT%H%M%S)" "$$" "$((RANDOM % 10000))"
}

# init_run_id — assign ORCH_RUN_ID and emit the RUN-START run.log header (ABS-347).
# Default-on per ADR-A-0010; escape hatch: ORCH_RUN_ID_SEPARATION=0 restores the
# legacy single-stream behavior (no run-ID minted, no RUN-START event emitted).
# Called once in main() after state dir creation and the ABS-335 instance-id guard.
init_run_id() {
    [ "${ORCH_RUN_ID_SEPARATION:-1}" = "1" ] || return 0
    [ -n "${ORCH_RUN_ID:-}" ] || ORCH_RUN_ID="$(mint_run_id)"
    runlog RUN-START - - - "run_id=${ORCH_RUN_ID}"
}

# resolve_instance_id — set $ORCH_INSTANCE_ID for this run. Precedence:
#   1. operator env override (used verbatim, never minted-over / persisted-over),
#   2. persisted file reused verbatim  — the identity invariant: a restart must
#      NOT re-mint, else the runner self-yields to its own live claims for up to
#      one TTL (spec §4.1),
#   3. fresh mint, persisted for later cycles/restarts.
# Also sets $ORCH_INSTANCE_ID_SOURCE (override|reused|minted) for the log line.
resolve_instance_id() {
    if [ -n "${ORCH_INSTANCE_ID:-}" ]; then
        ORCH_INSTANCE_ID_SOURCE="override"
        return 0
    fi
    if [ -s "$ORCH_INSTANCE_ID_FILE" ]; then
        ORCH_INSTANCE_ID="$(head -n1 "$ORCH_INSTANCE_ID_FILE")"
        if [ -n "$ORCH_INSTANCE_ID" ]; then
            ORCH_INSTANCE_ID_SOURCE="reused"
            return 0
        fi
    fi
    ORCH_INSTANCE_ID="$(mint_instance_id)"
    ORCH_INSTANCE_ID_SOURCE="minted"
    mkdir -p "$(dirname "$ORCH_INSTANCE_ID_FILE")" 2>/dev/null || true
    printf '%s\n' "$ORCH_INSTANCE_ID" > "$ORCH_INSTANCE_ID_FILE"
}

# =============================================================================
# Main
# =============================================================================
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --dry-run) MODE="dry-run"; shift ;;
            --live)    MODE="live"; shift ;;
            --once)    ONCE=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die "unknown argument: $1 (see --help)" ;;
        esac
    done
}

usage() {
    cat <<'EOF'
orchestrator.sh — event-loop Coordinator (spec: specs/ABS-36-orchestrator-spec.md)

Usage: scripts/orchestrator.sh [--dry-run|--live] [--once]

  --dry-run   (default) log spawn INTENTS only; spawn nothing.
  --live      route intents to the spawn adapter ($ORCH_SPAWN_CMD).
  --once      run a single poll cycle then exit (tests / manual smoke).

Kill switch: touch work/.orchestrator-stop to halt at the next cycle top.

Exit codes (ABS-455 budget-pause restart handshake):
  0   clean stop (kill-switch, --once, ORCH_MAX_CYCLES, or a completed DRAIN — the
      per-run SOFT cap was reached and all in-flight work finished, PILOT-47).
  75  budget pause — a HARD backstop (the per-DAY ledger, or the absolute per-run
      ceiling = soft cap x ORCH_SPAWN_BUDGET_HARD_MULTIPLE) tripped (ADR-A-0009);
      the run stopped cleanly for human cost review. A supervisor wrapper MAY
      restart the runner on this code; the runner persists+logs a restart counter
      (work/.orchestrator/budget-restart-count) so the cost gate stays auditable
      and is NOT auto-lifted. Override the code via ORCH_BUDGET_PAUSE_EXIT_CODE.
  1   fatal error (die).
EOF
}

main() {
    parse_args "$@"
    mkdir -p "$ORCH_STATE_DIR" "$LOCKS_DIR" "$PACKETS_DIR" "$SESSIONS_DIR"
    SPAWN_BUDGET="$ORCH_MAX_SPAWNS_PER_RUN"
    # PILOT-47: baseline the Done-count watermark at run start so the FIRST
    # auto-extend compares progress against the run's starting board, not against
    # the moment the soft cap is first hit.
    DONE_AT_LAST_CHECK="$(count_done_tickets)"; case "$DONE_AT_LAST_CHECK" in ''|*[!0-9]*) DONE_AT_LAST_CHECK=0 ;; esac
    resolve_instance_id   # ABS-183: stable per-run identity (spec §4.1)
    # ABS-335: fail-closed instance-id guard (ADR-A-0026 P13). Checked ONCE at
    # startup (not on every run.log append). A PERSISTED instance-id that is not
    # ours means this runner would append its intents/events into another
    # instance's run.log/state — the 2026-07-16 near-miss. Fresh runs mint the
    # file themselves and restarts reuse it verbatim (both match resolve above),
    # and a fresh operator override with no file persisted proceeds; only a
    # genuine cross-instance collision (file exists, differs) reaches here, and it
    # dies before the first run.log write, leaving the foreign log byte-identical.
    if [ -s "$ORCH_INSTANCE_ID_FILE" ]; then
        _persisted_iid="$(head -n1 "$ORCH_INSTANCE_ID_FILE")"
        if [ -n "$_persisted_iid" ] && [ "$_persisted_iid" != "$ORCH_INSTANCE_ID" ]; then
            die "instance-id mismatch: state dir '$ORCH_STATE_DIR' is owned by instance '$_persisted_iid' but this runner is '$ORCH_INSTANCE_ID' (source=$ORCH_INSTANCE_ID_SOURCE) — refusing to write run.log/state (ABS-335)"
        fi
        unset _persisted_iid
    fi
    # ABS-302 account handling runs AFTER the ABS-335 guard: check_account_switch
    # writes a runlog ACCOUNT-SWITCH event, deletes cached session files and
    # rewrites .account-id — all inside $ORCH_STATE_DIR. Before the guard, a
    # mismatched runner would mutate the FOREIGN instance's state on its way out.
    check_account_switch  # ABS-302: invalidate sessions when Claude account changed
    invalidate_sessions_on_account_switch  # ABS-302: wipe session store on CLI account change
    init_run_id   # ABS-347: mint ORCH_RUN_ID and emit RUN-START as the first run.log event
    # PILOT-81: refuse a live start on a non-release / dirty harness checkout, and
    # stamp the resolved harness version (tag+SHA) into the run.log head. Runs after
    # init_run_id so RUN-START is first and HARNESS-VERSION lands in the header.
    check_harness_release

    log "starting (mode=$MODE, interval=${ORCH_POLL_INTERVAL}s, tracker=$TRACKER_CMD)"
    log "instance-id: $ORCH_INSTANCE_ID (source=$ORCH_INSTANCE_ID_SOURCE)"
    # ABS-92 provenance: which harness governs, and which repo is the work target
    # (target == harness in single-repo mode).
    log "provenance: harness=$ORCH_HARNESS_HOME target=$ORCH_STATE_ROOT"
    # retro 2026-07-10: align the target-checkout allowlist with the worktree
    # grants before the first seat spawns (single source; see the function doc).
    provision_target_settings
    # ABS-224: install the pre-commit guard so no seat can commit to local main.
    provision_local_main_guard
    # PILOT-66 AC3: install the post-checkout guard so no seat leaves the main
    # checkout's HEAD moved off the protected branch (blocks `git worktree add`).
    provision_main_head_guard
    # PILOT-79: install the commit-msg guard so a seat's story-branch commit cannot
    # reach the epic branch without its [PREFIX-XXX] tag (RTE bisect mapping).
    provision_ticket_tag_guard
    # S4/PILOT-30: resolve the events-wait long-poll capability ONCE per run (like
    # the packet probe). Sets $EVENTS_WAIT_ACTIVE, consumed by one_cycle/poll_events.
    probe_events_wait_capability

    if [ "$ONCE" -eq 1 ]; then
        one_cycle || true
        # A1: --once keeps its synchronous post-conditions (tests assert right
        # after return) — drain background spawns before returning.
        wait_for_spawns
        emit_run_usage_rollup   # ABS-165: RUN-USAGE rollup at run end
        [ "$BUDGET_HALT" -eq 1 ] && exit_budget_pause   # ABS-455: distinct exit code
        return 0
    fi

    # ORCH_MAX_CYCLES (default 0 = unbounded): stop cleanly after N cycles. A
    # test hook for deterministic multi-cycle scenarios (§5.1 defer -> retry)
    # without racing a kill-switch timer. 0 keeps the production infinite loop.
    local max_cycles="${ORCH_MAX_CYCLES:-0}"
    while true; do
        # `|| rc=$?` captures one_cycle's rc without tripping `set -e` (a bare
        # `one_cycle` returning 10 would abort the script with status 10 before
        # `rc=$?` ran — the clean-stop signal must not become a non-zero exit).
        local rc=0
        one_cycle || rc=$?
        if [ "$rc" -eq 10 ]; then
            wait_for_spawns
            emit_run_usage_rollup   # ABS-165: RUN-USAGE rollup at run end
            # ABS-455: a budget halt exits with the restart-handshake code + one
            # clear exit line; a kill-switch stop keeps the clean exit 0.
            [ "$BUDGET_HALT" -eq 1 ] && exit_budget_pause
            exit 0
        fi
        if [ "$max_cycles" -gt 0 ] && [ "$CYCLE" -ge "$max_cycles" ]; then
            wait_for_spawns
            emit_run_usage_rollup   # ABS-165: RUN-USAGE rollup at run end
            [ "$BUDGET_HALT" -eq 1 ] && exit_budget_pause   # ABS-455
            exit 0
        fi
        # S4/PILOT-30: in events-wait mode the between-cycle pacing was ALREADY
        # provided by the blocking long-poll inside one_cycle (POLL_DID_WAIT=1), so
        # skip the sleep; otherwise (interval-poll or a degraded wait) sleep as before
        # — byte-identical to pre-S4 when the capability is absent (AC3).
        if [ "${POLL_DID_WAIT:-0}" -ne 1 ]; then
            sleep "$ORCH_POLL_INTERVAL"
        fi
    done
}

# Run the loop only when executed directly; when sourced (unit tests, e.g.
# tests/test-station-guard.sh) the functions load without starting main.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
