# Zero-Knowledge Receipt Attestation Design

## Overview

This document outlines the design for adding zero-knowledge proof capabilities to the AITBC receipt attestation system, enabling privacy-preserving settlement flows while maintaining verifiability.

## Goals

1. **Privacy**: Hide sensitive transaction details (amounts, parties, specific computations)
2. **Verifiability**: Prove receipts are valid and correctly signed without revealing contents
3. **Compatibility**: Work with existing receipt signing and settlement systems
4. **Efficiency**: Minimize proof generation and verification overhead

## Architecture

### Current Receipt System

The existing system has:
- Receipt signing with coordinator private key
- Optional coordinator attestations
- History retrieval endpoints
- Cross-chain settlement hooks

Receipt structure includes:
- Job ID and metadata
- Computation results
- Pricing information
- Miner and coordinator signatures

### Privacy-Preserving Flow

```
1. Job Execution
   ↓
2. Receipt Generation (clear text)
   ↓
3. ZK Circuit Input Preparation
   ↓
4. ZK Proof Generation
   ↓
5. On-Chain Settlement (with proof)
   ↓
6. Verification (without revealing data)
```

## ZK Circuit Design

### What to Prove

1. **Receipt Validity**
   - Receipt was signed by coordinator
   - Computation was performed correctly
   - Pricing follows agreed rules

2. **Settlement Conditions**
   - Amount owed is correctly calculated
   - Parties have sufficient funds/balance
   - Cross-chain transfer conditions met

### What to Hide

1. **Sensitive Data**
   - Actual computation amounts
   - Specific job details
   - Pricing rates
   - Participant identities

### Circuit Components

```circom
// High-level circuit structure
template ReceiptAttestation() {
    // Public inputs
    signal input receiptHash;
    signal input settlementAmount;
    signal input timestamp;
    
    // Private inputs
    signal input receipt;
    signal input computationResult;
    signal input pricingRate;
    signal input minerReward;
    
    // Verify receipt signature
    component signatureVerifier = ECDSAVerify();
    // ... signature verification logic
    
    // Verify computation correctness
    component computationChecker = ComputationVerify();
    // ... computation verification logic
    
    // Verify pricing calculation
    component pricingVerifier = PricingVerify();
    // ... pricing verification logic
    
    // Output settlement proof
    settlementAmount <== minerReward + coordinatorFee;
}
```

## Implementation Plan

### Phase 1: Research & Prototyping
1. **Library Selection**
   - snarkjs for development (JavaScript/TypeScript)
   - circomlib2 for standard circuits
   - Web3.js for blockchain integration

2. **Basic Circuit**
   - Simple receipt hash preimage proof
   - ECDSA signature verification
   - Basic arithmetic operations

### Phase 2: Integration
1. **Coordinator API Updates**
   - Add ZK proof generation endpoint
   - Integrate with existing receipt signing
   - Add proof verification utilities

2. **Settlement Flow**
   - Modify cross-chain hooks to accept proofs
   - Update verification logic
   - Maintain backward compatibility

### Phase 3: Optimization
1. **Performance**
   - Trusted setup for Groth16
   - Batch proof generation
   - Recursive proofs for complex receipts

2. **Security**
   - Audit circuits
   - Formal verification
   - Side-channel resistance

## Data Flow

### Proof Generation (Coordinator)

```python
async def generate_receipt_proof(receipt: Receipt) -> ZKProof:
    # 1. Prepare circuit inputs
    public_inputs = {
        "receiptHash": hash_receipt(receipt),
        "settlementAmount": calculate_settlement(receipt),
        "timestamp": receipt.timestamp
    }
    
    private_inputs = {
        "receipt": receipt,
        "computationResult": receipt.result,
        "pricingRate": receipt.pricing.rate,
        "minerReward": receipt.pricing.miner_reward
    }
    
    # 2. Generate witness
    witness = generate_witness(public_inputs, private_inputs)
    
    # 3. Generate proof
    proof = groth16.prove(witness, proving_key)
    
    return {
        "proof": proof,
        "publicSignals": public_inputs
    }
```

### Proof Verification (On-Chain/Settlement Layer)

```solidity
contract SettlementVerifier {
    // Groth16 verifier
    function verifySettlement(
        uint256[2] memory a,
        uint256[2][2] memory b,
        uint256[2] memory c,
        uint256[] memory input
    ) public pure returns (bool) {
        return verifyProof(a, b, c, input);
    }
    
    function settleWithProof(
        address recipient,
        uint256 amount,
        ZKProof memory proof
    ) public {
        require(verifySettlement(proof.a, proof.b, proof.c, proof.inputs));
        // Execute settlement
        _transfer(recipient, amount);
    }
}
```

## Privacy Levels

### Level 1: Basic Privacy
- Hide computation amounts
- Prove pricing correctness
- Reveal participant identities

### Level 2: Enhanced Privacy
- Hide all amounts
- Zero-knowledge participant proofs
- Anonymous settlement

### Level 3: Full Privacy
- Complete transaction privacy
- Ring signatures or similar
- Confidential transfers

## Security Considerations

1. **Trusted Setup**
   - Multi-party ceremony for Groth16
   - Documentation of setup process
   - Toxic waste destruction proof

2. **Circuit Security**
   - Constant-time operations
   - No side-channel leaks
   - Formal verification where possible

3. **Integration Security**
   - Maintain existing security guarantees
   - Fail-safe verification
   - Gradual rollout with monitoring

## Migration Strategy

1. **Parallel Operation**
   - Run both clear and ZK receipts
   - Gradual opt-in adoption
   - Performance monitoring

2. **Backward Compatibility**
   - Existing receipts remain valid
   - Optional ZK proofs
   - Graceful degradation

3. **Network Upgrade**
   - Coordinate with all participants
   - Clear communication
   - Rollback capability

## Next Steps

1. **Research Task**
   - Evaluate zk-SNARKs vs zk-STARKs trade-offs
   - Benchmark proof generation times
   - Assess gas costs for on-chain verification

2. **Prototype Development**
   - Implement basic circuit in circom
   - Create proof generation service
   - Build verification contract

3. **Integration Planning**
   - Design API changes
   - Plan data migration
   - Prepare rollout strategy
