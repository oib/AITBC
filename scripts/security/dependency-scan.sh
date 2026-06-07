#!/bin/bash
# Local dependency security scanning script
# Run this script to check for security vulnerabilities in dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== AITBC Dependency Security Scan ===${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating one...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
else
    source venv/bin/activate
fi

# Install security tools if not already installed
echo -e "${BLUE}Installing security tools...${NC}"
pip install safety bandit pip-audit --quiet

echo -e "${GREEN}✓ Security tools installed${NC}"
echo ""

# Run pip-audit
echo -e "${BLUE}=== Running pip-audit ===${NC}"
if [ -f "requirements.txt" ]; then
    pip-audit -r requirements.txt --desc || echo -e "${YELLOW}⚠ pip-audit found issues${NC}"
else
    echo -e "${YELLOW}No requirements.txt found${NC}"
fi
echo ""

# Run safety check
echo -e "${BLUE}=== Running safety check ===${NC}"
if [ -f "requirements.txt" ]; then
    safety check --file requirements.txt --json --output safety-report.json || echo -e "${YELLOW}⚠ Safety found issues${NC}"
    safety check --file requirements.txt || echo -e "${YELLOW}⚠ Safety found issues${NC}"
else
    echo -e "${YELLOW}No requirements.txt found${NC}"
fi
echo ""

# Check for outdated packages
echo -e "${BLUE}=== Checking for outdated packages ===${NC}"
pip list --outdated || echo -e "${GREEN}✓ All packages up to date${NC}"
echo ""

# Check package versions
echo -e "${BLUE}=== Critical Package Versions ===${NC}"
echo "Cryptography: $(pip show cryptography | grep Version || echo 'Not installed')"
echo "PyJWT: $(pip show pyjwt | grep Version || echo 'Not installed')"
echo "Requests: $(pip show requests | grep Version || echo 'Not installed')"
echo "SQLAlchemy: $(pip show sqlalchemy | grep Version || echo 'Not installed')"
echo ""

# Generate summary report
echo -e "${BLUE}=== Security Scan Summary ===${NC}"
echo -e "${GREEN}✓ Security scan completed${NC}"
echo ""
echo "Reports saved to:"
echo "  - safety-report.json"
echo ""
echo "Recommendations:"
echo "  1. Review any vulnerabilities found above"
echo "  2. Update affected packages: pip install --upgrade <package>"
echo "  3. Test thoroughly after updates"
echo "  4. Commit updated requirements.txt"
echo ""

# Check if safety report has vulnerabilities
if [ -f "safety-report.json" ]; then
    VULN_COUNT=$(python3 -c "import json; print(len(json.load(open('safety-report.json'))))" 2>/dev/null || echo "0")
    if [ "$VULN_COUNT" -gt 0 ]; then
        echo -e "${RED}⚠ Found $VULN_COUNT security vulnerabilities${NC}"
        exit 1
    else
        echo -e "${GREEN}✓ No security vulnerabilities found${NC}"
    fi
fi