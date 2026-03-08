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

  it("rejects minting to zero address", async function () {
    const { token, coordinator, attestor } = await loadFixture(deployAITokenFixture);

    const units = 100n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-4"));
    const signature = await buildSignature(token, attestor, ethers.ZeroAddress, units, receiptHash);

    await expect(
      token
        .connect(coordinator)
        .mintWithReceipt(ethers.ZeroAddress, units, receiptHash, signature)
    ).to.be.revertedWith("invalid provider");
  });

  it("rejects minting zero units", async function () {
    const { token, coordinator, attestor, provider } = await loadFixture(deployAITokenFixture);

    const units = 0n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-5"));
    const signature = await buildSignature(token, attestor, provider.address, units, receiptHash);

    await expect(
      token
        .connect(coordinator)
        .mintWithReceipt(provider.address, units, receiptHash, signature)
    ).to.be.revertedWith("invalid units");
  });

  it("rejects minting from non-coordinator", async function () {
    const { token, attestor, provider, outsider } = await loadFixture(deployAITokenFixture);

    const units = 100n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-6"));
    const signature = await buildSignature(token, attestor, provider.address, units, receiptHash);

    await expect(
      token
        .connect(outsider)
        .mintWithReceipt(provider.address, units, receiptHash, signature)
    ).to.be.reverted;
  });

  it("returns correct mint digest", async function () {
    const { token, provider } = await loadFixture(deployAITokenFixture);

    const units = 100n;
    const receiptHash = ethers.keccak256(ethers.toUtf8Bytes("receipt-7"));

    const digest = await token.mintDigest(provider.address, units, receiptHash);
    expect(digest).to.be.a("string");
    expect(digest.length).to.equal(66); // 0x + 64 hex chars
  });

  it("has correct token name and symbol", async function () {
    const { token } = await loadFixture(deployAITokenFixture);

    expect(await token.name()).to.equal("AIToken");
    expect(await token.symbol()).to.equal("AIT");
  });
});
