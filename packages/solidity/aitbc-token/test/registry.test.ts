import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { AITokenRegistry__factory } from "../typechain-types";

async function deployRegistryFixture() {
  const [admin, coordinator, provider1, provider2, outsider] = await ethers.getSigners();

  const factory = new AITokenRegistry__factory(admin);
  const registry = await factory.deploy(admin.address);
  await registry.waitForDeployment();

  const coordinatorRole = await registry.COORDINATOR_ROLE();
  await registry.grantRole(coordinatorRole, coordinator.address);

  return { registry, admin, coordinator, provider1, provider2, outsider };
}

describe("AITokenRegistry", function () {
  describe("Provider Registration", function () {
    it("allows coordinator to register a provider", async function () {
      const { registry, coordinator, provider1 } = await loadFixture(deployRegistryFixture);

      const collateral = ethers.parseEther("100");

      await expect(
        registry.connect(coordinator).registerProvider(provider1.address, collateral)
      )
        .to.emit(registry, "ProviderRegistered")
        .withArgs(provider1.address, collateral);

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(true);
      expect(info.collateral).to.equal(collateral);
    });

    it("rejects registration of zero address", async function () {
      const { registry, coordinator } = await loadFixture(deployRegistryFixture);

      await expect(
        registry.connect(coordinator).registerProvider(ethers.ZeroAddress, 0)
      ).to.be.revertedWith("invalid provider");
    });

    it("rejects duplicate registration", async function () {
      const { registry, coordinator, provider1 } = await loadFixture(deployRegistryFixture);

      await registry.connect(coordinator).registerProvider(provider1.address, 100);

      await expect(
        registry.connect(coordinator).registerProvider(provider1.address, 200)
      ).to.be.revertedWith("already registered");
    });

    it("rejects registration from non-coordinator", async function () {
      const { registry, provider1, outsider } = await loadFixture(deployRegistryFixture);

      await expect(
        registry.connect(outsider).registerProvider(provider1.address, 100)
      ).to.be.reverted;
    });
  });

  describe("Provider Updates", function () {
    it("allows coordinator to update provider status", async function () {
      const { registry, coordinator, provider1 } = await loadFixture(deployRegistryFixture);

      await registry.connect(coordinator).registerProvider(provider1.address, 100);

      await expect(
        registry.connect(coordinator).updateProvider(provider1.address, false, 50)
      )
        .to.emit(registry, "ProviderUpdated")
        .withArgs(provider1.address, false, 50);

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(false);
      expect(info.collateral).to.equal(50);
    });

    it("allows reactivating a deactivated provider", async function () {
      const { registry, coordinator, provider1 } = await loadFixture(deployRegistryFixture);

      await registry.connect(coordinator).registerProvider(provider1.address, 100);
      await registry.connect(coordinator).updateProvider(provider1.address, false, 100);
      await registry.connect(coordinator).updateProvider(provider1.address, true, 200);

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(true);
      expect(info.collateral).to.equal(200);
    });

    it("rejects update of unregistered provider", async function () {
      const { registry, coordinator, provider1 } = await loadFixture(deployRegistryFixture);

      await expect(
        registry.connect(coordinator).updateProvider(provider1.address, false, 100)
      ).to.be.revertedWith("provider not registered");
    });
  });

  describe("Access Control", function () {
    it("admin can grant coordinator role", async function () {
      const { registry, admin, outsider } = await loadFixture(deployRegistryFixture);

      const coordinatorRole = await registry.COORDINATOR_ROLE();
      await registry.connect(admin).grantRole(coordinatorRole, outsider.address);

      expect(await registry.hasRole(coordinatorRole, outsider.address)).to.equal(true);
    });

    it("non-admin cannot grant roles", async function () {
      const { registry, coordinator, outsider } = await loadFixture(deployRegistryFixture);

      const coordinatorRole = await registry.COORDINATOR_ROLE();

      await expect(
        registry.connect(coordinator).grantRole(coordinatorRole, outsider.address)
      ).to.be.reverted;
    });
  });
});
