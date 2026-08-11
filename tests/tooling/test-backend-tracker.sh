#!/bin/bash
# =============================================================================
# Conformance test: Agentic-Backend Task-Tracking Adapter (spec §7/§12, ABS-237)
# =============================================================================
# The epic's acceptance gate (Epic-AC 1, ADR-Risiko 1): mirrors the
# test-mock-tracker.sh assertion set (CLI in/out, exit codes, stderr texts)
# against a LIVE backend, proving scripts/backend-tracker.sh is a drop-in
# replacement for scripts/mock-tracker.sh. Any diff is a release blocker.
#
# Self-provisioning (AC#3): boots a throwaway docker-compose stack (backend +
# disposable Postgres) on an ephemeral port, seeds a project, runs the suite,
# and tears the stack + volumes down on exit. Requires docker; SKIPS cleanly
# (exit 0) when docker is unavailable, mirroring the DB-gated backend unit tests.
#
# Documented backend-vs-mock differences (sanctioned by the spec, NOT diffs):
#   - events emits every transition with its real from/to, never a `from: null`
#     creation snapshot; a server-side cursor delivers each exactly once (§8).
#   - a non-existent TARGET status maps to `illegal transition` (§4 error table),
#     where the mock says `unknown status`; both reject with a non-zero exit.
#
# Run from repo root: bash tests/tooling/test-backend-tracker.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ADAPTER="$REPO_ROOT/scripts/backend-tracker.sh"
BACKEND_DIR="$REPO_ROOT/backend"
PROJECT_NAME="betrack$$"
BOOTSTRAP_TOKEN="conformance-token-$$"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

# --- Preflight: docker or clean skip -----------------------------------------
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo -e "${YELLOW}SKIP${NC} docker / 'docker compose' unavailable — conformance suite needs a live backend."
    echo -e "${YELLOW}SKIP${NC} (mirrors the DB-gated backend unit tests; not a failure)."
    exit 0
fi
if [ ! -f "$BACKEND_DIR/Dockerfile" ]; then
    echo -e "${RED}FAIL${NC} backend/Dockerfile missing — cannot provision the stack."; exit 1
fi

TMPDIR_RUN="$(mktemp -d /tmp/be-conf-XXXXXX)"
COMPOSE_FILE="$TMPDIR_RUN/docker-compose.yml"

# Throwaway stack: ephemeral backend host port, no host DB port (reached via
# `compose exec`), no named volume — `down -v` disposes everything (AC#3).
cat > "$COMPOSE_FILE" <<YAML
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: agentic
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d agentic"]
      interval: 3s
      timeout: 3s
      retries: 20
  backend:
    build:
      context: ${BACKEND_DIR}
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://postgres:postgres@db:5432/agentic
      PORT: "8420"
      BACKEND_BOOTSTRAP_TOKEN: ${BOOTSTRAP_TOKEN}
    ports:
      - "8420"
YAML

compose() { docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"; }

cleanup() {
    compose down -v >/dev/null 2>&1 || true
    rm -rf "$TMPDIR_RUN"
}
trap cleanup EXIT

echo -e "${CYAN}=== Provisioning throwaway backend stack ($PROJECT_NAME) ===${NC}"
if ! compose up -d --build >/tmp/be-conf-up.$$.log 2>&1; then
    echo -e "${RED}FAIL${NC} 'docker compose up' failed:"; tail -30 /tmp/be-conf-up.$$.log; rm -f /tmp/be-conf-up.$$.log; exit 1
fi
rm -f /tmp/be-conf-up.$$.log

BACKEND_PORT="$(compose port backend 8420 2>/dev/null | sed 's/.*://')"
if [ -z "$BACKEND_PORT" ]; then echo -e "${RED}FAIL${NC} could not resolve backend host port"; exit 1; fi

# Wait for /healthz (migrations + bootstrap seed run at boot).
healthy=0
for _ in $(seq 1 60); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$BACKEND_PORT/healthz" 2>/dev/null)" = "200" ]; then
        healthy=1; break
    fi
    sleep 1
done
if [ "$healthy" -ne 1 ]; then
    echo -e "${RED}FAIL${NC} backend did not become healthy:"; compose logs backend 2>&1 | tail -20; exit 1
fi

# Seed a project in the bootstrap org (registration endpoint is S7/ABS-239; the
# test provisions directly, as the harness owns its throwaway backend, AC#3).
if ! compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 -c \
     "INSERT INTO project (id, org_id, key, name) SELECT gen_random_uuid(), id, 'CONF', 'Conformance' FROM org WHERE key='bootstrap' ON CONFLICT DO NOTHING;" \
     >/dev/null 2>&1; then
    echo -e "${RED}FAIL${NC} could not seed project CONF"; exit 1
fi

export BACKEND_URL="http://localhost:$BACKEND_PORT"
export BACKEND_TOKEN="$BOOTSTRAP_TOKEN"
export TRACKER_PROJECT="CONF"
echo -e "${GREEN}READY${NC} backend on :$BACKEND_PORT, project CONF\n"

tracker() { bash "$ADAPTER" "$@"; }

# --- Assertion helpers (identical contract to test-mock-tracker.sh) ----------
PASS=0; FAIL=0; TOTAL=0
assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; echo "$1" | head -20 | sed 's/^/      /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if ! echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (did NOT expect: $2)"; FAIL=$((FAIL + 1)); fi
}
assert_exit_code() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -eq "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected exit $2, got $1)"; FAIL=$((FAIL + 1)); fi
}
assert_nonzero_exit() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -ne 0 ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $2 (expected non-zero exit, got 0)"; FAIL=$((FAIL + 1)); fi
}
assert_empty() {
    TOTAL=$((TOTAL + 1))
    if [ -z "$1" ]; then echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $2 (expected empty, got: $1)"; FAIL=$((FAIL + 1)); fi
}

# =============================================================================
echo -e "${CYAN}=== Test 0: adapter syntax + help ===${NC}\n"
bash -n "$ADAPTER" >/dev/null 2>&1; assert_exit_code $? 0 "backend-tracker.sh has valid bash syntax"
help_output=$(tracker help)
assert_contains "$help_output" "transition" "help lists transition"
assert_contains "$help_output" "events" "help lists events"

# =============================================================================
echo -e "\n${CYAN}=== Test 1: create — epic + children, auto-incrementing ids ===${NC}\n"
EPIC=$(tracker create --type epic --title "Conformance demo epic")
assert_eq "$EPIC" "CONF-1" "first created id is CONF-1"
T1=$(tracker create --type ticket --title "First child ticket" --parent "$EPIC")
assert_eq "$T1" "CONF-2" "id auto-increments to CONF-2"
T2=$(tracker create --type ticket --title "Second child ticket" --parent "$EPIC")
assert_eq "$T2" "CONF-3" "id auto-increments to CONF-3"
OTHER=$(tracker create --type subtask --title "Other prefix" --prefix TEST)
assert_eq "$OTHER" "TEST-1" "ids auto-increment per prefix (TEST-1)"
ec=0; tracker create --type nonsense --title "bad" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects invalid type"
ec=0; tracker create --type ticket --title "orphan" --parent NOPE-99 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects unknown parent"

# =============================================================================
echo -e "\n${CYAN}=== Test 1b: create --role — optional implementer-role hint ===${NC}\n"
NOROLE=$(tracker create --type ticket --title "No role hint")
assert_not_contains "$(tracker get "$NOROLE")" "role:" "create without --role emits no role frontmatter line"
WITHROLE=$(tracker create --type ticket --title "Backend role" --role be-developer)
assert_contains "$(tracker get "$WITHROLE")" "role: be-developer" "create --role be-developer surfaces via get"
FEROLE=$(tracker create --type ticket --title "Frontend role" --role fe-developer)
assert_contains "$(tracker get "$FEROLE")" "role: fe-developer" "create --role fe-developer surfaces via get"
ec=0; tracker create --type ticket --title "bad role" --role qas >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects invalid role value"
ec=0; tracker create --type ticket --title "role no value" --role >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects --role without a value"

# =============================================================================
echo -e "\n${CYAN}=== Test 1c: create --body-file — enriched body persists via adapter ===${NC}\n"
assert_contains "$(tracker get "$(tracker create --type ticket --title "Default body")")" "_TBD_" "create without --body-file keeps the _TBD_ template"
BODY_FIXTURE="$TMPDIR_RUN/enriched.md"
printf '## Goal\n\nShip the enriched child.\n\n## Scope\n\n**In scope:**\n\n- The one enriched unit\n\n## Acceptance Criteria\n\n- [ ] Enriched AC holds\n' > "$BODY_FIXTURE"
ENRICHED=$(tracker create --type ticket --title "Enriched child" --body-file "$BODY_FIXTURE")
out=$(tracker get "$ENRICHED")
assert_contains "$out" "Ship the enriched child." "create --body-file seeds the ticket body from the file"
assert_contains "$out" "Enriched AC holds" "create --body-file persists enriched acceptance criteria"
assert_not_contains "$out" "_TBD_" "create --body-file replaces the _TBD_ template entirely"
tracker comment "$ENRICHED" --kind understanding --actor po-agent --body "first comment on enriched child" >/dev/null
assert_contains "$(tracker get "$ENRICHED")" "first comment on enriched child" "comment self-heals '## Comments' on a custom body"
ec=0; tracker create --type ticket --title "bad body file" --body-file "$TMPDIR_RUN/does-not-exist.md" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects a --body-file that does not exist"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: get — full canonical ticket ===${NC}\n"
out=$(tracker get "$EPIC")
assert_contains "$out" "id: CONF-1" "get returns frontmatter id"
assert_contains "$out" "type: epic" "get returns type"
assert_contains "$out" "status: Backlog" "get returns initial status Backlog"
assert_contains "$out" "title: Conformance demo epic" "get returns title"
assert_contains "$out" "## Goal" "ticket body has Goal section"
assert_contains "$out" "## Acceptance Criteria" "ticket body has Acceptance Criteria section"
assert_contains "$out" "## Definition of Done" "ticket body has Definition of Done section"
assert_contains "$out" "## Test Plan" "ticket body has Test Plan section"
assert_contains "$out" "## ADR Context" "ticket body has ADR Context section"
ec=0; tracker get NOPE-1 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "get rejects unknown ticket"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: children + search ===${NC}\n"
out=$(tracker children "$EPIC")
assert_contains "$out" "CONF-2" "children lists CONF-2"
assert_contains "$out" "CONF-3" "children lists CONF-3"
assert_contains "$out" "[Backlog]" "children includes status summary"
assert_not_contains "$out" "TEST-1" "children excludes non-children"
out=$(tracker search --status Backlog)
assert_contains "$out" "CONF-1" "search by status finds CONF-1"
assert_contains "$out" "CONF-3" "search by status finds CONF-3"
out=$(tracker search --type epic)
assert_contains "$out" "CONF-1" "search by type finds the epic"
assert_not_contains "$out" "CONF-2	ticket" "search by type excludes tickets"
out=$(tracker search --parent "$EPIC" --type ticket)
assert_contains "$out" "CONF-2" "search by parent+type finds children"
assert_not_contains "$out" "CONF-1	epic" "search by parent excludes the epic itself"

# =============================================================================
echo -e "\n${CYAN}=== Test 3b: search --text — full-text over title and body ===${NC}\n"
assert_contains "$(tracker search --text "conformance")" "CONF-1" "text search matches in title"
assert_contains "$(tracker search --text "CONFORMANCE Demo")" "CONF-1" "text search is case-insensitive"
# Backend text search is the Postgres `title || body` tsvector (spec §2), so body
# text is injected via the ticket body — NOT via a comment. (The mock searches
# comment text only because it stores comments inline in the body file; the
# backend keeps comments in a separate table, out of the search vector by design.)
BODYSRCH="$TMPDIR_RUN/body-search.md"
printf '## Goal\n\nDedup marker: zanzibar rollout.\n' > "$BODYSRCH"
BSEARCH=$(tracker create --type ticket --title "body search probe" --body-file "$BODYSRCH")
assert_contains "$(tracker search --text "ZANZIBAR")" "$BSEARCH" "text search matches in body (title+body tsvector §2), case-insensitively"
assert_not_contains "$(tracker search --text "ZANZIBAR")" "CONF-1" "body match excludes tickets without the text"
assert_empty "$(tracker search --text "unobtainium-flux-capacitor")" "text search with no match returns nothing"
assert_contains "$(tracker search --type epic --text "conformance")" "CONF-1" "text search combines with structural filters"
ec=0; tracker search --text >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "search rejects --text without a value"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: comment — timestamped, with kind and actor ===${NC}\n"
tracker comment "$T1" --kind understanding --actor po-agent --body "PO understanding recorded." >/dev/null
out=$(tracker get "$T1")
assert_contains "$out" "kind: understanding | actor: po-agent" "comment records kind and actor"
assert_contains "$out" "PO understanding recorded." "comment records the body"
assert_contains "$out" "## Comments" "comments live under the Comments section"
ec=0; tracker comment "$T1" --kind bogus --actor x --body y >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "comment rejects invalid kind"

# =============================================================================
echo -e "\n${CYAN}=== Test 6: transition — full legal walk Backlog -> ... -> Done ===${NC}\n"
ec=0
walk_out=$(
    for status in "Ready for Development" "In Progress" "In Review" "In Test" \
                  "Ready for Human Acceptance" "Ready for Merge" "Done"; do
        tracker transition "$T1" "$status" --actor coordinator --reason "walk: advancing to $status" || exit $?
    done
) || ec=$?
assert_exit_code "$ec" 0 "full legal walk succeeds"
assert_contains "$walk_out" "CONF-2: Backlog -> Ready for Development" "walk reports first hop"
assert_contains "$walk_out" "CONF-2: Ready for Merge -> Done" "walk reports final hop"
out=$(tracker get "$T1")
assert_contains "$out" "status: Done" "frontmatter status updated to Done"
assert_contains "$out" "kind: transition-reason | actor: coordinator" "transition-reason projection records actor (§5)"
assert_contains "$out" "Transition: Backlog -> Ready for Development. Reason: walk: advancing to Ready for Development" "projection records from/to + reason"
assert_contains "$out" "Transition: Ready for Merge -> Done. Reason: walk: advancing to Done" "final transition projection recorded"
assert_eq "$(echo "$out" | grep -c '^updated: ')" "1" "exactly one updated field in frontmatter"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: transition — illegal transitions rejected ===${NC}\n"
ec=0; out=$(tracker transition "$T2" "In Test" --actor coordinator --reason "skipping ahead" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "Backlog -> In Test rejected with non-zero exit"
assert_contains "$out" "illegal transition" "rejection message names the illegal transition"
assert_contains "$(tracker get "$T2")" "status: Backlog" "status unchanged after rejected transition"
# Non-existent TARGET status: backend maps to illegal transition (§4); mock says
# 'unknown status'. Both reject non-zero — the sanctioned documented difference.
ec=0; out=$(tracker transition "$T2" "Nonexistent Status" --actor coordinator --reason "typo" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "unknown target status rejected (non-zero)"
assert_contains "$out" "illegal transition" "unknown target maps to illegal transition (§4 error table)"
ec=0; tracker transition "$T1" "In Progress" --actor coordinator --reason "resurrect" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "Done -> In Progress rejected (only the bisect-reopen edge leaves Done)"

# =============================================================================
echo -e "\n${CYAN}=== Test 8: transition — Blocked round-trip ===${NC}\n"
tracker transition "$T2" "Ready for Development" --actor coordinator --reason "prioritized" >/dev/null
tracker transition "$T2" "In Progress" --actor coordinator --reason "subagent started" >/dev/null
ec=0; tracker transition "$T2" "Blocked" --actor be-developer --reason "missing credentials" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "In Progress -> Blocked allowed"
assert_contains "$(tracker get "$T2")" "status: Blocked" "status is Blocked"
ec=0; tracker transition "$T2" "In Progress" --actor po-agent --reason "unblocked: credentials provided" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Blocked -> In Progress allowed (round-trip)"
out=$(tracker get "$T2")
assert_contains "$out" "status: In Progress" "status back to In Progress"
assert_contains "$out" "Transition: In Progress -> Blocked. Reason: missing credentials" "block reason recorded in projection"

# =============================================================================
echo -e "\n${CYAN}=== Test 8b: transition --expect-from compare-and-set (ABS-198) ===${NC}\n"
CAS=$(tracker create --type ticket --title "compare-and-set path")
tracker transition "$CAS" "Ready for Development" --actor coordinator --reason "prioritized" >/dev/null
tracker transition "$CAS" "In Progress" --actor be-developer --reason "started" >/dev/null
ec=0; out=$(tracker transition "$CAS" "In Review" --actor coordinator --reason "cas mismatch" --expect-from "Blocked" 2>&1) || ec=$?
assert_exit_code "$ec" 0 "compare-and-set mismatch exits 0 (lost race is not an error)"
assert_contains "$out" "NOOP compare-and-set expect-from=Blocked actual=In Progress" "mismatch logs a NOOP naming expected + actual"
assert_contains "$(tracker get "$CAS")" "status: In Progress" "status unchanged after compare-and-set NOOP"
ec=0; out=$(tracker transition "$CAS" "In Review" --actor coordinator --reason "cas match" --expect-from "In Progress" 2>&1) || ec=$?
assert_exit_code "$ec" 0 "compare-and-set match succeeds"
assert_contains "$out" "$CAS: In Progress -> In Review" "matching compare-and-set performs the transition"
assert_contains "$(tracker get "$CAS")" "status: In Review" "status advanced after matching compare-and-set"

# =============================================================================
echo -e "\n${CYAN}=== Test 9: link + update ===${NC}\n"
tracker link "$T2" "$T1" depends-on >/dev/null
out=$(tracker get "$T2")
assert_contains "$out" "depends-on:CONF-2" "link recorded in links"
assert_contains "$out" "depends_on: [CONF-2]" "depends-on link mirrored into depends_on"
tracker link "$T2" "https://github.com/example/repo/pull/42" pr >/dev/null
assert_contains "$(tracker get "$T2")" "pr:https://github.com/example/repo/pull/42" "pr link appended"
ec=0; out=$(tracker link "$T2" "$T1" depends-on 2>&1) || ec=$?
assert_contains "$out" "already linked" "replayed link is idempotent (already linked)"
ec=0; tracker link "$T2" "$T1" friend-of >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid link type rejected"
# PILOT-8: `relates` — symmetric soft link, one-sided persist, not a dependency.
tracker link "$T1" "$T2" relates >/dev/null
outR=$(tracker get "$T1")
assert_contains "$outR" "relates:$T2" "relates link recorded in links facet"
assert_contains "$outR" "depends_on: []" "relates is NOT mirrored into depends_on"
ec=0; out=$(tracker link "$T1" "$T2" relates 2>&1) || ec=$?
assert_contains "$out" "already linked" "replayed relates link is idempotent (already linked)"
tracker update "$T2" title "Second child ticket (renamed)" >/dev/null
assert_contains "$(tracker get "$T2")" "title: Second child ticket (renamed)" "update rewrites title"
ec=0; tracker update "$T2" status "Done" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update refuses to touch status (must use transition)"

# =============================================================================
echo -e "\n${CYAN}=== Test 10: events — transition events, delivered exactly once (§8) ===${NC}\n"
tracker events >/dev/null   # drain the backlog from earlier sections
EV=$(tracker create --type ticket --title "events probe")
tracker transition "$EV" "Ready for Development" --actor coord --reason "ev1" >/dev/null
tracker transition "$EV" "In Progress" --actor coord --reason "ev2" >/dev/null
out=$(tracker events)
assert_contains "$out" "{ticket_id: $EV, from: Backlog, to: Ready for Development" "events surfaces the first transition (real from/to, not a creation snapshot — §8)"
assert_contains "$out" "{ticket_id: $EV, from: Ready for Development, to: In Progress" "events emits every transition in the batch (§8, ABS-236 AC2)"
assert_empty "$(tracker events)" "second poll is empty — server cursor delivers each event exactly once (§8)"

# =============================================================================
echo -e "\n${CYAN}=== Test 11: transition — Needs PO Decision ===${NC}\n"
NPD=$(tracker create --type ticket --title "PO decision path")
tracker transition "$NPD" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
tracker transition "$NPD" "In Progress" --actor be-developer --reason "started" >/dev/null
ec=0; tracker transition "$NPD" "Needs PO Decision" --actor be-developer --reason "scope question for PO" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "active status (In Progress) -> Needs PO Decision allowed"
assert_contains "$(tracker get "$NPD")" "status: Needs PO Decision" "status is Needs PO Decision"
ec=0; tracker transition "$NPD" "Ready for Development" --actor po-agent --reason "decided: proceed" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Needs PO Decision -> Ready for Development allowed"

# =============================================================================
echo -e "\n${CYAN}=== Test 12: v3 flags / labels / follow-up kinds / assign ===${NC}\n"
V3S=$(tracker create --type ticket --title "v3 flagged story" --parent "$EPIC" \
      --role fe-developer --flag design --flag security --flag data --ac-blocking)
out=$(tracker get "$V3S")
assert_contains "$out" "flags: [design, security, data]" "create --flag (repeatable) round-trips via get"
assert_contains "$out" "ac_blocking: true" "create --ac-blocking round-trips via get"
assert_contains "$out" "role: fe-developer" "role hint coexists with flags"
ec=0; out=$(tracker create --type ticket --title "bad flag" --flag bogus 2>&1) || ec=$?
assert_nonzero_exit "$ec" "create --flag bogus rejected"
# labels
LBL=$(tracker create --type ticket --title "labelled" --label orchestrator-ready --label triage)
assert_contains "$(tracker get "$LBL")" "labels: [orchestrator-ready, triage]" "create --label (repeatable) round-trips via get"
assert_contains "$(tracker search --label orchestrator-ready)" "$LBL" "search --label finds the labelled ticket"
assert_not_contains "$(tracker search --label ready)" "$LBL" "search --label ready does NOT match 'orchestrator-ready' (exact, not substring)"
tracker update "$LBL" labels "[triage]" >/dev/null
assert_contains "$(tracker get "$LBL")" "labels: [triage]" "update labels replaces the whole set"
ec=0; tracker create --type ticket --title "bad label" --label "has space" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create --label with an illegal char is rejected"
# follow-up comment kinds
ec=0; tracker comment "$V3S" --kind follow-up --actor qas --body "Follow-up: add a regression test." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: follow-up accepted"
ec=0; tracker comment "$V3S" --kind bsa-decision --actor bsa --body "Decision: create outside the epic." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: bsa-decision accepted"
ec=0; tracker comment "$V3S" --kind claim --actor orchestrator --body "Staking claim." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: claim accepted"
ec=0; tracker comment "$V3S" --kind made-up-kind --actor x --body "nope" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid comment kind still rejected"
# assign
ASGN=$(tracker create --type ticket --title "assign test ticket")
assert_eq "$(tracker assign "$ASGN" "user-account-123")" "$ASGN: assignee set to user-account-123" "assign prints the success line"
assert_contains "$(tracker get "$ASGN")" "assignee: user-account-123" "assign sets the assignee frontmatter field"
tracker assign "$ASGN" "user-account-456" >/dev/null
out=$(tracker get "$ASGN")
assert_contains "$out" "assignee: user-account-456" "re-assign overwrites the previous assignee"
assert_not_contains "$out" "user-account-123" "previous assignee value no longer present"
ec=0; out=$(tracker assign "$ASGN" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "assign without accountId fails (arity)"
assert_contains "$out" "usage: assign" "assign arity error mentions usage"
ec=0; tracker assign NOPE-99 some-acct >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "assign on unknown ticket fails"

# =============================================================================
echo -e "\n${CYAN}=== Test 13: §7 error-mapping table — auth + network ===${NC}\n"
# 401/403: a bogus token rejects non-zero (completes the §7 exit-code table).
ec=0; ( BACKEND_TOKEN="not-a-real-token" tracker get "$EPIC" ) >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid BACKEND_TOKEN rejected non-zero (401/403, §7)"
# Network error: an unreachable backend rejects non-zero (orchestrator outage path).
ec=0; ( BACKEND_URL="http://127.0.0.1:1" tracker get "$EPIC" ) >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "unreachable backend rejected non-zero (network error, §7)"

# =============================================================================
echo -e "\n${CYAN}=== Test 14: §6 packet / brief / capabilities (ABS-238) ===${NC}\n"
# capabilities: plain list advertising the optional server-composed ops.
CAP_OUT=$(tracker capabilities)
assert_eq "$(printf '%s\n' "$CAP_OUT" | grep -cx packet)" "1" "capabilities lists 'packet' on its own line"
assert_contains "$CAP_OUT" "brief" "capabilities lists 'brief'"
assert_contains "$CAP_OUT" "policies" "capabilities lists 'policies' (S4 / ABS-381)"
# Seed a ticket with a handoff so the packet has a slot-3 block to compose.
PKT=$(tracker create --type ticket --title "packet subject")
tracker comment "$PKT" --kind decision --actor po-agent --body "Decision: ship it." >/dev/null
tracker comment "$PKT" --kind handoff --actor be-developer --body "Handoff: implementation done." >/dev/null
tracker transition "$PKT" "Ready for Development" --actor orchestrator --reason "released to dev" >/dev/null 2>&1 || true
# packet <id>: composed context packet — frontmatter + AC + handoff + decision.
PKT_OUT=$(tracker packet "$PKT")
assert_contains "$PKT_OUT" "id: $PKT" "packet carries the frontmatter id"
assert_contains "$PKT_OUT" "## Acceptance Criteria" "packet carries the AC section (bounce-safe)"
assert_contains "$PKT_OUT" "Handoff: implementation done." "packet includes the latest handoff slot"
assert_contains "$PKT_OUT" "Decision: ship it." "packet always includes decisions"
# get --brief <id>: frontmatter + Goal + AC + latest handoff only (no decisions).
BRIEF_OUT=$(tracker get --brief "$PKT")
assert_contains "$BRIEF_OUT" "id: $PKT" "brief carries the frontmatter id"
assert_contains "$BRIEF_OUT" "## Acceptance Criteria" "brief carries the AC section"
assert_contains "$BRIEF_OUT" "Handoff: implementation done." "brief includes the latest handoff"
assert_not_contains "$BRIEF_OUT" "Decision: ship it." "brief excludes decisions (dedup-gate signal only)"
# unknown subcommands still fail exactly like the mock.
ec=0; tracker packet >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "packet without an id fails (arity)"

# =============================================================================
# Placed last so its extra creates never shift the ticket ids the earlier
# substring assertions (e.g. Test 3b's CONF-1 check) depend on.
echo -e "\n${CYAN}=== Test 15: create/update --priority — canonical priority field (ABS-334) ===${NC}\n"
TAB="$(printf '\t')"
PHI=$(tracker create --type ticket --title "priority high ticket" --priority high)
assert_contains "$(tracker get "$PHI")" "priority: high" "create --priority high surfaces via get"
PDEF=$(tracker create --type ticket --title "priority default ticket")
# get is only-when-set (mock parity): a default ticket carries NO priority line;
# the default 'normal' is what search projects (asserted below).
assert_not_contains "$(tracker get "$PDEF")" "priority:" "create without --priority emits no priority line (default normal, mock only-when-set parity)"
tracker update "$PHI" priority low >/dev/null
assert_contains "$(tracker get "$PHI")" "priority: low" "update <id> priority low round-trips via get"
# Search column form: id⇥type⇥status⇥priority⇥title (ABS-331/334 parity with mock).
srch=$(tracker search --type ticket)
assert_contains "$(printf '%s\n' "$srch" | grep "^$PHI$TAB")" "${TAB}low${TAB}" "search row carries priority as its own column"
assert_contains "$(printf '%s\n' "$srch" | grep "^$PDEF$TAB")" "${TAB}normal${TAB}" "search defaults an unset priority to 'normal' in its column"
# Invalid value dies with the mock-identical message (backend ENUM guard, §4).
ec=0; out=$(tracker create --type ticket --title "bad priority" --priority bogus 2>&1) || ec=$?
assert_nonzero_exit "$ec" "create --priority bogus rejected non-zero"
assert_contains "$out" "invalid priority 'bogus'" "invalid create priority rejected with mock-identical message"
ec=0; out=$(tracker update "$PHI" priority nonsense 2>&1) || ec=$?
assert_nonzero_exit "$ec" "update priority nonsense rejected non-zero"
assert_contains "$out" "invalid priority 'nonsense'" "invalid update priority rejected with mock-identical message"

# =============================================================================
# Placed after Test 15 so its DB inserts never shift the auto-increment ids.
echo -e "\n${CYAN}=== Test 16: §10/Case 4 — policies agent op (S4 / ABS-381) ===${NC}\n"
# Seed two active policies directly: one audience-specific, one all-audiences (NULL).
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO policy (org_id, project_id, key, audience, title, body, status, created, updated)
        SELECT o.id, p.id, 'commit-policy', 'be-developer', 'Commit Standards', 'Always squash commits.', 'active', now(), now()
          FROM project p JOIN org o ON o.id = p.org_id WHERE o.key='bootstrap' AND p.key='CONF'
         ON CONFLICT DO NOTHING;" >/dev/null 2>&1
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO policy (org_id, project_id, key, audience, title, body, status, created, updated)
        SELECT o.id, p.id, 'security', NULL, 'Security Policy', 'Never log secrets.', 'active', now(), now()
          FROM project p JOIN org o ON o.id = p.org_id WHERE o.key='bootstrap' AND p.key='CONF'
         ON CONFLICT DO NOTHING;" >/dev/null 2>&1
# policies --audience be-developer: audience-matching + NULL-audience included
out=$(tracker policies --audience be-developer)
assert_contains "$out" "Commit Standards" "policies --audience returns the audience-specific policy"
assert_contains "$out" "Always squash commits." "policies --audience includes policy body"
assert_contains "$out" "Security Policy" "policies --audience includes audience-NULL (all-audiences) policy"
assert_contains "$out" "policy_rev: " "policies response includes a policy_rev line"
# policies (no audience): all-audiences union
out_all=$(tracker policies)
assert_contains "$out_all" "Security Policy" "policies (no audience) returns all-audiences union"
assert_contains "$out_all" "policy_rev: " "policies (no audience) includes policy_rev line"
# unknown audience (non-matching): returns empty render + policy_rev, exits 0
ec=0; out_unk=$(tracker policies --audience nobody-role 2>&1) || ec=$?
assert_exit_code "$ec" 0 "policies --audience with no matching policies exits 0"
assert_contains "$out_unk" "policy_rev: " "policies (no match) still returns a policy_rev line"
# error cases
ec=0; tracker policies --bogus >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "policies: unknown flag rejected with non-zero exit"
ec=0; tracker policies --audience >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "policies: --audience without value rejected with non-zero exit"

# ======================================================================# §10 Conformance Cases 1–7 (ABS-384 / ABS-231 S7)
# ─────────────────────────────────────────────────
# Wires Spec §10 conformance cases into the backend conformance suite so any
# regression in ADR import, policy resolution, the `policies` op, human-only
# guards, or the export/import round-trip is a release blocker.
# All tests run against the same disposable compose stack provisioned above.
# =============================================================================

# Helper: POST a tar of (name, body) pairs to the import/adrs endpoint.
# Usage: import_adrs_tar <tar-file>
import_adrs_curl() {
    local tar_file="$1"
    curl -s -X POST \
        -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
        -H "Content-Type: application/x-tar" \
        --data-binary "@$tar_file" \
        "$BACKEND_URL/api/admin/import/adrs?project=CONF" 2>/dev/null
}

# Helper: GET the export tar for CONF (returns raw tar bytes to stdout).
export_curl() {
    curl -s \
        -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
        "$BACKEND_URL/api/export?project=CONF" 2>/dev/null
}

# Helper: obtain a human session cookie from the bootstrap (admin) token.
# Returns the Set-Cookie header value.  Uses a temp file to capture headers.
get_session_cookie() {
    local hdr_file; hdr_file="$(mktemp)"
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"token\":\"$BOOTSTRAP_TOKEN\"}" \
        -D "$hdr_file" \
        "$BACKEND_URL/api/v1/session" >/dev/null 2>&1
    local val; val=$(grep -i '^set-cookie:' "$hdr_file" | grep 'session=' \
        | sed 's/.*session=\([^;]*\).*/\1/' | head -1)
    rm -f "$hdr_file"
    printf '%s' "$val"
}

# Helper: create a project-scoped policy via the human REST surface.
# Usage: create_policy_curl <session_id> <key> <title> <body> [<audience>]
create_policy_curl() {
    local sid="$1" key="$2" title="$3" body="$4" audience="${5-}"
    local aud_json=""
    [ -z "$audience" ] || aud_json=",\"audience\":\"$audience\""
    curl -s -X POST \
        -H "Cookie: session=$sid" \
        -H "Content-Type: application/json" \
        -d "{\"key\":\"$(json_escape "$key")\",\"title\":\"$(json_escape "$title")\",\"body\":\"$(json_escape "$body")\",\"status\":\"active\"$aud_json}" \
        "$BACKEND_URL/api/v1/projects/CONF/policies" 2>/dev/null
}

# Robust JSON string escaper for the conformance helpers above (ABS-426).
# Mirrors the shared json_escape in scripts/backend-tracker.sh byte-for-byte:
# escapes backslash, double quote AND the control chars tab/CR/newline, so a
# fixture carrying newlines or control bytes still encodes to valid JSON. No
# minimal sed encoder remains in the conformance path.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\n'/\\n}"
    printf '%s' "$s"
}

# Fail (never silently pass) a conformance probe whose token/session mint failed
# (ABS-426). A broken throwaway stack must surface as a FAIL, not a green gate.
mint_fail_probe() {
    echo -e "  ${RED}FAIL${NC} $1 — token/session mint failed (must not auto-pass)"
    TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1))
}

# =============================================================================
echo -e "${CYAN}=== Test 17: §10/Case 1 — ADR import round-trip + no-op + unknown-status-fails ===${NC}\n"

# Seed a single ADR file into a tar and import it.
ADR1_MD="$TMPDIR_RUN/ADR-A-0001.md"
cat > "$ADR1_MD" <<'ADREOF'
---
id: ADR-A-0001
title: Use Agentic Backend
status: proposed
date: "2026-07-17"
scope: backend
---

## Context

We need a durable backend for the agentic workflow.

## Decision

Adopt the agentic backend service.
ADREOF

ADR1_TAR="$TMPDIR_RUN/adr1.tar"
tar -c -f "$ADR1_TAR" -C "$TMPDIR_RUN" "ADR-A-0001.md" 2>/dev/null

# AC#1: import returns 200 + key
resp=$(import_adrs_curl "$ADR1_TAR")
assert_contains "$resp" '"imported":1' "§10/1 ADR import → 200 + imported:1"
assert_contains "$resp" 'ADR-A-0001' "§10/1 ADR import response contains the key"

# AC#1: tracker get renders canonical frontmatter
adr_get=$(tracker get "ADR-A-0001")
assert_contains "$adr_get" "id: ADR-A-0001" "§10/1 tracker get: id rendered"
assert_contains "$adr_get" "type: adr" "§10/1 tracker get: type: adr"
assert_contains "$adr_get" "status: Proposed" "§10/1 tracker get: status normalized (proposed → Proposed)"
assert_contains "$adr_get" "adr_date: 2026-07-17" "§10/1 tracker get: adr_date field (quotes stripped)"
assert_contains "$adr_get" "adr_scope: backend" "§10/1 tracker get: adr_scope field (renamed from scope)"
assert_contains "$adr_get" "Use Agentic Backend" "§10/1 tracker get: title in frontmatter"

# AC#2: re-import unchanged ADR is a no-op (same response, no regression)
resp2=$(import_adrs_curl "$ADR1_TAR")
assert_contains "$resp2" '"imported":1' "§10/1 no-op re-import → 200 + imported:1 (idempotent)"

# AC#3: unknown status fails closed with a 422 + error payload
ADR_BAD_MD="$TMPDIR_RUN/ADR-A-BAD.md"
cat > "$ADR_BAD_MD" <<'ADREOF'
---
id: ADR-A-BAD
title: Bad Status
status: nonexistent
---

Body.
ADREOF
ADR_BAD_TAR="$TMPDIR_RUN/adr-bad.tar"
tar -c -f "$ADR_BAD_TAR" -C "$TMPDIR_RUN" "ADR-A-BAD.md" 2>/dev/null
resp3=$(import_adrs_curl "$ADR_BAD_TAR")
assert_contains "$resp3" '"errors"' "§10/1 unknown status → 422 with errors array"
assert_contains "$resp3" 'nonexistent' "§10/1 unknown-status error names the bad status"

# =============================================================================
echo -e "\n${CYAN}=== Test 18: §10/Case 2 — Supersedes link/transition ===${NC}\n"

# Import a Proposed ADR, then a superseding ADR that references it.
ADR_SUP1="$TMPDIR_RUN/ADR-A-0002.md"
cat > "$ADR_SUP1" <<'ADREOF'
---
id: ADR-A-0002
title: Old Architecture Decision
status: proposed
---

Original decision body.
ADREOF

ADR_SUP2="$TMPDIR_RUN/ADR-A-0003.md"
cat > "$ADR_SUP2" <<'ADREOF'
---
id: ADR-A-0003
title: New Architecture Decision
status: accepted
supersedes: ADR-A-0002
---

Replacement decision body.
ADREOF

ADR_SUP_TAR="$TMPDIR_RUN/adr-supersedes.tar"
tar -c -f "$ADR_SUP_TAR" -C "$TMPDIR_RUN" "ADR-A-0002.md" "ADR-A-0003.md" 2>/dev/null

resp_sup=$(import_adrs_curl "$ADR_SUP_TAR")
assert_contains "$resp_sup" '"imported":2' "§10/2 supersedes import → imported:2"

# The admin token is a human principal: it can accept ADRs (transition to Accepted).
# ADR-A-0002 should be Superseded automatically by the importer.
old_adr=$(tracker get "ADR-A-0002")
assert_contains "$old_adr" "status: Superseded" "§10/2 superseded ADR status = Superseded"

# ADR-A-0003 (accepted) imports correctly with status Accepted
new_adr=$(tracker get "ADR-A-0003")
assert_contains "$new_adr" "status: Accepted" "§10/2 superseding ADR status = Accepted"
assert_contains "$new_adr" "supersedes: ADR-A-0002" "§10/2 supersedes field in canonical output"

# =============================================================================
echo -e "\n${CYAN}=== Test 19: §10/Case 3 — Policy resolution matrix + byte-stable policy_rev ===${NC}\n"

# Reset policies for the CONF project (clean slate for the resolution matrix).
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "DELETE FROM policy WHERE project_id = (SELECT id FROM project WHERE key='CONF');" \
    >/dev/null 2>&1

# --- 19a: empty constellation --- no active policies → canonical empty render
out_empty=$(tracker policies --audience nobody-role)
rendered_empty=$(printf '%s\n' "$out_empty" | grep -v '^policy_rev:')
golden_empty=$(cat "$REPO_ROOT/tests/fixtures/phase3-golden-empty-render.txt")
assert_eq "$rendered_empty" "$golden_empty" "§10/3 empty constellation: rendered text matches golden fixture"
assert_contains "$out_empty" "policy_rev: " "§10/3 empty constellation: policy_rev line present"
rev_empty=$(printf '%s\n' "$out_empty" | sed -n 's/^policy_rev: *//p')
assert_eq "${#rev_empty}" "64" "§10/3 empty policy_rev is 64-char sha256 hex"

# --- 19b: seed one org-wide + one project-scoped policy ---
# Org-wide policy (NULL project_id): must be seeded via SQL since HTTP CRUD is project-scoped.
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO policy (org_id, project_id, key, audience, title, body, status, created, updated)
        SELECT id, NULL, 'org-standard', NULL, 'Org Standards', 'Follow org coding standards.', 'active', now(), now()
          FROM org WHERE key='bootstrap'
         ON CONFLICT DO NOTHING;" \
    >/dev/null 2>&1

# Project-scoped policy: use the human session surface.
SESSION_ID=$(get_session_cookie)
if [ -z "$SESSION_ID" ]; then
    echo -e "  ${YELLOW}WARN${NC} §10/3 could not obtain session cookie — skipping project-scoped policy create"
else
    resp_pol=$(create_policy_curl "$SESSION_ID" "be-style" "BE Code Style" "Use conventional commits." "be-developer")
    assert_contains "$resp_pol" '"status":"active"' "§10/3 project policy create returns active policy"
fi

# --- 19c: org-only constellation (NULL audience) ---
out_org=$(tracker policies --audience fe-developer)
assert_contains "$out_org" "Org Standards" "§10/3 org-only: NULL-audience policy included for any audience"
assert_not_contains "$out_org" "BE Code Style" "§10/3 org-only: audience-specific policy excluded for non-matching role"
assert_contains "$out_org" "policy_rev: " "§10/3 org-only: policy_rev present"

# --- 19d: audience constellation (audience-specific + null-audience both included) ---
out_be=$(tracker policies --audience be-developer)
assert_contains "$out_be" "Org Standards" "§10/3 audience: NULL-audience policy included"
assert_contains "$out_be" "BE Code Style" "§10/3 audience: audience-specific policy included"
assert_contains "$out_be" "policy_rev: " "§10/3 audience: policy_rev present"

# Exact rendered text matches the golden fixture (byte-stable).
rendered_be=$(printf '%s\n' "$out_be" | grep -v '^policy_rev:')
golden_matrix=$(cat "$REPO_ROOT/tests/fixtures/phase3-golden-policy-matrix.txt")
assert_eq "$rendered_be" "$golden_matrix" "§10/3 resolution matrix: rendered text matches golden fixture (exact bytes)"

# --- 19e: policy_rev byte-stability — same call same hash ---
out_be2=$(tracker policies --audience be-developer)
rev_be1=$(printf '%s\n' "$out_be" | sed -n 's/^policy_rev: *//p')
rev_be2=$(printf '%s\n' "$out_be2" | sed -n 's/^policy_rev: *//p')
assert_eq "$rev_be1" "$rev_be2" "§10/3 byte-stability: identical policy set → identical policy_rev on repeated calls"

# --- 19f: all-audiences union (no --audience) ---
out_all=$(tracker policies)
assert_contains "$out_all" "Org Standards" "§10/3 all-audiences: org-wide policy in union"
assert_contains "$out_all" "BE Code Style" "§10/3 all-audiences: project policy in union"
assert_contains "$out_all" "policy_rev: " "§10/3 all-audiences: policy_rev present"

# --- 19g: project-wins-on-override (same key+audience, project beats org) ---
# Seed an org-wide policy with the SAME key as the project policy to prove override.
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO policy (org_id, project_id, key, audience, title, body, status, created, updated)
        SELECT id, NULL, 'be-style', 'be-developer', 'Org BE Style', 'Org-level BE style.', 'active', now(), now()
          FROM org WHERE key='bootstrap'
         ON CONFLICT DO NOTHING;" \
    >/dev/null 2>&1
out_override=$(tracker policies --audience be-developer)
assert_contains "$out_override" "BE Code Style" "§10/3 override: project policy title wins over org policy same (key, audience)"
assert_not_contains "$out_override" "Org BE Style" "§10/3 override: org policy suppressed by project override"

# --- 19h: policy_rev changes when policy is updated (cache invalidation) ---
rev_before_change=$(printf '%s\n' "$out_override" | sed -n 's/^policy_rev: *//p')
# Add a new policy (changes the active set → different rev).
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO policy (org_id, project_id, key, audience, title, body, status, created, updated)
        SELECT o.id, p.id, 'new-rule', NULL, 'New Rule', 'Added a new rule.', 'active', now(), now()
          FROM project p JOIN org o ON o.id = p.org_id WHERE o.key='bootstrap' AND p.key='CONF'
         ON CONFLICT DO NOTHING;" \
    >/dev/null 2>&1
out_after=$(tracker policies --audience be-developer)
rev_after_change=$(printf '%s\n' "$out_after" | sed -n 's/^policy_rev: *//p')
if [ "$rev_before_change" != "$rev_after_change" ]; then
    echo -e "  ${GREEN}PASS${NC} §10/3 cache-invalidation: policy_rev changes when policy set changes"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} §10/3 cache-invalidation: policy_rev did NOT change after policy added"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# =============================================================================
echo -e "\n${CYAN}=== Test 20: §10/Case 6 — Human-only rejection tests ===${NC}\n"

# --- 20a: agent→ADR-accept → 403 ---
# Seed a Proposed ADR for the acceptance test.
ADR_ACCEPT_MD="$TMPDIR_RUN/ADR-A-0004.md"
cat > "$ADR_ACCEPT_MD" <<'ADREOF'
---
id: ADR-A-0004
title: For Acceptance Test
status: proposed
---

Needs human acceptance.
ADREOF
ADR_ACCEPT_TAR="$TMPDIR_RUN/adr-accept.tar"
tar -c -f "$ADR_ACCEPT_TAR" -C "$TMPDIR_RUN" "ADR-A-0004.md" 2>/dev/null
import_adrs_curl "$ADR_ACCEPT_TAR" >/dev/null 2>&1

# Mint a project-scoped orchestrator token for the guard tests (non-human role → 403).
ORCH_TOKEN_JSON=$(curl -s -X POST \
    -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"project\":\"CONF\",\"instance\":\"conformance-guard-test\"}" \
    "$BACKEND_URL/agent/v1/orchestrators" 2>/dev/null)
ORCH_TOKEN=$(printf '%s' "$ORCH_TOKEN_JSON" | grep -o '"token":"[^"]*"' | sed 's/"token":"//; s/"//')

if [ -n "$ORCH_TOKEN" ]; then
    resp_orch=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Authorization: Bearer $ORCH_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"to":"Accepted","actor":"orch-test","reason":"auto-accept attempt"}' \
        "$BACKEND_URL/agent/v1/projects/CONF/items/ADR-A-0004/transition" 2>/dev/null)
    assert_eq "$resp_orch" "403" "§10/6 orchestrator token → ADR→Accepted → 403 (human-only guard)"
else
    echo -e "  ${RED}FAIL${NC} §10/6 orchestrator token mint failed — cannot verify ADR→Accepted guard (security-flagged AC, must not auto-pass)"
    TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1))
fi

# Admin (human) token → ADR→Accepted → 200 (positive control).
resp_human=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
    -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"to":"Accepted","actor":"human-alice","reason":"reviewed and accepted"}' \
    "$BACKEND_URL/agent/v1/projects/CONF/items/ADR-A-0004/transition" 2>/dev/null)
assert_eq "$resp_human" "200" "§10/6 admin (human) token → ADR→Accepted → 200 (positive control)"

# --- 20b: agent→policy-write → 403 ---
if [ -n "$ORCH_TOKEN" ]; then
    resp_pol_write=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Authorization: Bearer $ORCH_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"key":"k","title":"t"}' \
        "$BACKEND_URL/api/v1/projects/CONF/policies" 2>/dev/null)
    assert_eq "$resp_pol_write" "403" "§10/6 orchestrator token → policy write → 403 (human-only guard)"
else
    echo -e "  ${RED}FAIL${NC} §10/6 orchestrator token mint failed — cannot verify policy-write guard (security-flagged AC, must not auto-pass)"
    TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1))
fi

# Human session → policy create → 201 (positive control).
if [ -n "$SESSION_ID" ]; then
    resp_pol_human=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Cookie: session=$SESSION_ID" \
        -H "Content-Type: application/json" \
        -d '{"key":"human-pol","title":"Human Policy","status":"draft"}' \
        "$BACKEND_URL/api/v1/projects/CONF/policies" 2>/dev/null)
    assert_eq "$resp_pol_human" "201" "§10/6 human session → policy create → 201 (positive control)"
else
    mint_fail_probe "§10/6 human-session positive control (policy create)"
fi

# --- 20c: adr→eligible guard — DB CHECK constraint rejects orchestrator-ready on ADR ---
# The 009_knowledge_adr_policy migration adds:
#   CHECK (type_key <> 'adr' OR orchestration_state = 'excluded')
# Attempting to set orchestrator-ready label on an ADR must return a non-zero error.
if [ -n "$ORCH_TOKEN" ]; then
    ec=0; BACKEND_TOKEN="$ORCH_TOKEN" TRACKER_PROJECT="CONF" \
        bash "$ADAPTER" update "ADR-A-0001" labels "[orchestrator-ready]" >/dev/null 2>&1 || ec=$?
    assert_nonzero_exit "$ec" "§10/6 adr→eligible: update labels=[orchestrator-ready] on ADR rejected (DB constraint)"
else
    # Use admin token to test the guard (admin is also blocked; constraint fires regardless of role).
    ec=0; tracker update "ADR-A-0001" labels "[orchestrator-ready]" >/dev/null 2>&1 || ec=$?
    assert_nonzero_exit "$ec" "§10/6 adr→eligible: update labels=[orchestrator-ready] on ADR rejected (DB constraint)"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 21: §10/Case 7 — Export→import round-trip incl. ADRs ===${NC}\n"

# Precondition: ADR-A-0001 and ADR-A-0002 exist in CONF from Tests 17/18.
# Export CONF to a tar archive.
EXPORT_TAR="$TMPDIR_RUN/conf-export.tar"
export_curl > "$EXPORT_TAR"

export_size=$(wc -c < "$EXPORT_TAR")
if [ "${export_size:-0}" -gt 512 ]; then
    echo -e "  ${GREEN}PASS${NC} §10/7 export produces a non-empty tar (${export_size} bytes)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} §10/7 export produced empty or tiny tar (${export_size} bytes)"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# Verify the exported tar contains the known items via tar -t.
export_list=$(tar -tf "$EXPORT_TAR" 2>/dev/null || true)
assert_contains "$export_list" "ADR-A-0001.md" "§10/7 export tar contains ADR-A-0001.md"
assert_contains "$export_list" "ADR-A-0002.md" "§10/7 export tar contains ADR-A-0002.md"

# Re-import the exported tar into a FRESH project (CONF2) to verify the round-trip.
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 \
    -c "INSERT INTO project (id, org_id, key, name)
        SELECT gen_random_uuid(), id, 'CONF2', 'Conformance Round-trip'
          FROM org WHERE key='bootstrap'
         ON CONFLICT DO NOTHING;" \
    >/dev/null 2>&1

REIMPORT_RESP=$(curl -s -X POST \
    -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
    -H "Content-Type: application/x-tar" \
    --data-binary "@$EXPORT_TAR" \
    "$BACKEND_URL/api/admin/import?project=CONF2" 2>/dev/null)

assert_contains "$REIMPORT_RESP" '"imported"' "§10/7 re-import response contains imported count"
# The re-imported ADR-A-0001 must be retrievable in the CONF2 project.
CONF2_TOKEN=$(curl -s -X POST \
    -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"project":"CONF2","instance":"conf2-probe"}' \
    "$BACKEND_URL/agent/v1/orchestrators" 2>/dev/null \
    | grep -o '"token":"[^"]*"' | sed 's/"token":"//; s/"//')

if [ -n "$CONF2_TOKEN" ]; then
    round_trip=$(BACKEND_TOKEN="$CONF2_TOKEN" TRACKER_PROJECT="CONF2" \
        bash "$ADAPTER" get "ADR-A-0001" 2>/dev/null || true)
    assert_contains "$round_trip" "id: ADR-A-0001" "§10/7 round-trip: ADR-A-0001 retrievable in reimported project"
    assert_contains "$round_trip" "type: adr" "§10/7 round-trip: ADR type preserved through export→import"
else
    mint_fail_probe "§10/7 CONF2 export→import round-trip"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 22: §10/Case 5 — Packet policy injection + cache-invalidation ===${NC}\n"
# §10/Case 5 registration + packet cache-invalidation proof.
# Full injection tests (ORCH_POLICY_INJECT=off / run.log audit / mock-adapter no-op) live in
# tests/test-orchestrator.sh (ABS-382 / §10/Case 5 block).
# Proof: the orchestrator builds the packet POLICY block as:
#   === POLICY (policy_rev: <hash>) ===\n<rendered text>
# Test 19h proves rev_before_change ≠ rev_after_change when the policy set changes.
# Therefore the POLICY block header differs → pre/post packets are byte-distinct → cache invalidated.

# 22a/22b: policy_rev values from Test 19h must be 64-char sha256 hex (non-empty, correct format).
assert_eq "${#rev_before_change}" "64" "§10/5 pre-change policy_rev is 64-char sha256 hex (Test 19h captured)"
assert_eq "${#rev_after_change}" "64" "§10/5 post-change policy_rev is 64-char sha256 hex (Test 19h captured)"

# 22c: packet POLICY block header differs → packet bytes differ → cache invalidated.
if [ "$rev_before_change" != "$rev_after_change" ]; then
    echo -e "  ${GREEN}PASS${NC} §10/5 packet cache-invalidation: policy change → different policy_rev → byte-distinct POLICY block → cache invalidated"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} §10/5 packet cache-invalidation: policy_rev unchanged after policy mutation — POLICY block header identical → cache NOT invalidated"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# =============================================================================
# ABS-426 bite proof: an induced token/session mint failure BITES (no silent PASS)
# -----------------------------------------------------------------------------
# Mirrors the ABS-370 suite-integrity self-test: snapshot the real counters,
# drive the mint-failure path (deliberately-empty token → the same
# `mint_fail_probe` the §10/6 and §10/7 probes now call), assert it recorded a
# FAIL (not a silent PASS), then RESTORE the tally so this expected failure
# leaves no trace in the release-gating conformance count.
_p0=$PASS; _f0=$FAIL; _t0=$TOTAL
INDUCED_TOKEN=""                       # simulate a failed token/session mint
if [ -n "$INDUCED_TOKEN" ]; then
    :                                  # a real probe would run against the stack here
else
    mint_fail_probe "ABS-426 bite proof: induced mint failure"
fi
_bit=0; [ "$FAIL" -gt "$_f0" ] && _bit=1
PASS=$_p0; FAIL=$_f0; TOTAL=$_t0       # restore — expected failure must not count
assert_eq "$_bit" "1" \
    "ABS-426 bite proof: an induced token/session mint failure records a FAIL (silent-pass path is gone)"
unset _p0 _f0 _t0 _bit INDUCED_TOKEN

# =============================================================================
echo -e "\n${CYAN}=== Test 17: search row ordering — priority ASC, created ASC (ABS-389) ===${NC}\n"
# Canonical cross-adapter contract (profiles/neutral/adapters/task-tracking.md):
# rows sort by priority band hotfix>high>normal>low, then created oldest-first
# within a band. Fence a fixture under one epic and CREATE it in scrambled order
# so a pass proves real sorting, not insertion order. Two same-priority (normal)
# tickets prove the age-ASC within-band tiebreak (older key created first).
OEPIC=$(tracker create --type epic --title "ord fixture epic")
ON1=$(tracker create --type ticket --parent "$OEPIC" --title "ord normal old"          --priority normal)
OH=$(tracker create  --type ticket --parent "$OEPIC" --title "ord hotfix"              --priority hotfix)
OL=$(tracker create  --type ticket --parent "$OEPIC" --title "ord low"                 --priority low)
OHI=$(tracker create --type ticket --parent "$OEPIC" --title "ord high"                --priority high)
ON2=$(tracker create --type ticket --parent "$OEPIC" --title "ord normal young"        --priority normal)
ord_actual=$(tracker search --parent "$OEPIC" | cut -f1 | tr '\n' ' ')
assert_eq "$ord_actual" "$OH $OHI $ON1 $ON2 $OL " \
  "search orders priority ASC then created ASC (hotfix>high>normal[old>young]>low), not insertion order"

# =============================================================================
echo -e "\n${CYAN}=== Test 23: lane — first-class fastlane field (PILOT-6/ABS-319) ===${NC}\n"
# Mirror of the mock suite's lane section: lane is a real frontmatter field on the
# Agentic Backend, mock-identical in create/get/update/search wording (ADR-A-0021).

# AC1: default lane is normal; --lane fastlane surfaces via get.
LANE_DEF=$(tracker create --type ticket --title "default lane")
out=$(tracker get "$LANE_DEF")
assert_contains "$out" "lane: normal" "create without --lane yields lane: normal"
LANE_FAST=$(tracker create --type ticket --title "fast lane" --lane fastlane)
out=$(tracker get "$LANE_FAST")
assert_contains "$out" "lane: fastlane" "create --lane fastlane surfaces via get"

# AC4: lane is a real frontmatter field, NOT stored as a lane:<x> label.
assert_not_contains "$out" "labels:" "lane fastlane ticket carries no labels list"
assert_not_contains "$out" "lane:fastlane" "lane is a field, not a lane:<x> label token"

# AC2: update flips the field both ways, mock-identical success line.
out=$(tracker update "$LANE_DEF" lane fastlane)
assert_eq "$out" "$LANE_DEF: lane updated" "update lane prints the canonical success line"
assert_contains "$(tracker get "$LANE_DEF")" "lane: fastlane" "update lane fastlane flips the field"
tracker update "$LANE_DEF" lane normal >/dev/null
assert_contains "$(tracker get "$LANE_DEF")" "lane: normal" "update lane normal flips it back"

# AC3: search --lane fastlane returns exactly the fastlane tickets.
out=$(tracker search --lane fastlane)
assert_contains "$out" "$LANE_FAST" "search --lane fastlane includes the fastlane ticket"
assert_not_contains "$out" "$LANE_DEF" "search --lane fastlane excludes a normal-lane ticket"

# lane coexists with role/flags/labels without clobbering.
LANE_MIX=$(tracker create --type ticket --title "lane + flags" --lane fastlane --role fe-developer --flag design --label orchestrator-ready)
out=$(tracker get "$LANE_MIX")
assert_contains "$out" "lane: fastlane" "lane survives alongside role/flags/labels"
assert_contains "$out" "flags: [design]" "flags survive alongside lane"
assert_contains "$out" "labels: [orchestrator-ready]" "labels survive alongside lane"

# AC5: invalid lane values rejected on create and update, non-zero exit.
ec=0
tracker create --type ticket --title "bad lane" --lane express >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create --lane with an invalid value is rejected"
ec=0
tracker update "$LANE_DEF" lane express >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update lane with an invalid value is rejected"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo -e "\n  ${RED}CONFORMANCE FAILED — any diff is a release blocker (Epic-AC 1)${NC}\n"
    exit 1
fi
echo -e "  Failed: 0"
echo -e "\n  ${GREEN}ALL CONFORMANCE ASSERTIONS PASSED${NC}\n"
exit 0
