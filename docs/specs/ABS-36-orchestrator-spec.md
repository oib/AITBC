# ABS-36 Design Spec — Orchestrator Event Loop

**Ticket**: ABS-36 (this spec is subtask ABS-51) · **Status**: accepted (human, 2026-07-04) · **Date**: 2026-07-03
**Author role**: BSA / System Architect · **Gates**: ABS-52 (runner) · ABS-53 (spawn seam) · ABS-54 (safety) · ABS-55 (E2E dry-run)

Decision record for the **Coordinator** described in [BLUEPRINT §11](../../blueprint/BLUEPRINT.md#11-orchestration-model)
— the single component that turns tracker status-change events into fresh-subagent spawns and advances
the status machine. This spec pins the contracts the implementation subtasks (ABS-52..55) must not
re-decide. It is **design only**: no runner code ships under ABS-51.

The orchestrator is the runtime realization of three standing invariants it must not weaken:

- **Fresh subagent per task** (ADR-A-0002 / §12): clean context in, handoff record out.
- **Active tracking** (ADR-A-0006 / §14): every status transition is a workflow trigger.
- **Adapter-only tracker access** (ADR-A-0007 / §18): the runner speaks the nine canonical
  operations of [`task-tracking.md`](../../profiles/neutral/adapters/task-tracking.md) through `TRACKER_CMD`
  — never touches `work/tickets/*.md` or a vendor API directly.

---

## 1. Runner contract — `scripts/orchestrator.sh`

### 1.1 Shape  `#PATH_DECISION`

A **single foreground poll loop**, zero-dependency bash+awk like the mock adapter, driven by the
adapter's `events` subcommand:

```
loop forever:
  if kill-switch present -> exit 0
  raw = "$TRACKER_CMD" events            # one poll; adapter diffs snapshot -> emits events
  for each event line in raw:
    parse {ticket_id, from, to}
    dedupe by (ticket_id, to, at)
    dispatch(event)                       # §2 mapping
  sleep "$ORCH_POLL_INTERVAL"
```

- **Chosen — polling loop over `TRACKER_CMD events`.** The mock adapter surfaces events by polling
  (`task-tracking.md`, §18); the runner is the poller. This keeps the runner runtime-neutral: a
  webhook-based adapter (Jira/GitLab) can implement `events` as "drain the queue since last call"
  behind the same subcommand, so the runner does not change when the provider does.
- **Rejected — the runner subscribes to a webhook directly.** Couples the runner to a provider,
  violates ADR-A-0007, and is out of scope (§9).
- **Rejected — a long-running daemon holding in-memory event state.** Violates ADR-A-0002/§12
  "no long-running hidden context." The only durable runner state is the adapter's snapshot and the
  lock/stop files (§7).

### 1.2 Interval

`ORCH_POLL_INTERVAL` (seconds), **default 10**. Documented as the event-latency floor (matches
`task-tracking.md`: "expected latency = the poll interval"). Tests set it to `1` or run **one pass**
via a `--once` flag (§8). The default is a comment-tunable constant, not a hardcoded literal.

### 1.3 Parsing `TRACKER_CMD events` output  `#PATH_DECISION`

The mock adapter emits one line per event in a fixed pseudo-JSON shape (see `cmd_events`):

```
{ticket_id: ABS-42, from: In Review, to: In Test, at: 2026-07-03T12:00:00Z}
{ticket_id: ABS-43, from: null, to: Backlog, at: 2026-07-03T12:00:00Z}
```

- **Chosen — parse with a field-extracting `sed`/`awk` regex** keyed on the literal `ticket_id:`,
  `from:`, `to:`, `at:` labels, tolerant of the spaces the adapter emits. Values may contain spaces
  (`Ready for Development`), so the parser splits on the label boundaries, **not** on whitespace.
- **Rejected — `jq`.** The output is not valid JSON (unquoted values) and the boilerplate is
  zero-dependency by mandate (mock-tracker header). Adding `jq` breaks the "no yq/jq/python" rule.
- **`from: null`** (creation / first-poll event) is a normal value; the mapping (§2) keys on `to`
  only, so `from` is informational for the ticket-comment audit trail.

#PLAN_UNCERTAINTY — **Output-shape coupling.** The parser is coupled to the mock adapter's exact
line format. A real adapter's `events` must emit the same labelled shape (this is now an implicit
part of the `subscribe_events` contract). ABS-52 should add a shape assertion to
`tests/test-mock-tracker.sh`'s neighborhood, or the contract in `task-tracking.md` should state the
line grammar explicitly. **Open for human decision:** formalize the `events` line grammar in the
adapter contract now, or defer until the second adapter lands?

### 1.4 At-least-once vs exactly-once  `#PATH_DECISION`

The adapter contract (`task-tracking.md` §Event contract) is written as **at-least-once**, but the
mock's actual mechanism is **snapshot-based and advances on read**: `cmd_events` diffs the current
statuses against `work/.events-state` and then **unconditionally overwrites** the snapshot before
returning, regardless of what the caller does with the emitted lines (confirmed by reading
`cmd_events`, `scripts/mock-tracker.sh`). **Correction (post-review):** for this adapter, that makes
per-event delivery to the runner **effectively at-most-once**, not at-least-once — an event the
runner does not act on (dropped, deferred past the cap, or lost to a crash) is not redelivered,
because the next poll's diff baseline already reflects it. "At-least-once" describes the contract's
intent for a future adapter's `events` (e.g. "drain the queue since last call," §1.1); it is not a
guarantee this mock's mechanism actually provides.

Consequences the runner must handle:

- **Missed intermediate transitions.** If a ticket moves `A -> B -> C` between two polls, the runner
  sees only `A -> C` (one event). This is acceptable: the mapping keys on the *destination* status, so
  the correct terminal workflow still fires. Rapid multi-hops are a known, documented lossy edge.
- **Redelivery / duplicate suppression.** When a redelivery *does* occur (e.g. a future at-least-once
  adapter, or a runner retry), the runner **deduplicates by `(ticket_id, to, at)`**, keeping a small
  in-memory set for the current process lifetime **plus** the per-ticket single-flight lock (§5) as
  the durable guard: even across a runner restart, an in-flight spawn holds its lock, so a redelivered
  event cannot double-spawn.
- **The durable safety net is not adapter redelivery.** Because this adapter will not redeliver a
  missed event, correctness cannot rely on "the event comes back around." It instead rests on three
  runner-owned mechanisms, in order: (1) the §5.1 in-memory pending set for cap-deferred events within
  a live process, (2) the §5.1 periodic reconciliation sweep (`search`/scan + re-derive actionable
  status) as the crash-safe net when the pending set is lost, and (3) the §5.4 re-read guard, which
  makes any dispatch — first attempt, retry, or reconciliation — a safe no-op once the ticket has
  already moved on. Exactly-once is still not attempted (persisting processed-event ids would
  contradict §7), but the combination of reconciliation + re-read + lock gives the practical guarantee
  that matters: **no permanent silent loss, and no double-spawn.**

---

## 2. Event → role mapping

Derived directly from the `triggers:` field of each status in
[`statuses.yaml`](../../profiles/neutral/adapters/statuses.yaml) and the §14 lifecycle table. The runner
keys on the **destination** status (`to`). Three action classes: **SPAWN** (fresh subagent),
**NOTIFY** (comment only, human-facing), **NOOP** (record nothing beyond the event's own audit).

| `to` status | statuses.yaml trigger | Action | Role spawned | Next status the role drives |
|-------------|-----------------------|--------|--------------|-----------------------------|
| Backlog | PO prioritization sweep | **SPAWN** | `po-agent` (prioritization only — bare-epic decomposition moved to `Needs PO Decision`, ABS-60) | Ready for Development / Blocked |
| Ready for Development | Coordinator spawns implementation subagent | **SPAWN** | implementer (`be-developer`/`fe-developer`, per ticket) | In Progress |
| In Progress | Progress monitoring | **NOOP** | — (the implementer set this itself on start) | — |
| In Review | Coordinator spawns Review Agent | **SPAWN** | `system-architect` (Stage 1 reviewer, AGENTS.md 3-stage PR review) | In Test / In Progress (bounce) |
| In Test | Coordinator spawns QA/Test Agent | **SPAWN** | `qas` | Ready for Human Acceptance / In Progress (bounce) |
| Ready for Human Acceptance | PO epic-completion check; human notification when epic-complete | **SPAWN then NOTIFY** | `po-agent` (epic-completion check) → notify human if epic complete | Ready for Merge (human) |
| Ready for Merge | Human merges (Release Agent has PR ready) | **NOOP** | — (human-owned gate, ADR-A-0004/0005) | Done (human) |
| Done | Documentation sweep, epic progress update | **SPAWN** | `tech-writer` (doc sweep) + PO epic-progress update | terminal |
| Blocked | PO Agent triage, then human escalation | **SPAWN then NOTIFY** | `po-agent` (triage) → notify human if unresolvable | any prior active status |
| Needs PO Decision | Coordinator spawns PO-Agent (ABS-61) | **SPAWN** | `po-agent` — branches on packet `type` (ABS-60): epic packet with no children → **decomposition** (fan-out children, then epic → Backlog); non-epic → on-demand **decision request** | Backlog / Ready for Development / Blocked |

### 2.1 Rationale for the NOOP rows  `#PATH_DECISION`

- **In Progress → NOOP.** `In Progress` is *entered by the implementer subagent when it starts*
  (statuses.yaml `entered_when: Subagent starts`). If the runner spawned on this event it would spawn a
  second implementer for a ticket already being worked — a double-spawn. "Progress monitoring" is the
  staleness sweep (§2.3), **not** a spawn.
- **Ready for Merge → NOOP.** Merge is a permanent human boundary (ADR-A-0004, ADR-A-0005). The runner
  must not act; the Release Agent prepared the PR earlier. Autonomous merge is explicitly out of scope
  (§9).
- **Rejected alternative — spawn on every transition.** Produces double-spawns (In Progress) and
  crosses human boundaries (Ready for Merge). The mapping is deliberately *not* the identity function
  over statuses.

### 2.2 Role selection for `Ready for Development`  — RESOLVED (human-accepted 2026-07-04)

The implementer role (backend vs frontend vs data) is ticket-dependent. **Decision (open question B, accepted):**
the ticket schema gains an optional `role` frontmatter field that the runner reads to select the
implementer subagent, falling back to `be-developer` when the field is absent. Accepted values:
`be-developer` | `fe-developer` | `data-engineer` (extendable). Implementation impact:

- **ABS-52** (runner): read `role` from the ticket frontmatter via the adapter's `get`; fall back to
  `be-developer` and record a `#PLAN_UNCERTAINTY` note when absent.
- **Mock tracker / ticket format** (prereq for the E2E dry-run, ABS-55): `create` accepts `--role`,
  the ticket frontmatter carries `role:`, and `profiles/neutral/adapters/task-tracking.md` documents
  it as an optional field. Keep it optional so existing tickets and other adapters are unaffected.

### 2.3 Staleness / `In Progress` monitoring — deferred

The §22 "scheduled staleness sweep" and statuses.yaml "Progress monitoring" trigger are a **separate
scheduled concern**, not part of the status-change event loop. Named here so it is visibly out of the
ABS-52 runner scope; tracked as a follow-up, not a subtask of ABS-36 unless a human pulls it in.

---

## 3. Headless spawn mechanics  `#PATH_DECISION`

Researched against the Claude Code CLI reference and headless docs
(`code.claude.com/docs/en/cli-reference`, `.../headless`), current as of 2026-07-03.

### 3.1 The pluggable seam — `ORCH_SPAWN_CMD`

The runner never hardcodes `claude`. It invokes **`ORCH_SPAWN_CMD`**, a command receiving a normalized
argument contract, so tests use a stub and other runtimes (Agent SDK, Cursor, Codex) plug in without
touching the runner — satisfying §11 "runtime neutrality."

**Stub / provider contract (documented for ABS-53 and other providers):**

```
"$ORCH_SPAWN_CMD" <role> <ticket-id> <packet-file>
  stdin:   the context packet (§4)                     # also written to <packet-file> for providers that want a path
  env:     ORCH_ROLE, ORCH_TICKET, ORCH_PACKET_FILE
  stdout:  the agent's final structured result, including the handoff record (§6)
  exit 0:  success (handoff record must be parseable from stdout, §6)
  exit !0: spawn failure -> runner retry-once-then-escalate (§6)
```

- **Chosen — a single pluggable command with a fixed positional+stdin contract.** One seam, one thing
  to stub, provider-agnostic. Default binding is the Claude Code invocation below.
- **Rejected — the runner calls `claude` directly with inline flags.** Un-stubbable without a `claude`
  on PATH, couples the runner to one runtime, and makes the E2E dry-run (ABS-55) need a live model.

### 3.2 Default Claude Code binding (the shipped `ORCH_SPAWN_CMD` default)

```bash
claude -p \                               # no --bare: it skips keychain reads -> "Not logged in" on macOS (ABS-58)
  --agents "$(cat "$ROLE_DEFS_JSON")" \    # role name -> {description, prompt, tools} from .claude/agents/<role>.md
  --agent "$ORCH_ROLE" \                   # select the role for this spawn
  --model "$ORCH_MODEL" \                  # cost cap: default per-role (below)
  --max-turns "$ORCH_MAX_TURNS" \          # cost cap: hard turn ceiling
  --output-format json \                   # structured capture (§6)
  --permission-mode dontAsk \              # non-interactive; no prompts hang the loop
  < "$ORCH_PACKET_FILE"                    # packet on stdin (§4)
```

Flag choices, each grounded in the docs:

- **`-p`** — headless print mode. `--bare` (skip auto-discovery of hooks/skills/MCP/CLAUDE.md) was
  originally chosen for reproducibility but **also skips keychain reads**, so on macOS
  keychain-credential machines every spawn fails with "Not logged in" (found in the first live run —
  ABS-58). The binding therefore omits it by default; `ORCH_CLAUDE_BARE=1` opts back in where
  credentials are file/env-based.
- **Agent definition injection** — two supported paths, **chosen: `--agents <json>` + `--agent <name>`.**
  The runner materializes the repo's `.claude/agents/<role>.md` frontmatter+body into the
  `--agents` JSON shape (`{name:{description, prompt, tools}}`, docs: "same field names as subagent
  frontmatter, plus a `prompt` field"). **Rejected — `--append-system-prompt-file <role>.md`:** it
  appends rather than scoping, and does not carry the role's tool grants. **Rejected — `--system-prompt-file`:**
  fully replaces Claude Code's default operating prompt, losing tool-use scaffolding.
- **Cost cap per spawn (ADR-A-0009 posture — no runaway spend):**
  - `--max-turns "$ORCH_MAX_TURNS"` (default **12**) — hard ceiling; the docs note the run *exits with
    an error* at the limit, which the runner treats as a spawn failure (§6) and comments on the ticket.
  - `--model "$ORCH_MODEL"` — per-role default (e.g. review/QA roles on a cheaper alias, implementer on
    the stronger one). A comment-tunable table in the runner, not hardcoded per call.
- **`--permission-mode dontAsk`** — a locked-down non-interactive baseline (denies anything outside
  `permissions.allow` / read-only set); prevents a spawn from blocking the loop on a permission prompt.
  **Not** `bypassPermissions` — the runner does not grant blanket write/exec authority.

### 3.3 Output capture for the handoff record

`--output-format json` yields `{ result, session_id, total_cost_usd, ... }`. The runner reads the
`result` field (the agent's final message, which by the handoff contract §6 contains the handoff
record) and captures `total_cost_usd` for the per-spawn budget accounting (§5). See §6 for the
"missing handoff" failure path.

---

## 4. Context packet  `#PATH_DECISION`

Per ADR-A-0003 (context minimization) and §12/§22, the packet is **minimal and adapter-sourced**:

**Contents (v1):**
1. The **ticket body** via `TRACKER_CMD get <id>` — goal, scope, acceptance criteria, DoD, test plan,
   embedded ADR excerpts (the mock `get` prints the whole file; that already is the packet's core).
2. The **latest handoff record** for the ticket — extracted from the ticket's `## Comments` where
   `kind: handoff` (per ADR-A-0003 / §22 resume flow: "read ticket → read latest handoff record"),
   **also via the adapter `get`**, never by reading files.
3. A **header line** naming: `role`, `ticket_id`, `from_status`, `to_status`, and `resume: true|false`
   (`true` when a prior handoff record exists — the §22 resume signal).

- **Chosen — packet passed on stdin** to `ORCH_SPAWN_CMD` (and mirrored to a temp file
  `work/.orchestrator/packets/<ticket>.<ts>.txt` whose path is in `ORCH_PACKET_FILE` for providers
  that prefer a path). stdin matches the headless "pipe data through Claude" pattern and the mock `get`
  output is well under the docs' 10MB stdin cap.
- **Rejected — packet as a single CLI arg.** Argv length limits; the ticket body is multi-KB markdown.
- **Rejected — the runner re-summarizes ADRs into the packet.** ADR-A-0003 puts excerpt-embedding at
  *ticket creation* time, paid once; the runner must not re-derive context. The runner forwards what
  the ticket already carries.

**Size bound:** packet **soft cap 32 KB** (`ORCH_PACKET_MAX_BYTES`). Over cap → the runner **truncates
the ticket body tail, keeps the header + full latest handoff record**, and appends a
`[packet truncated: over ORCH_PACKET_MAX_BYTES]` marker so the overrun is visible (ADR-A-0003 "declare
overruns"). A chronically-truncated ticket indicts ticket quality — a workflow defect, per §13.

#PLAN_UNCERTAINTY — **"latest handoff record" selection** relies on comment ordering. The mock appends
comments chronologically, so "last `kind: handoff` block" is well-defined. Confirm real adapters
preserve comment order (they do in the contract). **Open:** do we need a machine-readable handoff
delimiter beyond the `kind: handoff` comment kind? Recommendation: reuse the existing kind, no new
schema.

---

## 5. Safety model

The runner is a spawning loop with real cost and concurrency; safety is not optional.

### 5.1 `ORCH_MAX_CONCURRENT`

Maps to blueprint `orchestrator.max_parallel_subagents` (§11). **Default 3.** The runner tracks live
spawns and does not exceed the cap; over cap, an event is **deferred, not dropped.**

**Correction (post-review):** an earlier draft of this section claimed a deferred event "re-surfaces
next poll because the snapshot only advances on the statuses it already recorded." That is false for
the mock adapter. `cmd_events` (`scripts/mock-tracker.sh`) rebuilds its `current` snapshot from
**every** ticket's present status on **every call**, and unconditionally `mv`s it over
`$EVENTS_STATE` before returning — the snapshot advances **on read, not on processing**. A
cap-deferred event is therefore never re-emitted: by the next poll the adapter's diff baseline
already equals the ticket's current status, so nothing fires for it again. Left uncorrected, a
concurrency-cap defer would be **permanent event loss**, not a one-poll delay.

Because the adapter cannot be relied on to redeliver, the runner itself must hold and repair
deferred work:

- **In-memory pending set.** When the cap defers an event, the runner adds `(ticket_id, to)` to an
  in-process pending set and retries entries from that set at the **start of the next cycle**,
  ahead of newly polled events, until a concurrency slot is free. This is ordinary in-memory runner
  state for the current process's lifetime — it is not written to disk and is not the persisted
  queue §7 disclaims.
- **Reconciliation sweep (the crash-safe net).** The pending set dies with the process, so if the
  runner itself crashes or restarts while an event is pending, the in-memory record is lost. The
  runner therefore also runs a **periodic reconciliation sweep**: every
  `ORCH_RECONCILE_EVERY_N_CYCLES` poll cycles (default **10**), and once **on every startup**, the
  runner calls `TRACKER_CMD search` (or equivalent) to scan current ticket statuses directly and
  re-derive actionable state — any ticket sitting in a SPAWN-mapped status (§2) with no live
  single-flight lock (§5.2) is dispatched as if freshly observed. This sweep, not the adapter's
  diffed event log, is the durable backstop for a lost pending set: it reconciles against the
  tracker's current state directly, so nothing observed by `events` needs to survive a runner
  restart to eventually be acted on. The single-flight lock (§5.2) and re-read guard (§5.4) make a
  reconciliation dispatch safe even when nothing was actually lost — it is a no-op if the ticket
  already advanced or is already locked.

### 5.2 Per-ticket single-flight lock  `#PATH_DECISION`

**Chosen — `mkdir` lock** at `work/.orchestrator/locks/<ticket-id>/`.

- `mkdir` is **atomic on both macOS and Linux** (POSIX) and needs no external binary. It succeeds
  exactly once; a second attempt fails, giving free mutual exclusion. Cleanup: `rmdir` in a `trap` on
  spawn completion/failure.
- **Rejected — `flock`.** `flock(1)` **is not present on stock macOS** (it is a util-linux tool); the
  boilerplate targets macOS+Linux dev boxes (mock-tracker header: "BSD and GNU compatible"). Relying on
  it would fail-closed on Macs.
- **Stale-lock handling:** a lock dir older than `ORCH_LOCK_TTL` (default 30 min, > `ORCH_AGENT_TIMEOUT`
  §6) is considered orphaned (crashed runner) and reclaimed with a logged warning.

### 5.3 Kill switch

Presence of **`work/.orchestrator-stop`** makes the loop **finish the current in-flight spawns, spawn
nothing new, and exit 0** at the top of the next iteration. A human `touch`es it to halt the fleet; it
is checked before every poll and before every spawn. This is the operator's emergency brake.

### 5.4 Per-run spawn budget (ADR-A-0009)

`ORCH_MAX_SPAWNS_PER_RUN` (**default 50**). Each successful spawn decrements the budget. **At
exhaustion:** the runner **stops spawning, posts a `kind: notification` comment** to the epic (or a
designated ops ticket) — "orchestrator spawn budget exhausted (N spawns); paused, human review needed"
— and **exits 0**. This is the cost-approval-gate posture (ADR-A-0009): the machine must not silently
commit unbounded LLM spend; it pauses and asks a human.

- **Idempotency re-read guard:** before spawning, the runner **re-reads the ticket status via `get`**
  and confirms it still matches the event's `to`. If a human/agent already moved it on, the spawn is
  skipped (stale event). This is what makes every dispatch path — first attempt, pending-set retry,
  and reconciliation-sweep dispatch alike (§5.1) — safe to re-attempt (§1.4).

### 5.5 Iteration-guard integration  `#PATH_DECISION`

The runner **invokes `scripts/hooks/iteration-guard.sh <ticket-id>` (CLI mode) before every SPAWN that
represents a bounce-capable loop** (In Review, In Test — the implement↔validate cycle).

- **exit 0** → proceed with the spawn.
- **exit 2** (cap reached, per ABS-12) → **do not spawn.** Instead the runner posts a `kind: gate-results`
  comment recording the cap hit and **transitions the ticket to `Blocked`** with actor `orchestrator`
  and a reason naming the iteration cap, so PO triage + human escalation take over (statuses.yaml
  `Blocked.triggers`). This realizes ABS-12's "escalate to human instead of another loop" at the
  orchestration layer.
- The guard is **fail-open** (ABS-12 §3): if it exits 0 on a tracker hiccup, the runner proceeds — the
  runner does not add its own fail-closed behavior on top.

---

## 6. Failure handling

Per §11 "retry once … then reassign/escalate; every hop is a ticket comment." Concretely:

| Failure | Detection | Action |
|---------|-----------|--------|
| Spawn command non-zero exit | `$?` of `ORCH_SPAWN_CMD` | **Retry once** with the failure text appended to the packet (§4). Second failure → PO-Agent escalation: comment `kind: handoff` with the failure, transition to `Blocked`. Every attempt is a comment. |
| Agent timeout | Runner wraps the spawn in a timeout (§6.1) | Treated as a non-zero spawn (retry-once-then-escalate). |
| Missing handoff record in stdout | Runner scans `result` for a handoff block (a `## Handoff` / `kind: handoff`-shaped section per `.claude/AGENT_OUTPUT_GUIDE.md` + §12) | **Retry once** (the resume invariant §12 says a defective handoff is a workflow bug). Second miss → escalate to PO-Agent + `Blocked`, comment records "agent produced no parseable handoff record." |

Every hop — attempt 1, retry, escalation — is a `kind: handoff` or `kind: transition-reason` comment on
the ticket via the adapter, so the audit trail is complete and the work is resumable by a fresh
subagent (§12 invariant).

### 6.1 Timeout enforcement  `#PATH_DECISION`

**Chosen — a portable bash watchdog** (background the spawn, record its PID, `sleep "$ORCH_AGENT_TIMEOUT"`
in a parallel subshell, `kill` the spawn if still alive; default **`ORCH_AGENT_TIMEOUT=900`s / 15 min**).

- **Rejected — `timeout(1)` / `gtimeout`.** GNU `timeout` **is not on stock macOS** (same reason as
  `flock`, §5.2). A hand-rolled watchdog keeps the runner dependency-free and BSD/GNU portable. The
  Claude Code docs' own background-agent wait ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`) is a
  secondary backstop when the default binding is Claude Code, but the runner does not *rely* on it —
  the watchdog is the provider-agnostic guarantee.

---

## 7. State

**The runner persists nothing outside the tracker except:**

1. The **events snapshot the adapter already keeps** (`work/.events-state`) — owned by the adapter, not
   the runner; the runner only triggers its update by calling `events`.
2. Its **lock dirs** (`work/.orchestrator/locks/<id>/`) and **kill-switch** (`work/.orchestrator-stop`)
   — pure runtime coordination, git-ignored, reconstructible.
3. Ephemeral **packet temp files** (`work/.orchestrator/packets/`) — regenerated each spawn, safe to
   delete.
4. The **in-memory cap-deferred pending set** (§5.1) — held only in the running process, never
   written to disk.

- **Justification vs ADR-A-0002 (fresh subagent) / ADR-A-0006 (active tracking):** ADR-A-0002 forbids
  *hidden agent context* that state depends on to be understood. Locks and a stop-file carry **no work
  state** — losing them costs at most a redundant poll or a re-acquirable lock; the *source of truth for
  all work state stays in the tracker* (comments, statuses, handoff records). ADR-A-0006 makes the
  tracker the driver; the runner is a stateless translator of its events. A brand-new runner process,
  started cold, reconstructs everything it needs from `events` + `get` — the resumability invariant
  (§12) applied to the orchestrator itself.
- **The pending set is deliberately not persisted, and this is safe.** It is pure in-memory
  bookkeeping so a live process does not forget a cap-deferred event before it can retry it (§5.1). If
  the runner dies, the pending set dies with it — but nothing is silently lost: the §5.1
  **reconciliation sweep** (periodic + on-startup `search`/scan of ticket statuses) independently
  re-derives which tickets need a spawn directly from tracker state, with no dependency on the pending
  set having survived. That sweep is the durable repair mechanism, so the pending set can stay
  ephemeral without weakening ADR-A-0002/0006 or requiring a persisted queue — a persisted queue would
  be redundant with the tracker (which is already the durable source of truth) and was rejected for
  exactly that reason.
- **Explicitly not persisted:** processed-event ids, an in-memory queue *written to disk*, spawn
  history. These would be hidden state; their durable equivalents already live in ticket comments, and
  loss-repair for the one genuinely ephemeral structure (the pending set) comes from reconciliation,
  not from persistence.

---

## 8. Test strategy (ABS-52..55)

All tests are zero-dependency bash, mirroring `tests/test-mock-tracker.sh`, and run against the **mock
tracker** with `MOCK_TRACKER_TICKETS_DIR` pointed at a temp fixture dir.

### 8.1 Stub spawn (ABS-53)

A `tests/fixtures/stub-spawn.sh` implementing the §3.1 contract: reads the packet on stdin, echoes a
canned handoff record to stdout, exits 0 (or non-zero / hangs / omits-handoff on demand via an env var)
to exercise every §6 branch. The runner is pointed at it via `ORCH_SPAWN_CMD=tests/fixtures/stub-spawn.sh`.
No real `claude` invocation in CI.

### 8.2 Runner unit scenarios (ABS-52, ABS-54)

`tests/test-orchestrator.sh`, `--once`-driven (single poll pass, no infinite loop), asserting:

- **Mapping (§2):** seed a ticket in each status, run one pass, assert SPAWN/NOTIFY/NOOP per the table
  (stub records which role it was called with).
- **Dedup (§1.4):** two `events` passes over the same transition spawn once.
- **Stale-event guard (§5.4):** move the ticket on before the pass; assert no spawn.
- **Single-flight lock (§5.2):** concurrent passes on one ticket → one spawn; assert lock dir lifecycle.
- **Concurrency cap (§5.1):** N+1 ready tickets, `ORCH_MAX_CONCURRENT=N` → N spawns this pass; assert
  the deferred (N+1)th ticket is held in the pending set and spawns on the **next** pass once a slot
  frees, proving the deferred event is retried rather than lost.
- **Reconciliation sweep (§5.1):** simulate a runner crash by seeding a ticket in a SPAWN-mapped status
  with no pending-set entry and no lock held, then start a fresh runner process with
  `ORCH_RECONCILE_EVERY_N_CYCLES` due (or on its startup sweep) → assert the sweep dispatches the
  ticket exactly once. Also assert a reconciliation pass over an already-locked or already-advanced
  ticket is a no-op (re-read guard, §5.4).
- **Kill switch (§5.3):** `touch work/.orchestrator-stop` → zero new spawns, exit 0.
- **Spawn budget (§5.4):** `ORCH_MAX_SPAWNS_PER_RUN=1` → second eligible event yields a notification
  comment + halt.
- **Iteration guard (§5.5):** a ticket at the ABS-12 cap in `In Test` → no spawn; assert `Blocked`
  transition + gate-results comment (drive via seeded `Iteration N of M` bounce comments).
- **Failure paths (§6):** stub exits non-zero / hangs past `ORCH_AGENT_TIMEOUT` / omits handoff →
  assert retry-once then `Blocked` + comment.

### 8.3 E2E dry-run script (ABS-55)

`tests/test-orchestrator-e2e.sh` — a full happy-path walk with the stub spawn, proving the loop drives a
ticket across the lifecycle without a live model:

```
1. create epic + one child ticket (mock tracker)
2. transition child Backlog -> Ready for Development
3. run orchestrator --once  -> assert SPAWN(implementer), handoff comment, In Progress reached
4. transition -> In Review; run --once -> SPAWN(system-architect) -> In Test
5. transition -> In Test;   run --once -> SPAWN(qas)      -> Ready for Human Acceptance
6. transition -> Ready for Human Acceptance; run --once -> SPAWN(po-agent) + NOTIFY comment
7. assert Ready for Merge / Done remain human-gated (NOOP): run --once, assert NO spawn
8. assert every hop left a ticket comment; assert no state outside tracker + lock/stop files
9. seed a second child ticket in Ready for Development with `ORCH_MAX_CONCURRENT=1` while the first
   spawn is held open, so the second event is deferred; then kill the runner process before it retries
   (simulating a crash) and start a fresh runner instance -> assert the startup reconciliation sweep
   (§5.1) finds the still-pending ticket via `search`/scan and dispatches it exactly once, with no
   event-loss and no double-spawn
```

The stub returns canned handoffs and performs the role's transition, so the E2E exercises the runner's
orchestration, mapping, and audit-trail guarantees deterministically, including the crash-recovery path
that backstops the concurrency-cap defer (§5.1).

---

## 9. Out of scope

- **Provider webhooks.** The runner polls `TRACKER_CMD events`; a webhook-backed adapter is a future
  adapter change, not a runner change (ADR-A-0007).
- **Dark-factory / fully-autonomous multi-epic runs.** This spec is the single-loop Coordinator only.
- **Autonomous merge and deploy.** Permanent human boundaries (ADR-A-0004, ADR-A-0005); `Ready for
  Merge` and `Done` are NOOP/human-driven (§2.1).
- **The staleness / progress-monitoring sweep** (§2.3) — a separate scheduled concern.
- **Real-model cost tuning** beyond the `--model` / `--max-turns` seams (§3.2).

---

## Approval

**Status: ACCEPTED by human (POPM, 2026-07-04). Implementation (ABS-52..55) is unblocked.**

**Acceptance record (2026-07-04):**

- **Sign-off items 1–6:** accepted as written (runner shape, event→role mapping incl. NOOP rows, the
  `claude -p` spawn seam, cost/safety defaults `ORCH_MAX_CONCURRENT=3` / `ORCH_MAX_SPAWNS_PER_RUN=50` /
  `ORCH_RECONCILE_EVERY_N_CYCLES=10`, iteration-guard→`Blocked`, `mkdir`-lock + watchdog portability).
- **Open question A** (events line grammar): **deferred** to the second real adapter — do not formalize now.
- **Open question B** (implementer role): **ticket `role` frontmatter hint** with `be-developer` fallback —
  see the resolved §2.2 (this adds a small optional-field requirement to ABS-52 and the mock tracker).
- **Open question C** (handoff record): **reuse the existing `kind: handoff` comment** — no new delimiter.

Original gate text (for the record): implementation MUST NOT start until a human accepts this spec.

Decisions requiring explicit human sign-off:

1. **Runner shape (§1.1):** single foreground polling loop over `TRACKER_CMD events`, no daemon, no
   persisted event log. Default interval 10s.
2. **Event→role mapping (§2), incl. the NOOP rows:** In Progress and Ready for Merge do **not** spawn;
   Ready for Human Acceptance and Blocked do SPAWN-then-NOTIFY. Confirm the table.
3. **Headless spawn seam (§3):** `ORCH_SPAWN_CMD` contract + the default Claude Code binding
   (`claude -p --agents/--agent` (no `--bare`, ABS-58), `--max-turns 12`, per-role `--model`, `--permission-mode
   dontAsk`, `--output-format json`).
4. **Cost/safety defaults (§5):** `ORCH_MAX_CONCURRENT=3`, `ORCH_MAX_SPAWNS_PER_RUN=50` (budget-exhaust
   → pause + notify per ADR-A-0009), `mkdir` locks, `work/.orchestrator-stop` kill-switch,
   `ORCH_RECONCILE_EVERY_N_CYCLES=10` reconciliation-sweep cadence (§5.1) as the crash-safe net for
   concurrency-cap-deferred events.
5. **Iteration-guard integration (§5.5):** at cap → `Blocked` transition + comment instead of spawn.
6. **Timeout & lock mechanism (§5.2, §6.1):** `mkdir` + hand-rolled watchdog, both chosen for
   macOS+Linux portability over `flock`/`timeout`. Confirm the portability trade-off is acceptable.

Open questions (`#PLAN_UNCERTAINTY`) for the same review — **all three RESOLVED at acceptance
(2026-07-04); see the Acceptance record above.** Kept here for the decision trail:

- **A. `events` line grammar** (§1.3) — formalize now, or defer to the second adapter?
  → **RESOLVED: deferred** to the second real adapter.
- **B. Implementer role selection** (§2.2) — default `be-developer` now, or add a ticket `role`
  frontmatter hint first?
  → **RESOLVED: ticket `role` frontmatter hint** with `be-developer` fallback (see §2.2).
- **C. Handoff-record delimiter** (§4) — reuse the `kind: handoff` comment, or introduce a
  machine-readable delimiter?
  → **RESOLVED: reuse `kind: handoff`** — no new delimiter.

---

## Amendment (2026-07-04, PR #18 review follow-up)

One MUST-FIX and one SHOULD finding from the opus review of PR #18 (comment id 821754207), both
corrected in place above rather than left as a separate errata list, per this repo's ABS-12-style
decision log:

1. **MUST-FIX — §5.1 backpressure claim was unsound.** The original text asserted a concurrency-cap-
   deferred event "re-surfaces next poll because the snapshot only advances on the statuses it already
   recorded." Reading `cmd_events` in `scripts/mock-tracker.sh` shows the opposite: the snapshot is
   rebuilt from **all current statuses** and unconditionally `mv`ed on **every** call, so it advances
   on read, not on processing — a deferred event was never re-emitted, i.e. permanent event loss.
   **Fixed** by (a) correcting §5.1's claim outright, (b) adding an in-memory pending set so a live
   runner retries a deferred event next cycle, and (c) adding a periodic + startup **reconciliation
   sweep** (`ORCH_RECONCILE_EVERY_N_CYCLES`, default 10) that re-derives actionable ticket state
   directly from the tracker as the crash-safe net when the pending set itself is lost. §7 (State) now
   lists the pending set explicitly and justifies why it can stay ephemeral (loss is repaired by
   reconciliation, not by persistence) without weakening ADR-A-0002/ADR-A-0006 or requiring a
   persisted queue.
2. **SHOULD — §1.4 overstated delivery semantics.** "At-least-once → redelivery" does not hold for
   this adapter: the mock's advance-on-read mechanism gives the runner **effectively at-most-once**
   delivery per event. **Fixed** by rewording §1.4 to say so directly and naming the actual durable
   safety net as the combination of the §5.1 pending set + reconciliation sweep and the §5.4 re-read +
   single-flight lock guard — not adapter redelivery. §5.4's re-read guard description was updated to
   cover all three dispatch paths (first attempt, pending-set retry, reconciliation dispatch)
   consistently.

Also updated for consistency: §8.2 adds a reconciliation-sweep test case and revises the concurrency-
cap test to assert retry-on-next-pass rather than an unqualified "N spawns this pass"; §8.3's E2E
scenario adds a step simulating a runner crash mid-defer and asserting the startup reconciliation
sweep recovers it exactly once; the Approval section's decision item 4 now names the reconciliation
cadence as part of the safety defaults requiring sign-off.

No structural changes: this amendment corrects the mechanism description in §1.4/§5.1/§7/§8 and adds
the reconciliation-sweep design element; it does not change the event→role mapping (§2), the spawn
seam (§3), the packet (§4), or the out-of-scope list (§9). At the time this amendment was written the
spec was still "awaiting human review"; it has since been **ACCEPTED by human (POPM, 2026-07-04)** —
see the Approval section above, which is the authoritative status.

---

_This spec matches the decision-record style of [`docs/specs/ABS-12-iteration-guard-spec.md`](ABS-12-iteration-guard-spec.md)._
