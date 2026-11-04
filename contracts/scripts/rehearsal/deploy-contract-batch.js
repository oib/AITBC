#!/usr/bin/env node
/**
 * #1118-batch rehearsal deploy: the five landed contract fixes onto a local
 * hardhat/anvil chain. Idempotent — resumes from its own record file.
 *
 * Discipline (same as deploy-guards.js):
 * - DEPLOYER_KEY_FILE: 0600, one bare/0x 64-hex key, read to memory only.
 * - DEPLOY_RECORD (required when DEPLOYER_KEY_FILE is set): a scratch path,
 *   refused when it names or sits inside contracts/ next to deployments.json.
 * - RPC_URL: defaults to http://127.0.0.1:8545 (local hardhat/anvil only —
 *   any http URL not on loopback is refused, Sepolia needs the typed line).
 *
 * Order (deps first): ContractRegistry, AITBCGovernanceToken, AITBCVoting,
 * PerformanceAggregator, RewardDistributor, StakingPoolFactory,
 * PerformanceVerifier, ZKReceiptVerifier, AIPowerRental, DynamicPricing,
 * AgentBounty — then registry.registerContract + initialize() wiring.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPublicClient, createWalletClient, http, parseAbi } from "viem";
import { privateKeyToAccount } from "viem/accounts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CONTRACTS_DIR = path.resolve(HERE, "../..");
const KEY_RE = /^(0x)?[0-9a-fA-F]{64}$/;

function resolveRecord(env = process.env) {
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

function resolveRpc(env = process.env) {
  const url = env.RPC_URL || "http://127.0.0.1:8545";
  if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?/.test(url)) {
    throw new Error(`refusing non-loopback RPC_URL: ${url} — rehearsal is local-only; live targets need the operator's typed line`);
  }
  return url;
}

function readDeployerKey(file) {
  const st = fs.statSync(file);
  if ((st.mode & 0o777) !== 0o600) throw new Error("DEPLOYER_KEY_FILE must be mode 0600");
  const raw = fs.readFileSync(file, "utf8").trim();
  if (!KEY_RE.test(raw)) throw new Error("DEPLOYER_KEY_FILE must hold one 64-hex key");
  return raw.startsWith("0x") ? raw : `0x${raw}`;
}

function artifact(name) {
  const p = path.join(CONTRACTS_DIR, `artifacts/contracts/contracts/${name}.sol/${name}.json`);
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

// hardhat artifacts for contracts/, forge artifacts for governance/src.
async function deploy(wc, pc, record, name, sourceDir, args = []) {
  if (record.deployed[name]) return record.deployed[name];
  let abi, bytecode;
  if (sourceDir === "contracts") {
    const art = JSON.parse(fs.readFileSync(path.join(CONTRACTS_DIR, `artifacts/contracts/${name}.sol/${name}.json`), "utf8"));
    abi = art.abi;
    bytecode = art.bytecode;
  } else {
    const art = JSON.parse(fs.readFileSync(path.join(CONTRACTS_DIR, `governance/out/${name}.sol/${name}.json`), "utf8"));
    abi = art.abi;
    bytecode = art.bytecode.object ?? art.bytecode;
  }
  const hash = await wc.deployContract({ abi, bytecode, args });
  const receipt = await pc.waitForTransactionReceipt({ hash });
  if (receipt.status !== "success") throw new Error(`deploy ${name} failed: ${hash}`);
  record.deployed[name] = { address: receipt.contractAddress, tx: hash, bytecodeHash: null };
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
  console.log(`deployed ${name} -> ${receipt.contractAddress} (${hash})`);
  return record.deployed[name];
}

const recordPath = resolveRecord();
const rpcUrl = resolveRpc();
const account = privateKeyToAccount(readDeployerKey(process.env.DEPLOYER_KEY_FILE));
const pc = createPublicClient({ transport: http(rpcUrl) });
const wc = createWalletClient({ account, transport: http(rpcUrl) });

const record = fs.existsSync(recordPath)
  ? JSON.parse(fs.readFileSync(recordPath, "utf8"))
  : { network: await pc.getChainId(), deployer: account.address, deployed: {}, wired: false };

// --- deploy order (deps first) -------------------------------------------
await deploy(wc, pc, record, "ContractRegistry", "contracts");
await deploy(wc, pc, record, "AITBCGovernanceToken", "governance");
await deploy(wc, pc, record, "AITBCVoting", "governance", [record.deployed.AITBCGovernanceToken.address]);
await deploy(wc, pc, record, "PerformanceAggregator", "contracts");
await deploy(wc, pc, record, "RewardDistributor", "contracts");
const tokenAddr = record.deployed.AITBCGovernanceToken.address;
await deploy(wc, pc, record, "StakingPoolFactory", "contracts", [tokenAddr]);
await deploy(wc, pc, record, "ZKReceiptVerifier", "contracts");
await deploy(wc, pc, record, "Groth16Verifier", "contracts");
await deploy(wc, pc, record, "AIPowerRental", "contracts", [
  tokenAddr,
  record.deployed.ZKReceiptVerifier.address,
  record.deployed.Groth16Verifier.address,
]);
await deploy(wc, pc, record, "PerformanceVerifier", "contracts", [
  record.deployed.ZKReceiptVerifier.address,
  record.deployed.Groth16Verifier.address,
  record.deployed.AIPowerRental.address,
]);
await deploy(wc, pc, record, "DynamicPricing", "contracts", [
  record.deployed.AIPowerRental.address,
  record.deployed.PerformanceVerifier.address,
  tokenAddr,
]);
await deploy(wc, pc, record, "AgentBounty", "contracts", [tokenAddr, record.deployed.PerformanceVerifier.address]);
await deploy(wc, pc, record, "AgentStaking", "contracts", [tokenAddr, record.deployed.PerformanceVerifier.address]);

// --- wiring: registry ids + initialize() -----------------------------------
const REG_ABI = parseAbi([
  "function registerContract(bytes32 contractId, address contractAddress)",
  "function updateContract(bytes32 contractId, address newAddress)",
  "function getContract(bytes32 contractId) view returns (address)",
]);
const INIT_ABI = parseAbi(["function initialize(address _registry)"]);
const REGVIEW_ABI = parseAbi(["function registry() view returns (address)"]);
const id = (n) => `0x${Buffer.from(n).toString("hex").padEnd(64, "0")}`;
const keccak = async (s) => (await import("viem")).keccak256(`0x${Buffer.from(s).toString("hex")}`);

if (!record.wired) {
  const reg = record.deployed.ContractRegistry.address;
  // Every id any initialize() looks up must be registered first —
  // PerformanceAggregator resolves PerformanceVerifier, AgentBounty and
  // AgentStaking on top of the factory/distributor pair. Skip ids already
  // registered so a re-run after a partial wiring resumes.
  for (const n of ["StakingPoolFactory", "PerformanceAggregator", "RewardDistributor", "PerformanceVerifier", "AgentBounty", "AgentStaking"]) {
    const cid = await keccak(n);
    const have = await pc.readContract({ address: reg, abi: REG_ABI, functionName: "getContract", args: [cid] }).catch(() => null);
    if (have && have.toLowerCase() === record.deployed[n].address.toLowerCase()) continue;
    // id already pointing at a superseded deployment -> updateContract,
    // not register (which reverts ContractAlreadyRegistered).
    const fn = have && have !== "0x0000000000000000000000000000000000000000" ? "updateContract" : "registerContract";
    const h = await wc.writeContract({ address: reg, abi: REG_ABI, functionName: fn, args: [cid, record.deployed[n].address] });
    await pc.waitForTransactionReceipt({ hash: h });
  }
  for (const n of ["StakingPoolFactory", "RewardDistributor", "PerformanceAggregator"]) {
    const already = await pc.readContract({ address: record.deployed[n].address, abi: REGVIEW_ABI, functionName: "registry" }).catch(() => null);
    if (already && already !== "0x0000000000000000000000000000000000000000") continue;
    const h = await wc.writeContract({ address: record.deployed[n].address, abi: INIT_ABI, functionName: "initialize", args: [reg] });
    await pc.waitForTransactionReceipt({ hash: h });
  }
  record.wired = true;
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
  console.log("wired: registry ids + initialize()");
}
console.log(`done — record: ${recordPath}`);
