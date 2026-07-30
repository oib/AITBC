---
name: tracker-ops
description: "Adapter-CLI quick reference for the $TRACKER_CMD task tracker (scripts/backend-tracker.sh\
  \ / scripts/jira-tracker.sh / scripts/mock-tracker.sh). Use to read a ticket, comment\
  \ on or attach evidence to a ticket, transition a ticket's status, search tickets,\
  \ or link tickets from an autonomous seat. Opens with copy-paste blocks for the\
  \ five high-frequency ops (get / search / comment / transition / link) with the\
  \ mandatory flags pre-filled \u2014 so no seat needs to run `help` to relearn the\
  \ CLI."
triggers:
- user
- model
allowed-tools:
- exec
- read
---

# Tracker Ops (adapter CLI quick reference)

The autonomous lane talks to the tracker through the **`$TRACKER_CMD` adapter** —
`scripts/backend-tracker.sh` against the agentic backend, `scripts/jira-tracker.sh`
against Jira, or `scripts/mock-tracker.sh` in a sandbox. All three expose the
**identical** CLI surface (`profiles/neutral/adapters/task-tracking.md`), so the blocks
below work verbatim against any of them. Paste, swap the free-text values, call —
**do not run `$TRACKER_CMD help` first.**

> **Which lane is this?** This skill covers the **`$TRACKER_CMD` curl-adapter lane**
> used by the orchestrator poll loop and every headless seat. With the **agentic-backend**
> profile (ADR-A-0021) this is also the only lane — interactive human sessions use the same
> adapter, no Atlassian MCP server is needed, and the `jira-sop` skill is not loaded.
> The Atlassian MCP interactive lane (`jira-sop`) is Jira-profile-specific; see
> `profiles/neutral/adapters/task-tracking.md` (§ "Lane doctrine") for details.

## Backend env (agentic-backend profile)

When `$TRACKER_CMD` resolves to `scripts/backend-tracker.sh`, provision three env vars before
calling any adapter op:

| Variable | Required | Example |
| --- | --- | --- |
| `BACKEND_URL` | no (default `http://localhost:8420`) | `http://localhost:8420` |
| `BACKEND_TOKEN` | **yes** | project-scoped orchestrator token from registration |
| `TRACKER_PROJECT` | **yes** | project key, e.g. `ABS` |

These are the only env vars the backend adapter reads. The CLI surface — subcommands, flags,
`--body-file`, `--reason-file`, `--expect-from`, exit codes, stderr format — is **identical**
to the mock and Jira adapters; the quick-reference blocks below apply unchanged.

Install guide and token bootstrap: `docs/guides/AGENTIC-BACKEND-INSTALL.md`.

## Invocation rule (read once)

Invoke the adapter **exactly as the spawn packet prints it** — the absolute path
handed to you as `tracker_cmd` / `$TRACKER_CMD`:

```bash
"$TRACKER_CMD" get ABS-123
```

- **Do NOT** prepend `./` and **do NOT** wrap it in `bash …`. Under
  `--permission-mode dontAsk` the Bash allowlist matches the exact path; a
  `./scripts/...` or `bash scripts/...` form is a different string and is denied.
- All examples show `"$TRACKER_CMD"`; substitute the literal path if you are not
  in a spawned seat (e.g. `scripts/mock-tracker.sh` in a sandbox).

## Five high-frequency ops

### 1. get — read the full ticket

```bash
"$TRACKER_CMD" get ABS-123
```

Prints the canonical ticket: YAML frontmatter (`id/type/title/status/parent/
role/depends_on/links/created/updated`), the body, then a `## Comments` section
with each comment as `### <at> | kind: <kind> | actor: <actor>`. This is the one
call for "what state is this ticket in and what did the last seat say" — read it
before acting on a resumed spawn.

### 2. search — find tickets

```bash
"$TRACKER_CMD" search --status "Ready for Development" --type ticket
```

One match per line: `id<TAB>type<TAB>status<TAB>title`. Filters (all optional,
AND-ed): `--status S` `--type <epic|ticket|subtask>` `--parent P` `--text Q`
(case-insensitive substring over title+body) `--label L` (exact label match).

**Cross-lineage dedup search (ABS-452).** Before creating a ticket — especially a
Security-Review / QAS follow-up — the `duplicate-detection` gate must also catch a
sibling seat's near-simultaneous twin. The adapter has no time filter, so search by
the concrete change identifier and by lineage:

```bash
"$TRACKER_CMD" search --text "migration 010"      # affected file / DB column / migration number
"$TRACKER_CMD" search --parent ABS-430            # sibling lineage (same trigger/parent)
# then `get` each hit and read its `updated` field — an OPEN match touched in the last ~72h
# with the same concrete change is a cross-lineage twin → append, do not create.
```

On the Jira lane, the last-72h-open window is a single JQL (helper for the same gate):

```text
project = ABS AND statusCategory != Done AND updated >= -72h AND text ~ "reason column migration 010"
```

### 3. comment — post evidence / gate results (`--body-file`, ABS-163)

```bash
mkdir -p work/scratch
printf '%s\n' "Gate results: lint PASS, type-check PASS, integration PASS." > work/scratch/abs123-note.md
"$TRACKER_CMD" comment ABS-123 --kind gate-results --actor be-developer --body-file work/scratch/abs123-note.md
```

- **Always use `--body-file`, never `--body`, for anything non-trivial.** A body
  passed inline on the command line that contains a shell redirection character
  (`<` or `>` — common in code/evidence) is parsed as redirection by the
  `dontAsk` permission matcher and the call is **denied** (ABS-163). Writing the
  body to a file and passing `--body-file` keeps those characters off the command
  line entirely.
- `--kind` is one of: `understanding | transition-reason | gate-results |
  handoff | decision | notification | follow-up | bsa-decision | skip`.

### 4. transition — change status (`--expect-from`, ABS-198)

```bash
mkdir -p work/scratch
printf '%s\n' "All AC met; validation green. Ready for QAS." > work/scratch/abs123-reason.md
"$TRACKER_CMD" transition ABS-123 "In Progress" --actor be-developer \
  --reason-file work/scratch/abs123-reason.md --expect-from "Ready for Development"
```

- **`<to-status>` MUST be a canonical status name, spelled exactly** (see
  `profiles/neutral/adapters/statuses.yaml`): `Backlog`, `Ready for Development`,
  `In Progress`, `In Review`, `Done`, … A wrong/renamed spelling fails
  with "no transition to '<x>' available".
- **`--expect-from <status>` is a compare-and-set guard (ABS-198): always pass
  it.** If the ticket already left `<status>` (another seat moved it), the call
  is a logged **NOOP with exit 0** instead of a racing double-transition. Set it
  to the status you read in step 1.
- Use `--reason-file` (not `--reason`) for the same ABS-163 reason as `comment`.
- The runner does NOT transition for you — posting your exit transition is your
  duty.

### 5. link — relate two tickets

```bash
"$TRACKER_CMD" link ABS-123 ABS-100 parent-child
```

Link types: `parent-child | depends-on | origin-review | pr`. Idempotent —
re-linking the same pair prints `already linked` and exits 0.

## Known traps (all lanes)

- **No redirection chars on the command line.** `<` and `>` in any inline value
  (`--body`, `--reason`) are read as shell redirection under `dontAsk` and the
  call is denied. Route bodies/reasons through `--body-file` / `--reason-file`.
- **Canonical status names only.** Transition targets and `--status` filters use
  the canonical spellings from `profiles/neutral/adapters/statuses.yaml`, not a
  Jira-project-specific label. If the human Jira workflow renames a status, that
  rename is handled at the adapter boundary via `JIRA_STATUS_ALIASES`
  (`"Canonical=Jira"`, newline-separated) — set by the operator, never
  invented by a seat. You still pass the **canonical** name.
- **Compare-and-set on transitions.** Always pass `--expect-from` so a lost race
  NOOPs cleanly rather than overwriting a peer seat's transition (ABS-198).
- **`--body-file` / `--reason-file` read from a path**, so the file must exist —
  and **where you draft it depends on the TOOL you draft it with** (ABS-253):
  - **Write/Edit tool → `work/scratch/` only.** It is the one repo-relative path in
    the `Write`/`Edit` allowlist (`.claude/settings.template.json`), and it is
    gitignored, so drafts never get committed. A Write/Edit into `/tmp/…`, a bare
    `$(mktemp)`, or a repo-root path is **outside the grant**: under
    `--permission-mode dontAsk` it is **denied**, the file never appears, and the
    adapter then hard-fails on the missing `--body-file` — the comment or
    transition silently never lands.
  - **Bash redirection (`printf … > path`) → `/tmp/…` works**, because it is the
    Bash tool, not the Write grant. It is still not the default: prefer
    `work/scratch/` everywhere so one habit is correct under both tools.

  **Default: `mkdir -p work/scratch` and draft into `work/scratch/<ticket>-<what>.md`.**

## The other four ops (reference)

Occasional, same adapter — reach for these when the five above don't cover it:

```bash
"$TRACKER_CMD" create --type ticket --title "…" [--parent ABS-1] [--role be-developer] [--body-file <path>]
"$TRACKER_CMD" update ABS-123 <field> <value>     # title|type|parent|depends_on|links|labels|flags|ac_blocking (status → transition)
"$TRACKER_CMD" children ABS-100                     # child tickets of an epic, with status
"$TRACKER_CMD" parent ABS-123                       # parent-epic key (empty line if none)
```

### Rewrite a ticket BODY (`update … body-file`, ABS-252)

When the ACs change after enrichment, **rewrite the body** — do not patch it with
a comment, or the body goes stale against the ACs everyone works from:

```bash
mkdir -p work/scratch
"$TRACKER_CMD" get ABS-123 > work/scratch/abs123-current.md   # start from the current body
# …edit work/scratch/abs123-body.md: the goal/scope/AC/references body, WITHOUT frontmatter or comments…
"$TRACKER_CMD" update ABS-123 body-file work/scratch/abs123-body.md
```

- The body is **replaced**; frontmatter and every existing comment survive
  untouched (identical in both adapters — in Jira the body is the `description`
  field and comments live outside it).
- `update ABS-123 body "<text>"` is the inline form. **Prefer `body-file`** for
  the same ABS-163 reason as `comment`: a body containing `<` or `>` on the
  command line is read as shell redirection under `dontAsk` and denied.
- Status is not a body field — it still goes through `transition`.

(`events`, `child-count`, `assign` also exist — they are orchestrator-internal;
see the adapter header or `profiles/neutral/adapters/task-tracking.md`.)

## Verify against the mock before trusting a change

Every block above is executed as a smoke test in an isolated sandbox — no Jira,
no live state:

```bash
SB="$(mktemp -d)"; export MOCK_TRACKER_TICKETS_DIR="$SB/tickets"; mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
ID="$(scripts/mock-tracker.sh create --type ticket --title 'smoke' --prefix DEMO)"
scripts/mock-tracker.sh get "$ID"
printf 'gate: PASS\n' > "$SB/c.md"
scripts/mock-tracker.sh comment "$ID" --kind gate-results --actor be-developer --body-file "$SB/c.md"
printf 'released\n' > "$SB/r.md"
scripts/mock-tracker.sh transition "$ID" "Ready for Development" --actor be-developer --reason-file "$SB/r.md" --expect-from "Backlog"
rm -rf "$SB"
```

## Authoritative references

- **Adapter contract (nine ops):** `profiles/neutral/adapters/task-tracking.md`
- **Canonical statuses:** `profiles/neutral/adapters/statuses.yaml`
- **Adapter sources:** `scripts/backend-tracker.sh`, `scripts/jira-tracker.sh`, `scripts/mock-tracker.sh`
- **Backend install + env bootstrap:** `docs/guides/AGENTIC-BACKEND-INSTALL.md`
- **Backend profile:** `profiles/agentic-backend/profile.yaml`
- **Interactive MCP lane (Jira-profile only):** `harness/devin/skills/jira-sop/SKILL.md`
- **Sandbox driver:** `harness/devin/skills/run-boilerplate/SKILL.md`
