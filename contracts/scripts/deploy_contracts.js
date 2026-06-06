const { ethers } = require("hardhat");

async function main() {
    console.log("=== AITBC Smart Contract Deployment ===");
    
    // Get deployer account
    const [deployer] = await ethers.getSigners();
    console.log("Deploying contracts with the account:", deployer.address);
    console.log("Account balance:", (await deployer.getBalance()).toString());

    // Deployment addresses (to be replaced with actual addresses)
    const AITBC_TOKEN_ADDRESS = process.env.AITBC_TOKEN_ADDRESS || "0x0000000000000000000000000000000000000000";
    const ZK_VERIFIER_ADDRESS = process.env.ZK_VERIFIER_ADDRESS || "0x0000000000000000000000000000000000000000";
    const GROTH16_VERIFIER_ADDRESS = process.env.GROTH16_VERIFIER_ADDRESS || "0x0000000000000000000000000000000000000000";

    try {
        // 1. Deploy AI Power Rental Contract
        console.log("\n1. Deploying AIPowerRental...");
        const AIPowerRental = await ethers.getContractFactory("AIPowerRental");
        const aiPowerRental = await AIPowerRental.deploy(
            AITBC_TOKEN_ADDRESS,
            ZK_VERIFIER_ADDRESS,
            GROTH16_VERIFIER_ADDRESS
        );
        await aiPowerRental.deployed();
        console.log("AIPowerRental deployed to:", aiPowerRental.address);

        // 2. Deploy AITBC Payment Processor
        console.log("\n2. Deploying AITBCPaymentProcessor...");
        const AITBCPaymentProcessor = await ethers.getContractFactory("AITBCPaymentProcessor");
        const paymentProcessor = await AITBCPaymentProcessor.deploy(
            AITBC_TOKEN_ADDRESS,
            aiPowerRental.address
        );
        await paymentProcessor.deployed();
        console.log("AITBCPaymentProcessor deployed to:", paymentProcessor.address);

        // 3. Deploy Performance Verifier
        console.log("\n3. Deploying PerformanceVerifier...");
        const PerformanceVerifier = await ethers.getContractFactory("PerformanceVerifier");
        const performanceVerifier = await PerformanceVerifier.deploy(
            ZK_VERIFIER_ADDRESS,
            GROTH16_VERIFIER_ADDRESS,
            aiPowerRental.address
        );
        await performanceVerifier.deployed();
        console.log("PerformanceVerifier deployed to:", performanceVerifier.address);

        // 4. Deploy Dispute Resolution
        console.log("\n4. Deploying DisputeResolution...");
        const DisputeResolution = await ethers.getContractFactory("DisputeResolution");
        const disputeResolution = await DisputeResolution.deploy(
            aiPowerRental.address,
            paymentProcessor.address,
            performanceVerifier.address
        );
        await disputeResolution.deployed();
        console.log("DisputeResolution deployed to:", disputeResolution.address);

        // 5. Deploy Escrow Service
        console.log("\n5. Deploying EscrowService...");
        const EscrowService = await ethers.getContractFactory("EscrowService");
        const escrowService = await EscrowService.deploy(
            AITBC_TOKEN_ADDRESS,
            aiPowerRental.address,
            paymentProcessor.address
        );
        await escrowService.deployed();
        console.log("EscrowService deployed to:", escrowService.address);

        // 6. Deploy Dynamic Pricing
        console.log("\n6. Deploying DynamicPricing...");
        const DynamicPricing = await ethers.getContractFactory("DynamicPricing");
        const dynamicPricing = await DynamicPricing.deploy(
            aiPowerRental.address,
            performanceVerifier.address,
            AITBC_TOKEN_ADDRESS
        );
        await dynamicPricing.deployed();
        console.log("DynamicPricing deployed to:", dynamicPricing.address);

        // Initialize contracts with cross-references
        console.log("\n7. Initializing contract cross-references...");
        
        // Set payment processor in AI Power Rental
        await aiPowerRental.setPaymentProcessor(paymentProcessor.address);
        console.log("Payment processor set in AIPowerRental");

        // Set performance verifier in AI Power Rental
        await aiPowerRental.setPerformanceVerifier(performanceVerifier.address);
        console.log("Performance verifier set in AIPowerRental");

        // Set dispute resolver in payment processor
        await paymentProcessor.setDisputeResolver(disputeResolution.address);
        console.log("Dispute resolver set in PaymentProcessor");

        // Set escrow service in payment processor
        await paymentProcessor.setEscrowService(escrowService.address);
        console.log("Escrow service set in PaymentProcessor");

        // Authorize initial oracles and arbiters
        console.log("\n8. Setting up initial oracles and arbiters...");
        
        // Authorize deployer as price oracle
        await dynamicPricing.authorizePriceOracle(deployer.address);
        console.log("Deployer authorized as price oracle");

        // Authorize deployer as performance oracle
        await performanceVerifier.authorizeOracle(deployer.address);
        console.log("Deployer authorized as performance oracle");

        // Authorize deployer as arbitrator
        await disputeResolution.authorizeArbitrator(deployer.address);
        console.log("Deployer authorized as arbitrator");

        // Authorize deployer as escrow arbiter
        await escrowService.authorizeArbiter(deployer.address);
        console.log("Deployer authorized as escrow arbiter");

        // Save deployment addresses
        const deploymentInfo = {
            network: network.name,
            deployer: deployer.address,
            timestamp: new Date().toISOString(),
            contracts: {
                AITBC_TOKEN_ADDRESS,
                ZK_VERIFIER_ADDRESS,
                GROTH16_VERIFIER_ADDRESS,
                AIPowerRental: aiPowerRental.address,
                AITBCPaymentProcessor: paymentProcessor.address,
                PerformanceVerifier: performanceVerifier.address,
                DisputeResolution: disputeResolution.address,
                EscrowService: escrowService.address,
                DynamicPricing: dynamicPricing.address
            }
        };

        // Write deployment info to file
        const fs = require('fs');
        fs.writeFileSync(
            `deployment-${network.name}-${Date.now()}.json`,
            JSON.stringify(deploymentInfo, null, 2)
        );

        console.log("\n=== Deployment Summary ===");
        console.log("All contracts deployed successfully!");
        console.log("Deployment info saved to deployment file");
        console.log("\nContract Addresses:");
        console.log("- AIPowerRental:", aiPowerRental.address);
        console.log("- AITBCPaymentProcessor:", paymentProcessor.address);
        console.log("- PerformanceVerifier:", performanceVerifier.address);
        console.log("- DisputeResolution:", disputeResolution.address);
        console.log("- EscrowService:", escrowService.address);
        console.log("- DynamicPricing:", dynamicPricing.address);

        console.log("\n=== Next Steps ===");
        console.log("1. Update environment variables with contract addresses");
        console.log("2. Run integration tests");
        console.log("3. Configure marketplace API to use new contracts");
        console.log("4. Perform security audit");

    } catch (error) {
        console.error("Deployment failed:", error);
        process.exit(1);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
