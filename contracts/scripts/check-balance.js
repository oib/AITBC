const { ethers } = require("hardhat");

async function main() {
    try {
        const [deployer] = await ethers.getSigners();
        const balance = await deployer.getBalance();
        const balanceEth = ethers.utils.formatEther(balance);
        
        console.log("💰 Deployer Account Balance");
        console.log("==========================");
        console.log(`Address: ${deployer.address}`);
        console.log(`Balance: ${balanceEth} ETH`);
        
        // Calculate USD value (assuming $2000/ETH)
        const balanceUsd = parseFloat(balanceEth) * 2000;
        console.log(`USD Value: $${balanceUsd.toFixed(2)}`);
        
        // Balance recommendations
        const minRecommended = 10; // Minimum ETH recommended for deployment
        const safeAmount = 20; // Safe amount for deployment + buffer
        
        if (parseFloat(balanceEth) >= safeAmount) {
            console.log("✅ Sufficient balance for deployment");
        } else if (parseFloat(balanceEth) >= minRecommended) {
            console.log("⚠️  Minimum balance met, but consider adding more ETH for safety");
        } else {
            console.log("❌ Insufficient balance. Minimum 10 ETH recommended for deployment");
        }
        
        // Output just the balance for script consumption
        console.log(balanceEth);
        
    } catch (error) {
        console.error("Error checking balance:", error);
        process.exit(1);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
