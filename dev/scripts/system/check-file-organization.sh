#!/bin/bash
# scripts/check-file-organization.sh

echo "🔍 Checking project file organization..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Count issues
ISSUES=0

# Function to report issue
report_issue() {
    local file="$1"
    local issue="$2"
    local suggestion="$3"
    
    echo -e "${RED}❌ ISSUE: $file${NC}"
    echo -e "   ${YELLOW}Problem: $issue${NC}"
    echo -e "   ${BLUE}Suggestion: $suggestion${NC}"
    echo ""
    ((ISSUES++))
}

# Check root directory for misplaced files
echo "📁 Checking root directory..."
cd "$(dirname "$0")/.."

# Test files
for file in test_*.py test_*.sh run_mc_test.sh; do
    if [[ -f "$file" ]]; then
        report_issue "$file" "Test file at root level" "Move to dev/tests/"
    fi
done

# Development scripts
for file in patch_*.py fix_*.py simple_test.py; do
    if [[ -f "$file" ]]; then
        report_issue "$file" "Development script at root level" "Move to dev/scripts/"
    fi
done

# Multi-chain files
for file in MULTI_*.md; do
    if [[ -f "$file" ]]; then
        report_issue "$file" "Multi-chain file at root level" "Move to dev/multi-chain/"
    fi
done

# Environment files
for dir in node_modules .venv cli_env logs .pytest_cache .ruff_cache .vscode; do
    if [[ -d "$dir" ]]; then
        report_issue "$dir" "Environment directory at root level" "Move to dev/env/ or dev/cache/"
    fi
done

# Configuration files
for file in .aitbc.yaml .aitbc.yaml.example .env.production .nvmrc .lycheeignore; do
    if [[ -f "$file" ]]; then
        report_issue "$file" "Configuration file at root level" "Move to config/"
    fi
done

# Check if essential files are missing
echo "📋 Checking essential files..."
ESSENTIAL_FILES=(".editorconfig" ".env.example" ".gitignore" "LICENSE" "README.md" "pyproject.toml" "poetry.lock" "pytest.ini" "run_all_tests.sh")

for file in "${ESSENTIAL_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo -e "${YELLOW}⚠️  WARNING: Essential file '$file' is missing${NC}"
    fi
done

# Summary
if [[ $ISSUES -eq 0 ]]; then
    echo -e "${GREEN}✅ File organization is perfect! No issues found.${NC}"
    exit 0
else
    echo -e "${RED}❌ Found $ISSUES organization issue(s)${NC}"
    echo -e "${BLUE}💡 Run './scripts/move-to-right-folder.sh --auto' to fix automatically${NC}"
    exit 1
fi
