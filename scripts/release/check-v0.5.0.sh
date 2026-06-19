#!/bin/bash
# Pre-tag checklist for v0.5.0 release
# This script validates that the codebase is ready for release tagging

set -e

echo "=========================================="
echo "AITBC v0.5.0 Pre-Tag Release Checklist"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# 1. Check git status
echo "1. Checking git status..."
if git diff --quiet; then
    check_pass "Working directory is clean"
else
    check_fail "Working directory has uncommitted changes"
    echo "   Run: git status"
fi

# 2. Check for placeholder text
echo ""
echo "2. Checking for placeholder text..."
if git grep -r "change-me-in-production" -- '*.py' '*.yaml' '*.yml' '*.json' '*.md' '*.service' 2>/dev/null; then
    check_fail "Found 'change-me-in-production' placeholder text"
    echo "   Remove placeholder text before release"
else
    check_pass "No 'change-me-in-production' placeholder text found"
fi

if git grep -r "your_.*_here" -- '*.py' '*.yaml' '*.yml' '*.json' '*.md' 2>/dev/null; then
    check_fail "Found 'your_*_here' placeholder text"
    echo "   Remove placeholder text before release"
else
    check_pass "No 'your_*_here' placeholder text found"
fi

# 3. Check scope of changes
echo ""
echo "3. Checking scope of changes..."
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.4.27")
CHANGED_FILES=$(git diff --stat "$LAST_TAG" 2>/dev/null | wc -l)

if [ "$CHANGED_FILES" -eq 0 ]; then
    check_warn "No changes since last tag ($LAST_TAG)"
else
    check_pass "$CHANGED_FILES files changed since $LAST_TAG"
    echo "   Review: git diff --stat $LAST_TAG"
fi

# 4. Check critical services
echo ""
echo "4. Checking hardened services status..."
CRITICAL_SERVICES=(
    "aitbc-coordinator-api"
    "aitbc-agent-coordinator"
    "aitbc-governance"
    "aitbc-blockchain-p2p"
)

for service in "${CRITICAL_SERVICES[@]}"; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        check_pass "$service is active"
    else
        check_warn "$service is not active (may not be deployed)"
    fi
done

# 5. Check Redis connectivity
echo ""
echo "5. Checking Redis connectivity..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping 2>/dev/null | grep -q "PONG"; then
        check_pass "Redis is responding"
    else
        check_warn "Redis is not responding (may not be required)"
    fi
else
    check_warn "redis-cli not found (Redis may not be required)"
fi

# 6. Check PostgreSQL connectivity
echo ""
echo "6. Checking PostgreSQL connectivity..."
if command -v psql &> /dev/null; then
    if sudo -u postgres psql -c "SELECT 1" 2>/dev/null; then
        check_pass "PostgreSQL is responding"
    else
        check_warn "PostgreSQL is not responding (may not be required)"
    fi
else
    check_warn "psql not found (PostgreSQL may not be required)"
fi

# 7. Check for secrets in service files
echo ""
echo "7. Checking for plaintext secrets in service files..."
if grep -r "password\|_pass\|secret_key\|api_key" --include="*.service" apps/ 2>/dev/null | grep -q "Environment="; then
    check_fail "Found plaintext secrets in service files"
    echo "   Run: grep -rn 'password\\|_pass\\|secret_key\\|api_key' --include='*.service' apps/"
else
    check_pass "No plaintext secrets in service files"
fi

# 8. Check v0.5.0 change.log format
echo ""
echo "8. Checking v0.5.0 change.log format..."
CHANGELOG="docs/releases/v0.5.0/change.log"
if [ -f "$CHANGELOG" ]; then
    # Check for status indicators in task tables
    if grep -q "Status: ✅ Complete" "$CHANGELOG" || grep -q "Status: 🔴 Not started" "$CHANGELOG" || grep -q "Status: 🟡 Partial" "$CHANGELOG"; then
        check_pass "Change log has status indicators"
    else
        check_warn "Change log may be missing status indicators"
    fi

    # Check for blocker field in incomplete tasks
    if grep -A 2 "Status: 🔴 Not started" "$CHANGELOG" | grep -q "Blocker:"; then
        check_pass "Incomplete tasks have blocker documentation"
    else
        check_warn "Some incomplete tasks may lack blocker documentation"
    fi
else
    check_fail "Change log not found: $CHANGELOG"
fi

# 9. Check for hardcoded default passwords
echo ""
echo "9. Checking for hardcoded default passwords..."
if grep -r '="training123"\|="admin123"\|="operator123"\|="user123"\|="password"' --include="*.py" aitbc/ apps/ 2>/dev/null | grep -v ".example" | grep -v "test" | grep -v "__pycache__"; then
    check_fail "Found hardcoded default passwords"
    echo "   Run: grep -rn '=\"training123\"\\|=\"admin123\"' --include='*.py' aitbc/ apps/"
else
    check_pass "No hardcoded default passwords found"
fi

# 10. Check for default database connection strings
echo ""
echo "10. Checking for default database connection strings..."
if grep -r "postgresql://.*:.*@localhost" --include="*.py" apps/ 2>/dev/null | grep -v ".example" | grep -v "test" | grep -v "__pycache__"; then
    check_fail "Found default database connection strings"
    echo "   Run: grep -rn 'postgresql://.*:.*@localhost' --include='*.py' apps/"
else
    check_pass "No default database connection strings found"
fi

# 11. Check for security directives in service files
echo ""
echo "11. Checking for security directives in service files..."
SECURITY_DIRECTIVES=("PrivateTmp" "NoNewPrivileges" "ProtectSystem" "ProtectHome")
MISSING_DIRECTIVES=0

for directive in "${SECURITY_DIRECTIVES[@]}"; do
    if ! grep -r "$directive" --include="*.service" apps/ 2>/dev/null | grep -q "$directive"; then
        check_warn "Security directive '$directive' not found in some service files"
        ((MISSING_DIRECTIVES++))
    fi
done

if [ $MISSING_DIRECTIVES -eq 0 ]; then
    check_pass "All security directives present in service files"
fi

# 12. Check for metrics endpoints
echo ""
echo "12. Checking for metrics endpoints..."
METRICS_FILES=(
    "apps/coordinator-api/src/app/main.py"
    "apps/blockchain-node/src/aitbc_chain/app.py"
    "apps/marketplace/src/marketplace_service/main.py"
)

METRICS_FOUND=0
for file in "${METRICS_FILES[@]}"; do
    if [ -f "$file" ] && grep -q "/metrics" "$file"; then
        ((METRICS_FOUND++))
    fi
done

if [ $METRICS_FOUND -eq 3 ]; then
    check_pass "All core services have /metrics endpoints"
else
    check_warn "Only $METRICS_FOUND/3 core services have /metrics endpoints"
fi

# 13. Check for JSON logging configuration
echo ""
echo "13. Checking for JSON logging configuration..."
if grep -q "LOG_FORMAT=json" apps/coordinator-api/aitbc-coordinator-api.service; then
    check_pass "Coordinator API has JSON logging configured"
else
    check_warn "Coordinator API may not have JSON logging configured"
fi

# 14. Check for .gitignore includes
echo ""
echo "14. Checking .gitignore for .env files..."
if [ -f .gitignore ] && grep -q "\.env" .gitignore; then
    check_pass ".env files are in .gitignore"
else
    check_fail ".env files not in .gitignore"
fi

# 15. Check for production readiness script
echo ""
echo "15. Checking for production readiness script..."
if [ -f "scripts/check-production-readiness.py" ]; then
    check_pass "Production readiness script exists"
else
    check_warn "Production readiness script not found"
fi

# Summary
echo ""
echo "=========================================="
echo "Check Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} Checks completed successfully"
if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}Warnings:${NC} $WARNINGS warnings (review before release)"
fi
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Failed:${NC} $ERRORS errors (must fix before release)"
    echo ""
    echo "❌ Pre-tag checks failed. Fix errors before tagging v0.5.0."
    exit 1
else
    echo ""
    echo "✅ All pre-tag checks passed. Ready to tag v0.5.0."
    exit 0
fi
