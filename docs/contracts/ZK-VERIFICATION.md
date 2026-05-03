# ZK Receipt Verification Guide

This document describes the on-chain zero-knowledge proof verification flow for AITBC receipts.

## Overview

The ZK verification system allows proving receipt validity without revealing sensitive details:
- **Prover** (off-chain): Generates ZK proof from receipt data
- **Verifier** (on-chain): Validates proof and records verified receipts

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Receipt Data   │────▶│  ZK Prover      │────▶│  ZKReceiptVerifier │
│  (off-chain)    │     │  (snarkjs)      │     │  (on-chain)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │                       │                       │
        ▼                       ▼                       ▼
   Private inputs          Proof (a,b,c)         Verified receipt
   - receipt[4]            Public signals        - receiptHash
                           - receiptHash         - settlementAmount
```

## Contracts

### ZKReceiptVerifier.sol

Main contract for receipt verification.

| Function | Description |
|----------|-------------|
| `verifyReceiptProof()` | Verify a proof (view, no state change) |
| `verifyAndRecord()` | Verify and record receipt (prevents double-spend) |
| `batchVerify()` | Verify multiple proofs in one call |
| `isReceiptVerified()` | Check if receipt already verified |

### Groth16Verifier.sol

Auto-generated verifier from snarkjs. Contains the verification key and pairing check logic.

## Circuit: SimpleReceipt

The `receipt_simple.circom` circuit:

```circom
template SimpleReceipt() {
    signal input receiptHash;      // Public
    signal input receipt[4];       // Private
    
    component hasher = Poseidon(4);
    for (var i = 0; i < 4; i++) {
        hasher.inputs[i] <== receipt[i];
    }
    hasher.out === receiptHash;
}
```

**Public Signals:** `[receiptHash]`
**Private Inputs:** `receipt[4]` (4 field elements representing receipt data)

## Proof Generation (Off-chain)

### 1. Prepare Receipt Data

```javascript
const snarkjs = require("snarkjs");

// Receipt data as 4 field elements
const receipt = [
    BigInt(jobId),           // Job identifier
    BigInt(providerAddress), // Provider address as number
    BigInt(units * 1000),    // Units (scaled)
    BigInt(timestamp)        // Unix timestamp
];

// Compute receipt hash (Poseidon hash)
const receiptHash = poseidon(receipt);
```

### 2. Generate Proof

```javascript
const { proof, publicSignals } = await snarkjs.groth16.fullProve(
    {
        receiptHash: receiptHash,
        receipt: receipt
    },
    "receipt_simple.wasm",
    "receipt_simple_final.zkey"
);

console.log("Proof:", proof);
console.log("Public signals:", publicSignals);
// publicSignals = [receiptHash]
```

### 3. Format for Solidity

```javascript
function formatProofForSolidity(proof) {
    return {
        a: [proof.pi_a[0], proof.pi_a[1]],
        b: [
            [proof.pi_b[0][1], proof.pi_b[0][0]],
            [proof.pi_b[1][1], proof.pi_b[1][0]]
        ],
        c: [proof.pi_c[0], proof.pi_c[1]]
    };
}

const solidityProof = formatProofForSolidity(proof);
```

## On-chain Verification

### View-only Verification

```solidity
// Check if proof is valid without recording
bool valid = verifier.verifyReceiptProof(
    solidityProof.a,
    solidityProof.b,
    solidityProof.c,
    publicSignals
);
```

### Verify and Record (Settlement)

```solidity
// Verify and record for settlement (prevents replay)
bool success = verifier.verifyAndRecord(
    solidityProof.a,
    solidityProof.b,
    solidityProof.c,
    publicSignals,
    settlementAmount  // Amount to settle
);

// Check if receipt was already verified
bool alreadyVerified = verifier.isReceiptVerified(receiptHash);
```

### Batch Verification

```solidity
ZKReceiptVerifier.BatchProof[] memory proofs = new ZKReceiptVerifier.BatchProof[](3);
proofs[0] = ZKReceiptVerifier.BatchProof(a1, b1, c1, signals1);
proofs[1] = ZKReceiptVerifier.BatchProof(a2, b2, c2, signals2);
proofs[2] = ZKReceiptVerifier.BatchProof(a3, b3, c3, signals3);

bool[] memory results = verifier.batchVerify(proofs);
```

## Integration with Coordinator API

### Python Integration

```python
import subprocess
import json

def generate_receipt_proof(receipt: dict) -> dict:
    """Generate ZK proof for a receipt."""
    # Prepare input
    input_data = {
        "receiptHash": str(receipt["hash"]),
        "receipt": [
            str(receipt["job_id"]),
            str(int(receipt["provider"], 16)),
            str(int(receipt["units"] * 1000)),
            str(receipt["timestamp"])
        ]
    }
    
    with open("input.json", "w") as f:
        json.dump(input_data, f)
    
    # Generate witness
    subprocess.run([
        "node", "receipt_simple_js/generate_witness.js",
        "receipt_simple.wasm", "input.json", "witness.wtns"
    ], check=True)
    
    # Generate proof
    subprocess.run([
        "snarkjs", "groth16", "prove",
        "receipt_simple_final.zkey",
        "witness.wtns", "proof.json", "public.json"
    ], check=True)
    
    with open("proof.json") as f:
        proof = json.load(f)
    with open("public.json") as f:
        public_signals = json.load(f)
    
    return {"proof": proof, "publicSignals": public_signals}
```

### Submit to Contract

```python
from web3 import Web3

def submit_proof_to_contract(proof: dict, settlement_amount: int):
    """Submit proof to ZKReceiptVerifier contract."""
    w3 = Web3(Web3.HTTPProvider("https://rpc.example.com"))
    
    contract = w3.eth.contract(
        address=VERIFIER_ADDRESS,
        abi=VERIFIER_ABI
    )
    
    # Format proof
    a = [int(proof["pi_a"][0]), int(proof["pi_a"][1])]
    b = [
        [int(proof["pi_b"][0][1]), int(proof["pi_b"][0][0])],
        [int(proof["pi_b"][1][1]), int(proof["pi_b"][1][0])]
    ]
    c = [int(proof["pi_c"][0]), int(proof["pi_c"][1])]
    public_signals = [int(proof["publicSignals"][0])]
    
    # Submit transaction
    tx = contract.functions.verifyAndRecord(
        a, b, c, public_signals, settlement_amount
    ).build_transaction({
        "from": AUTHORIZED_ADDRESS,
        "gas": 500000,
        "nonce": w3.eth.get_transaction_count(AUTHORIZED_ADDRESS)
    })
    
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    
    return w3.eth.wait_for_transaction_receipt(tx_hash)
```

## Deployment

### 1. Generate Groth16Verifier

```bash
cd apps/zk-circuits

# Compile circuit
circom receipt_simple.circom --r1cs --wasm --sym -o build/

# Trusted setup
snarkjs groth16 setup build/receipt_simple.r1cs powersOfTau.ptau build/receipt_simple_0000.zkey
snarkjs zkey contribute build/receipt_simple_0000.zkey build/receipt_simple_final.zkey

# Export Solidity verifier
snarkjs zkey export solidityverifier build/receipt_simple_final.zkey contracts/Groth16Verifier.sol
```

### 2. Deploy Contracts

```bash
# Deploy Groth16Verifier first (or include in ZKReceiptVerifier)
npx hardhat run scripts/deploy-zk-verifier.ts --network sepolia
```

### 3. Configure Authorization

```solidity
// Add authorized verifiers
verifier.addAuthorizedVerifier(coordinatorAddress);

// Set settlement contract
verifier.setSettlementContract(settlementAddress);
```

## Security Considerations

1. **Trusted Setup**: Use a proper ceremony for production
2. **Authorization**: Only authorized addresses can record verified receipts
3. **Double-Spend Prevention**: `verifiedReceipts` mapping prevents replay
4. **Proof Validity**: Groth16 proofs are computationally sound

## Gas Estimates

| Operation | Estimated Gas |
|-----------|---------------|
| `verifyReceiptProof()` | ~300,000 |
| `verifyAndRecord()` | ~350,000 |
| `batchVerify(10)` | ~2,500,000 |

## Troubleshooting

### "Invalid proof"
- Verify circuit was compiled with same parameters
- Check public signals match between prover and verifier
- Ensure proof format is correct (note b array ordering)

### "Receipt already verified"
- Each receipt hash can only be verified once
- Check `isReceiptVerified()` before submitting

### "Unauthorized"
- Caller must be in `authorizedVerifiers` mapping
- Or caller must be the `settlementContract`
