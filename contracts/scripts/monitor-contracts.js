/**
 * Contract monitoring script for AITBC smart contracts
 * Monitors contract health, balances, and key metrics
 */

import { network as hardhatNetwork } from "hardhat";
const connection = await hardhatNetwork.getOrCreate();
const { ethers } = connection;
import fs from "fs";

async function main() {
  console.log("=== AITBC Smart Contract Monitoring ===");

  const network = await ethers.provider.getNetwork();
  console.log("Network:", network.name);
  console.log("Chain ID:", network.chainId.toString());
  console.log("Block:", await ethers.provider.getBlockNumber());

  // Load deployment addresses
  const deploymentFile = process.env.DEPLOYMENT_FILE || `deployments-${network.name}.json`;

  if (!fs.existsSync(deploymentFile)) {
    console.error(`Deployment file not found: ${deploymentFile}`);
    console.log("Usage: DEPLOYMENT_FILE=deployments-localhost.json npx hardhat run scripts/monitor-contracts.js");
    process.exit(1);
  }

  const deployments = JSON.parse(fs.readFileSync(deploymentFile, "utf8"));
  console.log("\nLoaded deployments from:", deploymentFile);

  const healthReport = {};

  try {
    // Monitor AIToken
    if (deployments.AIToken) {
      console.log("\n--- AIToken Monitoring ---");
      const AIToken = await ethers.getContractFactory("AIToken");
      const aiToken = AIToken.attach(deployments.AIToken);

      const totalSupply = await aiToken.totalSupply();
      const treasuryBalance = deployments.TreasuryManager
        ? await aiToken.balanceOf(deployments.TreasuryManager)
        : 0;

      console.log(`Total Supply: ${ethers.formatEther(totalSupply)}`);
      console.log(`Treasury Balance: ${ethers.formatEther(treasuryBalance)}`);

      healthReport.AIToken = {
        totalSupply: ethers.formatEther(totalSupply),
        treasuryBalance: ethers.formatEther(treasuryBalance),
        healthy: treasuryBalance > 0
      };
    }

    // Monitor TreasuryManager
    if (deployments.TreasuryManager) {
      console.log("\n--- TreasuryManager Monitoring ---");

      // This block used to call getTreasuryBalance(), getTotalAllocated() and
      // getTotalSpent(). TreasuryManager.sol declares none of them -- its only balance
      // accessor is getBudgetBalance(category). The script had been unrunnable since
      // `contracts/package.json` gained "type": "module", so the calls were never made and
      // the mismatch never surfaced. The treasury's holding is measured the way
      // verify-deployment.js measures it: the token balance at the treasury's address.
      let treasuryBalance = 0n;
      if (deployments.AIToken) {
        const AIToken = await ethers.getContractFactory("AIToken");
        const aiToken = AIToken.attach(deployments.AIToken);
        treasuryBalance = await aiToken.balanceOf(deployments.TreasuryManager);
      }

      console.log(`Treasury Balance: ${ethers.formatEther(treasuryBalance)} AIT`);

      healthReport.TreasuryManager = {
        balance: ethers.formatEther(treasuryBalance),
        healthy: treasuryBalance > 0n
      };
    }

    // Monitor AgentMarketplaceV2
    if (deployments.AgentMarketplaceV2) {
      console.log("\n--- AgentMarketplaceV2 Monitoring ---");
      const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
      const marketplace = AgentMarketplaceV2.attach(deployments.AgentMarketplaceV2);

      // This block used to call getMarketplaceStats() and getActiveListings() and report
      // totalListings / completedTransactions / totalVolume. AgentMarketplaceV2.sol has
      // none of that -- it has no listings concept at all. What it exposes is
      // capabilityCounter, subscriptionCounter and platformFeePercentage. Reported here
      // instead of inventing a stats struct the contract does not have.
      const capabilities = await marketplace.capabilityCounter();
      const subscriptions = await marketplace.subscriptionCounter();
      const feeBasisPoints = await marketplace.platformFeePercentage();

      console.log(`Capabilities: ${capabilities}`);
      console.log(`Subscriptions: ${subscriptions}`);
      console.log(`Platform Fee: ${Number(feeBasisPoints) / 100}%`);

      healthReport.AgentMarketplaceV2 = {
        capabilities: capabilities.toString(),
        subscriptions: subscriptions.toString(),
        platformFeePercentage: Number(feeBasisPoints) / 100,
        healthy: feeBasisPoints > 0n
      };
    }

    // Monitor ContractRegistry
    if (deployments.ContractRegistry) {
      console.log("\n--- ContractRegistry Monitoring ---");
      const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
      const registry = ContractRegistry.attach(deployments.ContractRegistry);

      // totalContracts() and getAllContractIds() do not exist; the contract exposes
      // getRegistryStats(), which returns (totalContracts, version, isPaused, owner).
      const [totalContracts, registryVersion, isPaused] = await registry.getRegistryStats();

      console.log(`Total Registered Contracts: ${totalContracts}`);
      console.log(`Registry Version: ${registryVersion}`);
      console.log(`Paused: ${isPaused}`);

      healthReport.ContractRegistry = {
        totalContracts: totalContracts.toString(),
        version: registryVersion.toString(),
        paused: isPaused,
        healthy: totalContracts > 0n && !isPaused
      };
    }

    // Monitor DAOGovernanceEnhanced
    if (deployments.DAOGovernanceEnhanced) {
      console.log("\n--- DAOGovernanceEnhanced Monitoring ---");
      const DAOGovernanceEnhanced = await ethers.getContractFactory("DAOGovernanceEnhanced");
      const dao = DAOGovernanceEnhanced.attach(deployments.DAOGovernanceEnhanced);

      // minStake() and activeProposals() do not exist. The contract declares
      // minStakeAmount and proposalCount.
      const minStake = await dao.minStakeAmount();
      const proposalCount = await dao.proposalCount();

      console.log(`Minimum Stake: ${ethers.formatEther(minStake)}`);
      console.log(`Proposals Created: ${proposalCount}`);

      healthReport.DAOGovernanceEnhanced = {
        minStake: ethers.formatEther(minStake),
        proposalCount: proposalCount.toString(),
        healthy: minStake > 0n
      };
    }

    // Generate health summary
    console.log("\n=== Health Summary ===");
    let allHealthy = true;

    for (const [name, data] of Object.entries(healthReport)) {
      const status = data.healthy ? "✅ Healthy" : "❌ Unhealthy";
      console.log(`${status} ${name}`);
      if (!data.healthy) allHealthy = false;
    }

    // Save health report
    const healthFile = `health-report-${network.name}-${Date.now()}.json`;
    fs.writeFileSync(healthFile, JSON.stringify(healthReport, null, 2));
    console.log(`\nHealth report saved to: ${healthFile}`);

    if (allHealthy) {
      console.log("\n✅ All contracts are healthy!");
      process.exit(0);
    } else {
      console.log("\n⚠️  Some contracts need attention!");
      process.exit(1);
    }

  } catch (error) {
    console.error("\n❌ Monitoring failed:", error);
    process.exit(1);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
