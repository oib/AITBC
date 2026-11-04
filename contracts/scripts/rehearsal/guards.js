/** Shared guards for rehearsal deploy/smoke scripts (#1134). */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const KEY_RE = /^(0x)?[0-9a-fA-F]{64}$/;
const CONTRACTS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

/** Local-only RPC: parse as a real URL — no regex lookalike tricks. */
export function resolveRpc(env = process.env) {
  const url = env.RPC_URL || "http://127.0.0.1:8545";
  let u;
  try { u = new URL(url); } catch { throw new Error(`invalid RPC_URL: ${url}`); }
  const loopback = u.hostname === "127.0.0.1" || u.hostname === "localhost" || u.hostname === "[::1]";
  if ((u.protocol !== "http:" && u.protocol !== "https:") || !loopback || u.username || u.password) {
    throw new Error(`refusing non-loopback RPC_URL: ${url} — rehearsal is local-only; live targets need the operator's typed line`);
  }
  return url;
}

export function resolveRecord(env = process.env) {
  const record = env.DEPLOY_RECORD;
  if (!record) throw new Error("DEPLOY_RECORD is required — a scratch path the script owns");
  const resolved = path.resolve(record);
  if (resolved.startsWith(CONTRACTS_DIR + path.sep)) {
    throw new Error(`refusing a record path inside contracts/: ${resolved}`);
  }
  if (path.basename(resolved) === "deployments.json") {
    throw new Error(`refusing a record path named like the real record: ${resolved}`);
  }
  return resolved;
}

export function readDeployerKey(file) {
  const st = fs.statSync(file);
  if ((st.mode & 0o777) !== 0o600) throw new Error("DEPLOYER_KEY_FILE must be mode 0600");
  const raw = fs.readFileSync(file, "utf8").trim();
  if (!KEY_RE.test(raw)) throw new Error("DEPLOYER_KEY_FILE must hold one 64-hex key");
  return raw.startsWith("0x") ? raw : `0x${raw}`;
}
