/**
 * ETH-3 rehearsal round-trip — deposit + withdraw through the Safe-owned
 * CrossChainBridge on Sepolia (rehearsal contract, throwaway token).
 *
 * Sequence (every state-changing call is gated behind --live):
 *   preflight   chain id, Safe owners == signer1..3, owner==Safe, paused,
 *               signer balances (gas floors: signer1 >= 0.05, others >= 0.005)
 *   1  signer1 deploys a throwaway MockToken (or --token <addr> reuses one)
 *   2  Safe exec: unpause()                                    [kit2+kit3 sign, kit1 submits]
 *   3  Safe exec: addSupportedToken(token, cap=1000e18, fee=0, false)
 *   4  Safe exec x3: addValidator(signerN, 1)
 *   5  signer1: token.approve(bridge, 100e18) then
 *      initiateBridge(token, token, 100e18, targetChainId=1, signer1)
 *      — target chain 1 is the constructor-seeded Ethereum config; the
 *      contract refuses target == own chain and completeBridge can never
 *      run on Sepolia, so the withdraw leg is the owner emergency path.
 *   6  each signerN sends confirmBridge(requestId, lockTxHash, sig) from its
 *      own EOA — sig = personal_sign over keccak256(requestId|lockTxHash|chainId);
 *      onlyActiveValidator + signature-recover == msg.sender means no other
 *      account can submit on a validator's behalf. After 3 confirms the
 *      request is CONFIRMED (min falls back to MIN_CONFIRMATIONS=3).
 *   7  Safe exec: emergencyWithdraw(token, held)   — funds to the Safe
 *   8  Safe exec: token.transfer(signer1, held)    — funds home to deployer
 *   9  Safe exec: pause()                          — back to paused
 *
 * Default is DRY RUN: all reads and the full plan print, no key file is
 * read and nothing is sent. --live performs the sends.
 *
 *   REHEARSAL_KEYS_DIR=~/windsurf/aitbc/keys/rehearsal-sepolia \
 *   SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
 *   SAFE_ADDRESS=0xdd32... BRIDGE_ADDRESS=0xb78c... \
 *     node scripts/rehearsal/roundtrip.js [--live] [--token 0x...]
 */

import { ethers } from "ethers";
import { getAddress } from "viem";
import {
  assertSepolia,
  assertSignerOwners,
  findDeploymentBlock,
  initKit,
  normalizeAddresses,
  publicClient,
  queryFilterChunked,
  readSignerAddresses,
  readSignerKey,
  resolveKeysDir,
  signAndExecute,
} from "./lib.js";

const LIVE = process.argv.includes("--live");
// --token / --resume-token reuse an already-deployed MockToken (resume path).
const tokenIdx = Math.max(process.argv.indexOf("--token"), process.argv.indexOf("--resume-token"));
const REUSE_TOKEN = tokenIdx > -1 ? getAddress(process.argv[tokenIdx + 1]) : null;
// --from-block bounds every log scan (publicnode rejects ranges > 50k with
// -32701). --lock-tx supplies the deposit tx hash for a resumed request, so
// the BridgeInitiated lookup is a receipt check instead of a log scan.
const fbIdx = process.argv.indexOf("--from-block");
const FROM_BLOCK = fbIdx > -1 ? Number(process.argv[fbIdx + 1]) : null;
if (FROM_BLOCK !== null && (!Number.isInteger(FROM_BLOCK) || FROM_BLOCK < 0)) {
  throw new Error("--from-block must be a non-negative integer");
}
const ltIdx = process.argv.indexOf("--lock-tx");
const LOCK_TX = ltIdx > -1 ? process.argv[ltIdx + 1] : null;
if (LOCK_TX !== null && !/^0x[0-9a-fA-F]{64}$/.test(LOCK_TX)) {
  throw new Error("--lock-tx must be a transaction hash");
}

const CAP = 1000n * 10n ** 18n;        // lock cap — the value we stay under
const DEPOSIT = 100n * 10n ** 18n;     // the small deposit
const TARGET_CHAIN_ID = 1n;            // constructor-seeded "Ethereum" entry
const VALIDATOR_WEIGHT = 1n;

const rpcUrl = process.env.SEPOLIA_RPC_URL;
const safeAddress = process.env.SAFE_ADDRESS && getAddress(process.env.SAFE_ADDRESS);
const bridgeAddress = process.env.BRIDGE_ADDRESS && getAddress(process.env.BRIDGE_ADDRESS);
for (const [name, v] of [["SEPOLIA_RPC_URL", rpcUrl], ["SAFE_ADDRESS", safeAddress], ["BRIDGE_ADDRESS", bridgeAddress]]) {
  if (!v) throw new Error(`${name} is required`);
}

const BRIDGE_ABI = [
  "function paused() view returns (bool)",
  "function owner() view returns (address)",
  "function feeRecipient() view returns (address)",
  "function requestCounter() view returns (uint256)",
  "function supportedTokens(address) view returns (address tokenAddress, bool isActive, uint256 bridgeLimit, uint256 feePercentage, bool requiresWhitelist)",
  "function validators(address) view returns (address validatorAddress, bool isActive, uint256 weight, uint256 lastValidation, uint256 totalValidations)",
  "function activeValidators(uint256) view returns (address)",
  "function getBridgeRequest(uint256) view returns (uint256 sourceChainId, uint256 targetChainId, address sourceToken, uint256 amount, address recipient, uint8 status, uint256 createdAt)",
  "function unpause()",
  "function pause()",
  "function addSupportedToken(address,uint256,uint256,bool)",
  "function addValidator(address,uint256)",
  "function emergencyWithdraw(address,uint256)",
  "function initiateBridge(address,address,uint256,uint256,address) returns (uint256)",
  "function confirmBridge(uint256,bytes32,bytes)",
  "event BridgeInitiated(uint256 indexed requestId, address indexed sender, address indexed recipient, address sourceToken, uint256 amount, uint256 sourceChainId, uint256 targetChainId)",
  "event BridgeConfirmed(uint256 indexed requestId, address indexed validator, bytes32 lockTxHash)",
];
const ERC20_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function approve(address,uint256) returns (bool)",
  "function transfer(address,uint256) returns (bool)",
];
const MOCK_ARTIFACT_PATH = new URL("../../out/CrossChainBridge.t.sol/MockToken.json", import.meta.url);

const report = [];
const loadedKeys = [];
function note(line) {
  report.push(line);
  console.error(line);
}
/** Never let a loaded key reach the report — scan before declaring success. */
function assertReportClean() {
  const blob = report.join("\n");
  for (const k of loadedKeys) {
    if (k && (blob.includes(k) || blob.includes(k.slice(2)))) {
      throw new Error("report would contain key material — refusing to print");
    }
  }
}

const client = publicClient(rpcUrl);
const provider = new ethers.JsonRpcProvider(rpcUrl);
const iface = new ethers.Interface([...BRIDGE_ABI, ...ERC20_ABI]);
const ro = new ethers.Contract(bridgeAddress, BRIDGE_ABI, provider);
const keysDir = resolveKeysDir();
const signerAddresses = normalizeAddresses(readSignerAddresses(keysDir));

function key(n) {
  const k = readSignerKey(keysDir, n);
  loadedKeys.push(k);
  return k;
}

/**
 * Lower bound for every log scan: --from-block if given, else the bridge's
 * deployment block (binary-searched via eth_getCode — needs a full node),
 * else latest - 200000. The contract exposes no deploymentBlock accessor,
 * so this is the only readable source for it.
 */
let _logLo;
async function logLowerBound() {
  if (_logLo !== undefined) return _logLo;
  if (FROM_BLOCK !== null) return (_logLo = FROM_BLOCK);
  const latest = await provider.getBlockNumber();
  const dep = await findDeploymentBlock(provider, bridgeAddress, latest).catch(() => null);
  if (dep !== null) {
    note(`log-scan: bridge deployment block = ${dep}`);
    return (_logLo = dep);
  }
  const fallback = Math.max(0, latest - 200000);
  note(`log-scan: deployment block unreadable — lower bound = latest-200000 = ${fallback}`);
  return (_logLo = fallback);
}

/** One bounded scan; logs each window it touches. `fromBlock` overrides the
 *  resolved lower bound — confirmation scans use the deposit block, since a
 *  BridgeConfirmed log cannot precede the request it confirms. */
async function boundedFilter(filter, { firstOnly = true, fromBlock } = {}) {
  const lo = fromBlock !== undefined ? fromBlock : await logLowerBound();
  const hi = await provider.getBlockNumber();
  return queryFilterChunked(ro, filter, { fromBlock: lo, toBlock: hi, firstOnly, log: (l) => note(l) });
}

/**
 * Validate a --lock-tx claim without any log scan: the receipt must carry a
 * BridgeInitiated log from the bridge for `requestId`. Returns
 * { hash, blockNumber }. Throws otherwise.
 */
async function lockTxFromReceipt(requestId) {
  const receipt = await provider.getTransactionReceipt(LOCK_TX);
  if (!receipt) throw new Error(`--lock-tx ${LOCK_TX} has no receipt`);
  for (const log of receipt.logs) {
    if (log.address.toLowerCase() !== bridgeAddress.toLowerCase()) continue;
    let parsed;
    try { parsed = iface.parseLog(log); } catch { continue; }
    if (parsed?.name === "BridgeInitiated" && Number(parsed.args.requestId) === Number(requestId)) {
      return { hash: receipt.hash ?? receipt.transactionHash, blockNumber: receipt.blockNumber };
    }
  }
  throw new Error(`--lock-tx ${LOCK_TX} carries no BridgeInitiated log for request ${requestId}`);
}

assertSepolia(await client.getChainId());
note(`mode: ${LIVE ? "LIVE — transactions will be sent" : "DRY RUN — reads and plan only"}`);
note(`chain: ${await client.getChainId()}  safe: ${safeAddress}  bridge: ${bridgeAddress}`);

// ---- preflight reads (always run, never need keys) ----
const [paused0, owner, feeRecipient, requestCounter0] = await Promise.all([
  ro.paused(), ro.owner(), ro.feeRecipient(), ro.requestCounter(),
]);
const safeContract = new ethers.Contract(safeAddress, [
  "function getOwners() view returns (address[])",
  "function getThreshold() view returns (uint256)",
  "function nonce() view returns (uint256)",
], provider);
const [owners, threshold, safeNonce] = await Promise.all([
  safeContract.getOwners(), safeContract.getThreshold(), safeContract.nonce(),
]);
assertSignerOwners(owners, signerAddresses);
if (owner.toLowerCase() !== safeAddress.toLowerCase()) throw new Error(`bridge owner ${owner} != Safe`);
if (Number(threshold) !== 2) throw new Error(`Safe threshold ${threshold} != 2`);
note(`preflight: paused=${paused0} owner=${owner} feeRecipient=${feeRecipient}`);
note(`preflight: safe nonce=${safeNonce} threshold=${threshold} owners=${owners.join(",")}`);
note(`preflight: requestCounter=${requestCounter0}`);
const balances = await Promise.all(signerAddresses.map((a) => provider.getBalance(a)));
signerAddresses.forEach((a, i) => {
  const eth = ethers.formatEther(balances[i]);
  const floor = i === 0 ? 0.05 : 0.005;
  const flag = Number(eth) < floor ? "  <-- BELOW GAS FLOOR" : "";
  note(`preflight: signer${i + 1} ${a} balance ${eth} ETH${flag}`);
});
if (LIVE && (Number(ethers.formatEther(balances[0])) < 0.05
  || Number(ethers.formatEther(balances[1])) < 0.005
  || Number(ethers.formatEther(balances[2])) < 0.005)) {
  throw new Error("gas floor not met — fund the shortfall signers first (operator-only step)");
}

note(`plan: cap=${CAP} deposit=${DEPOSIT} targetChainId=${TARGET_CHAIN_ID}`);
if (!LIVE) {
  // Resume preview — the same per-step checks the live path applies, read-only.
  const preview = [];
  preview.push(`unpause: ${paused0 ? "RUN" : "SKIP"}`);
  const cfg = REUSE_TOKEN ? await ro.supportedTokens(REUSE_TOKEN) : null;
  preview.push(`addSupportedToken: ${cfg?.isActive && cfg.bridgeLimit === CAP ? "SKIP" : "RUN"}`);
  for (let i = 0; i < 3; i++) {
    const v = await ro.validators(signerAddresses[i]);
    preview.push(`addValidator signer${i + 1}: ${v.isActive ? "SKIP" : "RUN"}`);
  }
  preview.push(`deposit: ${Number(requestCounter0) === 0 ? "RUN" : `SKIP (adopt request ${requestCounter0})`}`);
  if (Number(requestCounter0) > 0) {
    // Same bounded scans the live resume uses — a range problem surfaces here.
    let depositBlock;
    if (LOCK_TX) {
      const lk = await lockTxFromReceipt(Number(requestCounter0));
      preview.push(`lockTxHash=${lk.hash} (--lock-tx receipt)`);
      depositBlock = lk.blockNumber;
    } else {
      const initLogs = await boundedFilter(ro.filters.BridgeInitiated(requestCounter0));
      preview.push(`lockTxHash=${initLogs[0]?.transactionHash ?? "NOT FOUND"}`);
      depositBlock = initLogs[0]?.blockNumber;
    }
    if (depositBlock === undefined) {
      preview.push("confirms: lock tx not in scan range — pass --lock-tx or --from-block");
    } else {
      for (let i = 0; i < 3; i++) {
        // Confirmations can't precede the deposit — floor the scan at it.
        const c = await boundedFilter(ro.filters.BridgeConfirmed(requestCounter0, signerAddresses[i]), { fromBlock: depositBlock });
        preview.push(`confirm signer${i + 1}: ${c.length ? "SKIP" : "RUN"}`);
      }
    }
  } else {
    preview.push("confirms: depend on request state");
  }
  preview.push(`withdraw/repatriate: depend on balances`);
  preview.push(`pause: ${paused0 ? "SKIP" : "RUN"}`);
  note(`resume preview — ${preview.join(" | ")}`);
  note("dry run complete — rerun with --live to execute (operator authorization required)");
  assertReportClean();
  process.exit(0);
}

// ---- everything below sends transactions ----
async function waitOk(hash, label, signerAddr) {
  const receipt = await client.waitForTransactionReceipt({ hash });
  if (receipt.status !== "success") throw new Error(`${label} reverted on-chain: ${hash}`);
  note(`${label}: tx ${hash} block ${receipt.blockNumber} gas ${receipt.gasUsed}`);
  if (signerAddr) await recordNonce(hash, signerAddr);
  return receipt;
}
// The nonce every Safe exec must sign next — seeded from the preflight read
// and stepped only after a sealed exec, so a lagging RPC replica can never
// smuggle an old nonce into the signed hash (ETH-3 GS026).
let nextSafeNonce = Number(safeNonce);
async function safeExec(to, data, label) {
  note(`safe-exec ${label}: nonce=${nextSafeNonce} to=${to} data=${data}`);
  const res = await signAndExecute([kit2, kit3], [{ to, value: "0", data }], { executor: kit1, expectedNonce: nextSafeNonce });
  const hash = res.hash ?? res.transactionResponse?.hash;
  await waitOk(hash, `safe-exec ${label}`, signerAddresses[0]); // kit1 (signer1) submits
  nextSafeNonce += 1;
}

// signer2+3 approve, signer1 pays gas — same pattern as safe-exec.js
const kit1 = await initKit({ provider: rpcUrl, signerKey: key(1), safeAddress });
const kit2 = await initKit({ provider: rpcUrl, signerKey: key(2), safeAddress });
const kit3 = await initKit({ provider: rpcUrl, signerKey: key(3), safeAddress });
const w = (n) => new ethers.Wallet(loadedKeys[n - 1], provider);
const w1 = w(1), w2 = w(2), w3 = w(3);
// fresh forks can report a getTransactionCount("latest") that has not yet
// indexed the just-mined receipt — poll until the count moves past the last
// nonce we saw land, then use it. On live Sepolia the first read passes.
const lastNonce = new Map();
async function nextNonce(addr) {
  const floor = (lastNonce.get(addr) ?? -1) + 1;
  let n = 0;
  for (let i = 0; i < 20; i++) {
    n = await provider.getTransactionCount(addr, "latest");
    if (n >= floor) { lastNonce.set(addr, n); return n; }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`nonce for ${addr} stuck below ${floor}`);
}
// after a mined receipt from addr, record the sender nonce so the next call
// waits for the node to index it
async function recordNonce(hash, addr) {
  const tx = await provider.getTransaction(hash);
  if (tx) lastNonce.set(addr, tx.nonce);
}

// 1 — throwaway token
let tokenAddress = REUSE_TOKEN;
if (!tokenAddress) {
  const artifact = JSON.parse(await (await import("node:fs")).promises.readFile(MOCK_ARTIFACT_PATH, "utf8"));
  const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode.object, w1);
  const token = await factory.deploy({ nonce: await nextNonce(signerAddresses[0]) });
  await waitOk(token.deploymentTransaction().hash, "MockToken deploy", signerAddresses[0]);
  tokenAddress = await token.getAddress();
}
note(`token: ${tokenAddress}`);
const token = new ethers.Contract(tokenAddress, ERC20_ABI, provider);

// 2 — unpause (resume: skip when already unpaused)
if (await ro.paused()) {
  await safeExec(bridgeAddress, iface.encodeFunctionData("unpause"), "unpause");
  if (await ro.paused()) throw new Error("bridge still paused after unpause exec");
  note("read-back: paused=false");
} else {
  note("skip: already unpaused");
}

// 3 — token config under the cap (resume: skip when already supported at cap)
{
  const cfg = await ro.supportedTokens(tokenAddress);
  if (cfg.isActive && cfg.bridgeLimit === CAP) {
    note("skip: token already supported at cap");
  } else {
    await safeExec(bridgeAddress, iface.encodeFunctionData("addSupportedToken", [tokenAddress, CAP, 0n, false]), "addSupportedToken cap=1000 MTK");
  }
}
const tcfg = await ro.supportedTokens(tokenAddress);
if (!tcfg.isActive || tcfg.bridgeLimit !== CAP) throw new Error(`token config wrong: ${tcfg}`);
note(`read-back: token active, bridgeLimit=${tcfg.bridgeLimit}`);

// 4 — three validators (the rehearsal signers; resume: skip the ones already active)
for (let i = 0; i < 3; i++) {
  const v = await ro.validators(signerAddresses[i]);
  if (v.isActive) {
    note(`skip: addValidator signer${i + 1} already active`);
    continue;
  }
  await safeExec(bridgeAddress, iface.encodeFunctionData("addValidator", [signerAddresses[i], VALIDATOR_WEIGHT]), `addValidator signer${i + 1}`);
}
note(`read-back: activeValidators[0..2] = ${await ro.activeValidators(0)}, ${await ro.activeValidators(1)}, ${await ro.activeValidators(2)}`);

// 5 — deposit under the cap (resume: adopt the existing request; the lock tx
// hash is recovered from the BridgeInitiated log — it is not in any view)
let requestId, lockTxHash, depositBlock;
const existingCounter = Number(await ro.requestCounter());
if (existingCounter === 0) {
  const tw = new ethers.Contract(tokenAddress, ERC20_ABI, w1);
  await waitOk((await tw.approve(bridgeAddress, DEPOSIT,
    { nonce: await nextNonce(signerAddresses[0]) })).hash, "approve", signerAddresses[0]);
  const bw = new ethers.Contract(bridgeAddress, BRIDGE_ABI, w1);
  const initTx = await bw.initiateBridge(tokenAddress, tokenAddress, DEPOSIT, TARGET_CHAIN_ID, signerAddresses[0],
    { nonce: await nextNonce(signerAddresses[0]) });
  const initReceipt = await waitOk(initTx.hash, "initiateBridge deposit", signerAddresses[0]);
  requestId = Number(await ro.requestCounter());
  lockTxHash = initReceipt.transactionHash;
  depositBlock = initReceipt.blockNumber;
  note(`requestId=${requestId} lockTxHash=${lockTxHash}`);
} else {
  requestId = existingCounter;
  const req0 = await ro.getBridgeRequest(requestId);
  if (Number(req0.status) > 1) {
    throw new Error(`existing request ${requestId} has terminal status ${req0.status} — refusing to resume`);
  }
  if (req0.sourceToken.toLowerCase() !== tokenAddress.toLowerCase()
    || req0.amount !== DEPOSIT
    || req0.recipient.toLowerCase() !== signerAddresses[0].toLowerCase()
    || req0.targetChainId !== TARGET_CHAIN_ID) {
    throw new Error(`existing request ${requestId} does not match this rehearsal's deposit — refusing`);
  }
  if (LOCK_TX) {
    const lk = await lockTxFromReceipt(requestId);
    lockTxHash = lk.hash;
    depositBlock = lk.blockNumber;
    note(`resume: lockTxHash=${lockTxHash} verified from --lock-tx receipt`);
  } else {
    const initLogs = await boundedFilter(ro.filters.BridgeInitiated(requestId));
    if (initLogs.length !== 1) {
      throw new Error(`expected one BridgeInitiated log for request ${requestId}, found ${initLogs.length}`);
    }
    lockTxHash = initLogs[0].transactionHash;
    depositBlock = Number(initLogs[0].blockNumber);
  }
  note(`resume: request ${requestId} exists (status ${req0.status}) — lockTxHash=${lockTxHash}`);
}

// 6 — validator confirmations, each sent by its own EOA (resume: skip
// validators whose BridgeConfirmed log already exists for this request)
const messageHash = ethers.keccak256(ethers.solidityPacked(
  ["uint256", "bytes32", "uint256"], [requestId, lockTxHash, 11155111]));
for (const [i, wallet] of [[1, w1], [2, w2], [3, w3]]) {
  const confirms = await boundedFilter(ro.filters.BridgeConfirmed(requestId, signerAddresses[i - 1]), { fromBlock: depositBlock });
  if (confirms.length > 0) {
    note(`skip: confirmBridge signer${i} already confirmed`);
    continue;
  }
  const sig = await wallet.signMessage(ethers.getBytes(messageHash));
  await waitOk((await new ethers.Contract(bridgeAddress, BRIDGE_ABI, wallet)
    .confirmBridge(requestId, lockTxHash, sig,
      { nonce: await nextNonce(signerAddresses[i - 1]) })).hash, `confirmBridge signer${i}`, signerAddresses[i - 1]);
}
const req = await ro.getBridgeRequest(requestId);
if (Number(req.status) !== 1) throw new Error(`request status ${req.status}, want CONFIRMED(1)`);
note(`read-back: request ${requestId} status CONFIRMED`);

// 7-9 — withdraw via owner emergency path, repatriate, re-pause (each resume-aware)
const held = await token.balanceOf(bridgeAddress);
if (held === 0n) {
  note("skip: bridge holds no tokens — nothing to withdraw");
} else {
  await safeExec(bridgeAddress, iface.encodeFunctionData("emergencyWithdraw", [tokenAddress, held]), `emergencyWithdraw ${held}`);
  if (await token.balanceOf(bridgeAddress) !== 0n) throw new Error("bridge still holds tokens");
}
const safeHeld = await token.balanceOf(safeAddress);
if (safeHeld === 0n) {
  note("skip: Safe holds no tokens — nothing to repatriate");
} else {
  await safeExec(tokenAddress, iface.encodeFunctionData("transfer", [signerAddresses[0], safeHeld]), "token.transfer -> signer1");
}
if (await ro.paused()) {
  note("skip: already paused");
} else {
  await safeExec(bridgeAddress, iface.encodeFunctionData("pause"), "pause");
}
const [pausedEnd, ownerEnd] = await Promise.all([ro.paused(), ro.owner()]);
if (!pausedEnd || ownerEnd.toLowerCase() !== safeAddress.toLowerCase()) {
  throw new Error(`final state wrong: paused=${pausedEnd} owner=${ownerEnd}`);
}
note(`final: paused=${pausedEnd} owner=${ownerEnd} signer1 token balance=${await token.balanceOf(signerAddresses[0])}`);

assertReportClean();
note("round trip complete — every step verified");
