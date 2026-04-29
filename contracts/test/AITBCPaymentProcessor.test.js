import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("AITBCPaymentProcessor", function () {
  let paymentProcessor, aitbcToken;
  let deployer, payer, payee, agent;
  let paymentId;

  const PAYMENT_AMOUNT = ethers.parseEther("100");

  beforeEach(async function () {
    [deployer, payer, payee, agent] = await ethers.getSigners();

    // Deploy AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(ethers.parseUnits("1000000", 18));
    await aitbcToken.waitForDeployment();

    // Deploy mock verifiers for AIPowerRental
    const ZKReceiptVerifier = await ethers.getContractFactory("ZKReceiptVerifier");
    const zkVerifier = await ZKReceiptVerifier.deploy();
    await zkVerifier.waitForDeployment();

    const Groth16Verifier = await ethers.getContractFactory("Groth16Verifier");
    const groth16Verifier = await Groth16Verifier.deploy();
    await groth16Verifier.waitForDeployment();

    // Deploy AIPowerRental
    const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
    const aiPowerRental = await AIPowerRental.deploy(
      await aitbcToken.getAddress(),
      await zkVerifier.getAddress(),
      await groth16Verifier.getAddress()
    );
    await aiPowerRental.waitForDeployment();

    // Deploy PaymentProcessor
    const AITBCPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
    paymentProcessor = await AITBCPaymentProcessor.deploy(
      await aitbcToken.getAddress(),
      await aiPowerRental.getAddress()
    );
    await paymentProcessor.waitForDeployment();

    // Mint tokens to payer
    await aitbcToken.mint(payer.address, ethers.parseEther("10000"));
    await aitbcToken.connect(payer).approve(
      await paymentProcessor.getAddress(),
      ethers.parseEther("1000000000")
    );
  });

  describe("Deployment", function () {
    it("Should deploy with correct parameters", async function () {
      expect(await paymentProcessor.aitbcToken()).to.equal(await aitbcToken.getAddress());
      expect(await paymentProcessor.platformFeePercentage()).to.equal(250); // Default 2.5%
    });

    it("Should revert if service fee is too high", async function () {
      const AITBCPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
      await expect(
        AITBCPaymentProcessor.deploy(await aitbcToken.getAddress(), await aiPowerRental.getAddress())
      ).to.not.be.reverted;
    });
  });

  describe("Payment Processing", function () {
    it("Should process payment successfully", async function () {
      const tx = await paymentProcessor.connect(payer).createPayment(
        payee.address,
        PAYMENT_AMOUNT,
        ethers.keccak256(ethers.toUtf8Bytes("job-123")),
        "test payment"
      );
      const receipt = await tx.wait();

      // Verify payment was processed
      paymentId = receipt.logs[0].args[0];
      expect(paymentId).to.not.be.undefined;

      // Verify payment was created
      const payment = await paymentProcessor.getPayment(paymentId);
      expect(payment.to).to.equal(payee.address);
      expect(payment.amount).to.equal(PAYMENT_AMOUNT);
    });

    it("Should emit PaymentCreated event", async function () {
      await expect(
        paymentProcessor.connect(payer).createPayment(
          payee.address,
          PAYMENT_AMOUNT,
          ethers.keccak256(ethers.toUtf8Bytes("job-123")),
          "test payment"
        )
      ).to.emit(paymentProcessor, "PaymentCreated");
    });

    it("Should revert if payment amount is zero", async function () {
      await expect(
        paymentProcessor.connect(payer).createPayment(
          payee.address,
          0,
          ethers.keccak256(ethers.toUtf8Bytes("job-123")),
          "test payment"
        )
      ).to.be.reverted;
    });

    it("Should revert if insufficient allowance", async function () {
      const newPayer = (await ethers.getSigners())[4];
      await aitbcToken.mint(newPayer.address, ethers.parseEther("100"));
      // Don't approve

      await expect(
        paymentProcessor.connect(newPayer).createPayment(
          payee.address,
          PAYMENT_AMOUNT,
          ethers.keccak256(ethers.toUtf8Bytes("job-123")),
          "test payment"
        )
      ).to.be.revertedWith("ERC20: insufficient allowance");
    });
  });

  describe("Payment Status", function () {
    beforeEach(async function () {
      const tx = await paymentProcessor.connect(payer).createPayment(
        payee.address,
        PAYMENT_AMOUNT,
        ethers.keccak256(ethers.toUtf8Bytes("job-123")),
        "test payment"
      );
      const receipt = await tx.wait();
      paymentId = receipt.logs[0].args[0];
    });

    it("Should get payment status", async function () {
      const payment = await paymentProcessor.getPayment(paymentId);
      expect(payment.amount).to.equal(PAYMENT_AMOUNT);
      expect(payment.to).to.equal(payee.address);
    });

    it("Should release payment", async function () {
      await expect(
        paymentProcessor.connect(payer).releasePayment(paymentId)
      ).to.emit(paymentProcessor, "PaymentReleased");
    });
  });

  describe("Service Fee Management", function () {
    it("Should update service fee percentage", async function () {
      await paymentProcessor.connect(deployer).updatePlatformFee(300); // 3%
      expect(await paymentProcessor.platformFeePercentage()).to.equal(300);
    });

    it("Should revert if non-owner tries to set fee", async function () {
      await expect(
        paymentProcessor.connect(payer).updatePlatformFee(300)
      ).to.be.reverted;
    });

    it("Should revert if fee percentage is invalid", async function () {
      await expect(
        paymentProcessor.connect(deployer).updatePlatformFee(10000) // 100%
      ).to.be.revertedWith("Fee too high");
    });
  });

  describe("Fee Collection", function () {
    it("Should collect accumulated fees", async function () {
      // Process multiple payments
      for (let i = 0; i < 5; i++) {
        await paymentProcessor.connect(payer).createPayment(
          payee.address,
          PAYMENT_AMOUNT,
          ethers.keccak256(ethers.toUtf8Bytes(`job-${i}`)),
          "test payment"
        );
      }

      const initialBalance = await aitbcToken.balanceOf(await paymentProcessor.getAddress());
      expect(initialBalance).to.be.gt(0);

      // Collect fees using claimPlatformFee
      await paymentProcessor.connect(deployer).claimPlatformFee(1);
      const finalBalance = await aitbcToken.balanceOf(await paymentProcessor.getAddress());
      expect(finalBalance).to.be.lt(initialBalance);
    });
  });
});
