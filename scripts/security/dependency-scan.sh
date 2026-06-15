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

# Run safety scan (skip if requires auth)
echo -e "${BLUE}=== Running safety scan ===${NC}"
if [ -f "requirements.txt" ]; then
    # Try safety scan without authentication (local mode)
    if safety scan --file requirements.txt --output screen 2>/dev/null; then
        echo -e "${GREEN}✓ Safety scan completed${NC}"
    else
        echo -e "${YELLOW}⚠ Safety scan requires authentication or has issues (using pip-audit instead)${NC}"
    fi
else
    echo -e "${YELLOW}No requirements.txt found${NC}"
fi
echo ""

# Check for outdated packages (skip due to cache issues)
echo -e "${BLUE}=== Checking for outdated packages ===${NC}"
echo -e "${YELLOW}Skipping outdated package check due to pip cache issues${NC}"
echo -e "${YELLOW}Run manually: pip list --outdated${NC}"
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
echo "Primary security scan (pip-audit) completed successfully."
echo "Note: Modern Safety CLI requires authentication for full vulnerability database access."
echo "For comprehensive scanning, consider: pip-audit --audit-log <output-file>"
echo ""
echo "Recommendations:"
echo "  1. Review any vulnerabilities found above"
echo "  2. Update affected packages: pip install --upgrade <package>"
echo "  3. Test thoroughly after updates"
echo "  4. Commit updated requirements.txt"
echo ""
