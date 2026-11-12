// CONTRACT-CROSSCHAINBRIDGE-SIG-1 (#1463): validator confirmation signatures
// must be EIP-712 digests bound to chainid + verifyingContract. The pre-fix
// format -- personal-sign over keccak256(requestId|lockTxHash|chainid) --
// carried no contract binding, so a quorum signature for one bridge
// deployment replayed on any other deployment of the same contract on the
// same chain (requestIds are per-contract counters starting at 1).
//
// DEPLOYMENT NOTE: the live Sepolia bridge (deployments-bridge-sepolia.json,
// 0x29D5…ed9) still verifies the OLD format. This change only takes effect
// on a NEW deployment, and every validator must switch to signing the
// EIP-712 digest (see bridge.confirmationDigest(requestId, lockTxHash)).

import { expect } from "chai";
import { network } from "hardhat";
const { ethers } = await network.getOrCreate();

const DOMAIN_NAME = "CrossChainBridge";
const DOMAIN_VERSION = "1";
const TYPES = {
  BridgeConfirmation: [
    { name: "requestId", type: "uint256" },
    { name: "lockTxHash", type: "bytes32" },
  ],
};

describe("CrossChainBridge EIP-712 confirmation signatures (#1463)", function () {
  let token, bridge, bridge2, owner, validator, validator2, user;

  async function deployBridge() {
    const Bridge = await ethers.getContractFactory("CrossChainBridge");
    const b = await Bridge.deploy(owner.address);
    await b.waitForDeployment();
    await b.addSupportedToken(await token.getAddress(), ethers.parseEther("500000"), 0, false);
    // #795: initiateBridge requires >= MIN_QUORUM(2) active validators.
    await b.addValidator(validator.address, 1);
    await b.addValidator(validator2.address, 1);
    return b;
  }

  beforeEach(async function () {
    [owner, validator, validator2, user] = await ethers.getSigners();

    const Token = await ethers.getContractFactory("AIToken");
    token = await Token.deploy(ethers.parseEther("1000000"));
    await token.waitForDeployment();
    await token.transfer(user.address, ethers.parseEther("10000"));

    bridge = await deployBridge();
    bridge2 = await deployBridge();
  });

  async function initiate(b, amount = ethers.parseEther("100")) {
    await token.connect(user).approve(await b.getAddress(), amount);
    const tx = await b.connect(user).initiateBridge(
      await token.getAddress(),
      await token.getAddress(),
      amount,
      1, // target chain (constructor seeds chain 1; hardhat chainId differs)
      user.address
    );
    await tx.wait();
    return b.requestCounter();
  }

  async function signTyped(b, requestId, lockTxHash, signer = validator) {
    const domain = {
      name: DOMAIN_NAME,
      version: DOMAIN_VERSION,
      chainId: (await ethers.provider.getNetwork()).chainId,
      verifyingContract: await b.getAddress(),
    };
    return signer.signTypedData(domain, TYPES, { requestId, lockTxHash });
  }

  /// The pre-#1463 format: personal-sign (EIP-191) over
  /// keccak256(abi.encodePacked(requestId, lockTxHash, chainid)).
  async function signLegacy(requestId, lockTxHash, signer = validator) {
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const messageHash = ethers.keccak256(
      ethers.solidityPacked(["uint256", "bytes32", "uint256"], [requestId, lockTxHash, chainId])
    );
    return signer.signMessage(ethers.getBytes(messageHash));
  }

  it("accepts an EIP-712 signature bound to this deployment", async function () {
    const requestId = await initiate(bridge);
    const lockTxHash = ethers.keccak256(ethers.toUtf8Bytes("lock-tx"));

    // sanity: the contract exposes the exact digest off-chain signers need
    const digest = await bridge.confirmationDigest(requestId, lockTxHash);
    expect(digest).to.match(/^0x[0-9a-fA-F]{64}$/);

    await expect(
      bridge.connect(validator).confirmBridge(requestId, lockTxHash, await signTyped(bridge, requestId, lockTxHash))
    ).to.emit(bridge, "BridgeConfirmed");
  });

  it("rejects a legacy-format (pre-#1463) signature", async function () {
    const requestId = await initiate(bridge);
    const lockTxHash = ethers.keccak256(ethers.toUtf8Bytes("lock-tx-legacy"));

    const legacySig = await signLegacy(requestId, lockTxHash);
    await expect(
      bridge.connect(validator).confirmBridge(requestId, lockTxHash, legacySig)
    ).to.be.revertedWith("Invalid signature");
    expect(await bridge.validateBridgeRequest(requestId, lockTxHash, legacySig)).to.equal(false);
  });

  it("rejects a signature minted for a different bridge deployment", async function () {
    // Identical requestId on both deployments (per-contract counters start
    // at 1) and the same lockTxHash — the replay shape from the issue.
    const requestId1 = await initiate(bridge);
    const requestId2 = await initiate(bridge2);
    expect(requestId1).to.equal(requestId2);

    const lockTxHash = ethers.keccak256(ethers.toUtf8Bytes("shared-lock"));
    const sigForBridge1 = await signTyped(bridge, requestId1, lockTxHash);

    await expect(
      bridge2.connect(validator).confirmBridge(requestId2, lockTxHash, sigForBridge1)
    ).to.be.revertedWith("Invalid signature");

    // The correctly domain-bound signature still works on bridge2.
    await expect(
      bridge2.connect(validator).confirmBridge(requestId2, lockTxHash, await signTyped(bridge2, requestId2, lockTxHash))
    ).to.emit(bridge2, "BridgeConfirmed");
  });
});
