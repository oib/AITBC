# Migration Prefix Guard (ABS-428)

Catches duplicate numeric migration prefixes before they reach `main`. Two
parallel epics each picked `008` on the night of 17./18.07. (and `004` before
that), requiring manual re-numbering at Epic-Sync both times. This guard
surfaces a collision in `pnpm test` — no database needed — so the second
branch's author fixes it during rebase, not the operator at sync time.

## How it works

`findDuplicateMigrationPrefixes(files: string[]): string[]` in
`backend/packages/core/src/migrate.ts` scans `.sql` filenames, groups them by
their leading `NNN` prefix, and returns any prefix that appears more than once
(excluding the grandfathered set). The pure-filesystem guard test
(`backend/packages/core/test/migrate-prefix-guard.test.ts`) runs this against
the real migrations directory on every `pnpm test`, including CI runs that have
no Postgres.

## Numbering convention for parallel branches

When you add a migration file, **never count by hand** — ask the helper
(ABS-449). It returns the next free `NNN` as the union of `main`, the working
tree, and any ref you name, so two seats reserving concurrently do not collide:

```bash
# next free after main + your working tree:
scripts/next-migration-number.sh
# also count a target epic branch (and any open MR branch you know of):
scripts/next-migration-number.sh --target epic/ABS-000-integration
```

Reserve the number **before** opening a PR — do not read from your local
branch, which may already diverge from `main`.

If two branches collide, the branch that merges **second** renumbers its file to
the next free number and rebases. Only unmerged files can be renumbered.

## Pre-merge collision gate (ABS-449)

The ABS-428 test above only fires once **both** files sit on one tree — i.e.
after the add/add merge conflict. To catch the reuse **before** the merge, run
the collision gate (same merge-base family as the ABS-397/398 rebase-gate)
against the ref you will merge into:

```bash
scripts/migration-number-collision-check.sh <target-ref> [<branch-ref=HEAD>]
#   exit 0  — no number added on both sides
#   exit 1  — COLLISION (names the number + the colliding files)
#   exit 64 — usage / bad ref (fails closed)
```

It compares what the branch added and what the target added **relative to their
merge-base**; a number added on both sides was picked twice in parallel. It runs
in CI on every PR via `.github/workflows/pr-validation.yml`, so the second MR
goes red before merge — the collision cost (re-sync, renumber, conflict) is
never paid at Epic-Sync. The pinned-equivalence suite is
`tests/test-migration-number-coordination.sh`.

Never rename an already-applied migration. An applied file renamed on disk
triggers `MigrationDriftError: file missing on disk` (ABS-288 content-integrity
guard) and the server will not boot.

## Grandfathered prefix

`004` appears twice in the series (`004_pr_mirror.sql` and
`004_seat_spawns.sql`). Both landed from parallel epics before this guard
existed. They cannot be renumbered because they are already applied (see above).
`GRANDFATHERED_DUPLICATE_PREFIXES` in `migrate.ts` holds the exempt set; new
`004` collisions are **not** exempt.

## What a collision looks like

When the guard detects a duplicate prefix, `pnpm test` fails with:

```
AssertionError [ERR_ASSERTION]: two migrations share a numeric prefix: 010
— renumber the newer file to the next free number on main
(see backend/README.md).
```

The message names the offending prefix. Renumber the **unmerged** file,
rename it on disk, update the commit, and rebase onto the latest `main`.

## Current series

| Prefix | File(s) | Note |
| ------ | ------- | ---- |
| 001 | `001_init.sql` | |
| 002 | `002_work_item_priority.sql` | |
| 003 | `003_orchestration_and_link_facets.sql` | |
| 004 | `004_pr_mirror.sql`, `004_seat_spawns.sql` | Grandfathered duplicate |
| 005 | `005_telemetry_events.sql` | |
| 006 | `006_command_queue.sql` | |
| 007 | `007_dashboard_session_store.sql` | |
| 008 | `008_pr_mirror_base_sha.sql` | |
| 009 | `009_knowledge_adr_policy.sql` | |

Next free prefix on `main`: **010**.

## Related

- `backend/packages/core/src/migrate.ts` — `findDuplicateMigrationPrefixes`,
  `migrationPrefix`, `GRANDFATHERED_DUPLICATE_PREFIXES`
- `backend/packages/core/test/migrate-prefix-guard.test.ts` — guard test (4 cases)
- `scripts/next-migration-number.sh` — reserve the next free number (ABS-449)
- `scripts/migration-number-collision-check.sh` — pre-merge collision gate (ABS-449)
- `tests/test-migration-number-coordination.sh` — helper + gate suite (ABS-449)
- `backend/README.md` — "Adding a migration — numbering convention (ABS-428)"
- ABS-288 — content-integrity guard (renaming applied migrations)
- ABS-397/398 — rebase-gate (same merge-base primitive)
