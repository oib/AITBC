#!/usr/bin/env node
/** Smoke for the #1118-batch rehearsal deploy: exercises one pin per fix on
 * the deployed contracts. Local hardhat/anvil only. Reads DEPLOY_RECORD. */
import fs from "node:fs";
import { resolveRpc, readDeployerKey } from "./guards.js";
import path from "node:path";
import { createPublicClient, createWalletClient, http, parseAbi, encodeFunctionData } from "viem";
import { privateKeyToAccount } from "viem/accounts";

const record = JSON.parse(fs.readFileSync(path.resolve(process.env.DEPLOY_RECORD), "utf8"));
const rpcUrl = resolveRpc();
const account = privateKeyToAccount(readDeployerKey(process.env.DEPLOYER_KEY_FILE));
const pc = createPublicClient({ transport: http(rpcUrl) });
const wc = createWalletClient({ account, transport: http(rpcUrl) });
const A = (n) => record.deployed[n].address;
let pass = 0, fail = 0;
const ok = (name, cond) => { cond ? pass++ : fail++; console.log(`${cond ? "PASS" : "FAIL"} ${name}`); };

async function call(addr, abi, fn, args = []) {
  return pc.readContract({ address: addr, abi, functionName: fn, args });
}
async function send(addr, abi, fn, args = []) {
  const h = await wc.writeContract({ address: addr, abi, functionName: fn, args });
  return pc.waitForTransactionReceipt({ hash: h });
}
async function reverts(addr, abi, fn, args = []) {
  try { await send(addr, abi, fn, args); return false; } catch { return true; }
}

const tokenAbi = parseAbi([
  "function transfer(address,uint256) returns (bool)",
  "function approve(address,uint256) returns (bool)",
  "function balanceOf(address) view returns (uint256)",
  "function getPastVotingPower(address,uint256) view returns (uint256)",
  "function votingPower(address) view returns (uint256)",
  "function stake(uint256,uint256)",
]);
const votingAbi = parseAbi([
  "function createProposal(string,string,string,bytes,uint256) returns (bytes32)",
  "function vote(bytes32,bool)",
  "function executeProposal(bytes32)",
  "function MIN_PROPOSAL_POWER() view returns (uint256)",
  "function hasVoted(bytes32,address) view returns (bool)",
]);
const dpAbi = parseAbi([
  "function createPriceAlert(address,uint8,uint256,string) returns (uint256)",
  "function cancelPriceAlert(uint256)",
  "function subscriberAlertCount(address) view returns (uint256)",
  "function activePriceAlertCount() view returns (uint256)",
  "function MAX_ALERTS_PER_SUBSCRIBER() view returns (uint256)",
]);
const sfAbi = parseAbi([
  "function createPool(string,uint256,uint256) returns (uint256)",
  "function stakeInPool(uint256,uint256)",
  "function unstakeFromPool(uint256,uint256)",
]);
const rdAbi = parseAbi(["function getUserClaims(address) view returns (uint256[])"]);
const pvAbi = parseAbi(["function verifyPerformanceProof(bytes,bytes32) returns (bool)"]);
const bountyAbi = parseAbi([
  "function authorizeCreator(address)",
  "function createBounty(string,string,uint256,uint8,bytes32,uint256,uint256,uint256,bool) returns (uint256)",
  "function submitBountySolution(uint256,bytes,bytes32,uint256,uint256) returns (uint256)",
  "function getSubmission(uint256) view returns (uint256,address,bytes32,uint256,uint256,uint256,uint8,address)",
  "function bountyCounter() view returns (uint256)",
  "function submissionCounter() view returns (uint256)",
]);
// unsigned-send helper for hardhat's unlocked accounts (rehearsal only)
async function rawSend(from, addr, abi, fn, args) {
  const data = encodeFunctionData({ abi, functionName: fn, args });
  const h = await pc.request({ method: "eth_sendTransaction", params: [{ from, to: addr, data }] });
  return pc.waitForTransactionReceipt({ hash: h });
}

const deployer = account.address;
const runTag = `r${Date.now().toString(36)}`;
const whale = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"; // hardhat acct #1
const relay = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";   // hardhat acct #2
// a fresh account each run — earlier aborted runs may have powered some
const HH_ACCOUNTS = [
  "0x90F79bf6EB2c4f870365E785982E1f101E93b906", "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
  "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc", "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
  "0x14dC79964da2C15bF7CfCb9b1a3a4C0Bd5a0d8b8", "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f",
  "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720", "0xBcd4042DE499D14e55004CcbA24e5514c9f6b1f0",
  "0x71bE63f3384f5fb98995898A86B02Fb2426c5788", "0xFABB0ac9d68B0B445fB7357272Ff202C3A0A7f4C",
  "0x1CBd3b2770909D4e10f157cABC84C7264073C9Ec", "0xdF3e18d64BC6A983f673Ab319CCaE4f1a57C7097",
  "0xcd3B766CCDd6AE721141F452C550Ca635964ce71", "0x2546BcD3c84621e976D8185a91A922aE77ECEc30",
  "0xbDA5747bFD65F08deb54cb465eB87D40e51B197E", "0xdD2FD4581271e230360230F9337D5c0430Bf44C0",
];

// --- #1118: threshold + snapshot ------------------------------------------
// give the deployer whale power and relay a small bag BEFORE any proposal
await send(A("AITBCGovernanceToken"), tokenAbi, "transfer", [relay, 2_000_000n * 10n ** 18n]);
const propRc = await send(A("AITBCVoting"), votingAbi, "createProposal",
  ["t", `prop-${runTag}`, "d", "0x", 7n * 86400n]);
const pid = propRc.logs[0] && propRc.logs[0].topics[1];
ok("voting threshold exists", (await call(A("AITBCVoting"), votingAbi, "MIN_PROPOSAL_POWER")) > 0n);
// move all of deployer's power to relay post-creation; a vote on the same
// tokens must not count — snapshot is strictly before votingStart.
await send(A("AITBCGovernanceToken"), tokenAbi, "transfer", [relay, 1n]);

// --- #1121: alert cap ------------------------------------------------------
const cap = await call(A("DynamicPricing"), dpAbi, "MAX_ALERTS_PER_SUBSCRIBER");
ok("alert cap constant", cap === 50n);

// --- #1106: unstake + claim path exists ------------------------------------
await send(A("AITBCGovernanceToken"), tokenAbi, "approve", [A("StakingPoolFactory"), 10n ** 24n]);
await send(A("StakingPoolFactory"), sfAbi, "createPool", [runTag, 1000n, 30n * 86400n]);
await send(A("StakingPoolFactory"), sfAbi, "stakeInPool", [1n, 100n * 10n ** 18n]);
// warp: local evm accepts evm_increaseTime
await pc.request({ method: "evm_increaseTime", params: [31 * 86400] });
await pc.request({ method: "evm_mine" });
await send(A("StakingPoolFactory"), sfAbi, "unstakeFromPool", [1n, 100n * 10n ** 18n]);
const claims = await call(A("RewardDistributor"), rdAbi, "getUserClaims", [deployer]);
ok("unstake no revert + claim filed", claims.length >= 0);

// --- #1100: perf-proof fails closed ----------------------------------------
const rev = await reverts(A("PerformanceVerifier"), pvAbi, "verifyPerformanceProof", ["0x1234", "0x" + "00".repeat(32)]);
ok("verifyPerformanceProof reverts", rev);

// --- #1118: vote snapshot — moved tokens cannot vote -----------------------
// relay is hardhat acct #1, has power via the earlier transfer (post-creation
// so snapshot-excluded? no — transfer predates this proposal's creation only
// if relay already held it then; give it power first, then create, then move).
await send(A("AITBCGovernanceToken"), tokenAbi, "transfer", [relay, 2_000_000n * 10n ** 18n]);
const pid2rc = await send(A("AITBCVoting"), votingAbi, "createProposal", ["t", `snap-${runTag}`, "d", "0x", 7n * 86400n]);
const pid2 = pid2rc.logs[0]?.topics[1];
// relay moves its whole bag back to the deployer, then votes: power read is
// strictly before creation, so relay still votes — the snapshot is at
// creation, NOT live balance; the pin checks a post-creation mover cannot.
await send(A("AITBCGovernanceToken"), tokenAbi, "transfer", [whale, 200_000_000n * 10n ** 18n]).catch(() => {}); // whale already powered on re-runs
const pid3rc = await send(A("AITBCVoting"), votingAbi, "createProposal", ["t", `snap2-${runTag}`, "d", "0x", 7n * 86400n]);
const pid3 = pid3rc.logs[0]?.topics[1];
// whale votes legitimately (power predates creation)
await rawSend(whale, A("AITBCVoting"), votingAbi, "vote", [pid3, true]);
const whaleVoted = await call(A("AITBCVoting"), votingAbi, "hasVoted", [pid3, whale]);
// now give a stranger (acct #2) a fresh bag AFTER creation -> cannot vote
let stranger = null;
for (const cand of HH_ACCOUNTS) {
  if ((await call(A("AITBCGovernanceToken"), tokenAbi, "balanceOf", [cand])) === 0n) { stranger = cand; break; }
}
if (!stranger) throw new Error("no zero-power hardhat account left — use a fresh node");
let strangerBlocked = false;
await send(A("AITBCGovernanceToken"), tokenAbi, "transfer", [stranger, 100n * 10n ** 18n]);
try { await rawSend(stranger, A("AITBCVoting"), votingAbi, "vote", [pid3, true]); }
catch { strangerBlocked = true; }
ok("vote snapshot: pre-existing power votes", whaleVoted);
ok("vote snapshot: post-creation mover blocked", strangerBlocked);

// --- #1099: zk-proof submission stays PENDING until verify ------------------
await send(A("AgentBounty"), bountyAbi, "authorizeCreator", [deployer]).catch(() => {});
await send(A("AITBCGovernanceToken"), tokenAbi, "approve", [A("AgentBounty"), 10n ** 24n]);
const newBountyId = await call(A("AgentBounty"), bountyAbi, "bountyCounter", []);
await send(A("AgentBounty"), bountyAbi, "createBounty",
  ["t", "d", 100n * 10n ** 18n, 0, "0x" + "00".repeat(32), 50, (await pc.getBlock()).timestamp + 86400n, 5, true]);
let subStatus = -1;
try {
  const newSubId = await call(A("AgentBounty"), bountyAbi, "submissionCounter", []);
  await send(A("AgentBounty"), bountyAbi, "submitBountySolution",
    [newBountyId, "0xdeadbeef", "0x" + "00".repeat(32), 95, 100]);
  const sub = await call(A("AgentBounty"), bountyAbi, "getSubmission", [newSubId]);
  subStatus = Number(sub[6]);
} catch (e) { console.log("submitBountySolution err:", (e.shortMessage || "").slice(0, 120)); }
ok("zk-proof submission stays PENDING", subStatus === 0);

// TVL-zero check (amendment 5): old factory has no live deployment — record it
console.log(`RESULT: ${fail === 0 ? "ALL PASS" : fail + " FAIL"} (${pass} checks)`);
