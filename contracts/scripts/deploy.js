// Deploy ZKReceiptVerifier.
//
// deploy-testnet.sh invoked `hardhat run scripts/deploy.js` while this file did not
// exist -- the script printed its own source as a "template" in the fallback branch
// instead (SC-11). Extracted here so the documented path actually runs.

const hre = require("hardhat");
const { ethers, network } = hre;

async function main() {
  const Verifier = await ethers.getContractFactory("ZKReceiptVerifier");
  const verifier = await Verifier.deploy();
  await verifier.deployed();
  console.log("ZKReceiptVerifier deployed to:", verifier.address);

  // Verify on Etherscan for real networks. `network` comes from hre rather than an
  // implicit global, which is what made the original template fail under `hardhat run`.
  if (network.name !== "localhost" && network.name !== "hardhat") {
    console.log("Waiting for block confirmations...");
    await verifier.deployTransaction.wait(5);
    await hre.run("verify:verify", {
      address: verifier.address,
      constructorArguments: [],
    });
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
