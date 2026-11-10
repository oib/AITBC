import { expect } from "chai";
import { network } from "hardhat";
const { ethers } = await network.getOrCreate();

describe("ContractRegistry", function () {
  let contractRegistry;
  let deployer, user1, user2;
  let contractId1, contractId2;
  // registerContract/updateContract reject EOAs (NoCodeAtAddress, #1122),
  // so "registered contracts" in these tests are stub deployments, not
  // signer addresses.
  let contractAddr1, contractAddr2;

  beforeEach(async function () {
    [deployer, user1, user2] = await ethers.getSigners();

    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();

    const MockVerifier = await ethers.getContractFactory("MockVerifier");
    const stub1 = await MockVerifier.deploy();
    const stub2 = await MockVerifier.deploy();
    await stub1.waitForDeployment();
    await stub2.waitForDeployment();
    contractAddr1 = await stub1.getAddress();
    contractAddr2 = await stub2.getAddress();

    contractId1 = ethers.keccak256(ethers.toUtf8Bytes("Contract1"));
    contractId2 = ethers.keccak256(ethers.toUtf8Bytes("Contract2"));
  });

  describe("Deployment", function () {
    it("Should deploy successfully", async function () {
      expect(await contractRegistry.getAddress()).to.not.be.undefined;
    });

    it("Should set deployer as owner", async function () {
      expect(await contractRegistry.owner()).to.equal(deployer.address);
    });
  });

  describe("Contract Registration", function () {
    it("Should register a contract", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);

      const registeredAddress = await contractRegistry.getContract(contractId1);
      expect(registeredAddress).to.equal(contractAddr1);
    });

    it("Should emit ContractRegistered event", async function () {
      await expect(
        contractRegistry.registerContract(contractId1, contractAddr1)
      ).to.emit(contractRegistry, "ContractRegistered")
        .withArgs(contractId1, contractAddr1, 1);
    });

    it("Should revert if non-owner tries to register", async function () {
      await expect(
        contractRegistry.connect(user1).registerContract(contractId1, contractAddr1)
      ).to.be.revertedWithCustomError(contractRegistry, "NotAuthorized");
    });

    it("Should revert if address is zero", async function () {
      await expect(
        contractRegistry.registerContract(contractId1, ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(contractRegistry, "InvalidAddress");
    });
  });

  describe("Contract Retrieval", function () {
    it("Should retrieve registered contract", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);

      const address = await contractRegistry.getContract(contractId1);
      expect(address).to.equal(contractAddr1);
    });

    it("Should revert for unregistered contract", async function () {
      await expect(
        contractRegistry.getContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "ContractNotFound");
    });
  });

  describe("Contract Deregistration", function () {
    it("Should deregister a contract", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);
      await contractRegistry.deregisterContract(contractId1);

      await expect(
        contractRegistry.getContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "ContractNotFound");
    });

    it("Should emit ContractDeregistered event", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);

      await expect(
        contractRegistry.deregisterContract(contractId1)
      ).to.emit(contractRegistry, "ContractDeregistered")
        .withArgs(contractId1, contractAddr1);
    });

    it("Should revert if non-owner tries to deregister", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);

      await expect(
        contractRegistry.connect(user1).deregisterContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "NotAuthorized");
    });
  });

  describe("Batch Operations", function () {
    it("Should register multiple contracts", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);
      await contractRegistry.registerContract(contractId2, contractAddr2);

      expect(await contractRegistry.getContract(contractId1)).to.equal(contractAddr1);
      expect(await contractRegistry.getContract(contractId2)).to.equal(contractAddr2);
    });

    it("Should check if contract is registered", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);

      expect(await contractRegistry.isRegisteredContract(contractAddr1)).to.be.true;
      expect(await contractRegistry.isRegisteredContract(contractAddr2)).to.be.false;
    });
  });

  describe("Registry State", function () {
    it("Should get registry statistics", async function () {
      const stats = await contractRegistry.getRegistryStats();
      expect(stats.totalContracts).to.equal(1); // Registry itself is registered

      await contractRegistry.registerContract(contractId1, contractAddr1);
      const statsAfter = await contractRegistry.getRegistryStats();
      expect(statsAfter.totalContracts).to.equal(2);
    });

    it("Should list all registered contracts", async function () {
      await contractRegistry.registerContract(contractId1, contractAddr1);
      await contractRegistry.registerContract(contractId2, contractAddr2);

      const [ids, addresses] = await contractRegistry.listContracts();
      expect(ids.length).to.be.gte(2);
      expect(addresses.length).to.equal(ids.length);
    });
  });
});
