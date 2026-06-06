const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🚀 Deploying Advanced Agent Features Contracts");
    console.log("=============================================");
    
    const [deployer] = await ethers.getSigners();
    const balance = await deployer.getBalance();
    
    console.log(`Deployer: ${deployer.address}`);
    console.log(`Balance: ${ethers.utils.formatEther(balance)} ETH`);
    
    if (balance.lt(ethers.utils.parseEther("1"))) {
        throw new Error("Insufficient ETH balance. Minimum 1 ETH recommended for deployment.");
    }
    
    console.log("");
    console.log("Proceeding with advanced contracts deployment...");
    
    // Deployment configuration
    const deployedContracts = {
        network: hre.network.name,
        deployer: deployer.address,
        timestamp: new Date().toISOString(),
        contracts: {}
    };
    
    try {
        // Get existing contracts
        let aitbcTokenAddress, paymentProcessorAddress, agentWalletAddress, aiPowerRentalAddress;
        
        try {
            const existingContractsFile = `deployed-contracts-${hre.network.name}.json`;
            if (fs.existsSync(existingContractsFile)) {
                const existingContracts = JSON.parse(fs.readFileSync(existingContractsFile, 'utf8'));
                aitbcTokenAddress = existingContracts.contracts.AITBCToken?.address;
                paymentProcessorAddress = existingContracts.contracts.AITBCPaymentProcessor?.address;
                agentWalletAddress = existingContracts.contracts.AgentWallet?.address;
                aiPowerRentalAddress = existingContracts.contracts.AIPowerRental?.address;
            }
        } catch (error) {
            console.log("Could not load existing contracts, deploying mock ones...");
        }
        
        // Deploy Mock ERC20 if needed
        if (!aitbcTokenAddress) {
            console.log("📦 Deploying mock AITBC token...");
            const MockERC20 = await ethers.getContractFactory("MockERC20");
            const aitbcToken = await MockERC20.deploy(
                "AITBC Token",
                "AITBC",
                ethers.utils.parseEther("1000000")
            );
            await aitbcToken.deployed();
            aitbcTokenAddress = aitbcToken.address;
            
            deployedContracts.contracts.AITBCToken = {
                address: aitbcTokenAddress,
                deploymentHash: aitbcToken.deployTransaction.hash,
                gasUsed: (await aitbcToken.deployTransaction.wait()).gasUsed.toString()
            };
            
            console.log(`✅ AITBC Token: ${aitbcTokenAddress}`);
        }
        
        // Deploy Mock Payment Processor if needed
        if (!paymentProcessorAddress) {
            console.log("📦 Deploying mock AITBC Payment Processor...");
            const MockPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
            const paymentProcessor = await MockPaymentProcessor.deploy(aitbcTokenAddress);
            await paymentProcessor.deployed();
            paymentProcessorAddress = paymentProcessor.address;
            
            deployedContracts.contracts.AITBCPaymentProcessor = {
                address: paymentProcessorAddress,
                deploymentHash: paymentProcessor.deployTransaction.hash,
                gasUsed: (await paymentProcessor.deployTransaction.wait()).gasUsed.toString()
            };
            
            console.log(`✅ Payment Processor: ${paymentProcessorAddress}`);
        }
        
        // Deploy CrossChainReputation contract
        console.log("📦 Deploying CrossChainReputation contract...");
        const CrossChainReputation = await ethers.getContractFactory("CrossChainReputation");
        const crossChainReputation = await CrossChainReputation.deploy();
        await crossChainReputation.deployed();
        
        deployedContracts.contracts.CrossChainReputation = {
            address: crossChainReputation.address,
            deploymentHash: crossChainReputation.deployTransaction.hash,
            gasUsed: (await crossChainReputation.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ CrossChainReputation: ${crossChainReputation.address}`);
        
        // Deploy AgentCommunication contract
        console.log("📦 Deploying AgentCommunication contract...");
        const AgentCommunication = await ethers.getContractFactory("AgentCommunication");
        const agentCommunication = await AgentCommunication.deploy(crossChainReputation.address);
        await agentCommunication.deployed();
        
        deployedContracts.contracts.AgentCommunication = {
            address: agentCommunication.address,
            deploymentHash: agentCommunication.deployTransaction.hash,
            gasUsed: (await agentCommunication.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentCommunication: ${agentCommunication.address}`);
        
        // Deploy AgentCollaboration contract
        console.log("📦 Deploying AgentCollaboration contract...");
        const AgentCollaboration = await ethers.getContractFactory("AgentCollaboration");
        const agentCollaboration = await AgentCollaboration.deploy(
            aitbcTokenAddress,
            crossChainReputation.address,
            agentCommunication.address
        );
        await agentCollaboration.deployed();
        
        deployedContracts.contracts.AgentCollaboration = {
            address: agentCollaboration.address,
            deploymentHash: agentCollaboration.deployTransaction.hash,
            gasUsed: (await agentCollaboration.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentCollaboration: ${agentCollaboration.address}`);
        
        // Deploy AgentLearning contract
        console.log("📦 Deploying AgentLearning contract...");
        const AgentLearning = await ethers.getContractFactory("AgentLearning");
        const agentLearning = await AgentLearning.deploy(
            crossChainReputation.address,
            agentCollaboration.address
        );
        await agentLearning.deployed();
        
        deployedContracts.contracts.AgentLearning = {
            address: agentLearning.address,
            deploymentHash: agentLearning.deployTransaction.hash,
            gasUsed: (await agentLearning.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentLearning: ${agentLearning.address}`);
        
        // Deploy AgentMarketplaceV2 contract
        console.log("📦 Deploying AgentMarketplaceV2 contract...");
        const AgentMarketplaceV2 = await ethers.getContractFactory("AgentMarketplaceV2");
        const agentMarketplaceV2 = await AgentMarketplaceV2.deploy(
            aitbcTokenAddress,
            paymentProcessorAddress,
            crossChainReputation.address,
            agentCommunication.address,
            agentCollaboration.address,
            agentLearning.address
        );
        await agentMarketplaceV2.deployed();
        
        deployedContracts.contracts.AgentMarketplaceV2 = {
            address: agentMarketplaceV2.address,
            deploymentHash: agentMarketplaceV2.deployTransaction.hash,
            gasUsed: (await agentMarketplaceV2.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentMarketplaceV2: ${agentMarketplaceV2.address}`);
        
        // Deploy ReputationNFT contract
        console.log("📦 Deploying ReputationNFT contract...");
        const ReputationNFT = await ethers.getContractFactory("ReputationNFT");
        const reputationNFT = await ReputationNFT.deploy(
            "AITBC Reputation NFT",
            "AITBC-RNFT",
            crossChainReputation.address
        );
        await reputationNFT.deployed();
        
        deployedContracts.contracts.ReputationNFT = {
            address: reputationNFT.address,
            deploymentHash: reputationNFT.deployTransaction.hash,
            gasUsed: (await reputationNFT.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ ReputationNFT: ${reputationNFT.address}`);
        
        // Initialize contracts
        console.log("🔧 Initializing contracts...");
        
        // Initialize CrossChainReputation
        await crossChainReputation.updateGlobalSettings(
            1000, // baseReputationScore
            100,  // successBonus
            50,   // failurePenalty
            ethers.utils.parseEther("100"), // minStakeAmount
            10000, // maxDelegationRatio (100%)
            3600   // syncCooldown (1 hour)
        );
        console.log("✅ CrossChainReputation initialized");
        
        // Initialize AgentCommunication
        await agentCommunication.updateGlobalSettings(
            1000, // minReputationScore
            ethers.utils.parseEther("0.001"), // baseMessagePrice
            100000, // maxMessageSize (100KB)
            86400,  // messageTimeout (24 hours)
            2592000 // channelTimeout (30 days)
        );
        console.log("✅ AgentCommunication initialized");
        
        // Authorize deployer as agent
        await crossChainReputation.initializeReputation(deployer.address, 1000);
        await agentCommunication.authorizeAgent(deployer.address);
        await agentCollaboration.authorizeAgent(deployer.address);
        await agentLearning.authorizeAgent(deployer.address);
        console.log("✅ Deployer authorized as agent");
        
        // Add supported chains to CrossChainReputation
        await crossChainReputation.addSupportedChain(1, crossChainReputation.address); // Ethereum
        await crossChainReputation.addSupportedChain(137, crossChainReputation.address); // Polygon
        await crossChainReputation.addSupportedChain(42161, crossChainReputation.address); // Arbitrum
        await crossChainReputation.addSupportedChain(10, crossChainReputation.address); // Optimism
        console.log("✅ Supported chains added to CrossChainReputation");
        
        // Save deployment information
        const deploymentFile = `deployed-contracts-${hre.network.name}.json`;
        
        // Load existing contracts if file exists
        let existingContracts = {};
        if (fs.existsSync(deploymentFile)) {
            existingContracts = JSON.parse(fs.readFileSync(deploymentFile, 'utf8'));
        }
        
        // Merge with existing contracts
        const allContracts = {
            ...existingContracts,
            ...deployedContracts
        };
        
        fs.writeFileSync(
            path.join(__dirname, "..", deploymentFile),
            JSON.stringify(allContracts, null, 2)
        );
        
        // Generate environment variables for frontend
        const envVars = `
# AITBC Advanced Agent Features - ${hre.network.name.toUpperCase()}
# Generated on ${new Date().toISOString()}

# Advanced Contract Addresses
VITE_CROSS_CHAIN_REPUTATION_ADDRESS=${crossChainReputation.address}
VITE_AGENT_COMMUNICATION_ADDRESS=${agentCommunication.address}
VITE_AGENT_COLLABORATION_ADDRESS=${agentCollaboration.address}
VITE_AGENT_LEARNING_ADDRESS=${agentLearning.address}
VITE_AGENT_MARKETPLACE_V2_ADDRESS=${agentMarketplaceV2.address}
VITE_REPUTATION_NFT_ADDRESS=${reputationNFT.address}

# Network Configuration
VITE_NETWORK_NAME=${hre.network.name}
VITE_CHAIN_ID=${hre.network.config.chainId || 1}
VITE_RPC_URL=${hre.network.config.url || 'http://localhost:8545'}

# Advanced Features Configuration
VITE_MIN_REPUTATION_SCORE=1000
VITE_BASE_MESSAGE_PRICE=0.001
VITE_MAX_MESSAGE_SIZE=100000
VITE_MESSAGE_TIMEOUT=86400
VITE_CHANNEL_TIMEOUT=2592000
VITE_MAX_MODEL_SIZE=104857600
VITE_MAX_TRAINING_TIME=3600
VITE_DEFAULT_LEARNING_RATE=0.001
VITE_CONVERGENCE_THRESHOLD=0.001
VITE_SYNC_COOLDOWN=3600
VITE_MIN_STAKE_AMOUNT=100000000000000000000
VITE_MAX_DELEGATION_RATIO=1.0
`;
        
        const envFile = path.join(__dirname, "..", "..", "apps", "marketplace-web", ".env.advanced-features");
        fs.writeFileSync(envFile, envVars);
        
        console.log("");
        console.log("🎉 ADVANCED CONTRACTS DEPLOYMENT COMPLETED");
        console.log("=====================================");
        console.log(`Total gas used: ${calculateTotalGas(deployedContracts)}`);
        console.log(`Deployment file: ${deploymentFile}`);
        console.log(`Environment file: ${envFile}`);
        console.log("");
        console.log("📋 Contract Addresses:");
        console.log(`  CrossChainReputation: ${crossChainReputation.address}`);
        console.log(`  AgentCommunication: ${agentCommunication.address}`);
        console.log(`  AgentCollaboration: ${agentCollaboration.address}`);
        console.log(`  AgentLearning: ${agentLearning.address}`);
        console.log(`  AgentMarketplaceV2: ${agentMarketplaceV2.address}`);
        console.log(`  ReputationNFT: ${reputationNFT.address}`);
        console.log("");
        console.log("🔧 Next Steps:");
        console.log("  1. Verify contracts on Etherscan (if on testnet/mainnet)");
        console.log("  2. Initialize cross-chain reputation for agents");
        console.log("  3. Set up agent communication channels");
        console.log("  4. Configure advanced learning models");
        console.log("  5. Test agent collaboration protocols");
        
    } catch (error) {
        console.error("❌ Deployment failed:", error);
        process.exit(1);
    }
}

function calculateTotalGas(deployedContracts) {
    let totalGas = 0;
    for (const contract of Object.values(deployedContracts.contracts)) {
        if (contract.gasUsed) {
            totalGas += parseInt(contract.gasUsed);
        }
    }
    return totalGas.toLocaleString();
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
