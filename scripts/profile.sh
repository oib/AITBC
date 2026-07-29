#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Profile CLI (ABS-37) — mechanical activation for profiles/*/profile.yaml
# =============================================================================
# Stack profiles were declarative-only: nothing set an active profile, and
# only scripts/hooks/evolver-lifecycle.sh read profile.yaml at all. This CLI
# is the mechanical activation point on top of scripts/lib/profile.sh:
#
#   scripts/profile.sh show        active profile + resolved provider per capability
#   scripts/profile.sh set <name>  validate profiles/<name>/profile.yaml exists,
#                                  write it to .active-profile
#
# Precedence (see scripts/lib/profile.sh): ACTIVE_PROFILE env > .active-profile
# file > "neutral" default. `set` only ever writes the file layer — an
# ACTIVE_PROFILE env var still wins at resolution time.
#
# No YAML parser dependency: grep/sed only, bash 3.2 / BSD safe (macOS default
# bash). See profiles/README.md "Activating a profile".
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILES_DIR="$REPO_ROOT/profiles"

# shellcheck source=lib/profile.sh
source "$SCRIPT_DIR/lib/profile.sh"

usage() {
  cat <<'EOF'
scripts/profile.sh — show or set the active stack profile (ABS-37)

Usage:
  scripts/profile.sh show           Print the active profile and each
                                     capability's resolved provider.
  scripts/profile.sh set <name>     Activate profiles/<name>/profile.yaml
                                     by writing .active-profile.

Precedence: ACTIVE_PROFILE env var > .active-profile file > "neutral".
EOF
}

# List capability keys declared under the top-level `capabilities:` block.
list_capabilities() {
  local file="$1"
  awk '
    /^capabilities:/ { in_caps = 1; next }
    in_caps && /^[A-Za-z]/ { in_caps = 0 }
    in_caps && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
      line = $0
      sub(/^  /, "", line)
      sub(/:.*/, "", line)
      print line
    }
  ' "$file"
}

cmd_show() {
  local profile file cap provider
  profile="$(get_active_profile)"
  file="$PROFILES_DIR/$profile/profile.yaml"

  echo "Active profile: $profile"
  if [ ! -f "$file" ]; then
    echo "  (no profile.yaml found at $file)"
    return 0
  fi
  echo "Capabilities:"
  while IFS= read -r cap; do
    [ -n "$cap" ] || continue
    provider="$(get_capability_provider "$cap")"
    printf '  %-16s -> %s\n' "$cap" "$provider"
  done < <(list_capabilities "$file")
}

cmd_set() {
  local name="${1:-}"
  if [ -z "$name" ]; then
    echo "profile.sh: set requires a profile name (e.g. 'scripts/profile.sh set evolver')" >&2
    exit 1
  fi
  if [ ! -f "$PROFILES_DIR/$name/profile.yaml" ]; then
    echo "profile.sh: ERROR unknown profile '$name' (no $PROFILES_DIR/$name/profile.yaml)" >&2
    exit 1
  fi
  printf '%s\n' "$name" >"$ACTIVE_PROFILE_FILE"
  echo "profile.sh: activated '$name' ($ACTIVE_PROFILE_FILE written)"
  if [ -n "${ACTIVE_PROFILE:-}" ] && [ "${ACTIVE_PROFILE}" != "$name" ]; then
    echo "profile.sh: NOTE ACTIVE_PROFILE env var is set to '${ACTIVE_PROFILE}' and will override this at resolution time" >&2
  fi
}

main() {
  local sub="${1:-}"
  case "$sub" in
    show)
      cmd_show
      ;;
    set)
      shift || true
      cmd_set "${1:-}"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "profile.sh: unknown subcommand '$sub'" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
