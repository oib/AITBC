#!/bin/bash
# File: /home/oib/windsurf/aitbc/scripts/check-documentation-requirements.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Checking Documentation for Requirement Consistency"
echo "=================================================="

ISSUES_FOUND=false

# Function to check Python version in documentation
check_python_docs() {
    echo -e "\n📋 Checking Python version documentation..."
    
    # Find all markdown files
    find docs/ -name "*.md" -type f | while read -r file; do
        # Check for incorrect Python versions
        if grep -q "python.*3\.[0-9][0-9]" "$file"; then
            echo -e "${YELLOW}⚠️  $file: Contains Python version references${NC}"
            grep -n "python.*3\.[0-9][0-9]" "$file" | head -3
        fi
        
        # Check for correct Python 3.13.5 requirement
        if grep -q "3\.13\.5" "$file"; then
            echo -e "${GREEN}✅ $file: Contains Python 3.13.5 requirement${NC}"
        fi
    done
}

# Function to check system requirements documentation
check_system_docs() {
    echo -e "\n📋 Checking system requirements documentation..."
    
    # Check main deployment guide
    if [ -f "docs/10_plan/aitbc.md" ]; then
        echo "Checking aitbc.md..."
        
        # Check Python version
        if grep -q "3\.13\.5.*minimum.*requirement" docs/10_plan/aitbc.md; then
            echo -e "${GREEN}✅ Python 3.13.5 minimum requirement documented${NC}"
        else
            echo -e "${RED}❌ Python 3.13.5 minimum requirement missing or incorrect${NC}"
            ISSUES_FOUND=true
        fi
        
        # Check system requirements
        if grep -q "8GB.*RAM.*minimum" docs/10_plan/aitbc.md; then
            echo -e "${GREEN}✅ Memory requirement documented${NC}"
        else
            echo -e "${RED}❌ Memory requirement missing or incorrect${NC}"
            ISSUES_FOUND=true
        fi
        
        # Check storage requirement
        if grep -q "50GB.*available.*space" docs/10_plan/aitbc.md; then
            echo -e "${GREEN}✅ Storage requirement documented${NC}"
        else
            echo -e "${RED}❌ Storage requirement missing or incorrect${NC}"
            ISSUES_FOUND=true
        fi
    else
        echo -e "${RED}❌ Main deployment guide (aitbc.md) not found${NC}"
        ISSUES_FOUND=true
    fi
}

# Function to check service files for Python version checks
check_service_files() {
    echo -e "\n📋 Checking service files for Python version validation..."
    
    if [ -d "systemd" ]; then
        find systemd/ -name "*.service" -type f | while read -r file; do
            if grep -q "python.*version" "$file"; then
                echo -e "${GREEN}✅ $file: Contains Python version check${NC}"
            else
                echo -e "${YELLOW}⚠️  $file: Missing Python version check${NC}"
            fi
        done
    fi
}

# Function to check requirements files
check_requirements_files() {
    echo -e "\n📋 Checking requirements files..."
    
    # Check Python requirements
    if [ -f "apps/coordinator-api/requirements.txt" ]; then
        echo "Checking coordinator-api requirements.txt..."
        
        # Check for Python version specification
        if grep -q "python_requires" apps/coordinator-api/requirements.txt; then
            echo -e "${GREEN}✅ Python version requirement specified${NC}"
        else
            echo -e "${YELLOW}⚠️  Python version requirement not specified in requirements.txt${NC}"
        fi
    fi
    
    # Check pyproject.toml
    if [ -f "pyproject.toml" ]; then
        echo "Checking pyproject.toml..."
        
        if grep -q "requires-python.*3\.13" pyproject.toml; then
            echo -e "${GREEN}✅ Python 3.13+ requirement in pyproject.toml${NC}"
        else
            echo -e "${YELLOW}⚠️  Python 3.13+ requirement missing in pyproject.toml${NC}"
        fi
    fi
}

# Function to check for hardcoded versions in code
check_hardcoded_versions() {
    echo -e "\n📋 Checking for hardcoded versions in code..."
    
    # Find Python files with version checks
    find apps/ -name "*.py" -type f -exec grep -l "sys.version_info" {} \; | while read -r file; do
        echo -e "${GREEN}✅ $file: Contains version check${NC}"
        
        # Check if version is correct
        if grep -q "3.*13.*5" "$file"; then
            echo -e "${GREEN}   ✅ Correct version requirement (3.13.5)${NC}"
        else
            echo -e "${YELLOW}   ⚠️  May have incorrect version requirement${NC}"
        fi
    done
}

# Run all checks
check_python_docs
check_system_docs
check_service_files
check_requirements_files
check_hardcoded_versions

# Summary
echo -e "\n📊 Documentation Check Summary"
echo "============================="

if [ "$ISSUES_FOUND" = true ]; then
    echo -e "${RED}❌ Issues found in documentation requirements${NC}"
    echo -e "${RED}Please fix the above issues before deployment${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Documentation requirements are consistent${NC}"
    echo -e "${GREEN}Ready for deployment!${NC}"
    exit 0
fi
