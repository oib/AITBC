#!/usr/bin/env bash
# Validate documentation links in MASTER_INDEX.md
# This script checks that all referenced files exist

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MASTER_INDEX="/opt/aitbc/docs/MASTER_INDEX.md"
DOCS_DIR="/opt/aitbc/docs"

echo "Validating documentation links in $MASTER_INDEX..."

if [ ! -f "$MASTER_INDEX" ]; then
    echo -e "${RED}✗ ERROR: MASTER_INDEX.md not found at $MASTER_INDEX${NC}"
    exit 1
fi

# Extract markdown links from MASTER_INDEX.md
# Pattern: [text](path.md) or [text](path/)
LINKS=$(grep -oE '\[.*?\]\(([^)]+)\)' "$MASTER_INDEX" | sed 's/.*(\(.*\))/\1/' | grep -E '\.md$|/$' || true)

if [ -z "$LINKS" ]; then
    echo -e "${YELLOW}⚠ No markdown links found in MASTER_INDEX.md${NC}"
    exit 0
fi

MISSING_FILES=0
TOTAL_LINKS=0

while IFS= read -r link; do
    TOTAL_LINKS=$((TOTAL_LINKS + 1))

    # Handle relative paths
    if [[ "$link" == /* ]]; then
        # Absolute path
        FILE_PATH="$link"
    else
        # Relative path from docs directory
        FILE_PATH="$DOCS_DIR/$link"
    fi

    # Remove trailing slash for directory checks
    CHECK_PATH="${FILE_PATH%/}"

    if [ ! -e "$CHECK_PATH" ]; then
        echo -e "${RED}✗ Missing: $link${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done <<< "$LINKS"

echo ""
echo "Checked $TOTAL_LINKS documentation link(s)"

if [ $MISSING_FILES -gt 0 ]; then
    echo -e "${RED}✗ Found $MISSING_FILES missing file(s)${NC}"
    echo "Please update MASTER_INDEX.md to remove or fix broken links"
    exit 1
else
    echo -e "${GREEN}✓ All documentation links are valid${NC}"
    exit 0
fi
