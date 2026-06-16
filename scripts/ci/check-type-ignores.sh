#!/usr/bin/env bash
# Check for undocumented mypy: ignore-errors comments
# This script ensures that any new # mypy: ignore-errors comments are documented in docs/TYPE_CHECKING.md

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Checking for undocumented mypy: ignore-errors comments..."

# Find all Python files with # mypy: ignore-errors
TYPE_IGNORE_FILES=$(grep -r "# mypy: ignore-errors" --include="*.py" /opt/aitbc/apps /opt/aitbc/aitbc 2>/dev/null || true)

if [ -z "$TYPE_IGNORE_FILES" ]; then
    echo -e "${GREEN}✓ No mypy: ignore-errors comments found${NC}"
    exit 0
fi

# Count files with ignores
IGNORE_COUNT=$(echo "$TYPE_IGNORE_FILES" | wc -l)

echo -e "${YELLOW}Found $IGNORE_COUNT file(s) with # mypy: ignore-errors:${NC}"
echo "$TYPE_IGNORE_FILES"
echo ""

# Check if TYPE_CHECKING.md exists
TYPE_CHECKING_MD="/opt/aitbc/docs/TYPE_CHECKING.md"
if [ ! -f "$TYPE_CHECKING_MD" ]; then
    echo -e "${RED}✗ ERROR: docs/TYPE_CHECKING.md does not exist${NC}"
    echo "Please create TYPE_CHECKING.md to document type checking debt"
    exit 1
fi

# Check if each file is documented in TYPE_CHECKING.md
ERRORS=0
while IFS= read -r line; do
    # Extract file path from grep output
    FILE_PATH=$(echo "$line" | cut -d: -f1)

    # Extract relative path for documentation
    REL_PATH=${FILE_PATH#/opt/aitbc/}

    # Check if file is documented in TYPE_CHECKING.md
    if ! grep -q "$REL_PATH" "$TYPE_CHECKING_MD"; then
        echo -e "${RED}✗ ERROR: $REL_PATH has # mypy: ignore-errors but is not documented in docs/TYPE_CHECKING.md${NC}"
        ERRORS=$((ERRORS + 1))
    fi
done <<< "$TYPE_IGNORE_FILES"

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo -e "${RED}✗ Found $ERRORS undocumented mypy: ignore-errors comment(s)${NC}"
    echo "Please document these in docs/TYPE_CHECKING.md with:"
    echo "  - File path"
    echo "  - Reason for the ignore"
    echo "  - Target fix date"
    echo "  - Action plan"
    exit 1
else
    echo -e "${GREEN}✓ All mypy: ignore-errors comments are documented in docs/TYPE_CHECKING.md${NC}"
    exit 0
fi
