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
  let token, staking, owner, agent, staker, reporter;
  const STAKE = ethers.parseEther("1000");
  const LOCK = 30 * 24 * 60 * 60; // the contract requires >= 1 day

  beforeEach(async function () {
    [owner, agent, staker, reporter] = await ethers.getSigners();

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
    it("pays a share of what this report slashed", async function () {
      await makeStakes(3);
      const before = await token.balanceOf(reporter.address);

      await staking.connect(reporter).reportMaliciousAgent(agent.address, "bad output");

      const slashed = (STAKE * DEFAULT_SLASH_PCT) / 100n * 3n;
      const expectedReward = (slashed * (await staking.slashReporterReward())) / 10000n;

      expect((await token.balanceOf(reporter.address)) - before).to.equal(expectedReward);
    });

    it("pays nothing for a report that slashes nothing", async function () {
      // Everything already slashed by an earlier incident; this report causes no new loss.
      await makeStakes(3);
      await staking.checkAndSlashAgent(agent.address);
      const before = await token.balanceOf(reporter.address);

      await staking.connect(reporter).reportMaliciousAgent(agent.address, "same again");

      // The old code re-derived a total from the agent's whole SLASHED history and paid on
      // it, so a second reporter was rewarded for someone else's report.
      expect(await token.balanceOf(reporter.address)).to.equal(before);
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
