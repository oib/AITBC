import hardhatToolboxMochaEthers from "@nomicfoundation/hardhat-toolbox-mocha-ethers";
import dotenv from "dotenv";
dotenv.config();

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x" + "0".repeat(64);
const INFURA_PROJECT_ID = process.env.INFURA_PROJECT_ID || process.env.INFURA_API_KEY || "";
const ETH_RPC_URL = process.env.ETH_RPC_URL || "";

const compilerSettings = {
  optimizer: { enabled: true, runs: 200 },
  viaIR: true,
  // Pinned, not inherited. Under Hardhat 2 this project built for `paris`, because solc
  // 0.8.19 defaults to it. Hardhat 3 selects 0.8.20 for every file whose pragma allows it,
  // and 0.8.20 defaults to `shanghai` -- which emits PUSH0, an opcode chains that have not
  // adopted Shanghai will reject. A toolchain upgrade must not silently change the bytecode
  // that gets deployed, so the target stays where it was.
  evmVersion: "paris"
};

const config = {
  // Hardhat 3 loads plugins from an explicit list rather than by import side effect.
  plugins: [hardhatToolboxMochaEthers],

  solidity: {
    // Two compilers, not one. The config pinned 0.8.19 while AgentIdentity.sol declares
    // ^0.8.20, so `hardhat compile` failed with HH606 and the project could not be built
    // at all -- meaning no contract change has been compile-checked for some time.
    // Hardhat picks the newest configured compiler satisfying each file's pragma.
    profiles: {
      default: {
        compilers: [
          { version: "0.8.19", settings: compilerSettings },
          { version: "0.8.20", settings: compilerSettings }
        ]
      }
    }
  },

  networks: {
    // `networks.hardhat` is gone in Hardhat 3; in-process chains are declared with
    // type "edr-simulated" and named explicitly.
    hardhat: {
      type: "edr-simulated",
      chainType: "l1"
    },
    localhost: {
      type: "http",
      url: "http://127.0.0.1:8545"
    },
    testnet: {
      type: "http",
      url: process.env.TESTNET_RPC_URL || "http://localhost:8545",
      accounts: process.env.TESTNET_DEPLOYER_PRIVATE_KEY ? [process.env.TESTNET_DEPLOYER_PRIVATE_KEY] : [],
      chainId: 31337
    },
    sepolia: {
      type: "http",
      url: ETH_RPC_URL || `https://sepolia.infura.io/v3/${INFURA_PROJECT_ID}`,
      accounts: PRIVATE_KEY !== "0x" + "0".repeat(64) ? [PRIVATE_KEY] : [],
      chainId: 11155111
    }
  },

  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
    // Hardhat 3 compiles and runs Solidity tests natively, and its default test path is
    // ./test -- which is Foundry's (`test = "test"` in foundry.toml). Left at the default,
    // `hardhat compile` fails resolving forge-std from test/fuzz/*.t.sol. Point Hardhat's
    // Solidity test discovery at a directory forge does not own; the fuzz suite stays with
    // `forge test`, which is what the test-foundry CI job runs.
    tests: {
      mocha: "./test",
      solidity: "./test/solidity"
    }
  }
};

export default config;
