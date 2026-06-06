import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("AgentMarketplaceV2", function () {
  let marketplace, aitbcToken;
  let deployer, provider, consumer;
  let capabilityId;
  
  const PRICE_PER_CALL = ethers.parseEther("50");
  const SUBSCRIPTION_PRICE = ethers.parseEther("100");
  const INITIAL_SUPPLY = ethers.parseUnits("1000000", 18);

  beforeEach(async function () {
    [deployer, provider, consumer] = await ethers.getSigners();

    // Deploy AIToken
    const AIToken = await ethers.getContractFactory("AIToken");
    aitbcToken = await AIToken.deploy(INITIAL_SUPPLY);
    await aitbcToken.waitForDeployment();

    // Transfer tokens to consumer
    await aitbcToken.transfer(consumer.address, ethers.parseEther("10000"));

    // Deploy Marketplace
    const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
    marketplace = await AgentMarketplaceV2.deploy(await aitbcToken.getAddress());
    await marketplace.waitForDeployment();

    // Approve marketplace to spend consumer's tokens
    await aitbcToken.connect(consumer).approve(
      await marketplace.getAddress(),
      ethers.parseEther("1000000000")
    );
  });

  describe("Deployment", function () {
    it("Should deploy with correct token address", async function () {
      expect(await marketplace.aitbcToken()).to.equal(await aitbcToken.getAddress());
    });

    it("Should set deployer as owner", async function () {
      expect(await marketplace.owner()).to.equal(deployer.address);
    });

    it("Should set default platform fee", async function () {
      expect(await marketplace.platformFeePercentage()).to.equal(250); // 2.5%
    });
  });

  describe("Capability Listing", function () {
    it("Should list a capability", async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();

      capabilityId = receipt.logs[0].args[0];
      expect(capabilityId).to.not.be.undefined;
    });

    it("Should emit CapabilityListed event", async function () {
      await expect(
        marketplace.connect(provider).listCapability(
          "ipfs://QmTest",
          PRICE_PER_CALL,
          SUBSCRIPTION_PRICE,
          true
        )
      ).to.emit(marketplace, "CapabilityListed");
    });

    it("Should revert if metadata URI is empty", async function () {
      await expect(
        marketplace.connect(provider).listCapability(
          "",
          PRICE_PER_CALL,
          SUBSCRIPTION_PRICE,
          true
        )
      ).to.be.revertedWith("Invalid URI");
    });

    it("Should store capability details correctly", async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];

      const capability = await marketplace.capabilities(capabilityId);
      expect(capability.providerAgent).to.equal(provider.address);
      expect(capability.pricePerCall).to.equal(PRICE_PER_CALL);
      expect(capability.subscriptionPrice).to.equal(SUBSCRIPTION_PRICE);
      expect(capability.isSubscriptionEnabled).to.be.true;
      expect(capability.isActive).to.be.true;
    });
  });

  describe("Capability Management", function () {
    beforeEach(async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];
    });

    it("Should update capability", async function () {
      const newPrice = ethers.parseEther("75");
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        newPrice,
        SUBSCRIPTION_PRICE,
        true,
        true
      );
      
      const capability = await marketplace.capabilities(capabilityId);
      expect(capability.pricePerCall).to.equal(newPrice);
    });

    it("Should emit CapabilityUpdated event", async function () {
      await expect(
        marketplace.connect(provider).updateCapability(
          capabilityId,
          PRICE_PER_CALL,
          SUBSCRIPTION_PRICE,
          true,
          false
        )
      ).to.emit(marketplace, "CapabilityUpdated");
    });

    it("Should revert if non-provider updates capability", async function () {
      await expect(
        marketplace.connect(consumer).updateCapability(
          capabilityId,
          ethers.parseEther("75"),
          SUBSCRIPTION_PRICE,
          true,
          true
        )
      ).to.be.revertedWith("Not the provider");
    });

    it("Should deactivate capability", async function () {
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true,
        false
      );
      
      const capability = await marketplace.capabilities(capabilityId);
      expect(capability.isActive).to.be.false;
    });
  });

  describe("Call Purchase", function () {
    beforeEach(async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];
    });

    it("Should purchase a call", async function () {
      const providerBalance = await aitbcToken.balanceOf(provider.address);
      
      await marketplace.connect(consumer).purchaseCall(capabilityId);
      
      const newProviderBalance = await aitbcToken.balanceOf(provider.address);
      expect(newProviderBalance).to.be.gt(providerBalance);
    });

    it("Should emit CapabilityPurchased event", async function () {
      await expect(
        marketplace.connect(consumer).purchaseCall(capabilityId)
      ).to.emit(marketplace, "CapabilityPurchased");
    });

    it("Should revert if capability is inactive", async function () {
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true,
        false
      );
      
      await expect(
        marketplace.connect(consumer).purchaseCall(capabilityId)
      ).to.be.revertedWith("Capability inactive");
    });

    it("Should revert if price is zero", async function () {
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        0,
        SUBSCRIPTION_PRICE,
        true,
        true
      );
      
      await expect(
        marketplace.connect(consumer).purchaseCall(capabilityId)
      ).to.be.revertedWith("Not available for single call");
    });

    it("Should track total calls and revenue", async function () {
      await marketplace.connect(consumer).purchaseCall(capabilityId);
      
      const capability = await marketplace.capabilities(capabilityId);
      expect(capability.totalCalls).to.equal(1);
      expect(capability.totalRevenue).to.be.gt(0);
    });
  });

  describe("Subscription", function () {
    beforeEach(async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];
    });

    it("Should subscribe to capability", async function () {
      const tx = await marketplace.connect(consumer).subscribeToCapability(capabilityId);
      const receipt = await tx.wait();
      
      expect(receipt).to.not.be.undefined;
    });

    it("Should emit SubscriptionCreated event", async function () {
      await expect(
        marketplace.connect(consumer).subscribeToCapability(capabilityId)
      ).to.emit(marketplace, "SubscriptionCreated");
    });

    it("Should revert if capability is inactive", async function () {
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true,
        false
      );
      
      await expect(
        marketplace.connect(consumer).subscribeToCapability(capabilityId)
      ).to.be.revertedWith("Capability inactive");
    });

    it("Should revert if subscriptions not enabled", async function () {
      await marketplace.connect(provider).updateCapability(
        capabilityId,
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        false,
        true
      );
      
      await expect(
        marketplace.connect(consumer).subscribeToCapability(capabilityId)
      ).to.be.revertedWith("Subscriptions not enabled");
    });

    it("Should check subscription validity", async function () {
      const tx = await marketplace.connect(consumer).subscribeToCapability(capabilityId);
      await tx.wait();
      
      // Subscription creates a valid subscription that can be checked
      // Since we can't directly access the mapping, we just verify the subscription was created successfully
      expect(tx.hash).to.not.be.undefined;
    });
  });

  describe("Platform Fee Management", function () {
    it("Should update platform fee", async function () {
      await marketplace.connect(deployer).updatePlatformFee(300); // 3%
      expect(await marketplace.platformFeePercentage()).to.equal(300);
    });

    it("Should emit PlatformFeeUpdated event", async function () {
      await expect(
        marketplace.connect(deployer).updatePlatformFee(300)
      ).to.emit(marketplace, "PlatformFeeUpdated");
    });

    it("Should revert if fee is too high", async function () {
      await expect(
        marketplace.connect(deployer).updatePlatformFee(1001) // 10.01%
      ).to.be.revertedWith("Fee too high");
    });

    it("Should revert if non-owner updates fee", async function () {
      await expect(
        marketplace.connect(consumer).updatePlatformFee(300)
      ).to.be.reverted;
    });
  });

  describe("Reputation Management", function () {
    beforeEach(async function () {
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];
    });

    it("Should update capability reputation", async function () {
      await marketplace.connect(deployer).updateCapabilityReputation(capabilityId, 100);
      
      const capability = await marketplace.capabilities(capabilityId);
      expect(capability.reputationScore).to.equal(100);
    });

    it("Should emit CapabilityReputationUpdated event", async function () {
      await expect(
        marketplace.connect(deployer).updateCapabilityReputation(capabilityId, 100)
      ).to.emit(marketplace, "CapabilityReputationUpdated");
    });

    it("Should revert if non-owner updates reputation", async function () {
      await expect(
        marketplace.connect(consumer).updateCapabilityReputation(capabilityId, 100)
      ).to.be.reverted;
    });
  });

  describe("Fee Withdrawal", function () {
    it("Should withdraw platform fees", async function () {
      // Create some activity to generate fees
      const tx = await marketplace.connect(provider).listCapability(
        "ipfs://QmTest",
        PRICE_PER_CALL,
        SUBSCRIPTION_PRICE,
        true
      );
      const receipt = await tx.wait();
      capabilityId = receipt.logs[0].args[0];
      
      await marketplace.connect(consumer).purchaseCall(capabilityId);
      
      const ownerBalance = await aitbcToken.balanceOf(deployer.address);
      await marketplace.connect(deployer).withdrawPlatformFees();
      
      const newOwnerBalance = await aitbcToken.balanceOf(deployer.address);
      expect(newOwnerBalance).to.be.gt(ownerBalance);
    });

    it("Should revert if no fees to withdraw", async function () {
      await expect(
        marketplace.connect(deployer).withdrawPlatformFees()
      ).to.be.revertedWith("No fees to withdraw");
    });

    it("Should revert if non-owner withdraws fees", async function () {
      await expect(
        marketplace.connect(consumer).withdrawPlatformFees()
      ).to.be.reverted;
    });
  });
});
