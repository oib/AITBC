# Orchestrator State-Dir Marker Inventory (ABS-522 / epic ABS-514)

Every file/dir class the runner writes under `$ORCH_STATE_DIR` (`work/.orchestrator*`),
classified per [ADR-A-0026](../../adrs/agentic/ADR-A-0026-first-class-orchestration-state.md):
filesystem markers are the prose-reconstruction substrate that ADR-A-0026 migrates into
first-class typed backend state. This inventory FREEZES the surface — a NEW marker class
in `scripts/` fails `tests/tooling/test-orchestrator-marker-allowlist.sh` until it is added here
(and classified) deliberately. The migration itself is owned by ABS-229 Phase 2; this
document only pins what exists and where it should go.

Naming: `<prefix>-` entries are per-ticket/per-day families (`blocker-<ticket>`,
`spawn-ledger-<date>`); bare entries are singletons; `<name>/` entries are directories.

## Counters (ADR-A-0026 P4 — migrate to typed backend columns)

| Marker | Purpose |
|--------|---------|
| `budget-restart-count` | budget-pause restart handshake counter (ADR-A-0009) |
| `followup-budget` | per-epic follow-up budget state |
| `spawn-ledger-` | per-day spawn ledger (wipe-resistant, ABS-393) |
| `escalation-` | per-ticket escalation budget (ADR-A-0018) |
| `escalation-workcredit-` | escalation work-credit counter (ADR-A-0018) |
| `ops-sweep-last` | cadence-triggered ops-sweep last-run epoch (PILOT-42) |

## Leases and locks (ADR-A-0026 P10 — migrate to backend leases)

| Marker | Purpose |
|--------|---------|
| `locks/` | per-ticket single-flight spawn locks |
| `worktree.lock` | worktree provisioning mutex |
| `probe-inflight` | outage probe single-flight claim (ABS-118) |
| `claim-warn-` | multi-orchestrator claim-age warning de-dup (ABS-181) |

## Crash / repair markers (ADR-A-0026 P13 — replaced by restart-reconcile)

| Marker | Purpose |
|--------|---------|
| `blocker-` | per-ticket blocker marker (TDM triage) |
| `backoff-` | per-ticket crash backoff (ABS-118) |
| `wtfail-` | per-ticket worktree-provisioning failure counter (PILOT-66: count → backoff → escalate after N) |
| `halt-` | per-ticket escalation halt (ABS-118) |
| `outage` | outage pause marker + probe schedule; holds a real state string while paused — empty/`0` = cleared, no pause (ABS-118; PILOT-74) |
| `stuck-state` | stuck-detector state (ABS-116) |
| `standstill-state` | liveness-watchdog state (ABS-312) |
| `standstill-episode` | liveness-watchdog episode marker (ABS-312) |
| `local-main-drift` | local-main drift-guard finding (PILOT-3: checked against the active remote) |
| `fastfail` | fastlane eject fast-fail burst counter; reset to `0` in place while spawning continues — `0`/empty = cleared (no alarm), a real value = run paused (PILOT-74) |

> **Content rule (PILOT-74):** The run-status collector reads marker VALUE, not existence,
> for `fastfail` and `outage`. An empty or `0`-valued file is a cleared/reset state — not a
> human gate. Only a real, non-empty, non-`0` value raises the `run — paused` gate line (which
> also names the value). Found on first production use: a `fastfail` file containing `0` (burst
> counter reset in place by the runner) triggered a false human-gate alarm. Interim fix;
> ABS-579 typed fields are the end state.

## Legitimately local (stays runner-side; not ADR-A-0026 migration targets)

| Marker | Purpose |
|--------|---------|
| `run.log` | append-only run log (operator forensics; ORCH_RUN_LOG) |
| `telemetry/` | spawn telemetry `.seq` stream (ABS-125) |
| `packets/` | spawn packet copies (ABS-135) |
| `ops-sweep-reports/` | durable cadence ops-sweep reports — the shadow-phase deliverable, kept for Phase-0 acceptance (PILOT-73) |
| `sessions/` | session-resume records (ABS-111 A2) |
| `instance-id` | runner instance identity (multi-orchestrator) |
| `.claude-account` | account fingerprint for session invalidation (ABS-302) |
| `shipper-cursor` | backend command-queue consumer cursor (ABS-354) |
| `shipper-executed-commands` | executed-command receipt de-dup (ABS-354) |
| `fastlane-bundle-` | per-lead fastlane bundle roster (ABS-324) |
| `spawn-pid-ledger` | live spawn PID ledger (kill-guard scope, ABS-243) |

The orchestrator kill-switch stop file lives OUTSIDE the state dir (`ORCH_STOP_FILE`,
operator-owned) and is deliberately not part of this inventory.
