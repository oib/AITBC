#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# SessionStart wrong-entry guard (ABS-92, stable-governs-dev Phase 1)
# =============================================================================
# In self-hosting mode the boilerplate is DEVELOPED under a pinned stable
# checkout (~/boilerplate-stable). The dev repo's own CLAUDE.md, hooks and agent
# defs are WORK PRODUCT, never instructions — so an interactive Claude session
# must be governed by the STABLE checkout, not launched directly inside the dev
# repo. This guard refuses the wrong entry point loudly, printing the correct
# launch recipe, and is otherwise a silent no-op.
#
# It fails (exit 2) ONLY when ALL of these hold (see AC below):
#   a. a stable root is resolved, exists, and is a DIFFERENT dir than this repo;
#   b. the stable root's git `origin` URL == this repo's `origin` URL (identity
#      check — makes the guard a silent no-op in consuming projects that happen
#      to have a ~/boilerplate-stable of some OTHER product);
#   c. cwd (the session project root = where the hook runs) IS this dev repo;
#   d. NO spawn markers present: ORCH_ROLE and ORCH_PACKET_FILE are both
#      unset/empty. Headless orchestrator spawns run with cwd = the dev repo and
#      MUST NOT be killed (AC H3b) — those set the spawn markers.
# In every other case it exits 0 silently.
#
# Escape hatch: SAW_GUARD_DISABLE=1 -> exit 0 (documented; for the rare case a
# human must run a bare session in the dev repo intentionally).
#
# bash 3.2 / BSD tools only (no mapfile, no grep -P, no timeout).
# =============================================================================

# Escape hatch first — cheapest, always honored.
if [ "${SAW_GUARD_DISABLE:-0}" = "1" ]; then
    exit 0
fi

# --- (d) spawn-marker exemption (AC H3b) -------------------------------------
# Headless orchestrator spawns run in the dev repo with these markers set. They
# are legitimate and must never be blocked, so bail out silently BEFORE any repo
# resolution work.
if [ -n "${ORCH_ROLE:-}" ] || [ -n "${ORCH_PACKET_FILE:-}" ]; then
    exit 0
fi

# GUARD_REPO_ROOT: this repo = the dir the guard script itself lives in (../ of
# scripts/). Resolved from the script's own location, independent of cwd.
# Use physical paths (pwd -P) throughout so the same-dir / cwd comparisons below
# are not defeated by a symlinked path (e.g. macOS /tmp -> /private/tmp).
GUARD_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
GUARD_REPO_ROOT="$(cd "$GUARD_SCRIPT_DIR/.." && pwd -P)"

# --- Resolve the stable root -------------------------------------------------
# ORCH_HARNESS_HOME wins (explicit harness marker); else the conventional
# ~/boilerplate-stable IF it exists. No stable root -> not self-hosting -> pass.
STABLE_ROOT=""
if [ -n "${ORCH_HARNESS_HOME:-}" ]; then
    STABLE_ROOT="$ORCH_HARNESS_HOME"
elif [ -d "$HOME/boilerplate-stable" ]; then
    STABLE_ROOT="$HOME/boilerplate-stable"
fi
[ -n "$STABLE_ROOT" ] || exit 0
[ -d "$STABLE_ROOT" ] || exit 0

# Normalize both to absolute physical paths for the same-dir comparison in (a).
STABLE_ROOT="$(cd "$STABLE_ROOT" 2>/dev/null && pwd -P)" || exit 0

# --- (a) stable must be a DIFFERENT directory than this repo ------------------
# If stable IS this repo, the session is already governed by stable -> pass.
[ "$STABLE_ROOT" != "$GUARD_REPO_ROOT" ] || exit 0

# --- (b) identity check: same product (matching git origin URL) --------------
# Silent no-op in a consuming project whose ~/boilerplate-stable is a different
# product. Resolve each repo's origin from ITS own worktree (never cwd-relative).
git_origin() {
    git -C "$1" config --get remote.origin.url 2>/dev/null || true
}
DEV_ORIGIN="$(git_origin "$GUARD_REPO_ROOT")"
STABLE_ORIGIN="$(git_origin "$STABLE_ROOT")"
# Both must resolve and match. An unresolved origin on either side -> pass (we
# cannot prove same-product identity, so never block).
[ -n "$DEV_ORIGIN" ] || exit 0
[ -n "$STABLE_ORIGIN" ] || exit 0
[ "$DEV_ORIGIN" = "$STABLE_ORIGIN" ] || exit 0

# --- (c) cwd must BE this dev repo -------------------------------------------
# The SessionStart hook runs at the session project root. Compare its physical
# path to the dev repo root. Not the dev repo (e.g. running from stable already)
# -> pass.
CWD_PHYS="$(pwd -P 2>/dev/null || pwd)"
[ "$CWD_PHYS" = "$GUARD_REPO_ROOT" ] || exit 0

# --- All conditions met: WRONG ENTRY. Fail loudly with the recipe. -----------
cat >&2 <<EOF
============================================================================
  WRONG ENTRY (ABS-92 stable-governs-dev): this dev repo will NOT govern an
  interactive session while a stable checkout of the same product exists.

  In self-hosting mode the boilerplate is developed UNDER the stable checkout:
    stable  = $STABLE_ROOT
    dev     = $GUARD_REPO_ROOT

  The dev repo's CLAUDE.md, hooks and agent definitions are WORK PRODUCT, not
  instructions. Rules must load from the stable checkout only.

  Launch a governed session instead:
    - interactive:  $GUARD_REPO_ROOT/scripts/dev-session.sh
    - orchestrator: ORCH_TARGET_REPO=$GUARD_REPO_ROOT $STABLE_ROOT/scripts/orchestrator.sh

  (Escape hatch, for a deliberate bare session: SAW_GUARD_DISABLE=1)
============================================================================
EOF
exit 2
