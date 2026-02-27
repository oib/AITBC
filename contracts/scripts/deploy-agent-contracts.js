const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🚀 Deploying OpenClaw Autonomous Economics Contracts");
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
        // Get existing contracts
        let aitbcTokenAddress, paymentProcessorAddress, aiPowerRentalAddress;
        
        try {
            const existingContractsFile = `deployed-contracts-${hre.network.name}.json`;
            if (fs.existsSync(existingContractsFile)) {
                const existingContracts = JSON.parse(fs.readFileSync(existingContractsFile, 'utf8'));
                aitbcTokenAddress = existingContracts.contracts.AITBCToken?.address;
                paymentProcessorAddress = existingContracts.contracts.AITBCPaymentProcessor?.address;
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
        
        // Deploy AgentWallet contract
        console.log("📦 Deploying AgentWallet contract...");
        const AgentWallet = await ethers.getContractFactory("AgentWallet");
        const agentWallet = await AgentWallet.deploy(
            aitbcTokenAddress,
            paymentProcessorAddress
        );
        await agentWallet.deployed();
        
        deployedContracts.contracts.AgentWallet = {
            address: agentWallet.address,
            deploymentHash: agentWallet.deployTransaction.hash,
            gasUsed: (await agentWallet.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentWallet: ${agentWallet.address}`);
        
        // Deploy AgentOrchestration contract
        console.log("📦 Deploying AgentOrchestration contract...");
        const AgentOrchestration = await ethers.getContractFactory("AgentOrchestration");
        const agentOrchestration = await AgentOrchestration.deploy();
        await agentOrchestration.deployed();
        
        deployedContracts.contracts.AgentOrchestration = {
            address: agentOrchestration.address,
            deploymentHash: agentOrchestration.deployTransaction.hash,
            gasUsed: (await agentOrchestration.deployTransaction.wait()).gasUsed.toString()
        };
        
        console.log(`✅ AgentOrchestration: ${agentOrchestration.address}`);
        
        // Deploy or extend AIPowerRental contract
        if (!aiPowerRentalAddress) {
            console.log("📦 Deploying AIPowerRental contract...");
            const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
            const aiPowerRental = await AIPowerRental.deploy(
                aitbcTokenAddress
            );
            await aiPowerRental.deployed();
            aiPowerRentalAddress = aiPowerRental.address;
            
            deployedContracts.contracts.AIPowerRental = {
                address: aiPowerRentalAddress,
                deploymentHash: aiPowerRental.deployTransaction.hash,
                gasUsed: (await aiPowerRental.deployTransaction.wait()).gasUsed.toString()
            };
            
            console.log(`✅ AIPowerRental: ${aiPowerRentalAddress}`);
        } else {
            console.log(`📦 Using existing AIPowerRental: ${aiPowerRentalAddress}`);
            deployedContracts.contracts.AIPowerRental = {
                address: aiPowerRentalAddress,
                note: "Existing contract - agent features added"
            };
        }
        
        // Initialize contracts
        console.log("🔧 Initializing contracts...");
        
        // Authorize deployer as agent
        await agentWallet.authorizeAgent(deployer.address, deployer.address);
        console.log("✅ Authorized deployer as agent");
        
        // Authorize deployer as provider
        await agentWallet.authorizeProvider(deployer.address);
        console.log("✅ Authorized deployer as provider");
        
        // Authorize agent for AIPowerRental
        const aiPowerRentalContract = await ethers.getContractAt("AIPowerRental", aiPowerRentalAddress);
        await aiPowerRentalContract.authorizeAgent(deployer.address, deployer.address);
        console.log("✅ Authorized agent for AIPowerRental");
        
        // Authorize provider for AIPowerRental
        await aiPowerRentalContract.authorizeProvider(deployer.address);
        console.log("✅ Authorized provider for AIPowerRental");
        
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
# AITBC OpenClaw Autonomous Economics - ${hre.network.name.toUpperCase()}
# Generated on ${new Date().toISOString()}

# Contract Addresses
VITE_AGENT_WALLET_ADDRESS=${agentWallet.address}
VITE_AGENT_ORCHESTRATION_ADDRESS=${agentOrchestration.address}
VITE_AI_POWER_RENTAL_ADDRESS=${aiPowerRentalAddress}
VITE_AITBC_TOKEN_ADDRESS=${aitbcTokenAddress}
VITE_PAYMENT_PROCESSOR_ADDRESS=${paymentProcessorAddress}

# Network Configuration
VITE_NETWORK_NAME=${hre.network.name}
VITE_CHAIN_ID=${hre.network.config.chainId || 1}
VITE_RPC_URL=${hre.network.config.url || 'http://localhost:8545'}

# Agent Configuration
VITE_DEFAULT_SPENDING_LIMIT=1000
VITE_MICRO_TRANSACTION_THRESHOLD=0.001
VITE_MIN_ALLOWANCE=10
VITE_MAX_ALLOWANCE=100000

# Bid Strategy Configuration
VITE_MARKET_WINDOW=24
VITE_PRICE_HISTORY_DAYS=30
VITE_VOLATILITY_THRESHOLD=0.15
VITE_MAX_CONCURRENT_PLANS=10
VITE_ASSIGNMENT_TIMEOUT=300
VITE_MONITORING_INTERVAL=30
VITE_RETRY_LIMIT=3
`;
        
        const envFile = path.join(__dirname, "..", "..", "apps", "marketplace-web", ".env.agent-economics");
        fs.writeFileSync(envFile, envVars);
        
        console.log("");
        console.log("🎉 CONTRACT DEPLOYMENT COMPLETED");
        console.log("===============================");
        console.log(`Total gas used: ${calculateTotalGas(deployedContracts)}`);
        console.log(`Deployment file: ${deploymentFile}`);
        console.log(`Environment file: ${envFile}`);
        console.log("");
        console.log("📋 Contract Addresses:");
        console.log(`  AgentWallet: ${agentWallet.address}`);
        console.log(`  AgentOrchestration: ${agentOrchestration.address}`);
        console.log(`  AIPowerRental: ${aiPowerRentalAddress}`);
        console.log(`  AITBC Token: ${aitbcTokenAddress}`);
        console.log(`  Payment Processor: ${paymentProcessorAddress}`);
        console.log("");
        console.log("🔧 Next Steps:");
        console.log("  1. Verify contracts on Etherscan (if on testnet/mainnet)");
        console.log("  2. Update frontend with new contract addresses");
        console.log("  3. Test agent wallet functionality");
        console.log("  4. Initialize bid strategy engine");
        console.log("  5. Set up agent orchestrator");
        
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
