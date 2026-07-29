#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# dev-session.sh — launch a governed interactive session (ABS-92 Phase 1)
# =============================================================================
# Human ergonomics for stable-governs-dev mode: launches an interactive Claude
# session that is GOVERNED by the pinned stable checkout while making the dev
# repo available as an added working directory. Rules (CLAUDE.md, hooks, agent
# defs) load from stable; the dev repo is the work target.
#
#   stable governs  ->  cd <stable> && exec claude --add-dir <dev repo>
#
# Resolution:
#   stable root = ORCH_HARNESS_HOME if set, else ~/boilerplate-stable, else die.
#   dev repo    = this script's own repo root (../ of scripts/).
# Both must exist and share the same git origin URL (same product) — otherwise
# we refuse rather than silently governing with a mismatched checkout.
#
# bash 3.2 / BSD tools only. Extra args after the recipe are forwarded to claude.
# =============================================================================

die() { echo "dev-session: ERROR $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DEV_REPO="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# --- Resolve the stable/harness root -----------------------------------------
STABLE_ROOT=""
if [ -n "${ORCH_HARNESS_HOME:-}" ]; then
    STABLE_ROOT="$ORCH_HARNESS_HOME"
elif [ -d "$HOME/boilerplate-stable" ]; then
    STABLE_ROOT="$HOME/boilerplate-stable"
else
    die "no stable checkout found. Set ORCH_HARNESS_HOME=<stable> or create ~/boilerplate-stable (a pinned release checkout of this product)."
fi
[ -d "$STABLE_ROOT" ] || die "stable root does not exist: $STABLE_ROOT"
STABLE_ROOT="$(cd "$STABLE_ROOT" && pwd)"

# --- Same-product identity check (matching git origin URL) -------------------
git_origin() { git -C "$1" config --get remote.origin.url 2>/dev/null || true; }
DEV_ORIGIN="$(git_origin "$DEV_REPO")"
STABLE_ORIGIN="$(git_origin "$STABLE_ROOT")"
[ -n "$DEV_ORIGIN" ] || die "dev repo has no git origin URL: $DEV_REPO"
[ -n "$STABLE_ORIGIN" ] || die "stable checkout has no git origin URL: $STABLE_ROOT"
[ "$DEV_ORIGIN" = "$STABLE_ORIGIN" ] || die "stable/dev origin mismatch (not the same product): stable=$STABLE_ORIGIN dev=$DEV_ORIGIN"

# --- One-line provenance header, then launch governed by stable --------------
echo "dev-session: governed by stable=$STABLE_ROOT | dev target=$DEV_REPO (rules load from stable; dev repo is work product)"
cd "$STABLE_ROOT" || die "cannot cd to stable: $STABLE_ROOT"
exec claude --add-dir "$DEV_REPO" "$@"
