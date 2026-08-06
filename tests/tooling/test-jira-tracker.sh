#!/bin/bash
# =============================================================================
# Test: Jira Cloud Task-Tracking Adapter (ABS-64)
# =============================================================================
# Conformance test for scripts/jira-tracker.sh. Two tiers:
#
#   OFFLINE CONTRACT TIER (default; runs in CI, no network, no real creds):
#     A curl shim on PATH ($JIRA_CURL) serves canned Jira REST v3 responses.
#     Exercises all nine ops' argument parsing and output shapes, and asserts
#     CLI parity with scripts/mock-tracker.sh (same usage errors, same output
#     field layout). Also runs a credential-leak scan: a known dummy token must
#     never appear in any output/log.
#
#   LIVE SMOKE TIER (only when JIRA_API_TOKEN is set; skipped otherwise, so CI
#     skips it): a minimal get + search against the fenced project.
#
# Run from repo root:  bash tests/test-jira-tracker.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACKER="$REPO_ROOT/scripts/jira-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/jira-tracker-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

# --- Dummy environment (no real creds; offline tier must pass with these) ----
DUMMY_TOKEN="DUMMYTOKEN-LEAK-CANARY-abc123"
export JIRA_SITE="https://dummy.atlassian.net"
export JIRA_EMAIL="tester@example.com"
export JIRA_API_TOKEN="$DUMMY_TOKEN"
export JIRA_PROJECT_KEY="ABS"
export JIRA_JQL_FILTER=""
export JIRA_TRACKER_STATE="$TEST_DIR/.jira-events-state"
# Hermetic status-alias baseline: neutralize any ambient JIRA_STATUS_ALIASES from
# the developer's real Jira deployment (e.g. "Ready for Development=Selected for
# Development"). The suite assumes the neutral default (no alias) and sets aliases
# explicitly per-case in Test 9d; without this reset the deployment alias leaks in
# and breaks the transition (Test 7) and neutral-default (Test 9d) assertions.
export JIRA_STATUS_ALIASES=""

# The adapter calls curl via $JIRA_CURL; point it at our canned-response shim.
export JIRA_CURL="$SCRIPT_DIR/fixtures/jira-curl-shim.sh"
# Shim state dir (lets us fake create->get and status changes for events).
export JIRA_SHIM_DIR="$TEST_DIR/shim"
mkdir -p "$JIRA_SHIM_DIR"

MOCK_TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"

tracker() {
    bash "$TRACKER" "$@"
}
mocktracker() {
    bash "$MOCK_TRACKER" "$@"
}

PASS=0
FAIL=0
TOTAL=0
SKIP=0

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

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
    if grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output (first 20 lines):${NC}"
        head -20 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect to find: $expected)"; FAIL=$((FAIL + 1))
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

assert_exit_code() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"; FAIL=$((FAIL + 1))
    fi
}

assert_empty() {
    local output="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ -z "$output" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected empty output, got: $output)"; FAIL=$((FAIL + 1))
    fi
}

# assert_parity <args...> — run the SAME argv through both jira-tracker.sh and
# mock-tracker.sh, assert they produce the identical error message (stderr) for
# an argument-parsing failure. Both must fail; both messages must match.
assert_parity_error() {
    local label="$1"; shift
    local jout mout jrc mrc
    jout="$(bash "$TRACKER" "$@" 2>&1)"; jrc=$?
    mout="$(bash "$MOCK_TRACKER" "$@" 2>&1)"; mrc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$jrc" -ne 0 ] && [ "$mrc" -ne 0 ] && [ "$jout" = "$mout" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"
        echo -e "  ${YELLOW}  jira (rc=$jrc): $jout${NC}"
        echo -e "  ${YELLOW}  mock (rc=$mrc): $mout${NC}"
        FAIL=$((FAIL + 1))
    fi
}

# =============================================================================
echo -e "\n${CYAN}=== Test 0: syntax, help, shim present ===${NC}\n"
# =============================================================================
bash -n "$TRACKER" >/dev/null 2>&1
assert_exit_code $? 0 "jira-tracker.sh has valid bash syntax"

[ -x "$JIRA_CURL" ] || chmod +x "$JIRA_CURL" 2>/dev/null
TOTAL=$((TOTAL + 1))
if [ -f "$JIRA_CURL" ]; then
    echo -e "  ${GREEN}PASS${NC} curl shim fixture present"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} curl shim fixture missing: $JIRA_CURL"; FAIL=$((FAIL + 1))
fi

help_output=$(tracker help)
assert_contains "$help_output" "transition" "help lists transition"
assert_contains "$help_output" "events" "help lists events"
assert_contains "$help_output" "get_ticket" "help maps to canonical op names"

# assert_msg <label> <expected-stderr> -- run jira-tracker.sh with the trailing
# args and assert it fails with exactly <expected-stderr>. Used for the
# ticket-scoped semantic validations the mock reaches only AFTER an existence
# check (see the ordering note below), which the offline tier can't reproduce
# for the network-backed adapter.
assert_msg() {
    local label="$1" expected="$2"; shift 2
    local out rc
    out="$(bash "$TRACKER" "$@" 2>&1)"; rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" -ne 0 ] && [ "$out" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (rc=$rc)"
        echo -e "  ${YELLOW}  expected: $expected${NC}"
        echo -e "  ${YELLOW}  got:      $out${NC}"
        FAIL=$((FAIL + 1))
    fi
}

# =============================================================================
echo -e "\n${CYAN}=== Test 1a: CLI parity — errors byte-identical to mock-tracker.sh ===${NC}\n"
# =============================================================================
# These failures fire in argument parsing BEFORE any ticket lookup or HTTP call
# in BOTH adapters (arity checks in main(); flag-value and standalone create/
# search validations). They must be byte-identical to mock-tracker.sh.
# Unknown command: both print a usage banner (which differs per adapter) then an
# identical ERROR line. Assert the ERROR line matches byte-for-byte.
unk_j="$(bash "$TRACKER" boguscmd 2>&1 | grep '^ERROR:')"
unk_m="$(bash "$MOCK_TRACKER" boguscmd 2>&1 | grep '^ERROR:')"
assert_eq "$unk_j" "$unk_m" "unknown-command ERROR line parity"
assert_eq "$unk_j" "ERROR: unknown command: boguscmd" "unknown-command message text"

assert_parity_error "create missing --type parity"     create --title x
assert_parity_error "create invalid type parity"       create --type nonsense --title x
assert_parity_error "create invalid role parity"       create --type ticket --title x --role qas
assert_parity_error "create invalid lane parity"       create --type ticket --title x --lane bogus
assert_parity_error "create --lane no value parity"    create --type ticket --title x --lane
assert_parity_error "search --lane no value parity"    search --lane
assert_parity_error "create --role no value parity"    create --type ticket --title x --role
assert_parity_error "create --title no value parity"   create --type ticket --title
assert_parity_error "search --status no value parity"  search --status
assert_parity_error "search --text no value parity"    search --text
assert_parity_error "search --label no value parity"   search --label
assert_parity_error "search unknown arg parity"        search --bogus x
assert_parity_error "update arity parity"              update ABS-1 title
assert_parity_error "link arity parity"                link ABS-1 ABS-2
assert_parity_error "children arity parity"            children
assert_parity_error "events arity parity"              events extra
assert_parity_error "get arity parity"                 get

# Usage banner: names/descriptions legitimately differ per adapter, but the
# SHAPE (a Usage: line + the canonical-op layout + exit non-zero) is parity.
no_arg_out="$(bash "$TRACKER" 2>&1)"; no_arg_rc=$?
assert_nonzero_exit "$no_arg_rc" "no-args exits non-zero (usage), like the mock"
assert_contains "$no_arg_out" "Usage: scripts/jira-tracker.sh <command> [args]" "no-args prints a Usage: banner"
assert_contains "$no_arg_out" "get_ticket" "usage lists the canonical op mapping (shape parity)"

# =============================================================================
echo -e "\n${CYAN}=== Test 1b: ticket-scoped semantic validations (jira's own messages) ===${NC}\n"
# =============================================================================
# ORDERING NOTE: mock-tracker.sh validates ticket EXISTENCE first (a local file
# stat), so for a nonexistent id it emits "ticket not found" before reaching the
# field/kind/type validation below. jira-tracker.sh's existence check is a
# network call, so offline it reaches these local validations first and emits
# the SAME message the mock emits once the ticket exists. We assert jira's exact
# message text here (the field/flag error the mock also produces post-existence).
assert_msg "update status refused" \
    "ERROR: update: status changes must go through 'transition' (validated + reasoned)" \
    update ABS-1 status Done
assert_msg "update unknown field" \
    "ERROR: update: unknown field 'bogus' (title|type|parent|depends_on|links|lane|flags|labels|ac_blocking|priority|iteration_cap|body|body-file)" \
    update ABS-1 bogus v
# ABS-319: lane is a first-class updatable field; invalid values are rejected
# with the mock's exact message (existence-check ordering differs, so assert_msg).
assert_msg "update invalid lane" \
    "ERROR: update: lane must be 'normal' or 'fastlane'" \
    update ABS-1 lane bogus
assert_msg "update body-file missing path (ABS-252)" \
    "ERROR: update: body-file not found: /nonexistent/body.md" \
    update ABS-1 body-file /nonexistent/body.md
assert_msg "comment invalid kind" \
    "ERROR: comment: invalid kind 'bogus'" \
    comment ABS-1 --kind bogus --actor x --body y
assert_msg "comment missing flags" \
    "ERROR: comment: --kind, --actor and --body (or --body-file) are required" \
    comment ABS-1 --kind understanding
assert_msg "transition missing flags" \
    "ERROR: transition: --actor and --reason (or --reason-file) are required" \
    transition ABS-1 "In Progress"
assert_msg "transition --expect-from requires a value (ABS-198)" \
    "ERROR: transition: --expect-from requires a value" \
    transition ABS-1 "In Progress" --actor x --reason y --expect-from
assert_msg "link invalid type" \
    "ERROR: link: invalid link type 'friend-of' (parent-child|depends-on|origin-review|pr|relates)" \
    link ABS-1 ABS-2 friend-of

# The field/flag error messages jira emits above are the SAME strings mock emits
# (verified by grepping the mock source), confirming message-text parity even
# though the existence-check ordering differs.
TOTAL=$((TOTAL + 1))
if grep -qF "update: unknown field '\$field' (title|type|parent|depends_on|links|lane|flags|labels|ac_blocking|priority|iteration_cap|body|body-file)" "$MOCK_TRACKER" \
   && grep -qF "update: body-file not found: \$value" "$MOCK_TRACKER" \
   && grep -qF "comment: invalid kind '\$kind'" "$MOCK_TRACKER" \
   && grep -qF "link: invalid link type '\$ltype' (parent-child|depends-on|origin-review|pr|relates)" "$MOCK_TRACKER"; then
    echo -e "  ${GREEN}PASS${NC} jira semantic messages are the mock's own strings (text parity)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} jira semantic messages diverge from mock source strings"; FAIL=$((FAIL + 1))
fi

# ABS-198 (Measure 3): both adapters implement transition --expect-from with the
# identical NOOP marker text, so the compare-and-set guard is portable.
TOTAL=$((TOTAL + 1))
if grep -qF -- '--expect-from' "$MOCK_TRACKER" \
   && grep -qF -- '--expect-from' "$TRACKER" \
   && grep -qF 'NOOP compare-and-set expect-from=' "$MOCK_TRACKER" \
   && grep -qF 'NOOP compare-and-set expect-from=' "$TRACKER"; then
    echo -e "  ${GREEN}PASS${NC} compare-and-set --expect-from present in both adapters (ABS-198)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} compare-and-set --expect-from missing from an adapter"; FAIL=$((FAIL + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 2: create — prints the Jira-assigned id ===${NC}\n"
# =============================================================================
EPIC=$(tracker create --type epic --title "Conformance demo epic")
assert_eq "$EPIC" "ABS-101" "create returns the Jira-assigned key"

T1=$(tracker create --type ticket --title "First child ticket" --parent "$EPIC")
assert_eq "$T1" "ABS-102" "second create returns next key"

WITHROLE=$(tracker create --type ticket --title "Backend role" --role be-developer)
assert_eq "$WITHROLE" "ABS-103" "create --role returns a key"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: get — canonical frontmatter+body+comments dump ===${NC}\n"
# =============================================================================
out=$(tracker get ABS-101)
assert_contains "$out" "---" "get output is a frontmatter block"
assert_contains "$out" "id: ABS-101" "get returns frontmatter id"
assert_contains "$out" "type: epic" "get maps Jira Epic -> type epic"
assert_contains "$out" "status: Backlog" "get returns status"
assert_contains "$out" "title: Conformance demo epic" "get returns title"
assert_contains "$out" "## Comments" "get dump has a Comments section"
# Structured comment header parity: "### <at> | kind: <k> | actor: <a>"
assert_contains "$out" "kind: decision | actor: orchestrator" "get reconstructs the mock's kind/actor header line"

# role: line only present when the issue carries a role: label
outrole=$(tracker get ABS-103)
assert_contains "$outrole" "role: be-developer" "get surfaces role from a role: label"
assert_not_contains "$out" "role:" "get omits role: line when no role label present"

# ABS-319: lane is a first-class field — get ALWAYS emits it, defaulting to
# normal for a fixture with no lane: label (parity with the mock default).
assert_contains "$out" "lane: normal" "get emits lane: normal by default (ABS-319)"

# ABS-182: comment pagination — a ticket whose comments span TWO Jira API pages
# must have its FULL list returned. A single-page fetch would drop the newest
# comment (page two), hiding the freshest peer claim from claim adjudication.
outpg=$(tracker get ABS-105)
assert_contains "$outpg" "page-one-oldest-claim" "get returns page-one comments"
assert_contains "$outpg" "page-two-newest-claim" "get exhausts pages: page-two (newest) comment present"
pgclaims=$(printf '%s\n' "$outpg" | grep -c "kind: claim | actor: orchestrator")
assert_eq "$pgclaims" "2" "get returns both claim comments across page boundary"

# PILOT-12: fix_version — the native Jira fixVersions[] is rendered as a
# `fix_version:` frontmatter line, ONLY-WHEN-SET, byte-identical in format and
# position (immediately before depends_on) to backend-tracker.sh get (PILOT-7).
# Twin ABS-487.
outfv=$(tracker get ABS-108)
assert_contains "$outfv" "fix_version: v3.1.0" "get renders fix_version from a native single fixVersion"
fvcount=$(printf '%s\n' "$outfv" | grep -c '^fix_version:')
assert_eq "$fvcount" "1" "get emits exactly one fix_version line"
# byte-parity position: fix_version: sits immediately before depends_on:
fvln=$(printf '%s\n' "$outfv" | grep -nE '^fix_version:' | cut -d: -f1)
deln=$(printf '%s\n' "$outfv" | grep -nE '^depends_on:' | cut -d: -f1)
assert_eq "$((deln - fvln))" "1" "fix_version: sits immediately before depends_on: (backend parity position)"
# no regress: other frontmatter lines unchanged
assert_contains "$outfv" "role: be-developer" "fix_version render leaves role: line intact"
assert_contains "$outfv" "lane: normal" "fix_version render leaves lane: line intact"
# only-when-set: an issue with NO fixVersion emits NO fix_version line
# ($out still holds ABS-101, which carries no fixVersions -> byte-identical to pre-PILOT-12).
assert_not_contains "$out" "fix_version:" "get omits fix_version line when the issue has no fixVersion"
# multiple fixVersions -> exactly one deterministic line (first/primary; backend is single-valued)
outmv=$(tracker get ABS-109)
mvcount=$(printf '%s\n' "$outmv" | grep -c '^fix_version:')
assert_eq "$mvcount" "1" "multi-fixVersion get emits exactly one fix_version line"
assert_contains "$outmv" "fix_version: v3.1.0" "multi-fixVersion get renders the first (primary) version"
assert_not_contains "$outmv" "v4.0.0" "multi-fixVersion get does not render the secondary version"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: search — id<TAB>type<TAB>status<TAB>priority<TAB>title layout ===${NC}\n"
# =============================================================================
out=$(tracker search)
# ABS-331: the canonical priority (ABS-242 label mapping) is emitted as a column
# BEFORE the free-form title; ABS-101 carries no priority: label so it reads normal.
assert_contains "$out" "$(printf 'ABS-101\tepic\tBacklog\tnormal\tConformance demo epic')" "search rows are id<TAB>type<TAB>status<TAB>priority<TAB>title"
assert_contains "$out" "ABS-102" "search lists all fenced tickets"

# search field layout matches the mock's exactly (5 tab-separated columns, ABS-331)
cols=$(head -1 <<<"$out" | awk -F'\t' '{print NF}')
assert_eq "$cols" "5" "search rows have exactly 5 tab-separated columns (mock parity, ABS-331)"

out=$(tracker search --status Backlog)
assert_contains "$out" "ABS-101" "search --status filters"

out=$(tracker search --text "conformance")
assert_contains "$out" "ABS-101" "search --text matches case-insensitively in title"
assert_not_contains "$out" "ABS-102" "search --text excludes non-matching tickets"

# =============================================================================
echo -e "\n${CYAN}=== Test 5: children — id<TAB>[status]<TAB>title layout ===${NC}\n"
# =============================================================================
out=$(tracker children ABS-101)
assert_contains "$out" "$(printf 'ABS-102\t[Backlog]\tFirst child ticket')" "children rows are id<TAB>[status]<TAB>title"

# =============================================================================
echo -e "\n${CYAN}=== Test 6: comment — accepted kinds, structured header round-trip ===${NC}\n"
# =============================================================================
out=$(tracker comment ABS-101 --kind understanding --actor po-agent --body "PO understanding recorded.")
assert_eq "$out" "ABS-101: comment added" "comment prints the mock's success line"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: transition — resolves transition id, prints from->to ===${NC}\n"
# =============================================================================
out=$(tracker transition ABS-102 "Ready for Development" --actor coordinator --reason "prioritized")
assert_eq "$out" "ABS-102: Backlog -> Ready for Development" "transition prints '<id>: <from> -> <to>'"

ec=0
out=$(tracker transition ABS-102 "No Such Status" --actor coordinator --reason "typo" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "transition to an unavailable status fails"

# ABS-198 (Measure 3): compare-and-set parity with the mock. The shim serves
# ABS-102's fields=status as "Backlog", so --expect-from drives both branches.
out=$(tracker transition ABS-102 "Ready for Development" --actor coordinator --reason "cas mismatch" --expect-from "In Progress" 2>&1)
assert_eq "$out" "ABS-102: NOOP compare-and-set expect-from=In Progress actual=Backlog (skipped Ready for Development)" "compare-and-set mismatch is a logged NOOP, not a transition"
out=$(tracker transition ABS-102 "Ready for Development" --actor coordinator --reason "cas match" --expect-from "Backlog")
assert_eq "$out" "ABS-102: Backlog -> Ready for Development" "matching compare-and-set performs the transition"

# =============================================================================
echo -e "\n${CYAN}=== Test 8: link + update — success lines match the mock ===${NC}\n"
# =============================================================================
out=$(tracker link ABS-102 ABS-101 depends-on)
assert_eq "$out" "ABS-102: linked depends-on:ABS-101" "link prints the mock's success line"

out=$(tracker update ABS-102 title "Renamed child")
assert_eq "$out" "ABS-102: title updated" "update prints the mock's success line"

# =============================================================================
echo -e "\n${CYAN}=== Test 8b: v3 flags + ac-blocking + follow-up kinds (ABS-82) ===${NC}\n"
# =============================================================================
# get: flags/ac_blocking surfaced from labels (fixture ABS-104).
out=$(tracker get ABS-104)
assert_contains "$out" "flags: [design, security]" "get surfaces flag: labels as canonical flags list (sorted)"
assert_contains "$out" "ac_blocking: true" "get surfaces the ac-blocking label as ac_blocking: true"
assert_contains "$out" "role: fe-developer" "role label coexists with flag labels"
assert_not_contains "$(tracker get ABS-102)" "flags:" "get omits flags line when no flag labels present"

# create: --flag/--ac-blocking encoded as labels in the POST body.
CAPTURE="$TEST_DIR/create-capture.json"
: > "$CAPTURE"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE" tracker create --type ticket \
      --title "v3 flagged create" --flag design --flag data --ac-blocking)
assert_contains "$(cat "$CAPTURE")" "flag:design" "create --flag design lands as flag:design label"
assert_contains "$(cat "$CAPTURE")" "flag:data" "create --flag data lands as flag:data label"
assert_contains "$(cat "$CAPTURE")" "ac-blocking" "create --ac-blocking lands as ac-blocking label"

# create: invalid flag rejected before any HTTP call.
ec=0
out=$(tracker create --type ticket --title "bad" --flag bogus 2>&1) || ec=$?
assert_nonzero_exit "$ec" "create --flag bogus rejected"
assert_contains "$out" "invalid flag" "rejection names the invalid flag"

# create: lane (ABS-319) encoded as label lane:<value> in the POST body — default
# normal when omitted, and the explicit value when given.
CAPTURE_LANE_DEF="$TEST_DIR/create-lane-default.json"
: > "$CAPTURE_LANE_DEF"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE_LANE_DEF" tracker create --type ticket --title "default lane")
assert_contains "$(cat "$CAPTURE_LANE_DEF")" "lane:normal" "create without --lane lands as lane:normal label"
CAPTURE_LANE_FAST="$TEST_DIR/create-lane-fast.json"
: > "$CAPTURE_LANE_FAST"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE_LANE_FAST" tracker create --type ticket --title "fast lane" --lane fastlane)
assert_contains "$(cat "$CAPTURE_LANE_FAST")" "lane:fastlane" "create --lane fastlane lands as lane:fastlane label"

# update lane: replace-whole in place — PUT body drops any prior lane:* label and
# adds the new one, preserving every other label (role, flags).
CAPTURE_LANE_UPD="$TEST_DIR/update-lane-capture.json"
: > "$CAPTURE_LANE_UPD"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE_LANE_UPD" tracker update ABS-104 lane fastlane)
assert_eq "$out" "ABS-104: lane updated" "update lane prints the mock's success line"
assert_contains "$(cat "$CAPTURE_LANE_UPD")" "lane:fastlane" "update lane adds the lane:fastlane label"
assert_contains "$(cat "$CAPTURE_LANE_UPD")" "role:fe-developer" "update lane preserves the role label"

# update flags: replace-whole-set — PUT body keeps role/ac-blocking labels,
# drops old flag: labels, adds the new set.
CAPTURE2="$TEST_DIR/update-capture.json"
: > "$CAPTURE2"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE2" tracker update ABS-104 flags "[data]")
assert_eq "$out" "ABS-104: flags updated" "update flags prints the mock's success line"
assert_contains "$(cat "$CAPTURE2")" "flag:data" "update flags adds the new flag label"
assert_not_contains "$(cat "$CAPTURE2")" "flag:design" "update flags drops the previous flag labels (replace-whole-set)"
assert_contains "$(cat "$CAPTURE2")" "role:fe-developer" "update flags preserves the role label"

# update ac_blocking false: PUT body without the marker label.
CAPTURE3="$TEST_DIR/acb-capture.json"
: > "$CAPTURE3"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE3" tracker update ABS-104 ac_blocking false)
assert_eq "$out" "ABS-104: ac_blocking updated" "update ac_blocking prints the success line"
assert_not_contains "$(cat "$CAPTURE3")" "ac-blocking" "update ac_blocking false removes the marker label"

# update body / body-file (ABS-252): PUT rewrites the `description` field with
# the ADF-wrapped body; labels and comments are NOT touched (they are separate
# Jira fields), matching the mock's preserve-comments contract.
CAPTURE4="$TEST_DIR/body-capture.json"
: > "$CAPTURE4"
NEWBODY="$TEST_DIR/newbody.md"
printf '## Goal\n\nReworked goal.\n\n## Acceptance Criteria\n\n- [ ] AC1: reworked\n' > "$NEWBODY"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE4" tracker update ABS-104 body-file "$NEWBODY")
assert_eq "$out" "ABS-104: body updated" "update body-file prints the mock's success line"
assert_contains "$(cat "$CAPTURE4")" '"description"' "update body-file PUTs the description field"
assert_contains "$(cat "$CAPTURE4")" "AC1: reworked" "update body-file sends the new body text"
assert_contains "$(cat "$CAPTURE4")" '"type": "doc"' "update body-file wraps the body as an ADF document"
assert_not_contains "$(cat "$CAPTURE4")" '"labels"' "update body-file does not touch labels"

CAPTURE5="$TEST_DIR/body-inline-capture.json"
: > "$CAPTURE5"
out=$(JIRA_SHIM_CAPTURE_BODY="$CAPTURE5" tracker update ABS-104 body "Inline body text.")
assert_eq "$out" "ABS-104: body updated" "update body (inline) prints the mock's success line"
assert_contains "$(cat "$CAPTURE5")" "Inline body text." "update body sends the inline text as the description"

# update validation parity with the mock.
ec=0
tracker update ABS-104 flags "design" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update flags without [list] shape rejected"
ec=0
tracker update ABS-104 ac_blocking maybe >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update ac_blocking non-boolean rejected"

# v3 comment kinds accepted; invalid kind still rejected.
out=$(tracker comment ABS-101 --kind follow-up --actor qas --body "Follow-up: harden the fixture.")
assert_eq "$out" "ABS-101: comment added" "kind: follow-up accepted"
out=$(tracker comment ABS-101 --kind bsa-decision --actor bsa --body "Decision: create outside the epic.")
assert_eq "$out" "ABS-101: comment added" "kind: bsa-decision accepted"
# ABS-182: claim kind accepted (orchestrator stakes a distributed ticket claim).
out=$(tracker comment ABS-101 --kind claim --actor orchestrator --body "Staking claim on ABS-101.")
assert_eq "$out" "ABS-101: comment added" "kind: claim accepted"
ec=0
tracker comment ABS-101 --kind made-up --actor x --body "nope" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid comment kind still rejected"

# =============================================================================
echo -e "\n${CYAN}=== Test 8d: fixVersion create/update + parent inheritance (ABS-330) ===${NC}\n"
# =============================================================================
# Helper: assert the LAST captured request body's fields.fixVersions equals a
# given single-version array (or is absent when $2 is empty).
assert_fixversion() {
    local capfile="$1" want="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if WANT="$want" python3 - "$capfile" <<'PY'
import sys, json, os
want = os.environ.get("WANT", "")
last = None
for line in open(sys.argv[1]):
    line = line.strip()
    if line:
        last = json.loads(line)
fv = (last or {}).get("fields", {}).get("fixVersions")
if want == "":
    sys.exit(0 if fv is None else 1)
sys.exit(0 if fv == [{"name": want}] else 1)
PY
    then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; sed 's/^/    /' "$capfile"; FAIL=$((FAIL + 1))
    fi
}

# AC1 — explicit --fix-version lands as fields.fixVersions=[{"name":...}] in POST.
FV_AC1="$TEST_DIR/fv-ac1.json"; : > "$FV_AC1"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC1" tracker create --type ticket --title "Fixed-version create" --fix-version v3.0.0)
assert_fixversion "$FV_AC1" "v3.0.0" "create --fix-version builds fields.fixVersions=[{name:v3.0.0}] (AC1)"

# AC2 (root-cause) — create --parent <epic-with-fixVersion> and NO --fix-version
# inherits the parent's fixVersion onto the child.
FV_AC2="$TEST_DIR/fv-ac2.json"; : > "$FV_AC2"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC2" tracker create --type ticket --title "Inherited child" --parent ABS-201)
assert_fixversion "$FV_AC2" "v3.0.0" "create --parent inherits the parent epic's fixVersion (AC2 root-cause)"

# AC2 — parent has no fixVersion => child created with none (no error).
FV_AC2N="$TEST_DIR/fv-ac2n.json"; : > "$FV_AC2N"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC2N" tracker create --type ticket --title "No-version child" --parent ABS-101)
assert_fixversion "$FV_AC2N" "" "create --parent with a fixVersion-less parent adds none (AC2)"

# AC3 — an explicit --fix-version overrides inheritance (explicit wins).
FV_AC3="$TEST_DIR/fv-ac3.json"; : > "$FV_AC3"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC3" tracker create --type ticket --title "Explicit wins" --parent ABS-201 --fix-version v9.9.9)
assert_fixversion "$FV_AC3" "v9.9.9" "explicit --fix-version overrides the parent's (AC3)"
assert_not_contains "$(cat "$FV_AC3")" "v3.0.0" "explicit value replaces the inherited one (AC3)"

# AC4 (remediation) — update <id> fix_version sets fields.fixVersions via PUT.
FV_AC4="$TEST_DIR/fv-ac4.json"; : > "$FV_AC4"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC4" tracker update ABS-104 fix_version v3.0.0)
assert_eq "$out" "ABS-104: fix_version updated" "update fix_version prints the standard success line (AC4)"
assert_fixversion "$FV_AC4" "v3.0.0" "update fix_version PUTs fields.fixVersions=[{name:v3.0.0}] (AC4)"

# AC4 — empty value rejected with a clear die, like other update field checks.
ec=0
out=$(tracker update ABS-104 fix_version "" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "update fix_version empty value rejected (AC4)"
assert_contains "$out" "fix_version requires a non-empty value" "empty fix_version rejection names the field (AC4)"

# AC5 (regression) — a plain create with no fixVersion input keeps the POST body
# free of fixVersions (byte-identical to pre-ABS-330 behavior).
FV_AC5="$TEST_DIR/fv-ac5.json"; : > "$FV_AC5"
out=$(JIRA_SHIM_CAPTURE_BODY="$FV_AC5" tracker create --type ticket --title "Plain create")
assert_fixversion "$FV_AC5" "" "plain create adds no fixVersions (AC5 regression)"
assert_not_contains "$(cat "$FV_AC5")" "fixVersions" "plain create payload omits the fixVersions key entirely (AC5)"

# AC6 — help/usage advertises the new create flag and update field.
assert_contains "$help_output" "--fix-version" "help lists --fix-version on create (AC6)"
assert_contains "$help_output" "fix_version" "help lists fix_version as an update field (AC6)"

# =============================================================================
echo -e "\n${CYAN}=== Test 8c: assign — sets accountId, parity with mock (ABS-126) ===${NC}\n"
# =============================================================================
out=$(tracker assign ABS-101 "acct-xyz")
assert_eq "$out" "ABS-101: assignee set to acct-xyz" "assign prints the mock-parity success line"

ACAP="$TEST_DIR/assign-capture.json"
: > "$ACAP"
JIRA_SHIM_CAPTURE_BODY="$ACAP" tracker assign ABS-102 "acct-abc" >/dev/null
TOTAL=$((TOTAL + 1))
if python3 - "$ACAP" <<'PY'
import sys, json
for line in open(sys.argv[1]):
    line = line.strip()
    if not line: continue
    obj = json.loads(line)
    if obj.get("accountId") == "acct-abc":
        sys.exit(0)
sys.exit(1)
PY
then
    echo -e "  ${GREEN}PASS${NC} assign PUT body encodes accountId correctly"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} assign PUT body missing or malformed"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$ACAP"
fi

assert_contains "$help_output" "assign" "help lists the assign command"
assert_parity_error "assign arity parity" assign ABS-1

# =============================================================================
echo -e "\n${CYAN}=== Test 9: events — {ticket_id, from, to, at} lines + snapshot diff ===${NC}\n"
# =============================================================================
rm -f "$JIRA_TRACKER_STATE"
out=$(tracker events)
assert_contains "$out" "{ticket_id: ABS-101, from: null, to: Backlog" "first poll surfaces creation events (from: null)"
assert_contains "$out" ", at: " "event line carries an at: timestamp"

out=$(tracker events)
assert_empty "$out" "second poll with no changes is empty"

# Flip a status in the shim, expect exactly one net-change event next poll.
"$JIRA_CURL" __set_status ABS-102 "In Progress" >/dev/null 2>&1 || true
echo "ABS-102	In Progress" > "$JIRA_SHIM_DIR/status-override"
out=$(tracker events)
assert_contains "$out" "{ticket_id: ABS-102, from: Backlog, to: In Progress" "poll detects a net status change"
out=$(tracker events)
assert_empty "$out" "change delivered exactly once"

# =============================================================================
echo -e "\n${CYAN}=== Test 9e: ABS-308 — jql_search follows nextPageToken (no truncated sweep) ===${NC}\n"
# =============================================================================
# The shim splits the same three issues over two cursor pages. A single-page
# sweep would see only ABS-101/102 — the truncation that turns the events
# snapshot into a phantom-event machine.
out=$(JIRA_SHIM_PAGINATE=1 tracker search)
assert_contains "$out" "ABS-101" "paginated search returns page-1 issue ABS-101"
assert_contains "$out" "ABS-102" "paginated search returns page-1 issue ABS-102"
assert_contains "$out" "ABS-103" "paginated search returns page-2 issue ABS-103 (cursor followed)"

rm -f "$JIRA_TRACKER_STATE"
out=$(JIRA_SHIM_PAGINATE=1 tracker events)
assert_contains "$out" "ticket_id: ABS-103" "paginated events sweep sees the page-2 ticket"
out=$(JIRA_SHIM_PAGINATE=1 tracker events)
assert_empty "$out" "paginated second poll with no changes is empty (no phantom re-entry)"

# =============================================================================
echo -e "\n${CYAN}=== Test 9f: ABS-308 — a partial sweep never drops snapshot entries ===${NC}\n"
# =============================================================================
# BUSCH-54 defect class: a ticket absent from ONE sweep (hiccup / paging gap)
# was dropped from the snapshot and re-entered the NEXT sweep as a phantom
# "from: null" creation event — re-classifying a RESTING ticket as freshly
# transitioned, one paid PO no-op spawn per sweep (17 observed in 24h).
rm -f "$JIRA_TRACKER_STATE"
tracker events >/dev/null                       # full sweep primes the snapshot (101/102/103)
out=$(JIRA_SHIM_PARTIAL=1 tracker events)       # ABS-103 missing from this sweep
assert_empty "$out" "a partial sweep emits no phantom events for the missing ticket"
assert_contains "$(cat "$JIRA_TRACKER_STATE")" "ABS-103" "the missing ticket keeps its snapshot entry (merge, not replace)"
out=$(tracker events)                           # full sweep again: ABS-103 is back
assert_not_contains "$out" "ticket_id: ABS-103" "the returning ticket produces NO from:null re-entry event"

# =============================================================================
echo -e "\n${CYAN}=== Test 9b: JQL escaping — embedded quote does not break the JQL ===${NC}\n"
# =============================================================================
# A --text value containing a double quote must be escaped inside the JQL string
# literal, so the request body is still well-formed JSON with a well-formed JQL.
cap="$TEST_DIR/reqbody.log"
: > "$cap"
JIRA_SHIM_CAPTURE_BODY="$cap" tracker search --text 'foo"bar' >/dev/null 2>&1 || true
# The captured POST body must be valid JSON (python parses it) and its jql must
# contain the escaped literal foo\"bar (not a bare, JQL-breaking foo"bar).
TOTAL=$((TOTAL + 1))
if python3 - "$cap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)              # must be valid JSON (raises otherwise)
    jql = obj.get("jql", "")
    if 'text ~' in jql and 'foo\\"bar' in jql:
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} --text with an embedded quote yields well-formed, escaped JQL"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} JQL escaping: embedded quote not escaped / body malformed"; FAIL=$((FAIL + 1))
    echo -e "  ${YELLOW}  captured bodies:${NC}"; sed 's/^/    /' "$cap"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 9e: search endpoint migration — /rest/api/3/search/jql (CHANGE-2046) ===${NC}\n"
# =============================================================================
# Atlassian removed POST /rest/api/3/search (HTTP 410 Gone). The adapter must
# call the new POST /rest/api/3/search/jql for every JQL sweep. The shim returns
# 410 for the legacy path, so if the adapter still used it, search/children/
# events would die with an HTTP 410 error instead of returning rows.

# (a) the adapter never touches the removed legacy endpoint: no 410 error text.
ep_log="$TEST_DIR/endpoint.log"
{
    tracker search
    tracker children ABS-101
    tracker events
} > "$ep_log" 2>&1 || true
assert_not_contains "$(cat "$ep_log")" "HTTP 410" "no JQL sweep hits the removed /rest/api/3/search (would be HTTP 410)"
assert_not_contains "$(cat "$ep_log")" "has been removed" "no legacy-endpoint removal error surfaces"

# (b) the request body targets the new endpoint with maxResults=100 (the new
#     endpoint's cap). Capture the sweep body and assert its shape.
rm -f "$JIRA_TRACKER_STATE"
scap="$TEST_DIR/search-body.log"
: > "$scap"
JIRA_SHIM_CAPTURE_BODY="$scap" tracker search >/dev/null 2>&1 || true
TOTAL=$((TOTAL + 1))
if python3 - "$scap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    if "jql" in obj and obj.get("maxResults") == 100:
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} JQL sweep body sets maxResults=100 (new-endpoint cap)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} JQL sweep body missing/incorrect maxResults (expected 100)"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$scap"
fi

# (b2) ABS-331: the search JQL is ordered age-ASC within the fence so the live
#      priority-dispatch tiebreak (ABS-261) holds instead of Jira's default order.
TOTAL=$((TOTAL + 1))
if python3 - "$scap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    if "ORDER BY created ASC" in (obj.get("jql") or ""):
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} search JQL carries ORDER BY created ASC (age-ASC within the fence, ABS-331)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} search JQL missing ORDER BY created ASC (ABS-331)"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$scap"
fi

# (b3) ABS-389: the EMITTED rows honour the canonical cross-adapter order
#      `priority ASC, created ASC`. Priority is a label (not JQL-orderable), so
#      the adapter re-sorts the age-ASC JQL rows by priority band in the emit
#      step. The PRIOORDER fixture returns them age-ASC with scrambled
#      priorities; a pass proves the re-sort, incl. the stable within-band age
#      tiebreak (two normals: ABS-390 old before ABS-394 young).
prio_order="$(JIRA_SHIM_PRIOORDER=1 tracker search | cut -f1 | tr '\n' ' ')"
assert_eq "$prio_order" "ABS-391 ABS-393 ABS-390 ABS-394 ABS-392 " \
  "search emits rows priority ASC then created ASC (hotfix>high>normal[old>young]>low)"

# (c) the legacy path really is a 410 in the shim (guards the migration test's
#     own premise — a false-green if the shim silently served rows there).
leg="$(JIRA_SHIM_FORCE_HTTP= "$JIRA_CURL" -X POST -o /dev/stdout -w '' "https://dummy.atlassian.net/rest/api/3/search" --data-binary '{}' 2>/dev/null)"
assert_contains "$leg" "has been removed" "shim serves HTTP 410 for the removed legacy /rest/api/3/search"

# =============================================================================
echo -e "\n${CYAN}=== Test 9f: ADF newlines — real newlines split into paragraphs, verbatim (ABS-111) ===${NC}\n"
# =============================================================================
# The literal-"\n" artifact from live run 1 is fixed at its ROOT upstream: the
# orchestrator JSON-unescapes the spawn `result` before it reaches ANY adapter
# (scripts/orchestrator.sh json_unescape), so a handoff body arrives here with
# REAL newlines. This adapter is byte-verbatim (like the create/description path):
# adf_wrap splits real newlines into one paragraph per line, and a literal
# backslash-n is posted AS-IS (never silently turned into a newline). Assert both.
ncap="$TEST_DIR/comment-adf.log"
: > "$ncap"
JIRA_SHIM_CAPTURE_BODY="$ncap" tracker comment ABS-101 --kind handoff --actor orchestrator \
    --body "$(printf 'Line one.\nLine two.\n\nLine four.')" >/dev/null 2>&1 || true
TOTAL=$((TOTAL + 1))
if python3 - "$ncap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    doc = obj.get("body")
    if not isinstance(doc, dict):
        continue
    # collect every text node
    texts = []
    def walk(n):
        if isinstance(n, list):
            for x in n: walk(x)
        elif isinstance(n, dict):
            if n.get("type") == "text":
                texts.append(n.get("text", ""))
            for x in n.get("content", []) or []:
                walk(x)
    walk(doc)
    joined = "".join(texts)
    paras = [c for c in doc.get("content", []) if c.get("type") == "paragraph"]
    # Real newlines split into paragraphs (header + Line one + Line two + blank + Line four).
    if "Line one." in texts and "Line two." in texts \
       and "Line four." in texts and len(paras) >= 4:
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} real newlines in a comment body split into ADF paragraphs"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} comment body did not split real newlines into paragraphs"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$ncap"
fi

# Verbatim contract: a LITERAL backslash-n is posted as-is, NOT decoded to a
# newline (the root fix lives upstream in the orchestrator; the adapter must not
# second-guess a body that legitimately contains the two chars backslash-n).
vcap="$TEST_DIR/comment-verbatim.log"
: > "$vcap"
JIRA_SHIM_CAPTURE_BODY="$vcap" tracker comment ABS-101 --kind handoff --actor orchestrator \
    --body 'alpha\nbeta' >/dev/null 2>&1 || true
TOTAL=$((TOTAL + 1))
if python3 - "$vcap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    doc = obj.get("body")
    if not isinstance(doc, dict):
        continue
    texts = []
    def walk(n):
        if isinstance(n, list):
            for x in n: walk(x)
        elif isinstance(n, dict):
            if n.get("type") == "text":
                texts.append(n.get("text", ""))
            for x in n.get("content", []) or []:
                walk(x)
    walk(doc)
    # The literal two chars backslash-n survive verbatim in a single text node.
    if any("alpha\\nbeta" in t for t in texts):
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} literal backslash-n is posted verbatim (adapter does not decode)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} literal backslash-n was altered by the adapter (should be verbatim)"; FAIL=$((FAIL + 1))
    sed 's/^/    /' "$vcap"
fi

# The kind/actor header is still on its own first paragraph so `get` round-trips
# it (the verbatim path must not disturb the "[kind: ... | actor: ...]" first line).
TOTAL=$((TOTAL + 1))
if python3 - "$ncap" <<'PY'
import sys, json
ok = False
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    doc = obj.get("body")
    if not isinstance(doc, dict):
        continue
    first = doc.get("content", [{}])[0]
    fc = first.get("content", [])
    if fc and fc[0].get("text", "").startswith("[kind: handoff | actor: orchestrator]"):
        ok = True
sys.exit(0 if ok else 1)
PY
then
    echo -e "  ${GREEN}PASS${NC} kind/actor header stays the first ADF paragraph (get round-trip preserved)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} kind/actor header paragraph disturbed by the newline decode"; FAIL=$((FAIL + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 9c: timestamp normalization + ABS-62 stall helpers (BLOCKER) ===${NC}\n"
# =============================================================================
# The orchestrator's iso_to_epoch parses ONLY the mock's %Y-%m-%dT%H:%M:%SZ
# form. Jira emits native millis+offset timestamps. `get` MUST normalize them to
# ...Z UTC, or the ABS-62 stall subsystem silently breaks. We assert this by
# running the orchestrator's OWN helper functions (extracted from the real
# scripts/orchestrator.sh, never re-implemented) against a real jira `get` dump.
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
ORCH_HELPERS="$TEST_DIR/orch-helpers.sh"
# Extract the self-contained stall helpers (iso_to_epoch, fm_field,
# last_po_park_epoch, has_orchestrator_stall_marker) by function-name markers so
# this stays robust if surrounding orchestrator code moves.
awk '
    /^iso_to_epoch\(\) \{/            { grab=1 }
    grab                             { print }
    grab && /^has_orchestrator_stall_marker\(\) \{/ { inlast=1 }
    inlast && /^\}$/                 { grab=0; inlast=0 }
' "$ORCH" > "$ORCH_HELPERS"
# Guard the extraction: it must contain all four helpers and must not run away
# past the block (capturing main would execute the orchestrator on source).
for fn in iso_to_epoch fm_field last_po_park_epoch has_orchestrator_stall_marker; do
    grep -q "^${fn}() {" "$ORCH_HELPERS" || { echo "FATAL: helper extraction missing ${fn}() — orchestrator.sh layout changed"; exit 1; }
done
if grep -q '^main' "$ORCH_HELPERS"; then
    echo "FATAL: helper extraction over-captured (contains main) — fix the awk markers"; exit 1
fi

# The dump under test — a real jira get, produced through the shim (created:/
# updated: come back as +0530 Jira-native and must be normalized to ...Z).
DUMP="$(tracker get ABS-101)"

# 1) created:/updated: are emitted in the mock's ...Z form (no millis/offset).
assert_contains "$DUMP" "created: 2026-07-04T10:00:00Z" "get normalizes created: +0530 Jira ts -> UTC Z"
assert_contains "$DUMP" "updated: 2026-07-04T12:00:00Z" "get normalizes updated: +0530 Jira ts -> UTC Z"
assert_not_contains "$DUMP" "+0530" "no raw Jira offset survives into the dump"
assert_not_contains "$DUMP" ".000" "no raw Jira millis survive into the dump"
# comment header timestamps are normalized too (### <at> ...Z).
assert_contains "$DUMP" "### 2026-07-04T12:00:00Z | kind: decision | actor: orchestrator" "comment header ts normalized to UTC Z"

# 2) The orchestrator's REAL iso_to_epoch parses every emitted timestamp.
created_val=$(printf '%s\n' "$DUMP" | awk -F': ' '/^created: /{print $2; exit}')
updated_val=$(printf '%s\n' "$DUMP" | awk -F': ' '/^updated: /{print $2; exit}')
hdr_val=$(printf '%s\n' "$DUMP" | awk '/^### /{n=split($0,f," "); print f[2]; exit}')

epoch_created=$(bash -c "source '$ORCH_HELPERS'; iso_to_epoch '$created_val'")
epoch_updated=$(bash -c "source '$ORCH_HELPERS'; iso_to_epoch '$updated_val'")
epoch_hdr=$(bash -c "source '$ORCH_HELPERS'; iso_to_epoch '$hdr_val'")
TOTAL=$((TOTAL + 1))
if [ -n "$epoch_created" ] && [ -n "$epoch_updated" ] && [ -n "$epoch_hdr" ]; then
    echo -e "  ${GREEN}PASS${NC} orchestrator iso_to_epoch parses created:/updated:/### <at> to non-empty epochs"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} iso_to_epoch returned empty (created=$epoch_created updated=$epoch_updated hdr=$epoch_hdr)"; FAIL=$((FAIL + 1))
fi

# 3) last_po_park_epoch detects the PO park ("Needs PO Decision -> Backlog") in
#    the dump, and returns a parseable epoch — the guard that prevents re-raising
#    a genuinely PO-parked ticket every sweep.
park_epoch=$(bash -c "source '$ORCH_HELPERS'; last_po_park_epoch \"\$1\"" _ "$DUMP")
TOTAL=$((TOTAL + 1))
if [ -n "$park_epoch" ] && [ "$park_epoch" -gt 0 ] 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} last_po_park_epoch detects the PO park from the jira dump (epoch=$park_epoch)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} last_po_park_epoch empty/unparseable -> PO-parked ticket would re-raise every sweep (got: '$park_epoch')"; FAIL=$((FAIL + 1))
fi

# 4) has_orchestrator_stall_marker recognizes the real stall-raise decision.
TOTAL=$((TOTAL + 1))
if bash -c "source '$ORCH_HELPERS'; has_orchestrator_stall_marker \"\$1\"" _ "$DUMP"; then
    echo -e "  ${GREEN}PASS${NC} has_orchestrator_stall_marker detects the stall-raise decision in the jira dump"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} has_orchestrator_stall_marker did not detect the stall marker"; FAIL=$((FAIL + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 9d: status normalization — case-fold + provider alias ===${NC}\n"
# =============================================================================
# The neutral adapter surfaces canonical spellings to the orchestrator even when
# the human Jira workflow differs by case, or by a configured alias. The read
# path (search/get/children/events) feeds the orchestrator's case-SENSITIVE
# map_action, so it MUST canonicalize. ABS-102's status is driven by the shim
# override; `search` runs it through the same canon() as get/children/events.

# (a) case-fold: a lowercased Jira status is surfaced with canonical casing.
echo "ABS-102	in review" > "$JIRA_SHIM_DIR/status-override"
out=$(tracker search)
assert_contains "$out" "$(printf 'ABS-102\tticket\tIn Review\t')" "read path folds 'in review' -> canonical 'In Review'"

# (b) alias (read): a genuinely different Jira name maps to the canonical one.
echo "ABS-102	Selected for Development" > "$JIRA_SHIM_DIR/status-override"
out=$(JIRA_STATUS_ALIASES="Ready for Development=Selected for Development" tracker search)
assert_contains "$out" "$(printf 'ABS-102\tticket\tReady for Development\t')" "read path aliases 'Selected for Development' -> 'Ready for Development'"

# (c) neutral default: without the env, the Jira name passes through unchanged.
out=$(tracker search)
assert_contains "$out" "$(printf 'ABS-102\tticket\tSelected for Development\t')" "no alias configured -> Jira name passes through (neutral default)"

# (d) whitespace tolerance: spaces around '=' don't break the alias (both sides
# stripped, so read canon() and write to_jira() stay symmetric).
echo "ABS-102	Selected for Development" > "$JIRA_SHIM_DIR/status-override"
out=$(JIRA_STATUS_ALIASES="Ready for Development = Selected for Development" tracker search)
assert_contains "$out" "$(printf 'ABS-102\tticket\tReady for Development\t')" "alias tolerates whitespace around '=' -> 'Ready for Development'"

# Restore ABS-102 to a canonical resting status for any later use.
echo "ABS-102	Backlog" > "$JIRA_SHIM_DIR/status-override"

# =============================================================================
echo -e "\n${CYAN}=== Test 9g: oversized response — parsed via stdin, not argv (ABS-250) ===${NC}\n"
# =============================================================================
# A response JSON handed to python as an argv ARGUMENT dies with "Argument list
# too long" once it passes the OS argument limit — ~32 KB on Windows/MSYS (the
# reported break, a consumer's real ticket), ~1 MB here. ABS-106 serves a ~1.5 MB
# comment history, which exceeds the limit on EVERY platform, so this asserts the
# out-of-band (stdin / page-file) handover on macOS and Linux too.
big_out=$(tracker get ABS-106 2>"$TEST_DIR/big.err"); big_rc=$?
big_err=$(cat "$TEST_DIR/big.err")

assert_exit_code "$big_rc" 0 "get on a ~1.5MB comment history exits 0"
assert_not_contains "$big_err" "Argument list too long" "no E2BIG: response never crosses the argv boundary"
# Assert over COUNTS, not the payload itself: assert_contains pipes its input to
# `grep -q`, which exits at the first match and leaves the 1.5 MB writer with a
# SIGPIPE ("write error: Broken pipe") — noise, not a failure. grep -c drains.
assert_eq "$(echo "$big_out" | grep -c '^id: ABS-106$')" "1" "oversized get still emits canonical frontmatter"
# Every comment survives: the LAST one carries the marker, so a truncated or
# dropped page (the ABS-182 failure mode) is caught here as well.
assert_eq "$(echo "$big_out" | grep -c '^### ')" "400" "all 400 comments rendered from the oversized response"
assert_eq "$(echo "$big_out" | grep -c 'LAST-COMMENT-MARKER')" "1" "the NEWEST comment survives (claim adjudication reads it)"

# The same guard for the OTHER response-consuming ops: a fat JQL sweep must not
# reach argv either. The shim's search set is small, so this asserts the code
# path is wired to stdin rather than re-measuring size.
assert_not_contains "$(tracker events 2>&1)" "Argument list too long" "events: JQL response parsed via stdin"
assert_not_contains "$(tracker search 2>&1)" "Argument list too long" "search: JQL response parsed via stdin"

# =============================================================================
echo -e "\n${CYAN}=== Test 9h: oversized REQUEST body — posted via @file/stdin, not argv (ABS-263) ===${NC}\n"
# =============================================================================
# The write-path counterpart of Test 9g. A multi-KB comment body (gate-results /
# handoff) handed to python or curl as an argv ARGUMENT dies with "Argument list
# too long" past the OS argv limit — ~32 KB on Windows/MSYS, ~1 MB here. The body
# arrives via --body-file (the file escape hatch seats use — the CLI --body flag
# would itself hit the argv limit), so this exercises the INTERNAL write path:
# post_structured_comment's ADF build and http_call's curl. A ~2 MB body is past
# this host's ARG_MAX, so the guard holds on macOS/Linux, not just Windows.
# Pre-fix it dies at the first argv boundary (post_structured_comment's py call);
# post-fix it streams over stdin and reaches curl via --data-binary "@file".
bodyf="$TEST_DIR/write-oversize-body.txt"
python3 -c 'import sys; sys.stdout.write("EVIDENCE " * 250000 + "WRITE-PATH-MARKER")' > "$bodyf"  # ~2 MB
wcap="$TEST_DIR/write-oversize.log"
: > "$wcap"
wbig_out=$(JIRA_SHIM_CAPTURE_BODY="$wcap" tracker comment ABS-101 --kind gate-results --actor qas \
    --body-file "$bodyf" 2>"$TEST_DIR/wbig.err"); wbig_rc=$?
wbig_err=$(cat "$TEST_DIR/wbig.err")

assert_exit_code "$wbig_rc" 0 "comment with a ~2MB body exits 0"
assert_not_contains "$wbig_err" "Argument list too long" "no E2BIG: request body never crosses the argv boundary"
assert_eq "$wbig_out" "ABS-101: comment added" "oversized comment reports success"
# The shim captured the request body via --data-binary "@file": the end marker
# proves the FULL body reached curl (not truncated / dropped). grep -c on the file
# drains it (grep -q would SIGPIPE the writer, per Test 9g's note).
assert_eq "$(grep -c 'WRITE-PATH-MARKER' "$wcap")" "1" "the full oversized body reached the request (posted, not dropped)"

# =============================================================================
echo -e "\n${CYAN}=== Test 9j: oversized UPDATE body — description streams over stdin, not argv (ABS-263) ===${NC}\n"
# =============================================================================
# The third request site, and the one Test 9h did not cover: `update <id> body-file`
# (added by ABS-252) rebuilt the description ADF through json.loads(sys.argv[1]).
# ABS-263's first pass fixed post_structured_comment + cmd_create but this path
# merged into the epic branch afterwards, so integration caught it as a residual
# argv crossing — exactly what the lint guard is for. Same ~2 MB body as 9h: past
# this host's ARG_MAX, so a regression here fails on macOS/Linux too, not only on
# the Windows/MSYS ~32 KB limit this ticket exists to serve.
ubodyf="$TEST_DIR/update-oversize-body.txt"
python3 -c 'import sys; sys.stdout.write("EVIDENCE " * 250000 + "UPDATE-PATH-MARKER")' > "$ubodyf"  # ~2 MB
ucap="$TEST_DIR/update-oversize.log"
: > "$ucap"
ubig_out=$(JIRA_SHIM_CAPTURE_BODY="$ucap" tracker update ABS-104 body-file "$ubodyf" \
    2>"$TEST_DIR/ubig.err"); ubig_rc=$?
ubig_err=$(cat "$TEST_DIR/ubig.err")

assert_exit_code "$ubig_rc" 0 "update body-file with a ~2MB body exits 0"
assert_not_contains "$ubig_err" "Argument list too long" "no E2BIG: description never crosses the argv boundary"
assert_eq "$ubig_out" "ABS-104: body updated" "oversized update reports success"
# grep -c (not -q) drains the capture: -q SIGPIPEs the writer, per Test 9g's note.
assert_eq "$(grep -c 'UPDATE-PATH-MARKER' "$ucap")" "1" "the full oversized description reached the request (written, not dropped)"

# =============================================================================
echo -e "\n${CYAN}=== Test 9i: malformed comment page — page dir freed, no leak (ABS-263) ===${NC}\n"
# =============================================================================
# cmd_get's page-loop parse dies under `set -e` on a malformed page and, pre-fix,
# leaked its mktemp -d dir on every such poll. ABS-107 serves an unparseable
# comment page; get must fail cleanly (non-zero) AND leave no jira-comments.* dir
# behind. Use a private TMPDIR so only THIS call's dir would show up.
gtmp="$TEST_DIR/getleaktmp"; mkdir -p "$gtmp"
TMPDIR="$gtmp" tracker get ABS-107 >/dev/null 2>"$TEST_DIR/mal.err"; mal_rc=$?
leaked=$(ls -d "$gtmp"/jira-comments.* 2>/dev/null | wc -l | tr -d ' ')
assert_nonzero_exit "$mal_rc" "get on a malformed comment page fails cleanly (non-zero exit)"
assert_eq "$leaked" "0" "malformed comment page leaks no jira-comments mktemp dir"

# =============================================================================
echo -e "\n${CYAN}=== Test 10: CREDENTIAL LEAK — dummy token absent from all output ===${NC}\n"
# =============================================================================
# Drive every op and capture combined stdout+stderr; the token must not appear.
leak_log="$TEST_DIR/leak.log"
: > "$leak_log"
{
    tracker help
    tracker create --type ticket --title "leak probe"
    tracker get ABS-101
    tracker search
    tracker search --text conformance
    tracker children ABS-101
    tracker comment ABS-101 --kind notification --actor orchestrator --body "probe"
    tracker transition ABS-101 "Ready for Development" --actor x --reason y
    tracker link ABS-101 ABS-102 pr
    tracker update ABS-101 title "probe title"
    tracker events
    # Also force error paths (bad HTTP) to check scrubbing of error output.
    JIRA_SHIM_FORCE_HTTP=500 tracker get ABS-999
    JIRA_SHIM_FORCE_CURLFAIL=1 tracker get ABS-998
} >>"$leak_log" 2>&1 || true

assert_not_contains "$(cat "$leak_log")" "$DUMMY_TOKEN" "raw API token never appears in any output/error/log"

# The base64 Basic-auth encoding of email:token must also be absent.
b64=$(printf '%s:%s' "$JIRA_EMAIL" "$JIRA_API_TOKEN" | python3 -c 'import sys,base64; sys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode())')
assert_not_contains "$(cat "$leak_log")" "$b64" "base64 Basic-auth credential never appears in any output/error/log"

# The forced error paths must still fail cleanly (non-zero) and scrub.
ec=0; JIRA_SHIM_FORCE_HTTP=500 tracker get ABS-777 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "HTTP 500 surfaces as a clean adapter error"

# =============================================================================
echo -e "\n${CYAN}=== Test 11: LIVE SMOKE (only when JIRA_API_TOKEN is a real token) ===${NC}\n"
# =============================================================================
# The offline tier sets a DUMMY token; the live tier is opt-in via a real token
# passed through JIRA_LIVE_TOKEN (kept separate so the offline tier never talks
# to a network). Skipped — with a clear message — otherwise. CI skips it.
if [ -n "${JIRA_LIVE_TOKEN:-}" ]; then
    echo -e "  ${CYAN}running live smoke against ${JIRA_SITE_LIVE:-\$JIRA_SITE}${NC}"
    (
        unset JIRA_CURL JIRA_SHIM_DIR
        export JIRA_API_TOKEN="$JIRA_LIVE_TOKEN"
        [ -n "${JIRA_SITE_LIVE:-}" ] && export JIRA_SITE="$JIRA_SITE_LIVE"
        [ -n "${JIRA_EMAIL_LIVE:-}" ] && export JIRA_EMAIL="$JIRA_EMAIL_LIVE"
        [ -n "${JIRA_PROJECT_KEY_LIVE:-}" ] && export JIRA_PROJECT_KEY="$JIRA_PROJECT_KEY_LIVE"
        smoke=$(bash "$TRACKER" search 2>&1) || { echo "live search failed: $smoke"; exit 1; }
        head -3 <<<"$smoke"
    )
    lrc=$?
    assert_exit_code "$lrc" 0 "live smoke: search against the fenced project succeeds"
else
    echo -e "  ${YELLOW}SKIP${NC} live smoke tier (set JIRA_LIVE_TOKEN to enable; CI skips this)"
    SKIP=$((SKIP + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
# =============================================================================
echo -e "  Total:   $TOTAL"
echo -e "  ${GREEN}Passed:  $PASS${NC}"
echo -e "  Skipped: $SKIP"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed:  $FAIL${NC}"
    exit 1
else
    echo -e "  Failed:  0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
