# Zero-Knowledge Applications in AITBC

This document describes the Zero-Knowledge (ZK) proof capabilities implemented in the AITBC platform.

## Overview

AITBC now supports privacy-preserving operations through ZK-SNARKs, allowing users to prove computations, membership, and other properties without revealing sensitive information.

## Available ZK Features

### 1. Identity Commitments

Create privacy-preserving identity commitments that allow you to prove you're a valid user without revealing your identity.

**Endpoint**: `POST /api/zk/identity/commit`

**Request**:
```json
{
  "salt": "optional_random_string"
}
```

**Response**:
```json
{
  "commitment": "hash_of_identity_and_salt",
  "salt": "used_salt",
  "user_id": "user_identifier",
  "created_at": "2025-12-28T17:50:00Z"
}
```

### 2. Stealth Addresses

Generate one-time payment addresses for enhanced privacy in transactions.

**Endpoint**: `POST /api/zk/stealth/address`

**Parameters**:
- `recipient_public_key` (query): The recipient's public key

**Response**:
```json
{
  "stealth_address": "0x27b224d39bb988620a1447eb4bce6fc629e15331",
  "shared_secret_hash": "b9919ff990cd8793aa587cf5fd800efb997b6dcd...",
  "ephemeral_key": "ca8acd0ae4a9372cdaeef7eb3ac7eb10",
  "view_key": "0x5f7de2cc364f7c8d64ce1051c97a1ba6028f83d9"
}
```

### 3. Private Receipt Attestation

Create receipts that prove computation occurred without revealing the actual computation details.

**Endpoint**: `POST /api/zk/receipt/attest`

**Parameters**:
- `job_id` (query): Identifier of the computation job
- `user_address` (query): Address of the user requesting computation
- `computation_result` (query): Hash of the computation result
- `privacy_level` (query): "basic", "medium", or "maximum"

**Response**:
```json
{
  "job_id": "job_123",
  "user_address": "0xabcdef",
  "commitment": "a6a8598788c066115dcc8ca35032dc60b89f2e138...",
  "privacy_level": "basic",
  "timestamp": "2025-12-28T17:51:26.758953",
  "verified": true
}
```

### 4. Group Membership Proofs

Prove membership in a group (miners, clients, developers) without revealing your identity.

**Endpoint**: `POST /api/zk/membership/verify`

**Request**:
```json
{
  "group_id": "miners",
  "nullifier": "unique_64_char_string",
  "proof": "zk_snark_proof_string"
}
```

### 5. Private Bidding

Submit bids to marketplace auctions without revealing the bid amount.

**Endpoint**: `POST /api/zk/marketplace/private-bid`

**Request**:
```json
{
  "auction_id": "auction_123",
  "bid_commitment": "hash_of_bid_and_salt",
  "proof": "proof_that_bid_is_in_valid_range"
}
```

### 6. Computation Proofs

Verify that AI computations were performed correctly without revealing the inputs.

**Endpoint**: `POST /api/zk/computation/verify`

**Request**:
```json
{
  "job_id": "job_456",
  "result_hash": "hash_of_computation_result",
  "proof_of_execution": "zk_snark_proof",
  "public_inputs": {}
}
```

## Anonymity Sets

View available anonymity sets for privacy operations:

**Endpoint**: `GET /api/zk/anonymity/sets`

**Response**:
```json
{
  "sets": {
    "miners": {
      "size": 100,
      "description": "Registered GPU miners",
      "type": "merkle_tree"
    },
    "clients": {
      "size": 500,
      "description": "Active clients",
      "type": "merkle_tree"
    },
    "transactions": {
      "size": 1000,
      "description": "Recent transactions",
      "type": "ring_signature"
    }
  },
  "min_anonymity": 3,
  "recommended_sets": ["miners", "clients"]
}
```

## Technical Implementation

### Circuit Compilation

The ZK circuits are compiled using:
- **Circom**: v2.2.3
- **Circomlib**: For standard circuit components
- **SnarkJS**: For trusted setup and proof generation

### Trusted Setup

A complete trusted setup ceremony has been performed:
1. Powers of Tau ceremony with 2^12 powers
2. Phase 2 preparation for specific circuits
3. Groth16 proving keys generated
4. Verification keys exported

### Circuit Files

The following circuit files are deployed:
- `receipt_simple_0001.zkey`: Proving key for receipt circuit
- `receipt_simple.wasm`: WASM witness generator
- `verification_key.json`: Verification key for on-chain verification

### Privacy Levels

1. **Basic**: Hash-based commitments (no ZK-SNARKs)
2. **Medium**: Simple ZK proofs with limited constraints
3. **Maximum**: Full ZK-SNARKs with complete privacy

## Security Considerations

1. **Trusted Setup**: The trusted setup was performed with proper entropy and multiple contributions
2. **Randomness**: All operations use cryptographically secure random number generation
3. **Nullifiers**: Prevent double-spending and replay attacks
4. **Verification**: All proofs can be verified on-chain or off-chain

## Future Enhancements

1. **Additional Circuits**: Membership and bid range circuits to be compiled
2. **Recursive Proofs**: Enable proof composition for complex operations
3. **On-Chain Verification**: Deploy verification contracts to blockchain
4. **Hardware Acceleration**: GPU acceleration for proof generation

## API Status

Check the current status of ZK features:

**Endpoint**: `GET /api/zk/status`

This endpoint returns detailed information about:
- Which ZK features are active
- Circuit compilation status
- Available proof types
- Next steps for implementation

## Integration Guide

To integrate ZK proofs in your application:

1. **Generate Proof**: Use the appropriate endpoint to generate a proof
2. **Submit Proof**: Include the proof in your transaction or API call
3. **Verify Proof**: The system will automatically verify the proof
4. **Privacy**: Your sensitive data remains private throughout the process

## Examples

### Private Marketplace Bid

```javascript
// 1. Create bid commitment
const bidAmount = 100;
const salt = generateRandomSalt();
const commitment = hash(bidAmount + salt);

// 2. Generate ZK proof that bid is within range
const proof = await generateBidRangeProof(bidAmount, salt);

// 3. Submit private bid
const response = await fetch('/api/zk/marketplace/private-bid', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    auction_id: 'auction_123',
    bid_commitment: commitment,
    proof: proof
  })
});
```

### Stealth Address Payment

```javascript
// 1. Generate stealth address for recipient
const response = await fetch(
  '/api/zk/stealth/address?recipient_public_key=0x123...',
  { method: 'POST' }
);

const { stealth_address, view_key } = await response.json();

// 2. Send payment to stealth address
await sendTransaction({
  to: stealth_address,
  amount: 1000
});

// 3. Recipient can view funds using view_key
const balance = await viewStealthAddressBalance(view_key);
```

## Support

For questions about ZK applications:
- Check the API documentation at `/docs/`
- Review the status endpoint at `/api/zk/status`
- Examine the circuit source code in `apps/zk-circuits/`
