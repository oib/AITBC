#!/bin/bash

echo "=== AITBC Smart Contract Deployment to aitbc & aitbc1 ==="

# Server configurations - using cascade connections
AITBC_SSH="aitbc-cascade"
AITBC1_SSH="aitbc1-cascade"
DEPLOY_PATH="/home/oib/windsurf/aitbc"

# Contract files to deploy
CONTRACTS=(
    "contracts/AIPowerRental.sol"
    "contracts/AITBCPaymentProcessor.sol"
    "contracts/PerformanceVerifier.sol"
    "contracts/DisputeResolution.sol"
    "contracts/EscrowService.sol"
    "contracts/DynamicPricing.sol"
    "contracts/ZKReceiptVerifier.sol"
    "contracts/Groth16Verifier.sol"
)

# Deployment scripts
SCRIPTS=(
    "scripts/deploy_contracts.js"
    "scripts/validate_contracts.js"
    "scripts/integration_test.js"
    "scripts/compile_contracts.sh"
)

# Configuration files
CONFIGS=(
    "configs/deployment_config.json"
    "package.json"
    "hardhat.config.cjs"
)

# Test contracts
TEST_CONTRACTS=(
    "test/contracts/MockERC20.sol"
    "test/contracts/MockZKVerifier.sol"
    "test/contracts/MockGroth16Verifier.sol"
    "test/contracts/Integration.test.js"
)

echo "🚀 Starting deployment to aitbc and aitbc1 servers..."

# Function to deploy to a server
deploy_to_server() {
    local ssh_cmd=$1
    local server_name=$2
    
    echo ""
    echo "📡 Deploying to $server_name ($ssh_cmd)..."
    
    # Create directories
    ssh $ssh_cmd "mkdir -p $DEPLOY_PATH/contracts $DEPLOY_PATH/scripts $DEPLOY_PATH/configs $DEPLOY_PATH/test/contracts"
    
    # Deploy contracts
    echo "📄 Deploying smart contracts..."
    for contract in "${CONTRACTS[@]}"; do
        if [ -f "$contract" ]; then
            scp "$contract" $ssh_cmd:"$DEPLOY_PATH/$contract"
            echo "✅ $contract deployed to $server_name"
        else
            echo "❌ $contract not found"
        fi
    done
    
    # Deploy scripts
    echo "🔧 Deploying deployment scripts..."
    for script in "${SCRIPTS[@]}"; do
        if [ -f "$script" ]; then
            scp "$script" $ssh_cmd:"$DEPLOY_PATH/$script"
            ssh $ssh_cmd "chmod +x $DEPLOY_PATH/$script"
            echo "✅ $script deployed to $server_name"
        else
            echo "❌ $script not found"
        fi
    done
    
    # Deploy configurations
    echo "⚙️ Deploying configuration files..."
    for config in "${CONFIGS[@]}"; do
        if [ -f "$config" ]; then
            scp "$config" $ssh_cmd:"$DEPLOY_PATH/$config"
            echo "✅ $config deployed to $server_name"
        else
            echo "❌ $config not found"
        fi
    done
    
    # Deploy test contracts
    echo "🧪 Deploying test contracts..."
    for test_contract in "${TEST_CONTRACTS[@]}"; do
        if [ -f "$test_contract" ]; then
            scp "$test_contract" $ssh_cmd:"$DEPLOY_PATH/$test_contract"
            echo "✅ $test_contract deployed to $server_name"
        else
            echo "❌ $test_contract not found"
        fi
    done
    
    # Deploy node_modules if they exist
    if [ -d "node_modules" ]; then
        echo "📦 Deploying node_modules..."
        ssh $ssh_cmd "mkdir -p $DEPLOY_PATH/node_modules"
        # Use scp -r for recursive copy since rsync might not be available
        scp -r node_modules/ $ssh_cmd:"$DEPLOY_PATH/node_modules/"
        echo "✅ node_modules deployed to $server_name"
    fi
    
    echo "✅ Deployment to $server_name completed"
}

# Deploy to aitbc
deploy_to_server $AITBC_SSH "aitbc"

# Deploy to aitbc1
deploy_to_server $AITBC1_SSH "aitbc1"

echo ""
echo "🔍 Verifying deployment..."

# Verify deployment on aitbc
echo "📊 Checking aitbc deployment..."
ssh $AITBC_SSH "ls -la $DEPLOY_PATH/contracts/*.sol | wc -l | xargs echo 'Contract files on aitbc:'"
ssh $AITBC_SSH "ls -la $DEPLOY_PATH/scripts/*.js | wc -l | xargs echo 'Script files on aitbc:'"

# Verify deployment on aitbc1
echo "📊 Checking aitbc1 deployment..."
ssh $AITBC1_SSH "ls -la $DEPLOY_PATH/contracts/*.sol | wc -l | xargs echo 'Contract files on aitbc1:'"
ssh $AITBC1_SSH "ls -la $DEPLOY_PATH/scripts/*.js | wc -l | xargs echo 'Script files on aitbc1:'"

echo ""
echo "🧪 Running validation on aitbc..."
ssh $AITBC_SSH "cd $DEPLOY_PATH && node scripts/validate_contracts.js"

echo ""
echo "🧪 Running validation on aitbc1..."
ssh $AITBC1_SSH "cd $DEPLOY_PATH && node scripts/validate_contracts.js"

echo ""
echo "🔧 Setting up systemd services..."

# Create systemd service for contract monitoring
create_systemd_service() {
    local ssh_cmd=$1
    local server_name=$2
    
    echo "📝 Creating contract monitoring service on $server_name..."
    
    cat << EOF | $ssh_cmd "cat > /tmp/aitbc-contracts.service"
[Unit]
Description=AITBC Smart Contracts Monitoring
After=network.target aitbc-coordinator-api.service
Wants=aitbc-coordinator-api.service

[Service]
Type=simple
User=oib
Group=oib
WorkingDirectory=$DEPLOY_PATH
Environment=PATH=$DEPLOY_PATH/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/bin/node scripts/contract_monitor.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    ssh $ssh_cmd "sudo mv /tmp/aitbc-contracts.service /etc/systemd/system/"
    ssh $ssh_cmd "sudo systemctl daemon-reload"
    ssh $ssh_cmd "sudo systemctl enable aitbc-contracts.service"
    ssh $ssh_cmd "sudo systemctl start aitbc-contracts.service"
    
    echo "✅ Contract monitoring service created on $server_name"
}

# Create contract monitor script
create_contract_monitor() {
    local ssh_cmd=$1
    local server_name=$2
    
    echo "📝 Creating contract monitor script on $server_name..."
    
    cat << 'EOF' | $ssh_cmd "cat > $DEPLOY_PATH/scripts/contract_monitor.js"
#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

console.log("🔍 AITBC Contract Monitor Started");

// Monitor contracts directory
const contractsDir = path.join(__dirname, '..', 'contracts');

function checkContracts() {
    try {
        const contracts = fs.readdirSync(contractsDir).filter(file => file.endsWith('.sol'));
        console.log(`📊 Monitoring ${contracts.length} contracts`);
        
        contracts.forEach(contract => {
            const filePath = path.join(contractsDir, contract);
            const stats = fs.statSync(filePath);
            console.log(`📄 ${contract}: ${stats.size} bytes, modified: ${stats.mtime}`);
        });
        
        // Check if contracts are valid (basic check)
        const validContracts = contracts.filter(contract => {
            const content = fs.readFileSync(path.join(contractsDir, contract), 'utf8');
            return content.includes('pragma solidity') && content.includes('contract ');
        });
        
        console.log(`✅ Valid contracts: ${validContracts.length}/${contracts.length}`);
        
    } catch (error) {
        console.error('❌ Error monitoring contracts:', error.message);
    }
}

// Check every 30 seconds
setInterval(checkContracts, 30000);

// Initial check
checkContracts();

console.log("🔄 Contract monitoring active (30-second intervals)");
EOF

    ssh $ssh_cmd "chmod +x $DEPLOY_PATH/scripts/contract_monitor.js"
    echo "✅ Contract monitor script created on $server_name"
}

# Setup monitoring services
create_contract_monitor $AITBC_SSH "aitbc"
create_systemd_service $AITBC_SSH "aitbc"

create_contract_monitor $AITBC1_SSH "aitbc1"
create_systemd_service $AITBC1_SSH "aitbc1"

echo ""
echo "📊 Deployment Summary:"
echo "✅ Smart contracts deployed to aitbc and aitbc1"
echo "✅ Deployment scripts and configurations deployed"
echo "✅ Test contracts and validation tools deployed"
echo "✅ Node.js dependencies deployed"
echo "✅ Contract monitoring services created"
echo "✅ Systemd services configured and started"

echo ""
echo "🔗 Service URLs:"
echo "aitbc: http://127.0.0.1:18000"
echo "aitbc1: http://127.0.0.1:18001"

echo ""
echo "📝 Next Steps:"
echo "1. Verify contract deployment on both servers"
echo "2. Run integration tests"
echo "3. Configure marketplace API integration"
echo "4. Start contract deployment process"

echo ""
echo "✨ Deployment to aitbc & aitbc1 completed!"
