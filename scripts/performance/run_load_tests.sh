#!/usr/bin/env bash
set -euo pipefail

# Run load tests for Coordinator API

echo "=== AITBC Coordinator API Load Tests ==="
echo ""

# Check if coordinator API is running
if ! curl -s http://localhost:8203/api/health > /dev/null 2>&1; then
    echo "Error: Coordinator API is not running at http://localhost:8203"
    echo "Start it with: cd /opt/aitbc/apps/coordinator-api && uvicorn app.main:app --host 127.0.0.1 --port 8203"
    exit 1
fi

echo "Coordinator API is running. Starting load tests..."
echo ""

# Run locust with headless mode for automated testing
cd /opt/aitbc

# Test 1: Normal load (100 req/s job submit, 1000 req/s heartbeat)
echo "Test 1: Normal load (100 req/s job submit, 1000 req/s heartbeat)"
uv run locust -f tests/load/test_coordinator_api.py \
    --host http://localhost:8203 \
    --headless \
    --users 100 \
    --spawn-rate 10 \
    --run-time 60s \
    --html reports/load_test_normal.html \
    --csv reports/load_test_normal

echo ""
echo "Normal load test complete. Report: reports/load_test_normal.html"
echo ""

# Test 2: Stress test (higher load)
echo "Test 2: Stress test (higher load)"
uv run locust -f tests/load/test_coordinator_api.py \
    --host http://localhost:8203 \
    --headless \
    --users 500 \
    --spawn-rate 50 \
    --run-time 30s \
    --html reports/load_test_stress.html \
    --csv reports/load_test_stress

echo ""
echo "Stress test complete. Report: reports/load_test_stress.html"
echo ""

# Test 3: Spike test (rapid load increase)
echo "Test 3: Spike test (rapid load increase)"
uv run locust -f tests/load/test_coordinator_api.py \
    --host http://localhost:8203 \
    --headless \
    --users 1000 \
    --spawn-rate 100 \
    --run-time 20s \
    --html reports/load_test_spike.html \
    --csv reports/load_test_spike

echo ""
echo "Spike test complete. Report: reports/load_test_spike.html"
echo ""

echo "=== Load Tests Complete ==="
echo "Reports saved to reports/ directory"
echo ""
echo "Key metrics to check:"
echo "  - Average response time (should be < 500ms for normal load)"
echo "  - 95th percentile response time (should be < 1s for normal load)"
echo "  - Request success rate (should be > 99%)"
echo "  - Requests per second (baseline capacity)"
