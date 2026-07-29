#!/bin/bash
# =============================================================================
# promote-release.sh -- promotion = release (ABS-95, epic ABS-91 self-hosting)
# =============================================================================
# Promotion rolls the live governor forward, as one whole version, on a single
# release commit, then tags that commit -- so a consumer syncing the legacy
# .claude domain at the tag gets exactly the generated form of that release:
#
#     .claude@vN  ==  generate(vN)
#
#   promote-release.sh <new-tag> [--dry-run]
#
# STEPS (real mode, on the current repo at HEAD):
#   1. Preflight: clean tree; on a main-like branch; <new-tag> does NOT already
#      exist; <new-tag> is a valid semver-ish name.
#   2. Write <new-tag> to .governor-tag.
#   3. Regenerate the live .claude/ from the CURRENT TREE's harness source and
#      stamp the banner with <new-tag>:
#          generate-governor.sh --from-tree --banner-tag <new-tag>
#      (--from-tree is REQUIRED here: at a release commit <new-tag> does not
#      exist yet, so the shipped set cannot be extracted from the tag tree; it
#      is materialized from harness/claude/** in the working tree instead. The
#      ordinary tag-based `generate-governor.sh --check` semantics are untouched
#      -- once the tag lands on this commit, that check passes at the tag.)
#   4. git add the regenerated shipped set + CLAUDE.md + .governor-tag.
#   5. Single release commit.
#   6. Annotated tag `git tag -a <new-tag>` ON that commit.
#   7. Print follow-ups (human): push the tag; update ~/boilerplate-stable.
#   This script NEVER pushes -- pushing (tag or branch) is a human act.
#
# --dry-run: do ALL of the above inside a throwaway `git clone --local` of this
#   repo (mktemp), including the commit + local tag THERE, then verify TAG
#   FRESHNESS in the scratch clone: run the ORDINARY tag-based
#   `generate-governor.sh --check` at the scratch tag and assert clean
#   (.claude@tag == generate(tag)) and that the banner carries <new-tag>. Prints
#   evidence. NEVER creates tags/commits in the real repo. Cleans up on exit.
#
# bash 3.2 / BSD-safe: no `timeout`, no `grep -P`, no `sed -i`, no associative
# arrays. Offline. Run from anywhere inside the repo.
# =============================================================================

set -u

# --- Resolve repo root (must be a git repo) ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "${REPO_ROOT:-}" ]; then
    echo "ERROR: promote-release.sh must run inside a git repository." >&2
    exit 1
fi

# --- Main-like branch names (release is cut from one of these) --------------
MAIN_BRANCH="main"          # main -- template projects: set to your primary branch
MAINLIKE_BRANCHES="main master template"

# --- Parse args -------------------------------------------------------------
DRY_RUN=0
NEW_TAG=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --*) echo "ERROR: unknown option '$arg'." >&2; exit 1 ;;
        *)
            if [ -n "$NEW_TAG" ]; then
                echo "ERROR: multiple tags given ('$NEW_TAG', '$arg')." >&2
                exit 1
            fi
            NEW_TAG="$arg"
            ;;
    esac
done

# ABS-111 / PILOT-7: the tracker is the source of truth for the planned next
# version. With no tag argument, resolve the lowest unreleased version from the
# version helper bound to the ACTIVE PROFILE's task-tracking provider (Jira ->
# jira-version.sh, agentic-backend -> backend-version.sh). An explicit argument
# always wins; with no version source (mock/none) the legacy usage error stands.
# shellcheck source=lib/version-source.sh
. "$SCRIPT_DIR/lib/version-source.sh"
_version_script="$(resolve_version_script)"
if [ -z "$NEW_TAG" ] && [ -n "$_version_script" ]; then
    NEW_TAG="$(bash "$SCRIPT_DIR/$_version_script" next 2>/dev/null || true)"
    if [ -n "$NEW_TAG" ]; then
        echo "promote-release: resolved next version from ${_version_script%-version.sh}: $NEW_TAG"
    fi
fi
unset _version_script

if [ -z "$NEW_TAG" ]; then
    echo "ERROR: usage: promote-release.sh <new-tag> [--dry-run]" >&2
    echo "       (or plan the next version in Jira and export the JIRA_* env:" >&2
    echo "        scripts/jira-version.sh create vX.Y.Z — then the tag argument is optional)" >&2
    exit 1
fi

# --- Validate the tag is a semver-ish name ----------------------------------
# vMAJOR.MINOR.PATCH with an optional -prerelease suffix (e.g. v2.17.0,
# v2.17.0-rc1, v2.17.0-dryrun). Deliberately permissive on the suffix.
validate_semverish() {
    local t="$1"
    case "$t" in
        v[0-9]*.[0-9]*.[0-9]*) : ;;
        *)
            echo "ERROR: '$t' is not a valid semver-ish tag (expected vMAJOR.MINOR.PATCH[-suffix], e.g. v2.17.0)." >&2
            return 1
            ;;
    esac
    # Reject whitespace / obviously malformed names.
    case "$t" in
        *[!A-Za-z0-9.\-]*)
            echo "ERROR: tag '$t' contains characters that are not [A-Za-z0-9.-]." >&2
            return 1
            ;;
    esac
    return 0
}

# --- Is a branch name main-like? --------------------------------------------
is_mainlike() {
    local b="$1"
    local m
    for m in $MAINLIKE_BRANCHES; do
        if [ "$b" = "$m" ]; then
            return 0
        fi
    done
    return 1
}

# ============================================================================
# The promotion body -- run against a given repo root ($1). Creates the release
# commit + annotated tag in THAT repo. Used by both real and dry-run mode (in
# dry-run it targets the scratch clone).
# ============================================================================
do_promotion() {
    local root="$1"
    local tag="$2"

    printf '%s\n' "-> writing pin: .governor-tag = $tag"
    printf '%s\n' "$tag" > "$root/.governor-tag"

    # ABS-139: .boilerplate-version is the migration marker (BOILERPLATE_MIGRATION_SOP
    # §1.2): exactly one line, the semantic version with NO 'v' prefix and no comments.
    # It must move in lockstep with .governor-tag so the two never drift again (they
    # did, v2.10.0 through 11 releases). pre-release-check.sh asserts they agree.
    local marker_version="${tag#v}"
    printf '%s\n' "-> writing migration marker: .boilerplate-version = $marker_version"
    printf '%s\n' "$marker_version" > "$root/.boilerplate-version"

    printf '%s\n' "-> regenerating live .claude/ from working-tree harness source (banner: $tag)"
    if ! bash "$root/scripts/generate-governor.sh" --from-tree --banner-tag "$tag"; then
        echo "ERROR: generator (--from-tree) failed." >&2
        return 1
    fi

    # ABS-142 (ADR-A-0015): the agent_providers/claude_code/ mirror is a generated
    # view of the harness source and is regenerated at every promotion so it can
    # never drift (pre-release-check.sh byte-parity guards it).
    printf '%s\n' "-> regenerating agent_providers/claude_code/ mirror from working-tree harness source"
    if ! bash "$root/scripts/generate-governor.sh" --providers; then
        echo "ERROR: generator (--providers) failed." >&2
        return 1
    fi

    printf '%s\n' "-> staging regenerated shipped set + provider mirror + CLAUDE.md + README badge + .governor-tag + .boilerplate-version"
    # Stage the whole live .claude shipped set, the banner-stamped CLAUDE.md, the
    # badge-stamped root README.md (ABS-129), the pin, and the migration marker
    # (.boilerplate-version, ABS-139). `git add` on .claude/ picks up only tracked
    # shipped items that changed (LOCAL-RUNTIME items are gitignored, so they are
    # never staged).
    ( cd "$root" && git add .claude agent_providers/claude_code CLAUDE.md README.md .governor-tag .boilerplate-version ) || {
        echo "ERROR: git add failed." >&2
        return 1
    }

    printf '%s\n' "-> creating the release commit"
    ( cd "$root" && git commit -q -m "chore(release): promote governor to $tag

Regenerate live .claude/ from harness source, stamp provenance banner, and
bump .governor-tag to $tag so .claude@$tag == generate($tag) (ABS-95).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" ) || {
        echo "ERROR: release commit failed (nothing to commit? tree already at $tag?)." >&2
        return 1
    }

    printf '%s\n' "-> tagging the release commit: $tag"
    ( cd "$root" && git tag -a "$tag" -m "$tag -- self-hosting governor promotion (ABS-95)" ) || {
        echo "ERROR: git tag failed." >&2
        return 1
    }

    return 0
}

# ============================================================================
# DRY-RUN: everything in a scratch clone; verify tag freshness; never touch the
# real repo.
# ============================================================================
if [ "$DRY_RUN" -eq 1 ]; then
    echo "=== promote-release.sh --dry-run: $NEW_TAG ==="

    if ! validate_semverish "$NEW_TAG"; then
        exit 1
    fi

    # Preflight (relaxed for a scratch clone): the tag must not already exist in
    # the real repo (the dry-run would otherwise validate a stale target). Tree
    # cleanliness / branch are NOT enforced here -- the scratch clone is a fresh
    # checkout of HEAD and the whole point is to rehearse without touching the
    # real tree.
    if git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$NEW_TAG" >/dev/null 2>&1; then
        echo "ERROR: tag '$NEW_TAG' already exists in this repository." >&2
        exit 1
    fi

    SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/promote-dryrun.XXXXXX")" || {
        echo "ERROR: could not create scratch dir." >&2; exit 1
    }
    CLONE="$SCRATCH/clone"
    cleanup() { rm -rf "$SCRATCH"; }
    trap cleanup EXIT

    echo "-> cloning (local) into scratch: $CLONE"
    if ! git clone --local --quiet "$REPO_ROOT" "$CLONE"; then
        echo "ERROR: local clone failed." >&2
        exit 1
    fi

    # Sync the CURRENT working-tree copies of the generator + this script into
    # the clone. A `--local` clone carries only COMMITTED HEAD; when the ABS-95
    # generator/promotion changes are still uncommitted, the dry-run must
    # rehearse the mechanism AS IT EXISTS NOW (it will be committed alongside the
    # promotion). Copying just these two scripts keeps the clone's TREE (harness
    # source + live .claude) at HEAD -- which is what a real release operates on.
    echo "-> syncing working-tree generator + promotion script into the clone"
    cp "$REPO_ROOT/scripts/generate-governor.sh" "$CLONE/scripts/generate-governor.sh"
    cp "$REPO_ROOT/scripts/promote-release.sh"   "$CLONE/scripts/promote-release.sh"

    # The clone's default checkout is the current branch's HEAD. Ensure a
    # deterministic identity for the scratch commit (never touches real config).
    ( cd "$CLONE" \
        && git config user.email "promote-dryrun@localhost" \
        && git config user.name "promote-release dry-run" ) || {
        echo "ERROR: could not set scratch git identity." >&2
        exit 1
    }

    if ! do_promotion "$CLONE" "$NEW_TAG"; then
        echo "DRY-RUN FAILED during promotion." >&2
        exit 1
    fi

    echo ""
    echo "=== tag-freshness verification (scratch clone, at the scratch tag) ==="
    # The pin now names the freshly-created scratch tag, which exists in the
    # clone. Run the ORDINARY tag-based --check: it extracts the shipped set from
    # the tag tree and compares against the live .claude/ committed at that tag.
    # Clean output PROVES .claude@<tag> == generate(<tag>).
    FRESH_OUT="$( ( cd "$CLONE" && bash scripts/generate-governor.sh --check ) 2>&1 )"
    FRESH_RC=$?
    printf '%s\n' "$FRESH_OUT"
    if [ "$FRESH_RC" -ne 0 ]; then
        echo "DRY-RUN FAILED: tag-freshness check did not pass at $NEW_TAG." >&2
        exit 1
    fi

    # Confirm the pin was bumped and the banner carries the new version.
    SCRATCH_PIN="$( sed -n '1p' "$CLONE/.governor-tag" | tr -d '[:space:]' )"
    if [ "$SCRATCH_PIN" != "$NEW_TAG" ]; then
        echo "DRY-RUN FAILED: .governor-tag is '$SCRATCH_PIN', expected '$NEW_TAG'." >&2
        exit 1
    fi
    # ABS-139: the migration marker must carry the same version, sans 'v' prefix.
    SCRATCH_MARKER="$( sed -n '1p' "$CLONE/.boilerplate-version" | tr -d '[:space:]' )"
    if [ "$SCRATCH_MARKER" != "${NEW_TAG#v}" ]; then
        echo "DRY-RUN FAILED: .boilerplate-version is '$SCRATCH_MARKER', expected '${NEW_TAG#v}'." >&2
        exit 1
    fi
    if ! grep -q "boilerplate \`$NEW_TAG\`" "$CLONE/CLAUDE.md"; then
        echo "DRY-RUN FAILED: CLAUDE.md banner does not carry '$NEW_TAG'." >&2
        exit 1
    fi
    # ABS-129: confirm the README version badge was stamped in the scratch clone
    # (shields.io encodes a literal dash in the message as '--').
    BADGE_MSG_EXPECT="$( printf '%s' "$NEW_TAG" | sed 's/-/--/g' )"
    if ! grep -q "badge/version-$BADGE_MSG_EXPECT-" "$CLONE/README.md"; then
        echo "DRY-RUN FAILED: README.md version badge does not carry '$NEW_TAG'." >&2
        exit 1
    fi

    # Evidence dump.
    echo ""
    echo "=== dry-run evidence ==="
    echo "release commit (scratch):"
    ( cd "$CLONE" && git log -1 --oneline )
    echo "scratch tag points at that commit:"
    ( cd "$CLONE" && git rev-list -n1 "$NEW_TAG" | cut -c1-12 )
    ( cd "$CLONE" && git rev-parse --short=12 HEAD )
    echo ".governor-tag (scratch): $SCRATCH_PIN"
    echo ".boilerplate-version (scratch): $SCRATCH_MARKER"
    echo "banner line (scratch):"
    grep "Governance provenance" "$CLONE/CLAUDE.md" | sed 's/^/    /'
    echo ""
    echo "REAL REPO UNTOUCHED -- verifying no new tag/commit here:"
    if git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$NEW_TAG" >/dev/null 2>&1; then
        echo "ERROR: the real repo unexpectedly has tag '$NEW_TAG'!" >&2
        exit 1
    fi
    echo "    ok: real repo has no '$NEW_TAG' tag; scratch cleaned up on exit."
    echo ""
    echo "=== DRY-RUN OK: promotion is mechanically sound; tag-freshness clean at $NEW_TAG ==="
    exit 0
fi

# ============================================================================
# REAL MODE: promote in place. Preflight is strict.
# ============================================================================
echo "=== promote-release.sh: $NEW_TAG ==="

if ! validate_semverish "$NEW_TAG"; then
    exit 1
fi

# Tag must not already exist.
if git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$NEW_TAG" >/dev/null 2>&1; then
    echo "ERROR: tag '$NEW_TAG' already exists." >&2
    exit 1
fi

# Clean working tree (no staged or unstaged changes to tracked files).
if [ -n "$( git -C "$REPO_ROOT" status --porcelain --untracked-files=no )" ]; then
    echo "ERROR: working tree is not clean. Commit or stash tracked changes before promoting." >&2
    exit 1
fi

# On a main-like branch.
CUR_BRANCH="$( git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD )"
if ! is_mainlike "$CUR_BRANCH"; then
    echo "ERROR: on branch '$CUR_BRANCH'; a release must be cut from a main-like branch ($MAINLIKE_BRANCHES)." >&2
    echo "       (Override the branch list at the top of this script if your primary branch differs.)" >&2
    exit 1
fi

if ! do_promotion "$REPO_ROOT" "$NEW_TAG"; then
    echo "PROMOTION FAILED." >&2
    exit 1
fi

echo ""
echo "=== promotion complete (local): $NEW_TAG ==="
( cd "$REPO_ROOT" && git log -1 --oneline )
echo ""
echo "Follow-ups (HUMAN -- this script pushes nothing):"
echo "  1. Push the branch + tag:   git push origin $CUR_BRANCH && git push origin $NEW_TAG"
echo "  2. Update the stable checkout:  cd ~/boilerplate-stable && git fetch --tags && git checkout $NEW_TAG"
echo "  3. (RC path) if this graduated an RC, delete the throwaway RC checkout + local RC tag."
echo "  4. Mark the Jira version released:  scripts/jira-version.sh release $NEW_TAG  (and plan the next one: scripts/jira-version.sh create vX.Y.Z)"
echo ""
echo "Invariant established: .claude@$NEW_TAG == generate($NEW_TAG) (run: git checkout $NEW_TAG && bash scripts/generate-governor.sh --check)."
exit 0
