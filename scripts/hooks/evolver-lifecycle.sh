#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Evolver Lifecycle Hook (ABS-25) — thin wrapper for evolver --review
# =============================================================================
# Project-level integration only (.claude/hooks-config.json). Do NOT run
# evolver setup-hooks — that writes user-level config.
#
# Exit 0 on skip (evolver not installed, provider none, rate-limited) or success.
# See specs/ABS-25-evolver-integration-spec.md §5.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "${CLAUDE_PROJECT_DIR:-$REPO_ROOT}"

# shellcheck source=../lib/profile.sh
source "$REPO_ROOT/scripts/lib/profile.sh"

RATE_LIMIT_FILE=".evolver/.last-hook-run"
RATE_LIMIT_SECS=300

log() { echo "evolver-lifecycle: $*" >&2; }

# EVOLUTION_PROVIDER env keeps its override (unchanged behavior); otherwise
# resolve via scripts/lib/profile.sh, which applies the ABS-37 activation
# precedence (ACTIVE_PROFILE env > .active-profile file > neutral) and the
# based_on fallback (e.g. a profile without its own `evolution` key falls
# back to neutral's).
get_evolution_provider() {
  if [ -n "${EVOLUTION_PROVIDER:-}" ]; then
    echo "$EVOLUTION_PROVIDER"
    return
  fi
  get_capability_provider evolution
}

provider="$(get_evolution_provider)"
if [ "$provider" = "none" ]; then
  log "SKIP evolution provider none"
  exit 0
fi

if ! command -v evolver >/dev/null 2>&1; then
  log "SKIP evolver not installed"
  exit 0
fi

mkdir -p .evolver
if [ -f "$RATE_LIMIT_FILE" ]; then
  last_run="$(cat "$RATE_LIMIT_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  if [ "$((now - last_run))" -lt "$RATE_LIMIT_SECS" ]; then
    log "SKIP rate limit (${RATE_LIMIT_SECS}s)"
    exit 0
  fi
fi

export EVOLVER_AUTO_ISSUE="${EVOLVER_AUTO_ISSUE:-false}"
export EVOLVER_VALIDATOR_ENABLED="${EVOLVER_VALIDATOR_ENABLED:-0}"

log "RUN evolver --review provider=$provider"

if evolver --review >&2; then
  date +%s >"$RATE_LIMIT_FILE"
  exit 0
else
  # $? here is the exit status of `evolver --review`; a bare $? after the `if`
  # would report the compound statement's status (0) instead of evolver's.
  log "WARN evolver exited $?"
fi
exit 0
