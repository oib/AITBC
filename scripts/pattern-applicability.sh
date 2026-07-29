#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Stack-Applicability-Guard (ABS-257) — which patterns apply to THIS stack?
# =============================================================================
# Consumers on a foreign stack (e.g. FastAPI/Firestore) were offered SAW's
# Next.js/Prisma/Clerk patterns — noise, and occasionally wrong-stack code.
# This script is the ONE mechanical filter behind that guard; the
# pattern-discovery skill calls it and recommends only from its output.
#
#   scripts/pattern-applicability.sh          list applicable pattern paths
#   scripts/pattern-applicability.sh --all    list every pattern with a verdict
#
# Rule (see patterns_library/README.md "Stack applicability"):
#   * The ACTIVE profile may declare a `stack:` list (profiles/<name>/profile.yaml).
#   * Each pattern may declare a `stack:` list in its markdown frontmatter.
#   * NO `stack:` key in the profile -> filtering OFF, everything applies (back-compat).
#   * `stack:` key present (INCLUDING the empty `stack: []`) -> filtering ON; a pattern
#     is APPLICABLE when
#       - it is tagged `generic`, or is untagged, OR
#       - its tags intersect the profile's stack.
#   * Profile name declared but NOT resolvable under profiles/ -> FAIL CLOSED (ABS-269):
#     filtering ON with an empty stack (generic-only) + a loud WARN. A misconfiguration
#     must degrade to maximum protection, never to "no protection".
#   Untagged patterns are treated as `generic` (a project's own patterns stay
#   visible until it opts into tagging). The guard hides noise; it never hides
#   a pattern that has not been classified.
#
# No YAML parser dependency: grep/sed/awk only, bash 3.2 / BSD safe (macOS).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib/profile.sh
source "$SCRIPT_DIR/lib/profile.sh"

PATTERNS_DIR="$REPO_ROOT/patterns_library"

usage() {
  cat <<'EOF'
scripts/pattern-applicability.sh — filter patterns_library/ by the active profile's stack (ABS-257)

Usage:
  scripts/pattern-applicability.sh          Print pattern paths applicable to the active profile.
  scripts/pattern-applicability.sh --all    Print every pattern as "<verdict> <path> [tags]".
  scripts/pattern-applicability.sh --help

A profile opts in by declaring a top-level `stack:` list in profiles/<name>/profile.yaml.
Profiles without a `stack:` list are unfiltered (every pattern applies).
Patterns declare their stack in markdown frontmatter; `generic` and untagged always apply.
EOF
}

# read_stack_list <file>
# Print the values of the `stack:` key as a space-separated list, accepting both
#   stack: [nextjs, prisma]      (inline)
#   stack:                       (block)
#     - nextjs
# Reads only the top of a pattern file's frontmatter / a profile's top level:
# indented `stack:` keys nested inside other blocks are ignored on purpose, and a
# pattern file is scanned only up to the closing `---` of its frontmatter (so a
# `stack:` line inside the prose or a fenced code block can never be picked up).
read_stack_list() {
  local file="$1"
  [ -f "$file" ] || return 0
  awk '
    # bound the scan to the frontmatter block when the file has one
    NR == 1 && /^---[[:space:]]*$/ { fm = 1; next }
    fm && /^---[[:space:]]*$/ { exit }
    # inline form: stack: [a, b, c]
    /^stack:[[:space:]]*\[/ {
      line = $0
      sub(/^stack:[[:space:]]*\[/, "", line)
      sub(/\].*/, "", line)
      gsub(/[,"'"'"']/, " ", line)
      print line
      exit
    }
    # block form: stack:  followed by "  - value" items
    /^stack:[[:space:]]*$/ { in_block = 1; next }
    in_block && /^[[:space:]]*-[[:space:]]*/ {
      line = $0
      sub(/^[[:space:]]*-[[:space:]]*/, "", line)
      sub(/[[:space:]]*#.*/, "", line)
      gsub(/["'"'"']/, "", line)
      printf "%s ", line
      next
    }
    in_block { exit }
  ' "$file" | tr '\n' ' ' | awk '{ $1 = $1; print }' # squeeze + trim whitespace
}

# profile_declares_stack <profile.yaml> — 0 when a top-level `stack:` key EXISTS.
# Key ABSENT => filtering off (back-compat). Key present but EMPTY (`stack: []`)
# => filtering ON with an empty stack, i.e. only `generic` patterns apply. The
# empty list is an explicit "my stack shares nothing with SAW's" — failing open
# there would hand a FastAPI project the whole Next.js catalogue.
profile_declares_stack() {
  local file="$1"
  [ -f "$file" ] || return 1
  grep -q '^stack:' "$file"
}

# pattern_applies <pattern tags> <profile stack>
# Exit 0 when the pattern applies. Untagged / generic patterns always apply.
# Only called when the profile declares a stack (filtering is on).
pattern_applies() {
  local pattern_tags="$1" stack="$2" tag want

  [ -n "$pattern_tags" ] || return 0 # untagged pattern -> treated as generic

  for tag in $pattern_tags; do
    [ "$tag" = "generic" ] && return 0
    for want in $stack; do
      [ "$tag" = "$want" ] && return 0
    done
  done
  return 1
}

main() {
  local mode="list"
  case "${1:-}" in
    --all) mode="all" ;;
    -h | --help | help) usage; exit 0 ;;
    "") ;;
    *)
      echo "pattern-applicability.sh: unknown argument '$1'" >&2
      usage >&2
      exit 1
      ;;
  esac

  local stack pfile filtering file tags rel profile
  filtering=0
  stack=""
  profile="$(get_requested_profile)"

  if ! profile_is_resolvable "$profile"; then
    # ABS-269: a DECLARED but unresolvable profile is a misconfiguration, not an
    # opt-out. get_active_profile would degrade it to `neutral`, which declares no
    # `stack:` key and would hand this project the ENTIRE library — every wrong-stack
    # pattern included. Fail CLOSED instead: filter as if `stack: []` (generic-only).
    echo "pattern-applicability.sh: WARN profile '$profile' not found under $PROFILES_DIR;" \
      "FAIL-CLOSED: serving generic patterns only (fix .active-profile or run scripts/profile.sh set <name>)" >&2
    filtering=1
  else
    pfile="$PROFILES_DIR/$profile/profile.yaml"
    if profile_declares_stack "$pfile"; then
      filtering=1
      stack="$(read_stack_list "$pfile")"
    fi
  fi

  # -type f, sorted, README excluded: the index is not a pattern.
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    case "$file" in */README.md) continue ;; esac
    tags="$(read_stack_list "$file")"
    rel="${file#"$REPO_ROOT"/}"
    if [ "$filtering" -eq 0 ] || pattern_applies "$tags" "$stack"; then
      if [ "$mode" = "all" ]; then
        printf 'APPLIES  %s [%s]\n' "$rel" "${tags:-untagged}"
      else
        printf '%s\n' "$rel"
      fi
    elif [ "$mode" = "all" ]; then
      printf 'EXCLUDED %s [%s]\n' "$rel" "${tags:-untagged}"
    fi
  done < <(find "$PATTERNS_DIR" -type f -name '*.md' | LC_ALL=C sort)
}

main "$@"
