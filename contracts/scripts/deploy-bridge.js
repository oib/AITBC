/**
 * CrossChainBridge Deployment Script (BR-1)
 *
 * Deploys the bridge contract, pauses it, and hands ownership to the 2-of-3
 * Safe in the same run. A deployer-owned or unpaused bridge is never the
 * intended end state, so both are enforced, not just documented.
 *
 * Usage:
 *   BRIDGE_OWNER_SAFE=0x... BRIDGE_FEE_RECIPIENT=0x... \
 *     npx hardhat run scripts/deploy-bridge.js --network sepolia
 *
 * Required env vars:
 *   BRIDGE_OWNER_SAFE     - Address of the 2-of-3 Safe that will own the bridge.
 *   BRIDGE_FEE_RECIPIENT  - Address that receives bridge fees. Never reuse the
 *                           disposable deployer here — the key is thrown away.
 * Optional env vars:
 *   DEPLOYER_KEY_FILE     - Path to a file holding the deployer key; read
 *                           in-process (never via env/argv). Overrides the
 *                           network-configured account.
 *   BRIDGE_DEPLOY_RECORD  - Override path for the deployments record file
 *                           (rehearsals write outside deployments-bridge-*).
 *   BRIDGE_REQUIRE_CHAIN_ID - Refuse to run unless the chain id matches.
 * Network-dependent:
 *   PRIVATE_KEY           - Deployer wallet private key (disposable key only;
 *                           never a Safe signer or a funded long-lived key)
 *   INFURA_API_KEY / ALCHEMY_API_KEY - RPC credentials for public networks
 *
 * Local dry run (no real keys, no network RPC):
 *   BRIDGE_OWNER_SAFE=<any-throwaway-address> BRIDGE_FEE_RECIPIENT=<any-throwaway-address> \
 *     npx hardhat run scripts/deploy-bridge.js --network hardhat
 */

import { network as hardhatNetwork } from "hardhat";
const connection = await hardhatNetwork.getOrCreate();
const { ethers } = connection;

function requireEnv(name) {
  const value = process.env[name];
  if (!value || !ethers.isAddress(value)) {
    throw new Error(`${name} is required and must be a valid address`);
  }
  return value;
}

async function main() {
  const network = await ethers.provider.getNetwork();

  const requiredChainId = process.env.BRIDGE_REQUIRE_CHAIN_ID;
  if (requiredChainId && network.chainId.toString() !== requiredChainId) {
    throw new Error(`refusing to deploy on chainId ${network.chainId} (required: ${requiredChainId})`);
  }

  // DEPLOYER_KEY_FILE keeps the key out of env vars, argv and shell history:
  // it is read in-process here. When unset, the network-configured account is
  // used (PRIVATE_KEY path).
  const keyFile = process.env.DEPLOYER_KEY_FILE;
  let deployer;
  if (keyFile) {
    const fs = await import("fs");
    const key = fs.readFileSync(keyFile, "utf8").trim();
    deployer = new ethers.Wallet(key.startsWith("0x") ? key : `0x${key}`, ethers.provider);
  } else {
    [deployer] = await ethers.getSigners();
  }
  if (!deployer) {
    throw new Error("no deployer account (set DEPLOYER_KEY_FILE or PRIVATE_KEY)");
  }

  const safeOwner = requireEnv("BRIDGE_OWNER_SAFE");
  const feeRecipient = requireEnv("BRIDGE_FEE_RECIPIENT");
  if (feeRecipient.toLowerCase() === deployer.address.toLowerCase()) {
    throw new Error(
      "BRIDGE_FEE_RECIPIENT must not be the disposable deployer — the key is thrown away"
    );
  }

  console.log(`\n=== AITBC CrossChainBridge Deployment ===`);
  console.log(`Network:      ${network.name} (chainId: ${network.chainId})`);
  console.log(`Deployer:     ${deployer.address} (disposable)`);
  console.log(`Owner (Safe): ${safeOwner}`);
  console.log(`Fee recipient:${feeRecipient}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Balance:      ${ethers.formatEther(balance)} ETH`);

  if (balance < ethers.parseEther("0.01")) {
    throw new Error("Insufficient balance for deployment (need at least 0.01 ETH)");
  }

  console.log("\nDeploying CrossChainBridge...");
  // Bind the factory to the resolved deployer — required when the account
  // comes from DEPLOYER_KEY_FILE and the network config has no accounts.
  const BridgeFactory = await ethers.getContractFactory("CrossChainBridge", deployer);

  // Constructor arg is the fee recipient; Ownable makes the deployer the
  // initial owner, and ownership is handed to the Safe below in the same run.
  const bridge = await BridgeFactory.deploy(feeRecipient);
  await bridge.waitForDeployment();

  const bridgeAddress = await bridge.getAddress();
  console.log(`CrossChainBridge deployed: ${bridgeAddress}`);

  // Start paused: validators, tokens and chains are configured through the
  // Safe first, then the Safe unpauses.
  await (await bridge.pause()).wait();

  // Hand ownership to the 2-of-3 Safe before anything else can happen.
  await (await bridge.transferOwnership(safeOwner)).wait();

  // Read back the deployed state — assert, don't trust the calls above.
  // chainValidators is a public mapping of arrays: index 0 reverts when the
  // list is empty, which is the exact assert that no validator was seeded.
  let validatorSeeded = true;
  try {
    await bridge.chainValidators(1, 0);
  } catch {
    validatorSeeded = false;
  }
  const checks = {
    owner: await bridge.owner(),
    paused: await bridge.paused(),
    validatorSeeded,
    tokenProbed: (await bridge.supportedTokens(safeOwner)).isActive,
    requestCounter: Number(await bridge.requestCounter()),
  };
  console.log("\nPost-deploy state:", checks);

  const failures = [];
  if (checks.owner.toLowerCase() !== safeOwner.toLowerCase()) {
    failures.push(`owner is ${checks.owner}, expected Safe ${safeOwner}`);
  }
  if (!checks.paused) {
    failures.push("bridge is not paused");
  }
  if (checks.validatorSeeded) {
    failures.push("a validator was seeded at deploy — must be set through the Safe");
  }
  if (checks.tokenProbed) {
    failures.push("a supported token was seeded at deploy — must be set through the Safe");
  }
  if (checks.requestCounter !== 0) {
    failures.push(`requestCounter is ${checks.requestCounter}, expected 0`);
  }
  if (failures.length) {
    throw new Error(`Post-deploy verification failed: ${failures.join("; ")}`);
  }

  // Record deployment
  const deployment = {
    contract: "CrossChainBridge",
    address: bridgeAddress,
    deployer: deployer.address,
    owner: safeOwner,
    feeRecipient,
    pausedAtDeploy: true,
    network: network.name,
    chainId: network.chainId.toString(),
    timestamp: new Date().toISOString(),
    txHash: bridge.deploymentTransaction()?.hash,
  };

  const fs = await import("fs");
  const deployFile = process.env.BRIDGE_DEPLOY_RECORD
    || `${import.meta.dirname}/../deployments-bridge-${network.name}.json`;
  let deployments = [];
  if (fs.existsSync(deployFile)) {
    deployments = JSON.parse(fs.readFileSync(deployFile));
  }
  deployments.push(deployment);
  fs.writeFileSync(deployFile, JSON.stringify(deployments, null, 2));
  console.log(`\nDeployment recorded: ${deployFile}`);

  console.log("\n=== Next Steps ===");
  console.log(`1. Safe: configure validators, supported tokens and chains, then unpause.`);
  console.log(`2. Set BRIDGE_CONTRACT_ADDRESS=${bridgeAddress} in /etc/aitbc/blockchain.env`);
  console.log(`3. Restart aitbc-exchange.service (operator action)`);
  console.log(`4. Test: aitbc exchange bridge-status`);

  return bridgeAddress;
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
