#!/bin/bash
# Service Health Check Script
# Check all required services are running before CLI testing

echo "=== AITBC Service Health Check ==="
echo "Testing required services for CLI testing..."
echo ""

services=(
    "coordinator-api"
    "agent-coordinator"
    "blockchain-node"
    "marketplace-service"
    "governance-service"
    "trading-service"
)

failed_services=()

for service in "${services[@]}"; do
    echo -n "Checking $service... "
    if systemctl is-active --quiet "aitbc-$service.service"; then
        echo "✓ Active"
    else
        echo "✗ Not active"
        failed_services+=("$service")
    fi
done

echo ""
if [ ${#failed_services[@]} -eq 0 ]; then
    echo "All required services are running ✓"
    exit 0
else
    echo "Failed services: ${failed_services[*]}"
    exit 1
fi
