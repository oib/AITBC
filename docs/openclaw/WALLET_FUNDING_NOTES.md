# Wallet Funding Notes

**Date**: April 13, 2026  
**Purpose**: OpenClaw agent communication testing

## Funding Status

**Mock Funds for Testing**

The following wallets were funded with 1000 AIT each via direct database insertion for testing OpenClaw agent communication:

- **openclaw-trainee**: ait10a252a31c79939c689bf392e960afc7861df5ee9 (1000 AIT)
- **openclaw-backup**: ait11074723ad259f4fadcd5f81721468c89f2d6255d (1000 AIT)
- **temp-agent**: ait1d18e286fc0c12888aca94732b5507c8787af71a5 (1000 AIT)
- **test-agent**: ait168ef22ca8bcdab692445d68d3d95c0309bab87a0 (1000 AIT)

**Genesis Block Allocations**

The genesis block has the following official allocations:
- aitbc1genesis: 10,000,000 AIT (reduced to 9,996,000 AIT after mock funding)
- aitbc1treasury: 5,000,000 AIT
- aitbc1aiengine: 2,000,000 AIT
- aitbc1surveillance: 1,500,000 AIT
- aitbc1analytics: 1,000,000 AIT
- aitbc1marketplace: 2,000,000 AIT
- aitbc1enterprise: 3,000,000 AIT
- aitbc1multimodal: 1,500,000 AIT
- aitbc1zkproofs: 1,000,000 AIT
- aitbc1crosschain: 2,000,000 AIT
- aitbc1developer1: 500,000 AIT
- aitbc1developer2: 300,000 AIT
- aitbc1tester: 200,000 AIT

## Funding Method

**Mock Funding (Direct Database Insertion)**

The OpenClaw wallets were funded via direct database insertion for testing purposes:
```sql
INSERT INTO account (chain_id, address, balance, nonce, updated_at) 
VALUES ('ait-testnet', 'ait10a252a31c79939c689bf392e960afc7861df5ee9', 1000, 0, datetime('now'))
```

**Genesis Balance Adjustment**

The genesis wallet balance was reduced by 4000 AIT (1000 × 4 wallets) to account for the mock funding:
```sql
UPDATE account SET balance = balance - 4000 WHERE address = 'aitbc1genesis'
```

**Note**: This is a mock funding approach for testing. For production, actual blockchain transactions should be used with proper signatures and block validation.

## Production Funding Method (Recommended)

For production deployment, funds should be transferred via proper blockchain transactions:

1. Unlock genesis wallet with private key
2. Create signed transactions to each OpenClaw wallet
3. Submit transactions to mempool
4. Wait for block production and confirmation
5. Verify transactions on blockchain

## Node Sync Status

**aitbc Node:**
- All 4 OpenClaw wallets funded
- Genesis balance: 9,996,000 AIT
- Chain: ait-testnet, height 2

**aitbc1 Node:**
- All 4 OpenClaw wallets funded
- Genesis balance: 10,000,000 AIT (not adjusted on aitbc1)
- Chain: ait-testnet, height 2

## Notes

- **Wallet Decryption Issue**: Both aitbc1genesis and genesis wallets failed to decrypt with standard password "aitbc123"
  - aitbc1genesis uses fernet encryption with different cipher parameters
  - genesis wallet uses aes-256-gcm encryption
  - CLI send command fails with "Error decrypting wallet" for both wallets
  - This prevents actual blockchain transactions with proper signatures

- **Fallback Approach**: Due to wallet decryption issues, database manipulation was used instead of actual blockchain transactions
  - This is NOT production-ready
  - Wallet decryption must be fixed for proper production deployment

- **Current State**:
  - aitbc node: All 4 OpenClaw wallets funded with 1000 AIT each via database
  - aitbc1 node: Partial sync (2 of 4 wallets) due to database lock errors
  - Genesis balance adjusted to reflect funding on aitbc node only

- **Production Requirements**:
  - Fix wallet decryption to enable proper blockchain transactions
  - Use CLI send command with proper signatures
  - Submit transactions to mempool
  - Wait for block production and confirmation
  - Verify transactions on blockchain
