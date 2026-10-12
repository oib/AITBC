/**
 * BR-9 rehearsal step B1 — create the throwaway 2-of-3 Safe on Sepolia.
 *
 * Usage:
 *   REHEARSAL_KEYS_DIR=/path/to/keys/rehearsal-sepolia \
 *   SEPOLIA_RPC_URL=https://... \
 *     node scripts/rehearsal/safe-create.js
 *
 * Prints the deployed Safe address only (stdout). Progress goes to stderr.
 * Reads signer1.key into memory to pay for deployment; never prints it.
 */

import {
  assertSepolia,
  assertSignerOwners,
  deploySafe,
  initKit,
  normalizeAddresses,
  publicClient,
  readSignerAddresses,
  readSignerKey,
  resolveKeysDir,
  THRESHOLD,
} from "./lib.js";

const rpcUrl = process.env.SEPOLIA_RPC_URL;
if (!rpcUrl) throw new Error("SEPOLIA_RPC_URL is required");

const keysDir = resolveKeysDir();
const client = publicClient(rpcUrl);
assertSepolia(await client.getChainId());

const signerAddresses = normalizeAddresses(readSignerAddresses(keysDir));
const owners = [...signerAddresses];
assertSignerOwners(owners, signerAddresses); // owners == exactly the three .address files

const deployerKey = readSignerKey(keysDir, 1); // signer1 funds the rehearsal
const balance = await client.getBalance({ address: owners[0] });
console.error(`deployer (signer1): ${owners[0]} — balance ${balance} wei`);
if (balance === 0n) {
  throw new Error("signer1 has no Sepolia ETH — fund it before running (see runbook)");
}

const { safeAddress, txHash } = await deploySafe({
  provider: rpcUrl,
  deployerKey,
  owners,
  threshold: THRESHOLD,
});
console.error(`deployment tx: ${txHash}`);

// Read back: the on-chain owner set and threshold must match the files.
const check = await initKit({ provider: rpcUrl, signerKey: deployerKey, safeAddress });
assertSignerOwners(await check.getOwners(), signerAddresses);
const onchainThreshold = await check.getThreshold();
if (onchainThreshold !== THRESHOLD) {
  throw new Error(`on-chain threshold is ${onchainThreshold}, expected ${THRESHOLD}`);
}
console.error(`read-back: owners match signer files, threshold ${onchainThreshold}`);

// stdout: the Safe address only.
console.log(safeAddress);
