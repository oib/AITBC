/**
 * Deploy the money-critical contract subset on Sepolia (#1557, runbook
 * comment 29632, rulings comment 29652):
 *
 *   ZKReceiptVerifier -> Groth16Verifier -> AIPowerRental ->
 *   PerformanceVerifier -> PaymentProcessor -> EscrowService ->
 *   AgentStaking -> StakingPoolFactory
 *
 * CrossChainBridge is EXCLUDED (bundles into the #795 quorum redesign
 * redeploy). StakingPoolFactory.initialize(registry) is SKIPPED per ruling —
 * registry/performanceAggregator/rewardDistributor stay unset and the
 * reward paths degrade gracefully.
 *
 * DEFAULT MODE IS A DRY RUN: prints the full plan (deploy order, resolved
 * constructor args, post-deploy owner calls, record path) and broadcasts
 * nothing. Pass --live to actually deploy. This is deliberate — these are
 * money contracts and the operator GO on the #1557 GO/NO-GO checklist is a
 * separate gate.
 *
 *   npx hardhat run scripts/deploy-money-sepolia.js --network sepolia
 *     (dry run — plan only)
 *   npx hardhat run scripts/deploy-money-sepolia.js --network sepolia --live
 *     (deploy + record)
 *
 * Required / recognised env vars:
 *   DEPLOYER_KEY_FILE          - 0600 file holding the disposable deployer
 *                                key (read in-process; never env/argv).
 *                                When unset the network account (PRIVATE_KEY)
 *                                is used — local rehearsal only.
 *   BRIDGE_REQUIRE_CHAIN_ID    - required when DEPLOYER_KEY_FILE is set;
 *                                must be 11155111 (checked again in --live).
 *   ETH_RPC_URL                - Sepolia RPC (hardhat.config sepolia net).
 *
 * Constructor / role env vars:
 *   PAYMENT_TOKEN              - default Sepolia AIT
 *                                0x87fCf1bB267Bd4d56539b22f4e44137dCF71423A
 *   STAKING_TOKEN              - default: same as PAYMENT_TOKEN
 *   OWNER_ADDRESS              - post-deploy transferOwnership target for
 *                                every Ownable contract; default the 2-of-3
 *                                Safe 0xdd32618fa14eeeC4731882C958Ac80b194EA5aC7
 *                                (ruling comment 29652 item 8). ZKReceiptVerifier
 *                                has no Ownable — OWNER_ADDRESS is added via
 *                                addAuthorizedVerifier so the disposable
 *                                deployer key is never the only admin.
 *
 * Optional post-deploy authorisation lists (comma-separated addresses;
 * executed by the deployer BEFORE transferOwnership, so they must be
 * supplied at deploy time — after the Safe owns the contracts only the
 * Safe can authorise). Reuse the role addresses from the currently-live
 * Sepolia deployments; the executor reads them off-chain.
 *   PAYMENT_PAYEES             - PaymentProcessor.authorizePayee each
 *   PAYMENT_PAYERS             - PaymentProcessor.authorizePayer each
 *   PAYMENT_RELEASE_VERIFIERS  - PaymentProcessor.authorizeReleaseVerifier
 *   ESCROW_ORACLES             - EscrowService.authorizeOracle each
 *   ESCROW_ARBITERS            - EscrowService.authorizeArbiter each
 *   ESCROW_ORACLE_THRESHOLD    - setOracleVerificationThreshold (1..10)
 *   ESCROW_ORACLE_DELAY        - setOracleVerificationDelay (seconds)
 *   STAKING_ORACLES            - AgentStaking.addOracle each
 *   STAKING_AGENTS             - AgentStaking.addSupportedAgent, entries
 *                                "0xaddr:TIER" where TIER is one of
 *                                BRONZE SILVER GOLD PLATINUM DIAMOND
 *   ZK_RECEIPT_VERIFIER_ADMINS - extra ZKReceiptVerifier.addAuthorizedVerifier
 *
 * Record / misc:
 *   MONEY_DEPLOY_RECORD        - override record path (default
 *                                contracts/deployments-money-sepolia.json).
 *   AITBC_DEPLOY_COMMIT        - gitCommit stamped on record entries
 *                                (default: `git rev-parse --short=9 HEAD`).
 *   AITBC_DEPLOY_NOTE          - note stamped on record entries.
 */
import { network as hardhatNetwork } from "hardhat";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {
  padPostDeployGas,
  readDeployerKeyFile,
  requireChainIdForKeyFile,
} from "./rehearsal/deploy-guards.js";

const connection = await hardhatNetwork.getOrCreate();
const { ethers } = connection;

const SEPOLIA_CHAIN_ID = 11155111;
const DEFAULT_PAYMENT_TOKEN = "0x87fCf1bB267Bd4d56539b22f4e44137dCF71423A";
// Ruling comment 29652 item 8 — the 2-of-3 Safe that owns the bridge and
// AgentWallet Sepolia deployments. Overridable via OWNER_ADDRESS.
const DEFAULT_OWNER = "0xdd32618fa14eeeC4731882C958Ac80b194EA5aC7";
const MIN_LIVE_BALANCE = ethers.parseEther("0.02");

const TIER_NAMES = ["BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND"];

function isAddressListEnv(name) {
  return (process.env[name] || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function requireAddress(name, fallback) {
  const value = process.env[name] || fallback;
  if (!value || !ethers.isAddress(value)) {
    throw new Error(`${name} must be a valid address (got ${JSON.stringify(value)})`);
  }
  return ethers.getAddress(value);
}

function addressList(name) {
  return isAddressListEnv(name).map((a) => {
    if (!ethers.isAddress(a)) {
      throw new Error(`${name} entry is not a valid address: ${JSON.stringify(a)}`);
    }
    return ethers.getAddress(a);
  });
}

function uintEnv(name) {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return undefined;
  if (!/^\d+$/.test(raw)) throw new Error(`${name} must be a non-negative integer`);
  return BigInt(raw);
}

/** Parse "0xaddr:TIER,0xaddr2:TIER" into [{address, tierIndex}]. */
function agentList(name) {
  return isAddressListEnv(name).map((entry) => {
    const [addr, tier] = entry.split(":").map((s) => s.trim());
    if (!addr || !tier) {
      throw new Error(`${name} entries must be "0xaddr:TIER" — got ${JSON.stringify(entry)}`);
    }
    if (!ethers.isAddress(addr)) {
      throw new Error(`${name} entry is not a valid address: ${JSON.stringify(addr)}`);
    }
    const tierIndex = TIER_NAMES.indexOf(tier.toUpperCase());
    if (tierIndex < 0) {
      throw new Error(`${name} tier must be one of ${TIER_NAMES.join(" ")} — got ${tier}`);
    }
    return { address: ethers.getAddress(addr), tierIndex };
  });
}

/**
 * Record path: default contracts/deployments-money-sepolia.json (the file
 * the runbook commits after the real deploy). MONEY_DEPLOY_RECORD overrides.
 * Refuses paths that would clobber sibling deployment records.
 */
function resolveMoneyRecord(env, contractsDir) {
  const record = env.MONEY_DEPLOY_RECORD;
  if (record) {
    const resolved = path.resolve(record);
    if (/^deployments-(bridge|agent-wallet)-.*\.json$/.test(path.basename(resolved))) {
      throw new Error(`refusing a record path named like a sibling deployments file: ${resolved}`);
    }
    if (
      path.dirname(resolved) === path.resolve(contractsDir) &&
      path.basename(resolved) !== "deployments-money-sepolia.json"
    ) {
      throw new Error(`refusing a deployments record inside contracts/: ${resolved}`);
    }
    return resolved;
  }
  return `${contractsDir}/deployments-money-sepolia.json`;
}

function gitCommit() {
  if (process.env.AITBC_DEPLOY_COMMIT) return process.env.AITBC_DEPLOY_COMMIT;
  try {
    return execSync("git rev-parse --short=9 HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

/**
 * Deploy plan, in dependency order. argNames are the constructor parameter
 * names for the record; resolve() returns the actual args at run time.
 */
function buildPlan({ paymentToken, stakingToken }) {
  return [
    {
      name: "ZKReceiptVerifier",
      contractName: "ZKReceiptVerifier",
      args: [],
      argNames: [],
      ownable: false,
    },
    {
      name: "Groth16Verifier",
      contractName: "Groth16Verifier",
      args: [],
      argNames: [],
      ownable: false,
    },
    {
      name: "AIPowerRental",
      contractName: "AIPowerRental",
      args: [paymentToken, "@zkReceiptVerifier", "@groth16Verifier"],
      argNames: ["_paymentToken", "_zkVerifier", "_groth16Verifier"],
      ownable: true,
    },
    {
      name: "PerformanceVerifier",
      contractName: "PerformanceVerifier",
      args: ["@zkReceiptVerifier", "@groth16Verifier", "@aiPowerRental"],
      argNames: ["_zkVerifier", "_groth16Verifier", "_aiPowerRental"],
      ownable: true,
    },
    {
      name: "PaymentProcessor",
      contractName: "PaymentProcessor",
      args: [paymentToken, "@aiPowerRental"],
      argNames: ["_paymentToken", "_aiPowerRental"],
      ownable: true,
    },
    {
      name: "EscrowService",
      contractName: "EscrowService",
      args: [paymentToken, "@aiPowerRental", "@paymentProcessor"],
      argNames: ["_paymentToken", "_aiPowerRental", "_paymentProcessor"],
      ownable: true,
    },
    {
      name: "AgentStaking",
      contractName: "AgentStaking",
      args: [paymentToken, "@performanceVerifier"],
      argNames: ["_paymentToken", "_performanceVerifier"],
      ownable: true,
    },
    {
      name: "StakingPoolFactory",
      contractName: "StakingPoolFactory",
      args: [stakingToken],
      argNames: ["_stakingToken"],
      ownable: true,
    },
  ];
}

function resolveArgs(step, deployed) {
  return step.args.map((a) => {
    if (typeof a === "string" && a.startsWith("@")) {
      const ref = a.slice(1);
      const depKey = Object.keys(deployed).find(
        (k) => k.toLowerCase() === ref.toLowerCase()
      );
      const dep = deployed[ref] || (depKey && deployed[depKey]);
      if (!dep) throw new Error(`${step.name}: dependency ${a} not deployed yet`);
      return dep;
    }
    return a;
  });
}

/** Post-deploy calls per contract, executed while the deployer is still owner. */
function postDeployCalls(step, env) {
  const calls = [];
  switch (step.name) {
    case "ZKReceiptVerifier": {
      // No Ownable: the deployer is the only authorizedVerifier at birth.
      // OWNER_ADDRESS must be added explicitly or the disposable key is
      // the sole admin forever.
      calls.push({ fn: "addAuthorizedVerifier", args: [env.owner] });
      for (const a of env.zkAdmins) calls.push({ fn: "addAuthorizedVerifier", args: [a] });
      break;
    }
    case "PaymentProcessor":
      for (const a of env.paymentPayees) calls.push({ fn: "authorizePayee", args: [a] });
      for (const a of env.paymentPayers) calls.push({ fn: "authorizePayer", args: [a] });
      for (const a of env.paymentReleaseVerifiers)
        calls.push({ fn: "authorizeReleaseVerifier", args: [a] });
      break;
    case "EscrowService":
      for (const a of env.escrowOracles) calls.push({ fn: "authorizeOracle", args: [a] });
      for (const a of env.escrowArbiters) calls.push({ fn: "authorizeArbiter", args: [a] });
      if (env.escrowOracleThreshold !== undefined)
        calls.push({ fn: "setOracleVerificationThreshold", args: [env.escrowOracleThreshold] });
      if (env.escrowOracleDelay !== undefined)
        calls.push({ fn: "setOracleVerificationDelay", args: [env.escrowOracleDelay] });
      break;
    case "AgentStaking":
      for (const a of env.stakingOracles) calls.push({ fn: "addOracle", args: [a] });
      for (const ag of env.stakingAgents)
        calls.push({ fn: "addSupportedAgent", args: [ag.address, ag.tierIndex] });
      if (env.stakingPerformanceUpdateDelay !== undefined)
        calls.push({ fn: "setPerformanceUpdateDelay", args: [env.stakingPerformanceUpdateDelay] });
      break;
    default:
      break;
  }
  return calls;
}

async function main() {
  // Hardhat 3 run task rejects unknown flags, so --live cannot always be
  // passed on the CLI; MONEY_DEPLOY_LIVE=1 is the env equivalent.
  const live = process.argv.includes("--live") || process.env.MONEY_DEPLOY_LIVE === "1";
  const contractsDir = `${import.meta.dirname}/..`;

  requireChainIdForKeyFile(process.env);
  const network = await ethers.provider.getNetwork();
  const required = process.env.BRIDGE_REQUIRE_CHAIN_ID;
  if (required && network.chainId.toString() !== required) {
    throw new Error(`refusing chainId ${network.chainId} (required ${required})`);
  }
  if (live && BigInt(network.chainId) !== BigInt(SEPOLIA_CHAIN_ID)) {
    throw new Error(
      `--live is Sepolia-only: refusing chainId ${network.chainId} (required ${SEPOLIA_CHAIN_ID})`
    );
  }

  const deployFile = resolveMoneyRecord(process.env, contractsDir);

  const paymentToken = requireAddress("PAYMENT_TOKEN", DEFAULT_PAYMENT_TOKEN);
  const stakingToken = requireAddress("STAKING_TOKEN", paymentToken);
  const owner = requireAddress("OWNER_ADDRESS", DEFAULT_OWNER);

  const env = {
    owner,
    paymentPayees: addressList("PAYMENT_PAYEES"),
    paymentPayers: addressList("PAYMENT_PAYERS"),
    paymentReleaseVerifiers: addressList("PAYMENT_RELEASE_VERIFIERS"),
    escrowOracles: addressList("ESCROW_ORACLES"),
    escrowArbiters: addressList("ESCROW_ARBITERS"),
    escrowOracleThreshold: uintEnv("ESCROW_ORACLE_THRESHOLD"),
    escrowOracleDelay: uintEnv("ESCROW_ORACLE_DELAY"),
    stakingOracles: addressList("STAKING_ORACLES"),
    stakingAgents: agentList("STAKING_AGENTS"),
    stakingPerformanceUpdateDelay: uintEnv("STAKING_PERFORMANCE_UPDATE_DELAY"),
    zkAdmins: addressList("ZK_RECEIPT_VERIFIER_ADMINS"),
  };
  if (env.escrowOracleThreshold !== undefined &&
      (env.escrowOracleThreshold < 1n || env.escrowOracleThreshold > 10n)) {
    throw new Error("ESCROW_ORACLE_THRESHOLD must be between 1 and 10");
  }
  if (env.escrowOracleDelay !== undefined && env.escrowOracleDelay > 24n * 3600n) {
    throw new Error("ESCROW_ORACLE_DELAY must be <= 86400 seconds");
  }

  const plan = buildPlan({ paymentToken, stakingToken });

  // Resolve deployer (never printed secrets; address only).
  const keyFile = process.env.DEPLOYER_KEY_FILE;
  let deployer = null;
  if (keyFile) {
    deployer = new ethers.Wallet(readDeployerKeyFile(keyFile), ethers.provider);
  } else {
    [deployer] = await ethers.getSigners();
  }

  // Load any existing record for resume: name -> latest address.
  const deployed = {};
  const priorEntries = [];
  if (fs.existsSync(deployFile)) {
    const prior = JSON.parse(fs.readFileSync(deployFile, "utf8"));
    const arr = Array.isArray(prior) ? prior : [prior];
    for (const e of arr) {
      if (e && e.contract && e.address) {
        deployed[e.contract] = e.address; // last entry wins
        priorEntries.push(e);
      }
    }
  }

  // Resolve @dep args for display — deps deployed earlier in this same run
  // have no address yet, so show the dependency name as a placeholder.
  const displayArgs = (s) =>
    s.args.map((a) =>
      typeof a === "string" && a.startsWith("@")
        ? deployed[a.slice(1)] || `<${a.slice(1)}>`
        : a
    );
  const displayPlan = plan.map((s) => ({ ...s, resolvedArgs: displayArgs(s) }));

  console.log(`\n=== AITBC money-subset deploy (${live ? "LIVE" : "DRY RUN"}) ===`);
  console.log(`Network:      ${network.name} (chainId: ${network.chainId})`);
  console.log(`Deployer:     ${deployer ? deployer.address : "(none — would use network account)"}`);
  console.log(`Owner (Safe): ${owner}`);
  console.log(`PaymentToken: ${paymentToken}`);
  console.log(`StakingToken: ${stakingToken}`);
  console.log(`Record:       ${deployFile}`);
  if (deployer) {
    try {
      const bal = await ethers.provider.getBalance(deployer.address);
      console.log(`Balance:      ${ethers.formatEther(bal)} ETH`);
      if (live && bal < MIN_LIVE_BALANCE) {
        throw new Error(`insufficient balance for 8-contract deploy (need >= ${ethers.formatEther(MIN_LIVE_BALANCE)} ETH)`);
      }
    } catch (e) {
      if (live) throw e;
      console.log(`Balance:      (unavailable offline)`);
    }
  }

  console.log("\nDeploy order:");
  for (const s of displayPlan) {
    const done = deployed[s.name] ? ` [resumed: ${deployed[s.name]}]` : "";
    console.log(`  ${s.name}${done}`);
    if (s.resolvedArgs.length) {
      console.log(`    args: ${s.argNames.map((n, i) => `${n}=${s.resolvedArgs[i]}`).join(", ")}`);
    }
    const calls = postDeployCalls(s, env);
    for (const c of calls) {
      console.log(`    post: ${c.fn}(${c.args.join(", ")})`);
    }
    if (s.ownable) console.log(`    post: transferOwnership(${owner})`);
  }
  console.log("  (StakingPoolFactory.initialize(registry) intentionally skipped — ruling 29652)");

  if (!live) {
    console.log("\nDRY RUN — nothing broadcast, no record written. Re-run with --live after operator GO.");
    return;
  }
  if (!deployer) throw new Error("no deployer account (set DEPLOYER_KEY_FILE or PRIVATE_KEY)");

  // --- live deploy -------------------------------------------------------
  const sendCall = async (label, to, data) => {
    // Load-balanced public RPCs can serve a stale pending-nonce — retry on
    // nonce races; the post-deploy calls are idempotent authorizations.
    let lastErr;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const estimate = await ethers.provider.estimateGas({ from: deployer.address, to, data });
        const gasLimit = padPostDeployGas(estimate);
        const tx = await deployer.sendTransaction({ to, data, gasLimit });
        const receipt = await tx.wait();
        if (!receipt || receipt.status !== 1) throw new Error(`${label} reverted: ${tx.hash}`);
        console.log(`${label}: ${tx.hash} gasUsed=${receipt.gasUsed}`);
        return receipt;
      } catch (e) {
        lastErr = e;
        if (attempt === 3 || !/nonce too low|replacement transaction underpriced|already known|transaction underpriced/i.test(String(e))) throw e;
        await new Promise((r) => setTimeout(r, 4000));
      }
    }
    throw lastErr;
  };

  const appendRecord = (entry) => {
    const arr = fs.existsSync(deployFile)
      ? JSON.parse(fs.readFileSync(deployFile, "utf8"))
      : [];
    const list = Array.isArray(arr) ? arr : [arr];
    list.push(entry);
    fs.writeFileSync(deployFile, JSON.stringify(list, null, 2) + "\n");
  };

  const contracts = {};
  for (const step of plan) {
    if (deployed[step.name]) {
      console.log(`${step.name}: already recorded at ${deployed[step.name]} — skipping deploy`);
      continue;
    }
    const args = resolveArgs(step, deployed);
    const Factory = await ethers.getContractFactory(step.contractName, deployer);
    const tx = await Factory.deploy(...args);
    await tx.waitForDeployment();
    const address = await tx.getAddress();
    const txHash = tx.deploymentTransaction()?.hash || null;
    deployed[step.name] = address;
    contracts[step.name] = await ethers.getContractAt(step.contractName, address, deployer);

    const entry = {
      contract: step.contractName,
      address,
      deployer: deployer.address,
      owner,
      network: "sepolia",
      chainId: SEPOLIA_CHAIN_ID.toString(),
      timestamp: new Date().toISOString(),
      txHash,
      gitCommit: gitCommit(),
      constructorArgs: Object.fromEntries(step.argNames.map((n, i) => [n, args[i]])),
      note:
        process.env.AITBC_DEPLOY_NOTE ||
        "#1557 money-subset redeploy (runbook c29632, rulings c29652). Bridge excluded; StakingPoolFactory.initialize skipped.",
    };
    appendRecord(entry);
    console.log(`${step.name} deployed: ${address} (${txHash}) — recorded`);
  }

  // --- post-deploy: authorisations then transferOwnership ----------------
  for (const step of plan) {
    const address = deployed[step.name];
    if (!address) throw new Error(`internal: ${step.name} has no address`);
    const c = contracts[step.name] || (await ethers.getContractAt(step.contractName, address, deployer));
    contracts[step.name] = c;

    if (step.name === "ZKReceiptVerifier") {
      for (const call of postDeployCalls(step, env)) {
        await sendCall(`${step.name}.${call.fn}`, address, c.interface.encodeFunctionData(call.fn, call.args));
      }
      continue; // no Ownable / no transferOwnership
    }
    if (!step.ownable) {
      console.log(`${step.name}: not Ownable — no post-deploy owner calls`);
      continue;
    }

    // Only run owner calls while the deployer still owns the contract —
    // on resume after a prior transferOwnership the Safe already owns it.
    let currentOwner;
    try {
      currentOwner = await c.owner();
    } catch {
      currentOwner = null;
    }
    if (!currentOwner || currentOwner.toLowerCase() !== deployer.address.toLowerCase()) {
      console.log(`${step.name}: owner is ${currentOwner ?? "n/a"} — skipping authorisations/transferOwnership`);
      continue;
    }

    for (const call of postDeployCalls(step, env)) {
      await sendCall(`${step.name}.${call.fn}`, address, c.interface.encodeFunctionData(call.fn, call.args));
    }
    await sendCall(
      `${step.name}.transferOwnership`,
      address,
      c.interface.encodeFunctionData("transferOwnership", [owner])
    );
    // Public RPCs (load-balanced) can serve a pre-receipt state right after
    // tx.wait() — retry the read-back a few times before declaring failure.
    let nowOwner = await c.owner();
    for (let i = 0; i < 5 && nowOwner.toLowerCase() !== owner.toLowerCase(); i++) {
      await new Promise((r) => setTimeout(r, 3000));
      nowOwner = await c.owner();
    }
    if (nowOwner.toLowerCase() !== owner.toLowerCase()) {
      throw new Error(`${step.name}: owner is ${nowOwner} after transferOwnership, expected ${owner}`);
    }
    console.log(`${step.name}: ownership transferred to ${owner}`);
  }

  console.log(
    "\n=== Deploy complete — record: " + deployFile + " ==="
  );
  console.log(
    "Next (operator): commit deployments-money-sepolia.json, post tx-hash ledger comment on #1557, " +
      "then the separate gated step — fleet env wiring (ENERGY_*_CONTRACT_ADDRESS etc.)."
  );
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
