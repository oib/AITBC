# Miner

## Status
✅ Operational

## Overview
Mining and block validation service for the AITBC blockchain using Proof-of-Authority consensus.

## Architecture

### Core Components
- **Block Validator**: Validates blocks from the network
- **Block Proposer**: Proposes new blocks (for authorized proposers)
- **Transaction Validator**: Validates transactions before inclusion
- **Reward Claimer**: Claims mining rewards
- **Sync Manager**: Manages blockchain synchronization

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to blockchain RPC endpoint
- Valid proposer credentials (if proposing blocks)

### Installation
```bash
cd /opt/aitbc/apps/miner
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
BLOCKCHAIN_RPC_URL=http://localhost:8006
PROPOSER_ID=your-proposer-id
PROPOSER_PRIVATE_KEY=encrypted-key
MINING_ENABLED=true
VALIDATION_ENABLED=true
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure blockchain RPC endpoint
5. Configure proposer credentials (if proposing)
6. Run tests: `pytest tests/`

### Project Structure
```
miner/
├── src/
│   ├── block_validator/      # Block validation
│   ├── block_proposer/       # Block proposal
│   ├── transaction_validator/ # Transaction validation
│   ├── reward_claimer/       # Reward claiming
│   └── sync_manager/        # Sync management
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run block validator tests
pytest tests/test_validator.py

# Run block proposer tests
pytest tests/test_proposer.py
```

## API Reference

### Block Validation

#### Validate Block
```http
POST /api/v1/mining/validate/block
Content-Type: application/json

{
  "block": {},
  "chain_id": "ait-mainnet"
}
```

#### Get Validation Status
```http
GET /api/v1/mining/validation/status
```

### Block Proposal

#### Propose Block
```http
POST /api/v1/mining/propose/block
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "transactions": [{}],
  "timestamp": "2024-01-01T00:00:00Z"
}
```

#### Get Proposal Status
```http
GET /api/v1/mining/proposal/status
```

### Transaction Validation

#### Validate Transaction
```http
POST /api/v1/mining/validate/transaction
Content-Type: application/json

{
  "transaction": {},
  "chain_id": "ait-mainnet"
}
```

#### Get Validation Queue
```http
GET /api/v1/mining/validation/queue?limit=100
```

### Reward Claiming

#### Claim Reward
```http
POST /api/v1/mining/rewards/claim
Content-Type: application/json

{
  "block_height": 1000,
  "proposer_id": "string"
}
```

#### Get Reward History
```http
GET /api/v1/mining/rewards/history?proposer_id=string
```

### Sync Management

#### Get Sync Status
```http
GET /api/v1/mining/sync/status
```

#### Trigger Sync
```http
POST /api/v1/mining/sync/trigger
Content-Type: application/json

{
  "from_height": 1000,
  "to_height": 2000
}
```

## Configuration

### Environment Variables
- `BLOCKCHAIN_RPC_URL`: Blockchain RPC endpoint
- `PROPOSER_ID`: Proposer identifier
- `PROPOSER_PRIVATE_KEY`: Encrypted proposer private key
- `MINING_ENABLED`: Enable block proposal
- `VALIDATION_ENABLED`: Enable block validation
- `SYNC_INTERVAL`: Sync interval in seconds

### Consensus Parameters
- **Block Time**: Time between blocks (default: 10s)
- **Max Transactions**: Maximum transactions per block
- **Block Size**: Maximum block size in bytes

### Validation Rules
- **Signature Validation**: Validate block signatures
- **Transaction Validation**: Validate transaction format
- **State Validation**: Validate state transitions

## Troubleshooting

**Block validation failed**: Check block signature and state transitions.

**Proposal rejected**: Verify proposer authorization and block validity.

**Sync not progressing**: Check blockchain RPC connectivity and network status.

**Reward claim failed**: Verify proposer ID and block height.

## Security Notes

- Secure proposer private key storage
- Validate all blocks before acceptance
- Monitor for double-spending attacks
- Implement rate limiting for proposal
- Regularly audit mining operations
- Use secure key management
