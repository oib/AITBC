---
type: concept
resource: .harness-manifest.yml
tags: [harness, upgrade, configuration]
timestamp: 2026-07-03
---

# Harness sync and manifest

Forks keep their Claude/Gemini/Codex/Cursor harness directories up to date with upstream SAW via
a **manifest-based sync**: `.harness-manifest.yml` (repo root) declares how the fork has
customized the harness, and `scripts/sync-claude-harness.sh` reads it to sync intelligently
instead of overwriting local customizations.

## Manifest model

`.harness-manifest.yml` has four load-bearing sections:

- **`identity`** — project placeholder values (`PROJECT_NAME`, `TICKET_PREFIX`,
  `MAIN_BRANCH`, …), matching `scripts/setup-template.sh`'s placeholder names exactly.
- **`renames`** — upstream path → local path map (file or, with a trailing `/`, directory).
  Lets a fork rename e.g. `fe-developer.md` → `ui-engineer.md` and still receive upstream
  updates at the renamed path.
- **`protected`** — glob patterns the sync script must **never** overwrite (config that would
  break if replaced, e.g. `hooks-config.json`, `settings.local.json`).
- **`replaced`** — paths that exist upstream but the fork maintains independently; sync skips
  them and warns if upstream has changed since the last sync (distinct from `protected`: these
  have an upstream counterpart, protected files may not).

`sync.sync_scope` lists which top-level domains participate (default `[".claude/"]`; can include
`.gemini/`, `.codex/`, `.cursor/`, `.agents/`, `dark-factory/`). Always-excluded regardless of
scope: `.harness-sync.json`, `.harness-manifest.yml` itself, `.sync-exclude*`,
`.harness-backup/`, `.harness-patches/`.

## Sync flow

1. Load and validate the manifest against its JSON schema (sync fails without one, except
   `--dry-run`).
2. Fetch the upstream `.claude/` tarball at the requested version/branch.
3. Apply `{{PLACEHOLDER}}` substitutions from `identity`/`substitutions`.
4. Build the sync plan (every file to be written, renames resolved).
5. **Run preflight** (see below).
6. Create a timestamped backup of the current harness.
7. Apply changes — copy new/modified files, or generate `.patch` files with
   `--generate-patches`; skip protected and replaced files.
8. Record provenance (source SHA, version tag, timestamp, file counts) in `.harness-sync.json`.

## Preflight

Before any file is written, preflight validates: every target path falls within a declared
`sync_scope` domain (paths outside abort the whole sync); no unreplaced `{{TOKEN}}` remains in a
file after substitution; and no planned write targets a `protected` path (if it would, the
sync aborts rather than skip-and-continue). `--skip-preflight` bypasses this for advanced users
only.

## Conflict handling

`sync.conflict_strategy` controls what happens when both upstream and local changed a file since
the last sync: `upstream-wins`, `local-wins`, `prompt` (write `.upstream` copies for manual
review — the default), or `three-way` merge from the last-synced base.

## Related

- [capabilities-and-profiles.md](capabilities-and-profiles.md) — profiles are explicitly
  excluded from sync scope; they are project-owned configuration, not harness
- [bootstrap-flow.md](bootstrap-flow.md) — the manifest's `identity` values mirror
  `setup-template.sh`'s placeholder set
- Source: `docs/HARNESS_SYNC_GUIDE.md`, `.harness-manifest.yml`,
  `blueprint/BLUEPRINT.md` §7 (Upgrade Model)
