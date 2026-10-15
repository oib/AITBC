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
 *
 * `options.expectedNonce` — when set, the caller pins the exact Safe nonce the
 * signatures must cover. A bounded poll of kits[0].getNonce() must report that
 * value before anything is built (a lagging RPC replica once returned the
 * pre-exec nonce here — ETH-3 run, GS026); the pinned nonce then goes into the
 * safeTx via createTransaction options so the kit never re-reads it. Anything
 * but an exact match after the poll is a refusal, never a best-effort sign.
 */
export async function signAndExecute(kits, transactions, options = {}) {
  const { executor, expectedNonce, noncePollAttempts = 20, noncePollIntervalMs = 1500, ...execOptions } = options;
  if (expectedNonce !== undefined) {
    let seen = -1;
    for (let i = 0; i < noncePollAttempts && seen !== expectedNonce; i++) {
      seen = Number(await kits[0].getNonce());
      if (seen !== expectedNonce) await new Promise((r) => setTimeout(r, noncePollIntervalMs));
    }
    if (seen !== expectedNonce) {
      throw new Error(`safe nonce reads ${seen}, expected ${expectedNonce} — refusing to sign (stale replica or skipped exec)`);
    }
  }
  let safeTx = await kits[0].createTransaction({
    transactions,
    ...(expectedNonce === undefined ? {} : { options: { nonce: expectedNonce } }),
  });
  for (const kit of kits) {
    safeTx = await kit.signTransaction(safeTx);
  }
  return (executor ?? kits[0]).executeTransaction(safeTx, execOptions);
}

export const LOG_CHUNK = 40000;

/** Range-cap rejections: publicnode -32701 "exceed maximum block range",
 *  other nodes phrase it differently. */
export function isLogRangeError(err) {
  const code = err?.code ?? err?.error?.code;
  if (code === -32701 || code === -32005 || code === -32000 || code === -32602) {
    if (/range|limit|exceed/i.test(String(err?.error?.message ?? err?.message ?? err))) return true;
  }
  return /exceed.*block range|block range.*exceed|range.*too (large|wide|big)|log query.*(range|limit)/i
    .test(String(err?.error?.message ?? err?.message ?? err));
}

/** Pruned-history rejections (publicnode code 4444, "pruned history
 *  unavailable") — the node cannot serve that block's logs at all. */
export function isLogPruneError(err) {
  const code = err?.code ?? err?.error?.code;
  return code === 4444 || /pruned/i.test(String(err?.error?.message ?? err?.message ?? err));
}

/**
 * Public RPCs cap eth_getLogs ranges (publicnode: -32701 above 50,000
 * blocks) and prune old logs entirely (4444), so a from-0 queryFilter is
 * unusable on a long-lived chain. Walk backward from `toBlock` to
 * `fromBlock` in windows of at most `chunkSize` blocks; a window that hits a
 * range cap or straddles the prune boundary is split in half recursively
 * until it fits. A single-block window that is pruned is skipped with a
 * warning line — those logs are genuinely unavailable; any other failure
 * propagates. With `firstOnly`, stop at the first non-empty window — scans
 * run newest-first, so it holds the most recent matching logs, which is what
 * a resume wants. Returned logs are sorted in ascending chain order. `log`
 * receives one line per window attempted. `maxWindows` bounds total RPC
 * calls (512 default) — a scan that grinds past it fails loudly instead of
 * crawling a pruned chain for hours.
 */
export async function queryFilterChunked(contract, filter, { fromBlock, toBlock, chunkSize = LOG_CHUNK, firstOnly = false, maxWindows = 512, log } = {}) {
  const lo0 = Math.max(0, Number(fromBlock));
  let windows = 0;
  const rangeLogs = async (lo, hi) => {
    if (++windows > maxWindows) {
      throw new Error(`log scan exceeded ${maxWindows} windows — narrow --from-block or pass --lock-tx`);
    }
    log?.(`log-scan window ${lo}..${hi}`);
    try {
      return await contract.queryFilter(filter, lo, hi);
    } catch (err) {
      if (lo === hi) {
        if (isLogPruneError(err)) {
          log?.(`log-scan window ${lo}..${hi}: pruned on this node — skipped`);
          return [];
        }
        throw err;
      }
      if (!isLogRangeError(err) && !isLogPruneError(err)) throw err;
      const mid = lo + ((hi - lo) >> 1);
      const high = await rangeLogs(mid + 1, hi);
      if (firstOnly && high.length) return high;
      return (await rangeLogs(lo, mid)).concat(high);
    }
  };
  const found = [];
  for (let hi = Number(toBlock); hi >= lo0;) {
    const lo = Math.max(lo0, hi - chunkSize + 1);
    const logs = await rangeLogs(lo, hi);
    found.push(...logs);
    if (firstOnly && logs.length) break;
    hi = lo - 1;
  }
  found.sort((a, b) => Number(a.blockNumber - b.blockNumber) || a.index - b.index);
  return found;
}

/**
 * Binary-search the first block where `address` has code — a readable
 * deployment block for bounding log scans. Returns null when the node cannot
 * serve historical eth_getCode (caller falls back to a fixed window).
 */
export async function findDeploymentBlock(provider, address, latest) {
  const end = await provider.getCode(address, latest);
  if (!end || end === "0x") return null;
  let lo = 0, hi = Number(latest);
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    const code = await provider.getCode(address, mid).catch(() => null);
    if (code === null) return null;
    if (code === "0x") lo = mid + 1; else hi = mid;
  }
  return lo;
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
