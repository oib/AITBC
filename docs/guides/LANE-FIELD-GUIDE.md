# Lane Field — Fastlane Ticket Routing

> **Introduced in ABS-319 (epic ABS-314 v3 Fastlane). Adapter contract:**
> `profiles/neutral/adapters/task-tracking.md` — the authoritative interface spec.

## Overview

`lane` is a first-class scalar field on every tracker ticket. It tells the
orchestrator which routing path a ticket belongs to:

| Value      | Meaning                                                                               |
|------------|---------------------------------------------------------------------------------------|
| `normal`   | Standard pipeline — the default for all tickets.                                      |
| `fastlane` | Expedited routing — reserved for high-urgency stories that bypass the standard queue. |

`lane` is a **structural attribute**, not a label. The orchestrator reads it as a
frontmatter field, so routing decisions are unambiguous and type-safe. The interim
manual batch-lane (the `batch-candidate` label) is superseded by this field;
see [Migration](#migration-from-batch-candidate-label) below.

## Prerequisites

- Mock reference adapter: `scripts/mock-tracker.sh` (v3 story pipeline, ABS-319+).
- Jira adapter: `scripts/jira-tracker.sh` (same ABS-319 cut; parity via
  `lane:<value>` label re-emitted as the `lane:` frontmatter field).
- Env: `TRACKER_CMD` set to the adapter you are using, or rely on the default
  (`scripts/mock-tracker.sh`).

## Quick Start

### Create a fastlane ticket

```bash
scripts/mock-tracker.sh create \
  --type ticket \
  --title "Urgent: fix auth regression" \
  --prefix ABS \
  --lane fastlane
```

Retrieve it and confirm the field:

```bash
scripts/mock-tracker.sh get ABS-1 | grep '^lane:'
# lane: fastlane
```

### Create a normal-lane ticket (default)

```bash
scripts/mock-tracker.sh create \
  --type ticket \
  --title "Refactor logging" \
  --prefix ABS
# omitting --lane defaults to lane: normal
```

### Switch a ticket's lane

```bash
scripts/mock-tracker.sh update ABS-1 lane normal
scripts/mock-tracker.sh get ABS-1 | grep '^lane:'
# lane: normal
```

### Filter tickets by lane

```bash
# List only fastlane tickets
scripts/mock-tracker.sh search --lane fastlane

# List only normal-lane tickets
scripts/mock-tracker.sh search --lane normal
```

## Core Concepts

### Always-present field

Unlike `role` or `labels` (emitted only when set), `lane` is **always** present in
`get` output. A ticket created without `--lane` shows `lane: normal` — the
orchestrator never has to infer a missing field.

```
---
id: ABS-2
title: Refactor logging
lane: normal          # always here, even when not explicitly set
status: Backlog
---
```

### Lane is not a label

The `labels:` list in `get` output never contains a `lane:…` token. The field
lives in the frontmatter field block, separate from plain labels like
`orchestrator-ready`:

```
---
id: ABS-1
title: Urgent: fix auth regression
lane: fastlane        # field
labels: [orchestrator-ready]  # plain labels — no lane:<x> here
---
```

### Jira adapter parity

The Jira adapter has no native lane concept, so it stores `lane:<value>` as a
single Jira label and re-emits it as the `lane:` frontmatter field on `get`,
filtering it out of the plain `labels` list. The canonical `get` output is
**identical across the mock and Jira adapters** — consumers need no adapter-specific
code paths.

**One caveat (non-blocking):** `search --lane normal` may miss legacy Jira tickets
that predate ABS-319, because those tickets carry no `lane:normal` label. The
authoritative routing query is `search --lane fastlane` — it is exact and identical
in both adapters. New tickets always carry the field.

### Closed-value validation

Both adapters accept only `normal` or `fastlane`. Any other value exits non-zero
with a clear message:

```bash
scripts/mock-tracker.sh create --lane bogus ...
# ERROR: create: invalid lane 'bogus' (normal|fastlane)
# exit 1

scripts/mock-tracker.sh update ABS-1 lane bogus
# ERROR: update: lane must be 'normal' or 'fastlane'
# exit 1
```

## Migration from `batch-candidate` Label

The v2 manual batch-lane marked expedited tickets with a `batch-candidate` label.
That label is now superseded by the `lane` field:

| Before (v2 batch-lane)           | After (v3 lane field)                                           |
|----------------------------------|-----------------------------------------------------------------|
| Add label `batch-candidate`      | Set `--lane fastlane` at create, or `update <id> lane fastlane` |
| `search --label batch-candidate` | `search --lane fastlane`                                        |

**Existing `batch-candidate`-labelled tickets** remain readable but are not
automatically migrated. The `lane` field is authoritative going forward:

- A ticket with no `lane` field is treated as `normal`.
- New tickets should use `--lane fastlane` instead of `batch-candidate`.

## Troubleshooting

### `lane:` missing from `get` output on an older ticket

A ticket created before ABS-319 has no `lane:` key in its frontmatter. Both
adapters treat it as `normal`. To set it explicitly:

```bash
scripts/mock-tracker.sh update ABS-99 lane normal
```

After the update, `get` shows `lane: normal` explicitly.

### `search --lane normal` returns fewer tickets than expected (Jira)

`search --lane normal` uses JQL `labels = lane:normal`, which only matches
tickets that have the label explicitly set. Pre-ABS-319 tickets with no lane label
are not returned. Use `search --lane fastlane` for routing decisions — it is exact
and unambiguous in both adapters.

### Invalid lane value rejected

Only `normal` and `fastlane` are accepted. Check your spelling; the adapter exits 1
with the accepted values in the error message.

## See Also

- Adapter contract: `profiles/neutral/adapters/task-tracking.md` — field
  definition, Jira parity details, and migration mapping.
- Epic: ABS-314 — v3 Fastlane (children B–G implement eligibility, dashboard, and
  pipeline routing on top of this field).
- QA validation: `docs/agent-outputs/qa-validations/ABS-319-qa-validation.md`.
