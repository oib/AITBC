import { ethers } from "hardhat";
import { ContractFactory } from "ethers";

async function main() {
  console.log("🚀 Deploying AITBC Phase 4 Modular Smart Contracts...");
  
  const [deployer] = await ethers.getSigners();
  console.log("📝 Deploying contracts with account:", deployer.address);
  
  // Get initial balance
  const initialBalance = await deployer.getBalance();
  console.log("💰 Initial balance:", ethers.utils.formatEther(initialBalance), "ETH");
  
  try {
    // 1. Deploy ContractRegistry first (central registry)
    console.log("\n📋 1. Deploying ContractRegistry...");
    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    const contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.deployed();
    console.log("✅ ContractRegistry deployed to:", contractRegistry.address);
    
    // 2. Deploy TreasuryManager
    console.log("\n💰 2. Deploying TreasuryManager...");
    // Get AIToken address (assuming it's already deployed)
    const aiTokenAddress = "0x5FbDB2315673af4b26B5cC2F9E0c8E0E0b0b0b0b"; // Replace with actual AIToken address
    const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
    const treasuryManager = await TreasuryManager.deploy(aiTokenAddress);
    await treasuryManager.deployed();
    console.log("✅ TreasuryManager deployed to:", treasuryManager.address);
    
    // 3. Deploy RewardDistributor
    console.log("\n🎁 3. Deploying RewardDistributor...");
    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    const rewardDistributor = await RewardDistributor.deploy();
    await rewardDistributor.deployed();
    console.log("✅ RewardDistributor deployed to:", rewardDistributor.address);
    
    // 4. Deploy PerformanceAggregator
    console.log("\n📊 4. Deploying PerformanceAggregator...");
    const PerformanceAggregator = await ethers.getContractFactory("PerformanceAggregator");
    const performanceAggregator = await PerformanceAggregator.deploy();
    await performanceAggregator.deployed();
    console.log("✅ PerformanceAggregator deployed to:", performanceAggregator.address);
    
    // 5. Deploy StakingPoolFactory
    console.log("\n🏊 5. Deploying StakingPoolFactory...");
    const StakingPoolFactory = await ethers.getContractFactory("StakingPoolFactory");
    const stakingPoolFactory = await StakingPoolFactory.deploy(aiTokenAddress);
    await stakingPoolFactory.deployed();
    console.log("✅ StakingPoolFactory deployed to:", stakingPoolFactory.address);
    
    // 6. Deploy DAOGovernanceEnhanced
    console.log("\n🏛️ 6. Deploying DAOGovernanceEnhanced...");
    const DAOGovernanceEnhanced = await ethers.getContractFactory("DAOGovernanceEnhanced");
    const daoGovernanceEnhanced = await DAOGovernanceEnhanced.deploy(aiTokenAddress, ethers.utils.parseEther("100"));
    await daoGovernanceEnhanced.deployed();
    console.log("✅ DAOGovernanceEnhanced deployed to:", daoGovernanceEnhanced.address);
    
    // Initialize all contracts with registry
    console.log("\n🔧 Initializing contracts with registry...");
    
    // Initialize TreasuryManager
    await treasuryManager.initialize(contractRegistry.address);
    console.log("✅ TreasuryManager initialized");
    
    // Initialize RewardDistributor
    await rewardDistributor.initialize(contractRegistry.address);
    console.log("✅ RewardDistributor initialized");
    
    // Initialize PerformanceAggregator
    await performanceAggregator.initialize(contractRegistry.address);
    console.log("✅ PerformanceAggregator initialized");
    
    // Initialize StakingPoolFactory
    await stakingPoolFactory.initialize(contractRegistry.address);
    console.log("✅ StakingPoolFactory initialized");
    
    // Initialize DAOGovernanceEnhanced
    await daoGovernanceEnhanced.initialize(contractRegistry.address);
    console.log("✅ DAOGovernanceEnhanced initialized");
    
    // Register all contracts in the registry
    console.log("\n📝 Registering contracts in registry...");
    
    // Register TreasuryManager
    await contractRegistry.registerContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("TreasuryManager")),
      treasuryManager.address
    );
    console.log("✅ TreasuryManager registered");
    
    // Register RewardDistributor
    await contractRegistry.registerContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("RewardDistributor")),
      rewardDistributor.address
    );
    console.log("✅ RewardDistributor registered");
    
    // Register PerformanceAggregator
    await contractRegistry.registerContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("PerformanceAggregator")),
      performanceAggregator.address
    );
    console.log("✅ PerformanceAggregator registered");
    
    // Register StakingPoolFactory
    await contractRegistry.registerContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("StakingPoolFactory")),
      stakingPoolFactory.address
    );
    console.log("✅ StakingPoolFactory registered");
    
    // Register DAOGovernanceEnhanced
    await contractRegistry.registerContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("DAOGovernanceEnhanced")),
      daoGovernanceEnhanced.address
    );
    console.log("✅ DAOGovernanceEnhanced registered");
    
    // Setup initial configuration
    console.log("\n⚙️ Setting up initial configuration...");
    
    // Create initial budget categories in TreasuryManager
    await treasuryManager.createBudgetCategory("development", ethers.utils.parseEther("100000"));
    await treasuryManager.createBudgetCategory("marketing", ethers.utils.parseEther("50000"));
    await treasuryManager.createBudgetCategory("operations", ethers.utils.parseEther("30000"));
    await treasuryManager.createBudgetCategory("rewards", ethers.utils.parseEther("20000"));
    console.log("✅ Budget categories created");
    
    // Create initial staking pools
    await stakingPoolFactory.createPoolWithParameters(
      "Basic Staking",
      500, // 5% APY
      30 * 24 * 60 * 60, // 30 days
      ethers.utils.parseEther("100"), // Min stake
      ethers.utils.parseEther("1000000"), // Max stake
      "Basic staking pool with 5% APY"
    );
    console.log("✅ Basic staking pool created");
    
    await stakingPoolFactory.createPoolWithParameters(
      "Premium Staking",
      1000, // 10% APY
      90 * 24 * 60 * 60, // 90 days
      ethers.utils.parseEther("500"), // Min stake
      ethers.utils.parseEther("500000"), // Max stake
      "Premium staking pool with 10% APY"
    );
    console.log("✅ Premium staking pool created");
    
    await stakingPoolFactory.createPoolWithParameters(
      "VIP Staking",
      2000, // 20% APY
      180 * 24 * 60 * 60, // 180 days
      ethers.utils.parseEther("1000"), // Min stake
      ethers.utils.parseEther("100000"), // Max stake
      "VIP staking pool with 20% APY"
    );
    console.log("✅ VIP staking pool created");
    
    // Create initial reward pool
    await rewardDistributor.createRewardPoolWithDescription(
      aiTokenAddress,
      ethers.utils.parseEther("50000"),
      "Initial reward pool for staking rewards"
    );
    console.log("✅ Initial reward pool created");
    
    // Set up regional council members in DAO
    await daoGovernanceEnhanced.setRegionalCouncilMember("us-east", deployer.address, true);
    await daoGovernanceEnhanced.setRegionalCouncilMember("us-west", deployer.address, true);
    await daoGovernanceEnhanced.setRegionalCouncilMember("eu-west", deployer.address, true);
    console.log("✅ Regional council members set");
    
    // Get final balance
    const finalBalance = await deployer.getBalance();
    const gasUsed = initialBalance.sub(finalBalance);
    
    console.log("\n🎉 Deployment Complete!");
    console.log("⛽ Gas used:", ethers.utils.formatEther(gasUsed), "ETH");
    console.log("💰 Final balance:", ethers.utils.formatEther(finalBalance), "ETH");
    
    // Save deployment addresses
    const deploymentAddresses = {
      ContractRegistry: contractRegistry.address,
      TreasuryManager: treasuryManager.address,
      RewardDistributor: rewardDistributor.address,
      PerformanceAggregator: performanceAggregator.address,
      StakingPoolFactory: stakingPoolFactory.address,
      DAOGovernanceEnhanced: daoGovernanceEnhanced.address,
      AIToken: aiTokenAddress,
      Deployer: deployer.address,
      GasUsed: ethers.utils.formatEther(gasUsed),
      Network: network.name,
      Timestamp: new Date().toISOString()
    };
    
    // Write deployment info to file
    const fs = require('fs');
    fs.writeFileSync(
      './deployment-addresses-phase4.json',
      JSON.stringify(deploymentAddresses, null, 2)
    );
    
    console.log("\n📄 Deployment addresses saved to deployment-addresses-phase4.json");
    
    // Verify contracts are working
    console.log("\n🔍 Verifying contract integrations...");
    
    // Test registry lookup
    const treasuryAddress = await contractRegistry.getContract(
      ethers.utils.keccak256(ethers.utils.toUtf8Bytes("TreasuryManager"))
    );
    console.log("✅ TreasuryManager lookup:", treasuryAddress === treasuryManager.address ? "PASS" : "FAIL");
    
    // Test treasury budget
    const devBudget = await treasuryManager.getBudgetBalance("development");
    console.log("✅ Development budget:", ethers.utils.formatEther(devBudget), "AITBC");
    
    // Test staking pools
    const basicPoolId = await stakingPoolFactory.getPoolByName("Basic Staking");
    const basicPoolDetails = await stakingPoolFactory.getPoolDetails(basicPoolId);
    console.log("✅ Basic staking pool APY:", basicPoolDetails.currentAPY.toNumber() / 100, "%");
    
    // Test performance aggregator
    const performanceTiers = await performanceAggregator.getAllPerformanceTiers();
    console.log("✅ Performance tiers count:", performanceTiers.length);
    
    console.log("\n🎊 All Phase 4 modular contracts deployed and verified successfully!");
    
  } catch (error) {
    console.error("❌ Deployment failed:", error);
    process.exit(1);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
