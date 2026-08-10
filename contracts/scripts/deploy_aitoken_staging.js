import { network as hardhatNetwork } from "hardhat";
const connection = await hardhatNetwork.getOrCreate();
const { ethers } = connection;

async function main() {
  console.log("Deploying AIToken to testnet...");

  const [owner] = await ethers.getSigners();
  console.log("Deploying from account:", owner.address);

  const AIToken = await ethers.getContractFactory("AIToken");
  const initialSupply = ethers.parseEther("1000000"); // 1 million for staging
  const token = await AIToken.deploy(initialSupply);

  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();

  console.log("AIToken deployed to:", tokenAddress);

  // Verify supply cap
  const MAX_SUPPLY = await token.MAX_SUPPLY();
  console.log("MAX_SUPPLY:", ethers.formatEther(MAX_SUPPLY));

  // Verify cooldown
  const COOLDOWN = await token.MINTING_COOLDOWN();
  console.log("MINTING_COOLDOWN:", COOLDOWN.toString());

  // Verify initial supply
  const totalSupply = await token.totalSupply();
  console.log("Total Supply:", ethers.formatEther(totalSupply));

  console.log("\nDeployment successful!");
  console.log("Token Address:", tokenAddress);
  console.log("Owner Address:", owner.address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
