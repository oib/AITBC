import { expect } from "chai";
import { network } from "hardhat";
const { ethers, networkHelpers } = await network.getOrCreate();
const { time } = networkHelpers;

const ESCROW_TYPE = {
  Standard: 0,
  MultiSignature: 1,
  TimeLocked: 2,
  Conditional: 3,
  PerformanceBased: 4,
  MilestoneBased: 5,
  Emergency: 6,
  ProtectedCompute: 7,
};

const RELEASE_CONDITION = {
  Manual: 0,
  Automatic: 1,
  OracleVerified: 2,
  PerformanceMet: 3,
  TimeBased: 4,
  MultiSignature: 5,
  Emergency: 6,
};

describe("EscrowService High-Priority Tests", function () {
  let token, aiPowerRental, paymentProcessor, escrow;
  let deployer, depositor, beneficiary, arbiter, stranger;
  let platformFee;
  let escrowAmount;
  let totalAmount;

  async function getLatestTimestamp() {
    const block = await ethers.provider.getBlock("latest");
    return block.timestamp;
  }

  beforeEach(async function () {
    [deployer, depositor, beneficiary, arbiter, stranger] = await ethers.getSigners();

    const AIToken = await ethers.getContractFactory("AIToken");
    token = await AIToken.deploy(ethers.parseUnits("1000000", 18));
    await token.waitForDeployment();

    await token.mint(depositor.address, ethers.parseEther("10000"));

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
    escrow = await EscrowService.deploy(
      await token.getAddress(),
      await aiPowerRental.getAddress(),
      await paymentProcessor.getAddress()
    );
    await escrow.waitForDeployment();

    platformFee = await escrow.platformFeePercentage();
    escrowAmount = ethers.parseEther("1");
    totalAmount = escrowAmount + (escrowAmount * platformFee) / 10000n;

    await token.connect(depositor).approve(await escrow.getAddress(), ethers.parseEther("10000"));
  });

  describe("Deployment", function () {
    it("Should reject zero payment token", async function () {
      const EscrowService = await ethers.getContractFactory("EscrowService");
      await expect(
        EscrowService.deploy(ethers.ZeroAddress, await aiPowerRental.getAddress(), await paymentProcessor.getAddress())
      ).to.be.revertedWith("payment token cannot be zero address");
    });

    it("Should reject zero AI power rental", async function () {
      const EscrowService = await ethers.getContractFactory("EscrowService");
      await expect(
        EscrowService.deploy(await token.getAddress(), ethers.ZeroAddress, await paymentProcessor.getAddress())
      ).to.be.revertedWith("AI power rental cannot be zero address");
    });

    it("Should reject zero payment processor", async function () {
      const EscrowService = await ethers.getContractFactory("EscrowService");
      await expect(
        EscrowService.deploy(await token.getAddress(), await aiPowerRental.getAddress(), ethers.ZeroAddress)
      ).to.be.revertedWith("payment processor cannot be zero address");
    });
  });

  describe("createEscrow", function () {
    it("Should create a standard escrow with valid parameters", async function () {
      const tx = await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        "manual release escrow"
      );

      await expect(tx)
        .to.emit(escrow, "EscrowCreated")
        .withArgs(0, depositor.address, beneficiary.address, escrowAmount, 0, 0);

      const account = await escrow.getEscrowAccount(0);
      expect(account.depositor).to.equal(depositor.address);
      expect(account.beneficiary).to.equal(beneficiary.address);
      expect(account.arbiter).to.equal(arbiter.address);
      expect(account.amount).to.equal(escrowAmount);
      expect(account.isReleased).to.equal(false);
      expect(account.isRefunded).to.equal(false);
    });

    it("Should reject zero beneficiary", async function () {
      await expect(
        escrow.connect(depositor).createEscrow(
          ethers.ZeroAddress,
          arbiter.address,
          escrowAmount,
          ESCROW_TYPE.Standard,
          RELEASE_CONDITION.Manual,
          0,
          ""
        )
      ).to.be.revertedWith("Invalid beneficiary");
    });

    it("Should reject self as beneficiary", async function () {
      await expect(
        escrow.connect(depositor).createEscrow(
          depositor.address,
          arbiter.address,
          escrowAmount,
          ESCROW_TYPE.Standard,
          RELEASE_CONDITION.Manual,
          0,
          ""
        )
      ).to.be.revertedWith("Cannot be own beneficiary");
    });

    it("Should reject amount below minimum", async function () {
      const minAmount = await escrow.minEscrowAmount();
      await expect(
        escrow.connect(depositor).createEscrow(
          beneficiary.address,
          arbiter.address,
          minAmount - 1n,
          ESCROW_TYPE.Standard,
          RELEASE_CONDITION.Manual,
          0,
          ""
        )
      ).to.be.revertedWith("Invalid amount");
    });

    it("Should reject invalid release time", async function () {
      const now = await getLatestTimestamp();
      await expect(
        escrow.connect(depositor).createEscrow(
          beneficiary.address,
          arbiter.address,
          escrowAmount,
          ESCROW_TYPE.Standard,
          RELEASE_CONDITION.TimeBased,
          now - 1,
          ""
        )
      ).to.be.revertedWith("Invalid release time");
    });

    it("Should reject insufficient allowance", async function () {
      await token.connect(depositor).approve(await escrow.getAddress(), 0);
      await expect(
        escrow.connect(depositor).createEscrow(
          beneficiary.address,
          arbiter.address,
          escrowAmount,
          ESCROW_TYPE.Standard,
          RELEASE_CONDITION.Manual,
          0,
          ""
        )
      ).to.be.revertedWith("Insufficient allowance");
    });

    it("Should collect principal and platform fee", async function () {
      const balanceBefore = await token.balanceOf(depositor.address);
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );
      const balanceAfter = await token.balanceOf(depositor.address);
      expect(balanceBefore - balanceAfter).to.equal(totalAmount);
    });
  });

  describe("releaseEscrow", function () {
    it("Should release funds to beneficiary when arbiter calls", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        "arbiter release"
      );

      const beneficiaryBalanceBefore = await token.balanceOf(beneficiary.address);
      const tx = await escrow.connect(arbiter).releaseEscrow(0, "approved by arbiter");

      await expect(tx)
        .to.emit(escrow, "EscrowReleased")
        .withArgs(0, beneficiary.address, escrowAmount, "approved by arbiter");

      const beneficiaryBalanceAfter = await token.balanceOf(beneficiary.address);
      expect(beneficiaryBalanceAfter - beneficiaryBalanceBefore).to.equal(escrowAmount);
    });

    it("Should enforce time-based release condition", async function () {
      const releaseTime = (await getLatestTimestamp()) + 1000;
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.TimeBased,
        releaseTime,
        "time locked"
      );

      await expect(
        escrow.connect(depositor).releaseEscrow(0, "too early")
      ).to.be.revertedWith("Release time not reached");

      await time.increase(1001);

      const tx = await escrow.connect(depositor).releaseEscrow(0, "time reached");
      await expect(tx).to.emit(escrow, "EscrowReleased");
    });

    it("Should require multi-signature before release", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.MultiSignature,
        RELEASE_CONDITION.MultiSignature,
        0,
        "multi-sig"
      );

      await expect(
        escrow.connect(depositor).releaseEscrow(0, "not enough sigs")
      ).to.be.revertedWith("Insufficient signatures");

      await escrow.connect(depositor).submitSignature(0);
      await escrow.connect(beneficiary).submitSignature(0);

      const account = await escrow.getEscrowAccount(0);
      expect(account.isReleased).to.equal(true);
    });

    it("Should not allow a stranger to release", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );

      await expect(
        escrow.connect(stranger).releaseEscrow(0, "unauthorized")
      ).to.be.revertedWith("Not authorized to release");
    });
  });

  describe("refundEscrow", function () {
    it("Should refund time-locked escrow before release time", async function () {
      const releaseTime = (await getLatestTimestamp()) + 1000;
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.TimeBased,
        releaseTime,
        "refundable time lock"
      );

      const depositorBalanceBefore = await token.balanceOf(depositor.address);
      const tx = await escrow.connect(depositor).refundEscrow(0, "not delivered");

      await expect(tx)
        .to.emit(escrow, "EscrowRefunded")
        .withArgs(0, depositor.address, escrowAmount, "not delivered");

      const account = await escrow.getEscrowAccount(0);
      expect(account.isRefunded).to.equal(true);

      const depositorBalanceAfter = await token.balanceOf(depositor.address);
      expect(depositorBalanceAfter - depositorBalanceBefore).to.equal(escrowAmount);
    });

    it("Should not refund after release time", async function () {
      const releaseTime = (await getLatestTimestamp()) + 1000;
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.TimeBased,
        releaseTime,
        ""
      );

      await time.increase(1001);

      await expect(
        escrow.connect(depositor).refundEscrow(0, "too late")
      ).to.be.revertedWith("Release time passed, cannot refund");
    });

    it("Should allow arbiter to refund", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );

      const tx = await escrow.connect(arbiter).refundEscrow(0, "arbiter refund");
      await expect(tx).to.emit(escrow, "EscrowRefunded");
    });
  });

  describe("freezeEscrow", function () {
    it("Should pause an escrow and block releases", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );

      await escrow.connect(arbiter).freezeEscrow(0, "dispute");

      await expect(
        escrow.connect(arbiter).releaseEscrow(0, "frozen")
      ).to.be.revertedWith("Escrow is frozen");

      await escrow.connect(arbiter).unfreezeEscrow(0, "resolved");

      const tx = await escrow.connect(arbiter).releaseEscrow(0, "resolved release");
      await expect(tx).to.emit(escrow, "EscrowReleased");
    });

    it("Should only allow authorized parties to freeze", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );

      await expect(
        escrow.connect(stranger).freezeEscrow(0, "hacker")
      ).to.be.revertedWith("Not authorized to freeze");
    });
  });

  describe("createComputeEscrow", function () {
    it("Should revert when energy pricing is not configured", async function () {
      await expect(
        escrow.connect(depositor).createComputeEscrow(
          beneficiary.address,
          "gpu-1",
          "rtx4090",
          1,
          3600,
          escrowAmount,
          totalAmount,
          1
        )
      ).to.be.revertedWith("Energy pricing not configured");
    });

    it("Should create a protected compute escrow when energy pricing is set", async function () {
      const MockEnergyPricing = await ethers.getContractFactory("MockEnergyPricing");
      const energy = await MockEnergyPricing.deploy(
        beneficiary.address,
        "rtx4090",
        ethers.parseEther("0.5"),
        1
      );
      await energy.waitForDeployment();
      await escrow.setEnergyPricing(await energy.getAddress());

      const tx = await escrow.connect(depositor).createComputeEscrow(
        beneficiary.address,
        "gpu-1",
        "rtx4090",
        1,
        3600,
        escrowAmount,
        totalAmount,
        1
      );

      await expect(tx).to.emit(escrow, "EscrowCreated");

      const account = await escrow.getEscrowAccount(0);
      expect(account.escrowType).to.equal(ESCROW_TYPE.ProtectedCompute);
    });
  });

  describe("emergencyRelease", function () {
    it("Should execute an approved emergency release with arbiters", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        "emergency"
      );

      await escrow.setEmergencyReleaseQuorum(2);
      await escrow.setEmergencyReleaseVotingThreshold(51);
      await escrow.setEmergencyReleaseTimelock(0);

      await escrow.authorizeArbiter(stranger.address);
      await escrow.authorizeArbiter(arbiter.address);

      await escrow.connect(depositor).requestEmergencyRelease(0, "urgent");

      await escrow.connect(stranger).voteEmergencyRelease(0, true);
      await escrow.connect(arbiter).voteEmergencyRelease(0, true);

      const account = await escrow.getEscrowAccount(0);
      expect(account.isReleased).to.equal(true);
    });
  });

  describe("View functions", function () {
    it("Should list depositor and beneficiary escrows", async function () {
      await escrow.connect(depositor).createEscrow(
        beneficiary.address,
        arbiter.address,
        escrowAmount,
        ESCROW_TYPE.Standard,
        RELEASE_CONDITION.Manual,
        0,
        ""
      );

      const depositorEscrows = await escrow.getDepositorEscrows(depositor.address);
      const beneficiaryEscrows = await escrow.getBeneficiaryEscrows(beneficiary.address);

      expect(depositorEscrows).to.deep.equal([0n]);
      expect(beneficiaryEscrows).to.deep.equal([0n]);
    });
  });
});
