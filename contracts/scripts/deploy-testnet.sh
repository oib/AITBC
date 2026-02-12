#!/usr/bin/env bash
# Deploy ZKReceiptVerifier to testnet
#
# Prerequisites:
#   npm install -g hardhat @nomicfoundation/hardhat-toolbox
#   cd contracts && npm init -y && npm install hardhat
#
# Usage:
#   ./scripts/deploy-testnet.sh [--network <network>]
#
# Networks: localhost, sepolia, goerli

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACTS_DIR="$(dirname "$SCRIPT_DIR")"
NETWORK="${2:-localhost}"

echo "=== AITBC ZK Contract Deployment ==="
echo "Network: $NETWORK"
echo "Contracts: $CONTRACTS_DIR"
echo ""

# Step 1: Generate Groth16Verifier from circuit (if snarkjs available)
echo "--- Step 1: Check Groth16Verifier ---"
if [[ -f "$CONTRACTS_DIR/Groth16Verifier.sol" ]]; then
    echo "Groth16Verifier.sol exists"
else
    echo "Generating Groth16Verifier.sol from circuit..."
    ZK_DIR="$CONTRACTS_DIR/../apps/zk-circuits"
    if [[ -f "$ZK_DIR/circuit_final.zkey" ]]; then
        npx snarkjs zkey export solidityverifier \
            "$ZK_DIR/circuit_final.zkey" \
            "$CONTRACTS_DIR/Groth16Verifier.sol"
        echo "Generated Groth16Verifier.sol"
    else
        echo "WARNING: circuit_final.zkey not found. Using stub verifier."
        echo "To generate: cd apps/zk-circuits && npx snarkjs groth16 setup ..."
    fi
fi

# Step 2: Compile contracts
echo ""
echo "--- Step 2: Compile Contracts ---"
cd "$CONTRACTS_DIR"
if command -v npx &>/dev/null && [[ -f "hardhat.config.js" ]]; then
    npx hardhat compile
else
    echo "Hardhat not configured. Compile manually:"
    echo "  cd contracts && npx hardhat compile"
fi

# Step 3: Deploy
echo ""
echo "--- Step 3: Deploy to $NETWORK ---"
if command -v npx &>/dev/null && [[ -f "hardhat.config.js" ]]; then
    npx hardhat run scripts/deploy.js --network "$NETWORK"
else
    echo "Deploy script template:"
    echo ""
    cat <<'EOF'
// scripts/deploy.js
const { ethers } = require("hardhat");

async function main() {
    const Verifier = await ethers.getContractFactory("ZKReceiptVerifier");
    const verifier = await Verifier.deploy();
    await verifier.deployed();
    console.log("ZKReceiptVerifier deployed to:", verifier.address);

    // Verify on Etherscan (if not localhost)
    if (network.name !== "localhost" && network.name !== "hardhat") {
        console.log("Waiting for block confirmations...");
        await verifier.deployTransaction.wait(5);
        await hre.run("verify:verify", {
            address: verifier.address,
            constructorArguments: [],
        });
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
EOF
fi

echo ""
echo "=== Deployment Complete ==="
