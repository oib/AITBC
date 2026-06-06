const { ethers } = require("hardhat");

async function main() {
    try {
        // Get current gas price
        const gasPrice = await ethers.provider.getGasPrice();
        const gasPriceGwei = ethers.utils.formatUnits(gasPrice, "gwei");
        
        // Get gas limit estimates
        const block = await ethers.provider.getBlock("latest");
        const baseFeePerGas = block.baseFeePerGas ? ethers.utils.formatUnits(block.baseFeePerGas, "gwei") : "N/A";
        
        // Calculate estimated deployment costs
        const estimatedGasLimit = 8000000; // Estimated total gas for all contracts
        const estimatedCostEth = parseFloat(gasPriceGwei) * estimatedGasLimit / 1e9;
        
        console.log("🔍 Mainnet Gas Analysis");
        console.log("======================");
        console.log(`Current Gas Price: ${gasPriceGwei} gwei`);
        console.log(`Base Fee: ${baseFeePerGas} gwei`);
        console.log(`Estimated Deployment Cost: ${estimatedCostEth.toFixed(4)} ETH`);
        console.log(`Estimated Deployment Cost: $${(estimatedCostEth * 2000).toFixed(2)} USD (assuming $2000/ETH)`);
        
        // Gas price recommendations
        if (parseFloat(gasPriceGwei) < 20) {
            console.log("✅ Gas price is LOW - Good time to deploy");
        } else if (parseFloat(gasPriceGwei) < 50) {
            console.log("⚠️  Gas price is MODERATE - Consider waiting if possible");
        } else {
            console.log("❌ Gas price is HIGH - Consider waiting for lower gas");
        }
        
        // Output just the gas price for script consumption
        console.log(gasPriceGwei);
        
    } catch (error) {
        console.error("Error checking gas price:", error);
        process.exit(1);
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
