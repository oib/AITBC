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
        // Deploy prerequisites first
        console.log("📦 Deploying AIToken (Mock)...");
        const AIToken = await ethers.getContractFactory("AIToken");
        const initialSupply = ethers.parseEther("1000000000"); // 1B tokens
        const aiToken = await AIToken.deploy(initialSupply);
        await aiToken.waitForDeployment();
        const aitbcTokenAddr = await aiToken.getAddress();
        deployedContracts.contracts.AIToken = aitbcTokenAddr;
        console.log(`✅ AIToken deployed: ${aitbcTokenAddr}`);

        console.log("📦 Deploying ZKReceiptVerifier...");
        const ZKReceiptVerifier = await ethers.getContractFactory("ZKReceiptVerifier");
        const zkVerifier = await ZKReceiptVerifier.deploy();
        await zkVerifier.waitForDeployment();
        const zkVerifierAddr = await zkVerifier.getAddress();
        deployedContracts.contracts.ZKReceiptVerifier = zkVerifierAddr;
        console.log(`✅ ZKReceiptVerifier deployed: ${zkVerifierAddr}`);

        console.log("📦 Deploying Groth16Verifier...");
        const Groth16Verifier = await ethers.getContractFactory("Groth16Verifier");
        const groth16Verifier = await Groth16Verifier.deploy();
        await groth16Verifier.waitForDeployment();
        const groth16VerifierAddr = await groth16Verifier.getAddress();
        deployedContracts.contracts.Groth16Verifier = groth16VerifierAddr;
        console.log(`✅ Groth16Verifier deployed: ${groth16VerifierAddr}`);

        // Deploy core contracts with correct arguments
        console.log("📦 Deploying AgentWallet...");
        const AgentWallet = await ethers.getContractFactory("AgentWallet");
        const agentWallet = await AgentWallet.deploy(aitbcTokenAddr);
        await agentWallet.waitForDeployment();
        const agentWalletAddr = await agentWallet.getAddress();
        deployedContracts.contracts.AgentWallet = agentWalletAddr;
        console.log(`✅ AgentWallet deployed: ${agentWalletAddr}`);
        
        console.log("📦 Deploying AIPowerRental...");
        const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
        const aiPowerRental = await AIPowerRental.deploy(
            aitbcTokenAddr,
            zkVerifierAddr,
            groth16VerifierAddr
        );
        await aiPowerRental.waitForDeployment();
        const aiPowerRentalAddr = await aiPowerRental.getAddress();
        deployedContracts.contracts.AIPowerRental = aiPowerRentalAddr;
        console.log(`✅ AIPowerRental deployed: ${aiPowerRentalAddr}`);
        
        console.log("📦 Deploying PerformanceVerifier...");
        const PerformanceVerifier = await ethers.getContractFactory("PerformanceVerifier");
        const performanceVerifier = await PerformanceVerifier.deploy(
            zkVerifierAddr,
            groth16VerifierAddr,
            aiPowerRentalAddr
        );
        await performanceVerifier.waitForDeployment();
        const performanceVerifierAddr = await performanceVerifier.getAddress();
        deployedContracts.contracts.PerformanceVerifier = performanceVerifierAddr;
        console.log(`✅ PerformanceVerifier deployed: ${performanceVerifierAddr}`);

        console.log("📦 Deploying AgentBounty...");
        const AgentBounty = await ethers.getContractFactory("AgentBounty");
        const agentBounty = await AgentBounty.deploy(
            aitbcTokenAddr,
            performanceVerifierAddr
        );
        await agentBounty.waitForDeployment();
        const agentBountyAddr = await agentBounty.getAddress();
        deployedContracts.contracts.AgentBounty = agentBountyAddr;
        console.log(`✅ AgentBounty deployed: ${agentBountyAddr}`);
        
        console.log("📦 Deploying DynamicPricing...");
        const DynamicPricing = await ethers.getContractFactory("DynamicPricing");
        const dynamicPricing = await DynamicPricing.deploy(
            aiPowerRentalAddr,
            performanceVerifierAddr,
            aitbcTokenAddr
        );
        await dynamicPricing.waitForDeployment();
        const dynamicPricingAddr = await dynamicPricing.getAddress();
        deployedContracts.contracts.DynamicPricing = dynamicPricingAddr;
        console.log(`✅ DynamicPricing deployed: ${dynamicPricingAddr}`);
        
        console.log("📦 Deploying AgentStaking...");
        const AgentStaking = await ethers.getContractFactory("AgentStaking");
        const agentStaking = await AgentStaking.deploy(
            aitbcTokenAddr,
            performanceVerifierAddr
        );
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
