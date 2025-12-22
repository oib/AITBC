---
eip: 8XXX
title: AITBC Receipt Interoperability Standard
description: Standard format for AI/ML workload receipts enabling cross-chain verification and marketplace interoperability
author: AITBC Research Consortium <research@aitbc.io>
discussions-to: https://github.com/ethereum/EIPs/discussions/8XXX
status: Draft
type: Standards Track
category: ERC
created: 2024-01-XX
requires: 712, 191, 1155
---

## Abstract

This standard defines a universal format for AI/ML workload receipts that enables:
- Cross-chain verification of computation results
- Interoperability between decentralized AI marketplaces
- Standardized metadata for model inference and training
- Cryptographic proof verification across different blockchain networks
- Composable receipt-based workflows

## Motivation

The growing ecosystem of decentralized AI marketplaces and blockchain-based AI services lacks a standard for receipt representation. This leads to:
- Fragmented markets with incompatible receipt formats
- Difficulty in verifying computations across chains
- Limited composability between AI services
- Redundant implementations of similar functionality

By establishing a universal receipt standard, we enable:
- Seamless cross-chain AI service integration
- Unified verification mechanisms
- Enhanced marketplace liquidity
- Reduced development overhead for AI service providers

## Specification

### Core Receipt Structure

```solidity
interface IAITBCReceipt {
    struct Receipt {
        bytes32 receiptId;           // Unique identifier
        address provider;            // Service provider
        address client;              // Client who requested
        uint256 timestamp;           // Execution timestamp
        uint256 chainId;             // Source chain ID
        WorkloadType workloadType;   // Type of AI workload
        WorkloadMetadata metadata;   // Workload-specific data
        VerificationProof proof;     // Cryptographic proof
        bytes signature;             // Provider signature
    }
    
    enum WorkloadType {
        INFERENCE,
        TRAINING,
        FINE_TUNING,
        VALIDATION
    }
}
```

### Workload Metadata

```solidity
struct WorkloadMetadata {
    string modelId;                 // Model identifier
    string modelVersion;            // Model version
    bytes32 modelHash;              // Model content hash
    bytes32 inputHash;              // Input data hash
    bytes32 outputHash;             // Output data hash
    uint256 computeUnits;           // Compute resources used
    uint256 executionTime;          // Execution time in ms
    mapping(string => string) customFields;  // Extensible metadata
}
```

### Verification Proof

```solidity
struct VerificationProof {
    ProofType proofType;            // Type of proof
    bytes proofData;                // Proof bytes
    bytes32[] publicInputs;         // Public inputs
    bytes32[] verificationKeys;     // Verification keys
    uint256 verificationGas;        // Gas required for verification
}
```

### Cross-Chain Verification

```solidity
interface ICrossChainVerifier {
    event VerificationRequested(
        bytes32 indexed receiptId,
        uint256 fromChainId,
        uint256 toChainId
    );
    
    event VerificationCompleted(
        bytes32 indexed receiptId,
        bool verified,
        bytes32 crossChainId
    );
    
    function verifyReceipt(
        Receipt calldata receipt,
        uint256 targetChainId
    ) external returns (bytes32 crossChainId);
    
    function submitCrossChainProof(
        bytes32 crossChainId,
        bytes calldata proof
    ) external returns (bool verified);
}
```

### Marketplace Integration

```solidity
interface IAITBCMarketplace {
    function listService(
        Service calldata service,
        ReceiptTemplate calldata template
    ) external returns (uint256 serviceId);
    
    function executeWorkload(
        uint256 serviceId,
        bytes calldata workloadData
    ) external payable returns (Receipt memory receipt);
    
    function verifyAndSettle(
        Receipt calldata receipt
    ) external returns (bool settled);
}
```

### JSON Representation

```json
{
  "receiptId": "0x...",
  "provider": "0x...",
  "client": "0x...",
  "timestamp": 1704067200,
  "chainId": 1,
  "workloadType": "INFERENCE",
  "metadata": {
    "modelId": "gpt-4",
    "modelVersion": "1.0.0",
    "modelHash": "0x...",
    "inputHash": "0x...",
    "outputHash": "0x...",
    "computeUnits": 1000,
    "executionTime": 2500,
    "customFields": {
      "temperature": "0.7",
      "maxTokens": "1000"
    }
  },
  "proof": {
    "proofType": "ZK_SNARK",
    "proofData": "0x...",
    "publicInputs": ["0x..."],
    "verificationKeys": ["0x..."],
    "verificationGas": 50000
  },
  "signature": "0x..."
}
```

## Rationale

### Design Decisions

1. **Hierarchical Structure**: Receipt contains metadata and proof separately for flexibility
2. **Extensible Metadata**: Custom fields allow for workload-specific extensions
3. **Multiple Proof Types**: Supports ZK-SNARKs, STARKs, and optimistic rollups
4. **Chain Agnostic**: Works across EVM and non-EVM chains
5. **Backwards Compatible**: Builds on existing ERC standards

### Trade-offs

1. **Gas Costs**: Comprehensive metadata increases verification costs
   - Mitigation: Optional fields and lazy verification
2. **Proof Size**: ZK proofs can be large
   - Mitigation: Proof compression and aggregation
3. **Standardization vs Innovation**: Fixed format may limit innovation
   - Mitigation: Versioning and extension mechanisms

## Backwards Compatibility

This standard is designed to be backwards compatible with:
- **ERC-712**: Typed data signing for receipts
- **ERC-1155**: Multi-token standard for representing receipts as NFTs
- **ERC-191**: Signed data standard for cross-chain verification

Existing implementations can adopt this standard by:
1. Wrapping current receipt formats
2. Implementing adapter contracts
3. Using migration contracts for gradual transition

## Security Considerations

### Provider Misbehavior
- Providers must sign receipts cryptographically
- Slashing conditions for invalid proofs
- Reputation system integration

### Cross-Chain Risks
- Replay attacks across chains
- Bridge security dependencies
- Finality considerations

### Privacy Concerns
- Sensitive data in metadata
- Proof leakage risks
- Client privacy protection

### Mitigations
1. **Cryptographic Guarantees**: All receipts signed by providers
2. **Economic Security**: Stake requirements for providers
3. **Privacy Options**: Zero-knowledge proofs for sensitive data
4. **Audit Trails**: Complete verification history

## Implementation Guide

### Basic Implementation

```solidity
contract AITBCReceipt is IAITBCReceipt {
    mapping(bytes32 => Receipt) public receipts;
    mapping(address => uint256) public providerNonce;
    
    function createReceipt(
        WorkloadType workloadType,
        WorkloadMetadata calldata metadata,
        VerificationProof calldata proof
    ) external returns (bytes32 receiptId) {
        require(providerNonce[msg.sender] == metadata.nonce);
        
        receiptId = keccak256(
            abi.encodePacked(
                msg.sender,
                block.timestamp,
                metadata.modelHash,
                metadata.inputHash
            )
        );
        
        receipts[receiptId] = Receipt({
            receiptId: receiptId,
            provider: msg.sender,
            client: tx.origin,
            timestamp: block.timestamp,
            chainId: block.chainid,
            workloadType: workloadType,
            metadata: metadata,
            proof: proof,
            signature: new bytes(0)
        });
        
        providerNonce[msg.sender]++;
        emit ReceiptCreated(receiptId, msg.sender);
    }
}
```

### Cross-Chain Bridge Implementation

```solidity
contract AITBCBridge is ICrossChainVerifier {
    mapping(bytes32 => CrossChainVerification) public verifications;
    
    function verifyReceipt(
        Receipt calldata receipt,
        uint256 targetChainId
    ) external override returns (bytes32 crossChainId) {
        crossChainId = keccak256(
            abi.encodePacked(
                receipt.receiptId,
                targetChainId,
                block.timestamp
            )
        );
        
        verifications[crossChainId] = CrossChainVerification({
            receiptId: receipt.receiptId,
            fromChainId: receipt.chainId,
            toChainId: targetChainId,
            timestamp: block.timestamp,
            status: VerificationStatus.PENDING
        });
        
        emit VerificationRequested(receipt.receiptId, receipt.chainId, targetChainId);
    }
}
```

## Test Cases

### Test Case 1: Basic Receipt Creation
```solidity
function testCreateReceipt() public {
    WorkloadMetadata memory metadata = WorkloadMetadata({
        modelId: "test-model",
        modelVersion: "1.0.0",
        modelHash: keccak256("model"),
        inputHash: keccak256("input"),
        outputHash: keccak256("output"),
        computeUnits: 100,
        executionTime: 1000,
        customFields: new mapping(string => string)
    });
    
    bytes32 receiptId = receiptContract.createReceipt(
        WorkloadType.INFERENCE,
        metadata,
        proof
    );
    
    assertTrue(receiptId != bytes32(0));
}
```

### Test Case 2: Cross-Chain Verification
```solidity
function testCrossChainVerification() public {
    bytes32 crossChainId = bridge.verifyReceipt(receipt, targetChain);
    
    assertEq(bridge.getVerificationStatus(crossChainId), VerificationStatus.PENDING);
    
    // Submit proof on target chain
    bool verified = bridgeTarget.submitCrossChainProof(
        crossChainId,
        crossChainProof
    );
    
    assertTrue(verified);
}
```

## Reference Implementation

A full reference implementation is available at:
- GitHub: https://github.com/aitbc/receipt-standard
- npm: @aitbc/receipt-standard
- Documentation: https://docs.aitbc.io/receipt-standard

## Industry Adoption

### Current Supporters
- [List of supporting organizations]
- [Implemented marketplaces]
- [Tooling providers]

### Integration Examples
1. **Ethereum Mainnet**: Full implementation with ZK proofs
2. **Polygon**: Optimistic rollup integration
3. **Arbitrum**: STARK-based verification
4. **Cosmos**: IBC integration for cross-chain

### Migration Path
1. Phase 1: Adapter contracts for existing formats
2. Phase 2: Hybrid implementations
3. Phase 3: Full standard adoption

## Future Extensions

### Planned Enhancements
1. **Recursive Proofs**: Nested receipt verification
2. **Batch Verification**: Multiple receipts in one proof
3. **Dynamic Pricing**: Market-based verification costs
4. **AI Model Registry**: On-chain model verification

### Potential Standards
1. **EIP-XXXX**: AI Model Registry Standard
2. **EIP-XXXX**: Cross-Chain AI Service Protocol
3. **EIP-XXXX**: Decentralized AI Oracles

## Copyright

Copyright and related rights waived via CC0.

---

## Appendix A: Full Interface Definition

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.0;

interface IAITBCReceipt {
    // Structs
    struct Receipt {
        bytes32 receiptId;
        address provider;
        address client;
        uint256 timestamp;
        uint256 chainId;
        WorkloadType workloadType;
        WorkloadMetadata metadata;
        VerificationProof proof;
        bytes signature;
    }
    
    struct WorkloadMetadata {
        string modelId;
        string modelVersion;
        bytes32 modelHash;
        bytes32 inputHash;
        bytes32 outputHash;
        uint256 computeUnits;
        uint256 executionTime;
        mapping(string => string) customFields;
    }
    
    struct VerificationProof {
        ProofType proofType;
        bytes proofData;
        bytes32[] publicInputs;
        bytes32[] verificationKeys;
        uint256 verificationGas;
    }
    
    // Enums
    enum WorkloadType { INFERENCE, TRAINING, FINE_TUNING, VALIDATION }
    enum ProofType { ZK_SNARK, ZK_STARK, OPTIMISTIC, TRUSTED }
    
    // Events
    event ReceiptCreated(bytes32 indexed receiptId, address indexed provider);
    event ReceiptVerified(bytes32 indexed receiptId, bool verified);
    event ReceiptRevoked(bytes32 indexed receiptId, string reason);
    
    // Functions
    function createReceipt(
        WorkloadType workloadType,
        WorkloadMetadata calldata metadata,
        VerificationProof calldata proof
    ) external returns (bytes32 receiptId);
    
    function verifyReceipt(bytes32 receiptId) external returns (bool verified);
    
    function revokeReceipt(bytes32 receiptId, string calldata reason) external;
    
    function getReceipt(bytes32 receiptId) external view returns (Receipt memory);
}
```

## Appendix B: Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-01-XX | Initial draft |
| 1.0.1 | 2024-02-XX | Added cross-chain verification |
| 1.1.0 | 2024-03-XX | Added batch verification support |
| 1.2.0 | 2024-04-XX | Enhanced privacy features |
