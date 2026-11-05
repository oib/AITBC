/**
 * Deploy AgentWallet (Phase C1, #1143) on Sepolia against the live rehearsal AIToken.
 *
 *   PAYMENT_TOKEN=0x87fC... \
 *   DEPLOYER_KEY_FILE=/path/to/disposable.key \
 *   BRIDGE_REQUIRE_CHAIN_ID=11155111 \
 *   BRIDGE_DEPLOY_RECORD=/var/tmp/agentwallet-sepolia.json \
 *   ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
 *     npx hardhat run scripts/deploy-agent-wallet-sepolia.js --network sepolia
 *
 * Without DEPLOYER_KEY_FILE uses hardhat network account (PRIVATE_KEY).
 * Record appends one entry; default path contracts/deployments-agent-wallet-sepolia.json
 * when not using DEPLOYER_KEY_FILE.
 */
import { network as hardhatNetwork } from "hardhat";
import fs from "node:fs";
import {
  readDeployerKeyFile,
  requireChainIdForKeyFile,
  resolveDeployRecord,
} from "./rehearsal/deploy-guards.js";

const connection = await hardhatNetwork.getOrCreate();
const { ethers } = connection;

const DEFAULT_PAYMENT_TOKEN = "0x87fCf1bB267Bd4d56539b22f4e44137dCF71423A";

function resolvePaymentToken() {
  const t = process.env.PAYMENT_TOKEN || DEFAULT_PAYMENT_TOKEN;
  if (!ethers.isAddress(t)) throw new Error("PAYMENT_TOKEN must be a valid address");
  return t;
}

function resolveAgentWalletRecord(env, contractsDir, networkName) {
  if (env.DEPLOYER_KEY_FILE) {
    return resolveDeployRecord(env, contractsDir, networkName);
  }
  return (
    env.AGENT_WALLET_DEPLOY_RECORD ||
    `${contractsDir}/deployments-agent-wallet-sepolia.json`
  );
}

async function main() {
  requireChainIdForKeyFile(process.env);
  const network = await ethers.provider.getNetwork();
  const required = process.env.BRIDGE_REQUIRE_CHAIN_ID;
  if (required && network.chainId.toString() !== required) {
    throw new Error(`refusing chainId ${network.chainId} (required ${required})`);
  }

  const contractsDir = `${import.meta.dirname}/..`;
  const deployFile = resolveAgentWalletRecord(process.env, contractsDir, connection.networkName);

  let deployer;
  const keyFile = process.env.DEPLOYER_KEY_FILE;
  if (keyFile) {
    deployer = new ethers.Wallet(readDeployerKeyFile(keyFile), ethers.provider);
  } else {
    [deployer] = await ethers.getSigners();
  }
  if (!deployer) throw new Error("no deployer account");

  const paymentToken = resolvePaymentToken();
  const bal = await ethers.provider.getBalance(deployer.address);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance: ${ethers.formatEther(bal)} ETH`);
  console.log(`Payment token: ${paymentToken}`);
  if (bal < ethers.parseEther("0.005")) {
    throw new Error("insufficient Sepolia ETH for deploy");
  }

  const AgentWallet = await ethers.getContractFactory("AgentWallet", deployer);
  const tx = await AgentWallet.deploy(paymentToken);
  await tx.waitForDeployment();
  const address = await tx.getAddress();
  const deployTx = tx.deploymentTransaction();
  const txHash = deployTx ? deployTx.hash : null;

  const entry = {
    contract: "AgentWallet",
    address,
    deployer: deployer.address,
    paymentToken,
    network: "sepolia",
    chainId: "11155111",
    timestamp: new Date().toISOString(),
    txHash,
    gitCommit: process.env.AITBC_DEPLOY_COMMIT || "1ff11a641",
    note:
      process.env.AITBC_DEPLOY_NOTE ||
      "Phase C1 (#1143) + #1149 consent (propose/accept managed registration). Sepolia rehearsal.",
  };

  let record = [];
  if (fs.existsSync(deployFile)) {
    record = JSON.parse(fs.readFileSync(deployFile, "utf8"));
    if (!Array.isArray(record)) record = [record];
  }
  record.push(entry);
  fs.writeFileSync(deployFile, JSON.stringify(record, null, 2) + "\n");
  console.log(`AgentWallet deployed: ${address}`);
  console.log(`Record: ${deployFile}`);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
