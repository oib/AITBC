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
  isOnlyOwnerRevert,
  publicClient,
  queryFilterChunked,
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

    // Negative: one signature must not execute — and the refusal must be the
    // specific missing-signature error, not any failure (BR-11 finding 1).
    const err = await assertSingleSigCannotExecute(kit2, txSpec, provider);
    expect(err).to.be.instanceOf(Error);
    expect(`${err.shortMessage ?? ""} ${err.message}`).to.match(/signature missing|signatures? data|GS0(20|26)/i);

    // Negative: a direct EOA call to the owner-only fn must revert with the
    // bridge's actual OZ 4.x onlyOwner reason (BR-11 finding 2). On hardhat
    // the revert surfaces as SolidityError code 3 with Error(string) data —
    // isOnlyOwnerRevert decodes it; a JsonRpcProvider surfaces CALL_EXCEPTION.
    let reverted = false;
    try {
      await bridge.connect(s2).setFeeRecipient.staticCall(s2.address);
    } catch (e) {
      expect(isOnlyOwnerRevert(e)).to.equal(true);
      reverted = true;
    }
    expect(reverted).to.equal(true);

    // B4 — two locally collected signatures (signer2 + signer3); signer1's kit
    // only submits execTransaction (pays gas, adds no signature) — same split
    // as the live script where signer1 is the only funded account. NB the kit
    // must be bound to the deployed safeAddress (a predicted-mode kit refuses
    // executeTransaction as "not deployed").
    const kitExec = await initKit({ provider, signerKey: s1.privateKey, safeAddress, contractNetworks });
    const result = await signAndExecute([kit2, kit3], txSpec, { executor: kitExec });
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

  /** Wrap an EIP-1193 provider so one nonce() eth_call answers a stale value
   *  once `armed` is set — the lagging-replica shape that caused the ETH-3
   *  GS026. Only Safe.nonce() (selector 0xaffed0e0) is intercepted. */
  function staleNonceOnce(inner, safeAddr, staleValue) {
    const wrapped = {
      armed: false,
      request: async (args) => {
        const p0 = args?.params?.[0];
        if (
          wrapped.armed
          && args?.method === "eth_call"
          && typeof p0?.to === "string"
          && p0.to.toLowerCase() === safeAddr.toLowerCase()
          && typeof p0?.data === "string"
          && p0.data.startsWith("0xaffed0e0")
        ) {
          wrapped.armed = false;
          return `0x${BigInt(staleValue).toString(16).padStart(64, "0")}`;
        }
        return inner.request(args);
      },
      on: (...a) => inner.on?.(...a),
      once: (...a) => inner.once?.(...a),
      emit: (...a) => inner.emit?.(...a),
      removeListener: (...a) => inner.removeListener?.(...a),
    };
    return wrapped;
  }

  it("recovers a once-stale Safe nonce read (ETH-3 GS026 regression)", async function () {
    const owners = [s1.address, s2.address, s3.address];
    const { safeAddress } = await deploySafe({
      provider,
      deployerKey: s1.privateKey,
      owners,
      threshold: 2,
      contractNetworks,
      saltNonce: "7708",
    });
    const BridgeFactory = await ethers.getContractFactory("CrossChainBridge", funder);
    const bridge = await BridgeFactory.deploy(s1.address);
    await bridge.waitForDeployment();
    const bridgeAddress = await bridge.getAddress();
    await (await bridge.pause()).wait();
    await (await bridge.transferOwnership(safeAddress)).wait();

    const txSpec = [{ to: bridgeAddress, value: "0", data: bridge.interface.encodeFunctionData("setFeeRecipient", [s2.address]) }];

    // kit2's provider is wrapped — the nonce guard polls kits[0].getNonce().
    const laggy = staleNonceOnce(provider, safeAddress, 0);
    const kit2 = await initKit({ provider: laggy, signerKey: s2.privateKey, safeAddress, contractNetworks });
    const kit3 = await initKit({ provider, signerKey: s3.privateKey, safeAddress, contractNetworks });
    const kitExec = await initKit({ provider, signerKey: s1.privateKey, safeAddress, contractNetworks });
    const chainNonce = async () => {
      const c = new ethers.Contract(safeAddress, ["function nonce() view returns (uint256)"], ethers.provider);
      return Number(await c.nonce());
    };

    // Exec #1 pinned at nonce 0 — lands, Safe nonce is now 1.
    const r1 = await signAndExecute([kit2, kit3], txSpec, { executor: kitExec, expectedNonce: 0 });
    await publicClient(provider).waitForTransactionReceipt({ hash: r1.hash ?? r1.transactionResponse?.hash });
    expect(await chainNonce()).to.equal(1);

    // Exec #2: the first nonce read through kit2's provider lies — returns 0
    // while the chain is at 1. The guard polls past it and signs nonce 1.
    laggy.armed = true;
    const r2 = await signAndExecute([kit2, kit3], txSpec, { executor: kitExec, expectedNonce: 1, noncePollIntervalMs: 50 });
    await publicClient(provider).waitForTransactionReceipt({ hash: r2.hash ?? r2.transactionResponse?.hash });
    expect(await chainNonce()).to.equal(2);
  });

  /** Wrap an EIP-1193 provider so eth_getLogs refuses any range wider than
   *  `cap` blocks with the same -32701 shape publicnode returned in the ETH-3
   *  resumed run ("exceed maximum block range"). The real cap is 50,000 — far
   *  wider than any hardhat chain — so the test reproduces it at small scale;
   *  the chunking path is identical either way. */
  function cappedGetLogs(inner, cap) {
    const num = async (v) => {
      if (v === undefined || v === "latest" || v === "pending") {
        return parseInt(await inner.request({ method: "eth_blockNumber" }), 16);
      }
      if (v === "earliest") return 0;
      if (typeof v === "number") return v;
      if (typeof v === "bigint") return Number(v);
      return parseInt(v, 16);
    };
    return {
      request: async (args) => {
        if (args?.method === "eth_getLogs") {
          const p = args.params?.[0] ?? {};
          const [from, to] = [await num(p.fromBlock), await num(p.toBlock)];
          if (to - from > cap) {
            const err = new Error("exceed maximum block range: 50000");
            err.code = -32701;
            throw err;
          }
        }
        return inner.request(args);
      },
      on: (...a) => inner.on?.(...a),
      once: (...a) => inner.once?.(...a),
      emit: (...a) => inner.emit?.(...a),
      removeListener: (...a) => inner.removeListener?.(...a),
    };
  }

  it("chunks event queries under an eth_getLogs range cap (ETH-3 -32701 regression)", async function () {
    const BridgeFactory = await ethers.getContractFactory("CrossChainBridge", funder);
    const bridge = await BridgeFactory.deploy(s1.address);
    await bridge.waitForDeployment();
    const deployBlock = (await bridge.deploymentTransaction().wait()).blockNumber;
    // Put real distance between the event and the head so one window cannot
    // cover the whole range.
    await ethers.provider.send("hardhat_mine", ["0x10"]);

    const cap = 4;
    const bp = new ethers.BrowserProvider(cappedGetLogs(provider, cap));
    const capped = new ethers.Contract(
      await bridge.getAddress(),
      ["event OwnershipTransferred(address indexed previousOwner, address indexed newOwner)"],
      bp,
    );
    const filter = capped.filters.OwnershipTransferred();

    // What the old code did — one unbounded query — must fail under the cap.
    let threw = false;
    try {
      await capped.queryFilter(filter, 0, "latest");
    } catch (e) {
      expect(`${e.code ?? ""} ${e.message}`).to.match(/maximum block range|-32701/);
      threw = true;
    }
    expect(threw).to.equal(true);

    // The chunked helper subdivides oversized windows until each fits under
    // the cap, and finds the log.
    const latest = await bp.getBlockNumber();
    const windows = [];
    const logs = await queryFilterChunked(capped, filter, {
      fromBlock: 0, toBlock: latest, chunkSize: 16, firstOnly: true,
      log: (l) => windows.push(l),
    });
    expect(logs.length).to.equal(1);
    expect(logs[0].blockNumber).to.equal(deployBlock);
    expect(logs[0].args.newOwner).to.equal(funder.address);
    expect(windows.length).to.be.greaterThan(1); // actually chunked
  });

  it("refuses to sign when the Safe nonce never reaches the expected value", async function () {
    const owners = [s1.address, s2.address, s3.address];
    const { safeAddress } = await deploySafe({
      provider,
      deployerKey: s1.privateKey,
      owners,
      threshold: 2,
      contractNetworks,
      saltNonce: "7709",
    });
    const kit2 = await initKit({ provider, signerKey: s2.privateKey, safeAddress, contractNetworks });
    const kit3 = await initKit({ provider, signerKey: s3.privateKey, safeAddress, contractNetworks });
    let threw = false;
    try {
      await signAndExecute([kit2, kit3], [{ to: s1.address, value: "0", data: "0x" }], { expectedNonce: 7, noncePollAttempts: 3, noncePollIntervalMs: 10 });
    } catch (e) {
      expect(`${e.message}`).to.match(/safe nonce reads .* expected 7/);
      threw = true;
    }
    expect(threw).to.equal(true);
  });
});
