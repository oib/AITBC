# Consumer Fork Declaration Guide

<!-- docs-identifier-check: skip-file — this document cites consumer-project/template example paths that intentionally do not exist in this repo (ABS-517) -->

**Shipped in**: ABS-264 (epic ABS-245, boilerplate v2.25.0)

A consuming project can now declare its own boilerplate forks in a project-owned
file — `.agentic/upgrade/ownership.local.yaml` — and the migration driver will
honor them. Before this change, a consumer's only option was to edit the
boilerplate-owned `ownership.yaml`, which itself drifted and produced permanent
CONFLICT noise on every migration.

---

## When to Use This

You have locally patched a boilerplate-owned file (a script under `scripts/`,
an agent definition under `.claude/`, etc.) and want:

- the patched file **preserved** through future migrations (not overwritten), and
- the fork **tracked and graded** in the migration report's Fork Budget section.

Do **not** edit `.agentic/upgrade/ownership.yaml` — that file is boilerplate-owned
and editing it drifts it into permanent CONFLICT.

---

## Quick Start

### Step 1 — Create the local map

In your consuming project, create `.agentic/upgrade/ownership.local.yaml`:

```yaml
version: 1
project_owned_exceptions:
  - path: scripts/orchestrator.sh
    kind: fork
    upstream_ref: MY-PROJECT-123
    since: "2026-07-13"
```

Replace `MY-PROJECT-123` with the ticket where you tracked the upstream fix
request, and `since` with the date you took the fork.

### Step 2 — Run the migration

```bash
scripts/migrate-project.sh /path/to/your-project
```

The driver unions the upstream `ownership.yaml` with your `ownership.local.yaml`,
classifies `scripts/orchestrator.sh` as project-owned, and preserves it. The
migration report's `## Fork Budget` table grades your fork alongside upstream's.

### Step 3 — Check the Fork Budget

The report (written to `work/migration-reports/` in the target project) includes:

```text
## Fork Budget

| path | kind | upstream_ref | since | verdict |
| --- | --- | --- | --- | --- |
| scripts/orchestrator.sh | fork | MY-PROJECT-123 | 2026-07-13 | JUSTIFIED |
```

Verdicts: `JUSTIFIED` (within the 90-day budget), `STALE` (over budget), `DE-FORK`
(upstream now ships your content — delete the entry), `UNJUSTIFIED` (missing
`upstream_ref`), `STRUCTURAL` (permanent, never red).

---

## Core Concepts

### Subtract-only: you can opt out, not opt in

`ownership.local.yaml` may add paths to `project_owned_exceptions` — it may
**not** add paths to `boilerplate_owned`. A `boilerplate_owned:` block in the
local map is ignored with a warning. `boilerplate_owned` is always
SOURCE-authoritative, so upstream fixes (including security patches) reach you
unless you explicitly opt a file out.

### Zero conflict surface for the map file itself

`ownership.local.yaml` is carried as a `kind: structural` exception in the
upstream `ownership.yaml`. Migration never overwrites it — it has zero conflict
surface. You do not need to add it to your own local map.

### `.claude/**` domain

The `.claude/` domain is handled by the delegated `sync-claude-harness.sh` step.
That script now reads the same unioned exception list, so a `.claude/**` exception
declared in `ownership.local.yaml` is preserved through the delegated sync and
graded in the Fork Budget — no report/classifier divergence.

```yaml
version: 1
project_owned_exceptions:
  - path: .claude/agents/my-custom-agent.md
    kind: fork
    upstream_ref: MY-PROJECT-456
    since: "2026-07-01"
```

### Entry kinds

| `kind` | Required fields | Budget behavior |
| --- | --- | --- |
| `fork` (default) | `upstream_ref`, `since` | Grades JUSTIFIED / STALE / DE-FORK |
| `structural` | none | Permanent, never red |

A bare-path entry (`- scripts/foo.sh`) is valid and migration still preserves the
file, but the budget grades it UNJUSTIFIED until you add `upstream_ref`.

---

## Full Format Reference

```yaml
version: 1

# Only project_owned_exceptions is read from this file.
# A boilerplate_owned: block here is silently ignored (subtract-only).
project_owned_exceptions:
  # A fork you intend to upstream eventually:
  - path: scripts/orchestrator.sh
    kind: fork
    upstream_ref: MY-PROJECT-123   # required for kind: fork
    since: "2026-07-13"            # required for kind: fork (ISO date)

  # A permanent local customization (no budget clock):
  - path: .claude/agents/deploy.md
    kind: structural

  # Bare path — valid, but grades UNJUSTIFIED until upstream_ref is added:
  - scripts/my-local-adapter.sh
```

Path entries follow the same conventions as the upstream map: an exact file, or a
directory subtree (trailing `/`) to exempt everything under it.

---

## Troubleshooting

### "My declared fork is still being replaced"

Check that:

1. The file path in `ownership.local.yaml` exactly matches the path in
   `boilerplate_owned` (case-sensitive, no leading `./`).
2. The upstream `ownership.yaml` carries
   `.agentic/upgrade/ownership.local.yaml` as a `kind: structural` exception
   (present since ABS-264; upgrade from an older boilerplate first if missing).
3. You ran the driver with `--source` pointing at a boilerplate checkout that
   includes ABS-264 (v2.25.0+).

### "I see 'UNJUSTIFIED' in the Fork Budget table"

Add `upstream_ref` and `since` to the entry. File a ticket in your project
tracker, record it in `upstream_ref`, and set `since` to today's date.

### "I get a 'boilerplate_owned: block ignored' warning"

Remove the `boilerplate_owned:` section from `ownership.local.yaml`. That block
has no effect — `boilerplate_owned` is always read from the upstream source.

---

## Related

- `docs/sop/BOILERPLATE_MIGRATION_SOP.md` §3.2 — the migration SOP reference
- `adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md` — Amendment
  2026-07-13 (ABS-264): the ownership-semantics decision behind this feature
- `.agentic/upgrade/ownership.yaml` — upstream format reference (comments at top)
