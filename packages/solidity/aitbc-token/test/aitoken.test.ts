import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import type { Signer } from "ethers";
import type { AIToken } from "../typechain-types";
import { AIToken__factory } from "../typechain-types";

async function deployAITokenFixture() {
  const [admin, coordinator, attestor, provider, outsider] = await ethers.getSigners();

  const factory = new AIToken__factory(admin);
  const token = await factory.deploy(admin.address);
  await token.waitForDeployment();

  const coordinatorRole = await token.COORDINATOR_ROLE();
  const attestorRole = await token.ATTESTOR_ROLE();

  await token.grantRole(coordinatorRole, coordinator.address);
  await token.grantRole(attestorRole, attestor.address);

  return { token, admin, coordinator, attestor, provider, outsider };
}

async function buildSignature(
  token: AIToken,
  attestor: Signer,
  provider: string,
  units: bigint,
  receiptHash: string
) {
  const chainId = (await ethers.provider.getNetwork()).chainId;
  const contractAddress = await token.getAddress();
  const abiCoder = ethers.AbiCoder.defaultAbiCoder();

  const encoded = abiCoder.encode(
    ["uint256", "address", "address", "uint256", "bytes32"],
    [chainId, contractAddress, provider, units, receiptHash]
  );

  const structHash = ethers.keccak256(encoded);
  return attestor.signMessage(ethers.getBytes(structHash));
}

describe("AIToken", function () {
  it("mints tokens when presented a valid attestor signature", async function () {
    const { token, coordinator, attestor, provider } = await loadFixture(deployAITokenFixture);

    const units = 100n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-1"));
    const signature = await buildSignature(token, attestor, provider.address, units, receiptHash);

    await expect(
      token
        .connect(coordinator)
        .mintWithReceipt(provider.address, units, receiptHash, signature)
    )
      .to.emit(token, "ReceiptConsumed")
      .withArgs(receiptHash, provider.address, units, attestor.address);

    expect(await token.balanceOf(provider.address)).to.equal(units);
    expect(await token.consumedReceipts(receiptHash)).to.equal(true);
  });

  it("rejects reuse of a consumed receipt hash", async function () {
    const { token, coordinator, attestor, provider } = await loadFixture(deployAITokenFixture);

    const units = 50n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-2"));
    const signature = await buildSignature(token, attestor, provider.address, units, receiptHash);

    await token
      .connect(coordinator)
      .mintWithReceipt(provider.address, units, receiptHash, signature);

    await expect(
      token
        .connect(coordinator)
        .mintWithReceipt(provider.address, units, receiptHash, signature)
    ).to.be.revertedWith("receipt already consumed");
  });

  it("rejects signatures from non-attestors", async function () {
    const { token, coordinator, attestor, provider, outsider } = await loadFixture(
      deployAITokenFixture
    );

    const units = 25n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-3"));
    const signature = await buildSignature(
      token,
      outsider,
      provider.address,
      units,
      receiptHash
    );

    await expect(
      token
        .connect(coordinator)
        .mintWithReceipt(provider.address, units, receiptHash, signature)
    ).to.be.revertedWith("invalid attestor signature");
  });
});
