---
description: Execute full version release — merge PRs, promote governor, version bump, annotated tag, sync branches, cleanup
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
argument-hint: "<version> (e.g., v2.17.0)"
---

> **⚠️ Scope note (AITBC).** This command manages the **SAW harness's own self-hosting version
> pin** (`.governor-tag`, `harness/claude/**` → generated `.claude/`, `~/boilerplate-stable`) — it is
> the harness maintainer's release process for publishing a new harness version upstream. It is
> **NOT** AITBC's own application release process. AITBC's own versions (`v0.x.y`, see
> `docs/CHANGELOG.md` and the existing `v0.*` tags) are cut through AITBC's own separate release
> workflow, unrelated to this file. Only run this command if you deliberately intend to publish a
> new SAW-harness release from this fork upstream; otherwise **Phases 3 and 4.3 do not apply** to
> normal AITBC development and should be skipped.
>
> Resolved for this repo: host is **GitHub**, so `{{GIT_HOST_CLI}}` → `gh` and `{{GIT_REMOTE_SLUG}}`
> → `oib/AITBC` throughout.

You are executing a full version release. Follow each phase in order. **Do not skip phases.** Report status after each.

## Input

The user provides a version number (e.g., `v2.17.0`). If not provided, determine the next version by:

```bash
git tag -l 'v*' | sort -V | tail -1
```

Then bump the minor version (or ask the user for major/minor/patch).

---

## Phase 1: Pre-Release Validation

### 1.1 Verify Clean State

```bash
git status                    # Must be clean
git branch --show-current     # Must be on main
git fetch origin
git log --oneline origin/main..HEAD  # Must be empty (in sync)
```

**BLOCKER**: Working tree must be clean and branch must be current with remote.

### 1.2 Check Open PRs

```bash
gh pr list --state open
```

**Decision point**: If there are open PRs intended for this release, merge them first (Phase 2). If none, skip to Phase 3.

### 1.3 Verify CI Status

For each open PR to merge, inspect its build/merge state:

```bash
gh pr view <NUMBER>                      # shows status + merge checks
```

**BLOCKER**: All checks must pass. Do not merge PRs with failing required checks.

---

## Phase 2: Merge Open PRs (if any)

### 2.1 Merge in Dependency Order

For each PR (merge in order — base dependencies first):

```bash
gh pr merge <NUMBER> --squash --subject "..."
```

Use your host's squash/rebase option to keep history clean; match the commit-message convention
`type(scope): description [AITBC-XXX]`.

### 2.2 Rebase Dependent PRs

After each merge, rebase any remaining PRs that target the same base:

```bash
git fetch origin
git checkout <dependent-branch>
git rebase origin/main
git push --force-with-lease origin <dependent-branch>
```

Wait for CI to re-run before merging the next PR.

### 2.3 Sync Local After All Merges

```bash
git checkout main
git pull origin main
```

---

## Phase 3: Promotion — Roll the Governor Forward (self-hosting)

> **Self-hosting (ADR-A-0013).** This repository develops itself under a pinned stable release
> (`~/boilerplate-stable`). The live `.claude/` is `generated(.governor-tag)`; the editable SOURCE
> is `harness/claude/**`. Promotion rolls the governor forward, as one whole version, on a single
> release commit, then tags it — establishing `.claude@<version> == generate(<version>)` so a
> consumer syncing the `.claude` domain at the tag gets exactly that release's generated harness.
> A fork that is NOT self-hosted (no `.governor-tag` / `harness/` namespace) skips this phase.

### 3.1 Dry-run the promotion first

```bash
bash scripts/promote-release.sh <version> --dry-run
```

This rehearses the whole promotion inside a throwaway clone (release commit + local tag there) and
proves **tag freshness** — `generate-governor.sh --check` clean at the scratch tag and the banner
carrying `<version>`. It touches nothing in the real repo. **BLOCKER**: the dry-run must print
`DRY-RUN OK`.

### 3.2 Execute the promotion (creates the release commit + annotated tag locally)

```bash
bash scripts/promote-release.sh <version>
```

This, in order on one commit: writes `<version>` to `.governor-tag` → regenerates the live
`.claude/` from the working-tree `harness/claude` source (via `generate-governor.sh --from-tree`,
because `<version>` does not exist as a tag yet) → stamps the provenance banner with `<version>` →
commits → creates the annotated tag `<version>` on that commit. **The script pushes nothing** —
pushing the tag is a human step (Phase 4). Version-reference text edits (README badges etc.) are
Phase 3.3; they can be folded into this commit or committed just before running the script.

### 3.3 Version-reference text bump

The release touches several **version carriers**. Know which are automated and which you must edit,
or one silently rots (this is exactly how `.boilerplate-version` sat at v2.10.0 through 11 releases —
ABS-139):

| Carrier | Owner | Action |
| ------- | ----- | ------ |
| `.governor-tag` | `promote-release.sh` (Phase 3.2) | automatic — do NOT hand-edit |
| `.boilerplate-version` | `promote-release.sh` (Phase 3.2, ABS-139) | automatic — do NOT hand-edit |
| `CLAUDE.md` provenance banner | `promote-release.sh` (Phase 3.2) | automatic — do NOT hand-edit |
| `HARNESS_CHANGELOG.yml` | you (Phase 4 record) | add the release entry; **governor-only patches still get a stub entry** with `changes: []` for tag/changelog parity |
| `README.md` version badge | you / ABS-129 automation | edit the `shields.io/badge/version-…` badge |
| Other active "now at **vX.Y**" prose | you | edit in place |

`pre-release-check.sh` §6 fails the release if `.governor-tag` and `.boilerplate-version` disagree or
if the changelog's latest entry lags — run it (Phase 1) before promoting.

Search for active prose references and update them (do this before 3.2 so they land in the release
commit, or amend afterward):

```bash
grep -rn "v[0-9]\+\.[0-9]\+" README.md CLAUDE.md CONTRIBUTING.md --include="*.md" \
  | grep -v node_modules | grep -v releases/ | grep -v whitepapers/
```

Update **only active version references** (not historical references in changelogs, upgrade guides,
or KT docs). Do NOT hand-edit the automated carriers in the table above — `promote-release.sh` owns them.

---

## Phase 4: Tag and Release Record

> **Bitbucket has no `gh release`-object equivalent.** The **annotated tag** (created by
> `promote-release.sh` in Phase 3.2) plus the `HARNESS_CHANGELOG.yml` entry **is** the release
> record. There is no separate publishable "release" object to create on Bitbucket. (A GitHub fork
> MAY additionally run `gh release create` in 4.4 for a richer notes page — optional, not required.)

### 4.1 Confirm the annotated tag exists locally

```bash
git tag -l '<version>'                    # created by promote-release.sh (Phase 3.2)
git show <version> --stat | head -40      # inspect the annotated tag + release commit
```

If this fork is NOT self-hosted (Phase 3 skipped), create the annotated tag here instead:

```bash
LAST_TAG=$(git tag -l 'v*' | sort -V | tail -1)
git log --oneline "$LAST_TAG"..HEAD       # gather changes since the last tag
git tag -a <version> -m "<version> — <SHORT_SUMMARY>

<CATEGORIZED_CHANGES>"
```

Group the changes by type for the tag message: **Features** (`feat:`), **Fixes** (`fix:`),
**Documentation** (`docs:`), **Chores** (`chore:`).

### 4.2 Push branch + tag to the LIVE remote (HUMAN)

Pushing is a human act (ADR-A-0004 / ADR-A-0005 — the merge/publish gate is human).

**Push the LIVE remote — the pinned active remote, NOT `origin` by convention** (PILOT-25
remote doctrine). If `ORCH_MAIN_REMOTE` is set (e.g. `gitlab`), that is the live remote; on a
single-remote fork it is just `origin`.

```bash
LIVE_REMOTE="${ORCH_MAIN_REMOTE:-origin}"
git push "$LIVE_REMOTE" main
git push "$LIVE_REMOTE" <version>
```

### 4.2b Mirror the release to Bitbucket (release mirror — WARN-only)

After the tag lands on the live remote, mirror the finished version (main + tag) to the Bitbucket
**release mirror** (`origin`). This is the ONLY legitimate Bitbucket write — a release mirror,
nothing else (PILOT-25). **Bitbucket availability never gates the release:** any failure here is a
WARN and the release still succeeds.

```bash
bash scripts/release-mirror-push.sh <version>          # rehearse first with --dry-run
```

On a single-remote fork (no separate mirror) this is a no-op WARN — harmless.

### 4.3 Update the stable checkout (self-hosting)

After the tag is pushed, point the governing checkout at the new release so the NEXT development
cycle is governed by `<version>`:

```bash
cd ~/boilerplate-stable && git fetch --tags && git checkout <version>
```

If `<version>` graduated a release-candidate that was dogfooded in a throwaway checkout, delete
that throwaway checkout and its local RC tag now (see ORCHESTRATOR_SOP "RC dogfooding").

### 4.4 (GitHub forks only, optional) Publish a release object

```bash
gh release create <version> --title "<version> — <SHORT_SUMMARY>" --notes "$(cat <<'EOF'
## What's New
### Features
- <list features>
### Fixes
- <list fixes>
### Documentation
- <list doc changes>
## Stats
- **X files changed**, Y insertions, Z deletions
- **N tickets** closed
- Fully backward-compatible with <PREVIOUS_VERSION>
## Upgrade
<brief upgrade instructions or "No breaking changes.">
EOF
)"
```

On Bitbucket, skip this — the annotated tag + changelog entry is the record.

### 4.5 Structured release notes — Confluence page + Jira version description (ABS-226)

The `HARNESS_CHANGELOG.yml` entry for this version is turned into the two places
humans actually read release notes: a Confluence **Release Notes** page and the
**Jira version description** (stamped with a link + one-paragraph summary). This
follows the v2.24.1 reference format (info panel, change table with ticket links
+ category chips, operations notes).

> **Design note (ABS-226).** Confluence writes go through **curl against the
> Confluence REST API** (v2, storage format) — NOT the Atlassian MCP — reusing the
> same human-provisioned Keychain creds as Jira (`JIRA_EMAIL` + `JIRA_API_TOKEN`;
> Confluence lives at `$JIRA_SITE/wiki`). No new secrets. The Release-object
> rich-text sections themselves are not writable via any public API, so the notes
> live on a normal page the version description links to.

**Preview offline first** (pure render, no network, no creds):

```bash
bash scripts/release-notes.sh page <version>         # Confluence storage body
bash scripts/release-notes.sh description <version>  # Jira version-description text
```

**Publish** (renders the page, creates it in the `ADB` space under the
`Release Notes` parent, then stamps the Jira version description with the page
link via `jira-version.sh release --description-file`, atomically with the
released mark):

```bash
bash scripts/release-notes.sh publish <version>
```

- **Governor-only patch** (`changes: []`): a summary-only **stub page** is created
  for tag/changelog parity (AC5) — still run `publish`.
- **Confluence unreachable / no access**: `publish` degrades to a **WARN and does
  NOT abort** — the release proceeds and the Jira version is still marked released.
  Create the page by hand from `release-notes.sh page <version>` and re-stamp with
  `jira-version.sh release <version> --description-file <file>`. If the `Release
  Notes` parent needs elevated space permission you do not have, escalate to the
  human POPM — do not work around it.
- **MANUAL step (not API-settable):** on the Jira release page, click **"Add
  related work"** and link the Confluence page. `release-notes.sh` prints this
  reminder; do it by hand.

---

## Phase 5: Branch Sync

### 5.1 Sync All Long-Lived Branches

If the repository has multiple long-lived branches (e.g., `main` and `template`, or `main` and `dev`), sync them:

```bash
# Sync secondary branches to match primary
git push origin main:<SECONDARY_BRANCH>
```

Verify sync:

```bash
git log --oneline origin/main..origin/<SECONDARY_BRANCH>  # Should be empty
git log --oneline origin/<SECONDARY_BRANCH>..origin/main  # Should be empty
```

### 5.2 Verify the Tag Is Pushed

```bash
git tag -l 'v*' | sort -V | tail -5
gh pr list --state open                  # sanity: confirm no release PRs left open
```

---

## Phase 6: Cleanup

### 6.1 Delete Merged PR Branches

Delete stale branches from merged PRs via your host's UI or CLI (Bitbucket: delete via the PR view
or `bb`; GitHub: `gh api -X DELETE .../git/refs/heads/<BRANCH_NAME>`). Do not delete long-lived
branches (`main`, `dev`, `template`).

### 6.2 Clean Local

```bash
# Delete local branches that were merged
git branch --merged main | grep -v '^\*\|main' | xargs -r git branch -d

# Prune stale remote tracking refs
git fetch --prune origin

# Garbage collect
git gc --prune=now
```

### 6.3 Final Verification

```bash
echo "=== Local ===" && git branch -v
echo "=== Tags ===" && git tag -l 'v*' | sort -V | tail -5
echo "=== Governor pin ===" && cat .governor-tag         # must equal <version> (self-hosting)
echo "=== Drift guard ===" && git checkout <version> && bash scripts/generate-governor.sh --check
echo "=== Open PRs ===" && gh pr list --state open
```

---

## Output Format

Report final release status:

- ✅ PRs merged: (list with numbers)
- ✅ Governor promoted: `.governor-tag` → `<version>`, `.claude@<version> == generate(<version>)`
- ✅ Version bumped: `<OLD>` → `<NEW>`
- ✅ Annotated tag created + pushed: `<version>`
- ✅ Stable checkout updated to `<version>` (self-hosting)
- ✅ Branches synced: (list)
- ✅ Stale branches deleted: (count)
- ✅ Local cleaned and synced

Or flag blockers:

- ❌ BLOCKER: (description and recommended action)

## Success Criteria

- Annotated tag exists locally and on remote
- Governor pin (`.governor-tag`) equals `<version>`; `generate-governor.sh --check` clean at the tag (self-hosting)
- `~/boilerplate-stable` checked out at `<version>` (self-hosting)
- All long-lived branches are in sync
- No stale merged-PR branches remain
- Local working tree is clean on main
- Zero open PRs intended for this release

## Resolved Values (this repo)

| Value | Resolution |
|-------|------------|
| Primary branch | `main` |
| Ticket prefix | `AITBC` |
| Host PR CLI | `gh` (GitHub) |
| Remote repo slug | `oib/AITBC` |

> Reminder: per the scope note at the top of this file, this is the SAW harness's own
> self-hosting release process. AITBC's own `v0.x.y` application releases go through a separate,
> existing process (`docs/CHANGELOG.md`, the current `v0.*` tags) — not this command.
