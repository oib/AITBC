/**
 * BR-9 rehearsal — local hardhat exercise of the exact Safe flow the phase-B
 * scripts use: deploy Safe infra (v1.4.1 artifacts), create a 2-of-3 Safe,
 * own the bridge with it, one owner-only call executed with two locally
 * collected signatures, plus the two negative checks. No network, no key
 * files — throwaway in-test keys only.
 */
import { expect } from "chai";
import { network } from "hardhat";
import fs from "node:fs";
import { createRequire } from "node:module";
import Safe from "@safe-global/protocol-kit";
import {
  assertSignerOwners,
  assertSingleSigCannotExecute,
  deploySafe,
  initKit,
  publicClient,
  signAndExecute,
} from "../scripts/rehearsal/lib.js";

const require = createRequire(import.meta.url);
const SAFE_ARTIFACTS = "@safe-global/safe-contracts/build/artifacts/contracts";

function artifact(name) {
  return JSON.parse(fs.readFileSync(require.resolve(`${SAFE_ARTIFACTS}/${name}`), "utf8"));
}

describe("RehearsalSafe (BR-9 phase A, hardhat)", function () {
  this.timeout(120000);

  let conn, ethers, provider, chainId, funder;
  let contractNetworks;
  let s1, s2, s3; // throwaway in-test wallets == rehearsal signer1..3
  const gasLog = {};

  async function deployArtifact(name, deployer) {
    const { abi, bytecode } = artifact(name);
    const factory = new ethers.ContractFactory(abi, bytecode, deployer);
    const c = await factory.deploy();
    await c.waitForDeployment();
    return c;
  }

  before(async function () {
    conn = await network.getOrCreate();
    ethers = conn.ethers;
    provider = conn.provider;
    chainId = (await ethers.provider.getNetwork()).chainId;
    [funder] = await ethers.getSigners();

    // Three throwaway rehearsal signers, funded for gas.
    s1 = ethers.Wallet.createRandom().connect(ethers.provider);
    s2 = ethers.Wallet.createRandom().connect(ethers.provider);
    s3 = ethers.Wallet.createRandom().connect(ethers.provider);
    for (const w of [s1, s2, s3]) {
      await (await funder.sendTransaction({ to: w.address, value: ethers.parseEther("1") })).wait();
    }

    // Safe v1.4.1 infrastructure on the in-process chain.
    const safe = await deployArtifact("Safe.sol/Safe.json", funder);
    const safeL2 = await deployArtifact("SafeL2.sol/SafeL2.json", funder);
    const factory = await deployArtifact("proxies/SafeProxyFactory.sol/SafeProxyFactory.json", funder);
    const multiSend = await deployArtifact("libraries/MultiSend.sol/MultiSend.json", funder);
    const multiSendCallOnly = await deployArtifact("libraries/MultiSendCallOnly.sol/MultiSendCallOnly.json", funder);
    const fallbackHandler = await deployArtifact("handler/CompatibilityFallbackHandler.sol/CompatibilityFallbackHandler.json", funder);
    const signMessageLib = await deployArtifact("libraries/SignMessageLib.sol/SignMessageLib.json", funder);
    const simulateTxAccessor = await deployArtifact("accessors/SimulateTxAccessor.sol/SimulateTxAccessor.json", funder);
    const createCall = await deployArtifact("libraries/CreateCall.sol/CreateCall.json", funder);

    const a = (c) => c.target ?? c.address;
    const abi = (n) => artifact(n).abi;
    contractNetworks = {
      [chainId.toString()]: {
        safeSingletonAddress: a(safe),
        safeSingletonAbi: abi("Safe.sol/Safe.json"),
        safeProxyFactoryAddress: a(factory),
        safeProxyFactoryAbi: abi("proxies/SafeProxyFactory.sol/SafeProxyFactory.json"),
        multiSendAddress: a(multiSend),
        multiSendAbi: abi("libraries/MultiSend.sol/MultiSend.json"),
        multiSendCallOnlyAddress: a(multiSendCallOnly),
        multiSendCallOnlyAbi: abi("libraries/MultiSendCallOnly.sol/MultiSendCallOnly.json"),
        fallbackHandlerAddress: a(fallbackHandler),
        fallbackHandlerAbi: abi("handler/CompatibilityFallbackHandler.sol/CompatibilityFallbackHandler.json"),
        signMessageLibAddress: a(signMessageLib),
        signMessageLibAbi: abi("libraries/SignMessageLib.sol/SignMessageLib.json"),
        simulateTxAccessorAddress: a(simulateTxAccessor),
        simulateTxAccessorAbi: abi("accessors/SimulateTxAccessor.sol/SimulateTxAccessor.json"),
        createCallAddress: a(createCall),
        createCallAbi: abi("libraries/CreateCall.sol/CreateCall.json"),
      },
    };
    // keep SafeL2 referenced: L1 singleton suffices; L2 deployed for parity with
    // networks where protocol-kit picks the L2 flavor.
    expect(await safeL2.getAddress()).to.match(/^0x[0-9a-fA-F]{40}$/);
  });

  it("runs the full 2-of-3 owner flow with negative checks", async function () {
    const owners = [s1.address, s2.address, s3.address];

    // B1 — create the Safe (signer1 pays, like the real script).
    const { safeAddress, kit: kit1, gasUsed: safeGas } = await deploySafe({
      provider,
      deployerKey: s1.privateKey,
      owners,
      threshold: 2,
      contractNetworks,
    });
    gasLog.safeDeploy = safeGas;
    assertSignerOwners(await kit1.getOwners(), owners);
    expect(await kit1.getThreshold()).to.equal(2);

    // B2/B3 — deploy the bridge paused and hand it to the Safe.
    const BridgeFactory = await ethers.getContractFactory("CrossChainBridge", funder);
    const bridge = await BridgeFactory.deploy(s1.address);
    await bridge.waitForDeployment();
    const bridgeAddress = await bridge.getAddress();
    gasLog.bridgeDeploy = (await bridge.deploymentTransaction().wait()).gasUsed;
    await (await bridge.pause()).wait();
    await (await bridge.transferOwnership(safeAddress)).wait();
    expect(await bridge.owner()).to.equal(safeAddress);
    expect(await bridge.paused()).to.equal(true);

    const callData = bridge.interface.encodeFunctionData("setFeeRecipient", [s1.address]);
    const txSpec = [{ to: bridgeAddress, value: "0", data: callData }];

    const kit2 = await initKit({ provider, signerKey: s2.privateKey, safeAddress, contractNetworks });
    const kit3 = await initKit({ provider, signerKey: s3.privateKey, safeAddress, contractNetworks });

    // Negative: one signature must not execute.
    const err = await assertSingleSigCannotExecute(kit2, txSpec, provider);
    expect(err).to.be.instanceOf(Error);

    // Negative: a direct EOA call to the owner-only fn must revert.
    let reverted = false;
    try {
      await bridge.connect(s2).setFeeRecipient.staticCall(s2.address);
    } catch {
      reverted = true;
    }
    expect(reverted).to.equal(true);

    // B4 — two locally collected signatures (signer2 + signer3), then execute.
    const result = await signAndExecute([kit2, kit3], txSpec);
    const execHash = result.hash ?? result.transactionResponse?.hash;
    expect(execHash).to.match(/^0x[0-9a-fA-F]{64}$/);
    const receipt = await publicClient(provider).waitForTransactionReceipt({ hash: execHash });
    gasLog.safeExec = receipt.gasUsed;

    // Read-back: effect landed, bridge still paused, owner still the Safe.
    expect(await bridge.feeRecipient()).to.equal(s1.address);
    expect(await bridge.paused()).to.equal(true);
    expect(await bridge.owner()).to.equal(safeAddress);

    console.log("gas:", Object.fromEntries(Object.entries(gasLog).map(([k, v]) => [k, v.toString()])));
  });

  it("refuses a wrong owner set (guard sanity)", function () {
    const signers = [s1.address, s2.address, s3.address];
    expect(() => assertSignerOwners([s1.address, s2.address], signers)).to.throw();
    expect(() => assertSignerOwners([s1.address, s2.address, funder.address], signers)).to.throw();
    expect(() => assertSignerOwners(signers, signers)).to.not.throw();
  });
});
