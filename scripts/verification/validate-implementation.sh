#!/bin/bash

# ============================================================================
# AITBC Mesh Network - Simple Validation Script
# ============================================================================
# Runs basic validation tests without complex dependencies
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
PYTHON_CMD="$VENV_DIR/bin/python"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check virtual environment
if [[ ! -d "$VENV_DIR" ]]; then
    log_error "Virtual environment not found: $VENV_DIR"
    exit 1
fi

# Check Python modules
log_info "Checking Python module imports..."

cd "$AITBC_ROOT"

# Test basic imports
"$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
    print('✅ MultiValidatorPoA import successful')
except Exception as e:
    print(f'❌ MultiValidatorPoA import failed: {e}')
    exit(1)

try:
    from aitbc_chain.consensus.pbft import PBFTConsensus
    print('✅ PBFTConsensus import successful')
except Exception as e:
    print(f'❌ PBFTConsensus import failed: {e}')
    exit(1)

try:
    from aitbc_chain.consensus.slashing import SlashingManager
    print('✅ SlashingManager import successful')
except Exception as e:
    print(f'❌ SlashingManager import failed: {e}')
    exit(1)

print('✅ All consensus modules imported successfully')
"

if [[ $? -ne 0 ]]; then
    log_error "Module import validation failed"
    exit 1
fi

# Test basic functionality
log_info "Testing basic consensus functionality..."

"$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole

# Create PoA instance
poa = MultiValidatorPoA(chain_id=1337)

# Test adding validators
success = poa.add_validator('0xvalidator1', 1000.0)
if success:
    print('✅ Validator addition successful')
else:
    print('❌ Validator addition failed')
    exit(1)

success = poa.add_validator('0xvalidator2', 1000.0)
if success:
    print('✅ Second validator addition successful')
else:
    print('❌ Second validator addition failed')
    exit(1)

# Test validator count
validator_count = len(poa.validators)
if validator_count >= 2:
    print(f'✅ Validator count correct: {validator_count}')
else:
    print(f'❌ Validator count incorrect: {validator_count}')
    exit(1)

print('✅ Basic consensus functionality tests passed')
"

if [[ $? -ne 0 ]]; then
    log_error "Basic functionality validation failed"
    exit 1
fi

# Test configuration files
log_info "Checking configuration files..."

config_dirs=("$AITBC_ROOT/config/dev" "$AITBC_ROOT/config/staging" "$AITBC_ROOT/config/production")
for config_dir in "${config_dirs[@]}"; do
    if [[ -f "$config_dir/.env" ]]; then
        echo "✅ Configuration file found: $config_dir/.env"
    else
        log_error "Configuration file missing: $config_dir/.env"
        exit 1
    fi
done

# Test scripts
log_info "Checking implementation scripts..."

script_dir="$AITBC_ROOT/scripts/plan"
scripts=("01_consensus_setup.sh" "02_network_infrastructure.sh" "03_economic_layer.sh" "04_agent_network_scaling.sh" "05_smart_contracts.sh")

for script in "${scripts[@]}"; do
    if [[ -f "$script_dir/$script" ]]; then
        echo "✅ Script found: $script"
    else
        log_error "Script missing: $script"
        exit 1
    fi
done

# Test deployment script
if [[ -f "$AITBC_ROOT/scripts/deploy-mesh-network.sh" ]]; then
    echo "✅ Master deployment script found"
else
    log_error "Master deployment script missing"
    exit 1
fi

log_info "✅ All validation checks passed!"
log_info "Implementation is ready for deployment"

echo ""
echo "🚀 Next Steps:"
echo "1. Run: ./scripts/deploy-mesh-network.sh dev"
echo "2. Monitor deployment logs: tail -f logs/deployment.log"
echo "3. Check deployment status: ./scripts/deploy-mesh-network.sh --status"
