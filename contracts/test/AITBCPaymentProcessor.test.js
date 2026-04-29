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

    // Deploy AIPowerRental (mock)
    const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
    const aiPowerRental = await AIPowerRental.deploy();
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
      expect(await paymentProcessor.serviceFeePercentage()).to.equal(SERVICE_FEE_PERCENTAGE);
    });

    it("Should revert if service fee is too high", async function () {
      const AITBCPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
      await expect(
        AITBCPaymentProcessor.deploy(await aitbcToken.getAddress(), 10000) // 100%
      ).to.be.revertedWithCustomError(AITBCPaymentProcessor, "InvalidFeePercentage");
    });
  });

  describe("Payment Processing", function () {
    it("Should process payment successfully", async function () {
      const tx = await paymentProcessor.connect(payer).processPayment(
        payee.address,
        PAYMENT_AMOUNT,
        agent.address,
        ethers.keccak256(ethers.toUtf8Bytes("job-123"))
      );
      const receipt = await tx.wait();

      // Verify payment was processed
      paymentId = receipt.logs[0].args[0];
      expect(paymentId).to.not.be.undefined;

      // Verify balances
      const expectedPayeeAmount = PAYMENT_AMOUNT - (PAYMENT_AMOUNT * BigInt(SERVICE_FEE_PERCENTAGE) / 10000n);
      const payeeBalance = await aitbcToken.balanceOf(payee.address);
      expect(payeeBalance).to.equal(expectedPayeeAmount);
    });

    it("Should emit PaymentProcessed event", async function () {
      await expect(
        paymentProcessor.connect(payer).processPayment(
          payee.address,
          PAYMENT_AMOUNT,
          agent.address,
          ethers.keccak256(ethers.toUtf8Bytes("job-123"))
        )
      ).to.emit(paymentProcessor, "PaymentProcessed");
    });

    it("Should revert if payment amount is zero", async function () {
      await expect(
        paymentProcessor.connect(payer).processPayment(
          payee.address,
          0,
          agent.address,
          ethers.keccak256(ethers.toUtf8Bytes("job-123"))
        )
      ).to.be.revertedWithCustomError(paymentProcessor, "InvalidPaymentAmount");
    });

    it("Should revert if insufficient allowance", async function () {
      const newPayer = (await ethers.getSigners())[4];
      await aitbcToken.mint(newPayer.address, ethers.parseEther("100"));
      // Don't approve

      await expect(
        paymentProcessor.connect(newPayer).processPayment(
          payee.address,
          PAYMENT_AMOUNT,
          agent.address,
          ethers.keccak256(ethers.toUtf8Bytes("job-123"))
        )
      ).to.be.reverted;
    });
  });

  describe("Payment Status", function () {
    beforeEach(async function () {
      const tx = await paymentProcessor.connect(payer).processPayment(
        payee.address,
        PAYMENT_AMOUNT,
        agent.address,
        ethers.keccak256(ethers.toUtf8Bytes("job-123"))
      );
      const receipt = await tx.wait();
      paymentId = receipt.logs[0].args[0];
    });

    it("Should get payment status", async function () {
      const status = await paymentProcessor.getPaymentStatus(paymentId);
      expect(status.amount).to.equal(PAYMENT_AMOUNT);
      expect(status.payer).to.equal(payer.address);
      expect(status.payee).to.equal(payee.address);
      expect(status.agent).to.equal(agent.address);
    });

    it("Should refund payment if job fails", async function () {
      await expect(
        paymentProcessor.connect(deployer).refundPayment(
          paymentId,
          "Job execution failed"
        )
      ).to.emit(paymentProcessor, "PaymentRefunded");
    });
  });

  describe("Service Fee Management", function () {
    it("Should update service fee percentage", async function () {
      await paymentProcessor.connect(deployer).setServiceFeePercentage(300); // 3%
      expect(await paymentProcessor.serviceFeePercentage()).to.equal(300);
    });

    it("Should revert if non-owner tries to set fee", async function () {
      await expect(
        paymentProcessor.connect(payer).setServiceFeePercentage(300)
      ).to.be.revertedWithCustomError(paymentProcessor, "OwnableUnauthorizedAccount");
    });

    it("Should revert if fee percentage is invalid", async function () {
      await expect(
        paymentProcessor.connect(deployer).setServiceFeePercentage(10000) // 100%
      ).to.be.revertedWithCustomError(paymentProcessor, "InvalidFeePercentage");
    });
  });

  describe("Fee Collection", function () {
    it("Should collect accumulated fees", async function () {
      // Process multiple payments
      for (let i = 0; i < 5; i++) {
        await paymentProcessor.connect(payer).processPayment(
          payee.address,
          PAYMENT_AMOUNT,
          agent.address,
          ethers.keccak256(ethers.toUtf8Bytes(`job-${i}`))
        );
      }

      const initialBalance = await aitbcToken.balanceOf(await paymentProcessor.getAddress());
      expect(initialBalance).to.be.gt(0);

      // Collect fees
      await paymentProcessor.connect(deployer).collectFees();
      const finalBalance = await aitbcToken.balanceOf(await paymentProcessor.getAddress());
      expect(finalBalance).to.equal(0);
    });
  });
});
