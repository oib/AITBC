// SC-06: slashing must be bounded, must not transfer once per stake, and must pay the
// reporter for what the report actually slashed.
//
// _slashAllStakesForAgent looped over every stake ever recorded for an agent with no
// bound, calling paymentToken.transfer inside the loop. Anyone can stake on an agent, so
// an agent could accumulate enough stakes to push slashing past the block gas limit and
// become permanently un-slashable -- the stakes protecting against its misbehaviour would
// be the thing preventing that misbehaviour from being punished.
//
// reportMaliciousAgent compounded it: the reporter's reward came from
// _calculateTotalSlashed, which walked every SLASHED stake the agent had ever accumulated
// and applied defaultSlashingPercentage to the already-reduced amounts. A reporter was
// paid on stakes slashed in earlier, unrelated incidents.

import { expect } from "chai";
import { network } from "hardhat";
const { ethers } = await network.getOrCreate();

describe("AgentStaking slashing (SC-06)", function () {
  let token, staking, owner, agent, staker, reporter, oracle, attacker;
  const STAKE = ethers.parseEther("1000");
  const LOCK = 30 * 24 * 60 * 60; // the contract requires >= 1 day

  beforeEach(async function () {
    [owner, agent, staker, reporter, oracle, attacker] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AIToken");
    token = await Token.deploy(ethers.parseEther("10000000"));
    await token.waitForDeployment();

    const Staking = await ethers.getContractFactory("AgentStaking");
    staking = await Staking.deploy(await token.getAddress(), owner.address);
    await staking.waitForDeployment();

    await token.transfer(staker.address, ethers.parseEther("1000000"));
    await token.connect(staker).approve(await staking.getAddress(), ethers.parseEther("1000000"));

    // Rate limits exist to slow real users down; they only get in the way of building the
    // many-stakes case this suite is about.
    await staking.setStakeCooldown(0);
    await staking.setMaxStakesPerDay(100);
    await staking.setMaxStakesPerUser(500);

    await staking.addSupportedAgent(agent.address, 0); // BRONZE
    // #1460: reportMaliciousAgent is oracle-gated.
    await staking.addOracle(oracle.address);
  });

  async function makeStakes(count, amount = STAKE) {
    for (let i = 0; i < count; i++) {
      await staking.connect(staker).stakeOnAgent(agent.address, amount, LOCK, false);
    }
  }

  // A fresh agent has averageAccuracy 0, below the default minimum of 50, so
  // checkAndSlashAgent slashes on the first call.
  const DEFAULT_SLASH_PCT = 10n;

  describe("bounded work per call", function () {
    it("slashes at most maxSlashBatch stakes in one call", async function () {
      await staking.setMaxSlashBatch(2);
      await makeStakes(5);

      await staking.checkAndSlashAgent(agent.address);

      expect(await staking.slashProgress(agent.address)).to.equal(2);
    });

    it("announces that stakes remain", async function () {
      await staking.setMaxSlashBatch(2);
      await makeStakes(5);

      await expect(staking.checkAndSlashAgent(agent.address))
        .to.emit(staking, "SlashingIncomplete")
        .withArgs(agent.address, 2, 3);
    });

    it("finishes the job across continueSlashing calls", async function () {
      await staking.setMaxSlashBatch(2);
      await makeStakes(5);

      await staking.checkAndSlashAgent(agent.address);
      await staking.connect(reporter).continueSlashing(agent.address);
      await staking.connect(reporter).continueSlashing(agent.address);

      expect(await staking.slashProgress(agent.address)).to.equal(5);
      for (let i = 0; i < 5; i++) {
        const stakeId = await staking.agentStakes(agent.address, i);
        // enum StakeStatus { ACTIVE, UNBONDING, COMPLETED, SLASHED }
        expect((await staking.stakes(stakeId)).status).to.equal(3); // SLASHED
      }
    });

    it("slashes the same total whether it takes one call or several", async function () {
      await makeStakes(4);
      const before = await token.balanceOf(owner.address);
      await staking.checkAndSlashAgent(agent.address); // one call, batch of 100
      const inOneCall = (await token.balanceOf(owner.address)) - before;

      // Same setup, but forced to take three calls.
      const Staking = await ethers.getContractFactory("AgentStaking");
      const staking2 = await Staking.deploy(await token.getAddress(), owner.address);
      await staking2.waitForDeployment();
      await token.connect(staker).approve(await staking2.getAddress(), ethers.parseEther("1000000"));
      await staking2.setStakeCooldown(0);
      await staking2.setMaxStakesPerDay(100);
      await staking2.addSupportedAgent(agent.address, 0);
      await staking2.setMaxSlashBatch(2);
      for (let i = 0; i < 4; i++) {
        await staking2.connect(staker).stakeOnAgent(agent.address, STAKE, LOCK, false);
      }

      const before2 = await token.balanceOf(owner.address);
      await staking2.checkAndSlashAgent(agent.address);
      await staking2.connect(reporter).continueSlashing(agent.address);
      const inThreeCalls = (await token.balanceOf(owner.address)) - before2;

      expect(inThreeCalls).to.equal(inOneCall);
    });

    it("refuses to continue when there is nothing left", async function () {
      await makeStakes(2);
      await staking.checkAndSlashAgent(agent.address);

      await expect(staking.connect(reporter).continueSlashing(agent.address)).to.be.revertedWith(
        "Nothing left to slash",
      );
    });

    it("lets anyone continue, so completion does not depend on the owner", async function () {
      await staking.setMaxSlashBatch(1);
      await makeStakes(2);
      await staking.checkAndSlashAgent(agent.address);

      await expect(staking.connect(reporter).continueSlashing(agent.address)).to.not.revert(ethers);
    });

    it("does not grow un-slashable as stakes accumulate", async function () {
      // The DoS: cost per call must stay flat once past the batch size.
      await staking.setMaxSlashBatch(5);
      await makeStakes(40);

      const gas = await staking.checkAndSlashAgent.estimateGas(agent.address);
      await staking.checkAndSlashAgent(agent.address);
      const gasLater = await staking.continueSlashing.estimateGas(agent.address);

      // Both walk 5 stakes; neither depends on the 40.
      expect(gasLater).to.be.lessThan(gas * 2n);
    });
  });

  describe("token movement", function () {
    it("transfers the slashed total once, not once per stake", async function () {
      await makeStakes(4);
      const before = await token.balanceOf(owner.address);

      const receipt = await (await staking.checkAndSlashAgent(agent.address)).wait();

      // Four stakes slashed...
      const slashEvents = receipt.logs.filter((log) => {
        try {
          return staking.interface.parseLog(log)?.name === "StakeSlashed";
        } catch {
          return false;
        }
      });
      expect(slashEvents).to.have.lengthOf(4);

      // ...but a single Transfer out of the staking contract.
      const transfersOut = receipt.logs.filter((log) => {
        try {
          const parsed = token.interface.parseLog(log);
          return parsed?.name === "Transfer" && parsed.args[0] === staking.target;
        } catch {
          return false;
        }
      });
      expect(transfersOut).to.have.lengthOf(1);

      const expected = (STAKE * DEFAULT_SLASH_PCT) / 100n * 4n;
      expect((await token.balanceOf(owner.address)) - before).to.equal(expected);
    });

    it("reduces each slashed stake by the slashing percentage", async function () {
      await makeStakes(2);
      await staking.checkAndSlashAgent(agent.address);

      const stakeId = await staking.agentStakes(agent.address, 0);
      const stake = await staking.stakes(stakeId);

      expect(stake.amount).to.equal(STAKE - (STAKE * DEFAULT_SLASH_PCT) / 100n);
    });
  });

  describe("reporter reward", function () {
    // #1460: reports require an authorized oracle AND at least one performance
    // submission -- a fresh agent's averageAccuracy is 0 by initialization,
    // not by evidence, so it must not be slashable through the report path.
    async function reportableAgent(accuracy = 30) {
      await staking.connect(oracle).updateAgentPerformance(agent.address, accuracy, false);
    }

    it("pays a share of what this report slashed", async function () {
      await makeStakes(3);
      await reportableAgent();
      const before = await token.balanceOf(oracle.address);

      await staking.connect(oracle).reportMaliciousAgent(agent.address, "bad output");

      const slashed = (STAKE * DEFAULT_SLASH_PCT) / 100n * 3n;
      const expectedReward = (slashed * (await staking.slashReporterReward())) / 10000n;

      expect((await token.balanceOf(oracle.address)) - before).to.equal(expectedReward);
    });

    it("pays the reward only out of the proceeds this report slashed", async function () {
      // #1460: the owner's share is totalSlashed - reward and the reporter's
      // is reward -- together exactly the slashed total, so the reward can
      // never draw on pooled principal of untouched stakes.
      await makeStakes(3);
      await reportableAgent();

      const ownerBefore = await token.balanceOf(owner.address);
      const oracleBefore = await token.balanceOf(oracle.address);
      await staking.connect(oracle).reportMaliciousAgent(agent.address, "bad output");

      const slashed = (STAKE * DEFAULT_SLASH_PCT) / 100n * 3n;
      const expectedReward = (slashed * (await staking.slashReporterReward())) / 10000n;

      expect((await token.balanceOf(oracle.address)) - oracleBefore).to.equal(expectedReward);
      expect((await token.balanceOf(owner.address)) - ownerBefore).to.equal(slashed - expectedReward);
    });

    it("rejects reports from non-oracles", async function () {
      await makeStakes(1);
      await reportableAgent();

      await expect(
        staking.connect(attacker).reportMaliciousAgent(agent.address, "bad output"),
      ).to.be.revertedWith("Not authorized oracle");
      await expect(
        staking.connect(reporter).reportMaliciousAgent(agent.address, "bad output"),
      ).to.be.revertedWith("Not authorized oracle");
    });

    it("rejects a report on an agent with no performance submissions", async function () {
      // Fresh agent: averageAccuracy is 0 (< defaultMinAccuracy 50) purely by
      // initialization. Before #1460 anyone could slash all its stakes here.
      await makeStakes(1);

      await expect(
        staking.connect(oracle).reportMaliciousAgent(agent.address, "fresh agent"),
      ).to.be.revertedWith("No performance submissions");
    });

    it("pays nothing for a report that slashes nothing", async function () {
      // Everything already slashed by an earlier incident; this report causes no new loss.
      await makeStakes(3);
      await reportableAgent();
      await staking.checkAndSlashAgent(agent.address);
      const before = await token.balanceOf(oracle.address);

      await staking.connect(oracle).reportMaliciousAgent(agent.address, "same again");

      // The old code re-derived a total from the agent's whole SLASHED history and paid on
      // it, so a second reporter was rewarded for someone else's report.
      expect(await token.balanceOf(oracle.address)).to.equal(before);
    });
  });

  describe("slashed remainder exit (#1457)", function () {
    // SLASHED used to be terminal: the un-slashed remainder was stranded
    // forever and pool/metrics accounting never unwound. withdrawSlashedStake
    // now pays the remainder after unbondingPeriod measured from slashedAt.

    it("pays the staker exactly the un-slashed remainder, not 100%", async function () {
      await makeStakes(1);
      const stakeId = await staking.agentStakes(agent.address, 0);

      const ownerBefore = await token.balanceOf(owner.address);
      const stakerBefore = await token.balanceOf(staker.address);
      await staking.slashStake(stakeId, 10, "manual");

      // Exactly 10% confiscated to the owner; nothing to the staker yet.
      const expectedSlash = (STAKE * 10n) / 100n;
      expect((await token.balanceOf(owner.address)) - ownerBefore).to.equal(expectedSlash);
      expect(await token.balanceOf(staker.address)).to.equal(stakerBefore);

      // Accounting unwound by the confiscated share only.
      const metrics = await staking.getAgentMetrics(agent.address);
      expect(metrics[0]).to.equal(STAKE - expectedSlash);
      const pool = await staking.getStakingPool(agent.address);
      expect(pool[0]).to.equal(STAKE - expectedSlash);

      // Enforces the unbonding delay from slashedAt.
      await ethers.provider.send("evm_increaseTime", [6 * 24 * 60 * 60]);
      await expect(staking.connect(staker).withdrawSlashedStake(stakeId)).to.be.revertedWith(
        "Unbonding period not ended",
      );

      await ethers.provider.send("evm_increaseTime", [2 * 24 * 60 * 60]);
      await staking.connect(staker).withdrawSlashedStake(stakeId);

      const remainder = STAKE - expectedSlash;
      expect((await token.balanceOf(staker.address)) - stakerBefore).to.equal(remainder);

      // Fully unwound.
      const metricsAfter = await staking.getAgentMetrics(agent.address);
      expect(metricsAfter[0]).to.equal(0n);
      const poolAfter = await staking.getStakingPool(agent.address);
      expect(poolAfter[0]).to.equal(0n);

      const stake = await staking.stakes(stakeId);
      expect(stake.status).to.equal(2); // COMPLETED
      expect(stake.amount).to.equal(remainder);

      // Terminal: no second withdrawal, no normal unbond path.
      await expect(staking.connect(staker).withdrawSlashedStake(stakeId)).to.be.revertedWith(
        "Stake not slashed",
      );
      await expect(staking.connect(staker).unbondStake(stakeId)).to.be.revertedWith("Stake not active");
    });

    it("recovers remainders for every stake slashed by checkAndSlashAgent", async function () {
      await makeStakes(3);
      const unbonding = await staking.unbondingPeriod();

      await staking.checkAndSlashAgent(agent.address); // owner = deployer signer
      await ethers.provider.send("evm_increaseTime", [Number(unbonding) + 1]);

      const metrics = await staking.getAgentMetrics(agent.address);
      const expectedRemainderEach = STAKE - (STAKE * DEFAULT_SLASH_PCT) / 100n;
      expect(metrics[0]).to.equal(expectedRemainderEach * 3n);

      const stakerBefore = await token.balanceOf(staker.address);
      for (let i = 0; i < 3; i++) {
        const stakeId = await staking.agentStakes(agent.address, i);
        await staking.connect(staker).withdrawSlashedStake(stakeId);
      }
      expect((await token.balanceOf(staker.address)) - stakerBefore).to.equal(
        expectedRemainderEach * 3n,
      );

      const metricsAfter = await staking.getAgentMetrics(agent.address);
      expect(metricsAfter[0]).to.equal(0n);
      const poolAfter = await staking.getStakingPool(agent.address);
      expect(poolAfter[0]).to.equal(0n);
    });

    it("rejects withdrawal by a non-owner and on non-slashed stakes", async function () {
      await makeStakes(1);
      const stakeId = await staking.agentStakes(agent.address, 0);
      await staking.slashStake(stakeId, 10, "manual");

      await expect(staking.connect(reporter).withdrawSlashedStake(stakeId)).to.be.revertedWith(
        "Not stake owner",
      );

      await makeStakes(1); // second stake stays ACTIVE
      const activeId = await staking.agentStakes(agent.address, 1);
      await expect(staking.connect(staker).withdrawSlashedStake(activeId)).to.be.revertedWith(
        "Stake not slashed",
      );
    });

    it("does not let an approved appeal resurrect a withdrawn stake", async function () {
      await makeStakes(1);
      const stakeId = await staking.agentStakes(agent.address, 0);
      await staking.slashStake(stakeId, 10, "manual");

      await staking.connect(staker).appealSlashing(stakeId, "appeal");
      const unbonding = await staking.unbondingPeriod();
      await ethers.provider.send("evm_increaseTime", [Number(unbonding) + 1]);
      await staking.connect(staker).withdrawSlashedStake(stakeId);

      await expect(staking.resolveSlashAppeal(stakeId, true)).to.be.revertedWith(
        "Stake no longer slashed",
      );
    });
  });

  describe("batch size control", function () {
    it("is owner-only", async function () {
      await expect(staking.connect(reporter).setMaxSlashBatch(5)).to.revert(ethers);
    });

    it("rejects zero, which would stall slashing entirely", async function () {
      await expect(staking.setMaxSlashBatch(0)).to.be.revertedWith("Batch size must be positive");
    });

    it("reports the change", async function () {
      await expect(staking.setMaxSlashBatch(7))
        .to.emit(staking, "MaxSlashBatchUpdated")
        .withArgs(100, 7);
    });
  });
});
