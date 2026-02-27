import hardhat from "hardhat";
const { ethers } = hardhat;
import fs from "fs";

async function main() {
    console.log("🚀 Deploying AITBC Smart Contracts to Mainnet");
    console.log("==============================================");
    
    const [deployer] = await ethers.getSigners();
    const balance = await ethers.provider.getBalance(deployer.address);
    
    console.log(`Deployer: ${deployer.address}`);
    console.log(`Balance: ${ethers.formatEther(balance)} ETH`);
    
    if (balance < ethers.parseEther("1")) {
        throw new Error("Insufficient ETH balance. Minimum 1 ETH recommended for deployment.");
    }
    
    console.log("");
    console.log("Proceeding with contract deployment...");
    
    // Deployment configuration
    const deployedContracts = {
        network: hardhat.network.name,
        deployer: deployer.address,
        timestamp: new Date().toISOString(),
        contracts: {}
    };
    
    try {
        // Deploy core contracts
        console.log("📦 Deploying AgentWallet...");
        const AgentWallet = await ethers.getContractFactory("AgentWallet");
        const agentWallet = await AgentWallet.deploy();
        await agentWallet.waitForDeployment();
        const agentWalletAddr = await agentWallet.getAddress();
        deployedContracts.contracts.AgentWallet = agentWalletAddr;
        console.log(`✅ AgentWallet deployed: ${agentWalletAddr}`);
        
        console.log("📦 Deploying AIPowerRental...");
        const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
        const aiPowerRental = await AIPowerRental.deploy();
        await aiPowerRental.waitForDeployment();
        const aiPowerRentalAddr = await aiPowerRental.getAddress();
        deployedContracts.contracts.AIPowerRental = aiPowerRentalAddr;
        console.log(`✅ AIPowerRental deployed: ${aiPowerRentalAddr}`);
        
        console.log("📦 Deploying AgentServiceMarketplace...");
        const AgentServiceMarketplace = await ethers.getContractFactory("AgentServiceMarketplace");
        const agentServiceMarketplace = await AgentServiceMarketplace.deploy();
        await agentServiceMarketplace.waitForDeployment();
        const agentServiceMarketplaceAddr = await agentServiceMarketplace.getAddress();
        deployedContracts.contracts.AgentServiceMarketplace = agentServiceMarketplaceAddr;
        console.log(`✅ AgentServiceMarketplace deployed: ${agentServiceMarketplaceAddr}`);
        
        console.log("📦 Deploying DynamicPricing...");
        const DynamicPricing = await ethers.getContractFactory("DynamicPricing");
        const dynamicPricing = await DynamicPricing.deploy();
        await dynamicPricing.waitForDeployment();
        const dynamicPricingAddr = await dynamicPricing.getAddress();
        deployedContracts.contracts.DynamicPricing = dynamicPricingAddr;
        console.log(`✅ DynamicPricing deployed: ${dynamicPricingAddr}`);
        
        console.log("📦 Deploying AgentStaking...");
        const AgentStaking = await ethers.getContractFactory("AgentStaking");
        const agentStaking = await AgentStaking.deploy();
        await agentStaking.waitForDeployment();
        const agentStakingAddr = await agentStaking.getAddress();
        deployedContracts.contracts.AgentStaking = agentStakingAddr;
        console.log(`✅ AgentStaking deployed: ${agentStakingAddr}`);
        
        // Save deployment info
        fs.writeFileSync("deployments.json", JSON.stringify(deployedContracts, null, 2));
        
        console.log("");
        console.log("🎉 Deployment Summary:");
        console.log("====================");
        console.log(`Network: ${deployedContracts.network}`);
        console.log(`Deployer: ${deployedContracts.deployer}`);
        console.log(`Timestamp: ${deployedContracts.timestamp}`);
        console.log("");
        console.log("Deployed Contracts:");
        for (const [name, address] of Object.entries(deployedContracts.contracts)) {
            console.log(`  ${name}: ${address}`);
        }
        
        console.log("");
        console.log("✅ All contracts deployed successfully!");
        console.log("📁 Deployment saved to: deployments.json");
        
    } catch (error) {
        console.error("❌ Deployment failed:", error);
        process.exitCode = 1;
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
