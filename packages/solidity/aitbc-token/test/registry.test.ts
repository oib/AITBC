import { expect } from "chai";
import type { HardhatEthers } from "@nomicfoundation/hardhat-ethers/types";
import type { NetworkHelpers } from "@nomicfoundation/hardhat-network-helpers/types";
import type { BaseContract, ContractTransactionResponse } from "ethers";
import { network } from "hardhat";
import type { NetworkConnection } from "hardhat/types/network";
import { AITokenRegistry__factory } from "../typechain-types";

type HardhatConnection = NetworkConnection & {
  ethers: HardhatEthers;
  networkHelpers: NetworkHelpers;
};

const { ethers, networkHelpers } =
  (await network.connect()) as HardhatConnection;

async function expectRevert(
  operation: Promise<unknown>,
  expectedMessage?: string,
) {
  let caughtError: unknown;

  try {
    await operation;
  } catch (error) {
    caughtError = error;
  }

  expect(caughtError).to.not.equal(undefined);

  if (expectedMessage !== undefined) {
    const message =
      caughtError instanceof Error ? caughtError.message : String(caughtError);
    expect(message).to.contain(expectedMessage);
  }
}

async function expectEvent(
  contract: BaseContract,
  operation: Promise<ContractTransactionResponse>,
  eventName: string,
  expectedArgs: readonly unknown[],
) {
  const tx = await operation;
  const receipt = await tx.wait();

  expect(receipt).to.not.equal(null);

  const parsedLog = receipt!.logs
    .map((log) => {
      try {
        return contract.interface.parseLog(log);
      } catch {
        return null;
      }
    })
    .find((entry) => entry?.name === eventName);

  expect(parsedLog).to.not.equal(undefined);
  expect(parsedLog).to.not.equal(null);
  expect(Array.from(parsedLog!.args)).to.deep.equal([...expectedArgs]);
}

async function deployRegistryFixture() {
  const [admin, coordinator, provider1, provider2, outsider] =
    await ethers.getSigners();

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
      const { registry, coordinator, provider1 } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      const collateral = ethers.parseEther("100");

      await expectEvent(
        registry,
        registry
          .connect(coordinator)
          .registerProvider(provider1.address, collateral),
        "ProviderRegistered",
        [provider1.address, collateral],
      );

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(true);
      expect(info.collateral).to.equal(collateral);
    });

    it("rejects registration of zero address", async function () {
      const { registry, coordinator } = await networkHelpers.loadFixture(
        deployRegistryFixture,
      );

      await expectRevert(
        registry.connect(coordinator).registerProvider(ethers.ZeroAddress, 0),
        "invalid provider",
      );
    });

    it("rejects duplicate registration", async function () {
      const { registry, coordinator, provider1 } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      await registry
        .connect(coordinator)
        .registerProvider(provider1.address, 100);

      await expectRevert(
        registry.connect(coordinator).registerProvider(provider1.address, 200),
        "already registered",
      );
    });

    it("rejects registration from non-coordinator", async function () {
      const { registry, provider1, outsider } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      await expectRevert(
        registry.connect(outsider).registerProvider(provider1.address, 100),
      );
    });
  });

  describe("Provider Updates", function () {
    it("allows coordinator to update provider status", async function () {
      const { registry, coordinator, provider1 } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      await registry
        .connect(coordinator)
        .registerProvider(provider1.address, 100);

      await expectEvent(
        registry,
        registry
          .connect(coordinator)
          .updateProvider(provider1.address, false, 50),
        "ProviderUpdated",
        [provider1.address, false, 50n],
      );

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(false);
      expect(info.collateral).to.equal(50);
    });

    it("allows reactivating a deactivated provider", async function () {
      const { registry, coordinator, provider1 } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      await registry
        .connect(coordinator)
        .registerProvider(provider1.address, 100);
      await registry
        .connect(coordinator)
        .updateProvider(provider1.address, false, 100);
      await registry
        .connect(coordinator)
        .updateProvider(provider1.address, true, 200);

      const info = await registry.providerInfo(provider1.address);
      expect(info.active).to.equal(true);
      expect(info.collateral).to.equal(200);
    });

    it("rejects update of unregistered provider", async function () {
      const { registry, coordinator, provider1 } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      await expectRevert(
        registry
          .connect(coordinator)
          .updateProvider(provider1.address, false, 100),
        "provider not registered",
      );
    });
  });

  describe("Access Control", function () {
    it("admin can grant coordinator role", async function () {
      const { registry, admin, outsider } = await networkHelpers.loadFixture(
        deployRegistryFixture,
      );

      const coordinatorRole = await registry.COORDINATOR_ROLE();
      await registry
        .connect(admin)
        .grantRole(coordinatorRole, outsider.address);

      expect(
        await registry.hasRole(coordinatorRole, outsider.address),
      ).to.equal(true);
    });

    it("non-admin cannot grant roles", async function () {
      const { registry, coordinator, outsider } =
        await networkHelpers.loadFixture(deployRegistryFixture);

      const coordinatorRole = await registry.COORDINATOR_ROLE();

      await expectRevert(
        registry
          .connect(coordinator)
          .grantRole(coordinatorRole, outsider.address),
      );
    });
  });
});
