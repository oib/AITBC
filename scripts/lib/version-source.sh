#!/usr/bin/env bash
# =============================================================================
# version-source.sh — resolve the planned-version script for the active profile
# =============================================================================
# The release tooling (promote-release.sh / pre-release-check.sh) resolves the
# NEXT version from the tracker that owns it. WHICH tracker is a profile choice,
# so this maps the active profile's `task-tracking` provider onto the matching
# `*-version.sh` helper (PILOT-7 / ADR-A-0007: release tooling speaks only through
# the version-script seam, never a tracker adapter directly).
#
# Minimal dispatch, NOT a refactor: sourceable, bash 3.2 / BSD safe.
#
# Usage:
#   source "$SCRIPT_DIR/lib/version-source.sh"
#   vs="$(resolve_version_script)"     # "jira-version.sh" | "backend-version.sh" | ""
# =============================================================================

# shellcheck source=profile.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/profile.sh"

# resolve_version_script — print the version helper bound to the active profile's
# task-tracking provider, or nothing when the provider plans no versions (mock/none/…).
resolve_version_script() {
  local provider
  provider="$(get_capability_provider task-tracking 2>/dev/null || echo none)"
  case "$provider" in
    jira-cloud|jira*)   echo "jira-version.sh" ;;
    agentic-backend)    echo "backend-version.sh" ;;
    *)                  echo "" ;;
  esac
}
