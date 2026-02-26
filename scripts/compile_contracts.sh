#!/bin/bash

echo "=== AITBC Smart Contract Compilation ==="

# Check if solc is installed
if ! command -v solc &> /dev/null; then
    echo "Error: solc (Solidity compiler) not found"
    echo "Please install solc: npm install -g solc"
    exit 1
fi

# Create artifacts directory
mkdir -p artifacts
mkdir -p cache

# Contract files to compile
contracts=(
    "contracts/AIPowerRental.sol"
    "contracts/AITBCPaymentProcessor.sol"
    "contracts/PerformanceVerifier.sol"
    "contracts/DisputeResolution.sol"
    "contracts/EscrowService.sol"
    "contracts/DynamicPricing.sol"
    "test/contracts/MockERC20.sol"
    "test/contracts/MockZKVerifier.sol"
    "test/contracts/MockGroth16Verifier.sol"
)

echo "Compiling contracts..."

# Compile each contract
for contract in "${contracts[@]}"; do
    if [ -f "$contract" ]; then
        echo "Compiling $contract..."
        
        # Extract contract name from file path
        contract_name=$(basename "$contract" .sol)
        
        # Compile with solc
        solc --bin --abi --optimize --output-dir artifacts \
              --base-path . \
              --include-path node_modules/@openzeppelin/contracts/node_modules/@openzeppelin/contracts \
              "$contract"
        
        if [ $? -eq 0 ]; then
            echo "✅ $contract_name compiled successfully"
        else
            echo "❌ $contract_name compilation failed"
            exit 1
        fi
    else
        echo "⚠️  Contract file not found: $contract"
    fi
done

echo ""
echo "=== Compilation Summary ==="
echo "✅ All contracts compiled successfully"
echo "📁 Artifacts saved to: artifacts/"
echo "📋 ABI files available for integration"

# List compiled artifacts
echo ""
echo "Compiled artifacts:"
ls -la artifacts/*.bin 2>/dev/null | wc -l | xargs echo "Binary files:"
ls -la artifacts/*.abi 2>/dev/null | wc -l | xargs echo "ABI files:"

echo ""
echo "=== Next Steps ==="
echo "1. Review compilation artifacts"
echo "2. Run integration tests"
echo "3. Deploy to testnet"
echo "4. Perform security audit"
