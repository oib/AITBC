import { ethers } from "hardhat";
import { AIToken__factory } from "../typechain-types";

function envOrDefault(name: string, fallback?: string): string | undefined {
  const value = process.env[name]?.trim();
  return value && value.length > 0 ? value : fallback;
}

async function main() {
  const [deployer, coordinatorCandidate] = await ethers.getSigners();

  console.log("Deploying AIToken using admin:", deployer.address);

  const contractFactory: AIToken__factory = await ethers.getContractFactory("AIToken");
  const token = await contractFactory.deploy(deployer.address);
  await token.waitForDeployment();

  const contractAddress = await token.getAddress();
  console.log("AIToken deployed to:", contractAddress);

  const coordinatorRole = await token.COORDINATOR_ROLE();
  const attestorRole = await token.ATTESTOR_ROLE();

  const coordinatorAddress = envOrDefault("COORDINATOR_ADDRESS", coordinatorCandidate.address);
  if (!coordinatorAddress) {
    throw new Error(
      "COORDINATOR_ADDRESS not provided and could not infer fallback signer address"
    );
  }

  if (!(await token.hasRole(coordinatorRole, coordinatorAddress))) {
    console.log("Granting coordinator role to", coordinatorAddress);
    const tx = await token.grantRole(coordinatorRole, coordinatorAddress);
    await tx.wait();
  } else {
    console.log("Coordinator role already assigned to", coordinatorAddress);
  }

  const attestorAddress = envOrDefault("ATTESTOR_ADDRESS");
  if (attestorAddress) {
    if (!(await token.hasRole(attestorRole, attestorAddress))) {
      console.log("Granting attestor role to", attestorAddress);
      const tx = await token.grantRole(attestorRole, attestorAddress);
      await tx.wait();
    } else {
      console.log("Attestor role already assigned to", attestorAddress);
    }
  } else {
    console.log("No ATTESTOR_ADDRESS provided; skipping attestor role grant.");
  }

  console.log("Deployment complete. Export AITOKEN_ADDRESS=", contractAddress);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
