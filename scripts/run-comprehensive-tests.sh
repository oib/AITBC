#!/bin/bash
# Comprehensive test runner for AITBC project

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 AITBC Comprehensive Test Runner${NC}"
echo "=================================="

cd "$(dirname "$0")/.."

# Function to run tests by category
run_tests_by_category() {
    local category="$1"
    local marker="$2"
    local description="$3"
    
    echo -e "\n${YELLOW}Running $description tests...${NC}"
    
    if python -m pytest -m "$marker" -v --tb=short; then
        echo -e "${GREEN}✅ $description tests passed${NC}"
        return 0
    else
        echo -e "${RED}❌ $description tests failed${NC}"
        return 1
    fi
}

# Function to run tests by directory
run_tests_by_directory() {
    local directory="$1"
    local description="$2"
    
    echo -e "\n${YELLOW}Running $description tests...${NC}"
    
    if python -m pytest "$directory" -v --tb=short; then
        echo -e "${GREEN}✅ $description tests passed${NC}"
        return 0
    else
        echo -e "${RED}❌ $description tests failed${NC}"
        return 1
    fi
}

# Show test collection info
echo -e "${BLUE}Collecting tests from all directories...${NC}"
python -m pytest --collect-only -q 2>/dev/null | wc -l | xargs echo -e "${BLUE}Total tests collected:${NC}"

# Parse command line arguments
CATEGORY=""
DIRECTORY=""
VERBOSE=""
COVERAGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --category)
            CATEGORY="$2"
            shift 2
            ;;
        --directory)
            DIRECTORY="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        --coverage|-c)
            COVERAGE="--cov=cli --cov=apps --cov=packages --cov-report=html --cov-report=term"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --category <type>    Run tests by category (unit, integration, cli, api, blockchain, crypto, contracts)"
            echo "  --directory <path>   Run tests from specific directory"
            echo "  --verbose, -v       Verbose output"
            echo "  --coverage, -c      Generate coverage report"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --category cli                    # Run CLI tests only"
            echo "  $0 --directory tests/cli             # Run tests from CLI directory"
            echo "  $0 --category unit --coverage        # Run unit tests with coverage"
            echo "  $0                                    # Run all tests"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run specific category tests
if [[ -n "$CATEGORY" ]]; then
    case "$CATEGORY" in
        unit)
            run_tests_by_category "unit" "unit" "Unit"
            ;;
        integration)
            run_tests_by_category "integration" "integration" "Integration"
            ;;
        cli)
            run_tests_by_category "cli" "cli" "CLI"
            ;;
        api)
            run_tests_by_category "api" "api" "API"
            ;;
        blockchain)
            run_tests_by_category "blockchain" "blockchain" "Blockchain"
            ;;
        crypto)
            run_tests_by_category "crypto" "crypto" "Cryptography"
            ;;
        contracts)
            run_tests_by_category "contracts" "contracts" "Smart Contract"
            ;;
        *)
            echo -e "${RED}Unknown category: $CATEGORY${NC}"
            echo "Available categories: unit, integration, cli, api, blockchain, crypto, contracts"
            exit 1
            ;;
    esac
    exit $?
fi

# Run specific directory tests
if [[ -n "$DIRECTORY" ]]; then
    if [[ -d "$DIRECTORY" ]]; then
        run_tests_by_directory "$DIRECTORY" "$DIRECTORY"
        exit $?
    else
        echo -e "${RED}Directory not found: $DIRECTORY${NC}"
        exit 1
    fi
fi

# Run all tests with summary
echo -e "\n${BLUE}Running all tests with comprehensive coverage...${NC}"

# Start time
start_time=$(date +%s)

# Run tests with coverage if requested
if [[ -n "$COVERAGE" ]]; then
    python -m pytest $COVERAGE --tb=short $VERBOSE
else
    python -m pytest --tb=short $VERBOSE
fi

# End time
end_time=$(date +%s)
duration=$((end_time - start_time))

# Summary
echo -e "\n${BLUE}==================================${NC}"
echo -e "${GREEN}🎉 Test Run Complete!${NC}"
echo -e "${BLUE}Duration: ${duration}s${NC}"

if [[ -n "$COVERAGE" ]]; then
    echo -e "${BLUE}Coverage report generated in htmlcov/index.html${NC}"
fi

echo -e "\n${YELLOW}Quick test commands:${NC}"
echo -e "  ${BLUE}• CLI tests:        $0 --category cli${NC}"
echo -e "  ${BLUE}• API tests:        $0 --category api${NC}"
echo -e "  ${BLUE}• Unit tests:       $0 --category unit${NC}"
echo -e "  ${BLUE}• Integration:     $0 --category integration${NC}"
echo -e "  ${BLUE}• Blockchain:      $0 --category blockchain${NC}"
echo -e "  ${BLUE}• Crypto:          $0 --category crypto${NC}"
echo -e "  ${BLUE}• Contracts:       $0 --category contracts${NC}"
echo -e "  ${BLUE}• With coverage:   $0 --coverage${NC}"
