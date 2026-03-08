const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🔍 Verifying OpenClaw Autonomous Economics Contracts");
    console.log("==============================================");
    
    const networkName = hre.network.name;
    const deploymentFile = `deployed-contracts-${networkName}.json`;
    
    // Check if deployment file exists
    if (!fs.existsSync(deploymentFile)) {
        console.error(`❌ Deployment file not found: ${deploymentFile}`);
        console.log("Please run the deployment script first.");
        process.exit(1);
    }
    
    // Load deployment information
    const deployedContracts = JSON.parse(fs.readFileSync(deploymentFile, 'utf8'));
    
    console.log(`Network: ${networkName}`);
    console.log(`Deployer: ${deployedContracts.deployer}`);
    console.log(`Timestamp: ${deployedContracts.timestamp}`);
    console.log("");
    
    // Check if Etherscan API key is configured
    const etherscanApiKey = process.env.ETHERSCAN_API_KEY;
    if (!etherscanApiKey) {
        console.warn("⚠️  ETHERSCAN_API_KEY not configured");
        console.log("Set ETHERSCAN_API_KEY in your .env file for automatic verification");
        console.log("Skipping verification...");
        return;
    }
    
    const contracts = [
        {
            name: "AgentWallet",
            address: deployedContracts.contracts.AgentWallet?.address,
            constructorArgs: [
                deployedContracts.contracts.AITBCToken?.address,
                deployedContracts.contracts.AITBCPaymentProcessor?.address
            ]
        },
        {
            name: "AgentOrchestration",
            address: deployedContracts.contracts.AgentOrchestration?.address,
            constructorArgs: []
        },
        {
            name: "AIPowerRental",
            address: deployedContracts.contracts.AIPowerRental?.address,
            constructorArgs: [
                deployedContracts.contracts.AITBCToken?.address
            ]
        },
        {
            name: "AITBCToken",
            address: deployedContracts.contracts.AITBCToken?.address,
            constructorArgs: [
                "AITBC Token",
                "AITBC",
                "1000000000000000000000000"
            ]
        },
        {
            name: "AITBCPaymentProcessor",
            address: deployedContracts.contracts.AITBCPaymentProcessor?.address,
            constructorArgs: [
                deployedContracts.contracts.AITBCToken?.address
            ]
        }
    ];
    
    console.log(`Found ${contracts.length} contracts to verify`);
    console.log("");
    
    let verificationResults = {
        verified: [],
        failed: [],
        skipped: []
    };
    
    for (const contract of contracts) {
        if (!contract.address) {
            console.log(`⏭️  Skipping ${contract.name} - no address found`);
            verificationResults.skipped.push({
                name: contract.name,
                reason: "No address found"
            });
            continue;
        }
        
        console.log(`🔍 Verifying ${contract.name} at ${contract.address}...`);
        
        try {
            // Wait for a few seconds to ensure the contract is properly deployed
            await new Promise(resolve => setTimeout(resolve, 5000));
            
            // Verify the contract
            await hre.run("verify:verify", {
                address: contract.address,
                constructorArgs: contract.constructorArgs
            });
            
            console.log(`✅ ${contract.name} verified successfully`);
            verificationResults.verified.push({
                name: contract.name,
                address: contract.address,
                etherscanUrl: `https://${networkName === "mainnet" ? "" : networkName + "."}etherscan.io/address/${contract.address}`
            });
            
        } catch (error) {
            console.error(`❌ Failed to verify ${contract.name}:`, error.message);
            
            // Check if it's already verified
            if (error.message.includes("Already Verified") || error.message.includes("already verified")) {
                console.log(`✅ ${contract.name} is already verified`);
                verificationResults.verified.push({
                    name: contract.name,
                    address: contract.address,
                    etherscanUrl: `https://${networkName === "mainnet" ? "" : networkName + "."}etherscan.io/address/${contract.address}`,
                    alreadyVerified: true
                });
            } else {
                verificationResults.failed.push({
                    name: contract.name,
                    address: contract.address,
                    error: error.message
                });
            }
        }
        
        // Add delay between verifications to avoid rate limiting
        await new Promise(resolve => setTimeout(resolve, 3000));
    }
    
    console.log("");
    console.log("🎉 VERIFICATION SUMMARY");
    console.log("=======================");
    console.log(`✅ Verified: ${verificationResults.verified.length}`);
    console.log(`❌ Failed: ${verificationResults.failed.length}`);
    console.log(`⏭️  Skipped: ${verificationResults.skipped.length}`);
    console.log("");
    
    // Show verification results
    if (verificationResults.verified.length > 0) {
        console.log("✅ Successfully Verified Contracts:");
        verificationResults.verified.forEach(contract => {
            const status = contract.alreadyVerified ? "(Already Verified)" : "";
            console.log(`  ${contract.name}: ${contract.etherscanUrl} ${status}`);
        });
    }
    
    if (verificationResults.failed.length > 0) {
        console.log("");
        console.log("❌ Failed Verifications:");
        verificationResults.failed.forEach(contract => {
            console.log(`  ${contract.name}: ${contract.error}`);
        });
        console.log("");
        console.log("💡 Tips for failed verifications:");
        console.log("  1. Wait a few minutes and try again");
        console.log("  2. Check if the contract address is correct");
        console.log("  3. Verify constructor arguments match exactly");
        console.log("  4. Check Etherscan API rate limits");
    }
    
    if (verificationResults.skipped.length > 0) {
        console.log("");
        console.log("⏭️  Skipped Contracts:");
        verificationResults.skipped.forEach(contract => {
            console.log(`  ${contract.name}: ${contract.reason}`);
        });
    }
    
    // Save verification results
    const verificationReport = {
        timestamp: new Date().toISOString(),
        network: networkName,
        results: verificationResults,
        summary: {
            total: contracts.length,
            verified: verificationResults.verified.length,
            failed: verificationResults.failed.length,
            skipped: verificationResults.skipped.length
        }
    };
    
    const reportFile = `agent-contract-verification-${networkName}-${Date.now()}.json`;
    fs.writeFileSync(
        path.join(__dirname, "..", reportFile),
        JSON.stringify(verificationReport, null, 2)
    );
    
    console.log(`📄 Verification report saved to: ${reportFile}`);
    
    // Return appropriate exit code
    if (verificationResults.failed.length > 0) {
        console.log("");
        console.log("⚠️  Some contracts failed verification");
        console.log("Please check the errors above and try manual verification if needed");
        process.exit(1);
    } else {
        console.log("");
        console.log("🎉 All contracts verified successfully!");
        process.exit(0);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
