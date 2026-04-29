/**
 * Automated deployment script for AITBC smart contracts
 * Supports deployment to local, testnet, and mainnet environments
 */

const { ethers } = require("hardhat");

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

    // Initialize TreasuryManager
    await treasuryManager.initialize(deployments.ContractRegistry);
    console.log("TreasuryManager initialized");

    // 4. Deploy RewardDistributor
    console.log("\n--- Deploying RewardDistributor ---");
    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    const rewardDistributor = await RewardDistributor.deploy();
    await rewardDistributor.waitForDeployment();
    deployments.RewardDistributor = await rewardDistributor.getAddress();
    console.log("RewardDistributor deployed to:", deployments.RewardDistributor);

    // Initialize RewardDistributor
    await rewardDistributor.initialize(deployments.ContractRegistry);
    console.log("RewardDistributor initialized");

    // 5. Deploy PerformanceAggregator
    console.log("\n--- Deploying PerformanceAggregator ---");
    const PerformanceAggregator = await ethers.getContractFactory("PerformanceAggregator");
    const performanceAggregator = await PerformanceAggregator.deploy();
    await performanceAggregator.waitForDeployment();
    deployments.PerformanceAggregator = await performanceAggregator.getAddress();
    console.log("PerformanceAggregator deployed to:", deployments.PerformanceAggregator);

    // Initialize PerformanceAggregator
    await performanceAggregator.initialize(deployments.ContractRegistry);
    console.log("PerformanceAggregator initialized");

    // 6. Deploy StakingPoolFactory
    console.log("\n--- Deploying StakingPoolFactory ---");
    const StakingPoolFactory = await ethers.getContractFactory("StakingPoolFactory");
    const stakingPoolFactory = await StakingPoolFactory.deploy(deployments.AIToken);
    await stakingPoolFactory.waitForDeployment();
    deployments.StakingPoolFactory = await stakingPoolFactory.getAddress();
    console.log("StakingPoolFactory deployed to:", deployments.StakingPoolFactory);

    // Initialize StakingPoolFactory
    await stakingPoolFactory.initialize(deployments.ContractRegistry);
    console.log("StakingPoolFactory initialized");

    // 7. Deploy DAOGovernanceEnhanced
    console.log("\n--- Deploying DAOGovernanceEnhanced ---");
    const DAOGovernanceEnhanced = await ethers.getContractFactory("DAOGovernanceEnhanced");
    const daoGovernanceEnhanced = await DAOGovernanceEnhanced.deploy(
      deployments.AIToken,
      ethers.parseEther("100") // MIN_STAKE
    );
    await daoGovernanceEnhanced.waitForDeployment();
    deployments.DAOGovernanceEnhanced = await daoGovernanceEnhanced.getAddress();
    console.log("DAOGovernanceEnhanced deployed to:", deployments.DAOGovernanceEnhanced);

    // Initialize DAOGovernanceEnhanced
    await daoGovernanceEnhanced.initialize(deployments.ContractRegistry);
    console.log("DAOGovernanceEnhanced initialized");

    // 8. Deploy AgentMarketplaceV2
    console.log("\n--- Deploying AgentMarketplaceV2 ---");
    const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
    const agentMarketplace = await AgentMarketplaceV2.deploy(deployments.AIToken);
    await agentMarketplace.waitForDeployment();
    deployments.AgentMarketplaceV2 = await agentMarketplace.getAddress();
    console.log("AgentMarketplaceV2 deployed to:", deployments.AgentMarketplaceV2);

    // 9. Register all contracts in registry
    console.log("\n--- Registering Contracts ---");
    await registerContract(contractRegistry, "TreasuryManager", deployments.TreasuryManager);
    await registerContract(contractRegistry, "RewardDistributor", deployments.RewardDistributor);
    await registerContract(contractRegistry, "PerformanceAggregator", deployments.PerformanceAggregator);
    await registerContract(contractRegistry, "StakingPoolFactory", deployments.StakingPoolFactory);
    await registerContract(contractRegistry, "DAOGovernanceEnhanced", deployments.DAOGovernanceEnhanced);
    await registerContract(contractRegistry, "AgentMarketplaceV2", deployments.AgentMarketplaceV2);
    console.log("All contracts registered");

    // 10. Transfer tokens to TreasuryManager
    console.log("\n--- Funding Treasury ---");
    const treasuryFunding = ethers.parseEther("100000");
    await aiToken.transfer(deployments.TreasuryManager, treasuryFunding);
    console.log("Transferred", ethers.formatEther(treasuryFunding), "AIT to TreasuryManager");

    // Save deployment addresses
    console.log("\n=== Deployment Summary ===");
    console.log(JSON.stringify(deployments, null, 2));
    
    // Write to file
    const fs = require("fs");
    const deploymentFile = `deployments-${network.name}-${Date.now()}.json`;
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
  await registry.registerContract(contractId, address);
  console.log(`Registered ${name}: ${address}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
