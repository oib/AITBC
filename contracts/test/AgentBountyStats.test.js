// SC-12: getBountyStats must be O(1) and its counters must track real bounty states.
//
// getBountyStats used to loop over every bounty ever created. That loop grows without
// bound and eventually exceeds the block gas limit -- and because it is a `view`, another
// contract calling it on-chain fails with it. It now reads counters maintained by
// _setBountyStatus.
//
// The risk in that trade is drift: counters that disagree with the bounties they
// summarise. These tests drive real status transitions and check the counters after each.

import { expect } from "chai";
import { network } from "hardhat";
const { ethers } = await network.getOrCreate();

describe("AgentBounty statistics (SC-12)", function () {
  let token, bounty, owner, creator;
  const REWARD = ethers.parseEther("1000");

  beforeEach(async function () {
    [owner, creator] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AIToken");
    token = await Token.deploy(ethers.parseEther("10000000"));
    await token.waitForDeployment();

    // AgentBounty only stores the verifier address; none of the paths exercised here
    // call into it, and PerformanceVerifier needs its own three-contract dependency
    // chain. A plain non-zero address keeps this test on the statistics.
    const Bounty = await ethers.getContractFactory("AgentBounty");
    bounty = await Bounty.deploy(await token.getAddress(), owner.address);
    await bounty.waitForDeployment();

    await bounty.authorizeCreator(creator.address);
    await token.transfer(creator.address, ethers.parseEther("1000000"));
    await token.connect(creator).approve(await bounty.getAddress(), ethers.parseEther("1000000"));
  });

  async function createOne() {
    const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;
    const tx = await bounty.connect(creator).createBounty(
      "t",
      "d",
      REWARD,
      2, // GOLD
      ethers.encodeBytes32String("criteria"),
      90,
      deadline,
      5,
      false,
    );
    await tx.wait();
  }

  it("starts at zero", async function () {
    const stats = await bounty.getBountyStats();
    expect(stats.totalBounties).to.equal(0);
    expect(stats.activeBounties).to.equal(0);
    expect(stats.completedBounties).to.equal(0);
    expect(stats.totalValueLocked).to.equal(0);
  });

  it("counts an active bounty and its value", async function () {
    await createOne();
    const stats = await bounty.getBountyStats();
    expect(stats.totalBounties).to.equal(1);
    expect(stats.activeBounties).to.equal(1);
    expect(stats.totalValueLocked).to.equal(REWARD);
  });

  it("counters agree with a full scan of bounty states", async function () {
    // The invariant the old implementation got for free by scanning, and the one the
    // counters could plausibly break.
    for (let i = 0; i < 5; i++) await createOne();

    const total = await bounty.bountyCounter();
    let scannedActive = 0n;
    let scannedValue = 0n;
    for (let i = 0; i < total; i++) {
      const b = await bounty.getBounty(i);
      if (b.status === 1n) {
        scannedActive += 1n;
        scannedValue += b.rewardAmount;
      }
    }

    expect(await bounty.activeBountyCount()).to.equal(scannedActive);
    expect(await bounty.trackedBountyValue()).to.equal(scannedValue);
  });

  it("expiry moves a bounty out of the active count", async function () {
    await createOne();
    expect(await bounty.activeBountyCount()).to.equal(1);

    await ethers.provider.send("evm_increaseTime", [86401]);
    await ethers.provider.send("evm_mine", []);
    await bounty.expireBounty(0);

    expect(await bounty.activeBountyCount()).to.equal(0);
    // Value follows the bounty out of the active/completed set.
    expect(await bounty.trackedBountyValue()).to.equal(0);
  });

  it("stays O(1) as bounty count grows", async function () {
    // The point of the change: gas for the getter must not scale with bountyCounter.
    await createOne();
    const gasOne = await bounty.getBountyStats.estimateGas();

    for (let i = 0; i < 10; i++) await createOne();
    const gasMany = await bounty.getBountyStats.estimateGas();

    // Allow a little slack for calldata/warm-storage differences, but nothing
    // proportional to an 11x increase in bounties.
    expect(gasMany).to.be.lessThan(gasOne + 5000n);
  });
});
