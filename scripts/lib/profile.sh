#!/usr/bin/env bash
# =============================================================================
# Profile Resolution Helper (ABS-37) — sourceable, bash 3.2 / BSD safe
# =============================================================================
# Shared logic for resolving the ACTIVE profile and the provider bound to a
# capability in that profile's profiles/<name>/profile.yaml. Consumed by
# scripts/profile.sh (CLI) and scripts/hooks/evolver-lifecycle.sh (provider
# resolution), so both agree on precedence and parsing.
#
# No YAML parser dependency: profile.yaml is read with grep/sed only, the
# same shallow "find the capability block, grep its provider: line" strategy
# already used by evolver-lifecycle.sh before this refactor.
#
# Activation point precedence (ABS-37, extended ABS-257):
#   1. ACTIVE_PROFILE env var        (wins unconditionally — CI/local override)
#   2. .active-profile file          (repo root; plain text, one profile name)
#   3. .active-profile of the MAIN CHECKOUT when REPO_ROOT is a linked git
#      worktree (ABS-257 — see _main_checkout_active_profile_file below)
#   4. "neutral"                     (default when none is set)
#
# .active-profile is a plain file (not YAML) deliberately: it must be
# parsable with only bash 3.2 + grep/sed (no yq/python dependency), and a
# single bare name needs no structure. ABS-48 (bootstrap) is expected to
# write this file during setup-template.sh; this ticket only wires the
# mechanical read/write/resolve path.
#
# Usage:
#   source "$REPO_ROOT/scripts/lib/profile.sh"
#   profile="$(get_active_profile)"
#   provider="$(get_capability_provider evolution)"
# =============================================================================

# Resolve REPO_ROOT if the sourcing script hasn't already set it.
# Callers that already export REPO_ROOT (evolver-lifecycle.sh, profile.sh)
# always win; this is a best-effort fallback for standalone `source`.
if [ -z "${REPO_ROOT:-}" ]; then
  _profile_lib_source="${BASH_SOURCE[0]:-}"
  if [ -z "$_profile_lib_source" ]; then
    # Some shells leave BASH_SOURCE[0] empty for a directly-sourced file at
    # the top frame; BASH_SOURCE[1] is the includer's frame in that case.
    _profile_lib_source="${BASH_SOURCE[1]:-}"
  fi
  if [ -n "$_profile_lib_source" ]; then
    _PROFILE_LIB_DIR="$(cd "$(dirname "$_profile_lib_source")" && pwd)"
    REPO_ROOT="$(cd "$_PROFILE_LIB_DIR/../.." && pwd)"
  else
    # Last resort: walk up from cwd looking for profiles/neutral/profile.yaml.
    _profile_lib_dir="$(pwd)"
    while [ "$_profile_lib_dir" != "/" ]; do
      if [ -f "$_profile_lib_dir/profiles/neutral/profile.yaml" ]; then
        REPO_ROOT="$_profile_lib_dir"
        break
      fi
      _profile_lib_dir="$(dirname "$_profile_lib_dir")"
    done
    REPO_ROOT="${REPO_ROOT:-$(pwd)}"
  fi
  unset _profile_lib_source _profile_lib_dir
fi

# A caller that points ACTIVE_PROFILE_FILE somewhere itself (tests, tooling) owns
# the activation point completely: no main-checkout fallback is applied for it.
if [ -n "${ACTIVE_PROFILE_FILE:-}" ]; then
  ACTIVE_PROFILE_FILE_EXPLICIT=1
else
  ACTIVE_PROFILE_FILE="$REPO_ROOT/.active-profile"
  ACTIVE_PROFILE_FILE_EXPLICIT=0
fi
PROFILES_DIR="${PROFILES_DIR:-$REPO_ROOT/profiles}"

# _read_profile_file <file> — first non-empty, non-comment line, trimmed.
_read_profile_file() {
  grep -v '^[[:space:]]*#' "$1" 2>/dev/null \
    | grep -v '^[[:space:]]*$' | head -1 \
    | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//'
}

# _main_checkout_active_profile_file (ABS-257)
# Print the main checkout's .active-profile path when REPO_ROOT is a LINKED git
# worktree and that file exists; print nothing otherwise.
#
# Why: .active-profile is gitignored, so it exists only in the main checkout —
# but agent seats run with cwd = a per-ticket git worktree, where the file can
# never appear. Without this fallback every seat resolved to "neutral" and the
# project's profile (stack filter, capability providers) was silently ignored:
# a FastAPI project's seat was still handed SAW's Next.js patterns. The worktree
# and the main checkout are the same project, so they share the same profile.
_main_checkout_active_profile_file() {
  local common_dir root
  command -v git >/dev/null 2>&1 || return 0
  common_dir="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)" || return 0
  [ -n "$common_dir" ] || return 0
  # rev-parse may print a path relative to REPO_ROOT (the -C dir).
  case "$common_dir" in /*) ;; *) common_dir="$REPO_ROOT/$common_dir" ;; esac
  root="$(cd "$common_dir/.." 2>/dev/null && pwd)" || return 0
  [ -f "$root/.active-profile" ] && printf '%s\n' "$root/.active-profile"
  return 0
}

# get_requested_profile (ABS-269) — the profile the project ASKED for: precedence
# applied (env > file > main-checkout file > "neutral"), resolvability NOT validated.
# Callers that must fail CLOSED on a misconfiguration use this + profile_is_resolvable
# instead of get_active_profile, whose "neutral" degradation would hide the typo
# (see scripts/pattern-applicability.sh).
get_requested_profile() {
  local candidate="" main_file=""

  if [ -n "${ACTIVE_PROFILE:-}" ]; then
    candidate="$ACTIVE_PROFILE"
  elif [ -f "$ACTIVE_PROFILE_FILE" ]; then
    candidate="$(_read_profile_file "$ACTIVE_PROFILE_FILE")"
  elif [ "${ACTIVE_PROFILE_FILE_EXPLICIT:-0}" = "0" ]; then
    main_file="$(_main_checkout_active_profile_file)"
    [ -n "$main_file" ] && candidate="$(_read_profile_file "$main_file")"
  fi

  if [ -z "$candidate" ]; then
    candidate="neutral"
  fi

  echo "$candidate"
}

# profile_is_resolvable <name> — 0 when profiles/<name>/ exists.
profile_is_resolvable() {
  [ -n "${1:-}" ] && [ -d "$PROFILES_DIR/$1" ]
}

# get_active_profile — the requested profile, degraded to "neutral" (with a stderr
# warning) when it has no profiles/<name>/ directory (typo, deleted profile, …).
# Every caller therefore gets a name that is guaranteed to resolve.
get_active_profile() {
  local candidate
  candidate="$(get_requested_profile)"

  if ! profile_is_resolvable "$candidate"; then
    echo "profile.sh: WARN profile '$candidate' not found under $PROFILES_DIR; falling back to neutral" >&2
    candidate="neutral"
  fi

  echo "$candidate"
}

# _profile_capability_provider <profile.yaml path> <capability>
# Print the provider: value of the given capability block, or empty if the
# capability is absent from that file. Internal helper (not part of the
# public API — use get_capability_provider).
_profile_capability_provider() {
  local file="$1" capability="$2"
  [ -f "$file" ] || return 0
  # Print the capability block (from "  <capability>:" up to the next
  # top-level "  <key>:" line), then take the first provider: line in it.
  awk -v cap="  ${capability}:" '
    $0 == cap { in_block = 1; next }
    in_block && /^  [A-Za-z0-9_-]+:/ { in_block = 0 }
    in_block { print }
  ' "$file" | grep 'provider:' | head -1 \
    | sed 's/.*provider:[[:space:]]*//' | sed 's/[[:space:]]*#.*//' \
    | sed 's/[[:space:]]*$//'
}

# _profile_based_on <profile.yaml path>
# Print the based_on: value (bare profile name), or empty.
_profile_based_on() {
  local file="$1"
  [ -f "$file" ] || return 0
  grep '^based_on:' "$file" | head -1 \
    | sed 's/^based_on:[[:space:]]*//' | sed 's/[[:space:]]*#.*//' \
    | sed 's/[[:space:]]*$//'
}

# get_capability_provider <capability>
# Resolve the provider bound to <capability> in the active profile.
# Falls back to the profile's based_on target (typically "neutral") when the
# active profile doesn't declare the capability at all, then to "none".
get_capability_provider() {
  local capability="$1"
  local profile file provider based_on based_on_file

  profile="$(get_active_profile)"
  file="$PROFILES_DIR/$profile/profile.yaml"

  provider="$(_profile_capability_provider "$file" "$capability")"
  if [ -n "$provider" ]; then
    echo "$provider"
    return 0
  fi

  based_on="$(_profile_based_on "$file")"
  if [ -n "$based_on" ] && [ -d "$PROFILES_DIR/$based_on" ]; then
    based_on_file="$PROFILES_DIR/$based_on/profile.yaml"
    provider="$(_profile_capability_provider "$based_on_file" "$capability")"
    if [ -n "$provider" ]; then
      echo "$provider"
      return 0
    fi
  fi

  echo "none"
}
