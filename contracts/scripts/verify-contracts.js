const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
    console.log("🔍 Verifying AITBC Developer Ecosystem Contracts");
    console.log("==============================================");
    
    const network = network.name;
    
    if (network === "localhost" || network === "hardhat") {
        console.log("⏭️ Skipping verification for local network");
        return;
    }
    
    // Read deployed contracts
    const deploymentFile = `deployed-contracts-${network}.json`;
    const deploymentPath = path.join(__dirname, "..", deploymentFile);
    
    if (!fs.existsSync(deploymentPath)) {
        console.error(`❌ Deployment file not found: ${deploymentFile}`);
        process.exit(1);
    }
    
    const deployedContracts = JSON.parse(fs.readFileSync(deploymentPath, "utf8"));
    
    console.log(`Network: ${network}`);
    console.log(`Contracts to verify: ${Object.keys(deployedContracts.contracts).length}`);
    console.log("");
    
    const verificationResults = {
        verified: [],
        failed: [],
        skipped: []
    };
    
    // Verification configurations for each contract
    const verificationConfigs = {
        AITBCToken: {
            constructorArguments: ["AITBC Token", "AITBC", ethers.utils.parseEther("1000000")]
        },
        ZKVerifier: {
            constructorArguments: []
        },
        Groth16Verifier: {
            constructorArguments: []
        },
        AgentBounty: {
            constructorArguments: [
                deployedContracts.contracts.AITBCToken.address,
                deployedContracts.contracts.ZKVerifier.address,
                deployedContracts.contracts.Groth16Verifier.address
            ]
        },
        AgentStaking: {
            constructorArguments: [deployedContracts.contracts.AITBCToken.address]
        },
        PerformanceVerifier: {
            constructorArguments: [
                deployedContracts.contracts.ZKVerifier.address,
                deployedContracts.contracts.Groth16Verifier.address,
                deployedContracts.contracts.AgentBounty.address
            ]
        },
        DisputeResolution: {
            constructorArguments: [
                deployedContracts.contracts.AgentBounty.address,
                deployedContracts.contracts.AITBCToken.address,
                deployedContracts.contracts.PerformanceVerifier.address
            ]
        },
        EscrowService: {
            constructorArguments: [
                deployedContracts.contracts.AITBCToken.address,
                deployedContracts.contracts.AgentBounty.address,
                deployedContracts.contracts.AgentStaking.address
            ]
        }
    };
    
    // Verify each contract
    for (const [contractName, contractInfo] of Object.entries(deployedContracts.contracts)) {
        console.log(`🔍 Verifying ${contractName}...`);
        
        try {
            const config = verificationConfigs[contractName];
            if (!config) {
                console.log(`⏭️ Skipping ${contractName} (no verification config)`);
                verificationResults.skipped.push(contractName);
                continue;
            }
            
            // Wait for a few block confirmations
            console.log(`⏳ Waiting for block confirmations...`);
            await ethers.provider.waitForTransaction(contractInfo.deploymentHash, 3);
            
            // Verify contract
            await hre.run("verify:verify", {
                address: contractInfo.address,
                constructorArguments: config.constructorArguments
            });
            
            console.log(`✅ ${contractName} verified successfully`);
            verificationResults.verified.push(contractName);
            
        } catch (error) {
            if (error.message.includes("Already Verified")) {
                console.log(`✅ ${contractName} already verified`);
                verificationResults.verified.push(contractName);
            } else {
                console.log(`❌ ${contractName} verification failed: ${error.message}`);
                verificationResults.failed.push({
                    contract: contractName,
                    error: error.message
                });
            }
        }
        
        // Add delay between verifications to avoid rate limiting
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    console.log("");
    console.log("📊 Verification Summary");
    console.log("======================");
    console.log(`Verified: ${verificationResults.verified.length}`);
    console.log(`Failed: ${verificationResults.failed.length}`);
    console.log(`Skipped: ${verificationResults.skipped.length}`);
    console.log("");
    
    if (verificationResults.verified.length > 0) {
        console.log("✅ Verified Contracts:");
        verificationResults.verified.forEach(name => {
            console.log(`  - ${name}: ${deployedContracts.contracts[name].address}`);
        });
        console.log("");
    }
    
    if (verificationResults.failed.length > 0) {
        console.log("❌ Failed Verifications:");
        verificationResults.failed.forEach(({ contract, error }) => {
            console.log(`  - ${contract}: ${error}`);
        });
        console.log("");
    }
    
    if (verificationResults.skipped.length > 0) {
        console.log("⏭️ Skipped Verifications:");
        verificationResults.skipped.forEach(name => {
            console.log(`  - ${name}`);
        });
        console.log("");
    }
    
    // Save verification results
    const verificationResultsFile = `verification-results-${network}.json`;
    fs.writeFileSync(
        path.join(__dirname, "..", verificationResultsFile),
        JSON.stringify({
            network: network,
            timestamp: new Date().toISOString(),
            results: verificationResults
        }, null, 2)
    );
    
    console.log(`📄 Verification results saved to ${verificationResultsFile}`);
    console.log("");
    
    if (verificationResults.failed.length > 0) {
        console.log("⚠️ Some contracts failed verification. Check the logs above.");
        process.exit(1);
    } else {
        console.log("🎉 All contracts verified successfully!");
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
