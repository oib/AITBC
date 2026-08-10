// SC-05: distributeAgentEarnings must credit every reward it counts, and must not scan
// every stake for every staker.
//
// The old implementation looped stakers, and for each one scanned agentStakes[agent] to
// find an ACTIVE stake to attach the reward to. Two consequences:
//
//   1. O(stakers x stakes). Unbounded, and eventually un-executable, which permanently
//      blocks distribution for that agent.
//   2. `totalDistributed` was incremented whether or not the scan found an ACTIVE stake.
//      A staker still listed in the pool with no active stake had their reward counted as
//      distributed while it was written nowhere.
//
// Rewards now go to a per-staker pending balance, claimed via claimPoolRewards.

import { expect } from "chai";
import { network } from "hardhat";
const { ethers } = await network.getOrCreate();

describe("AgentStaking earnings distribution (SC-05)", function () {
  let token, staking, owner, agent, stakerA, stakerB, distributor;
  const STAKE = ethers.parseEther("1000");
  const EARNINGS = ethers.parseEther("100");
  const LOCK = 30 * 24 * 60 * 60; // 30 days; the contract requires >= 1 day

  beforeEach(async function () {
    [owner, agent, stakerA, stakerB, distributor] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AIToken");
    token = await Token.deploy(ethers.parseEther("10000000"));
    await token.waitForDeployment();

    const Staking = await ethers.getContractFactory("AgentStaking");
    staking = await Staking.deploy(await token.getAddress(), owner.address);
    await staking.waitForDeployment();

    for (const who of [stakerA, stakerB, distributor]) {
      await token.transfer(who.address, ethers.parseEther("100000"));
      await token.connect(who).approve(await staking.getAddress(), ethers.parseEther("100000"));
    }
  });

  async function ensureAgent() {
    const metrics = await staking.agentMetrics(agent.address);
    if (metrics.agentWallet === ethers.ZeroAddress) {
      await staking.addSupportedAgent(agent.address, 0); // BRONZE
    }
  }

  async function registerAndStake(staker, amount) {
    await ensureAgent();
    await staking.connect(staker).stakeOnAgent(agent.address, amount, LOCK, false);
  }

  it("credits every reward it counts as distributed", async function () {
    await registerAndStake(stakerA, STAKE);
    await registerAndStake(stakerB, STAKE);

    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);

    const pendingA = await staking.pendingPoolRewards(agent.address, stakerA.address);
    const pendingB = await staking.pendingPoolRewards(agent.address, stakerB.address);
    const metrics = await staking.agentMetrics(agent.address);

    // The invariant the old code broke: what was reported distributed must equal what
    // was actually credited.
    expect(pendingA + pendingB).to.equal(metrics.totalRewardsDistributed);
    expect(pendingA).to.be.greaterThan(0n);
    expect(pendingB).to.be.greaterThan(0n);
  });

  it("splits earnings in proportion to stake", async function () {
    await registerAndStake(stakerA, STAKE * 3n);
    await registerAndStake(stakerB, STAKE);

    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);

    const pendingA = await staking.pendingPoolRewards(agent.address, stakerA.address);
    const pendingB = await staking.pendingPoolRewards(agent.address, stakerB.address);

    expect(pendingA).to.equal(pendingB * 3n);
  });

  it("pays the claimed amount and zeroes the balance", async function () {
    await registerAndStake(stakerA, STAKE);
    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);

    const pending = await staking.pendingPoolRewards(agent.address, stakerA.address);
    const before = await token.balanceOf(stakerA.address);

    await staking.connect(stakerA).claimPoolRewards(agent.address);

    expect(await token.balanceOf(stakerA.address)).to.equal(before + pending);
    expect(await staking.pendingPoolRewards(agent.address, stakerA.address)).to.equal(0);
  });

  it("refuses a second claim", async function () {
    await registerAndStake(stakerA, STAKE);
    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);
    await staking.connect(stakerA).claimPoolRewards(agent.address);

    await expect(staking.connect(stakerA).claimPoolRewards(agent.address)).to.be.revertedWith(
      "No rewards to claim",
    );
  });

  it("accumulates across multiple distributions", async function () {
    await registerAndStake(stakerA, STAKE);

    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);
    const afterFirst = await staking.pendingPoolRewards(agent.address, stakerA.address);
    await staking.connect(distributor).distributeAgentEarnings(agent.address, EARNINGS);
    const afterSecond = await staking.pendingPoolRewards(agent.address, stakerA.address);

    expect(afterSecond).to.equal(afterFirst * 2n);
  });

  it("distribution cost does not grow with the number of stakes", async function () {
    // The DoS: the old inner scan walked every stake for the agent, for every staker.
    await registerAndStake(stakerA, STAKE);
    const gasFewStakes = await staking
      .connect(distributor)
      .distributeAgentEarnings.estimateGas(agent.address, EARNINGS);

    // Same single staker, many more stake records on the same agent.
    for (let i = 0; i < 8; i++) {
      // The contract enforces a cooldown between stakes from one address.
      await ethers.provider.send("evm_increaseTime", [86400]);
      await ethers.provider.send("evm_mine", []);
      await staking.connect(stakerA).stakeOnAgent(agent.address, ethers.parseEther("200"), LOCK, false);
    }

    const gasManyStakes = await staking
      .connect(distributor)
      .distributeAgentEarnings.estimateGas(agent.address, EARNINGS);

    // Staker count is unchanged, so cost should be flat regardless of stake count.
    expect(gasManyStakes).to.be.lessThan(gasFewStakes + 5000n);
  });
});
