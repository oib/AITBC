#!/usr/bin/env bash
# =============================================================================
# Integration test: backend-shipper.sh — Run.log / Telemetry Ingest (ABS-351)
# =============================================================================
# Provisions a throwaway Docker backend, creates synthetic run.log + ledger
# fixtures, drives scripts/backend-shipper.sh, and asserts all ACs:
#
#   AC1: N records → N events POSTed; count + payload fields present.
#   AC2: Cursor persists across restart — no duplicate, no dropped events.
#   AC3: Auth — 201 authenticated, 401 unauthenticated.
#   AC4: run_id present and non-empty on every event.
#   AC5: No listen/bind in backend-shipper.sh (reviewer-checkable; asserted here
#        via grep on the script diff).
#   AC6: scripts/backend-shipper.sh exists, is executable, named in assertions.
#
# Requires docker + docker compose. Skips cleanly (exit 0) when docker is
# absent, mirroring test-backend-tracker.sh.
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHIPPER="$REPO_ROOT/scripts/backend-shipper.sh"
BACKEND_DIR="$REPO_ROOT/backend"
PROJECT_NAME="beship$$"
BOOTSTRAP_TOKEN="shipper-test-token-$$"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

# --- AC5: outbound-only check (no listen/bind) — early, no docker needed ----
echo -e "${CYAN}=== AC5: outbound-only check ===${NC}"
# Exclude comment lines (starting with optional whitespace + #) before scanning.
if grep -vE '^\s*#' "$SHIPPER" 2>/dev/null | grep -qE '\blisten\b|\bbind\b'; then
    echo -e "  ${RED}FAIL${NC} AC5: backend-shipper.sh contains listen/bind call in code"
    exit 1
else
    echo -e "  ${GREEN}PASS${NC} AC5: no listen/bind code in scripts/backend-shipper.sh"
fi

# --- AC6: executable check ---------------------------------------------------
echo -e "${CYAN}=== AC6: scripts/backend-shipper.sh exists + executable ===${NC}"
if [ -x "$SHIPPER" ]; then
    echo -e "  ${GREEN}PASS${NC} AC6: scripts/backend-shipper.sh exists and is executable"
else
    echo -e "  ${RED}FAIL${NC} AC6: scripts/backend-shipper.sh missing or not executable"
    exit 1
fi

# --- Docker preflight --------------------------------------------------------
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo -e "${YELLOW}SKIP${NC} docker / 'docker compose' unavailable — integration suite needs a live backend."
    echo -e "${YELLOW}SKIP${NC} (AC1/AC2/AC3/AC4 require a running backend; not a failure)."
    exit 0
fi
if [ ! -f "$BACKEND_DIR/Dockerfile" ]; then
    echo -e "${RED}FAIL${NC} backend/Dockerfile missing — cannot provision the stack."; exit 1
fi

TMPDIR_RUN="$(mktemp -d /tmp/be-ship-XXXXXX)"
COMPOSE_FILE="$TMPDIR_RUN/docker-compose.yml"
STATE_DIR="$TMPDIR_RUN/state"
mkdir -p "$STATE_DIR"

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
if ! compose up -d --build >/tmp/be-ship-up.$$.log 2>&1; then
    echo -e "${RED}FAIL${NC} 'docker compose up' failed:"; tail -30 /tmp/be-ship-up.$$.log; rm -f /tmp/be-ship-up.$$.log; exit 1
fi
rm -f /tmp/be-ship-up.$$.log

BACKEND_PORT="$(compose port backend 8420 2>/dev/null | sed 's/.*://')"
if [ -z "$BACKEND_PORT" ]; then echo -e "${RED}FAIL${NC} could not resolve backend host port"; exit 1; fi

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
echo -e "${GREEN}READY${NC} backend on :$BACKEND_PORT\n"

# Seed project via psql (bootstrap org is already seeded at boot with the
# BOOTSTRAP_TOKEN; the admin token is used for all shipper calls in the test).
compose exec -T db psql -U postgres -d agentic -v ON_ERROR_STOP=1 <<SQL >/dev/null 2>&1
INSERT INTO project (id, org_id, key, name)
  SELECT gen_random_uuid(), id, 'SHIP', 'Shipper Test'
  FROM org WHERE key='bootstrap'
  ON CONFLICT DO NOTHING;
SQL

export BACKEND_URL="http://localhost:$BACKEND_PORT"
export BACKEND_TOKEN="$BOOTSTRAP_TOKEN"
export TRACKER_PROJECT="SHIP"
export ORCH_STATE_DIR="$STATE_DIR"
export ORCH_RUN_LOG="$STATE_DIR/run.log"
export SHIPPER_CURSOR_FILE="$STATE_DIR/shipper-cursor"
export SHIPPER_FOLLOW=0

# --- Assertion helpers -------------------------------------------------------
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_ge() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -ge "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected >= $2, got $1)"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; echo "$1" | head -5 | sed 's/^/      /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if ! echo "$1" | grep -qF -- "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (did NOT expect: $2)"; FAIL=$((FAIL + 1)); fi
}

# Convenience: count run_events rows for our project via psql
count_events() {
    compose exec -T db psql -U postgres -d agentic -tA -c \
        "SELECT COUNT(*) FROM run_event re JOIN project p ON p.id = re.project_id WHERE p.key = 'SHIP';" \
        2>/dev/null | tr -d '[:space:]'
}

# Convenience: fetch run_ids from run_event (all distinct, comma-joined)
distinct_run_ids() {
    compose exec -T db psql -U postgres -d agentic -tA -c \
        "SELECT DISTINCT run_id FROM run_event re JOIN project p ON p.id = re.project_id WHERE p.key = 'SHIP' ORDER BY run_id;" \
        2>/dev/null | tr '\n' ','
}

# Convenience: check any row has empty run_id
empty_run_ids() {
    compose exec -T db psql -U postgres -d agentic -tA -c \
        "SELECT COUNT(*) FROM run_event re JOIN project p ON p.id = re.project_id WHERE p.key = 'SHIP' AND (run_id IS NULL OR run_id = '');" \
        2>/dev/null | tr -d '[:space:]'
}

# Convenience: check a specific payload field exists (non-null) for a kind
check_field() {
    local kind="$1" field="$2"
    compose exec -T db psql -U postgres -d agentic -tA -c \
        "SELECT COUNT(*) FROM run_event re JOIN project p ON p.id = re.project_id WHERE p.key = 'SHIP' AND kind = '$kind' AND $field IS NOT NULL;" \
        2>/dev/null | tr -d '[:space:]'
}

RUN_ID="20260717T020000-99999-1234"

# ---------------------------------------------------------------------------
# AC3: unauthenticated POST → 401
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC3: unauthenticated POST returns 401 ===${NC}"
unauth_code="$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST "$BACKEND_URL/agent/v1/projects/SHIP/telemetry/events" \
    -H "Content-Type: application/json" \
    -d '{"events":[]}' 2>/dev/null)"
assert_eq "$unauth_code" "401" "unauthenticated POST returns 401"

# ---------------------------------------------------------------------------
# AC3: authenticated POST with empty batch → 201
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC3: authenticated empty batch → 201 ===${NC}"
auth_code="$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST "$BACKEND_URL/agent/v1/projects/SHIP/telemetry/events" \
    -H "Authorization: Bearer $BOOTSTRAP_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"events":[]}' 2>/dev/null)"
assert_eq "$auth_code" "201" "authenticated empty batch returns 201"

# ---------------------------------------------------------------------------
# AC1 + AC4: N records → N events; run_id present on every event
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC1 + AC4: N records → N events; run_id present ===${NC}"

# Create a synthetic run.log with 5 events (1 RUN-START + 4 others).
cat > "$ORCH_RUN_LOG" <<RUNLOG
2026-07-17T02:00:00Z	RUN-START	-	-	-	run_id=${RUN_ID}
2026-07-17T02:00:01Z	INTENT-SPAWN	ABS-351	be-developer	In Progress	note=test
2026-07-17T02:00:02Z	SPAWN-USAGE	ABS-351	be-developer	In Review	tokens=50 cost=\$0.01
2026-07-17T02:00:03Z	TELEMETRY	ABS-351	be-developer	In Review	Read=3 Bash=2
2026-07-17T02:00:04Z	INTENT-COMPLETE	ABS-351	be-developer	Done
RUNLOG

# Create a synthetic spawn ledger with 2 entries.
TODAY="$(date -u +%Y%m%d)"
LEDGER_FILE="$STATE_DIR/spawn-ledger-$TODAY"
cat > "$LEDGER_FILE" <<LEDGER
2026-07-17T02:00:01Z run_id=${RUN_ID} ABS-351 be-developer In Progress
2026-07-17T02:00:02Z run_id=${RUN_ID} ABS-351 be-developer In Review
LEDGER

# Run shipper (drain mode).
bash "$SHIPPER" 2>/dev/null

# run.log has 5 lines; 1 RUN-START + 4 payload events = 5 events shipped.
# Ledger has 2 entries. Total expected = 7.
got_count="$(count_events)"
assert_eq "$got_count" "7" "AC1: 7 records shipped (5 run.log + 2 ledger)"

# Verify payload fields on a SPAWN-USAGE event.
kind_rows="$(check_field "SPAWN-USAGE" "ticket")"
assert_eq "$kind_rows" "1" "AC1: SPAWN-USAGE event has ticket field"

# AC4: no empty run_ids.
empty_count="$(empty_run_ids)"
assert_eq "$empty_count" "0" "AC4: all events have non-empty run_id"

# AC4: the shipped run_id matches the fixture.
run_ids="$(distinct_run_ids)"
assert_contains "$run_ids" "$RUN_ID" "AC4: run_id matches fixture run-ID"

# ---------------------------------------------------------------------------
# AC2: Cursor persistence — restart ships zero new events (idempotent).
# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC2: cursor persists — restart sends no duplicate events ===${NC}"

# Run shipper again without adding new lines.
bash "$SHIPPER" 2>/dev/null

got_count_after="$(count_events)"
assert_eq "$got_count_after" "7" "AC2: count unchanged after restart (no duplicates)"

# Now add one new line to run.log and re-run.
printf '2026-07-17T02:00:05Z\tRUN-STOP\t-\t-\t-\t\n' >> "$ORCH_RUN_LOG"
bash "$SHIPPER" 2>/dev/null

got_count_after2="$(count_events)"
assert_eq "$got_count_after2" "8" "AC2: new line shipped; old lines not re-sent"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$TOTAL tests passed"
    exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$TOTAL tests failed"
    exit 1
fi
