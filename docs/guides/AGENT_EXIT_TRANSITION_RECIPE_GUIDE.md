# Feature Guide: Explicit Exit-Transition Blocks and Sanctioned Draft Path (ABS-253)

**Story**: ABS-253 — Agent-Def-Hygiene: explicit exit-transition block for be/fe/data-engineer;
issue-enrichment body-file default path  
**Agent defs affected**: `harness/claude/agents/be-developer.md`,
`harness/claude/agents/fe-developer.md`, `harness/claude/agents/data-engineer.md`,
`harness/claude/agents/issue-enrichment.md`,
`harness/claude/skills/issue-enrichment/SKILL.md`  
**SOP updated**: `docs/sop/AGENT_WORKFLOW_SOP.md` — Exit States table

---

## Overview

Two defects let implementer seats declare an exit in prose while the transition never fired,
leaving tickets stuck in `In Progress` with no owning seat. This guide describes both defects,
the fixes shipped in ABS-253, and the patterns agent-def authors must follow going forward.

### Defect 1 — Non-existent exit status

`be-developer.md`, `fe-developer.md`, and `data-engineer.md` declared
`Exit State: "Ready for QAS"`. That string does not exist in
`profiles/neutral/adapters/statuses.yaml`. Driving it against either adapter:

```bash
"${TRACKER_CMD}" transition ABS-XXX "Ready for QAS" --expect-from "In Progress"
# ERROR: transition: unknown status 'Ready for QAS'   (exit=1)
```

The transition never applied. Seats fell back to writing `exit: In Review` in handoff prose
and the ticket sat in `In Progress`, feeding the stuck-detector. The canonical implementer
chain is `Ready for Development → In Progress → In Review`; "Ready for QAS" is a **handoff
label** — prose naming who picks the work up next — not a tracker status.

### Defect 2 — Unsanctioned draft path in issue-enrichment

`issue-enrichment.md` and its backing `harness/claude/skills/issue-enrichment/SKILL.md`
used a bare `$(mktemp)` for body-draft files (resolves to `/tmp/...`). Under
`--permission-mode dontAsk` the Write/Edit tools are gated by the paths in
`settings.template.json`. That grant covers only `work/scratch/**`; a Write to `/tmp/` is
denied silently, the draft is never created, and `--body-file` receives a missing-file
path:

```bash
ERROR: --body-file not found: /tmp/enrichment-body.XXXXXX   (exit=1)
```

The enrichment output was silently dropped.

---

## What changed in ABS-253

### Explicit claim/exit blocks (be/fe/data-engineer)

Each of the three implementer defs now carries a two-part command block under
**Exit Protocol**. The claim block runs at work start:

```bash
mkdir -p work/scratch
printf '%s\n' "Claiming <ticket-id>: starting BE implementation." \
  > work/scratch/<ticket-id>-claim.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <ticket-id> "In Progress" \
  --actor be-developer \
  --reason-file work/scratch/<ticket-id>-claim.md \
  --expect-from "Ready for Development"
```

The exit block runs after gate criteria pass:

```bash
printf '%s\n' "AC/DoD met. <one-line evidence summary>" \
  > work/scratch/<ticket-id>-handoff.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <ticket-id> "In Review" \
  --actor be-developer \
  --reason-file work/scratch/<ticket-id>-handoff.md \
  --expect-from "In Progress"
```

Both blocks appear verbatim in the defs and are reproduced in the provider mirror under
`agent_providers/claude_code/prompts/`.

### Sanctioned draft path for reason and body files

`work/scratch/` is the only repo-relative path covered by `Write/Edit` in both settings
templates (`harness/claude/settings.template.json`,
`agent_providers/claude_code/permissions/settings.template.json`):

```json
"Write(work/scratch/**)", "Edit(work/scratch/**)"
```

The directory is gitignored (`.gitignore:164` — `work/scratch/`) so drafts are never
committed. All reason-file and body-file drafts in issue-enrichment and in the three
implementer defs now target this path.

**Note**: a Bash redirect (`printf > /tmp/x`) is governed by the Bash rules, not the
`Write(...)` grant. The Write/Edit tool is what the grant gates. `work/scratch/` is the
correct path under both execution paths — Bash redirect and Write tool.

### SOP Exit States table split

`docs/sop/AGENT_WORKFLOW_SOP.md` — the `Exit States` section previously had a single
column mixing canonical statuses and handoff labels. ABS-253 splits it:

| Role          | Exit status (transition target) | Handoff label   |
| ------------- | ------------------------------- | --------------- |
| BE-Developer  | `In Review`                     | "Ready for QAS" |
| FE-Developer  | `In Review`                     | "Ready for QAS" |
| Data-Engineer | `In Review`                     | "Ready for QAS" |

The other seats (`System Architect`, `QAS`, `RTE`, `HITL`) carry statuses drawn from
`profiles/neutral/adapters/statuses.yaml` as legal edges from each seat's own transition
block. All nine statuses in the rewritten table exist in the adapter and are reachable from
the relevant source status.

---

## Core concepts for agent-def authors

### Status vs. handoff label

These two things are completely distinct:

- **Exit status** — the string passed to `transition <id> "<status>"`. Only values in
  `profiles/neutral/adapters/statuses.yaml` are valid. A wrong value exits 1 and the
  transition does not apply.
- **Handoff label** — prose in the handoff comment ("Ready for QAS", "Stage 1 Approved",
  etc.). It tells the next human or seat who picks up the work. It is never passed to
  `transition`.

### `--reason-file` is mandatory (ABS-163)

The adapters require a reason file, not an inline `--reason` string, when ABS-163
compliance is active. The `--reason-file` argument must point to a file that exists at
call time. Draft it before calling `transition`.

### `--expect-from` prevents lost races (ABS-198)

`--expect-from "<current-status>"` makes the transition a compare-and-set: if the ticket
is not in the expected status (another seat won the race), the adapter exits 0 with a
`NOOP compare-and-set` message rather than clobbering the state. Always include it.

### Status is positional, not `--to`

```bash
# Correct
transition <id> "In Review" --actor be-developer ...

# Wrong — rejected with 'unknown argument'
transition <id> --to "In Review" --actor be-developer ...
```

---

## Troubleshooting

### Transition exits 1 with "unknown status"

**Symptoms**: `ERROR: transition: unknown status '<x>'`  
**Cause**: the status string passed to `transition` is not in `profiles/neutral/adapters/statuses.yaml`  
**Fix**: check the legal status chain in that file; use the exact string including capitalisation

```bash
grep "name:" profiles/neutral/adapters/statuses.yaml
```

### Transition exits 1 with "--reason-file not found"

**Symptoms**: `ERROR: transition: --reason-file not found: /tmp/...`  
**Cause**: the draft was written to a path the Write tool is not allowed to access, so
the file was never created  
**Fix**: ensure the draft targets `work/scratch/`:

```bash
mkdir -p work/scratch
printf '%s\n' "reason text" > work/scratch/<ticket-id>-reason.md
```

### Ticket stays in "In Progress" after handoff

**Symptoms**: stuck-detector fires; ticket not advancing  
**Cause**: the seat declared exit status in prose but never called `transition`  
**Fix**: drive the exit block verbatim; `transition` must be called — the runner does not
call it for the seat

### "Ready for QAS" transition fails

**Symptoms**: `ERROR: transition: unknown status 'Ready for QAS'`  
**Cause**: this is a handoff label, not a status; the three implementer seats exit via
`In Review`  
**Fix**: use `"In Review"` as the transition target; keep "Ready for QAS" as prose in the
handoff comment only

---

## Related

- `harness/claude/agents/be-developer.md` — BE-Developer claim/exit blocks
- `harness/claude/agents/fe-developer.md` — FE-Developer claim/exit blocks
- `harness/claude/agents/data-engineer.md` — Data-Engineer claim/exit blocks
- `harness/claude/agents/issue-enrichment.md` — sanctioned body-draft path
- `harness/claude/skills/issue-enrichment/SKILL.md` — issue-enrichment skill
- `docs/sop/AGENT_WORKFLOW_SOP.md` — Exit States reference (status vs. label)
- `profiles/neutral/adapters/statuses.yaml` — canonical status registry
- `harness/claude/settings.template.json` — Write/Edit allowlist
- Epic ABS-245 — consumer-feedback de-fork epic
