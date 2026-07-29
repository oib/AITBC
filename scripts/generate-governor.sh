#!/bin/bash
# =============================================================================
# generate-governor.sh -- materialize the live .claude/ from the release tag
# =============================================================================
# ABS-94 (Phase 2b, epic ABS-91 "self-hosting: stable governs dev").
#
# The live .claude/ in this repo is NOT a byte-copy of harness/claude anymore.
# It is generated(pin): the SHIPPED harness materialized from the RELEASE TAG
# recorded in the committed `.governor-tag` file. harness/claude/** diverges
# freely as inert work product; the pin bumps only at promotion (ABS-95).
# (harness/claude is the current source path; harness/.claude is the
# pre-v2.23.0 legacy name still found in older tags.)
#
# This script IS the generator and the drift-guard engine:
#
#   generate-governor.sh [<tag>] [--check]
#
#     <tag>     Governing tag. Defaults to the content of ./.governor-tag.
#               Accepts ANY existing tag, incl. RC / pre-release names.
#     --check   Compare only. No writes. Exit 1 on drift. This is what the
#               CI drift guard runs (tests/test-harness-parity.sh).
#
# WHAT IT MATERIALIZES (the shipped set, ABS-96 decision doc §2.1 -- EXACTLY):
#     agents/ skills/ commands/ hooks/ hooks-config.json
#     settings.template.json README.md SETUP.md TROUBLESHOOTING.md
#     AGENT_OUTPUT_GUIDE.md
# and the CLAUDE.md SAW-PROVENANCE-BANNER block (stamped with the tag).
#
# WHAT IT NEVER TOUCHES under the live .claude/ (LOCAL-RUNTIME, §2.1):
#     settings.local.json team-config.json worktrees/ .sync-exclude*
#     .harness-sync.json .harness-backup/ .harness-patches/
#   -- these exist only in the live tree and are the consuming project's own
#   files; generation replaces ONLY the shipped items and leaves the rest.
#
# LAYOUT-AWARE EXTRACTION: from the tag's tree the shipped source is
# `harness/claude/**` when that path exists at the tag (v2.23.0+), else
# `harness/.claude/**` (pre-rename tags, ABS-96+ through v2.22.x), else
# `.claude/<shipped items>` (legacy tags <= v2.16.x). v2.16.0 is legacy.
#
# DETERMINISM: two consecutive runs are byte-identical (stable git-archive
# extraction, no timestamps written into output). The banner text is canonical
# generator-owned metadata (not tag content) so a legacy tag whose CLAUDE.md
# predates the block still gets a correctly-stamped block written into the LIVE
# CLAUDE.md.
#
# bash 3.2 / BSD safe: no `timeout`, no `grep -P`, no `sed -i`, no associative
# arrays, no process substitution requirements. Never touches the network.
# Run from repo root (or anywhere inside the repo): bash scripts/generate-governor.sh
#
# RELEASE-COMMIT MODE (ABS-95, promote-release.sh):
#     generate-governor.sh --from-tree [--banner-tag <name>]
#
#   At a release commit the target tag does NOT exist yet (the tag is created
#   AFTER the commit). So the shipped set cannot be extracted from the tag tree.
#   --from-tree materializes the shipped set from the WORKING TREE's harness
#   source (`harness/claude/**` when present, else the pre-v2.23.0
#   `harness/.claude/**`, else the legacy `.claude/<items>`)
#   instead of `git archive <tag>`, and does NOT require the tag to exist.
#   --banner-tag <name> supplies the version string stamped into the banner (and
#   compared, with --check) -- default is the .governor-tag content. This is what
#   promote-release.sh uses to write generated(vN) at the release commit so that,
#   once the tag lands on that commit, `.claude@vN == generate(vN)` holds and the
#   ordinary tag-based `--check` (no flags) passes at the tag unchanged.
#   --from-tree composes with --check (compare only, no writes).
#
# PROVIDER-MIRROR MODE (ABS-142, ADR-A-0015):
#     generate-governor.sh --providers [--check]
#
#   Regenerates the agent_providers/claude_code/ mirror as a GENERATED VIEW of
#   the working-tree harness source (agents -> prompts/, hooks -> hooks/,
#   settings.template.json -> permissions/). This mirror tracks the working tree
#   (dev work product), NOT the .governor-tag pin, so the mode is tag-independent
#   and accepts no tag / --from-tree / --banner-tag. --check compares only and
#   exits 1 on drift (the byte-parity drift guard run by pre-release-check.sh and
#   tests/test-harness-parity.sh). promote-release.sh runs the write form so the
#   mirror is regenerated at every governor promotion.
# =============================================================================

set -u

# --- Resolve repo root (must be a git repo) ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "${REPO_ROOT:-}" ]; then
    echo "ERROR: generate-governor.sh must run inside a git repository." >&2
    exit 1
fi

GOVERNOR_TAG_FILE="$REPO_ROOT/.governor-tag"
LIVE_CLAUDE="$REPO_ROOT/.claude"
CLAUDE_MD="$REPO_ROOT/CLAUDE.md"
README_MD="$REPO_ROOT/README.md"   # ABS-129: root README carries the version badge

# --- The shipped set (ABS-96 §2.1) -- EXACT, order-stable --------------------
SHIPPED_ITEMS="agents skills commands hooks hooks-config.json settings.template.json README.md SETUP.md TROUBLESHOOTING.md AGENT_OUTPUT_GUIDE.md"

# --- LOCAL-RUNTIME items that must NEVER appear in a generated set -----------
LOCAL_RUNTIME_ITEMS="settings.local.json team-config.json worktrees .sync-exclude .sync-exclude.local .harness-sync.json .harness-backup .harness-patches"

# --- Parse args -------------------------------------------------------------
CHECK_ONLY=0
FROM_TREE=0
PROVIDERS=0
BANNER_TAG=""
TAG=""
WANT_BANNER_TAG=0
for arg in "$@"; do
    if [ "$WANT_BANNER_TAG" -eq 1 ]; then
        BANNER_TAG="$arg"
        WANT_BANNER_TAG=0
        continue
    fi
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --from-tree) FROM_TREE=1 ;;
        --providers) PROVIDERS=1 ;;
        --banner-tag) WANT_BANNER_TAG=1 ;;
        --*) echo "ERROR: unknown option '$arg'." >&2; exit 1 ;;
        *)
            if [ -n "$TAG" ]; then
                echo "ERROR: multiple tags given ('$TAG', '$arg')." >&2
                exit 1
            fi
            TAG="$arg"
            ;;
    esac
done
if [ "$WANT_BANNER_TAG" -eq 1 ]; then
    echo "ERROR: --banner-tag requires a value." >&2
    exit 1
fi
if [ "$FROM_TREE" -eq 0 ] && [ -n "$BANNER_TAG" ]; then
    echo "ERROR: --banner-tag is only valid with --from-tree." >&2
    exit 1
fi
if [ "$FROM_TREE" -eq 1 ] && [ -n "$TAG" ]; then
    echo "ERROR: --from-tree materializes from the working tree; a positional tag is not accepted (use --banner-tag for the stamped version)." >&2
    exit 1
fi
# ABS-142: --providers regenerates the agent_providers/claude_code/ mirror from
# the WORKING-TREE harness source; it is tag-independent, so it accepts neither a
# tag, --from-tree, nor --banner-tag. Only --check composes with it.
if [ "$PROVIDERS" -eq 1 ] && { [ "$FROM_TREE" -eq 1 ] || [ -n "$TAG" ] || [ -n "$BANNER_TAG" ]; }; then
    echo "ERROR: --providers does not accept a tag, --from-tree, or --banner-tag (it regenerates agent_providers/claude_code/ from the working-tree harness source)." >&2
    exit 1
fi

# --- Resolve the version string (TAG) used for banner stamping / comparison --
# In --from-tree mode the tag need not exist yet (release-commit case); the
# version string comes from --banner-tag, else .governor-tag. Otherwise TAG is
# a positional or .governor-tag content and MUST be an existing tag.
# (--providers is tag-independent and skips this resolution entirely.)
if [ "$PROVIDERS" -eq 1 ]; then
    : # no tag needed; handled in main after functions/TMP_ROOT are set up
elif [ "$FROM_TREE" -eq 1 ]; then
    if [ -n "$BANNER_TAG" ]; then
        TAG="$BANNER_TAG"
    else
        if [ ! -f "$GOVERNOR_TAG_FILE" ]; then
            echo "ERROR: --from-tree without --banner-tag and no .governor-tag file at $GOVERNOR_TAG_FILE." >&2
            exit 1
        fi
        TAG="$(sed -n '1p' "$GOVERNOR_TAG_FILE" | tr -d '[:space:]')"
        if [ -z "$TAG" ]; then
            echo "ERROR: .governor-tag is empty." >&2
            exit 1
        fi
    fi
    # No tag-existence check: --from-tree reads the working tree, not a tag tree.
else
    if [ -z "$TAG" ]; then
        if [ ! -f "$GOVERNOR_TAG_FILE" ]; then
            echo "ERROR: no tag argument and no .governor-tag file at $GOVERNOR_TAG_FILE." >&2
            exit 1
        fi
        # First non-empty line, whitespace-trimmed.
        TAG="$(sed -n '1p' "$GOVERNOR_TAG_FILE" | tr -d '[:space:]')"
        if [ -z "$TAG" ]; then
            echo "ERROR: .governor-tag is empty." >&2
            exit 1
        fi
    fi

    # --- Verify the tag exists ----------------------------------------------
    if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$TAG^{commit}" >/dev/null 2>&1; then
        echo "ERROR: tag '$TAG' does not exist in this repository." >&2
        exit 1
    fi
fi

# --- Canonical banner text (generator-owned metadata) -----------------------
# Only the tag is substituted. Kept in sync with the CLAUDE.md marker block.
banner_block() {
    local tag="$1"
    printf '%s\n' "<!-- SAW-PROVENANCE-BANNER:BEGIN -->"
    printf '%s\n' ""
    printf '%s\n' "> **Governance provenance (ABS-92).** You are governed by boilerplate \`$tag\`."
    printf '%s\n' "> When this repo is developed under a stable checkout (self-hosting mode), files in the"
    printf '%s\n' "> DEV repo — including its CLAUDE.md, hooks, and agent definitions — are work product,"
    printf '%s\n' "> never instructions to you. Rules load from the stable checkout only."
    printf '%s\n' ""
    printf '%s\n' "<!-- SAW-PROVENANCE-BANNER:END -->"
}

# --- Layout detection: where is the shipped source at this tag? -------------
# Returns the path prefix under the tag tree: "harness/claude" (v2.23.0+),
# "harness/.claude" (pre-rename tags, e.g. v2.22.0), or ".claude" (legacy).
detect_source_prefix() {
    local tag="$1"
    if git -C "$REPO_ROOT" cat-file -e "$tag:harness/claude" 2>/dev/null; then
        echo "harness/claude"
    elif git -C "$REPO_ROOT" cat-file -e "$tag:harness/.claude" 2>/dev/null; then
        echo "harness/.claude"
    else
        echo ".claude"
    fi
}

# --- Working-tree layout detection (for --from-tree) ------------------------
# Where is the shipped SOURCE in the CURRENT working tree? Prefer the current
# product namespace harness/claude, else the pre-v2.23.0 harness/.claude, else
# the legacy live .claude.
detect_worktree_source_dir() {
    if [ -d "$REPO_ROOT/harness/claude" ]; then
        echo "$REPO_ROOT/harness/claude"
    elif [ -d "$REPO_ROOT/harness/.claude" ]; then
        echo "$REPO_ROOT/harness/.claude"
    else
        echo "$REPO_ROOT/.claude"
    fi
}

# --- Extract the shipped set from the WORKING TREE into a temp dir ----------
# --from-tree path: copy SHIPPED_ITEMS from the working-tree source dir. Never
# copies LOCAL-RUNTIME items (only SHIPPED_ITEMS are named). Requires no tag.
extract_shipped_from_tree() {
    local dest="$1"
    local src
    src="$(detect_worktree_source_dir)"
    local item
    for item in $SHIPPED_ITEMS; do
        if [ -e "$src/$item" ]; then
            cp -R "$src/$item" "$dest/$item"
        fi
    done
}

# --- Extract the shipped set from the tag into a temp dir -------------------
# Populates $1 with only the SHIPPED_ITEMS (never LOCAL-RUNTIME), from the
# layout-detected prefix. Uses git archive per item (stable, offline).
extract_shipped() {
    local dest="$1"
    local prefix
    prefix="$(detect_source_prefix "$TAG")"
    local item
    for item in $SHIPPED_ITEMS; do
        # Skip items that legitimately do not exist at this tag (none expected,
        # but stay robust across tag ages).
        if git -C "$REPO_ROOT" cat-file -e "$TAG:$prefix/$item" 2>/dev/null; then
            # git archive preserves tree shape; extract just this path.
            git -C "$REPO_ROOT" archive "$TAG" "$prefix/$item" 2>/dev/null \
                | tar -x -C "$dest" 2>/dev/null
        fi
    done
    # The extracted tree is dest/$prefix/*; normalise so callers always see
    # dest/<items> directly (handles any detected prefix generically).
    if [ -d "$dest/$prefix" ]; then
        local it
        for it in $SHIPPED_ITEMS; do
            if [ -e "$dest/$prefix/$it" ]; then
                mv "$dest/$prefix/$it" "$dest/$it"
            fi
        done
        # Remove the (now-emptied) prefix scaffolding, top component only.
        rm -rf "$dest/${prefix%%/*}"
    fi
}

# --- Build the CLAUDE.md with the banner block stamped ----------------------
# Writes to $1 a copy of the live CLAUDE.md with ONLY the banner block replaced
# by banner_block($TAG). If no block exists, this is an error condition for a
# repo whose CLAUDE.md is expected to carry the markers -- but we (re)write the
# block in place of the existing markers only. The current live CLAUDE.md always
# has the markers (ABS-92), so we replace between them.
build_stamped_claude_md() {
    local dest="$1"
    if [ ! -f "$CLAUDE_MD" ]; then
        echo "ERROR: $CLAUDE_MD not found." >&2
        return 1
    fi
    if ! grep -q "SAW-PROVENANCE-BANNER:BEGIN" "$CLAUDE_MD" \
       || ! grep -q "SAW-PROVENANCE-BANNER:END" "$CLAUDE_MD"; then
        echo "ERROR: CLAUDE.md is missing the SAW-PROVENANCE-BANNER markers; cannot stamp." >&2
        return 1
    fi
    # awk: replace everything from BEGIN..END (inclusive) with the stamped block.
    # Banner text passed via env to avoid quoting hazards.
    SAW_BANNER="$(banner_block "$TAG")" awk '
        BEGIN { inblock = 0 }
        /SAW-PROVENANCE-BANNER:BEGIN/ {
            printf "%s\n", ENVIRON["SAW_BANNER"]
            inblock = 1
            next
        }
        /SAW-PROVENANCE-BANNER:END/ {
            if (inblock) { inblock = 0; next }
        }
        { if (!inblock) print }
    ' "$CLAUDE_MD" > "$dest"
}

# --- Build the root README.md with the version badge stamped (ABS-129) ------
# The top-level README carries a shields.io version badge that must always
# reflect the released version:
#     https://img.shields.io/badge/version-vX.Y.Z-<color>?style=...
# It is stamped at promotion (write) and asserted at --check, exactly like the
# CLAUDE.md provenance banner. TEXT-ONLY: only the badge message token is
# rewritten; every other line -- including historical version strings in
# changelog/upgrade references -- passes through byte-identical. Writes to $1 a
# copy of README.md with only the badge message set to $TAG. Returns non-zero
# (and writes nothing) when there is no root README to stamp -- callers then
# skip README handling gracefully.
build_stamped_readme() {
    local dest="$1"
    [ -f "$README_MD" ] || return 1
    # shields.io encodes a literal dash in the message as '--', so a prerelease
    # tag (vX.Y.Z-rc1) renders correctly and re-stamps idempotently.
    local badge_msg
    badge_msg="$(printf '%s' "$TAG" | sed 's/-/--/g')"
    # Rewrite ONLY the badge message: group 1 is the fixed prefix, the greedy
    # [^?"]* is the current message (it backtracks so the trailing -<color> is
    # left for group 2), group 2 is that "-<color>" plus its ? or " delimiter --
    # both preserved, so colour/style are untouched. A '.' in the shields host
    # is escaped so it matches literally.
    sed 's#\(img\.shields\.io/badge/version-\)[^?"]*\(-[a-z][a-z]*[?"]\)#\1'"$badge_msg"'\2#' \
        "$README_MD" > "$dest"
}

# --- Provider mirror: agent_providers/claude_code/ (ABS-142) ----------------
# The claude_code provider mirror is a GENERATED VIEW of the working-tree harness
# source (ADR-A-0015). It is regenerated at governor promotion and byte-parity
# checked at pre-release. Mapping (source -> mirror):
#     harness/claude/agents/<role>.md  -> prompts/<role>.md   (README.md excluded)
#     harness/claude/hooks/<name>      -> hooks/<name>
#     harness/claude/settings.template.json -> permissions/settings.template.json
# The mirror tracks the WORKING TREE (dev work product), not the pinned tag: it
# ships adapter prompts for the CURRENT harness, so its source is the same one
# --from-tree uses (detect_worktree_source_dir), independent of .governor-tag.
PROVIDERS_DIR="$REPO_ROOT/agent_providers/claude_code"

# Build the full expected mirror tree under $1 from the working-tree harness.
project_agent_providers() {
    local dest="$1"
    local src
    src="$(detect_worktree_source_dir)"
    mkdir -p "$dest/prompts" "$dest/hooks" "$dest/permissions"
    local f base
    # prompts/: one .md per agent role. README.md is not a role and is excluded;
    # so are underscore-prefixed shared fragments (e.g. _common-rules.md, ABS-174)
    # which the spawn seam prepends but which are never spawnable roles themselves.
    for f in "$src"/agents/*.md; do
        [ -e "$f" ] || continue
        base="$(basename "$f")"
        [ "$base" = "README.md" ] && continue
        case "$base" in _*) continue ;; esac
        cp "$f" "$dest/prompts/$base"
    done
    # hooks/: every shipped hook script, verbatim.
    for f in "$src"/hooks/*; do
        [ -e "$f" ] || continue
        cp -R "$f" "$dest/hooks/$(basename "$f")"
    done
    # permissions/settings.template.json: the shipped settings template, verbatim.
    if [ -e "$src/settings.template.json" ]; then
        cp "$src/settings.template.json" "$dest/permissions/settings.template.json"
    fi
}

# --providers entry point. Honours CHECK_ONLY. Uses TMP_ROOT for scratch.
run_providers_mode() {
    local gen="$TMP_ROOT/providers"
    mkdir -p "$gen"
    project_agent_providers "$gen"

    if [ "$CHECK_ONLY" -eq 1 ]; then
        if [ ! -d "$PROVIDERS_DIR" ]; then
            echo "DRIFT: $PROVIDERS_DIR does not exist (expected generated mirror)." >&2
            return 1
        fi
        if ! diff -r "$gen" "$PROVIDERS_DIR" >/dev/null 2>&1; then
            echo "DRIFT: agent_providers/claude_code/ differs from generated(harness/claude)." >&2
            diff -r "$gen" "$PROVIDERS_DIR" 2>&1 | sed 's/^/    /' >&2
            return 1
        fi
        echo "generate-governor.sh --providers --check: OK (agent_providers/claude_code == generated(harness/claude))."
        return 0
    fi

    # WRITE: replace the mirror's generated subtrees wholesale.
    mkdir -p "$PROVIDERS_DIR"
    rm -rf "$PROVIDERS_DIR/prompts" "$PROVIDERS_DIR/hooks" "$PROVIDERS_DIR/permissions"
    cp -R "$gen/prompts" "$PROVIDERS_DIR/prompts"
    cp -R "$gen/hooks" "$PROVIDERS_DIR/hooks"
    cp -R "$gen/permissions" "$PROVIDERS_DIR/permissions"
    echo "generate-governor.sh --providers: agent_providers/claude_code/ regenerated from harness/claude/."
    return 0
}

# --- Assert the generated set contains no LOCAL-RUNTIME items ----------------
assert_no_local_runtime() {
    local dir="$1"
    local bad=0
    local it
    for it in $LOCAL_RUNTIME_ITEMS; do
        if [ -e "$dir/$it" ]; then
            echo "ERROR: LOCAL-RUNTIME item '$it' leaked into the generated set." >&2
            bad=1
        fi
    done
    return $bad
}

# ============================================================================
# Main
# ============================================================================
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/governor.XXXXXX")" || {
    echo "ERROR: could not create temp dir." >&2; exit 1
}
GEN_DIR="$TMP_ROOT/gen"
mkdir -p "$GEN_DIR"
cleanup() { rm -rf "$TMP_ROOT"; }
trap cleanup EXIT

# ABS-142: --providers is a self-contained, tag-independent path.
if [ "$PROVIDERS" -eq 1 ]; then
    run_providers_mode
    exit $?
fi

if [ "$FROM_TREE" -eq 1 ]; then
    extract_shipped_from_tree "$GEN_DIR"
else
    extract_shipped "$GEN_DIR"
fi

if ! assert_no_local_runtime "$GEN_DIR"; then
    exit 1
fi

STAMPED_MD="$TMP_ROOT/CLAUDE.md.stamped"
if ! build_stamped_claude_md "$STAMPED_MD"; then
    exit 1
fi

# ABS-129: the root README version badge is stamped/compared alongside CLAUDE.md.
STAMPED_README="$TMP_ROOT/README.md.stamped"
HAVE_README=0
if build_stamped_readme "$STAMPED_README"; then
    HAVE_README=1
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    # -------- DRIFT CHECK: live == generated(pin) + banner == pin -----------
    DRIFT=0

    # Each shipped item must match generated. Compare recursively.
    for item in $SHIPPED_ITEMS; do
        if [ ! -e "$GEN_DIR/$item" ]; then
            # Item absent at tag -> live must also not have it as shipped.
            # (Not expected for v2.16.0; skip gracefully.)
            continue
        fi
        if ! diff -r "$GEN_DIR/$item" "$LIVE_CLAUDE/$item" >/dev/null 2>&1; then
            echo "DRIFT: .claude/$item differs from generated($TAG)." >&2
            DRIFT=1
        fi
    done

    # CLAUDE.md must be byte-identical to the stamped form.
    if ! diff "$STAMPED_MD" "$CLAUDE_MD" >/dev/null 2>&1; then
        echo "DRIFT: CLAUDE.md banner does not match generated($TAG)." >&2
        DRIFT=1
    fi

    # ABS-129: the root README version badge must match the pin.
    if [ "$HAVE_README" -eq 1 ] && ! diff "$STAMPED_README" "$README_MD" >/dev/null 2>&1; then
        echo "DRIFT: README.md version badge does not match generated($TAG)." >&2
        DRIFT=1
    fi

    if [ "$DRIFT" -ne 0 ]; then
        echo "generate-governor.sh --check: DRIFT detected against tag '$TAG'." >&2
        exit 1
    fi
    echo "generate-governor.sh --check: OK (live .claude == generated($TAG), banner stamped)."
    exit 0
fi

# -------- WRITE: materialize generated(pin) into the live tree --------------
if [ ! -d "$LIVE_CLAUDE" ]; then
    echo "ERROR: live .claude/ not found at $LIVE_CLAUDE." >&2
    exit 1
fi

for item in $SHIPPED_ITEMS; do
    if [ ! -e "$GEN_DIR/$item" ]; then
        continue
    fi
    # Replace the shipped item wholesale; never touch anything else in .claude/.
    rm -rf "$LIVE_CLAUDE/$item"
    cp -R "$GEN_DIR/$item" "$LIVE_CLAUDE/$item"
done

cp "$STAMPED_MD" "$CLAUDE_MD"

# ABS-129: stamp the root README version badge to the pin.
if [ "$HAVE_README" -eq 1 ]; then
    cp "$STAMPED_README" "$README_MD"
fi

echo "generate-governor.sh: live .claude/ materialized from generated($TAG); CLAUDE.md banner + README badge stamped '$TAG'."
exit 0
