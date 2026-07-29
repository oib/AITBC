# Task Tracking Adapter — Interface

> _Adapted from the clean-room blueprint. Inline `.agentic/…` names below are design-record concepts; their live homes are in the [crosswalk](../../../blueprint/CROSSWALK.md). Treat this file as the capability contract._

Task tracking is **active, not passive**: status changes are events that trigger workflows
([`docs/sop/AGENT_WORKFLOW_SOP.md`](../../../docs/sop/AGENT_WORKFLOW_SOP.md)). The boilerplate is
tracker-agnostic; this interface is the only surface agents may use.

## Canonical model

- **Ticket:** the canonical fields (goal, scope, acceptance criteria, definition of done, test plan) as captured in [`specs_templates/spec_template.md`](../../../specs_templates/spec_template.md)
  (id, type, title, status, goal, scope, acceptance_criteria, definition_of_done, test_plan,
  adr_context, affected, cost_flags, links, …).
  - **Optional `role`** — an implementer-role hint (`be-developer` | `fe-developer` |
    `data-engineer`, extendable) that the orchestrator reads when it spawns an implementation
    subagent for a `Ready for Development` ticket (spec ABS-36 §2.2 / accepted open question B). It
    is **optional**: when absent the orchestrator falls back to `be-developer`. Adapters that carry
    it should omit the field entirely when it was not set, so existing tickets and adapters that do
    not model it are unaffected. In the mock adapter, `create --role <role>` writes a `role:`
    frontmatter line and `get` surfaces it.
  - **Optional `labels`** — free-form labels surfaced as a `labels:` list. Adapters MUST emit the
    field only when at least one plain label is set (only-when-given, like `role`) and MUST NOT lose
    labels on round-trip. The orchestrator reads **`orchestrator-ready`** as the **Backlog opt-in
    gate** (ABS-101): with the gate on (default), it acts on a Backlog ticket only when that label
    is present — an unlabelled ticket rests untouched. This is the human INPUT gate ("you may start")
    and is distinct from enrichment's *agent-ready* (the OUTPUT: groomed/executable). Bindings: the
    mock adapter writes it via `create --label` / `update <id> labels [..]` and filters via
    `search --label`; the Jira binding maps it to native Jira labels (a `labels = orchestrator-ready`
    `JIRA_JQL_FILTER` can additionally fence the whole sweep at the adapter level).
  - **`lane`** — the fastlane routing field (`normal` | `fastlane`, **default `normal`**). Unlike
    `role`/`labels` it is a **first-class scalar field, not a label**, and adapters MUST **always**
    emit it (a ticket created without `--lane` reads `lane: normal`), so the orchestrator can route
    on lane as a structural attribute rather than a label convention (ABS-319; epic ABS-314). Bindings:
    the mock adapter writes it via `create --lane <normal|fastlane>` / `update <id> lane <value>`,
    surfaces it in the `get` frontmatter, and filters via `search --lane <value>`; the Jira binding —
    which has no native lane field — persists it as a single `lane:<value>` label and **re-emits it as
    the `lane:` frontmatter field, never in the plain `labels` list** (same technique as `role:`), so
    the canonical `get` output matches across adapters. **Migration from the interim v2 batch-lane:**
    the manual batch-lane (`work/scratch/batch-collector.sh`) marked candidates with a
    `batch-candidate` **label**; that label maps to `lane: fastlane`. Existing `batch-candidate`-labelled
    tickets remain readable, but `lane` is authoritative going forward — new work sets the field, and
    a ticket with no `lane` field counts as `normal`.
  - **Canonical `priority`** — urgency signal consumed by the orchestrator and displayed on boards.
    ENUM (ordered, high-to-low): `hotfix` | `high` | `normal` | `low`. Default: `normal`.
    **Seats read priority; they MUST NOT raise it** — only a human or the PO-agent may increase
    urgency. A seat may lower it (e.g. after scope reduction) or leave it unchanged.
    Adapters MUST surface the field on `get` and persist it on `create`/`update`. When not
    explicitly set, emit `normal`. Adapter mappings:

    | Adapter | Mapping |
    | --- | --- |
    | `backend-tracker.sh` | Native `priority` column (stored in the backend DB; S2 API field). |
    | `jira-tracker.sh` | Persisted as a single `priority:<value>` label (same technique as `lane`), re-emitted as the `priority:` frontmatter field. This label persistence IS the canonical mapping (ABS-261); it deliberately does NOT touch Jira's native priority field. |
    | `mock-tracker.sh` | `priority:` frontmatter field in the ticket `.md` file; defaults to `normal` when absent. |

- **Statuses:** the canonical set in [`statuses.yaml`](statuses.yaml). Adapters map them to provider states and
  must represent every canonical status distinctly (no lossy folding).
- **Hierarchy:** epics have child tickets; tickets may have subtasks.
- **Comments:** structured comments carry PO understanding, transition reasons, gate results,
  handoff summaries, and human decisions.

## Operations (all adapters MUST implement)

| Operation | Semantics |
|-----------|-----------|
| `get_ticket(id)` | Full canonical ticket. |
| `search_tickets(filter)` | By status/type/parent/label/lane; used e.g. by duplicate detection (`status != done`) and fastlane routing (`lane = fastlane`). |
| `create_ticket(ticket)` | Create epic/ticket/subtask; returns id. |
| `update_ticket(id, fields)` | Update canonical fields. Includes the ticket **body**: adapters MUST support `update <id> body <text>` and `update <id> body-file <path>`, which REPLACE the body and MUST preserve the frontmatter and every existing comment (Jira binding: the `description` field; comments live outside it). This is the rework path — after enrichment an AC change edits the body instead of patching it with a comment, so the body never goes stale against the agreed ACs (ABS-252). Prefer `body-file`: it keeps shell redirection chars (`<` `>`) off the command line (ABS-163). Status is NOT updatable here — it goes through `transition`. |
| `comment(id, body, kind)` | kind: understanding \| transition-reason \| gate-results \| handoff \| decision \| notification \| follow-up \| bsa-decision \| skip \| claim. |
| `transition(id, to_status, reason, actor_role)` | Must enforce the canonical transition table; must record actor + reason. |
| `link(id, other_id, link_type)` | parent-child, depends-on, origin-review, pr. |
| `get_epic_children(epic_id)` | Child tickets with status summaries. |
| `parent(id)` | The ticket's parent-epic id (empty when it has none). Thin projection of `get_ticket`; consumed by the orchestrator's bash-only intake classifier (ABS-104). |
| `child_count(id)` | Number of tickets whose parent is `id` (0 when none). Thin projection of `get_epic_children`; consumed by the intake classifier (ABS-104). |
| `subscribe_events(callback)` | Deliver status-change (+ comment-command) events to the Coordinator. Webhook or polling; declare which and the expected latency. |
| `assign_ticket(id, accountId)` | Set the assignee of a ticket. Called by the orchestrator at spawn time so Jira boards show ownership. Graceful no-op when `accountId` is empty — never an error. **Never hardcode accountIds** — supply via `ORCH_ASSIGNEE` / `ORCH_ASSIGNEE_<ROLE>` env vars (ADR-A-0010). ABS-126. |

### `search` output contract (ABS-331 / ABS-334 / ABS-389)

`search_tickets` emits one tab-separated row per match, in the fixed **column form**
`id⇥type⇥status⇥priority⇥title` (`priority` before the free-form `title` so `title` stays the
trailing catch-all; unset priority renders `normal`). A no-match search emits **no output at all**.

**Row ordering — one canonical order across every adapter:** rows are ordered
`priority ASC, created ASC` — i.e. by priority band **hotfix → high → normal → low**, and by
`created` **oldest-first** within each band (adapters MAY append a stable per-id tiebreak, e.g.
`key ASC`, for equal `(priority, created)`). This is the single documented contract all three
bindings satisfy, so their `search` output is row-order interchangeable for a fixed fixture set:

| Adapter | How the canonical order is produced |
| --- | --- |
| `backend-tracker.sh` | Baked into the backend query: `ORDER BY priority ASC, created ASC, key ASC` (the DB `priority` enum is declared hotfix→low, so `ASC` yields the band order). |
| `mock-tracker.sh` | Rows prefixed with a priority-rank digit (hotfix=0<high=1<normal=2<low=3) + `created`, stable-sorted on both, keys stripped. |
| `jira-tracker.sh` | JQL fetches age-ASC (`ORDER BY created ASC`); priority persists as a `priority:<value>` label (not a JQL-orderable field), so the emit step STABLE-sorts the age-ASC rows by priority rank, preserving age-ASC within each band. |

The orchestrator's priority-aware dispatch (`prioritize_rows`, ABS-261) re-derives this same order
from the `priority` column, so it is robust to any adapter that has not yet adopted the contract;
the contract makes the adapters' *raw* `search` output identical without relying on that re-sort.

## Event contract

Event = `{ticket_id, from_status, to_status, actor, at}`. Delivery must be at-least-once; the
Coordinator deduplicates by `(ticket_id, to_status, at)`. Human comment commands
(`/agentic upgrade`, `/agentic migrate`) are surfaced as manual-trigger events.

## Provider bindings

A [profile](../../README.md) binds this capability to a provider:

- **mock** — the live, fully functional reference adapter (default in this profile): tickets as
  markdown+frontmatter files in [`work/tickets/`](../../../work/README.md), all canonical operations via
  [`scripts/mock-tracker.sh`](../../../scripts/mock-tracker.sh), transitions validated against
  [`statuses.yaml`](statuses.yaml), events by **polling** (the `events` subcommand diffs ticket
  statuses against `work/.events-state`; expected latency = the poll interval). It doubles as the
  conformance reference for new adapters — see [`tests/test-mock-tracker.sh`](../../../tests/test-mock-tracker.sh).
- **Linear** — the [`saw-stack`](../../saw-stack/profile.yaml) profile (SAW's `linear-sop` /
  `sync-linear` + `linear-mcp`).
- **agentic-backend** — the [`agentic-backend`](../../agentic-backend/profile.yaml) profile
  (ABS-229 / ADR-A-0021): self-hosted Node/Postgres tracker with a `docker compose up` install and
  a built-in kanban dashboard. **A single `$TRACKER_CMD` lane serves both the orchestrator poll loop
  and interactive human sessions** — no Atlassian MCP server required. Switch:
  `export TRACKER_CMD=scripts/backend-tracker.sh`.
  Install guide: [`docs/guides/AGENTIC-BACKEND-INSTALL.md`](../../../docs/guides/AGENTIC-BACKEND-INSTALL.md).
- **Jira / GitHub Issues / GitLab** — the [`jira-github-postgres`](../../jira-github-postgres/profile.yaml)
  reference profile shows a non-SAW binding. **Jira is the only provider that uses two lanes**
  (MCP for interactive + curl adapter for autonomous) — see the lane doctrine below.
- **Any other tracker** — implement the operations above and bind it in a profile; see the
  [adapters index](README.md).

## Lane doctrine: `$TRACKER_CMD` adapter and the Jira two-lane exception

**Default (agentic-backend, mock, Linear, and any future self-hosted tracker):** a single
`$TRACKER_CMD` curl adapter handles all traffic — both the autonomous orchestrator poll loop and
interactive human sessions. No separate MCP server is loaded; the `jira-sop` skill is not used.
The `tracker-ops` skill covers all adapter operations (ADR-A-0021 Consequences, ADR-A-0007).

**Jira exception:** Jira is reached through **two sanctioned lanes** that serve different callers
and are deliberately kept separate (ABS-152, ADR-A-0007):

| Lane | Transport | Caller | Use it for |
|------|-----------|--------|------------|
| **Interactive lane** | Atlassian **MCP** server (`https://mcp.atlassian.com/v1/sse`), OAuth | a **human-in-the-loop seat** — an interactive Cursor/Claude session | ad-hoc create/search/comment/transition, mock-ticket migration, evidence attachment — see the [`jira-sop` skill](../../../.claude/skills/jira-sop/SKILL.md) |
| **Autonomous lane** | `scripts/jira-tracker.sh` **curl** adapter behind `$TRACKER_CMD` | the **headless orchestrator poll loop** (`scripts/orchestrator.sh`) | every automated status-change poll and adapter operation — see [`ORCHESTRATOR_SOP.md`](../../../docs/sop/ORCHESTRATOR_SOP.md) |

**Why Jira needs two lanes:**

- **The MCP lane cannot run headless.** Its OAuth flow and per-session server ids
  (`user-atlassian` / `project-0-<workspace>-atlassian`) are resolved interactively and are not
  available to an unattended process — so the autonomous loop cannot use it.
- **The curl lane is built for the loop.** `scripts/jira-tracker.sh` is a zero-interaction
  `$TRACKER_CMD` binding (env-provisioned `JIRA_*` credentials, curl-only) whose CLI mirrors the
  mock adapter exactly, so `scripts/orchestrator.sh` runs unmodified against it (ADR-A-0007:
  adapter-only tracker access).
- **The one-JQL-sweep-per-poll budget is deliberate.** The autonomous lane issues a single JQL
  sweep per poll cycle by design — it bounds tracker API load and cost, and is not a limitation to
  "fix" by widening queries. Rich, multi-call exploration belongs in the interactive MCP lane where
  a human is present.
- **With the agentic backend, the two-lane split disappears entirely.** Both the orchestrator loop
  and an interactive session use the same `scripts/backend-tracker.sh` CLI, provisioned by the
  same env vars (`BACKEND_URL`, `BACKEND_TOKEN`, `TRACKER_PROJECT`) — there is no MCP server and
  no OAuth flow to thread. The one-call-per-poll discipline still applies: the backend adapter
  calls `GET /events` once per cycle, identical in spirit to the Jira JQL sweep.

Out of scope here: OAuth/auth mechanics, Jira bootstrap plumbing (ABS-27 / ABS-144), and backend
installation steps (see [`docs/guides/AGENTIC-BACKEND-INSTALL.md`](../../../docs/guides/AGENTIC-BACKEND-INSTALL.md)).
