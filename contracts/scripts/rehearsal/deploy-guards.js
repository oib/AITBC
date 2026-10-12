/**
 * Guards for deploy-bridge.js's DEPLOYER_KEY_FILE path — pure functions so
 * the hardhat suite can exercise every refusal without a network.
 *
 * The DEPLOYER_KEY_FILE path is the rehearsal/throwaway-key path: when it is
 * used, the script must be explicit about the chain (BRIDGE_REQUIRE_CHAIN_ID)
 * and about where the deployment record goes (BRIDGE_DEPLOY_RECORD, never the
 * real contracts/deployments-bridge-*.json files or anywhere inside
 * contracts/). When DEPLOYER_KEY_FILE is unset the historical behaviour is
 * byte-identical.
 */
import fs from "node:fs";
import path from "node:path";
import { assertKeyFileMode } from "./lib.js";

const KEY_RE = /^(0x)?[0-9a-fA-F]{64}$/;
const REAL_RECORD_RE = /^deployments-bridge-.*\.json$/;

/** With DEPLOYER_KEY_FILE set, the chain must be pinned — checked before any
 *  key file is touched. */
export function requireChainIdForKeyFile(env) {
  if (env.DEPLOYER_KEY_FILE && !env.BRIDGE_REQUIRE_CHAIN_ID) {
    throw new Error(
      "BRIDGE_REQUIRE_CHAIN_ID is required when DEPLOYER_KEY_FILE is set — a key file must never guess the chain"
    );
  }
}

/**
 * Resolve the deployment-record path. With DEPLOYER_KEY_FILE set the record
 * must be explicit and must not collide with the real records: no basename
 * matching deployments-bridge-*.json and nothing inside contractsDir. Without
 * DEPLOYER_KEY_FILE the previous behaviour is preserved (env override or the
 * network-named default).
 */
export function resolveDeployRecord(env, contractsDir, networkName) {
  const record = env.BRIDGE_DEPLOY_RECORD;
  if (!env.DEPLOYER_KEY_FILE) {
    // Unchanged historical behaviour: raw env value or the
    // "<contractsDir>/deployments-bridge-<network>.json" template verbatim.
    return record || `${contractsDir}/deployments-bridge-${networkName}.json`;
  }
  if (!record) {
    throw new Error(
      "BRIDGE_DEPLOY_RECORD is required when DEPLOYER_KEY_FILE is set — a rehearsal must never touch the real deployments records"
    );
  }
  const resolved = path.resolve(record);
  if (REAL_RECORD_RE.test(path.basename(resolved))) {
    throw new Error(`refusing a record path named like a real deployments file: ${resolved}`);
  }
  if (path.dirname(resolved) === path.resolve(contractsDir)) {
    throw new Error(`refusing a record path inside contracts/ next to the real records: ${resolved}`);
  }
  return resolved;
}

/**
 * Read DEPLOYER_KEY_FILE into memory: mode 0600 required, content must be a
 * bare or 0x-prefixed 64-hex key. Validation happens BEFORE ethers.Wallet so
 * a malformed file cannot echo its content through an ethers error. Error
 * messages never carry file content.
 */
export function readDeployerKeyFile(keyFile) {
  assertKeyFileMode(keyFile);
  const raw = fs.readFileSync(keyFile, "utf8").trim();
  if (!KEY_RE.test(raw)) {
    throw new Error("DEPLOYER_KEY_FILE does not contain a single 64-hex secp256k1 key");
  }
  return raw.startsWith("0x") ? raw : `0x${raw}`;
}
