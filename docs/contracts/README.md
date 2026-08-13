# AITBC Contract Documentation

**Level**: Advanced
**Prerequisites**: Beginner blockchain concepts and smart contract familiarity
**Last Updated**: 2026-07-23

## Available Content

### Python in-memory contracts (blockchain-node)

These documents describe the Python contract implementations used by the blockchain-node RPC layer:

- [Agent Messaging Contract](agent-messaging.md)
- [Agent Wallet Security Contract](agent-wallet-security.md)
- [Dispute Resolution Contract](dispute-resolution.md)
- [Escrow Contract](escrow.md)
- [Guardian Contract](guardian.md)
- [HTLC Contract](htlc.md)
- [Persistent Spending Tracker](persistent-spending-tracker.md)
- [Upgrades Contract](upgrades.md)

### Solidity contracts

Production Solidity contracts live in `contracts/contracts/`:

| Contract | Source |
|----------|--------|
| `AIPowerRental` | [AIPowerRental.sol](../../contracts/contracts/AIPowerRental.sol) |
| `AIServiceAMM` | [AIServiceAMM.sol](../../contracts/contracts/AIServiceAMM.sol) |
| `AITBCPaymentProcessor` | [AITBCPaymentProcessor.sol](../../contracts/contracts/AITBCPaymentProcessor.sol) |
| `AIToken` | [AIToken.sol](../../contracts/contracts/AIToken.sol) |
| `AgentBounty` | [AgentBounty.sol](../../contracts/contracts/AgentBounty.sol) |
| `AgentCommunication` | [AgentCommunication.sol](../../contracts/contracts/AgentCommunication.sol) |
| `AgentMarketplaceV2` | [AgentMarketplaceV2.sol](../../contracts/contracts/AgentMarketplaceV2.sol) |
| `AgentMemory` | [AgentMemory.sol](../../contracts/contracts/AgentMemory.sol) |
| `AgentPortfolioManager` | [AgentPortfolioManager.sol](../../contracts/contracts/AgentPortfolioManager.sol) |
| `AgentServiceMarketplace` | [AgentServiceMarketplace.sol](../../contracts/contracts/AgentServiceMarketplace.sol) |
| `AgentStaking` | [AgentStaking.sol](../../contracts/contracts/AgentStaking.sol) |
| `AgentWallet` | [AgentWallet.sol](../../contracts/contracts/AgentWallet.sol) |
| `BountyIntegration` | [BountyIntegration.sol](../../contracts/contracts/BountyIntegration.sol) |
| `ContractRegistry` | [ContractRegistry.sol](../../contracts/contracts/ContractRegistry.sol) |
| `CrossChainAtomicSwap` | [CrossChainAtomicSwap.sol](../../contracts/contracts/CrossChainAtomicSwap.sol) |
| `CrossChainBridge` | [CrossChainBridge.sol](../../contracts/contracts/CrossChainBridge.sol) |
| `CrossChainReputation` | [CrossChainReputation.sol](../../contracts/contracts/CrossChainReputation.sol) |
| `DAOGovernance` | [DAOGovernance.sol](../../contracts/contracts/DAOGovernance.sol) |
| `DAOGovernanceEnhanced` | [DAOGovernanceEnhanced.sol](../../contracts/contracts/DAOGovernanceEnhanced.sol) |
| `DisputeResolution` | [DisputeResolution.sol](../../contracts/contracts/DisputeResolution.sol) |
| `DynamicPricing` | [DynamicPricing.sol](../../contracts/contracts/DynamicPricing.sol) |
| `EscrowService` | [EscrowService.sol](../../contracts/contracts/EscrowService.sol) |
| `GPURegistry` | [GPURegistry.sol](../../contracts/contracts/GPURegistry.sol) |
| `Groth16Verifier` | [Groth16Verifier.sol](../../contracts/contracts/Groth16Verifier.sol) |
| `KnowledgeGraphMarket` | [KnowledgeGraphMarket.sol](../../contracts/contracts/KnowledgeGraphMarket.sol) |
| `MemoryVerifier` | [MemoryVerifier.sol](../../contracts/contracts/MemoryVerifier.sol) |
| `MockVerifier` | [MockVerifier.sol](../../contracts/contracts/MockVerifier.sol) |
| `PerformanceAggregator` | [PerformanceAggregator.sol](../../contracts/contracts/PerformanceAggregator.sol) |
| `PerformanceVerifier` | [PerformanceVerifier.sol](../../contracts/contracts/PerformanceVerifier.sol) |
| `RewardDistributor` | [RewardDistributor.sol](../../contracts/contracts/RewardDistributor.sol) |
| `StakingPoolFactory` | [StakingPoolFactory.sol](../../contracts/contracts/StakingPoolFactory.sol) |
| `TreasuryManager` | [TreasuryManager.sol](../../contracts/contracts/TreasuryManager.sol) |
| `ZKReceiptVerifier` | [ZKReceiptVerifier.sol](../../contracts/contracts/ZKReceiptVerifier.sol) |

### Governance contracts

| Contract | Source |
|----------|--------|
| `AITBCGovernanceToken` | [AITBCGovernanceToken.sol](../../contracts/governance/src/AITBCGovernanceToken.sol) |
| `AITBCVoting` | [AITBCVoting.sol](../../contracts/governance/src/AITBCVoting.sol) |
| `Counter` | [Counter.sol](../../contracts/governance/src/Counter.sol) |

### Development and verification

- [ZK Verification Guide](ZK-VERIFICATION.md) — off-chain proof generation and on-chain verification
- [pnpm Setup](PNPM_SETUP.md) — package manager configuration for contract development
- [Hardhat Version Investigation](HARDHAT_VERSION_INVESTIGATION.md) — historical toolchain notes

## See Also

- [Blockchain Documentation](../blockchain/README.md)
- [Security Documentation](../security/README.md)
- [Deployment Guide](../deployment/SMART_CONTRACT_DEPLOYMENT.md)
- [Master Index](../MASTER_INDEX.md)
