import { expect } from "chai";
import pkg from "hardhat";
const { ethers } = pkg;

describe("Phase 4 Modular Smart Contracts", function () {
  let deployer, user1, user2, user3;
  
  // Contracts
  let contractRegistry;
  let treasuryManager;
  let rewardDistributor;
  let performanceAggregator;
  let stakingPoolFactory;
  let daoGovernanceEnhanced;
  let aiToken;
  
  // Test constants
  const INITIAL_SUPPLY = ethers.parseEther("1000000");
  const MIN_STAKE = ethers.parseEther("100");
  const BUDGET_AMOUNT = ethers.parseEther("10000");
  const REWARD_AMOUNT = ethers.parseEther("1000");
  
  beforeEach(async function () {
    [deployer, user1, user2, user3] = await ethers.getSigners();
    
    // Deploy AIToken for testing
    const AIToken = await ethers.getContractFactory("AIToken");
    aiToken = await AIToken.deploy(INITIAL_SUPPLY);
    await aiToken.waitForDeployment();
    
    // Transfer tokens to users
    await aiToken.transfer(user1.address, ethers.parseEther("10000"));
    await aiToken.transfer(user2.address, ethers.parseEther("10000"));
    await aiToken.transfer(user3.address, ethers.parseEther("10000"));
    
    // Deploy ContractRegistry
    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();
    
    // Deploy TreasuryManager
    const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
    treasuryManager = await TreasuryManager.deploy(await aiToken.getAddress());
    await treasuryManager.waitForDeployment();
    
    // Deploy RewardDistributor
    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    rewardDistributor = await RewardDistributor.deploy();
    await rewardDistributor.waitForDeployment();
    
    // Deploy PerformanceAggregator
    const PerformanceAggregator = await ethers.getContractFactory("PerformanceAggregator");
    performanceAggregator = await PerformanceAggregator.deploy();
    await performanceAggregator.waitForDeployment();
    
    // Deploy StakingPoolFactory
    const StakingPoolFactory = await ethers.getContractFactory("StakingPoolFactory");
    stakingPoolFactory = await StakingPoolFactory.deploy(await aiToken.getAddress());
    await stakingPoolFactory.waitForDeployment();
    
    // Deploy DAOGovernanceEnhanced
    const DAOGovernanceEnhanced = await ethers.getContractFactory("DAOGovernanceEnhanced");
    daoGovernanceEnhanced = await DAOGovernanceEnhanced.deploy(await aiToken.getAddress(), MIN_STAKE);
    await daoGovernanceEnhanced.waitForDeployment();

    // Register contracts in registry first (required by PerformanceAggregator.initialize)
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("TreasuryManager")),
      await treasuryManager.getAddress()
    );
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("RewardDistributor")),
      await rewardDistributor.getAddress()
    );
    // StakingPoolFactory, PerformanceAggregator, and DAOGovernanceEnhanced register themselves during initialize()
    // PerformanceAggregator registers itself during initialize(), so don't register it here

    // Register mock contracts that PerformanceAggregator.initialize() requires
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("PerformanceVerifier")),
      user1.address
    );
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("AgentBounty")),
      user2.address
    );
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("AgentStaking")),
      deployer.address
    );

    // Initialize all contracts (after registration)
    await treasuryManager.initialize(await contractRegistry.getAddress());
    await rewardDistributor.initialize(await contractRegistry.getAddress());
    await performanceAggregator.initialize(await contractRegistry.getAddress());
    await stakingPoolFactory.initialize(await contractRegistry.getAddress());
    await daoGovernanceEnhanced.initialize(await contractRegistry.getAddress());
  });

  describe("ContractRegistry", function () {
    it("Should register and retrieve contracts", async function () {
      const testContractId = ethers.keccak256(ethers.toUtf8Bytes("TestContract"));
      
      await contractRegistry.registerContract(testContractId, user1.address);
      
      const retrievedAddress = await contractRegistry.getContract(testContractId);
      expect(retrievedAddress).to.equal(user1.address);
    });
    
    it("Should update contract addresses", async function () {
      const testContractId = ethers.keccak256(ethers.toUtf8Bytes("TestContract"));
      
      await contractRegistry.registerContract(testContractId, user1.address);
      await contractRegistry.updateContract(testContractId, user2.address);
      
      const retrievedAddress = await contractRegistry.getContract(testContractId);
      expect(retrievedAddress).to.equal(user2.address);
    });
    
    it("Should list all contracts", async function () {
      const [ids, addresses] = await contractRegistry.listContracts();
      expect(ids.length).to.be.greaterThan(0);
      expect(addresses.length).to.equal(ids.length);
    });
  });

  describe("TreasuryManager", function () {
    it("Should create budget categories", async function () {
      await treasuryManager.createBudgetCategory("development", BUDGET_AMOUNT);
      
      const budget = await treasuryManager.getBudgetBalance("development");
      expect(budget).to.equal(BUDGET_AMOUNT);
    });
    
    it("Should allocate funds", async function () {
      await treasuryManager.createBudgetCategory("development", BUDGET_AMOUNT);
      
      // Deposit funds to treasury
      await aiToken.connect(deployer).transfer(treasuryManager.address, BUDGET_AMOUNT);
      
      await treasuryManager.allocateFunds("development", user1.address, ethers.utils.parseEther("1000"));
      
      const allocation = await treasuryManager.getAllocation(1);
      expect(allocation[0]).to.equal(user1.address);
      expect(allocation[1]).to.equal(ethers.utils.parseEther("1000"));
    });
    
    it("Should release vested funds", async function () {
      await treasuryManager.createBudgetCategory("development", BUDGET_AMOUNT);
      
      // Deposit funds to treasury
      await aiToken.connect(deployer).transfer(treasuryManager.address, BUDGET_AMOUNT);
      
      await treasuryManager.allocateFunds("development", user1.address, ethers.utils.parseEther("1000"));
      
      // Fast forward time
      await ethers.provider.send("evm_increaseTime", [31 * 24 * 60 * 60]); // 31 days
      await ethers.provider.send("evm_mine");
      
      const userBalanceBefore = await aiToken.balanceOf(user1.address);
      await treasuryManager.releaseVestedFunds(1);
      const userBalanceAfter = await aiToken.balanceOf(user1.address);
      
      expect(userBalanceAfter.sub(userBalanceBefore)).to.equal(ethers.utils.parseEther("1000"));
    });
  });

  describe("RewardDistributor", function () {
    it("Should create reward pools", async function () {
      await rewardDistributor.createRewardPool(aiToken.address, REWARD_AMOUNT);
      
      const poolBalance = await rewardDistributor.getPoolBalance(1);
      expect(poolBalance).to.equal(REWARD_AMOUNT);
    });
    
    it("Should distribute rewards", async function () {
      await rewardDistributor.createRewardPool(aiToken.address, REWARD_AMOUNT);
      
      // Deposit tokens to reward distributor
      await aiToken.connect(deployer).transfer(rewardDistributor.address, REWARD_AMOUNT);
      
      const recipients = [user1.address, user2.address];
      const amounts = [ethers.utils.parseEther("500"), ethers.utils.parseEther("500")];
      
      await rewardDistributor.distributeRewards(1, recipients, amounts);
      
      const userRewards = await rewardDistributor.getUserRewards(user1.address);
      expect(userRewards).to.equal(ethers.utils.parseEther("500"));
    });
    
    it("Should claim rewards", async function () {
      await rewardDistributor.createRewardPool(aiToken.address, REWARD_AMOUNT);
      
      // Deposit tokens to reward distributor
      await aiToken.connect(deployer).transfer(rewardDistributor.address, REWARD_AMOUNT);
      
      const recipients = [user1.address];
      const amounts = [ethers.utils.parseEther("500")];
      
      await rewardDistributor.distributeRewards(1, recipients, amounts);
      
      const userBalanceBefore = await aiToken.balanceOf(user1.address);
      await rewardDistributor.claimReward(1);
      const userBalanceAfter = await aiToken.balanceOf(user1.address);
      
      // Account for claim fee
      const expectedAmount = ethers.utils.parseEther("500").mul(9990).div(10000); // 0.1% fee
      expect(userBalanceAfter.sub(userBalanceBefore)).to.equal(expectedAmount);
    });
  });

  describe("PerformanceAggregator", function () {
    it("Should update agent performance", async function () {
      await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      
      const reputation = await performanceAggregator.getReputationScore(user1.address);
      expect(reputation).to.be.greaterThan(0);
    });
    
    it("Should calculate APY multiplier", async function () {
      await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      
      const multiplier = await performanceAggregator.calculateAPYMultiplier(8000);
      expect(multiplier).to.be.greaterThan(10000); // Greater than 1x
    });
    
    it("Should maintain performance history", async function () {
      await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      await performanceAggregator.updateAgentPerformance(user1.address, 8500);
      
      const history = await performanceAggregator.getPerformanceHistory(user1.address);
      expect(history.length).to.equal(2);
    });
  });

  describe("StakingPoolFactory", function () {
    it("Should create staking pools", async function () {
      await stakingPoolFactory.createPool("Basic Pool", 500, 30 * 24 * 60 * 60);
      
      const poolDetails = await stakingPoolFactory.getPoolDetails(1);
      expect(poolDetails.poolName).to.equal("Basic Pool");
      expect(poolDetails.baseAPY).to.equal(500);
    });
    
    it("Should allow staking", async function () {
      await stakingPoolFactory.createPool("Basic Pool", 500, 30 * 24 * 60 * 60);
      
      await stakingPoolFactory.stakeInPool(1, MIN_STAKE);
      
      const positionDetails = await stakingPoolFactory.getPositionDetails(1);
      expect(positionDetails.amount).to.equal(MIN_STAKE);
      expect(positionDetails.staker).to.equal(user1.address);
    });
    
    it("Should calculate pool performance", async function () {
      await stakingPoolFactory.createPool("Basic Pool", 500, 30 * 24 * 60 * 60);
      
      const performance = await stakingPoolFactory.getPoolPerformance(1);
      expect(performance).to.be.greaterThan(0);
    });
  });

  describe("DAOGovernanceEnhanced", function () {
    it("Should allow staking", async function () {
      await daoGovernanceEnhanced.stake(MIN_STAKE);
      
      const stakerInfo = await daoGovernanceEnhanced.getStakerInfo(user1.address);
      expect(stakerInfo.amount).to.equal(MIN_STAKE);
      expect(stakerInfo.isActive).to.be.true;
    });
    
    it("Should create proposals", async function () {
      await daoGovernanceEnhanced.stake(MIN_STAKE);
      
      const proposalId = await daoGovernanceEnhanced.createProposal(
        "",
        "test proposal",
        7 * 24 * 60 * 60,
        0, // TREASURY_ALLOCATION
        treasuryManager.address,
        "0x",
        0
      );
      
      expect(proposalId).to.be.greaterThan(0);
    });
    
    it("Should allow voting", async function () {
      await daoGovernanceEnhanced.stake(MIN_STAKE);
      
      const proposalId = await daoGovernanceEnhanced.createProposal(
        "",
        "test proposal",
        7 * 24 * 60 * 60,
        0,
        treasuryManager.address,
        "0x",
        0
      );
      
      await daoGovernanceEnhanced.castVote(proposalId, 1); // Vote for
      
      const proposalInfo = await daoGovernanceEnhanced.getProposalInfo(proposalId);
      expect(proposalInfo.forVotes).to.be.greaterThan(0);
    });
  });

  describe("Integration Tests", function () {
    it("Should integrate TreasuryManager with DAOGovernanceEnhanced", async function () {
      // Set up budget category
      await treasuryManager.createBudgetCategory("governance", BUDGET_AMOUNT);
      await aiToken.connect(deployer).transfer(treasuryManager.address, BUDGET_AMOUNT);
      
      // Create and execute proposal for treasury allocation
      await daoGovernanceEnhanced.stake(MIN_STAKE);
      
      const proposalId = await daoGovernanceEnhanced.createProposal(
        "",
        "treasury allocation",
        7 * 24 * 60 * 60,
        0, // TREASURY_ALLOCATION
        treasuryManager.address,
        treasuryManager.interface.encodeFunctionData("allocateFunds", ["governance", user1.address, ethers.utils.parseEther("1000")]),
        0
      );
      
      await daoGovernanceEnhanced.castVote(proposalId, 1);
      
      // Fast forward voting period
      await ethers.provider.send("evm_increaseTime", [8 * 24 * 60 * 60]);
      await ethers.provider.send("evm_mine");
      
      await daoGovernanceEnhanced.executeProposal(proposalId);
      
      const allocation = await treasuryManager.getAllocation(1);
      expect(allocation[0]).to.equal(user1.address);
    });
    
    it("Should integrate PerformanceAggregator with StakingPoolFactory", async function () {
      // Update agent performance
      await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      
      // Create staking pool
      await stakingPoolFactory.createPool("Performance Pool", 500, 30 * 24 * 60 * 60);
      
      // Stake in pool
      await stakingPoolFactory.stakeInPool(1, MIN_STAKE);
      
      // Check if performance affects staking
      const positionDetails = await stakingPoolFactory.getPositionDetails(1);
      expect(positionDetails.amount).to.equal(MIN_STAKE);
    });
    
    it("Should integrate RewardDistributor with PerformanceAggregator", async function () {
      // Update agent performance
      await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      
      // Create performance-based reward
      await rewardDistributor.createPerformanceReward(user1.address, ethers.utils.parseEther("100"));
      
      // Check if performance multiplier is applied
      const userRewards = await rewardDistributor.getUserRewards(user1.address);
      expect(userRewards).to.be.greaterThan(0);
    });
    
    it("Should handle cross-contract communication through registry", async function () {
      // Test that contracts can find each other through registry
      const treasuryAddress = await stakingPoolFactory.registry.getContract(
        ethers.utils.keccak256(ethers.utils.toUtf8Bytes("TreasuryManager"))
      );
      
      expect(treasuryAddress).to.equal(treasuryManager.address);
      
      const performanceAddress = await treasuryManager.registry.getContract(
        ethers.utils.keccak256(ethers.utils.toUtf8Bytes("PerformanceAggregator"))
      );
      
      expect(performanceAddress).to.equal(performanceAggregator.address);
    });
  });

  describe("Security Tests", function () {
    it("Should prevent unauthorized contract registration", async function () {
      const testContractId = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("UnauthorizedContract"));
      
      await expect(
        contractRegistry.connect(user1).registerContract(testContractId, user1.address)
      ).to.be.reverted;
    });
    
    it("Should prevent invalid budget allocations", async function () {
      await treasuryManager.createBudgetCategory("development", BUDGET_AMOUNT);
      
      await expect(
        treasuryManager.allocateFunds("development", user1.address, BUDGET_AMOUNT.add(1))
      ).to.be.reverted;
    });
    
    it("Should prevent invalid voting", async function () {
      const proposalId = await daoGovernanceEnhanced.createProposal(
        "",
        "test proposal",
        7 * 24 * 60 * 60,
        0,
        treasuryManager.address,
        "0x",
        0
      );
      
      await expect(
        daoGovernanceEnhanced.castVote(proposalId, 3) // Invalid vote type
      ).to.be.reverted;
    });
  });

  describe("Gas Optimization Tests", function () {
    it("Should track gas usage for key operations", async function () {
      // Test gas usage for contract registration
      const testContractId = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("GasTest"));
      const tx = await contractRegistry.registerContract(testContractId, user1.address);
      const receipt = await tx.wait();
      
      console.log("Gas used for contract registration:", receipt.gasUsed.toString());
      
      // Test gas usage for performance update
      const tx2 = await performanceAggregator.updateAgentPerformance(user1.address, 8000);
      const receipt2 = await tx2.wait();
      
      console.log("Gas used for performance update:", receipt2.gasUsed.toString());
      
      // Test gas usage for staking
      await stakingPoolFactory.createPool("Gas Test Pool", 500, 30 * 24 * 60 * 60);
      const tx3 = await stakingPoolFactory.stakeInPool(1, MIN_STAKE);
      const receipt3 = await tx3.wait();
      
      console.log("Gas used for staking:", receipt3.gasUsed.toString());
    });
  });

  after(async function () {
    console.log("\n🎉 All Phase 4 modular contract tests completed!");
  });
});
