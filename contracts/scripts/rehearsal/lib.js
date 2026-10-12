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
import { createPublicClient, custom, decodeErrorResult, getAddress, http } from "viem";

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
  // A symlink named rehearsal-sepolia must not smuggle in a different
  // directory: compare the resolved target's basename too. realpathSync
  // throws on a nonexistent path — a refusal either way.
  const realBase = path.basename(fs.realpathSync(resolved));
  if (realBase !== "rehearsal-sepolia") {
    throw new Error(`REHEARSAL_KEYS_DIR resolves to "${realBase}", not a rehearsal-sepolia directory`);
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

/** Read signerN.key into memory. Returns 0x-prefixed hex; never logged.
 *  Refuses a file with any group/other mode bit and any non-64-hex content;
 *  error messages never echo file content. */
export function readSignerKey(keysDir, n) {
  const file = path.join(keysDir, `signer${n}.key`);
  assertKeyFileMode(file);
  const raw = fs.readFileSync(file, "utf8").trim().toLowerCase().replace(/^0x/, "");
  if (!/^[0-9a-f]{64}$/.test(raw)) {
    throw new Error(`${file} does not look like a raw secp256k1 key`);
  }
  return `0x${raw}`;
}

/** A key file must be mode 0600 — any group or other bit refuses the read. */
export function assertKeyFileMode(file) {
  if (fs.statSync(file).mode & 0o077) {
    throw new Error(`${file} has group/other permission bits set — key files must be mode 0600`);
  }
}

/**
 * Normalize a list of addresses to EIP-55 checksums. MUST use an explicit
 * callback — passing getAddress directly to Array.map hands the array index
 * to getAddress's second (EIP-1191 chainId) parameter and produces wrong
 * checksums (observed live in BR-9 phase B). Centralized here so the
 * footgun has exactly one place to return.
 */
export function normalizeAddresses(addresses) {
  return addresses.map((a) => getAddress(a));
}

/**
 * The bridge's onlyOwner revert, and ONLY that revert. OpenZeppelin 4.x
 * Ownable uses Error(string) "Ownable: caller is not the owner" (selector
 * 0x08c379a0). Observed shapes:
 *  - ethers v6 via JsonRpcProvider (Sepolia): Error, code "CALL_EXCEPTION",
 *    .reason = the string;
 *  - hardhat in-process: SolidityError, code 3 (eth revert), .data = the
 *    ABI-encoded Error(string).
 * Anything else must rethrow — an unrelated failure is not a proof.
 */
export const ONLY_OWNER_REASON = "Ownable: caller is not the owner";
const ERROR_STRING_ABI = [{ type: "error", name: "Error", inputs: [{ name: "reason", type: "string" }] }];

export function isOnlyOwnerRevert(err) {
  if (err?.code === "CALL_EXCEPTION" && err.reason === ONLY_OWNER_REASON) return true;
  const data = typeof err?.data === "string" ? err.data : "";
  if (err?.code === 3 && data.startsWith("0x08c379a0")) {
    try {
      return decodeErrorResult({ abi: ERROR_STRING_ABI, data }).args?.[0] === ONLY_OWNER_REASON;
    } catch {
      return false;
    }
  }
  return false;
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
 * in-process signature — no Transaction Service), and execute it. `options.executor`
 * is a kit that only submits the tx (pays the gas); it does not sign. Defaults
 * to kits[0]. Any EOA may submit execTransaction — that is how relayers work.
 */
export async function signAndExecute(kits, transactions, options = {}) {
  const { executor, ...execOptions } = options;
  let safeTx = await kits[0].createTransaction({ transactions });
  for (const kit of kits) {
    safeTx = await kit.signTransaction(safeTx);
  }
  return (executor ?? kits[0]).executeTransaction(safeTx, execOptions);
}

/**
 * A Safe transaction signed below threshold must not execute. Only errors
 * that specifically mean "not enough signatures" count as a pass — anything
 * else (RPC down, nonce, funds, a different revert) is rethrown so the
 * check can never pass on an unrelated failure.
 *
 * Accepted patterns, observed on hardhat + Sepolia (protocol-kit 8.0.7):
 *  - client-side refusal: "There is 1 signature missing"
 *  - on-chain GS0xx signature validation if it ever reaches the contract:
 *    GS020 "signatures data too short", GS026 signature decoding.
 * If the call does broadcast, a mined receipt is checked: success = the
 * threshold was bypassed (hard fail); any revert is accepted.
 */
const MISSING_SIGNATURE_ERRORS = [
  /signature(s)? missing/i,
  /signatures? data too short/i,
  /GS0(20|26)/,
];

export async function assertSingleSigCannotExecute(kit, transactions, rpcUrl) {
  const safeTx = await kit.signTransaction(await kit.createTransaction({ transactions }));
  try {
    const res = await kit.executeTransaction(safeTx);
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
    const text = `${err.shortMessage ?? ""} ${err.message ?? err}`;
    if (MISSING_SIGNATURE_ERRORS.some((re) => re.test(text))) {
      return err; // the specific refusal we assert
    }
    throw err; // unrelated failure — the check did not prove anything
  }
}
