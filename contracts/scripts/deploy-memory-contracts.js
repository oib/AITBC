const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🚀 Deploying Decentralized Memory & Storage Contracts");
    console.log("==============================================");
    
    const [deployer] = await ethers.getSigners();
    const balance = await deployer.getBalance();
    
    console.log(`Deployer: ${deployer.address}`);
    console.log(`Balance: ${ethers.utils.formatEther(balance)} ETH`);
    
    if (balance.lt(ethers.utils.parseEther("1"))) {
        throw new Error("Insufficient ETH balance. Minimum 1 ETH recommended for deployment.");
    }
    
    console.log("");
    console.log("Proceeding with contract deployment...");
    
    // Deployment configuration
    const deployedContracts = {
        network: hre.network.name,
        deployer: deployer.address,
        timestamp: new Date().toISOString(),
        contracts: {}
    };
    
    try {
        // Deploy AgentMemory contract
        console.log("📦 Deploying AgentMemory contract...");
        const AgentMemory = await ethers.getContractFactory("AgentMemory");
        const agentMemory = await AgentMemory.deploy();
        await agentMemory.deployed();
        
        deployedContracts.contracts.AgentMemory = {
            address: agentMemory.address,
            deploymentHash: agentMemory.deployTransaction.hash,
            gasUsed: (await agentMemory.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentMemory: ${agentMemory.address}`);
        
        // Deploy MemoryVerifier contract
        console.log("📦 Deploying MemoryVerifier contract...");
        const ZKReceiptVerifier = await ethers.getContractFactory("ZKReceiptVerifier");
        const zkVerifier = await ZKReceiptVerifier.deploy();
        await zkVerifier.deployed();
        
        const MemoryVerifier = await ethers.getContractFactory("MemoryVerifier", {
            libraries: {
                ZKReceiptVerifier: zkVerifier.address
            }
        });
        const memoryVerifier = await MemoryVerifier.deploy(zkVerifier.address);
        await memoryVerifier.deployed();
        
        deployedContracts.contracts.MemoryVerifier = {
            address: memoryVerifier.address,
            deploymentHash: memoryVerifier.deployTransaction.hash,
            gasUsed: (await memoryVerifier.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ MemoryVerifier: ${memoryVerifier.address}`);
        
        // Deploy KnowledgeGraphMarket contract
        console.log("📦 Deploying KnowledgeGraphMarket contract...");
        
        // Get existing AITBCPaymentProcessor address or deploy a mock one
        let paymentProcessorAddress;
        let aitbcTokenAddress;
        
        try {
            // Try to get existing payment processor
            const paymentProcessorFile = `deployed-contracts-${hre.network.name}.json`;
            if (fs.existsSync(paymentProcessorFile)) {
                const existingContracts = JSON.parse(fs.readFileSync(paymentProcessorFile, 'utf8'));
                paymentProcessorAddress = existingContracts.contracts.AITBCPaymentProcessor?.address;
                aitbcTokenAddress = existingContracts.contracts.AITBCToken?.address;
            }
        } catch (error) {
            console.log("Could not load existing contracts, deploying mock ones...");
        }
        
        // Deploy mock AITBC token if needed
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
        
        // Deploy mock payment processor if needed
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
        
        // Deploy KnowledgeGraphMarket
        const KnowledgeGraphMarket = await ethers.getContractFactory("KnowledgeGraphMarket");
        const knowledgeGraphMarket = await KnowledgeGraphMarket.deploy(
            paymentProcessorAddress,
            aitbcTokenAddress
        );
        await knowledgeGraphMarket.deployed();
        
        deployedContracts.contracts.KnowledgeGraphMarket = {
            address: knowledgeGraphMarket.address,
            deploymentHash: knowledgeGraphMarket.deployTransaction.hash,
            gasUsed: (await knowledgeGraphMarket.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ KnowledgeGraphMarket: ${knowledgeGraphMarket.address}`);
        
        // Initialize contracts
        console.log("🔧 Initializing contracts...");
        
        // Authorize deployer as memory verifier
        await memoryVerifier.authorizeVerifier(deployer.address, 100000, 300);
        console.log("✅ Authorized deployer as memory verifier");
        
        // Save deployment information
        const deploymentFile = `deployed-contracts-${hre.network.name}.json`;
        fs.writeFileSync(
            path.join(__dirname, "..", deploymentFile),
            JSON.stringify(deployedContracts, null, 2)
        );
        
        // Generate environment variables for frontend
        const envVars = `
# AITBC Decentralized Memory & Storage - ${hre.network.name.toUpperCase()}
# Generated on ${new Date().toISOString()}

# Contract Addresses
VITE_AGENT_MEMORY_ADDRESS=${agentMemory.address}
VITE_MEMORY_VERIFIER_ADDRESS=${memoryVerifier.address}
VITE_KNOWLEDGE_GRAPH_MARKET_ADDRESS=${knowledgeGraphMarket.address}
VITE_AITBC_TOKEN_ADDRESS=${aitbcTokenAddress}
VITE_PAYMENT_PROCESSOR_ADDRESS=${paymentProcessorAddress}

# Network Configuration
VITE_NETWORK_NAME=${hre.network.name}
VITE_CHAIN_ID=${hre.network.config.chainId || 1}
VITE_RPC_URL=${hre.network.config.url || 'http://localhost:8545'}

# IPFS Configuration
VITE_IPFS_URL=http://localhost:5001
VITE_IPFS_GATEWAY_URL=http://localhost:8080/ipfs/

# Memory Configuration
VITE_MEMORY_UPLOAD_THRESHOLD=100
VITE_MEMORY_BATCH_SIZE=50
VITE_MEMORY_EXPIRY_DAYS=30
`;
        
        const envFile = path.join(__dirname, "..", "..", "apps", "marketplace-web", ".env.memory");
        fs.writeFileSync(envFile, envVars);
        
        console.log("");
        console.log("🎉 CONTRACT DEPLOYMENT COMPLETED");
        console.log("===============================");
        console.log(`Total gas used: ${calculateTotalGas(deployedContracts)}`);
        console.log(`Deployment file: ${deploymentFile}`);
        console.log(`Environment file: ${envFile}`);
        console.log("");
        console.log("📋 Contract Addresses:");
        console.log(`  AgentMemory: ${agentMemory.address}`);
        console.log(`  MemoryVerifier: ${memoryVerifier.address}`);
        console.log(`  KnowledgeGraphMarket: ${knowledgeGraphMarket.address}`);
        console.log(`  AITBC Token: ${aitbcTokenAddress}`);
        console.log(`  Payment Processor: ${paymentProcessorAddress}`);
        console.log("");
        console.log("🔧 Next Steps:");
        console.log("  1. Verify contracts on Etherscan (if on testnet/mainnet)");
        console.log("  2. Update frontend with new contract addresses");
        console.log("  3. Test contract functionality");
        console.log("  4. Set up IPFS node for storage");
        
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
