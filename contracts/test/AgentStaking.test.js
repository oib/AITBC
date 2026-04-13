import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("AgentStaking High-Priority Tests", function () {
  let aitbcToken, performanceVerifier, agentStaking;
  let deployer, staker, agentWallet;
  let stakeId;

  beforeEach(async function () {
    [deployer, staker, agentWallet] = await ethers.getSigners();

    // Deploy AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(ethers.parseUnits("1000000", 18));
    await aitbcToken.waitForDeployment();

    // Deploy mock verifier (simple contract with verify function)
    const MockVerifier = await ethers.getContractFactory("MockVerifier");
    performanceVerifier = await MockVerifier.deploy();
    await performanceVerifier.waitForDeployment();

    // Deploy AgentStaking
    const AgentStaking = await ethers.getContractFactory("AgentStaking");
    agentStaking = await AgentStaking.deploy(
      await aitbcToken.getAddress(),
      await performanceVerifier.getAddress()
    );
    await agentStaking.waitForDeployment();

    // Mint tokens to staker
    await aitbcToken.mint(staker.address, ethers.parseEther("10000"));
    await aitbcToken.connect(staker).approve(
      await agentStaking.getAddress(),
      ethers.parseEther("1000000000")
    );

    // Add supported agent
    await agentStaking.addSupportedAgent(
      agentWallet.address,
      0 // PerformanceTier.BRONZE
    );
  });

  describe("Test 1.1.1: Create stake with valid parameters", function () {
    it("Should create stake with valid parameters", async function () {
      const stakeAmount = ethers.parseEther("1000"); // 1000 AITBC
      const lockPeriod = 30 * 24 * 60 * 60; // 30 days in seconds

      // Create stake
      stakeId = await agentStaking.connect(staker).stakeOnAgent.staticCall(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false // autoCompound
      );

      const tx = await agentStaking.connect(staker).stakeOnAgent(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );
      const receipt = await tx.wait();

      // Verify StakeCreated event
      await expect(tx)
        .to.emit(agentStaking, "StakeCreated")
        .withArgs(
          stakeId,
          staker.address,
          agentWallet.address,
          stakeAmount,
          lockPeriod,
          5 // APY
        );

      // Verify stake details
      const stake = await agentStaking.getStake(stakeId);
      expect(stake[0]).to.equal(staker.address); // staker
      expect(stake[1]).to.equal(agentWallet.address); // agentWallet
      expect(stake[2]).to.equal(stakeAmount); // amount
      expect(stake[6]).to.equal(0); // status = ACTIVE
      expect(stake[9]).to.equal(0); // agentTier = BRONZE

      // Verify staker's balance decreased
      const stakerBalance = await aitbcToken.balanceOf(staker.address);
      expect(stakerBalance).to.equal(ethers.parseEther("9000"));
    });

    it("Should calculate correct APY for Bronze tier with 30-day lock", async function () {
      const stakeAmount = ethers.parseEther("1000");
      const lockPeriod = 30 * 24 * 60 * 60;

      const tx = await agentStaking.connect(staker).stakeOnAgent(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );
      const receipt = await tx.wait();

      // Get stake details to check APY
      const logs = await agentStaking.queryFilter(agentStaking.filters.StakeCreated());
      const log = logs[logs.length - 1];
      const apy = log.args.apy;

      // Base APY = 5%
      // Bronze tier multiplier = 1.0
      // 30-day lock multiplier = 1.0
      // Expected APY = 5% * 1.0 * 1.0 = 5%
      expect(apy).to.be.closeTo(5, 1); // Allow small rounding error
    });
  });

  describe("Test 1.4.1: Initiate unbonding after lock period", function () {
    beforeEach(async function () {
      const stakeAmount = ethers.parseEther("1000");
      const lockPeriod = 30 * 24 * 60 * 60;

      stakeId = await agentStaking.connect(staker).stakeOnAgent.staticCall(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );

      await agentStaking.connect(staker).stakeOnAgent(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );
    });

    it("Should initiate unbonding after lock period ends", async function () {
      // Advance time by 30 days
      await ethers.provider.send("evm_increaseTime", [30 * 24 * 60 * 60]);
      await ethers.provider.send("evm_mine");

      // Calculate rewards before unbonding
      const rewardsBefore = await agentStaking.calculateRewards(stakeId);

      // Initiate unbonding
      const tx = await agentStaking.connect(staker).unbondStake(stakeId);
      const receipt = await tx.wait();

      // Verify stake status changed to UNBONDING
      const stake = await agentStaking.getStake(stakeId);
      expect(stake[6]).to.equal(1); // status = UNBONDING


      // Verify rewards were calculated
      const rewardsAfter = await agentStaking.calculateRewards(stakeId);
      expect(rewardsAfter).to.be.greaterThanOrEqual(rewardsBefore);
    });

    it("Should fail to unbond before lock period ends", async function () {
      // Try to unbond immediately
      await expect(
        agentStaking.connect(staker).unbondStake(stakeId)
      ).to.be.revertedWith("Lock period not ended");
    });
  });

  describe("Test 1.4.3: Complete unbonding after unbonding period", function () {
    beforeEach(async function () {
      const stakeAmount = ethers.parseEther("1000");
      const lockPeriod = 30 * 24 * 60 * 60;

      stakeId = await agentStaking.connect(staker).stakeOnAgent.staticCall(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );

      await agentStaking.connect(staker).stakeOnAgent(
        agentWallet.address,
        stakeAmount,
        lockPeriod,
        false
      );

      // Advance time by 30 days (lock period)
      await ethers.provider.send("evm_increaseTime", [30 * 24 * 60 * 60]);
      await ethers.provider.send("evm_mine");

      // Initiate unbonding
      await agentStaking.connect(staker).unbondStake(stakeId);
    });

    it("Should complete unbonding after unbonding period", async function () {
      // Get accumulated rewards before completion
      const stakeBefore = await agentStaking.getStake(stakeId);
      const accumulatedRewards = stakeBefore[8];

      // Advance time by 7 days (unbonding period)
      await ethers.provider.send("evm_increaseTime", [7 * 24 * 60 * 60]);
      await ethers.provider.send("evm_mine");

      // Get staker balance before completion
      const balanceBefore = await aitbcToken.balanceOf(staker.address);

      // Complete unbonding
      const tx = await agentStaking.connect(staker).completeUnbonding(stakeId);
      const receipt = await tx.wait();

      // Verify StakeCompleted event
      const event = receipt.logs.find(log => log.fragment?.name === "StakeCompleted");
      expect(event).to.exist;
      expect(event.args[0]).to.equal(stakeId); // stakeId
      expect(event.args[1]).to.equal(staker.address); // staker
      expect(event.args[2]).to.equal(ethers.parseEther("900")); // totalAmount
      expect(event.args[3]).to.be.at.least(0); // totalRewards

      // Verify stake status changed to COMPLETED
      const stakeAfter = await agentStaking.getStake(stakeId);
      expect(stakeAfter[6]).to.equal(2); // status = COMPLETED

      // Verify staker received stake amount (900 after penalty) + rewards
      const balanceAfter = await aitbcToken.balanceOf(staker.address);
      expect(balanceAfter).to.be.greaterThan(balanceBefore + ethers.parseEther("900"));
    });

    it("Should apply early unbonding penalty if completed within 30 days", async function () {
      // Get accumulated rewards before completion
      const stakeBefore = await agentStaking.getStake(stakeId);
      const accumulatedRewards = stakeBefore[7];

      // Advance time by only 10 days (less than 30-day penalty window)
      await ethers.provider.send("evm_increaseTime", [10 * 24 * 60 * 60]);
      await ethers.provider.send("evm_mine");

      // Get staker balance before completion
      const balanceBefore = await aitbcToken.balanceOf(staker.address);

      // Complete unbonding
      const tx = await agentStaking.connect(staker).completeUnbonding(stakeId);
      const receipt = await tx.wait();

      // Verify penalty was applied (10% of 1000 AITBC = 100 AITBC)
      const balanceAfter = await aitbcToken.balanceOf(staker.address);
      const expectedBalance = balanceBefore + ethers.parseEther("900") + accumulatedRewards; // 1000 - 100 penalty + rewards
      expect(balanceAfter).to.be.closeTo(expectedBalance, ethers.parseEther("0.01"));
    });
  });
});
