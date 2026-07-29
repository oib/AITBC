---
name: tracker-ops
description: Adapter-CLI quick reference for the $TRACKER_CMD task tracker (scripts/jira-tracker.sh / scripts/mock-tracker.sh). Use to read a ticket, comment on or attach evidence to a ticket, transition a ticket's status, search tickets, or link tickets from an autonomous seat. Opens with copy-paste blocks for the five high-frequency ops (get / search / comment / transition / link) with the mandatory flags pre-filled — so no seat needs to run `help` to relearn the CLI.
allowed-tools: Read, Bash
---

# Tracker Ops (adapter CLI quick reference)

The autonomous lane talks to the tracker through the **`$TRACKER_CMD` adapter**
(`scripts/jira-tracker.sh` against real Jira, or `scripts/mock-tracker.sh` in a
sandbox). Both expose the **identical** nine-command surface
(`profiles/neutral/adapters/task-tracking.md`), so the blocks below work verbatim
against either. Paste, swap the free-text values, call — **do not run
`$TRACKER_CMD help` first.**

> **Which lane is this?** This is the **autonomous** `$TRACKER_CMD` curl-adapter
> lane used by the orchestrator poll loop and every headless seat. The
> **interactive** human-in-the-loop lane (Cursor/Claude + Atlassian MCP) is the
> separate `jira-sop` skill. Neither replaces the other — see
> `profiles/neutral/adapters/task-tracking.md` (§ "Lane doctrine").

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
  and **where you draft it depends on the TOOL** (ABS-253): the **Write/Edit tool**
  may only write `work/scratch/` (the one path in the allowlist) — a Write into
  `/tmp/…` or a bare `$(mktemp)` is **denied** under `--permission-mode dontAsk` and
  the body is lost silently; **Bash redirection** (`printf … > path`) into `/tmp/…`
  does work, but `work/scratch/` is the default so one habit is correct under both.

## The other four ops (reference)

Occasional, same adapter — reach for these when the five above don't cover it:

```bash
"$TRACKER_CMD" create --type ticket --title "…" [--parent ABS-1] [--role be-developer] [--body-file <path>]
"$TRACKER_CMD" update ABS-123 <field> <value>     # title|type|parent|depends_on|links|labels (status → transition)
"$TRACKER_CMD" children ABS-100                     # child tickets of an epic, with status
"$TRACKER_CMD" parent ABS-123                       # parent-epic key (empty line if none)
```

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
- **Adapter source:** `scripts/jira-tracker.sh`, `scripts/mock-tracker.sh`
- **Interactive MCP lane:** `.claude/skills/jira-sop/SKILL.md`
- **Sandbox driver:** `.claude/skills/run-boilerplate/SKILL.md`
