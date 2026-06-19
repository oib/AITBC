#!/usr/bin/env bash
set -euo pipefail

# Pre-tag checklist for v0.5.0 release
# Usage: bash scripts/release/check-v0.5.0.sh

echo "=== v0.5.0 Pre-Tag Release Checklist ==="
echo ""

# Get last tag
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.4.27")
echo "Last tag: $LAST_TAG"
echo ""

# 1. Scope check
echo "1. Checking scope against last tag..."
SCOPE_CHECK=$(git diff --stat "$LAST_TAG" 2>/dev/null || echo "No diff available")
echo "Changed files: $SCOPE_CHECK"
echo ""

# 2. Check for placeholder secrets
echo "2. Checking for placeholder secrets..."
# Exclude validation code that uses placeholders for checking
if grep -r "change-me-in-production" /opt/aitbc/apps --include="*.service" --include="*.py" --exclude-dir=tests --exclude="config_pg.py" 2>/dev/null; then
    echo "❌ FAILED: Found 'change-me-in-production' placeholder"
    exit 1
else
    echo "✅ PASS: No 'change-me-in-production' placeholders found"
fi
echo ""

# 3. Check for TODO placeholders
echo "3. Checking for TODO placeholders..."
# Exclude validation code that uses placeholders for checking
if grep -r "your_.*_here" /opt/aitbc/apps --include="*.service" --include="*.py" --exclude-dir=tests --exclude="config.py" --exclude="settings.py" 2>/dev/null; then
    echo "❌ FAILED: Found 'your_*_here' placeholder"
    exit 1
else
    echo "✅ PASS: No 'your_*_here' placeholders found"
fi
echo ""

# 4. Check hardened services are active
echo "4. Checking hardened services are active..."
CRITICAL_SERVICES=(
    "aitbc-coordinator-api.service"
    "aitbc-blockchain-node.service"
)
ALL_ACTIVE=true
for service in "${CRITICAL_SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo "✅ $service: active"
    else
        echo "❌ $service: NOT active"
        ALL_ACTIVE=false
    fi
done
if [ "$ALL_ACTIVE" = false ]; then
    echo "❌ FAILED: Some critical services are not active"
    exit 1
fi
echo ""

# 5. Check Redis connectivity (if required)
echo "5. Checking Redis connectivity..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis: connected"
    else
        echo "⚠️  Redis: not connected (acceptable if Redis not deployed yet)"
    fi
else
    echo "⚠️  Redis: redis-cli not found (acceptable if Redis not deployed yet)"
fi
echo ""

# 6. Check JSON logging is enabled
echo "6. Checking JSON logging is enabled..."
if systemctl show aitbc-coordinator-api.service --property=Environment | grep -q "LOG_FORMAT=json"; then
    echo "✅ JSON logging: enabled in coordinator-api"
else
    echo "❌ FAILED: JSON logging not enabled in coordinator-api"
    exit 1
fi
echo ""

# 7. Check for placeholder secrets in service files
echo "7. Checking for placeholder secrets in service files..."
PLACEHOLDER_PATTERNS=("change-me" "REPLACE_WITH_SECRET" "placeholder" "changeme" "TODO.*secret")
FOUND_PLACEHOLDERS=false
for pattern in "${PLACEHOLDER_PATTERNS[@]}"; do
    if grep -r "$pattern" /opt/aitbc/apps --include="*.service" 2>/dev/null; then
        echo "❌ FAILED: Found placeholder pattern: $pattern"
        FOUND_PLACEHOLDERS=true
    fi
done
if [ "$FOUND_PLACEHOLDERS" = true ]; then
    exit 1
else
    echo "✅ PASS: No placeholder secrets found in service files"
fi
echo ""

echo "=== All Checks Passed ==="
echo "v0.5.0 is ready for tagging"
