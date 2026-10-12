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

// NB: never pass getAddress directly to Array.map — the map index argument
// reaches viem as an EIP-1191 chain id and produces wrong checksums.
const signerAddresses = readSignerAddresses(keysDir).map((a) => getAddress(a));
const callArg = process.env.REHEARSAL_OWNER_CALL_ARG || signerAddresses[0]; // default: signer1
const iface = new ethers.Interface(BRIDGE_ABI);
const calldata = iface.encodeFunctionData(OWNER_CALL, [getAddress(callArg)]);
const transactions = [{ to: getAddress(bridgeAddress), value: "0", data: calldata }];

// signer2 + signer3 — the deployer's key is not needed for the 2-of-3.
const key2 = readSignerKey(keysDir, 2);
const key3 = readSignerKey(keysDir, 3);
const kit2 = await initKit({ provider: rpcUrl, signerKey: key2, safeAddress });
const kit3 = await initKit({ provider: rpcUrl, signerKey: key3, safeAddress });
assertSignerOwners(await kit2.getOwners(), signerAddresses);

// --- negative check 1: a single signature must not execute ---
const err = await assertSingleSigCannotExecute(kit2, transactions, rpcUrl);
console.error(`single-sig check: refused as expected (${String(err.message).slice(0, 80)})`);

// --- negative check 2: a direct EOA call to the owner-only fn must revert ---
const eoa = new ethers.Wallet(key2, new ethers.JsonRpcProvider(rpcUrl));
const bridge = new ethers.Contract(bridgeAddress, BRIDGE_ABI, eoa);
let reverted = false;
try {
  await bridge.getFunction(OWNER_CALL).staticCall(getAddress(callArg));
} catch {
  reverted = true;
}
if (!reverted) throw new Error(`direct EOA call to ${OWNER_CALL} did NOT revert — bridge owner check broken?`);
console.error(`direct-EOA check: reverted as expected`);

// --- real execution: signatures from signer2 and signer3 ---
const result = await signAndExecute([kit2, kit3], transactions);
const hash = result.hash ?? result.transactionResponse?.hash;
console.error(`execution tx: ${hash}`);

// Read back the effect.
const ro = new ethers.Contract(bridgeAddress, BRIDGE_ABI, new ethers.JsonRpcProvider(rpcUrl));
const [feeRecipient, paused, owner] = await Promise.all([ro.feeRecipient(), ro.paused(), ro.owner()]);
console.error(`read-back: feeRecipient=${feeRecipient} paused=${paused} owner=${owner}`);
if (owner.toLowerCase() !== safeAddress.toLowerCase()) {
  throw new Error("bridge owner is not the Safe after execution");
}

console.log(JSON.stringify({ txHash: hash, feeRecipient, paused, owner }));
