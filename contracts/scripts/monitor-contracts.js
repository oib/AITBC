/**
 * Contract monitoring script for AITBC smart contracts
 * Monitors contract health, balances, and key metrics
 */

import hardhat from "hardhat";
const { ethers } = hardhat;
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
      const TreasuryManager = await ethers.getContractFactory("TreasuryManager");
      const treasuryManager = TreasuryManager.attach(deployments.TreasuryManager);
      
      const treasuryBalance = deployments.AIToken
        ? await treasuryManager.getTreasuryBalance()
        : 0;
      const totalAllocated = await treasuryManager.getTotalAllocated();
      const totalSpent = await treasuryManager.getTotalSpent();
      
      console.log(`Treasury Balance: ${ethers.formatEther(treasuryBalance)}`);
      console.log(`Total Allocated: ${ethers.formatEther(totalAllocated)}`);
      console.log(`Total Spent: ${ethers.formatEther(totalSpent)}`);
      
      healthReport.TreasuryManager = {
        balance: ethers.formatEther(treasuryBalance),
        totalAllocated: ethers.formatEther(totalAllocated),
        totalSpent: ethers.formatEther(totalSpent),
        healthy: treasuryBalance > 0
      };
    }

    // Monitor AgentMarketplaceV2
    if (deployments.AgentMarketplaceV2) {
      console.log("\n--- AgentMarketplaceV2 Monitoring ---");
      const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
      const marketplace = AgentMarketplaceV2.attach(deployments.AgentMarketplaceV2);
      
      const stats = await marketplace.getMarketplaceStats();
      const activeListings = await marketplace.getActiveListings();
      
      console.log(`Total Listings: ${stats.totalListings}`);
      console.log(`Active Listings: ${stats.activeListings}`);
      console.log(`Completed Transactions: ${stats.completedTransactions}`);
      console.log(`Total Volume: ${ethers.formatEther(stats.totalVolume)}`);
      
      healthReport.AgentMarketplaceV2 = {
        totalListings: stats.totalListings.toString(),
        activeListings: stats.activeListings.toString(),
        completedTransactions: stats.completedTransactions.toString(),
        totalVolume: ethers.formatEther(stats.totalVolume),
        healthy: stats.activeListings >= 0
      };
    }

    // Monitor ContractRegistry
    if (deployments.ContractRegistry) {
      console.log("\n--- ContractRegistry Monitoring ---");
      const ContractRegistry = await ethers.getContractFactory("ContractRegistry");
      const registry = ContractRegistry.attach(deployments.ContractRegistry);
      
      const totalContracts = await registry.totalContracts();
      const contractIds = await registry.getAllContractIds();
      
      console.log(`Total Registered Contracts: ${totalContracts}`);
      console.log(`Registered Contracts: ${contractIds.length}`);
      
      healthReport.ContractRegistry = {
        totalContracts: totalContracts.toString(),
        registeredCount: contractIds.length,
        healthy: totalContracts > 0
      };
    }

    // Monitor DAOGovernanceEnhanced
    if (deployments.DAOGovernanceEnhanced) {
      console.log("\n--- DAOGovernanceEnhanced Monitoring ---");
      const DAOGovernanceEnhanced = await ethers.getContractFactory("DAOGovernanceEnhanced");
      const dao = DAOGovernanceEnhanced.attach(deployments.DAOGovernanceEnhanced);
      
      const minStake = await dao.minStake();
      const activeProposals = await dao.activeProposals();
      
      console.log(`Minimum Stake: ${ethers.formatEther(minStake)}`);
      console.log(`Active Proposals: ${activeProposals}`);
      
      healthReport.DAOGovernanceEnhanced = {
        minStake: ethers.formatEther(minStake),
        activeProposals: activeProposals.toString(),
        healthy: minStake > 0
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
