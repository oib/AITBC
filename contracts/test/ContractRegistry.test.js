import { expect } from "chai";
import hardhat from "hardhat";
const { ethers } = hardhat;

describe("ContractRegistry", function () {
  let contractRegistry;
  let deployer, user1, user2;
  let contractId1, contractId2;

  beforeEach(async function () {
    [deployer, user1, user2] = await ethers.getSigners();

    const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
    contractRegistry = await ContractRegistry.deploy();
    await contractRegistry.waitForDeployment();

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
      await contractRegistry.registerContract(contractId1, user1.address);
      
      const registeredAddress = await contractRegistry.getContract(contractId1);
      expect(registeredAddress).to.equal(user1.address);
    });

    it("Should emit ContractRegistered event", async function () {
      await expect(
        contractRegistry.registerContract(contractId1, user1.address)
      ).to.emit(contractRegistry, "ContractRegistered")
        .withArgs(contractId1, user1.address, 1);
    });

    it("Should revert if non-owner tries to register", async function () {
      await expect(
        contractRegistry.connect(user1).registerContract(contractId1, user1.address)
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
      await contractRegistry.registerContract(contractId1, user1.address);
      
      const address = await contractRegistry.getContract(contractId1);
      expect(address).to.equal(user1.address);
    });

    it("Should revert for unregistered contract", async function () {
      await expect(
        contractRegistry.getContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "ContractNotFound");
    });
  });

  describe("Contract Deregistration", function () {
    it("Should deregister a contract", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      await contractRegistry.deregisterContract(contractId1);
      
      await expect(
        contractRegistry.getContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "ContractNotFound");
    });

    it("Should emit ContractDeregistered event", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      
      await expect(
        contractRegistry.deregisterContract(contractId1)
      ).to.emit(contractRegistry, "ContractDeregistered")
        .withArgs(contractId1, user1.address);
    });

    it("Should revert if non-owner tries to deregister", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      
      await expect(
        contractRegistry.connect(user1).deregisterContract(contractId1)
      ).to.be.revertedWithCustomError(contractRegistry, "NotAuthorized");
    });
  });

  describe("Batch Operations", function () {
    it("Should register multiple contracts", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      await contractRegistry.registerContract(contractId2, user2.address);
      
      expect(await contractRegistry.getContract(contractId1)).to.equal(user1.address);
      expect(await contractRegistry.getContract(contractId2)).to.equal(user2.address);
    });

    it("Should check if contract is registered", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      
      expect(await contractRegistry.isRegisteredContract(user1.address)).to.be.true;
      expect(await contractRegistry.isRegisteredContract(user2.address)).to.be.false;
    });
  });

  describe("Registry State", function () {
    it("Should get registry statistics", async function () {
      const stats = await contractRegistry.getRegistryStats();
      expect(stats.totalContracts).to.equal(1); // Registry itself is registered
      
      await contractRegistry.registerContract(contractId1, user1.address);
      const statsAfter = await contractRegistry.getRegistryStats();
      expect(statsAfter.totalContracts).to.equal(2);
    });

    it("Should list all registered contracts", async function () {
      await contractRegistry.registerContract(contractId1, user1.address);
      await contractRegistry.registerContract(contractId2, user2.address);
      
      const [ids, addresses] = await contractRegistry.listContracts();
      expect(ids.length).to.be.gte(2);
      expect(addresses.length).to.equal(ids.length);
    });
  });
});
