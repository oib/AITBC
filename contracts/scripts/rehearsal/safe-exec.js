/**
 * BR-9 rehearsal step B4 — one 2-of-3 Safe transaction against the bridge,
 * signatures collected in-process (no Safe Transaction Service).
 *
 * Default owner call: setFeeRecipient(signer1.address) — readable back via
 * feeRecipient(). Override with REHEARSAL_OWNER_CALL / REHEARSAL_OWNER_CALL_ARG
 * for another owner-only function (single-address-arg functions only).
 *
 * Negative checks run BEFORE the real execution:
 *   - the same Safe tx with only one signature must not execute;
 *   - a direct EOA call to the owner-only function must revert.
 *
 * Usage:
 *   REHEARSAL_KEYS_DIR=/path/to/keys/rehearsal-sepolia \
 *   SEPOLIA_RPC_URL=https://... \
 *   SAFE_ADDRESS=0x... BRIDGE_ADDRESS=0x... \
 *     node scripts/rehearsal/safe-exec.js
 */

import { ethers } from "ethers";
import { getAddress } from "viem";
import {
  assertSepolia,
  assertSignerOwners,
  assertSingleSigCannotExecute,
  initKit,
  isOnlyOwnerRevert,
  normalizeAddresses,
  publicClient,
  readSignerAddresses,
  readSignerKey,
  resolveKeysDir,
  signAndExecute,
  THRESHOLD,
} from "./lib.js";

const OWNER_CALL = process.env.REHEARSAL_OWNER_CALL || "setFeeRecipient";
const BRIDGE_ABI = [
  `function ${OWNER_CALL}(address) external`,
  "function feeRecipient() view returns (address)",
  "function paused() view returns (bool)",
  "function owner() view returns (address)",
];

const rpcUrl = process.env.SEPOLIA_RPC_URL;
const safeAddress = process.env.SAFE_ADDRESS;
const bridgeAddress = process.env.BRIDGE_ADDRESS;
for (const [name, v] of [["SEPOLIA_RPC_URL", rpcUrl], ["SAFE_ADDRESS", safeAddress], ["BRIDGE_ADDRESS", bridgeAddress]]) {
  if (!v) throw new Error(`${name} is required`);
}

const keysDir = resolveKeysDir();
const client = publicClient(rpcUrl);
assertSepolia(await client.getChainId());

const signerAddresses = normalizeAddresses(readSignerAddresses(keysDir));
const callArg = process.env.REHEARSAL_OWNER_CALL_ARG || signerAddresses[0]; // default: signer1
const iface = new ethers.Interface(BRIDGE_ABI);
const calldata = iface.encodeFunctionData(OWNER_CALL, [getAddress(callArg)]);
const transactions = [{ to: getAddress(bridgeAddress), value: "0", data: calldata }];

// signer2 + signer3 sign — signer1 only submits execTransaction (pays gas);
// its key adds no signature, so the 2-of-3 approval is still signer2+signer3.
const key1 = readSignerKey(keysDir, 1);
const key2 = readSignerKey(keysDir, 2);
const key3 = readSignerKey(keysDir, 3);
const kit1 = await initKit({ provider: rpcUrl, signerKey: key1, safeAddress });
const kit2 = await initKit({ provider: rpcUrl, signerKey: key2, safeAddress });
const kit3 = await initKit({ provider: rpcUrl, signerKey: key3, safeAddress });
assertSignerOwners(await kit2.getOwners(), signerAddresses);

// --- negative check 1: a single signature must not execute ---
const err = await assertSingleSigCannotExecute(kit2, transactions, rpcUrl);
console.error(`single-sig check: refused as expected (${String(err.message).slice(0, 80)})`);

// --- negative check 2: a direct EOA call to the owner-only fn must revert ---
// Only the bridge's actual onlyOwner revert counts — OpenZeppelin 4.x
// "Ownable: caller is not the owner", whether it arrives as a CALL_EXCEPTION
// (JsonRpcProvider) or a hardhat SolidityError carrying Error(string) data.
// Any other outcome — a successful call, a different error — rethrows/fails.
const eoa = new ethers.Wallet(key2, new ethers.JsonRpcProvider(rpcUrl));
const bridge = new ethers.Contract(bridgeAddress, BRIDGE_ABI, eoa);
let reverted = false;
try {
  await bridge.getFunction(OWNER_CALL).staticCall(getAddress(callArg));
} catch (e) {
  reverted = isOnlyOwnerRevert(e);
  if (!reverted) throw e;
}
if (!reverted) throw new Error(`direct EOA call to ${OWNER_CALL} did NOT revert — bridge owner check broken?`);
console.error(`direct-EOA check: reverted with onlyOwner reason as expected`);

// --- real execution: signatures from signer2 and signer3, gas paid by signer1 ---
const pausedBefore = await new ethers.Contract(bridgeAddress, BRIDGE_ABI, new ethers.JsonRpcProvider(rpcUrl)).paused();
const result = await signAndExecute([kit2, kit3], transactions, { executor: kit1 });
const hash = result.hash ?? result.transactionResponse?.hash;

// Wait for the receipt and assert the tx itself succeeded before trusting
// any read-back.
const receipt = await client.waitForTransactionReceipt({ hash });
if (receipt.status !== "success") {
  throw new Error(`Safe execution tx reverted on-chain: ${hash}`);
}
console.error(`execution tx: ${hash} block ${receipt.blockNumber} gas ${receipt.gasUsed}`);

// Read back and assert every expected effect. A Safe whose inner call failed
// (ExecutionFailure) still lands a "success" receipt — the feeRecipient
// assert below is what catches it, so nothing here may be softened.
const ro = new ethers.Contract(bridgeAddress, BRIDGE_ABI, new ethers.JsonRpcProvider(rpcUrl));
const [feeRecipient, paused, owner] = await Promise.all([ro.feeRecipient(), ro.paused(), ro.owner()]);
const want = getAddress(callArg).toLowerCase();
const mismatches = [];
if (feeRecipient.toLowerCase() !== want) mismatches.push(`feeRecipient=${feeRecipient}, want ${want}`);
if (paused !== pausedBefore) mismatches.push(`paused=${paused}, unchanged expected (${pausedBefore})`);
if (owner.toLowerCase() !== safeAddress.toLowerCase()) mismatches.push(`owner=${owner}, want ${safeAddress}`);
if (mismatches.length) {
  throw new Error(`post-execution read-back failed: ${mismatches.join("; ")}`);
}
console.error(`read-back: feeRecipient=${feeRecipient} paused=${paused} owner=${owner} — all asserted`);

console.log(JSON.stringify({
  txHash: hash,
  blockNumber: receipt.blockNumber.toString(),
  gasUsed: receipt.gasUsed.toString(),
  feeRecipient,
  paused,
  owner,
}));
