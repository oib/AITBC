#!/bin/bash
# =============================================================================
# Test: Stack-Applicability-Guard (ABS-257)
# =============================================================================
# scripts/pattern-applicability.sh filters patterns_library/ against the ACTIVE
# profile's `stack:` list, so a foreign-stack project (FastAPI/Firestore) is
# never offered SAW's Next.js/Prisma/Clerk patterns (consumer feedback item 19).
#
# Covers:
#   AC1  taxonomy: every shipped pattern carries a `stack:` frontmatter tag
#   AC2  filtering by profile; `generic` patterns always survive the filter
#   AC3  FastAPI profile gets NO Next.js pattern recommendation
#   +    back-compat: a profile without a `stack:` key is unfiltered
#
# bash 3.2 / BSD safe. Run from repo root: bash tests/test-pattern-applicability.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/pattern-applicability.sh"

TEST_DIR=$(mktemp -d /tmp/pattern-applicability-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok() {
  echo -e "  ${GREEN}PASS${NC} $1"
  PASS=$((PASS + 1))
}
ko() {
  echo -e "  ${RED}FAIL${NC} $1"
  [ -n "${2:-}" ] && echo "        $2"
  FAIL=$((FAIL + 1))
}

assert_contains() {
  if echo "$1" | grep -q "$2"; then ok "$3"; else ko "$3" "expected to find: $2"; fi
}
assert_not_contains() {
  if echo "$1" | grep -q "$2"; then ko "$3" "must NOT be recommended: $2"; else ok "$3"; fi
}

# --- Fixture profiles --------------------------------------------------------
# PROFILES_DIR + ACTIVE_PROFILE are the documented override seams (scripts/lib/profile.sh),
# so the guard is exercised against real patterns_library/ content, no mocks.
FIXTURES="$TEST_DIR/profiles"

mkdir -p "$FIXTURES/fastapi-firestore"
cat >"$FIXTURES/fastapi-firestore/profile.yaml" <<'EOF'
profile: fastapi-firestore
description: The consumer's stack — Python/FastAPI + Firestore. No Next.js, no Prisma, no Clerk.
stack: [generic]
EOF

mkdir -p "$FIXTURES/nextjs-block-form"
cat >"$FIXTURES/nextjs-block-form/profile.yaml" <<'EOF'
profile: nextjs-block-form
description: Declares its stack in YAML block form (both list forms must parse).
stack:
  - nextjs
  - prisma
EOF

mkdir -p "$FIXTURES/empty-stack"
cat >"$FIXTURES/empty-stack/profile.yaml" <<'EOF'
profile: empty-stack
description: Explicit "my stack shares nothing with SAW's" — must filter down to generic, not fail open.
stack: []
EOF

mkdir -p "$FIXTURES/legacy-no-stack"
cat >"$FIXTURES/legacy-no-stack/profile.yaml" <<'EOF'
profile: legacy-no-stack
description: Pre-ABS-257 profile with no stack key — must stay unfiltered (back-compat).
EOF

run_guard() { # run_guard <profile> [args...]
  local profile="$1"
  shift
  PROFILES_DIR="$FIXTURES" ACTIVE_PROFILE="$profile" bash "$GUARD" "$@" 2>/dev/null
}

run_guard_stderr() { # run_guard_stderr <profile> [args...] — stderr only
  local profile="$1"
  shift
  PROFILES_DIR="$FIXTURES" ACTIVE_PROFILE="$profile" bash "$GUARD" "$@" \
    2>"$TEST_DIR/stderr.txt" >/dev/null
  cat "$TEST_DIR/stderr.txt"
}

echo -e "${CYAN}=== ABS-257: Stack-Applicability-Guard ===${NC}"

# --- AC1: taxonomy applied to every shipped pattern --------------------------
echo -e "\n${CYAN}AC1: every shipped pattern declares a stack: tag${NC}"
PATTERN_FILES="$TEST_DIR/pattern-files.txt"
find "$REPO_ROOT/patterns_library" -type f -name '*.md' | grep -v 'README.md' | LC_ALL=C sort >"$PATTERN_FILES"

UNTAGGED=""
TAGS_SEEN=""
while IFS= read -r f; do
  if head -3 "$f" | grep -q '^stack:'; then
    TAGS_SEEN="$TAGS_SEEN $(head -3 "$f" | grep '^stack:' |
      sed 's/^stack:[[:space:]]*\[//' | sed 's/\]//' | tr ',' ' ')"
  else
    UNTAGGED="$UNTAGGED $(basename "$f")"
  fi
done <"$PATTERN_FILES"

if [ -z "$UNTAGGED" ]; then
  ok "all patterns_library/**/*.md carry stack: frontmatter"
else
  ko "all patterns carry stack: frontmatter" "untagged:$UNTAGGED"
fi

KNOWN_TAGS=" generic nextjs react clerk prisma postgres-rls stripe github-actions playwright "
UNKNOWN=""
for tag in $(echo "$TAGS_SEEN" | tr ' ' '\n' | LC_ALL=C sort -u); do
  [ -n "$tag" ] || continue
  case "$KNOWN_TAGS" in *" $tag "*) ;; *) UNKNOWN="$UNKNOWN $tag" ;; esac
done
if [ -z "$UNKNOWN" ]; then
  ok "every tag used comes from the documented taxonomy"
else
  ko "tags stay inside the taxonomy" "unknown tag(s):$UNKNOWN"
fi

# --- AC3: FastAPI profile gets no Next.js pattern ----------------------------
echo -e "\n${CYAN}AC3: FastAPI/Firestore profile gets no wrong-stack recommendation${NC}"
FASTAPI_OUT="$(run_guard fastapi-firestore)"

assert_not_contains "$FASTAPI_OUT" "api/user-context-api.md" "Next.js/Clerk user-context API is NOT recommended"
assert_not_contains "$FASTAPI_OUT" "ui/authenticated-page.md" "Next.js authenticated page is NOT recommended"
assert_not_contains "$FASTAPI_OUT" "database/prisma-transaction.md" "Prisma transaction pattern is NOT recommended"
assert_not_contains "$FASTAPI_OUT" "database/rls-migration.md" "Postgres-RLS migration is NOT recommended"

if echo "$FASTAPI_OUT" | grep -qE 'patterns_library/(api|ui)/'; then
  ko "no Next.js-stack pattern (api/, ui/) survives the FastAPI filter" "$(echo "$FASTAPI_OUT" | grep -E '/(api|ui)/')"
else
  ok "no Next.js-stack pattern (api/, ui/) survives the FastAPI filter"
fi

# --- AC2: generic patterns always visible; filtering is per-profile ----------
echo -e "\n${CYAN}AC2: generic patterns always apply; filtering follows the profile${NC}"
assert_contains "$FASTAPI_OUT" "config/structured-logging.md" "generic pattern (structured logging) stays visible"
assert_contains "$FASTAPI_OUT" "security/input-sanitization.md" "generic pattern (input sanitization) stays visible"
assert_contains "$FASTAPI_OUT" "config/environment-config.md" "generic pattern (environment config) stays visible"

BLOCK_OUT="$(run_guard nextjs-block-form)"
assert_contains "$BLOCK_OUT" "api/user-context-api.md" "Next.js profile DOES get the Next.js API pattern (block-form stack: parses)"
assert_contains "$BLOCK_OUT" "config/structured-logging.md" "Next.js profile also keeps generic patterns"
assert_not_contains "$BLOCK_OUT" "testing/e2e-user-flow.md" "playwright-only pattern excluded when not in the profile's stack"

# --- Empty stack: [] is a declaration, not a missing key ---------------------
# `stack: []` means "my stack shares nothing with SAW's". Failing open here would hand a
# FastAPI project the entire Next.js catalogue — the exact bug this guard exists to prevent.
echo -e "\n${CYAN}stack: [] filters down to generic (does NOT fail open)${NC}"
EMPTY_OUT="$(run_guard empty-stack)"
assert_not_contains "$EMPTY_OUT" "api/user-context-api.md" "empty stack excludes Next.js patterns"
assert_contains "$EMPTY_OUT" "config/structured-logging.md" "empty stack keeps generic patterns"

# --- Back-compat: no stack: key => unfiltered --------------------------------
echo -e "\n${CYAN}Back-compat: a profile without stack: is unfiltered${NC}"
LEGACY_OUT="$(run_guard legacy-no-stack)"
ALL_COUNT=$(find "$REPO_ROOT/patterns_library" -type f -name '*.md' | grep -vc 'README.md')
LEGACY_COUNT=$(echo "$LEGACY_OUT" | grep -c 'patterns_library/')
if [ "$LEGACY_COUNT" -eq "$ALL_COUNT" ]; then
  ok "all $ALL_COUNT patterns applicable when the profile declares no stack"
else
  ko "unfiltered when no stack declared" "got $LEGACY_COUNT of $ALL_COUNT"
fi

# --- --all verdicts ----------------------------------------------------------
echo -e "\n${CYAN}--all prints APPLIES/EXCLUDED verdicts${NC}"
ALL_OUT="$(run_guard fastapi-firestore --all)"
assert_contains "$ALL_OUT" "EXCLUDED patterns_library/api/user-context-api.md" "excluded pattern reported with its verdict"
assert_contains "$ALL_OUT" "APPLIES  patterns_library/config/structured-logging.md" "applicable pattern reported with its verdict"

# --- AC3, REAL SEAT PATH: file-only activation, invoked from a git worktree ---
# The cases above activate the profile through the ACTIVE_PROFILE env seam, which
# PRODUCTION NEVER SETS. Real consumers activate with `scripts/profile.sh set`, which
# writes the gitignored .active-profile into the MAIN CHECKOUT — while agent seats run
# with cwd = a per-ticket git WORKTREE, where that file cannot exist. Filtering therefore
# has to survive a worktree with no env var and no local .active-profile, or the guard is
# a no-op in the only place it runs. This case builds that exact topology (own repo, own
# worktree — never the real .active-profile) and is the AC3 that actually protects a
# consumer.
echo -e "\n${CYAN}AC3 (real path): worktree seat, profile activated by file only${NC}"
SANDBOX="$TEST_DIR/sandbox"
MAIN="$SANDBOX/main"
mkdir -p "$MAIN/scripts/lib" "$MAIN/profiles/neutral" "$MAIN/profiles/fastapi-firestore" \
  "$MAIN/patterns_library/api" "$MAIN/patterns_library/config"

cp "$GUARD" "$MAIN/scripts/pattern-applicability.sh"
cp "$REPO_ROOT/scripts/lib/profile.sh" "$MAIN/scripts/lib/profile.sh"
printf 'profile: neutral\ndescription: no stack key — unfiltered.\n' \
  >"$MAIN/profiles/neutral/profile.yaml"
printf 'profile: fastapi-firestore\ndescription: the consumer stack.\nstack: [generic]\n' \
  >"$MAIN/profiles/fastapi-firestore/profile.yaml"
printf -- '---\nstack: [nextjs, clerk]\n---\n\n# Next.js API pattern\n' \
  >"$MAIN/patterns_library/api/user-context-api.md"
printf -- '---\nstack: [generic]\n---\n\n# Structured logging\n' \
  >"$MAIN/patterns_library/config/structured-logging.md"

(
  cd "$MAIN" || exit 1
  git init -q .
  git config user.email test@example.com
  git config user.name "ABS-257 test"
  git add -A
  git commit -qm "sandbox repo"
  # .active-profile is gitignored in the real repo: untracked here too, on purpose —
  # it must NOT be able to reach the worktree through git.
  printf 'fastapi-firestore\n' >.active-profile
  git worktree add -q "$SANDBOX/wt" -b seat-branch
) >/dev/null 2>&1

WT_GUARD="$SANDBOX/wt/scripts/pattern-applicability.sh"
if [ ! -f "$WT_GUARD" ]; then
  ko "sandbox worktree provisioned" "git worktree add failed"
else
  ok "sandbox worktree provisioned (main checkout holds .active-profile, worktree does not)"

  [ -f "$SANDBOX/wt/.active-profile" ] &&
    ko "worktree has no .active-profile (as in production)" "fixture leaked the file into the worktree"

  # env -u ACTIVE_PROFILE: exactly what a seat has — no env seam, cwd elsewhere.
  WT_OUT="$(cd / && env -u ACTIVE_PROFILE bash "$WT_GUARD" 2>/dev/null)"
  assert_not_contains "$WT_OUT" "api/user-context-api.md" \
    "worktree seat gets NO Next.js pattern (profile reached through the main checkout)"
  assert_contains "$WT_OUT" "config/structured-logging.md" \
    "worktree seat still gets the generic pattern"

  # Back-compat from a worktree: no .active-profile anywhere -> neutral -> unfiltered.
  rm -f "$MAIN/.active-profile"
  NOPROF_OUT="$(cd / && env -u ACTIVE_PROFILE bash "$WT_GUARD" 2>/dev/null)"
  assert_contains "$NOPROF_OUT" "api/user-context-api.md" \
    "no .active-profile anywhere -> unfiltered from the worktree (back-compat)"
fi

# =============================================================================
# ABS-269: an UNRESOLVABLE profile must fail CLOSED, not open
# =============================================================================
# Third instance of the fail-open family (after `stack: []` and the worktree
# resolution). A profile name that resolves to no directory under profiles/ used to
# degrade to `neutral` — which declares no `stack:` key — and thus served the FULL,
# unfiltered library. A misconfiguration must yield MAXIMUM protection.
echo -e "\n${CYAN}ABS-269: unresolvable profile fails CLOSED (generic-only)${NC}"

# AC1: declared-but-missing profile dir -> generic subset, NOT the 11 foreign patterns.
GHOST_OUT="$(run_guard fastapi)" # profiles/fastapi/ does not exist in $FIXTURES
assert_not_contains "$GHOST_OUT" "api/user-context-api.md" "unresolvable profile gets NO Next.js/Clerk API pattern"
assert_not_contains "$GHOST_OUT" "database/prisma-transaction.md" "unresolvable profile gets NO Prisma pattern"
assert_not_contains "$GHOST_OUT" "ui/authenticated-page.md" "unresolvable profile gets NO Next.js UI pattern"
if echo "$GHOST_OUT" | grep -qE 'patterns_library/(api|ui)/'; then
  ko "no stack-specific pattern survives an unresolvable profile" "$(echo "$GHOST_OUT" | grep -E '/(api|ui)/')"
else
  ok "no stack-specific pattern survives an unresolvable profile"
fi
assert_contains "$GHOST_OUT" "config/structured-logging.md" "generic patterns still served (guard degrades, does not blank out)"

# AC3: the diagnosis stays loud — name + searched path + the fail-closed behavior.
GHOST_ERR="$(run_guard_stderr fastapi)"
assert_contains "$GHOST_ERR" "fastapi" "WARN names the unresolvable profile"
assert_contains "$GHOST_ERR" "$FIXTURES" "WARN names the searched profiles path"
assert_contains "$GHOST_ERR" "FAIL-CLOSED" "WARN names the chosen fail-closed behavior"

# #PATH_DECISION: fail-closed WITHOUT a non-zero exit. pattern-discovery consumes stdout;
# a hard failure would turn a misconfiguration into a broken seat.
if PROFILES_DIR="$FIXTURES" ACTIVE_PROFILE=fastapi bash "$GUARD" >/dev/null 2>&1; then
  ok "guard still exits 0 (degrade, do not break the consuming seat)"
else
  ko "guard still exits 0" "unresolvable profile made the guard exit non-zero"
fi

# AC2 regression: the deliberate asymmetry is UNCHANGED by the fail-closed change.
echo -e "\n${CYAN}AC2: the deliberate asymmetry survives (absent key != unresolvable profile)${NC}"
LEGACY_OUT2="$(run_guard legacy-no-stack)"
assert_contains "$LEGACY_OUT2" "api/user-context-api.md" "stack: key ABSENT -> still unfiltered (back-compat)"
EMPTY_OUT2="$(run_guard empty-stack)"
assert_not_contains "$EMPTY_OUT2" "api/user-context-api.md" "stack: [] -> still generic-only"

# AC1, REAL PATH: the PO's actual repro — .active-profile in the main checkout names a
# profile whose directory does not exist, seat runs from the worktree, no env seam.
echo -e "\n${CYAN}ABS-269 (real path): worktree seat, .active-profile names a missing profile${NC}"
if [ -f "$WT_GUARD" ]; then
  printf 'fastapi\n' >"$MAIN/.active-profile" # profiles/fastapi/ was never created
  GHOST_WT_OUT="$(cd / && env -u ACTIVE_PROFILE bash "$WT_GUARD" 2>/dev/null)"
  assert_not_contains "$GHOST_WT_OUT" "api/user-context-api.md" \
    "worktree seat with an unresolvable profile gets NO Next.js pattern"
  assert_contains "$GHOST_WT_OUT" "config/structured-logging.md" \
    "worktree seat with an unresolvable profile still gets generic patterns"
  rm -f "$MAIN/.active-profile"
fi

# AC4: the OTHER capability provider must not break. get_capability_provider keeps the
# neutral degradation (a missing profile dir must never hard-break the evolver hook), so
# an unresolvable profile resolves EXACTLY as neutral does.
echo -e "\n${CYAN}AC4: capability providers do not break on a missing profile dir${NC}"
NEUTRAL_PROVIDER="$(ACTIVE_PROFILE=neutral bash -c 'source "$0"; get_capability_provider evolution' "$REPO_ROOT/scripts/lib/profile.sh" 2>/dev/null)"
GHOST_PROVIDER="$(ACTIVE_PROFILE=does-not-exist bash -c 'source "$0"; get_capability_provider evolution' "$REPO_ROOT/scripts/lib/profile.sh" 2>/dev/null)"
if [ -n "$GHOST_PROVIDER" ] && [ "$GHOST_PROVIDER" = "$NEUTRAL_PROVIDER" ]; then
  ok "get_capability_provider on an unresolvable profile resolves as neutral ('$GHOST_PROVIDER')"
else
  ko "get_capability_provider degrades to neutral" "neutral='$NEUTRAL_PROVIDER' ghost='$GHOST_PROVIDER'"
fi

if ACTIVE_PROFILE=does-not-exist bash "$REPO_ROOT/scripts/hooks/evolver-lifecycle.sh" >/dev/null 2>&1; then
  ok "scripts/hooks/evolver-lifecycle.sh exits 0 on an unresolvable profile (no hard break)"
else
  ko "evolver-lifecycle.sh survives an unresolvable profile" "exit=$?"
fi

# --- Summary -----------------------------------------------------------------
echo ""
echo "============================================"
echo -e "Passed: ${GREEN}${PASS}${NC}   Failed: ${RED}${FAIL}${NC}"
echo "============================================"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "${GREEN}ABS-257: Stack-Applicability-Guard OK${NC}"
