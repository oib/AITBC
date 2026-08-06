import "@nomicfoundation/hardhat-toolbox";
import dotenv from "dotenv";
dotenv.config();

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x" + "0".repeat(64);
const INFURA_PROJECT_ID = process.env.INFURA_PROJECT_ID || process.env.INFURA_API_KEY || "";
const ETH_RPC_URL = process.env.ETH_RPC_URL || "";

const config = {
  solidity: {
    // Two compilers, not one. The config pinned 0.8.19 while AgentIdentity.sol declares
    // ^0.8.20, so `hardhat compile` failed with HH606 and the project could not be built
    // at all -- meaning no contract change has been compile-checked for some time.
    // Hardhat picks the newest configured compiler satisfying each file's pragma.
    compilers: [
      {
        version: "0.8.19",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          viaIR: true
        }
      },
      {
        version: "0.8.20",
        settings: {
          optimizer: { enabled: true, runs: 200 },
          viaIR: true
        }
      }
    ]
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545"
    },
    testnet: {
      url: process.env.TESTNET_RPC_URL || "http://localhost:8545",
      accounts: process.env.TESTNET_DEPLOYER_PRIVATE_KEY ? [process.env.TESTNET_DEPLOYER_PRIVATE_KEY] : [],
      chainId: 31337
    },
    sepolia: {
      url: ETH_RPC_URL || `https://sepolia.infura.io/v3/${INFURA_PROJECT_ID}`,
      accounts: PRIVATE_KEY !== "0x" + "0".repeat(64) ? [PRIVATE_KEY] : [],
      chainId: 11155111
    }
  },
  paths: {
    sources: "./contracts",
    artifacts: "./artifacts"
  }
};

export default config;
