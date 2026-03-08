import { ethers } from "hardhat";
import { AIToken__factory } from "../typechain-types";

type HexString = `0x${string}`;

type EnvValue = string & {}

function requireEnv(name: string): EnvValue {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable ${name}`);
  }
  return value as EnvValue;
}

function parseUnits(value: string): bigint {
  try {
    if (value.startsWith("0x") || value.startsWith("0X")) {
      return BigInt(value);
    }
    return BigInt(value);
  } catch (error) {
    throw new Error(`UNITS must be a BigInt-compatible value, received ${value}`);
  }
}

function assertHex(value: string, name: string): HexString {
  if (!value.startsWith("0x") && !value.startsWith("0X")) {
    throw new Error(`${name} must be 0x-prefixed`);
  }
  return value.toLowerCase() as HexString;
}

async function main() {
  const contractAddress = assertHex(requireEnv("AITOKEN_ADDRESS"), "AITOKEN_ADDRESS");
  const providerAddress = requireEnv("PROVIDER_ADDRESS");
  const units = parseUnits(requireEnv("UNITS"));
  const receiptHash = assertHex(requireEnv("RECEIPT_HASH"), "RECEIPT_HASH");
  const signature = assertHex(requireEnv("ATTESTOR_SIGNATURE"), "ATTESTOR_SIGNATURE");

  const coordinatorIndex = Number(process.env.COORDINATOR_SIGNER_INDEX ?? "1");
  const signers = await ethers.getSigners();
  const coordinator = signers[coordinatorIndex];
  if (!coordinator) {
    throw new Error(
      `COORDINATOR_SIGNER_INDEX=${coordinatorIndex} does not correspond to an available signer`
    );
  }

  console.log("Using coordinator signer:", coordinator.address);
  console.log("Minting receipt for provider:", providerAddress);
  console.log("Units:", units.toString());

  const token = AIToken__factory.connect(contractAddress, coordinator);
  const tx = await token.mintWithReceipt(providerAddress, units, receiptHash, signature);
  const receipt = await tx.wait();

  console.log("Mint transaction hash:", receipt?.hash ?? tx.hash);
  const balance = await token.balanceOf(providerAddress);
  console.log("Provider balance:", balance.toString());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
