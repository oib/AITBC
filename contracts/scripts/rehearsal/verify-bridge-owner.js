/**
 * BR-9 rehearsal — read-only bridge owner check. Sends no transaction.
 *
 * Usage:
 *   SEPOLIA_RPC_URL=https://... BRIDGE_ADDRESS=0x... BRIDGE_OWNER_SAFE=0x... \
 *     node scripts/rehearsal/verify-bridge-owner.js
 *
 * Prints owner/paused/feeRecipient/requestCounter and OK or FAIL.
 */

import { ethers } from "ethers";
import { assertSepolia } from "./lib.js";

const ABI = [
  "function owner() view returns (address)",
  "function paused() view returns (bool)",
  "function feeRecipient() view returns (address)",
  "function requestCounter() view returns (uint256)",
];

const rpcUrl = process.env.SEPOLIA_RPC_URL;
const bridgeAddress = process.env.BRIDGE_ADDRESS;
const expected = process.env.BRIDGE_OWNER_SAFE;
for (const [name, v] of [["SEPOLIA_RPC_URL", rpcUrl], ["BRIDGE_ADDRESS", bridgeAddress], ["BRIDGE_OWNER_SAFE", expected]]) {
  if (!v) throw new Error(`${name} is required`);
}

const provider = new ethers.JsonRpcProvider(rpcUrl);
assertSepolia((await provider.getNetwork()).chainId);

const bridge = new ethers.Contract(bridgeAddress, ABI, provider);
const [owner, paused, feeRecipient, requestCounter] = await Promise.all([
  bridge.owner(),
  bridge.paused(),
  bridge.feeRecipient(),
  bridge.requestCounter(),
]);

const ok = owner.toLowerCase() === expected.toLowerCase();
console.log(JSON.stringify({ owner, expected, paused, feeRecipient, requestCounter: requestCounter.toString(), verdict: ok ? "OK" : "FAIL" }));
process.exit(ok ? 0 : 1);
