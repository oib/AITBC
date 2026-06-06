const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🚀 Deploying AITBC Developer Ecosystem Contracts");
    console.log("==============================================");
    
    const network = network.name;
    const [deployer] = await ethers.getSigners();
    
    console.log(`Deploying contracts to ${network} with account: ${deployer.address}`);
    console.log(`Account balance: ${ethers.utils.formatEther(await deployer.getBalance())} ETH`);
    console.log("");
    
    // Deployed contracts storage
    const deployedContracts = {
        network: network,
        deployer: deployer.address,
        timestamp: new Date().toISOString(),
        contracts: {}
    };
    
    try {
        // Step 1: Deploy Mock AITBC Token (if not already deployed)
        console.log("📦 Step 1: Deploying AITBC Token...");
        const AITBCToken = await ethers.getContractFactory("MockERC20");
        const aitbcToken = await AITBCToken.deploy("AITBC Token", "AITBC", ethers.utils.parseEther("1000000"));
        await aitbcToken.deployed();
        
        deployedContracts.contracts.AITBCToken = {
            address: aitbcToken.address,
            deploymentHash: aitbcToken.deployTransaction.hash
        };
        
        console.log(`✅ AITBC Token deployed to: ${aitbcToken.address}`);
        console.log("");
        
        // Step 2: Deploy Mock Verifiers
        console.log("🔍 Step 2: Deploying Mock Verifiers...");
        
        // Deploy Mock ZK Verifier
        const MockZKVerifier = await ethers.getContractFactory("MockZKVerifier");
        const zkVerifier = await MockZKVerifier.deploy();
        await zkVerifier.deployed();
        
        deployedContracts.contracts.ZKVerifier = {
            address: zkVerifier.address,
            deploymentHash: zkVerifier.deployTransaction.hash
        };
        
        console.log(`✅ ZK Verifier deployed to: ${zkVerifier.address}`);
        
        // Deploy Mock Groth16 Verifier
        const MockGroth16Verifier = await ethers.getContractFactory("MockGroth16Verifier");
        const groth16Verifier = await MockGroth16Verifier.deploy();
        await groth16Verifier.deployed();
        
        deployedContracts.contracts.Groth16Verifier = {
            address: groth16Verifier.address,
            deploymentHash: groth16Verifier.deployTransaction.hash
        };
        
        console.log(`✅ Groth16 Verifier deployed to: ${groth16Verifier.address}`);
        console.log("");
        
        // Step 3: Deploy Core Developer Ecosystem Contracts
        console.log("🎯 Step 3: Deploying Core Developer Ecosystem Contracts...");
        
        // Deploy AgentBounty
        const AgentBounty = await ethers.getContractFactory("AgentBounty");
        const agentBounty = await AgentBounty.deploy(
            aitbcToken.address,
            zkVerifier.address,
            groth16Verifier.address
        );
        await agentBounty.deployed();
        
        deployedContracts.contracts.AgentBounty = {
            address: agentBounty.address,
            deploymentHash: agentBounty.deployTransaction.hash
        };
        
        console.log(`✅ AgentBounty deployed to: ${agentBounty.address}`);
        
        // Deploy AgentStaking
        const AgentStaking = await ethers.getContractFactory("AgentStaking");
        const agentStaking = await AgentStaking.deploy(aitbcToken.address);
        await agentStaking.deployed();
        
        deployedContracts.contracts.AgentStaking = {
            address: agentStaking.address,
            deploymentHash: agentStaking.deployTransaction.hash
        };
        
        console.log(`✅ AgentStaking deployed to: ${agentStaking.address}`);
        console.log("");
        
        // Step 4: Deploy Supporting Contracts
        console.log("🔧 Step 4: Deploying Supporting Contracts...");
        
        // Deploy PerformanceVerifier
        const PerformanceVerifier = await ethers.getContractFactory("PerformanceVerifier");
        const performanceVerifier = await PerformanceVerifier.deploy(
            zkVerifier.address,
            groth16Verifier.address,
            agentBounty.address
        );
        await performanceVerifier.deployed();
        
        deployedContracts.contracts.PerformanceVerifier = {
            address: performanceVerifier.address,
            deploymentHash: performanceVerifier.deployTransaction.hash
        };
        
        console.log(`✅ PerformanceVerifier deployed to: ${performanceVerifier.address}`);
        
        // Deploy DisputeResolution
        const DisputeResolution = await ethers.getContractFactory("DisputeResolution");
        const disputeResolution = await DisputeResolution.deploy(
            agentBounty.address,
            aitbcToken.address,
            performanceVerifier.address
        );
        await disputeResolution.deployed();
        
        deployedContracts.contracts.DisputeResolution = {
            address: disputeResolution.address,
            deploymentHash: disputeResolution.deployTransaction.hash
        };
        
        console.log(`✅ DisputeResolution deployed to: ${disputeResolution.address}`);
        
        // Deploy EscrowService
        const EscrowService = await ethers.getContractFactory("EscrowService");
        const escrowService = await EscrowService.deploy(
            aitbcToken.address,
            agentBounty.address,
            agentStaking.address
        );
        await escrowService.deployed();
        
        deployedContracts.contracts.EscrowService = {
            address: escrowService.address,
            deploymentHash: escrowService.deployTransaction.hash
        };
        
        console.log(`✅ EscrowService deployed to: ${escrowService.address}`);
        console.log("");
        
        // Step 5: Initialize Contracts
        console.log("⚙️ Step 5: Initializing Contracts...");
        
        // Initialize AgentBounty with owner settings
        await agentBounty.updateCreationFee(50); // 0.5%
        await agentBounty.updateSuccessFee(200); // 2%
        await agentBounty.updateDisputeFee(10); // 0.1%
        await agentBounty.updatePlatformFee(100); // 1%
        
        console.log("✅ AgentBounty initialized with fee settings");
        
        // Initialize AgentStaking with performance recorder
        await agentStaking.setPerformanceRecorder(deployer.address);
        
        console.log("✅ AgentStaking initialized with performance recorder");
        
        // Initialize PerformanceVerifier with settings
        await performanceVerifier.setMinimumAccuracy(80); // 80% minimum accuracy
        await performanceVerifier.setMaximumResponseTime(3600); // 1 hour max response time
        
        console.log("✅ PerformanceVerifier initialized with performance thresholds");
        console.log("");
        
        // Step 6: Setup Contract Interactions
        console.log("🔗 Step 6: Setting up Contract Interactions...");
        
        // Transfer some tokens to the contracts for testing
        const initialTokenAmount = ethers.utils.parseEther("10000");
        await aitbcToken.transfer(agentBounty.address, initialTokenAmount);
        await aitbcToken.transfer(escrowService.address, initialTokenAmount);
        
        console.log("✅ Initial tokens transferred to contracts");
        console.log("");
        
        // Step 7: Save Deployment Information
        console.log("💾 Step 7: Saving Deployment Information...");
        
        const deploymentFile = `deployed-contracts-${network}.json`;
        fs.writeFileSync(
            path.join(__dirname, "..", deploymentFile),
            JSON.stringify(deployedContracts, null, 2)
        );
        
        console.log(`✅ Deployment information saved to ${deploymentFile}`);
        console.log("");
        
        // Step 8: Generate Environment Variables
        console.log("📝 Step 8: Generating Environment Variables...");
        
        const envVars = `
# AITBC Developer Ecosystem - ${network.toUpperCase()} Deployment
# Generated on ${new Date().toISOString()}

# Contract Addresses
NEXT_PUBLIC_AITBC_TOKEN_ADDRESS=${aitbcToken.address}
NEXT_PUBLIC_AGENT_BOUNTY_ADDRESS=${agentBounty.address}
NEXT_PUBLIC_AGENT_STAKING_ADDRESS=${agentStaking.address}
NEXT_PUBLIC_PERFORMANCE_VERIFIER_ADDRESS=${performanceVerifier.address}
NEXT_PUBLIC_DISPUTE_RESOLUTION_ADDRESS=${disputeResolution.address}
NEXT_PUBLIC_ESCROW_SERVICE_ADDRESS=${escrowService.address}
NEXT_PUBLIC_ZK_VERIFIER_ADDRESS=${zkVerifier.address}
NEXT_PUBLIC_GROTH16_VERIFIER_ADDRESS=${groth16Verifier.address}

# Network Configuration
NEXT_PUBLIC_NETWORK_NAME=${network}
NEXT_PUBLIC_CHAIN_ID=${network.config.chainId}
NEXT_PUBLIC_RPC_URL=${network.config.url}

# Deployment Info
NEXT_PUBLIC_DEPLOYER_ADDRESS=${deployer.address}
NEXT_PUBLIC_DEPLOYMENT_TIMESTAMP=${new Date().toISOString()}
`;
        
        const envFile = `.env.${network}`;
        fs.writeFileSync(path.join(__dirname, "..", envFile), envVars);
        
        console.log(`✅ Environment variables saved to ${envFile}`);
        console.log("");
        
        // Step 9: Display Deployment Summary
        console.log("🎉 Deployment Summary");
        console.log("===================");
        console.log(`Network: ${network}`);
        console.log(`Deployer: ${deployer.address}`);
        console.log(`Total Contracts: ${Object.keys(deployedContracts.contracts).length}`);
        console.log("");
        console.log("Deployed Contracts:");
        
        for (const [name, contract] of Object.entries(deployedContracts.contracts)) {
            console.log(`  ${name}: ${contract.address}`);
        }
        console.log("");
        
        // Step 10: Verification Instructions
        if (network !== "localhost" && network !== "hardhat") {
            console.log("🔍 Contract Verification");
            console.log("=======================");
            console.log("To verify contracts on Etherscan, run:");
            console.log(`npx hardhat run scripts/verify-contracts.js --network ${network}`);
            console.log("");
        }
        
        // Step 11: Next Steps
        console.log("📋 Next Steps");
        console.log("=============");
        console.log("1. Copy environment variables to frontend application");
        console.log("2. Update API configuration with contract addresses");
        console.log("3. Deploy frontend application");
        console.log("4. Run integration tests");
        console.log("5. Monitor contract operations");
        console.log("");
        
        print_success("🎉 Developer Ecosystem deployment completed successfully!");
        
    } catch (error) {
        console.error("❌ Deployment failed:", error);
        process.exit(1);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
