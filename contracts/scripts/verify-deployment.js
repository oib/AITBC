/**
 * Deployment verification script for AITBC smart contracts
 * Verifies contract deployments and performs basic health checks
 */

const { ethers } = require("hardhat");
const fs = require("fs");

async function main() {
  console.log("=== AITBC Smart Contract Deployment Verification ===");
  
  const network = await ethers.provider.getNetwork();
  console.log("Network:", network.name);
  console.log("Chain ID:", network.chainId.toString());

  // Load deployment addresses
  const deploymentFile = process.env.DEPLOYMENT_FILE || `deployments-${network.name}.json`;
  
  if (!fs.existsSync(deploymentFile)) {
    console.error(`Deployment file not found: ${deploymentFile}`);
    console.log("Usage: DEPLOYMENT_FILE=deployments-localhost.json npx hardhat run scripts/verify-deployment.js");
    process.exit(1);
  }

  const deployments = JSON.parse(fs.readFileSync(deploymentFile, "utf8"));
  console.log("\nLoaded deployments from:", deploymentFile);
  console.log(JSON.stringify(deployments, null, 2));

  const verificationResults = {};

  try {
    // Verify each contract
    for (const [name, address] of Object.entries(deployments)) {
      console.log(`\n--- Verifying ${name} ---`);
      const result = await verifyContract(name, address);
      verificationResults[name] = result;
    }

    // Verify contract registry registrations
    console.log("\n--- Verifying Contract Registry ---");
    if (deployments.ContractRegistry) {
      const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
      const registry = ContractRegistry.attach(deployments.ContractRegistry);
      
      for (const [name, address] of Object.entries(deployments)) {
        if (name === "ContractRegistry") continue;
        
        const contractId = ethers.keccak256(ethers.toUtf8Bytes(name));
        const registeredAddress = await registry.getContract(contractId);
        
        if (registeredAddress.toLowerCase() === address.toLowerCase()) {
          console.log(`✅ ${name} registered correctly in registry`);
          verificationResults[`${name}_registry`] = { success: true, registered: true };
        } else {
          console.log(`❌ ${name} NOT registered in registry (expected: ${address}, got: ${registeredAddress})`);
          verificationResults[`${name}_registry`] = { success: false, registered: false };
        }
      }
    }

    // Verify TreasuryManager balance
    console.log("\n--- Verifying TreasuryManager Balance ---");
    if (deployments.TreasuryManager && deployments.AIToken) {
      const AIToken = await ethers.getContractFactory("AIToken");
      const aiToken = AIToken.attach(deployments.AIToken);
      
      const treasuryBalance = await aiToken.balanceOf(deployments.TreasuryManager);
      console.log("TreasuryManager balance:", ethers.formatEther(treasuryBalance), "AIT");
      
      verificationResults.TreasuryManagerBalance = {
        success: treasuryBalance > 0,
        balance: ethers.formatEther(treasuryBalance)
      };
    }

    // Summary
    console.log("\n=== Verification Summary ===");
    let allPassed = true;
    
    for (const [name, result] of Object.entries(verificationResults)) {
      const status = result.success ? "✅" : "❌";
      console.log(`${status} ${name}`);
      if (!result.success) allPassed = false;
    }

    if (allPassed) {
      console.log("\n✅ All verifications passed!");
      process.exit(0);
    } else {
      console.log("\n❌ Some verifications failed!");
      process.exit(1);
    }

  } catch (error) {
    console.error("\n❌ Verification failed:", error);
    process.exit(1);
  }
}

async function verifyContract(name, address) {
  try {
    // Check if address is valid
    if (!ethers.isAddress(address)) {
      console.log(`❌ Invalid address: ${address}`);
      return { success: false, error: "Invalid address" };
    }

    // Check if code exists at address
    const code = await ethers.provider.getCode(address);
    if (code === "0x") {
      console.log(`❌ No contract code at address: ${address}`);
      return { success: false, error: "No contract code" };
    }

    // Try to get contract instance
    let contract;
    try {
      const factory = await ethers.getContractFactory(name);
      contract = factory.attach(address);
      console.log(`✅ Contract deployed at: ${address}`);
      
      // Try to call a view function to verify it's functional
      if (name === "AIToken") {
        const totalSupply = await contract.totalSupply();
        console.log(`   Total Supply: ${ethers.formatEther(totalSupply)}`);
      } else if (name === "ContractRegistry") {
        const owner = await contract.owner();
        console.log(`   Owner: ${owner}`);
      } else if (name === "TreasuryManager") {
        const token = await contract.aitbcToken();
        console.log(`   Token: ${token}`);
      }
      
      return { success: true, address };
      
    } catch (error) {
      console.log(`⚠️  Could not attach contract: ${error.message}`);
      return { success: false, error: error.message };
    }

  } catch (error) {
    console.log(`❌ Verification error: ${error.message}`);
    return { success: false, error: error.message };
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
