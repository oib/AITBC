#!/usr/bin/env bash
# =============================================================================
# Test: structured release notes generator + jira-version.sh --description-file
# =============================================================================
# ABS-226. Fully offline — no live Jira/Confluence, no creds. Two subjects:
#
#   1) scripts/release-notes.sh render (page/description): golden-file diff
#      against tests/fixtures/release-notes/*.golden.* built from a FROZEN
#      changelog fixture. Covers AC2 (deterministic page+description from a
#      changelog entry), AC3 (v2.24.1 page format: info panel, ticket-linked
#      change table, category chips, operations notes), AC5 (governor-only
#      patch -> summary-only stub page).
#
#   2) scripts/jira-version.sh release --description-file: a curl shim captures
#      the PUT body; asserts the description is stamped atomically with
#      released:true, and that the no-flag path omits the description (AC1).
#
# Run from repo root:  bash tests/tooling/test-release-notes.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RN="$REPO_ROOT/scripts/release-notes.sh"
JV="$REPO_ROOT/scripts/jira-version.sh"
FIX_DIR="$SCRIPT_DIR/fixtures/release-notes"
CHANGELOG="$FIX_DIR/changelog-fixture.yml"
JIRA_BASE="https://lovebytecodes.atlassian.net"
PAGE_URL="$JIRA_BASE/wiki/x/AgAcOQ"

TEST_DIR=$(mktemp -d /tmp/release-notes-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected: '$expected', got: '$actual')"; FAIL=$((FAIL + 1))
    fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! printf '%s' "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1))
    fi
}
assert_nonzero_exit() {
    local actual="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -ne 0 ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected non-zero exit, got 0)"; FAIL=$((FAIL + 1))
    fi
}
# assert_golden <label> <golden-file> -- run a release-notes render and diff its
# stdout against the golden file.
assert_golden() {
    local label="$1" golden="$2"; shift 2
    local got="$TEST_DIR/golden-out"
    # Write directly to a file (command substitution would strip trailing
    # newlines and make the diff falsely fail on the final line).
    bash "$RN" "$@" > "$got" 2>/dev/null
    TOTAL=$((TOTAL + 1))
    if diff -u "$golden" "$got" >/dev/null 2>&1; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (output diverged from $(basename "$golden"))"
        diff -u "$golden" "$got" | head -20 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

# =============================================================================
echo -e "\n${CYAN}=== Test 0: syntax + fixtures present ===${NC}\n"
# =============================================================================
bash -n "$RN" >/dev/null 2>&1; assert_eq "$?" "0" "release-notes.sh has valid bash syntax"
bash -n "$JV" >/dev/null 2>&1; assert_eq "$?" "0" "jira-version.sh has valid bash syntax"
[ -f "$CHANGELOG" ] && echo -e "  ${GREEN}PASS${NC} frozen changelog fixture present" && PASS=$((PASS+1)) || { echo -e "  ${RED}FAIL${NC} changelog fixture missing"; FAIL=$((FAIL+1)); }
TOTAL=$((TOTAL+1))

# =============================================================================
echo -e "\n${CYAN}=== Test 1: golden page + description (AC2/AC3/AC5) ===${NC}\n"
# =============================================================================
assert_golden "page 9.9.0 matches golden (panel + table + chips + ops notes)" \
    "$FIX_DIR/9.9.0.page.golden.html" \
    page 9.9.0 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE"
assert_golden "description 9.9.0 matches golden (link line 1 + summary)" \
    "$FIX_DIR/9.9.0.description.golden.txt" \
    description 9.9.0 --changelog "$CHANGELOG" --page-url "$PAGE_URL"
assert_golden "page 9.9.1 matches golden (governor-only stub, summary-only)" \
    "$FIX_DIR/9.9.1.page.golden.html" \
    page 9.9.1 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE"
assert_golden "description 9.9.1 matches golden (summary-only, no link)" \
    "$FIX_DIR/9.9.1.description.golden.txt" \
    description 9.9.1 --changelog "$CHANGELOG"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: format details (AC3) ===${NC}\n"
# =============================================================================
page="$(bash "$RN" page 9.9.0 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE" 2>/dev/null)"
assert_contains "$page" 'ac:name="info"'   "page opens with an info panel macro"
assert_contains "$page" 'ac:name="status"' "categories render as status-macro chips"
assert_contains "$page" "$JIRA_BASE/browse/ABS-226" "descriptions carry ticket hyperlinks"
assert_contains "$page" "Operations notes"  "page has an operations-notes section"
assert_contains "$page" "&gt;"              "raw text is HTML-escaped in the storage body"

stub="$(bash "$RN" page 9.9.1 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE" 2>/dev/null)"
assert_not_contains "$stub" "<table"        "stub page has no change table (AC5)"
assert_contains "$stub" "Governor-only patch release" "stub page states it is a governor-only patch"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: determinism + no-link + errors ===${NC}\n"
# =============================================================================
a="$(bash "$RN" page 9.9.0 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE" 2>/dev/null)"
b="$(bash "$RN" page 9.9.0 --changelog "$CHANGELOG" --jira-base "$JIRA_BASE" 2>/dev/null)"
assert_eq "$a" "$b" "render is deterministic (same input -> byte-identical output)"

# env -u JIRA_SITE: the generator defaults --jira-base to $JIRA_SITE, so a real
# Jira-connected environment would otherwise linkify even without the flag.
nolink="$(env -u JIRA_SITE bash "$RN" page 9.9.0 --changelog "$CHANGELOG" 2>/dev/null)"
assert_not_contains "$nolink" "<a href=" "without --jira-base, ticket refs stay plain text"
assert_contains "$nolink" "ABS-226" "ticket tokens still present as plain text without a base"

ec=0; bash "$RN" page 0.0.0 --changelog "$CHANGELOG" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "unknown version fails cleanly"
ec=0; bash "$RN" bogus 9.9.0 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "unknown command fails cleanly"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: jira-version.sh release --description-file (AC1) ===${NC}\n"
# =============================================================================
export JIRA_SITE="https://dummy.atlassian.net"
export JIRA_EMAIL="tester@example.com"
export JIRA_API_TOKEN="DUMMYTOKEN-LEAK-CANARY-abc123"
export JIRA_PROJECT_KEY="ABS"
export JIRA_CURL="$SCRIPT_DIR/fixtures/jira-version-curl-shim.sh"
[ -x "$JIRA_CURL" ] || chmod +x "$JIRA_CURL" 2>/dev/null

# (a) with --description-file: PUT body has released:true AND the description.
descf="$TEST_DIR/desc.txt"
printf 'Release notes: %s\n\nA one-paragraph summary.' "$PAGE_URL" > "$descf"
CAP="$TEST_DIR/put-with-desc.json"; : > "$CAP"
out="$(JV_CAPTURE="$CAP" bash "$JV" release 9.9.0 --description-file "$descf" 2>&1)"
assert_eq "$out" "released version '9.9.0' in ABS" "release --description-file prints the success line"
TOTAL=$((TOTAL + 1))
if python3 - "$CAP" "$descf" <<'PY'
import sys, json
cap, descf = sys.argv[1], sys.argv[2]
want = open(descf).read()
for line in open(cap):
    line = line.strip()
    if not line: continue
    obj = json.loads(line)
    if obj.get("released") is True and obj.get("description") == want and "releaseDate" in obj:
        sys.exit(0)
sys.exit(1)
PY
then
    echo -e "  ${GREEN}PASS${NC} PUT body stamps released:true + description atomically (AC1)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} PUT body missing released/description"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$CAP"
fi

# (b) without the flag: released:true, NO description key (unchanged behaviour).
CAP2="$TEST_DIR/put-no-desc.json"; : > "$CAP2"
out="$(JV_CAPTURE="$CAP2" bash "$JV" release 9.9.0 2>&1)"
assert_eq "$out" "released version '9.9.0' in ABS" "plain release still prints the success line"
TOTAL=$((TOTAL + 1))
if python3 - "$CAP2" <<'PY'
import sys, json
for line in open(sys.argv[1]):
    line = line.strip()
    if not line: continue
    obj = json.loads(line)
    if obj.get("released") is True and "description" not in obj:
        sys.exit(0)
sys.exit(1)
PY
then
    echo -e "  ${GREEN}PASS${NC} no-flag release omits description (unchanged behaviour, AC1)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} no-flag release leaked a description key"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$CAP2"
fi

# (c) missing description file fails cleanly.
ec=0; bash "$JV" release 9.9.0 --description-file "$TEST_DIR/nope.txt" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "release --description-file with a missing file fails cleanly"

# (d) credential never leaks into output.
leak="$(JV_CAPTURE="$TEST_DIR/leak-cap.json" bash "$JV" release 9.9.0 --description-file "$descf" 2>&1)"
assert_not_contains "$leak" "DUMMYTOKEN-LEAK-CANARY-abc123" "raw token never appears in release output"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
# =============================================================================
echo -e "  Total:   $TOTAL"
echo -e "  ${GREEN}Passed:  $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed:  $FAIL${NC}"
    exit 1
else
    echo -e "  Failed:  0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
