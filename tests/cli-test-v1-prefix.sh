#!/bin/bash
# /v1 Prefix Verification Script
# Verify /v1 prefix on all updated service endpoints

echo "=== /v1 Prefix Verification ==="
echo "Testing /v1 prefix on updated service endpoints..."
echo ""

failed_endpoints=()

# Test coordinator-api (port 8011)
echo -n "coordinator-api /v1/jobs... "
if curl -s http://localhost:8011/v1/jobs > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("coordinator-api /v1/jobs")
fi

echo -n "coordinator-api /v1/miners... "
if curl -s http://localhost:8011/v1/miners > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("coordinator-api /v1/miners")
fi

# Test agent-coordinator (port 9001)
echo -n "agent-coordinator /v1/health... "
if curl -s http://localhost:9001/v1/health > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("agent-coordinator /v1/health")
fi

echo -n "agent-coordinator /v1/agents/discover... "
if curl -s http://localhost:9001/v1/agents/discover -X POST -H "Content-Type: application/json" -d '{}' > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("agent-coordinator /v1/agents/discover")
fi

# Test marketplace-service (port 8102)
echo -n "marketplace-service /v1/marketplace/offers... "
if curl -s http://localhost:8102/v1/marketplace/offers > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("marketplace-service /v1/marketplace/offers")
fi

echo -n "marketplace-service /v1/marketplace/status... "
if curl -s http://localhost:8102/v1/marketplace/status > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("marketplace-service /v1/marketplace/status")
fi

# Test governance-service (port 8105)
echo -n "governance-service /v1/governance/status... "
if curl -s http://localhost:8105/v1/governance/status > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("governance-service /v1/governance/status")
fi

# Test trading-service (port 8104)
echo -n "trading-service /v1/trading/status... "
if curl -s http://localhost:8104/v1/trading/status > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("trading-service /v1/trading/status")
fi

echo -n "trading-service /v1/blocks... "
if curl -s http://localhost:8104/v1/blocks > /dev/null; then
    echo "✓"
else
    echo "✗"
    failed_endpoints+=("trading-service /v1/blocks")
fi

echo ""
if [ ${#failed_endpoints[@]} -eq 0 ]; then
    echo "All /v1 prefix endpoints are responding ✓"
    exit 0
else
    echo "Failed endpoints:"
    for endpoint in "${failed_endpoints[@]}"; do
        echo "  - $endpoint"
    done
    exit 1
fi
