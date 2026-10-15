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
  initKit,
  normalizeAddresses,
  publicClient,
  readSignerAddresses,
  readSignerKey,
  resolveKeysDir,
  signAndExecute,
} from "./lib.js";

const LIVE = process.argv.includes("--live");
const tokenIdx = process.argv.indexOf("--token");
const REUSE_TOKEN = tokenIdx > -1 ? getAddress(process.argv[tokenIdx + 1]) : null;

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
async function safeExec(to, data, label) {
  const nonce = await safeContract.nonce();
  note(`safe-exec ${label}: nonce=${nonce} to=${to} data=${data}`);
  const res = await signAndExecute([kit2, kit3], [{ to, value: "0", data }], { executor: kit1 });
  const hash = res.hash ?? res.transactionResponse?.hash;
  await waitOk(hash, `safe-exec ${label}`, signerAddresses[0]); // kit1 (signer1) submits
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

// 2 — unpause
await safeExec(bridgeAddress, iface.encodeFunctionData("unpause"), "unpause");
if (await ro.paused()) throw new Error("bridge still paused after unpause exec");
note("read-back: paused=false");

// 3 — token config under the cap
await safeExec(bridgeAddress, iface.encodeFunctionData("addSupportedToken", [tokenAddress, CAP, 0n, false]), "addSupportedToken cap=1000 MTK");
const tcfg = await ro.supportedTokens(tokenAddress);
if (!tcfg.isActive || tcfg.bridgeLimit !== CAP) throw new Error(`token config wrong: ${tcfg}`);
note(`read-back: token active, bridgeLimit=${tcfg.bridgeLimit}`);

// 4 — three validators (the rehearsal signers)
for (let i = 0; i < 3; i++) {
  await safeExec(bridgeAddress, iface.encodeFunctionData("addValidator", [signerAddresses[i], VALIDATOR_WEIGHT]), `addValidator signer${i + 1}`);
}
note(`read-back: activeValidators[0..2] = ${await ro.activeValidators(0)}, ${await ro.activeValidators(1)}, ${await ro.activeValidators(2)}`);

// 5 — deposit under the cap
const tw = new ethers.Contract(tokenAddress, ERC20_ABI, w1);
await waitOk((await tw.approve(bridgeAddress, DEPOSIT,
  { nonce: await nextNonce(signerAddresses[0]) })).hash, "approve", signerAddresses[0]);
const bw = new ethers.Contract(bridgeAddress, BRIDGE_ABI, w1);
const initTx = await bw.initiateBridge(tokenAddress, tokenAddress, DEPOSIT, TARGET_CHAIN_ID, signerAddresses[0],
  { nonce: await nextNonce(signerAddresses[0]) });
const initReceipt = await waitOk(initTx.hash, "initiateBridge deposit", signerAddresses[0]);
const requestId = Number(await ro.requestCounter());
const lockTxHash = initReceipt.transactionHash;
note(`requestId=${requestId} lockTxHash=${lockTxHash}`);

// 6 — validator confirmations, each sent by its own EOA
const messageHash = ethers.keccak256(ethers.solidityPacked(
  ["uint256", "bytes32", "uint256"], [requestId, lockTxHash, 11155111]));
for (const [i, wallet] of [[1, w1], [2, w2], [3, w3]]) {
  const sig = await wallet.signMessage(ethers.getBytes(messageHash));
  await waitOk((await new ethers.Contract(bridgeAddress, BRIDGE_ABI, wallet)
    .confirmBridge(requestId, lockTxHash, sig,
      { nonce: await nextNonce(signerAddresses[i - 1]) })).hash, `confirmBridge signer${i}`, signerAddresses[i - 1]);
}
const req = await ro.getBridgeRequest(requestId);
if (Number(req.status) !== 1) throw new Error(`request status ${req.status}, want CONFIRMED(1)`);
note(`read-back: request ${requestId} status CONFIRMED`);

// 7-9 — withdraw via owner emergency path, repatriate, re-pause
const held = await token.balanceOf(bridgeAddress);
await safeExec(bridgeAddress, iface.encodeFunctionData("emergencyWithdraw", [tokenAddress, held]), `emergencyWithdraw ${held}`);
if (await token.balanceOf(bridgeAddress) !== 0n) throw new Error("bridge still holds tokens");
await safeExec(tokenAddress, iface.encodeFunctionData("transfer", [signerAddresses[0], held]), "token.transfer -> signer1");
await safeExec(bridgeAddress, iface.encodeFunctionData("pause"), "pause");
const [pausedEnd, ownerEnd] = await Promise.all([ro.paused(), ro.owner()]);
if (!pausedEnd || ownerEnd.toLowerCase() !== safeAddress.toLowerCase()) {
  throw new Error(`final state wrong: paused=${pausedEnd} owner=${ownerEnd}`);
}
note(`final: paused=${pausedEnd} owner=${ownerEnd} signer1 token balance=${await token.balanceOf(signerAddresses[0])}`);

assertReportClean();
note("round trip complete — every step verified");
