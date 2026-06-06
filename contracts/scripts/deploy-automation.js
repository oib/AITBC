/**
 * Automated deployment script for AITBC smart contracts
 * Supports deployment to local, testnet, and mainnet environments
 */

import hardhat from "hardhat";
const { ethers } = hardhat;
import fs from "fs";

async function main() {
  console.log("=== AITBC Smart Contract Deployment ===");
  
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());

  const network = await ethers.provider.getNetwork();
  console.log("Network:", network.name);
  console.log("Chain ID:", network.chainId.toString());

  // Deploy contracts in dependency order
  const deployments = {};

  try {
    // 1. Deploy AIToken (if not already deployed)
    console.log("\n--- Deploying AIToken ---");
    const AIToken = await ethers.getContractFactory("AIToken");
    const aiToken = await AIToken.deploy(ethers.parseUnits("1000000", 18));
    await aiToken.waitForDeployment();
    deployments.AIToken = await aiToken.getAddress();
    console.log("AIToken deployed to:", deployments.AIToken);

    // 2. Deploy ContractRegistry
    console.log("\n--- Deploying ContractRegistry ---");
    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    const contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();
    deployments.ContractRegistry = await contractRegistry.getAddress();
    console.log("ContractRegistry deployed to:", deployments.ContractRegistry);

    // 3. Deploy TreasuryManager
    console.log("\n--- Deploying TreasuryManager ---");
    const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
    const treasuryManager = await TreasuryManager.deploy(deployments.AIToken);
    await treasuryManager.waitForDeployment();
    deployments.TreasuryManager = await treasuryManager.getAddress();
    console.log("TreasuryManager deployed to:", deployments.TreasuryManager);

    // 4. Deploy AgentMarketplaceV2
    console.log("\n--- Deploying AgentMarketplaceV2 ---");
    const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
    const agentMarketplace = await AgentMarketplaceV2.deploy(deployments.AIToken);
    await agentMarketplace.waitForDeployment();
    deployments.AgentMarketplaceV2 = await agentMarketplace.getAddress();
    console.log("AgentMarketplaceV2 deployed to:", deployments.AgentMarketplaceV2);

    // 5. Register contracts in registry
    console.log("\n--- Registering Contracts ---");
    await registerContract(contractRegistry, "TreasuryManager", deployments.TreasuryManager);
    await registerContract(contractRegistry, "AgentMarketplaceV2", deployments.AgentMarketplaceV2);
    console.log("Contracts registered");

    // 6. Initialize TreasuryManager
    console.log("\n--- Initializing TreasuryManager ---");
    await treasuryManager.initialize(deployments.ContractRegistry);
    console.log("TreasuryManager initialized");

    // 7. Transfer tokens to TreasuryManager
    console.log("\n--- Funding Treasury ---");
    const treasuryFunding = ethers.parseEther("100000");
    await aiToken.transfer(deployments.TreasuryManager, treasuryFunding);
    console.log("Transferred", ethers.formatEther(treasuryFunding), "AIT to TreasuryManager");

    // Save deployment addresses
    console.log("\n=== Deployment Summary ===");
    console.log(JSON.stringify(deployments, null, 2));
    
    // Write to file (use consistent filename for verification)
    const deploymentFile = `deployments-${network.name}.json`;
    fs.writeFileSync(deploymentFile, JSON.stringify(deployments, null, 2));
    console.log(`Deployment addresses saved to: ${deploymentFile}`);

    console.log("\n✅ Deployment completed successfully!");
    
    return deployments;

  } catch (error) {
    console.error("\n❌ Deployment failed:", error);
    throw error;
  }
}

async function registerContract(registry, name, address) {
  const contractId = ethers.keccak256(ethers.toUtf8Bytes(name));
  try {
    await registry.registerContract(contractId, address);
    console.log(`Registered ${name}: ${address}`);
  } catch (error) {
    if (error.message.includes("ContractAlreadyRegistered")) {
      console.log(`${name} already registered, skipping`);
    } else {
      throw error;
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
