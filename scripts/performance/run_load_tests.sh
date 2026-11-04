#!/usr/bin/env bash
set -euo pipefail

# Run load tests for Coordinator API.
# Every test runs even when an earlier one fails; thresholds are checked
# from the locust CSV stats, not just printed (#1041).
#
# Env overrides:
#   COORDINATOR_URL   default http://localhost:8203
#   REPORTS_DIR       default reports
#   MIN_SUCCESS_PCT   default 99  (percent)
#   MAX_P95_MS        default 1000 (ms, normal load)

COORDINATOR_URL="${COORDINATOR_URL:-http://localhost:8203}"
REPORTS_DIR="${REPORTS_DIR:-reports}"
MIN_SUCCESS_PCT="${MIN_SUCCESS_PCT:-99}"
MAX_P95_MS="${MAX_P95_MS:-1000}"

echo "=== AITBC Coordinator API Load Tests ==="
echo ""

if ! curl -fsS "$COORDINATOR_URL/health" > /dev/null 2>&1; then
    echo "Error: Coordinator API is not running at $COORDINATOR_URL"
    exit 1
fi

mkdir -p "$REPORTS_DIR"
FAILED=0

run_test() {
    local name="$1" users="$2" spawn="$3" runtime="$4"
    echo "Test: $name (${users} users, ${runtime})"
    if ! uv run locust -f tests/load/test_coordinator_api.py \
        --host "$COORDINATOR_URL" \
        --headless \
        --users "$users" \
        --spawn-rate "$spawn" \
        --run-time "$runtime" \
        --html "$REPORTS_DIR/load_test_${name}.html" \
        --csv "$REPORTS_DIR/load_test_${name}"; then
        echo "FAIL: $name locust run aborted (rc non-zero)"
        FAILED=1
        return
    fi
    check_thresholds "$name"
}

# Locust writes <prefix>_stats.csv: the Aggregated row carries
# request count, failure count and percentile columns.
check_thresholds() {
    local name="$1" stats="$REPORTS_DIR/load_test_${name}_stats.csv"
    if [ ! -f "$stats" ]; then
        echo "FAIL: $name produced no stats file ($stats)"
        FAILED=1
        return
    fi
    python3 - "$stats" "$name" "$MIN_SUCCESS_PCT" "$MAX_P95_MS" <<'PY' || FAILED=1
import csv, sys
stats, name, min_ok, max_p95 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
rows = [r for r in csv.DictReader(open(stats)) if r.get("Name") == "Aggregated"]
if not rows:
    print(f"FAIL: {name} stats has no Aggregated row"); sys.exit(1)
agg = rows[0]
reqs, fails = int(agg["Request Count"]), int(agg["Failure Count"])
p95 = float(agg.get("95%", agg.get("95%ile", "0")) or 0)
ok = 100.0 * (reqs - fails) / reqs if reqs else 0.0
print(f"{name}: {reqs} reqs, {ok:.1f}% success, p95 {p95:.0f}ms")
if ok < min_ok:
    print(f"FAIL: {name} success rate {ok:.1f}% < {min_ok}%"); sys.exit(1)
if name == "normal" and p95 > max_p95:
    print(f"FAIL: {name} p95 {p95:.0f}ms > {max_p95}ms"); sys.exit(1)
PY
}

run_test normal 100 10 60s
run_test stress 500 50 30s
run_test spike  1000 100 20s

echo ""
if [ "$FAILED" -ne 0 ]; then
    echo "=== Load Tests FAILED ==="
    exit 1
fi
echo "=== Load Tests Complete ==="
