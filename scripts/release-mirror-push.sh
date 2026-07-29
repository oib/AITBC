#!/usr/bin/env bash
# release-mirror-push.sh — push a finished release (main + tag) to the Bitbucket
# RELEASE MIRROR after it has landed on the live GitLab remote (PILOT-25, ABS-539).
#
# Remote doctrine (Operator, 2026-07-23): GitLab is the permanent LIVE remote;
# Bitbucket (`origin`) is a RELEASE MIRROR that receives ONLY finished versions —
# main + the release tag — at release time. This script is that mirror step, run by
# the /release flow AFTER the tag is pushed to GitLab (release.md Phase 4).
#
#   release-mirror-push.sh <tag> [--dry-run]
#
# It pushes <main-branch> and <tag> to the mirror remote. CRITICAL invariant:
# Bitbucket availability must NEVER gate the release. Any failure here — mirror
# remote absent, host unreachable, auth failure — is a WARN and the script still
# exits 0. Only a usage error (missing/invalid tag) exits non-zero (64).
#
# Env (all optional):
#   ORCH_MIRROR_REMOTE   mirror remote name (default: "origin" = Bitbucket).
#   ORCH_MAIN_REMOTE     the LIVE remote — informational; the mirror is the OTHER one.
#   ORCH_LOCAL_MAIN_BRANCH  main-like branch to mirror (default: "main").
#
# Runs against the git repo containing the current working directory. Offline-safe
# preflight; the single network act is the `git push` to the mirror. bash 3.2 + BSD.
set -uo pipefail

warn() { echo "release-mirror-push: WARN: $*" >&2; }
die()  { echo "release-mirror-push: $*" >&2; exit 64; }

# --- Parse args -------------------------------------------------------------
DRY_RUN=0
TAG=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --*) die "unknown option '$arg' (usage: release-mirror-push.sh <tag> [--dry-run])" ;;
        *)
            [ -z "$TAG" ] || die "multiple tags given ('$TAG', '$arg')"
            TAG="$arg"
            ;;
    esac
done
[ -n "$TAG" ] || die "usage: release-mirror-push.sh <tag> [--dry-run]"
case "$TAG" in
    v[0-9]*.[0-9]*.[0-9]*) : ;;
    *) die "'$TAG' is not a valid semver-ish tag (expected vMAJOR.MINOR.PATCH[-suffix])" ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || die "must run inside a git repository."

MIRROR_REMOTE="${ORCH_MIRROR_REMOTE:-origin}"
BRANCH="${ORCH_LOCAL_MAIN_BRANCH:-main}"

echo "=== release-mirror-push: mirror '$BRANCH' + '$TAG' to '$MIRROR_REMOTE' (Bitbucket release mirror) ==="

# Mirror remote configured? Absence is a WARN, never a gate.
if ! git -C "$REPO_ROOT" remote get-url "$MIRROR_REMOTE" >/dev/null 2>&1; then
    warn "mirror remote '$MIRROR_REMOTE' is not configured — skipping mirror push (release proceeds)."
    exit 0
fi

# Tag must exist locally (it was created + pushed to the LIVE remote already).
if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null 2>&1; then
    warn "tag '$TAG' does not exist locally — nothing to mirror (release proceeds)."
    exit 0
fi

PUSH_CMD="git -C \"$REPO_ROOT\" push \"$MIRROR_REMOTE\" \"$BRANCH\" \"$TAG\" --follow-tags"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "-> [dry-run] would run: $PUSH_CMD"
    echo "=== DRY-RUN OK: mirror push rehearsed (nothing pushed) ==="
    exit 0
fi

echo "-> $PUSH_CMD"
if git -C "$REPO_ROOT" push "$MIRROR_REMOTE" "$BRANCH" "$TAG" --follow-tags; then
    echo "=== mirror push OK: '$BRANCH' + '$TAG' now on '$MIRROR_REMOTE' ==="
    exit 0
fi

# Push failed — Bitbucket unreachable / auth / whatever. WARN, never gate.
warn "mirror push to '$MIRROR_REMOTE' FAILED — Bitbucket availability does NOT gate the release."
warn "The release is complete on the LIVE remote; mirror by hand later:  $PUSH_CMD"
exit 0
