#!/usr/bin/env bash
# =============================================================================
# PILOT-26 — Seat-lifecycle reconcile FALLBACK (repair path, AC2)
# -----------------------------------------------------------------------------
# The PRIMARY Live-Spawns producer is the orchestrator (it POSTs the seat
# open/close upsert first-hand at spawn/reap). This suite exercises the REPAIR
# path in scripts/backend-shipper.sh (`ship_spawns`): replaying the SEAT-SPAWN
# run.log markers to heal gaps left by a missed POST or a runner crash. The
# log-derived heuristic lives ONLY here (ADR-A-0010: the primary path never
# parses logs).
#
# No docker needed: we drive the real shipper as a subprocess with a STUB curl
# (BACKEND_CURL) that records every POST body to a file and returns HTTP 201, so
# we can assert exactly which seat-upsert bodies the reconcile emits.
#
#   AC2a: a MISSED close is HEALED — a respawn (attempt 2 open) of a still-open
#         predecessor (attempt 1) synthesizes the predecessor's close, so the
#         lifecycle is not lost permanently.
#   AC2b: no phantom — the respawn (attempt 2) is emitted as a distinct open.
#   AC2c: a normal open+close pair replays with the real exit_code.
#   AC2d: the close body carries the FULL identity incl. started_at (the live
#         contract detail: the endpoint 400s on missing_field otherwise).
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHIPPER="$REPO_ROOT/scripts/backend-shipper.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_contains() {
    local hay="$1" needle="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$needle" <<<"$hay"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $needle)"
        FAIL=$((FAIL + 1))
    fi
}

# --- Executable check --------------------------------------------------------
echo -e "${CYAN}=== PILOT-26 reconcile fallback: shipper exists + executable ===${NC}"
if [ -x "$SHIPPER" ]; then
    echo -e "  ${GREEN}PASS${NC} scripts/backend-shipper.sh exists and is executable"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} scripts/backend-shipper.sh missing or not executable"; FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

WORK="$(mktemp -d /tmp/pilot26-recon-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
STATE="$WORK/state"; mkdir -p "$STATE"
POSTLOG="$WORK/posts.log"
RUNLOG="$STATE/run.log"

# --- stub curl: record each POST body, return 201 ----------------------------
STUBCURL="$WORK/curl"
cat > "$STUBCURL" <<'STUB'
#!/usr/bin/env bash
# Minimal curl stand-in for the shipper reconcile test: capture the --data-binary
# body + URL, always report HTTP 201. Args mirror the shipper's invocation
# (-sS --config <f> -o <out> -w '%{http_code}' -X POST -H ... --data-binary <body> <url>).
body=""; url=""
while [ $# -gt 0 ]; do
    case "$1" in
        --data-binary) body="$2"; shift 2 ;;
        http://*|https://*) url="$1"; shift ;;
        *) shift ;;
    esac
done
printf '%s\t%s\n' "$url" "$body" >> "$PILOT26_POSTLOG"
printf '201'
STUB
chmod +x "$STUBCURL"

# --- run.log fixture: markers the runner writes alongside each first-hand POST -
# RUN-START seeds the run_id. Then:
#  - PILOT-1 be-developer opens (attempt 1) but its close is MISSED (crash).
#  - PILOT-1 be-developer opens again (attempt 2 respawn) -> heals attempt 1.
#  - PILOT-2 qas opens then closes cleanly (exit 0).
{
    printf '%s\tRUN-START\t-\t-\t-\trun_id=testrun123\n' '2026-07-24T10:00:00Z'
    printf '%s\tSEAT-SPAWN\tPILOT-1\tbe-developer\tIn Progress\tphase=open spawn_id=testrun123:PILOT-1:be-developer:1 attempt=1 started_at=2026-07-24T10:00:01Z\n' '2026-07-24T10:00:01Z'
    printf '%s\tSEAT-SPAWN\tPILOT-1\tbe-developer\tIn Progress\tphase=open spawn_id=testrun123:PILOT-1:be-developer:2 attempt=2 started_at=2026-07-24T10:05:00Z\n' '2026-07-24T10:05:00Z'
    printf '%s\tSEAT-SPAWN\tPILOT-2\tqas\tIn Review\tphase=open spawn_id=testrun123:PILOT-2:qas:1 attempt=1 started_at=2026-07-24T10:06:00Z\n' '2026-07-24T10:06:00Z'
    printf '%s\tSEAT-SPAWN\tPILOT-2\tqas\tIn Review\tphase=close spawn_id=testrun123:PILOT-2:qas:1 attempt=1 started_at=2026-07-24T10:06:00Z completed_at=2026-07-24T10:07:00Z exit=0\n' '2026-07-24T10:07:00Z'
} > "$RUNLOG"

# --- drive the shipper (single pass) with the stub curl ----------------------
echo -e "${CYAN}=== PILOT-26 reconcile fallback: replay SEAT-SPAWN markers ===${NC}"
PILOT26_POSTLOG="$POSTLOG" \
BACKEND_CURL="$STUBCURL" \
BACKEND_TOKEN="recon-test-token" \
TRACKER_PROJECT="pilotproj" \
BACKEND_URL="http://stub.local" \
ORCH_STATE_DIR="$STATE" \
ORCH_RUN_LOG="$RUNLOG" \
SHIPPER_CURSOR_FILE="$STATE/cursor" \
SHIPPER_FOLLOW=0 \
    bash "$SHIPPER" >/dev/null 2>&1 || true

# Only the seat-upsert POSTs (body carries "spawn_id"; the heartbeat endpoint and
# the run.log telemetry POSTs do not).
SPAWN_POSTS="$(grep -F '"spawn_id"' "$POSTLOG" 2>/dev/null || true)"

assert_contains "$SPAWN_POSTS" '"diagnostic":"reconcile: superseded by respawn"' \
    "AC2a: a MISSED close is healed — respawn synthesizes the predecessor's close"
assert_contains "$SPAWN_POSTS" '"spawn_id":"testrun123:PILOT-1:be-developer:1"' \
    "AC2a: the healed close carries the predecessor's (attempt 1) spawn_id"
assert_contains "$SPAWN_POSTS" '"spawn_id":"testrun123:PILOT-1:be-developer:2"' \
    "AC2b: the respawn (attempt 2) is emitted as a distinct open — no phantom"
assert_contains "$SPAWN_POSTS" '"exit_code":0' \
    "AC2c: the normal PILOT-2 close replays with the real exit_code"
# AC2d: the healed close body includes started_at (endpoint 400s on missing_field).
HEALED_CLOSE="$(grep -F '"spawn_id":"testrun123:PILOT-1:be-developer:1"' <<<"$SPAWN_POSTS" | grep -F 'superseded by respawn' || true)"
assert_contains "$HEALED_CLOSE" '"started_at":"2026-07-24T10:00:01Z"' \
    "AC2d: the healed close carries the FULL identity incl. started_at"

# --- Results -----------------------------------------------------------------
echo -e "\n${CYAN}=== PILOT-26 reconcile fallback results ===${NC}"
echo -e "  Total: $TOTAL  ${GREEN}Passed: $PASS${NC}  Failed: $FAIL"
[ "$FAIL" -eq 0 ] && { echo -e "  ${GREEN}ALL PASSED${NC}"; exit 0; } || exit 1
