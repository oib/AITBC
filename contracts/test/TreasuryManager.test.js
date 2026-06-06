import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("TreasuryManager", function () {
  let treasuryManager, aitbcToken, contractRegistry;
  let deployer, user1, user2;
  
  const INITIAL_BALANCE = ethers.parseEther("1000000");
  const BUDGET_AMOUNT = ethers.parseEther("10000");

  beforeEach(async function () {
    [deployer, user1, user2] = await ethers.getSigners();

    // Deploy AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(INITIAL_BALANCE);
    await aitbcToken.waitForDeployment();

    // Deploy ContractRegistry
    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();

    // Deploy TreasuryManager
    const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
    treasuryManager = await TreasuryManager.deploy(await aitbcToken.getAddress());
    await treasuryManager.waitForDeployment();

    // Initialize treasury (this will register it in the registry)
    await treasuryManager.initialize(await contractRegistry.getAddress());

    // Transfer tokens to treasury
    await aitbcToken.transfer(await treasuryManager.getAddress(), ethers.parseEther("100000"));
  });

  describe("Deployment", function () {
    it("Should deploy with correct token address", async function () {
      expect(await treasuryManager.treasuryToken()).to.equal(await aitbcToken.getAddress());
    });

    it("Should set deployer as owner", async function () {
      expect(await treasuryManager.owner()).to.equal(deployer.address);
    });

    it("Should set registry address", async function () {
      expect(await treasuryManager.registry()).to.equal(await contractRegistry.getAddress());
    });
  });

  describe("Budget Category Management", function () {
    it("Should create budget category", async function () {
      await treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT);
      
      const category = await treasuryManager.budgetCategories("operations");
      expect(category.name).to.equal("operations");
      expect(category.totalBudget).to.equal(BUDGET_AMOUNT);
      expect(category.allocatedAmount).to.equal(0);
      expect(category.spentAmount).to.equal(0);
      expect(category.isActive).to.be.true;
    });

    it("Should emit BudgetCategoryCreated event", async function () {
      await expect(
        treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT)
      ).to.emit(treasuryManager, "BudgetCategoryCreated")
        .withArgs("operations", BUDGET_AMOUNT, deployer.address);
    });

    it("Should revert if category already exists", async function () {
      await treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT);
      
      await expect(
        treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT)
      ).to.be.revertedWith("Category already exists");
    });

    it("Should revert if non-owner creates category", async function () {
      await expect(
        treasuryManager.connect(user1).createBudgetCategory("operations", BUDGET_AMOUNT)
      ).to.be.revertedWithCustomError(treasuryManager, "NotAuthorized");
    });

    it("Should revert if budget amount is zero", async function () {
      await expect(
        treasuryManager.createBudgetCategory("operations", 0)
      ).to.be.revertedWithCustomError(treasuryManager, "InvalidAmount");
    });
  });

  describe("Fund Allocation", function () {
    beforeEach(async function () {
      await treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT);
    });

    it("Should allocate funds", async function () {
      await treasuryManager.allocateFunds("operations", user1.address, ethers.parseEther("1000"));
      
      const category = await treasuryManager.budgetCategories("operations");
      expect(category.allocatedAmount).to.equal(ethers.parseEther("1000"));
    });

    it("Should emit FundsAllocated event", async function () {
      await expect(
        treasuryManager.allocateFunds("operations", user1.address, ethers.parseEther("1000"))
      ).to.emit(treasuryManager, "FundsAllocated");
    });

    it("Should revert if insufficient budget", async function () {
      await expect(
        treasuryManager.allocateFunds("operations", user1.address, BUDGET_AMOUNT + ethers.parseEther("1"))
      ).to.be.revertedWithCustomError(treasuryManager, "InsufficientBudget");
    });

    it("Should revert if category is invalid", async function () {
      await expect(
        treasuryManager.allocateFunds("invalid", user1.address, ethers.parseEther("1000"))
      ).to.be.revertedWithCustomError(treasuryManager, "InvalidCategory");
    });
  });

  describe("Treasury Operations", function () {
    it("Should deposit funds to treasury", async function () {
      const depositAmount = ethers.parseEther("1000");
      await aitbcToken.mint(deployer.address, depositAmount);
      await aitbcToken.approve(await treasuryManager.getAddress(), depositAmount);
      
      await expect(
        treasuryManager.depositFunds(depositAmount)
      ).to.emit(treasuryManager, "TreasuryDeposited");
    });

    it("Should emergency withdraw funds from treasury", async function () {
      const withdrawAmount = ethers.parseEther("1000");
      const initialBalance = await aitbcToken.balanceOf(deployer.address);
      
      await treasuryManager.emergencyWithdraw(await aitbcToken.getAddress(), withdrawAmount);
      
      const finalBalance = await aitbcToken.balanceOf(deployer.address);
      expect(finalBalance - initialBalance).to.equal(withdrawAmount);
    });

    it("Should revert if non-owner withdraws", async function () {
      await expect(
        treasuryManager.connect(user1).emergencyWithdraw(await aitbcToken.getAddress(), ethers.parseEther("1000"))
      ).to.be.reverted;
    });

    it("Should revert if insufficient balance", async function () {
      await expect(
        treasuryManager.emergencyWithdraw(await aitbcToken.getAddress(), INITIAL_BALANCE + ethers.parseEther("1"))
      ).to.be.reverted;
    });
  });

  describe("Treasury Status", function () {
    it("Should get category count", async function () {
      await treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT);
      await treasuryManager.createBudgetCategory("development", BUDGET_AMOUNT);
      
      expect(await treasuryManager.categoryCounter()).to.equal(2);
    });

    it("Should get allocation count", async function () {
      await treasuryManager.createBudgetCategory("operations", BUDGET_AMOUNT);
      await treasuryManager.allocateFunds("operations", user1.address, ethers.parseEther("1000"));
      
      expect(await treasuryManager.allocationCounter()).to.equal(1);
    });
  });
});
