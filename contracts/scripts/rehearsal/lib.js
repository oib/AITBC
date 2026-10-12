/**
 * Shared helpers for the Sepolia bridge-deploy rehearsal (BR-9).
 *
 * Key discipline: signer keys are read from <REHEARSAL_KEYS_DIR>/signerN.key
 * into memory only. They are never printed, logged, exported to the
 * environment, placed in argv, or written anywhere else. Every guard that can
 * be checked before a key is loaded is checked first.
 */

import fs from "node:fs";
import path from "node:path";
import Safe from "@safe-global/protocol-kit";
import { createPublicClient, custom, http } from "viem";

export const SEPOLIA_CHAIN_ID = 11155111;
export const SIGNER_COUNT = 3;
export const THRESHOLD = 2;

/** Reject any chainId other than Sepolia. Checked before anything else. */
export function assertSepolia(chainId) {
  if (Number(chainId) !== SEPOLIA_CHAIN_ID) {
    throw new Error(`refusing to run on chainId ${chainId} — rehearsal is Sepolia-only (${SEPOLIA_CHAIN_ID})`);
  }
}

/**
 * REHEARSAL_KEYS_DIR must be set and must resolve to a directory whose path
 * ends in `rehearsal-sepolia` — a path guard so a stray env var cannot point
 * the scripts at real custody keys.
 */
export function resolveKeysDir(env = process.env) {
  const dir = env.REHEARSAL_KEYS_DIR;
  if (!dir) {
    throw new Error("REHEARSAL_KEYS_DIR is required (path to keys/rehearsal-sepolia)");
  }
  const resolved = path.resolve(dir);
  if (path.basename(resolved) !== "rehearsal-sepolia") {
    throw new Error(`REHEARSAL_KEYS_DIR must end in "rehearsal-sepolia" (got: ${resolved})`);
  }
  return resolved;
}

/** Read signer1..3 .address files; returns checksummed addresses in order. */
export function readSignerAddresses(keysDir) {
  const out = [];
  for (let i = 1; i <= SIGNER_COUNT; i++) {
    const file = path.join(keysDir, `signer${i}.address`);
    const addr = fs.readFileSync(file, "utf8").trim();
    if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) {
      throw new Error(`${file} does not contain a valid address`);
    }
    out.push(addr);
  }
  return out;
}

/** Read signerN.key into memory. Returns 0x-prefixed hex; never logged. */
export function readSignerKey(keysDir, n) {
  const file = path.join(keysDir, `signer${n}.key`);
  const raw = fs.readFileSync(file, "utf8").trim().toLowerCase().replace(/^0x/, "");
  if (!/^[0-9a-f]{64}$/.test(raw)) {
    throw new Error(`${file} does not look like a raw secp256k1 key`);
  }
  return `0x${raw}`;
}

/** The Safe's owner list must be exactly the three rehearsal signers. */
export function assertSignerOwners(owners, signerAddresses) {
  const want = signerAddresses.map((a) => a.toLowerCase()).sort();
  const got = owners.map((a) => a.toLowerCase()).sort();
  if (got.length !== SIGNER_COUNT || want.some((a, i) => got[i] !== a)) {
    throw new Error("owner list is not exactly the three rehearsal signers — refusing");
  }
}

/** Public client for chain reads (chainId, balances, receipts). Accepts an
 *  RPC URL or any EIP-1193 provider (the local test uses hardhat's). */
export function publicClient(rpcUrlOrProvider) {
  const transport = typeof rpcUrlOrProvider === "string" ? http(rpcUrlOrProvider) : custom(rpcUrlOrProvider);
  return createPublicClient({ transport });
}

/**
 * Init a Safe instance for one signer. `config.predicted` = pre-deploy config;
 * `config.safeAddress` = existing Safe; `contractNetworks` overrides bundled
 * addresses (used only by the local hardhat test).
 */
export async function initKit({ provider, signerKey, owners, threshold, safeAddress, contractNetworks, saltNonce }) {
  const base = { provider, signer: signerKey, contractNetworks };
  if (safeAddress) {
    return Safe.init({ ...base, safeAddress });
  }
  return Safe.init({
    ...base,
    predictedSafe: {
      safeAccountConfig: { owners, threshold },
      safeDeploymentConfig: saltNonce ? { saltNonce } : {},
    },
  });
}

/**
 * Deploy the predicted Safe from the deployer's EOA. Returns the Safe address
 * after the deployment receipt confirms contract code on-chain.
 */
export async function deploySafe({ provider, deployerKey, owners, threshold, contractNetworks, saltNonce }) {
  const kit = await initKit({ provider, signerKey: deployerKey, owners, threshold, contractNetworks, saltNonce });
  const deployment = await kit.createSafeDeploymentTransaction();
  const externalSigner = await kit.getSafeProvider().getExternalSigner();
  const hash = await externalSigner.sendTransaction({
    to: deployment.to,
    value: BigInt(deployment.value),
    data: deployment.data,
  });
  const client = publicClient(provider);
  const receipt = await client.waitForTransactionReceipt({ hash });
  const safeAddress = await kit.getAddress();
  const code = await client.getCode({ address: safeAddress });
  if (!code || code === "0x") {
    throw new Error(`Safe deployment tx mined but no code at ${safeAddress}`);
  }
  return { safeAddress, kit, txHash: receipt.transactionHash, gasUsed: receipt.gasUsed };
}

/**
 * Build a Safe transaction, sign it with each kit in `kits` (each adds its own
 * in-process signature — no Transaction Service), and execute it. Returns the
 * execution result.
 */
export async function signAndExecute(kits, transactions, options = {}) {
  let safeTx = await kits[0].createTransaction({ transactions });
  for (const kit of kits) {
    safeTx = await kit.signTransaction(safeTx);
  }
  return kits[0].executeTransaction(safeTx, options);
}

/**
 * Negative check: a Safe transaction signed by fewer than `threshold` signers
 * must not execute. Returns the error it produced; throws if it succeeded.
 */
export async function assertSingleSigCannotExecute(kit, transactions, rpcUrl) {
  const safeTx = await kit.signTransaction(await kit.createTransaction({ transactions }));
  try {
    const res = await kit.executeTransaction(safeTx);
    // Some providers resolve the call but the tx itself reverts on-chain.
    const hash = res.hash ?? res.transactionResponse?.hash;
    if (hash) {
      const client = publicClient(rpcUrl);
      const receipt = await client.waitForTransactionReceipt({ hash }).catch(() => null);
      if (receipt && receipt.status === "success") {
        throw new Error("single-signature Safe transaction EXECUTED — threshold not enforced");
      }
      return new Error(`single-signature tx reverted on-chain (${hash})`);
    }
    throw new Error("single-signature Safe transaction EXECUTED — threshold not enforced");
  } catch (err) {
    if (String(err.message).includes("threshold not enforced")) throw err;
    return err; // expected: the call failed before or at mining
  }
}
