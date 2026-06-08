/**
 * CrossChainBridge Deployment Script
 * Deploys the bridge contract to Ethereum Sepolia testnet or mainnet.
 *
 * Usage:
 *   npx hardhat run scripts/deploy-bridge.js --network sepolia
 *   npx hardhat run scripts/deploy-bridge.js --network mainnet
 *
 * Required env vars:
 *   PRIVATE_KEY        - Deployer wallet private key
 *   INFURA_API_KEY     - Infura project ID (or ALCHEMY_API_KEY)
 *   ALCHEMY_API_KEY    - Alchemy API key
 */

import pkg from "hardhat";
const { ethers } = pkg;

async function main() {
  const [deployer] = await ethers.getSigners();
  const network = await ethers.provider.getNetwork();

  console.log(`\n=== AITBC CrossChainBridge Deployment ===`);
  console.log(`Network:   ${network.name} (chainId: ${network.chainId})`);
  console.log(`Deployer:  ${deployer.address}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Balance:   ${ethers.formatEther(balance)} ETH`);

  if (balance < ethers.parseEther("0.01")) {
    throw new Error("Insufficient balance for deployment (need at least 0.01 ETH)");
  }

  console.log("\nDeploying CrossChainBridge...");
  const BridgeFactory = await ethers.getContractFactory("CrossChainBridge");

  // Deploy with deployer as initial owner
  const bridge = await BridgeFactory.deploy(deployer.address);
  await bridge.waitForDeployment();

  const bridgeAddress = await bridge.getAddress();
  console.log(`CrossChainBridge deployed: ${bridgeAddress}`);

  // Record deployment
  const deployment = {
    contract: "CrossChainBridge",
    address: bridgeAddress,
    deployer: deployer.address,
    network: network.name,
    chainId: network.chainId.toString(),
    timestamp: new Date().toISOString(),
    txHash: bridge.deploymentTransaction()?.hash,
  };

  const fs = await import("fs");
  const deployFile = `${import.meta.dirname}/../deployments-bridge-${network.name}.json`;
  let deployments = [];
  if (fs.existsSync(deployFile)) {
    deployments = JSON.parse(fs.readFileSync(deployFile));
  }
  deployments.push(deployment);
  fs.writeFileSync(deployFile, JSON.stringify(deployments, null, 2));
  console.log(`\nDeployment recorded: ${deployFile}`);

  console.log("\n=== Next Steps ===");
  console.log(`1. Set BRIDGE_CONTRACT_ADDRESS=${bridgeAddress} in /etc/aitbc/blockchain.env`);
  console.log(`2. Restart aitbc-exchange.service`);
  console.log(`3. Test: aitbc exchange bridge-status`);

  return bridgeAddress;
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
