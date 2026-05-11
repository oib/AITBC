import hre from "hardhat";

async function main() {
  console.log("Deploying AIToken to testnet...");

  const [owner] = await hre.ethers.getSigners();
  console.log("Deploying from account:", owner.address);

  const AIToken = await hre.ethers.getContractFactory("AIToken");
  const initialSupply = hre.ethers.parseEther("1000000"); // 1 million for staging
  const token = await AIToken.deploy(initialSupply);
  
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  
  console.log("AIToken deployed to:", tokenAddress);
  
  // Verify supply cap
  const MAX_SUPPLY = await token.MAX_SUPPLY();
  console.log("MAX_SUPPLY:", hre.ethers.formatEther(MAX_SUPPLY));
  
  // Verify cooldown
  const COOLDOWN = await token.MINTING_COOLDOWN();
  console.log("MINTING_COOLDOWN:", COOLDOWN.toString());
  
  // Verify initial supply
  const totalSupply = await token.totalSupply();
  console.log("Total Supply:", hre.ethers.formatEther(totalSupply));
  
  console.log("\nDeployment successful!");
  console.log("Token Address:", tokenAddress);
  console.log("Owner Address:", owner.address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
