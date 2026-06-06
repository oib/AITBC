import { expect } from "chai";
import pkg from "hardhat";
const { ethers } = pkg;

describe("Phase 4 Modular Smart Contracts - Basic Tests", function () {
  let deployer, user1;
  let contractRegistry, treasuryManager, rewardDistributor;
  
  beforeEach(async function () {
    [deployer, user1] = await ethers.getSigners();
    
    // Deploy ContractRegistry
    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();
    
    // Deploy TreasuryManager (using a mock token address for testing)
    const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
    treasuryManager = await TreasuryManager.deploy(deployer.address);
    await treasuryManager.waitForDeployment();
    
    // Deploy RewardDistributor
    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    rewardDistributor = await RewardDistributor.deploy();
    await rewardDistributor.waitForDeployment();
    
    // Register contracts FIRST
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("TreasuryManager")),
      await treasuryManager.getAddress()
    );
    await contractRegistry.registerContract(
      ethers.keccak256(ethers.toUtf8Bytes("RewardDistributor")),
      await rewardDistributor.getAddress()
    );
    
    // Initialize contracts AFTER registration
    await treasuryManager.initialize(await contractRegistry.getAddress());
    await rewardDistributor.initialize(await contractRegistry.getAddress());
  });

  describe("ContractRegistry", function () {
    it("Should deploy successfully", async function () {
      const address = await contractRegistry.getAddress();
      expect(address).to.not.be.undefined;
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    });
    
    it("Should get version", async function () {
      const version = await contractRegistry.getVersion();
      expect(version).to.equal(1);
    });
    
    it("Should register and retrieve contracts", async function () {
      const testContractId = ethers.keccak256(ethers.toUtf8Bytes("TestContract"));
      
      await contractRegistry.registerContract(testContractId, user1.address);
      
      const retrievedAddress = await contractRegistry.getContract(testContractId);
      expect(retrievedAddress).to.equal(user1.address);
    });
  });

  describe("TreasuryManager", function () {
    it("Should deploy successfully", async function () {
      const address = await treasuryManager.getAddress();
      expect(address).to.not.be.undefined;
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    });
    
    it("Should get version", async function () {
      const version = await treasuryManager.getVersion();
      expect(version).to.equal(1);
    });
    
    it("Should create budget category", async function () {
      await treasuryManager.createBudgetCategory("development", ethers.parseEther("1000"));
      
      const budget = await treasuryManager.getBudgetBalance("development");
      expect(budget).to.equal(ethers.parseEther("1000"));
    });
  });

  describe("RewardDistributor", function () {
    it("Should deploy successfully", async function () {
      const address = await rewardDistributor.getAddress();
      expect(address).to.not.be.undefined;
      expect(address).to.match(/^0x[a-fA-F0-9]{40}$/);
    });
    
    it("Should get version", async function () {
      const version = await rewardDistributor.getVersion();
      expect(version).to.equal(1);
    });
    
    it("Should create reward pool", async function () {
      await rewardDistributor.createRewardPool(deployer.address, ethers.parseEther("1000"));
      
      const poolBalance = await rewardDistributor.getPoolBalance(1);
      expect(poolBalance).to.equal(ethers.parseEther("1000"));
    });
  });

  describe("Integration Tests", function () {
    it("Should integrate contracts through registry", async function () {
      // Test that TreasuryManager can find RewardDistributor through registry
      const rewardAddress = await contractRegistry.getContract(
        ethers.keccak256(ethers.toUtf8Bytes("RewardDistributor"))
      );
      
      expect(rewardAddress).to.equal(await rewardDistributor.getAddress());
    });
    
    it("Should handle cross-contract communication", async function () {
      // Create budget category
      await treasuryManager.createBudgetCategory("rewards", ethers.parseEther("1000"));
      
      // Create reward pool
      await rewardDistributor.createRewardPool(deployer.address, ethers.parseEther("500"));
      
      // Verify both contracts are working
      const budget = await treasuryManager.getBudgetBalance("rewards");
      const poolBalance = await rewardDistributor.getPoolBalance(1);
      
      expect(budget).to.equal(ethers.parseEther("1000"));
      expect(poolBalance).to.equal(ethers.parseEther("500"));
    });
  });

  after(async function () {
    console.log("\n🎉 Phase 4 Modular Contracts Basic Tests Completed!");
  });
});
