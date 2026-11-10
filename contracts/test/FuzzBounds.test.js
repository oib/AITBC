import { expect } from "chai";
import { network } from "hardhat";
const { ethers, networkHelpers } = await network.getOrCreate();
const { time } = networkHelpers;

// Fuzz/bounds suite for the payment + escrow + staking amount and price
// inputs (batch v3, item 16). Mocha has no built-in fuzzer, so inputs come
// from a seeded PRNG (mulberry32) — deterministic across runs, so a failure
// reproduces exactly. Assertions encode the CORRECT behavior:
//   - in-range amounts never revert for a valid caller,
//   - zero / below-min / above-max amounts are rejected,
//   - no arithmetic overflow on fee math (amount * feeBps stays bounded),
//   - an escrow/payment settles at most once.
// Any failure on current code is evidence of a defect — see comments.

const ESCROW_TYPE = { Standard: 0, PerformanceBased: 1, TimeBased: 2, Conditional: 3 };
const RELEASE_CONDITION = { Immediate: 0, Manual: 1, Performance: 2, TimeBased: 3, DisputeResolution: 4 };

const ES_TYPE = { Standard: 0, MultiSignature: 1, TimeLocked: 2, Conditional: 3, PerformanceBased: 4, MilestoneBased: 5, Emergency: 6, ProtectedCompute: 7 };
const ES_CONDITION = { Manual: 0, Automatic: 1, OracleVerified: 2, PerformanceMet: 3, TimeBased: 4, MultiSignature: 5, Emergency: 6 };

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let rand;
function rnd() { return rand(); }
function randInt(n) { return Math.floor(rnd() * n); }
// Uniform-ish bigint in [0, max)
function randBigInt(max) {
  const n = BigInt(max);
  const nBytes = Math.ceil(n.toString(2).length / 8) + 1;
  let v;
  do {
    const arr = new Uint8Array(nBytes);
    for (let i = 0; i < nBytes; i++) arr[i] = Math.floor(rnd() * 256);
    v = BigInt("0x" + Buffer.from(arr).toString("hex"));
  } while (v >= n);
  return v;
}
function hash32(label) {
  return ethers.keccak256(ethers.toUtf8Bytes(label));
}

describe("Fuzz bounds: PaymentProcessor + EscrowService + AgentStaking", function () {
  this.timeout(300000);

  let token, aiPowerRental, paymentProcessor, escrowService, agentStaking;
  let deployer, payer, payee, verifier, stranger, agentWallet;
  const FUZZ_RUNS = 80;

  beforeEach(async function () {
    rand = mulberry32(0xa17c);
    [deployer, payer, payee, verifier, stranger, agentWallet] = await ethers.getSigners();

    const AIToken = await ethers.getContractFactory("AIToken");
    // Generous supply so fuzzed amounts never hit the balance wall — the
    // bounds under test are the contract's own min/max checks.
    token = await AIToken.deploy(ethers.parseUnits("10000000", 18));
    await token.waitForDeployment();

    const MockVerifier = await ethers.getContractFactory("MockVerifier");
    const zkVerifier = await MockVerifier.deploy();
    await zkVerifier.waitForDeployment();
    const groth16Verifier = await MockVerifier.deploy();
    await groth16Verifier.waitForDeployment();

    const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
    aiPowerRental = await AIPowerRental.deploy(
      await token.getAddress(),
      await zkVerifier.getAddress(),
      await groth16Verifier.getAddress()
    );
    await aiPowerRental.waitForDeployment();

    const PaymentProcessor = await ethers.getContractFactory("PaymentProcessor");
    paymentProcessor = await PaymentProcessor.deploy(
      await token.getAddress(),
      await aiPowerRental.getAddress()
    );
    await paymentProcessor.waitForDeployment();

    const EscrowService = await ethers.getContractFactory("EscrowService");
    escrowService = await EscrowService.deploy(
      await token.getAddress(),
      await aiPowerRental.getAddress(),
      await paymentProcessor.getAddress()
    );
    await escrowService.waitForDeployment();

    const AgentStaking = await ethers.getContractFactory("AgentStaking");
    agentStaking = await AgentStaking.deploy(
      await token.getAddress(),
      await zkVerifier.getAddress()
    );
    await agentStaking.waitForDeployment();
    await agentStaking.addSupportedAgent(agentWallet.address, 0);

    await paymentProcessor.authorizePayer(payer.address);
    await paymentProcessor.authorizePayee(payee.address);
    await paymentProcessor.authorizeReleaseVerifier(verifier.address);

    await token.mint(payer.address, ethers.parseUnits("5000000", 18));
    await token
      .connect(payer)
      .approve(await paymentProcessor.getAddress(), ethers.MaxUint256);
    await token
      .connect(payer)
      .approve(await escrowService.getAddress(), ethers.MaxUint256);
    await token
      .connect(payer)
      .approve(await agentStaking.getAddress(), ethers.MaxUint256);
  });

  // ---------------------------------------------------------------
  // PaymentProcessor.createPayment — amount bounds + settle-once
  // ---------------------------------------------------------------
  describe("PaymentProcessor.createPayment fuzz", function () {
    it("accepts every in-range amount and rejects out-of-range amounts", async function () {
      const minAmt = await paymentProcessor.minPaymentAmount();
      const maxAmt = await paymentProcessor.maxPaymentAmount();
      const span = maxAmt - minAmt;

      for (let i = 0; i < FUZZ_RUNS; i++) {
        const amount = minAmt + randBigInt(span);
        const condition = randInt(5);
        const tx = await paymentProcessor.connect(payer).createPayment(
          payee.address,
          amount,
          hash32(`agreement-${i}`),
          `fuzz payment ${i}`,
          condition
        );
        const receipt = await tx.wait();
        expect(receipt.status).to.equal(1);

        // Every 4th payment goes through confirm + release to exercise the
        // settle path under fuzzed amounts. paymentCounter increments by 1
        // per createPayment and nothing else touches it in this test, so
        // the id equals the number of payments created so far.
        if (i % 4 === 0) {
          const paymentId = i;
          const payeeBefore = await token.balanceOf(payee.address);
          await paymentProcessor.connect(payer).confirmPayment(paymentId, hash32(`tx-${i}`));
          if (condition === RELEASE_CONDITION.TimeBased) {
            await time.increase(3700);
          }
          if (condition === RELEASE_CONDITION.Performance || condition === RELEASE_CONDITION.DisputeResolution) {
            await paymentProcessor.connect(verifier).approveRelease(paymentId);
          }
          if (condition !== RELEASE_CONDITION.Immediate) {
            // Immediate already released inside confirmPayment.
            const releaser = condition === RELEASE_CONDITION.Manual ? payer : payee;
            await paymentProcessor.connect(releaser).releasePayment(paymentId);
          }
          expect(await token.balanceOf(payee.address) - payeeBefore).to.equal(amount);
          // (a) no double release
          await expect(
            paymentProcessor.connect(payee).releasePayment(paymentId)
          ).to.be.revertedWith("Payment not ready for release");
        }
      }
    });

    it("rejects zero, below-minimum and above-maximum amounts", async function () {
      const minAmt = await paymentProcessor.minPaymentAmount();
      const maxAmt = await paymentProcessor.maxPaymentAmount();
      const badAmounts = [
        0n,
        minAmt - 1n,
        maxAmt + 1n,
        maxAmt + randBigInt(maxAmt),
      ];
      for (const amount of badAmounts) {
        await expect(
          paymentProcessor.connect(payer).createPayment(
            payee.address,
            amount,
            ethers.ZeroHash,
            "bad",
            RELEASE_CONDITION.Manual
          )
        ).to.revert(ethers);
      }
      // Sanity: a valid amount still succeeds after the rejects.
      await expect(
        paymentProcessor.connect(payer).createPayment(
          payee.address,
          minAmt,
          ethers.ZeroHash,
          "ok",
          RELEASE_CONDITION.Manual
        )
      ).to.not.revert(ethers);
    });

    it("fee math cannot overflow: total pull stays amount + bounded fees", async function () {
      const minAmt = await paymentProcessor.minPaymentAmount();
      const maxAmt = await paymentProcessor.maxPaymentAmount();
      const platformFeeBps = await paymentProcessor.platformFeePercentage();
      const disputeFeeBps = await paymentProcessor.disputeResolutionFee();

      for (let i = 0; i < 20; i++) {
        const amount = minAmt + randBigInt(maxAmt - minAmt);
        const before = await token.balanceOf(await paymentProcessor.getAddress());
        await paymentProcessor.connect(payer).createPayment(
          payee.address,
          amount,
          ethers.ZeroHash,
          "fee fuzz",
          RELEASE_CONDITION.Manual
        );
        const expectedPull =
          amount + (amount * platformFeeBps) / 10000n + (amount * disputeFeeBps) / 10000n;
        expect(await token.balanceOf(await paymentProcessor.getAddress()) - before).to.equal(expectedPull);
      }
    });
  });

  // ---------------------------------------------------------------
  // PaymentProcessor.createEscrow / releaseEscrow / refundEscrow
  // ---------------------------------------------------------------
  describe("PaymentProcessor escrow fuzz", function () {
    it("settles each escrow at most once across fuzzed type/amount inputs", async function () {
      const minAmt = await paymentProcessor.minPaymentAmount();
      const maxAmt = await paymentProcessor.maxPaymentAmount();
      const span = maxAmt - minAmt;

      for (let i = 0; i < FUZZ_RUNS; i++) {
        const amount = minAmt + randBigInt(span);
        const escrowType = randInt(4);
        const hasCondition = randInt(2) === 1;
        const condition = hasCondition ? hash32(`cond-${i}`) : ethers.ZeroHash;
        const releaseTime = escrowType === ESCROW_TYPE.TimeBased
          ? BigInt(await time.latest()) + 1n + randBigInt(86400n)
          : 0n;

        // #1466 creation rules: TimeBased needs a release time;
        // PerformanceBased/Conditional need a condition hash.
        const expectRevert =
          (escrowType === ESCROW_TYPE.PerformanceBased || escrowType === ESCROW_TYPE.Conditional) && condition === ethers.ZeroHash;

        const payerConn = paymentProcessor.connect(payer);
        if (expectRevert) {
          await expect(
            payerConn.createEscrow.staticCall(payee.address, amount, releaseTime, escrowType, condition)
          ).to.be.revertedWith("Escrow release condition required");
          continue;
        }
        const escrowId = Number(
          await payerConn.createEscrow.staticCall(payee.address, amount, releaseTime, escrowType, condition)
        );
        await payerConn.createEscrow(payee.address, amount, releaseTime, escrowType, condition);

        // Settle: verifier-gated types need approval; TimeBased needs time.
        const gated = escrowType === ESCROW_TYPE.PerformanceBased || escrowType === ESCROW_TYPE.Conditional;
        if (gated) {
          await paymentProcessor.connect(verifier).approveEscrowRelease(escrowId);
        }
        if (escrowType === ESCROW_TYPE.TimeBased) {
          await time.increaseTo(releaseTime + 1n);
        }

        const settleByRefund = randInt(2) === 0;
        if (settleByRefund) {
          await paymentProcessor.connect(payer).refundEscrow(escrowId, "fuzz refund");
          await expect(
            paymentProcessor.connect(payee).releaseEscrow(escrowId)
          ).to.be.revertedWith("Escrow already refunded");
          await expect(
            paymentProcessor.connect(payer).refundEscrow(escrowId, "again")
          ).to.be.revertedWith("Escrow already refunded");
        } else {
          const before = await token.balanceOf(payee.address);
          await paymentProcessor.connect(payee).releaseEscrow(escrowId);
          expect(await token.balanceOf(payee.address) - before).to.equal(amount);
          await expect(
            paymentProcessor.connect(payer).releaseEscrow(escrowId)
          ).to.be.revertedWith("Escrow already released");
          await expect(
            paymentProcessor.connect(payer).refundEscrow(escrowId, "post-release")
          ).to.be.revertedWith("Escrow already released");
        }
      }
    });

    it("rejects a stranger on release and refund for every escrow type", async function () {
      const minAmt = await paymentProcessor.minPaymentAmount();
      for (let i = 0; i < 8; i++) {
        const escrowType = i % 4;
        const condition =
          escrowType === ESCROW_TYPE.PerformanceBased || escrowType === ESCROW_TYPE.Conditional
            ? hash32(`acl-${i}`)
            : ethers.ZeroHash;
        const releaseTime = escrowType === ESCROW_TYPE.TimeBased
          ? BigInt(await time.latest()) + 100n
          : 0n;
        const payerConn = paymentProcessor.connect(payer);
        const escrowId = Number(
          await payerConn.createEscrow.staticCall(payee.address, minAmt, releaseTime, escrowType, condition)
        );
        await payerConn.createEscrow(payee.address, minAmt, releaseTime, escrowType, condition);
        if (escrowType === ESCROW_TYPE.PerformanceBased || escrowType === ESCROW_TYPE.Conditional) {
          await paymentProcessor.connect(verifier).approveEscrowRelease(escrowId);
        }
        if (escrowType === ESCROW_TYPE.TimeBased) {
          await time.increaseTo(releaseTime + 1n);
        }
        await expect(
          paymentProcessor.connect(stranger).releaseEscrow(escrowId)
        ).to.be.revertedWith("Not authorized to release");
        await expect(
          paymentProcessor.connect(stranger).refundEscrow(escrowId, "stranger")
        ).to.be.revertedWith("Only depositor or owner can refund");
      }
    });
  });

  // ---------------------------------------------------------------
  // EscrowService.createEscrow — amount/time/counterparty bounds
  // ---------------------------------------------------------------
  describe("EscrowService.createEscrow fuzz", function () {
    it("enforces amount bounds, release-time rules and counterparty rules", async function () {
      const minAmt = await escrowService.minEscrowAmount();
      const maxAmt = await escrowService.maxEscrowAmount();
      const now = BigInt(await time.latest());

      // Invalid amounts — all must revert with "Invalid amount".
      const badAmounts = [0n, minAmt - 1n, maxAmt + 1n, maxAmt + randBigInt(maxAmt)];
      for (const amount of badAmounts) {
        await expect(
          escrowService.connect(payer).createEscrow(
            payee.address, arbiterOrZero(), amount, ES_TYPE.Standard, ES_CONDITION.Manual,
            0n, "bad amount"
          )
        ).to.be.revertedWith("Invalid amount");
      }

      // Invalid release times: strictly-past and exactly-now both rejected.
      const badTimes = [now - 1n - randBigInt(86400n), now];
      for (const t of badTimes) {
        await expect(
          escrowService.connect(payer).createEscrow(
            payee.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.TimeBased,
            t, "bad time"
          )
        ).to.be.revertedWith("Invalid release time");
      }

      // Counterparty rules.
      await expect(
        escrowService.connect(payer).createEscrow(
          ethers.ZeroAddress, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.Manual,
          0n, "no beneficiary"
        )
      ).to.be.revertedWith("Invalid beneficiary");
      await expect(
        escrowService.connect(payer).createEscrow(
          payer.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.Manual,
          0n, "self beneficiary"
        )
      ).to.be.revertedWith("Cannot be own beneficiary");

      // Valid fuzzed inputs always succeed.
      const span = maxAmt - minAmt;
      for (let i = 0; i < FUZZ_RUNS; i++) {
        const amount = minAmt + randBigInt(span);
        const condition = randInt(7); // all ReleaseCondition enum values are creatable
        // Fresh timestamp per iteration — each mined tx advances time.
        const t = BigInt(await time.latest());
        const releaseTime = randInt(2) === 0 ? 0n : t + 1n + randBigInt(86400n);
        await expect(
          escrowService.connect(payer).createEscrow(
            payee.address, arbiterOrZero(), amount, ES_TYPE.Standard, condition,
            releaseTime, `valid ${i}`
          )
        ).to.not.revert(ethers);
      }
    });

    it("settles each escrow at most once under fuzzed conditions", async function () {
      const minAmt = await escrowService.minEscrowAmount();
      const maxAmt = await escrowService.maxEscrowAmount();
      const span = maxAmt - minAmt;

      // Plain conditions reachable without oracle/emergency setup.
      const plain = [ES_CONDITION.Manual, ES_CONDITION.Automatic, ES_CONDITION.TimeBased];

      for (let i = 0; i < 40; i++) {
        // Refresh per iteration: earlier iterations may have warped time
        // past a releaseTime computed from a stale `now`.
        const now = BigInt(await time.latest());
        const amount = minAmt + randBigInt(span);
        const condition = plain[randInt(plain.length)];
        const releaseTime = condition === ES_CONDITION.TimeBased
          ? now + 1n + randBigInt(7200n)
          : 0n;

        const payerConn = escrowService.connect(payer);
        const escrowId = Number(
          await payerConn.createEscrow.staticCall(
            payee.address, arbiterOrZero(), amount, ES_TYPE.Standard, condition,
            releaseTime, `settle ${i}`
          )
        );
        await payerConn.createEscrow(
          payee.address, arbiterOrZero(), amount, ES_TYPE.Standard, condition,
          releaseTime, `settle ${i}`
        );

        const settleByRefund = randInt(2) === 0;
        if (settleByRefund) {
          await escrowService.connect(payer).refundEscrow(escrowId, "fuzz refund");
          await expect(
            escrowService.connect(payer).releaseEscrow(escrowId, "late release")
          ).to.be.revertedWith("Escrow already refunded");
          await expect(
            escrowService.connect(payer).refundEscrow(escrowId, "again")
          ).to.be.revertedWith("Escrow already refunded");
        } else {
          if (condition === ES_CONDITION.TimeBased) {
            await time.increaseTo(releaseTime + 1n);
          }
          const before = await token.balanceOf(payee.address);
          await escrowService.connect(payer).releaseEscrow(escrowId, "fuzz release");
          expect(await token.balanceOf(payee.address) - before).to.equal(amount);
          await expect(
            escrowService.connect(payer).releaseEscrow(escrowId, "again")
          ).to.be.revertedWith("Escrow already released");
          await expect(
            escrowService.connect(payer).refundEscrow(escrowId, "post-release")
          ).to.be.revertedWith("Escrow already released");
        }
      }
    });

    it("blocks stranger release/refund and gates TimeBased correctly", async function () {
      const minAmt = await escrowService.minEscrowAmount();
      const now = BigInt(await time.latest());

      // Stranger cannot touch a fresh escrow.
      const payerConn = escrowService.connect(payer);
      const id1 = Number(
        await payerConn.createEscrow.staticCall(
          payee.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.Manual,
          0n, "acl"
        )
      );
      await payerConn.createEscrow(
        payee.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.Manual,
        0n, "acl"
      );
      await expect(
        escrowService.connect(stranger).releaseEscrow(id1, "stranger")
      ).to.be.revertedWith("Not authorized to release");
      await expect(
        escrowService.connect(stranger).refundEscrow(id1, "stranger")
      ).to.be.revertedWith("Not authorized to refund");
      await expect(
        escrowService.connect(payee).refundEscrow(id1, "beneficiary refund")
      ).to.be.revertedWith("Not authorized to refund");

      // TimeBased: release before the time reverts; refund after the time reverts.
      const releaseTime = now + 100n;
      const id2 = Number(
        await payerConn.createEscrow.staticCall(
          payee.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.TimeBased,
          releaseTime, "timegate"
        )
      );
      await payerConn.createEscrow(
        payee.address, arbiterOrZero(), minAmt, ES_TYPE.Standard, ES_CONDITION.TimeBased,
        releaseTime, "timegate"
      );
      await expect(
        escrowService.connect(payer).releaseEscrow(id2, "too early")
      ).to.be.revertedWith("Release time not reached");
      await time.increaseTo(releaseTime + 1n);
      await expect(
        escrowService.connect(payer).refundEscrow(id2, "too late")
      ).to.be.revertedWith("Release time passed, cannot refund");
      await escrowService.connect(payer).releaseEscrow(id2, "on time");
    });
  });

  // ---------------------------------------------------------------
  // AgentStaking.stakeOnAgent — amount/lock-period bounds
  // ---------------------------------------------------------------
  describe("AgentStaking.stakeOnAgent fuzz", function () {
    it("enforces stake amount and lock-period bounds", async function () {
      const stakers = await ethers.getSigners();
      const pool = stakers.slice(1, 9); // 8 stakers, under maxStakesPerDay=10
      const minStake = await agentStaking.minStakeAmount();
      const maxStake = await agentStaking.maxStakeAmount();
      const span = maxStake - minStake;

      // Fund each staker once (deploy-time supply covers this).
      for (const s of pool) {
        await token.transfer(s.address, ethers.parseUnits("900000", 18));
        await token.connect(s).approve(await agentStaking.getAddress(), ethers.MaxUint256);
      }

      const N = 24;
      for (let i = 0; i < N; i++) {
        const staker = pool[i % pool.length];
        const amount = minStake + randBigInt(span);
        const lockPeriod = (1n + randBigInt(364n)) * 86400n; // 1..364 days in seconds
        await agentStaking.connect(staker).stakeOnAgent(
          agentWallet.address, amount, lockPeriod, randInt(2) === 0
        );
        // stakeCooldown is 1 minute — stay ahead of it.
        await time.increase(61);
      }

      // Invalid amounts revert.
      const badAmounts = [0n, minStake - 1n, maxStake + 1n];
      for (const amount of badAmounts) {
        await expect(
          agentStaking.connect(pool[0]).stakeOnAgent(agentWallet.address, amount, 30n * 86400n, false)
        ).to.be.revertedWith("Invalid stake amount");
      }

      // Invalid lock periods revert (valid bounds: 1..365 days).
      for (const lp of [0n, 86399n]) {
        await expect(
          agentStaking.connect(pool[0]).stakeOnAgent(agentWallet.address, minStake, lp, false)
        ).to.be.revertedWith("Lock period too short");
      }
      await expect(
        agentStaking.connect(pool[0]).stakeOnAgent(agentWallet.address, minStake, 366n * 86400n, false)
      ).to.be.revertedWith("Lock period too long");
    });
  });
});

// EscrowService accepts a zero arbiter; using address(0) keeps the fuzz
// inputs focused on amount/time/condition.
function arbiterOrZero() {
  return ethers.ZeroAddress;
}
