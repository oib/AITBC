# AIToken Deployment Guide

This guide covers deploying the AIToken and AITokenRegistry contracts.

## Prerequisites

- Node.js 18+
- Hardhat
- Private key with ETH for gas
- RPC endpoint for target network

## Contracts

| Contract | Description |
|----------|-------------|
| `AIToken.sol` | ERC20 token with receipt-based minting |
| `AITokenRegistry.sol` | Provider registration and collateral tracking |

## Environment Setup

Create `.env` file:

```bash
# Required
PRIVATE_KEY=0x...your_deployer_private_key

# Network RPC endpoints
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
MAINNET_RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY

# Optional: Role assignments during deployment
COORDINATOR_ADDRESS=0x...coordinator_address
ATTESTOR_ADDRESS=0x...attestor_address

# Etherscan verification
ETHERSCAN_API_KEY=your_api_key
```

## Network Configuration

Update `hardhat.config.ts`:

```typescript
import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";

dotenv.config();

const config: HardhatUserConfig = {
  solidity: "0.8.24",
  networks: {
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
    mainnet: {
      url: process.env.MAINNET_RPC_URL || "",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
    },
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY,
  },
};

export default config;
```

## Deployment Steps

### 1. Compile Contracts

```bash
npx hardhat compile
```

### 2. Run Tests

```bash
npx hardhat test
```

### 3. Deploy to Testnet (Sepolia)

```bash
# Set environment
export COORDINATOR_ADDRESS=0x...
export ATTESTOR_ADDRESS=0x...

# Deploy
npx hardhat run scripts/deploy.ts --network sepolia
```

Expected output:
```
Deploying AIToken using admin: 0x...
AIToken deployed to: 0x...
Granting coordinator role to 0x...
Granting attestor role to 0x...
Deployment complete. Export AITOKEN_ADDRESS= 0x...
```

### 4. Verify on Etherscan

```bash
npx hardhat verify --network sepolia DEPLOYED_ADDRESS "ADMIN_ADDRESS"
```

### 5. Deploy Registry (Optional)

```bash
npx hardhat run scripts/deploy-registry.ts --network sepolia
```

## Post-Deployment

### Grant Additional Roles

```typescript
// In Hardhat console
const token = await ethers.getContractAt("AIToken", "DEPLOYED_ADDRESS");
const coordinatorRole = await token.COORDINATOR_ROLE();
await token.grantRole(coordinatorRole, "NEW_COORDINATOR_ADDRESS");
```

### Test Minting

```bash
npx hardhat run scripts/mintWithReceipt.ts --network sepolia
```

## Mainnet Deployment Checklist

- [ ] All tests passing
- [ ] Security audit completed
- [ ] Testnet deployment verified
- [ ] Gas estimation reviewed
- [ ] Multi-sig wallet for admin role
- [ ] Role addresses confirmed
- [ ] Deployment script reviewed
- [ ] Emergency procedures documented

## Gas Estimates

| Operation | Estimated Gas |
|-----------|---------------|
| Deploy AIToken | ~1,500,000 |
| Deploy Registry | ~800,000 |
| Grant Role | ~50,000 |
| Mint with Receipt | ~80,000 |
| Register Provider | ~60,000 |

## Security Considerations

1. **Admin Key Security**: Use hardware wallet or multi-sig for admin
2. **Role Management**: Carefully manage COORDINATOR and ATTESTOR roles
3. **Receipt Replay**: Contract prevents receipt reuse via `consumedReceipts` mapping
4. **Signature Verification**: Uses OpenZeppelin ECDSA for secure signature recovery

## Troubleshooting

### "invalid attestor signature"
- Verify attestor has ATTESTOR_ROLE
- Check signature was created with correct chain ID and contract address
- Ensure message hash matches expected format

### "receipt already consumed"
- Each receipt hash can only be used once
- Generate new unique receipt hash for each mint

### "AccessControl: account ... is missing role"
- Grant required role to the calling address
- Verify role was granted on correct contract instance

## Contract Addresses

### Testnet (Sepolia)
| Contract | Address |
|----------|---------|
| AIToken | TBD |
| AITokenRegistry | TBD |

### Mainnet
| Contract | Address |
|----------|---------|
| AIToken | TBD |
| AITokenRegistry | TBD |
