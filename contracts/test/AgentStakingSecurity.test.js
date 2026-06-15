import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("AgentStaking Security Tests", function () {
  let agentStaking;
  let aitbcToken;
  let owner, oracle, staker, agentWallet, attacker;

  beforeEach(async function () {
    [owner, oracle, staker, agentWallet, attacker] = await ethers.getSigners();

    // Deploy mock AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(ethers.parseEther("1000000"));
    await aitbcToken.waitForDeployment();

    // Transfer tokens to staker
    await aitbcToken.transfer(staker.address, ethers.parseEther("10000"));
    await aitbcToken.transfer(attacker.address, ethers.parseEther("10000"));

    // Deploy AgentStaking
    const AgentStaking = await ethers.getContractFactory("AgentStaking");
    agentStaking = await AgentStaking.deploy(
      await aitbcToken.getAddress(),
      ethers.ZeroAddress // PerformanceVerifier (not needed for these tests)
    );
    await agentStaking.waitForDeployment();

    // Add supported agent
    await agentStaking.addSupportedAgent(
      agentWallet.address,
      2 // SILVER tier
    );

    // Add oracle
    await agentStaking.addOracle(oracle.address);
  });

  describe("SC-H-01: Slashing Mechanism", function () {
    beforeEach(async function () {
      // Stake tokens
      await aitbcToken.connect(staker).approve(
        await agentStaking.getAddress(),
        ethers.parseEther("1000")
      );

      await agentStaking.connect(staker).stakeOnAgent(
        agentWallet.address,
        ethers.parseEther("1000"),
        30 * 24 * 60 * 60,
        false
      );
    });

    it("should allow owner to manually slash a stake", async function () {
      const stakeId = 0;
      const slashingPercentage = 10;

      await expect(
        agentStaking.slashStake(
          stakeId,
          slashingPercentage,
          "Manual slash for testing"
        )
      ).to.emit(agentStaking, "StakeSlashed");

      const stake = await agentStaking.stakes(stakeId);
      expect(stake.status).to.equal(3); // SLASHED
      expect(stake.amount).to.equal(ethers.parseEther("900")); // 1000 - 10%
    });

    it("should not allow non-owner to slash", async function () {
      const stakeId = 0;
      const slashingPercentage = 10;

      await expect(
        agentStaking.connect(attacker).slashStake(
          stakeId,
          slashingPercentage,
          "Unauthorized slash"
        )
      ).to.be.revertedWith("Ownable: caller is not the owner");
    });

    it("should not allow slashing inactive stakes", async function () {
      const stakeId = 0;

      // Fast forward past lock period (30 days)
      await ethers.provider.send("evm_increaseTime", [30 * 24 * 60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      // Unbond the stake first
      await agentStaking.connect(staker).unbondStake(stakeId);

      await expect(
        agentStaking.slashStake(
          stakeId,
          10,
          "Test"
        )
      ).to.be.revertedWith("Stake not active");
    });

    it("should not allow invalid slashing percentage", async function () {
      const stakeId = 0;

      await expect(
        agentStaking.slashStake(
          stakeId,
          101, // > 100%
          "Test"
        )
      ).to.be.revertedWith("Invalid percentage");
    });

    it("should automatically slash agent based on low accuracy", async function () {
      // Set low accuracy metrics (as oracle)
      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        30, // 30% accuracy (below default 50%)
        false
      );

      await expect(
        agentStaking.checkAndSlashAgent(agentWallet.address)
      ).to.emit(agentStaking, "StakeSlashed");
    });

    it("should automatically slash agent based on missed jobs", async function () {
      // Set metrics with many missed jobs (as oracle) with delays
      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        70,
        false
      );

      await expect(
        agentStaking.checkAndSlashAgent(agentWallet.address)
      ).to.emit(agentStaking, "StakeSlashed");
    });

    it("should allow filing an appeal for slashed stake", async function () {
      const stakeId = 0;

      // Slash the stake
      await agentStaking.slashStake(stakeId, 10, "Test");

      await expect(
        agentStaking.connect(staker).appealSlashing(
          stakeId,
          "Appeal reason"
        )
      ).to.emit(agentStaking, "SlashAppealFiled");
    });

    it("should not allow appeal from non-staker", async function () {
      const stakeId = 0;

      await agentStaking.slashStake(stakeId, 10, "Test");

      await expect(
        agentStaking.connect(attacker).appealSlashing(
          stakeId,
          "Appeal reason"
        )
      ).to.be.revertedWith("Not your stake");
    });

    it("should not allow appeal after window expires", async function () {
      const stakeId = 0;

      await agentStaking.slashStake(stakeId, 10, "Test");

      // Fast forward past appeal window (3 days)
      await ethers.provider.send("evm_increaseTime", [3 * 24 * 60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      await expect(
        agentStaking.connect(staker).appealSlashing(
          stakeId,
          "Appeal reason"
        )
      ).to.be.revertedWith("Appeal window expired");
    });

    it("should allow owner to approve appeal", async function () {
      const stakeId = 0;

      await agentStaking.slashStake(stakeId, 10, "Test");
      await agentStaking.connect(staker).appealSlashing(stakeId, "Appeal reason");

      await expect(
        agentStaking.resolveSlashAppeal(stakeId, true)
      ).to.emit(agentStaking, "SlashAppealApproved");

      const stake = await agentStaking.stakes(stakeId);
      expect(stake.status).to.equal(0); // ACTIVE
    });

    it("should allow owner to reject appeal", async function () {
      const stakeId = 0;

      await agentStaking.slashStake(stakeId, 10, "Test");
      await agentStaking.connect(staker).appealSlashing(stakeId, "Appeal reason");

      await expect(
        agentStaking.resolveSlashAppeal(stakeId, false)
      ).to.emit(agentStaking, "SlashAppealRejected");
    });

    it("should allow reporting malicious agent with reward", async function () {
      // Set low accuracy (as oracle)
      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        30,
        false
      );

      const reporterBalanceBefore = await aitbcToken.balanceOf(attacker.address);

      await expect(
        agentStaking.connect(attacker).reportMaliciousAgent(
          agentWallet.address,
          "Evidence of malicious behavior"
        )
      ).to.emit(agentStaking, "MaliciousAgentReported");

      const reporterBalanceAfter = await aitbcToken.balanceOf(attacker.address);
      expect(reporterBalanceAfter).to.be.gt(reporterBalanceBefore);
    });

    it("should allow owner to set custom slashing conditions", async function () {
      await agentStaking.setSlashingConditions(
        agentWallet.address,
        60, // minAccuracy
        3, // maxMissedJobs
        15 // slashingPercentage
      );

      const conditions = await agentStaking.slashingConditions(agentWallet.address);
      expect(conditions.minAccuracyThreshold).to.equal(60);
      expect(conditions.maxMissedJobs).to.equal(3);
      expect(conditions.slashingPercentage).to.equal(15);
    });
  });

  describe("SC-H-02: Oracle Protection", function () {
    it("should allow owner to add oracle", async function () {
      const newOracle = attacker;

      await expect(
        agentStaking.addOracle(newOracle.address)
      ).to.emit(agentStaking, "OracleAdded");

      const isAuthorized = await agentStaking.authorizedOracles(newOracle.address);
      expect(isAuthorized).to.be.true;
    });

    it("should not allow adding duplicate oracle", async function () {
      await expect(
        agentStaking.addOracle(oracle.address)
      ).to.be.revertedWith("Oracle already authorized");
    });

    it("should allow owner to remove oracle", async function () {
      await expect(
        agentStaking.removeOracle(oracle.address)
      ).to.emit(agentStaking, "OracleRemoved");

      const isAuthorized = await agentStaking.authorizedOracles(oracle.address);
      expect(isAuthorized).to.be.false;
    });

    it("should not allow non-owner to add oracle", async function () {
      await expect(
        agentStaking.connect(attacker).addOracle(attacker.address)
      ).to.be.revertedWith("Ownable: caller is not the owner");
    });

    it("should not allow unauthorized oracle to update performance", async function () {
      await expect(
        agentStaking.connect(attacker).updateAgentPerformance(
          agentWallet.address,
          80,
          true
        )
      ).to.be.revertedWith("Not authorized oracle");
    });

    it("should allow authorized oracle to update performance with signature", async function () {
      const accuracy = 85;
      const successful = true;
      const nonce = await agentStaking.oracleNonces(oracle.address);

      // Get current block timestamp
      const block = await ethers.provider.getBlock("latest");
      const timestamp = block.timestamp + 3600; // 1 hour in future

      // Create message hash
      const messageHash = ethers.solidityPackedKeccak256(
        ["address", "uint256", "bool", "uint256", "uint256"],
        [agentWallet.address, accuracy, successful, timestamp, nonce]
      );

      // Sign the message hash directly (not the eth signed message hash)
      const signature = await oracle.signMessage(ethers.getBytes(messageHash));

      await expect(
        agentStaking.connect(oracle).updateAgentPerformanceWithSignature(
          agentWallet.address,
          accuracy,
          successful,
          timestamp,
          nonce,
          signature
        )
      ).to.emit(agentStaking, "PerformanceUpdateWithSignature");
    });

    it("should reject expired signature", async function () {
      const accuracy = 85;
      const successful = true;
      const timestamp = Math.floor(Date.now() / 1000) - 2 * 60 * 60; // 2 hours ago
      const nonce = await agentStaking.oracleNonces(oracle.address);

      const messageHash = ethers.solidityPackedKeccak256(
        ["address", "uint256", "bool", "uint256", "uint256"],
        [agentWallet.address, accuracy, successful, timestamp, nonce]
      );
      const ethSignedMessageHash = ethers.solidityPackedKeccak256(
        ["string", "bytes32"],
        ["\x19Ethereum Signed Message:\n32", messageHash]
      );
      const signature = await oracle.signMessage(ethers.getBytes(ethSignedMessageHash));

      await expect(
        agentStaking.connect(oracle).updateAgentPerformanceWithSignature(
          agentWallet.address,
          accuracy,
          successful,
          timestamp,
          nonce,
          signature
        )
      ).to.be.revertedWith("Signature expired");
    });

    it("should reject invalid nonce", async function () {
      const accuracy = 85;
      const successful = true;
      const nonce = BigInt(await agentStaking.oracleNonces(oracle.address)) + 1n;

      // Get current block timestamp
      const block = await ethers.provider.getBlock("latest");
      const timestamp = block.timestamp + 3600; // 1 hour in future

      const messageHash = ethers.solidityPackedKeccak256(
        ["address", "uint256", "bool", "uint256", "uint256"],
        [agentWallet.address, accuracy, successful, timestamp, nonce]
      );
      const ethSignedMessageHash = ethers.solidityPackedKeccak256(
        ["string", "bytes32"],
        ["\x19Ethereum Signed Message:\n32", messageHash]
      );
      const signature = await oracle.signMessage(ethers.getBytes(ethSignedMessageHash));

      await expect(
        agentStaking.connect(oracle).updateAgentPerformanceWithSignature(
          agentWallet.address,
          accuracy,
          successful,
          timestamp,
          nonce,
          signature
        )
      ).to.be.revertedWith("Invalid nonce");
    });

    it("should enforce time delay for performance updates", async function () {
      // First update should succeed
      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        80,
        true
      );

      // Immediate second update should fail
      await expect(
        agentStaking.connect(oracle).updateAgentPerformance(
          agentWallet.address,
          85,
          true
        )
      ).to.be.revertedWith("Update too frequent");

      // Fast forward past delay (1 hour)
      await ethers.provider.send("evm_increaseTime", [60 * 60 + 1]);
      await ethers.provider.send("evm_mine");

      // Update after delay should succeed
      await expect(
        agentStaking.connect(oracle).updateAgentPerformance(
          agentWallet.address,
          85,
          true
        )
      ).to.not.be.reverted;
    });

    it("should allow oracle rotation after period", async function () {
      const newOracle = attacker;

      // First call should succeed (no rotation period set initially)
      await expect(
        agentStaking.rotateOracle(oracle.address, newOracle.address)
      ).to.emit(agentStaking, "OracleRotated");
    });

    it("should update oracle reputation on successful updates", async function () {
      await agentStaking.connect(oracle).updateAgentPerformance(
        agentWallet.address,
        80,
        true
      );

      const reputation = await agentStaking.oracleReputations(oracle.address);
      expect(reputation.totalUpdates).to.equal(1);
      expect(reputation.successfulUpdates).to.equal(1);
      expect(reputation.reputationScore).to.equal(100);
    });

    it("should allow owner to report disputed oracle", async function () {
      await expect(
        agentStaking.reportDisputedOracle(oracle.address, "Evidence")
      ).to.not.be.reverted;

      const reputation = await agentStaking.oracleReputations(oracle.address);
      expect(reputation.disputedUpdates).to.equal(1);
    });

    it("should allow owner to set performance update delay", async function () {
      const newDelay = 2 * 60 * 60; // 2 hours

      await agentStaking.setPerformanceUpdateDelay(newDelay);

      const delay = await agentStaking.performanceUpdateDelay();
      expect(delay).to.equal(newDelay);
    });

    it("should allow owner to set oracle rotation period", async function () {
      const newPeriod = 60 * 24 * 60 * 60; // 60 days

      await agentStaking.setOracleRotationPeriod(newPeriod);

      const period = await agentStaking.oracleRotationPeriod();
      expect(period).to.equal(newPeriod);
    });
  });
});
