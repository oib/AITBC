import { expect } from "chai";
import { network } from "hardhat";

const { ethers, networkHelpers } = await network.getOrCreate();
const { time } = networkHelpers;

const ESCROW_TYPE = {
  Standard: 0,
  PerformanceBased: 1,
  TimeBased: 2,
  Conditional: 3,
};

const RELEASE_CONDITION = {
  Immediate: 0,
  Manual: 1,
  Performance: 2,
  TimeBased: 3,
  DisputeResolution: 4,
};

describe("PaymentProcessor", function () {
  let token, aiPowerRental, paymentProcessor;
  let deployer, payer, payee, stranger;
  let paymentAmount;

  beforeEach(async function () {
    [deployer, payer, payee, stranger] = await ethers.getSigners();

    const AIToken = await ethers.getContractFactory("AIToken");
    token = await AIToken.deploy(ethers.parseUnits("1000000", 18));
    await token.waitForDeployment();
    await token.mint(payer.address, ethers.parseEther("10000"));

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

    paymentAmount = ethers.parseEther("1");

    await token
      .connect(payer)
      .approve(await paymentProcessor.getAddress(), ethers.parseEther("10000"));
    await paymentProcessor.connect(deployer).authorizePayer(payer.address);
    await paymentProcessor.connect(deployer).authorizePayee(payee.address);
  });

  describe("Deployment", function () {
    it("Should reject zero payment token", async function () {
      const PaymentProcessor = await ethers.getContractFactory("PaymentProcessor");
      await expect(
        PaymentProcessor.deploy(
          ethers.ZeroAddress,
          await aiPowerRental.getAddress()
        )
      ).to.be.revertedWith("payment token cannot be zero address");
    });

    it("Should reject zero AI power rental", async function () {
      const PaymentProcessor = await ethers.getContractFactory("PaymentProcessor");
      await expect(
        PaymentProcessor.deploy(
          await token.getAddress(),
          ethers.ZeroAddress
        )
      ).to.be.revertedWith("AI power rental cannot be zero address");
    });
  });

  describe("createEscrow", function () {
    it("Should create a standard escrow", async function () {
      const tx = await paymentProcessor
        .connect(payer)
        .createEscrow(
          payee.address,
          paymentAmount,
          0,
          ESCROW_TYPE.Standard,
          ethers.encodeBytes32String("manual")
        );

      await expect(tx)
        .to.emit(paymentProcessor, "EscrowCreated")
        .withArgs(0, payer.address, payee.address, paymentAmount, ESCROW_TYPE.Standard);

      const account = await paymentProcessor.escrowAccounts(0);
      expect(account.beneficiary).to.equal(payee.address);
      expect(account.amount).to.equal(paymentAmount);
      expect(account.isReleased).to.equal(false);
    });

    it("Should reject unauthorized payer", async function () {
      await expect(
        paymentProcessor
          .connect(stranger)
          .createEscrow(
            payee.address,
            paymentAmount,
            0,
            ESCROW_TYPE.Standard,
            ethers.encodeBytes32String("manual")
          )
      ).to.be.revertedWith("Not authorized payer");
    });
  });

  describe("releaseEscrow", function () {
    beforeEach(async function () {
      await paymentProcessor
        .connect(payer)
        .createEscrow(
          payee.address,
          paymentAmount,
          0,
          ESCROW_TYPE.Standard,
          ethers.encodeBytes32String("manual")
        );
    });

    it("Should allow beneficiary to release", async function () {
      const tx = await paymentProcessor.connect(payee).releaseEscrow(0);
      await expect(tx)
        .to.emit(paymentProcessor, "EscrowReleased")
        .withArgs(0, paymentAmount, ethers.encodeBytes32String("manual"));

      const account = await paymentProcessor.escrowAccounts(0);
      expect(account.isReleased).to.equal(true);
    });

    it("Should allow payer to release", async function () {
      const tx = await paymentProcessor.connect(payer).releaseEscrow(0);
      await expect(tx).to.emit(paymentProcessor, "EscrowReleased");
    });

    it("Should allow owner to release", async function () {
      const tx = await paymentProcessor.connect(deployer).releaseEscrow(0);
      await expect(tx).to.emit(paymentProcessor, "EscrowReleased");
    });

    it("Should reject release by a stranger", async function () {
      await expect(
        paymentProcessor.connect(stranger).releaseEscrow(0)
      ).to.be.revertedWith("Not authorized to release");
    });

    it("Should reject double release", async function () {
      await paymentProcessor.connect(payee).releaseEscrow(0);
      await expect(
        paymentProcessor.connect(payee).releaseEscrow(0)
      ).to.be.revertedWith("Escrow already released");
    });
  });

  describe("refundEscrow", function () {
    beforeEach(async function () {
      await paymentProcessor
        .connect(payer)
        .createEscrow(
          payee.address,
          paymentAmount,
          0,
          ESCROW_TYPE.Standard,
          ethers.encodeBytes32String("manual")
        );
    });

    it("Should allow payer to refund", async function () {
      const tx = await paymentProcessor.connect(payer).refundEscrow(0, "changed mind");
      await expect(tx)
        .to.emit(paymentProcessor, "EscrowRefunded")
        .withArgs(0, payer.address, paymentAmount, "changed mind");

      const account = await paymentProcessor.escrowAccounts(0);
      expect(account.isRefunded).to.equal(true);
    });

    it("Should allow owner to refund", async function () {
      const tx = await paymentProcessor.connect(deployer).refundEscrow(0, "dispute");
      await expect(tx).to.emit(paymentProcessor, "EscrowRefunded");
    });

    it("Should reject refund by beneficiary or stranger", async function () {
      await expect(
        paymentProcessor.connect(payee).refundEscrow(0, "not allowed")
      ).to.be.revertedWith("Only depositor or owner can refund");

      await expect(
        paymentProcessor.connect(stranger).refundEscrow(0, "not allowed")
      ).to.be.revertedWith("Only depositor or owner can refund");
    });

    it("Should reject double refund", async function () {
      await paymentProcessor.connect(payer).refundEscrow(0, "changed mind");
      await expect(
        paymentProcessor.connect(payer).refundEscrow(0, "again")
      ).to.be.revertedWith("Escrow already refunded");
    });
  });

  describe("createPayment", function () {
    it("Should create a manual payment", async function () {
      const tx = await paymentProcessor
        .connect(payer)
        .createPayment(
          payee.address,
          paymentAmount,
          ethers.encodeBytes32String("agreement-1"),
          "test payment",
          RELEASE_CONDITION.Manual
        );

      await expect(tx)
        .to.emit(paymentProcessor, "PaymentCreated")
        .withArgs(0, payer.address, payee.address, paymentAmount, ethers.encodeBytes32String("agreement-1"), "test payment");

      const payment = await paymentProcessor.getPayment(0);
      expect(payment.from).to.equal(payer.address);
      expect(payment.to).to.equal(payee.address);
      expect(payment.status).to.equal(0); // Created
    });

    it("Should reject unauthorized payer", async function () {
      await expect(
        paymentProcessor
          .connect(stranger)
          .createPayment(
            payee.address,
            paymentAmount,
            ethers.encodeBytes32String("agreement-1"),
            "test payment",
            RELEASE_CONDITION.Manual
          )
      ).to.be.revertedWith("Not authorized payer");
    });
  });

  describe("releasePayment", function () {
    beforeEach(async function () {
      await paymentProcessor
        .connect(payer)
        .createPayment(
          payee.address,
          paymentAmount,
          ethers.encodeBytes32String("agreement-1"),
          "manual payment",
          RELEASE_CONDITION.Manual
        );

      await paymentProcessor
        .connect(payer)
        .confirmPayment(0, ethers.encodeBytes32String("tx-hash"));
    });

    it("Should allow payer to manually release", async function () {
      const tx = await paymentProcessor.connect(payer).releasePayment(0);
      await expect(tx).to.emit(paymentProcessor, "PaymentReleased");

      const payment = await paymentProcessor.getPayment(0);
      expect(payment.status).to.equal(3); // Released
    });

    it("Should reject manual release by payee", async function () {
      await expect(
        paymentProcessor.connect(payee).releasePayment(0)
      ).to.be.revertedWith("Only payer can release manually");
    });

    it("Should reject release by a stranger", async function () {
      await expect(
        paymentProcessor.connect(stranger).releasePayment(0)
      ).to.be.revertedWith("Not authorized to release");
    });

    it("Should reject double release", async function () {
      await paymentProcessor.connect(payer).releasePayment(0);
      await expect(
        paymentProcessor.connect(payer).releasePayment(0)
      ).to.be.revertedWith("Payment not ready for release");
    });
  });

  describe("time-based payment release", function () {
    beforeEach(async function () {
      await paymentProcessor
        .connect(payer)
        .createPayment(
          payee.address,
          paymentAmount,
          ethers.encodeBytes32String("agreement-2"),
          "time payment",
          RELEASE_CONDITION.TimeBased
        );

      await paymentProcessor
        .connect(payer)
        .confirmPayment(0, ethers.encodeBytes32String("tx-hash"));
    });

    it("Should allow payee to release after the hold period", async function () {
      await time.increase(3700);

      const tx = await paymentProcessor.connect(payee).releasePayment(0);
      await expect(tx).to.emit(paymentProcessor, "PaymentReleased");

      const payment = await paymentProcessor.getPayment(0);
      expect(payment.status).to.equal(3); // Released
    });

    it("Should reject release before the hold period", async function () {
      await expect(
        paymentProcessor.connect(payee).releasePayment(0)
      ).to.be.revertedWith("Release time not reached");
    });

    it("Should reject release by a stranger even after the hold period", async function () {
      await time.increase(3700);

      await expect(
        paymentProcessor.connect(stranger).releasePayment(0)
      ).to.be.revertedWith("Not authorized to release");
    });
  });
});
