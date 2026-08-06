#!/bin/bash
# =============================================================================
# Test: Tracker Divergence Reporter (epic ABS-326, story ABS-328)
# =============================================================================
# Offline test for scripts/tracker-divergence.sh against STUB adapters (no
# Jira, no backend): asserts the reporter's whole contract —
#   1. identical trackers -> exit 0, clean report, history line unexplained=0,
#   2. an artificially injected STATUS DRIFT on a test ticket is detected on
#      the next run with both values in the report (the AC's drift scenario),
#   3. a whitelist entry marks the same drift explained -> exit 0, still
#      listed in the report,
#   4. a ticket missing on the mirror -> presence divergence,
#   5. a comment-count difference is detected,
#   6. READ-ONLY audit: the stub adapters record every invocation; only the
#      read verbs `search`/`get` may occur, and the script source passes no
#      mutating verb to any adapter (AC 3).
#
# Run from repo root: bash tests/tooling/test-tracker-divergence.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORTER="$REPO_ROOT/scripts/tracker-divergence.sh"

TEST_DIR=$(mktemp -d /tmp/tracker-divergence-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"
        echo "        expected: $(printf '%q' "$expected")"
        echo "        actual:   $(printf '%q' "$actual")"
        FAIL=$((FAIL + 1))
    fi
}

assert_true() {
    local code="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

# --- Stub adapter: a dir of canonical dumps + a search listing -----------------
# Usage: STUB_STORE=<dir> stub.sh (search|get <id>); records every argv line.
STUB="$TEST_DIR/stub-adapter.sh"
cat > "$STUB" <<'EOF'
#!/bin/bash
echo "$*" >> "$STUB_CALLS"
case "${1:-}" in
    search) cat "$STUB_STORE/search.tsv" ;;
    get)    [ -f "$STUB_STORE/$2.md" ] || { echo "ERROR: not found: $2" >&2; exit 1; }
            cat "$STUB_STORE/$2.md" ;;
    *)      echo "ERROR: stub got unexpected verb: $1" >&2; exit 99 ;;
esac
EOF
chmod +x "$STUB"

# write_ticket <store> <id> <status> <comment-count>
write_ticket() {
    local store="$1" id="$2" status="$3" ncom="$4" i
    {
        printf -- '---\nid: %s\ntype: ticket\ntitle: Test %s\nstatus: %s\nparent: ABS-900\n' "$id" "$id" "$status"
        printf 'lane: normal\npriority: normal\ndepends_on: []\nlinks: []\n'
        printf 'created: 2026-07-16T08:00:00Z\nupdated: 2026-07-16T08:00:00Z\n---\n\nBody.\n\n## Comments\n'
        i=0
        while [ "$i" -lt "$ncom" ]; do
            printf '\n### 2026-07-16T08:0%s:00Z | kind: notification | actor: test\n\ncomment %s\n' "$i" "$i"
            i=$((i + 1))
        done
    } > "$store/$id.md"
}

# build_store <dir> — two tickets, baseline shape.
build_store() {
    mkdir -p "$1"
    printf 'ABS-101\tticket\tDoing\tTest ABS-101\nABS-102\tticket\tBacklog\tTest ABS-102\n' > "$1/search.tsv"
    write_ticket "$1" ABS-101 Doing 2
    write_ticket "$1" ABS-102 Backlog 0
}

run_reporter() {  # run_reporter <primary-store> <mirror-store> [whitelist]
    STUB_STORE_PRIMARY="$1" STUB_STORE_MIRROR="$2" \
    DIVERGENCE_PRIMARY_CMD="$TEST_DIR/primary-wrap.sh" \
    DIVERGENCE_MIRROR_CMD="$TEST_DIR/mirror-wrap.sh" \
    DIVERGENCE_STATE_DIR="$STATE_DIR" \
    DIVERGENCE_WHITELIST="${3:-$TEST_DIR/no-whitelist.txt}" \
    bash "$REPORTER" >"$TEST_DIR/out.txt" 2>"$TEST_DIR/err.txt"
}

# Wrappers bind the shared stub to the right store per side.
cat > "$TEST_DIR/primary-wrap.sh" <<EOF
#!/bin/bash
STUB_STORE="\$STUB_STORE_PRIMARY" STUB_CALLS="$TEST_DIR/calls.txt" exec "$STUB" "\$@"
EOF
cat > "$TEST_DIR/mirror-wrap.sh" <<EOF
#!/bin/bash
STUB_STORE="\$STUB_STORE_MIRROR" STUB_CALLS="$TEST_DIR/calls.txt" exec "$STUB" "\$@"
EOF
chmod +x "$TEST_DIR/primary-wrap.sh" "$TEST_DIR/mirror-wrap.sh"

STATE_DIR="$TEST_DIR/state"
json_get() { python3 -c "import json,sys; d=json.load(open('$STATE_DIR/report.json')); print($1)"; }

echo -e "${CYAN}=== tracker-divergence.sh — divergence reporter (ABS-328) ===${NC}\n"

# --- 1. Identical sides -> clean gate ------------------------------------------
echo -e "${CYAN}[1] identical trackers -> exit 0, clean report${NC}"
build_store "$TEST_DIR/jira-a"; build_store "$TEST_DIR/back-a"
: > "$TEST_DIR/calls.txt"
run_reporter "$TEST_DIR/jira-a" "$TEST_DIR/back-a"
assert_eq "$?" 0 "exit 0 on identical trackers"
assert_eq "$(json_get "d['unexplained_count']")" 0 "report.json: unexplained_count 0"
assert_eq "$(json_get "d['tickets_compared']")" 2 "report.json: both fenced tickets compared"
assert_true "$(grep -q 'unexplained=0' "$STATE_DIR/history.log"; echo $?)" \
    "history line appended with unexplained=0"

# --- 2. Artificial status drift (the AC scenario) --------------------------------
echo -e "\n${CYAN}[2] injected status drift is detected on the next run${NC}"
build_store "$TEST_DIR/jira-b"; build_store "$TEST_DIR/back-b"
write_ticket "$TEST_DIR/back-b" ABS-101 Blocked 2     # drift: Doing -> Blocked, mirror side
run_reporter "$TEST_DIR/jira-b" "$TEST_DIR/back-b"
assert_eq "$?" 1 "exit 1 (unexplained divergence gates)"
assert_eq "$(json_get "[e['field'] for e in d['divergences'] if e['key']=='ABS-101']")" "['status']" \
    "exactly the drifted field reported"
assert_eq "$(json_get "next(e['primary']+'/'+e['mirror'] for e in d['divergences'] if e['field']=='status')")" \
    "Doing/Blocked" "report carries BOTH values (AC 1)"
assert_true "$(grep -q 'Doing' "$STATE_DIR/report.md" && grep -q 'Blocked' "$STATE_DIR/report.md"; echo $?)" \
    "markdown report lists both values"

# --- 3. Whitelist marks it explained ---------------------------------------------
echo -e "\n${CYAN}[3] whitelisted divergence: listed but not gating${NC}"
printf '# operator whitelist\nABS-10*|status|migration backfill pending (test)\n' > "$TEST_DIR/wl.txt"
run_reporter "$TEST_DIR/jira-b" "$TEST_DIR/back-b" "$TEST_DIR/wl.txt"
assert_eq "$?" 0 "exit 0 when every divergence is explained"
assert_eq "$(json_get "d['explained_count']")" 1 "entry still listed, marked explained"
assert_true "$(grep -q 'migration backfill pending' "$STATE_DIR/report.md"; echo $?)" \
    "markdown report shows the whitelist reason"

# --- 4. Missing ticket on the mirror ---------------------------------------------
echo -e "\n${CYAN}[4] ticket missing on the mirror -> presence divergence${NC}"
build_store "$TEST_DIR/jira-c"; build_store "$TEST_DIR/back-c"
rm "$TEST_DIR/back-c/ABS-102.md"
run_reporter "$TEST_DIR/jira-c" "$TEST_DIR/back-c"
assert_eq "$?" 1 "exit 1 on missing mirror ticket"
assert_eq "$(json_get "next(e['mirror'] for e in d['divergences'] if e['field']=='presence')")" \
    "MISSING" "presence divergence names the missing side"

# --- 5. Comment-count difference ---------------------------------------------------
echo -e "\n${CYAN}[5] comment-count drift detected${NC}"
build_store "$TEST_DIR/jira-d"; build_store "$TEST_DIR/back-d"
write_ticket "$TEST_DIR/back-d" ABS-101 Doing 1        # one comment short
run_reporter "$TEST_DIR/jira-d" "$TEST_DIR/back-d"
assert_eq "$?" 1 "exit 1 on comment-count drift"
assert_eq "$(json_get "next(e['primary']+'/'+e['mirror'] for e in d['divergences'] if e['field']=='comment_count')")" \
    "2/1" "comment counts reported from both sides"

# --- 6. Read-only audit (AC 3) ------------------------------------------------------
echo -e "\n${CYAN}[6] read-only: only search/get ever reach an adapter${NC}"
assert_eq "$(grep -cv -E '^(search$|get )' "$TEST_DIR/calls.txt" | tr -d ' ')" 0 \
    "recorded adapter calls across ALL runs are search/get only"
# Source audit: no mutating verb is passed to $PRIMARY_CMD / $MIRROR_CMD.
assert_eq "$(grep -c -E '"\$(PRIMARY|MIRROR)_CMD" (create|update|comment|transition|link|assign)' "$REPORTER" | tr -d ' ')" 0 \
    "script source invokes no mutating adapter verb"
assert_true "$(grep -q 'X POST "\${JIRA_SITE%/}/rest/api/3/search/jql"' "$REPORTER"; echo $?)" \
    "the only HTTP call in the source is the read-only search/jql query"

# --- 7. Crash != divergence: an internal reporter failure exits 2, not 1 (ABS-364) --
echo -e "\n${CYAN}[7] reporter crash exits 2 (error), never 1 (divergence)${NC}"
build_store "$TEST_DIR/jira-e"; build_store "$TEST_DIR/back-e"
# Inject an uncaught exception in the report step via the self-test seam.
STUB_STORE_PRIMARY="$TEST_DIR/jira-e" STUB_STORE_MIRROR="$TEST_DIR/back-e" \
DIVERGENCE_PRIMARY_CMD="$TEST_DIR/primary-wrap.sh" \
DIVERGENCE_MIRROR_CMD="$TEST_DIR/mirror-wrap.sh" \
DIVERGENCE_STATE_DIR="$STATE_DIR" \
DIVERGENCE_WHITELIST="$TEST_DIR/no-whitelist.txt" \
DIVERGENCE_SELFTEST_RAISE=1 \
bash "$REPORTER" >"$TEST_DIR/out.txt" 2>"$TEST_DIR/err.txt"
assert_eq "$?" 2 "a reporter-internal failure exits 2 (error), NOT 1 (unexplained divergence)"
# And the three semantics are disjoint: 0 clean (test 1), 1 unexplained (test 2),
# 2 error (this test). Re-assert 0 and 1 hold with a clean vs. divergent run.
run_reporter "$TEST_DIR/jira-e" "$TEST_DIR/back-e"
assert_eq "$?" 0 "clean run still exits 0 (semantics intact)"
write_ticket "$TEST_DIR/back-e" ABS-101 Blocked 2
run_reporter "$TEST_DIR/jira-e" "$TEST_DIR/back-e"
assert_eq "$?" 1 "unexplained divergence still exits 1 (semantics intact)"

# --- 8. fixVersion sweep pages through >100 tickets (ABS-364) --------------------
echo -e "\n${CYAN}[8] fixVersion sweep is paged: a fence >100 tickets is fully enumerated${NC}"
# Build a 105-ticket fence (identical on both sides so the ONLY divergence per key
# is the fixVersion the paged sweep discovers). Keys ABS-201..ABS-305.
FENCE_P="$TEST_DIR/jira-f"; FENCE_M="$TEST_DIR/back-f"
mkdir -p "$FENCE_P" "$FENCE_M"
: > "$FENCE_P/search.tsv"
i=201
while [ "$i" -le 305 ]; do
    printf 'ABS-%s\tticket\tDoing\tTest ABS-%s\n' "$i" "$i" >> "$FENCE_P/search.tsv"
    write_ticket "$FENCE_P" "ABS-$i" Doing 0
    write_ticket "$FENCE_M" "ABS-$i" Doing 0
    i=$((i + 1))
done
# A curl shim standing in for Jira /search/jql: page 1 = first 100 keys + a
# nextPageToken; page 2 (payload carries nextPageToken) = the remaining 5, no
# token. Proves the reporter follows the token to a second page.
PAGE_SHIM="$TEST_DIR/curl-page-shim.sh"
cat > "$PAGE_SHIM" <<'SHIM'
#!/usr/bin/env python3
import sys, json
# Find the -d payload among argv (curl invocation from the reporter).
payload = ""
for i, a in enumerate(sys.argv):
    if a == "-d" and i + 1 < len(sys.argv):
        payload = sys.argv[i + 1]
body = {}
try:
    body = json.loads(payload)
except Exception:
    pass
def issue(n):
    return {"key": "ABS-%d" % n, "fields": {"fixVersions": [{"name": "v2.26.2"}]}}
if body.get("nextPageToken"):
    # Page 2: the final 5 keys, no further token.
    out = {"issues": [issue(n) for n in range(301, 306)]}
else:
    # Page 1: first 100 keys + a continuation token.
    out = {"issues": [issue(n) for n in range(201, 301)], "nextPageToken": "PAGE2"}
sys.stdout.write(json.dumps(out))
SHIM
chmod +x "$PAGE_SHIM"

STUB_STORE_PRIMARY="$FENCE_P" STUB_STORE_MIRROR="$FENCE_M" \
DIVERGENCE_PRIMARY_CMD="$TEST_DIR/primary-wrap.sh" \
DIVERGENCE_MIRROR_CMD="$TEST_DIR/mirror-wrap.sh" \
DIVERGENCE_STATE_DIR="$STATE_DIR" \
DIVERGENCE_WHITELIST="$TEST_DIR/no-whitelist.txt" \
DIVERGENCE_CURL="$PAGE_SHIM" \
JIRA_SITE="https://example.invalid" JIRA_EMAIL="t@example.invalid" \
JIRA_API_TOKEN="x" JIRA_PROJECT_KEY="ABS" \
bash "$REPORTER" >"$TEST_DIR/out.txt" 2>"$TEST_DIR/err.txt"
assert_eq "$(json_get "d['fixversion_swept']")" "True" "fixVersion sweep ran (env present)"
# Every one of the 105 fenced keys must carry a fixVersion divergence — i.e. the
# sweep enumerated BOTH pages. If page 2 were dropped, ABS-301..305 would be absent.
assert_eq "$(json_get "sum(1 for e in d['divergences'] if e['field']=='fixVersion')")" \
    "105" "all 105 keys across 2 pages carry a swept fixVersion (nothing truncated)"
assert_eq "$(json_get "any(e['key']=='ABS-305' and e['field']=='fixVersion' for e in d['divergences'])")" \
    "True" "a page-2 key (ABS-305) is present — pagination followed nextPageToken"

# --- Summary --------------------------------------------------------------------
echo ""
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL of $TOTAL assertions failed${NC} ($PASS passed)"
    exit 1
else
    echo -e "${GREEN}All $TOTAL assertions passed${NC}"
    exit 0
fi
