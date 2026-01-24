# Working with ZK Proofs

This tutorial explains how to use zero-knowledge proofs in the AITBC network for privacy-preserving operations.

## Overview

AITBC uses ZK proofs for:
- **Private receipt attestation** - Prove job completion without revealing details
- **Identity commitments** - Prove identity without exposing address
- **Stealth addresses** - Receive payments privately
- **Group membership** - Prove you're part of a group without revealing which member

## Prerequisites

- Circom compiler v2.2.3+
- snarkjs library
- Node.js 18+

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Circuit   │────▶│   Prover    │────▶│  Verifier   │
│   (Circom)  │     │  (snarkjs)  │     │  (On-chain) │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Step 1: Understanding Circuits

AITBC includes pre-built circuits in `apps/zk-circuits/`:

### Receipt Simple Circuit

Proves a receipt is valid without revealing the full receipt:

```circom
// circuits/receipt_simple.circom
pragma circom 2.0.0;

include "circomlib/poseidon.circom";

template ReceiptSimple() {
    // Private inputs
    signal input receipt_id;
    signal input job_id;
    signal input provider;
    signal input client;
    signal input units;
    signal input price;
    signal input salt;
    
    // Public inputs
    signal input receipt_hash;
    signal input min_units;
    
    // Compute hash of receipt
    component hasher = Poseidon(7);
    hasher.inputs[0] <== receipt_id;
    hasher.inputs[1] <== job_id;
    hasher.inputs[2] <== provider;
    hasher.inputs[3] <== client;
    hasher.inputs[4] <== units;
    hasher.inputs[5] <== price;
    hasher.inputs[6] <== salt;
    
    // Verify hash matches
    receipt_hash === hasher.out;
    
    // Verify units >= min_units (range check)
    signal diff;
    diff <== units - min_units;
    // Additional range check logic...
}

component main {public [receipt_hash, min_units]} = ReceiptSimple();
```

## Step 2: Compile Circuit

```bash
cd apps/zk-circuits

# Compile circuit
circom circuits/receipt_simple.circom --r1cs --wasm --sym -o build/

# View circuit info
snarkjs r1cs info build/receipt_simple.r1cs
# Constraints: 300
```

## Step 3: Trusted Setup

```bash
# Download Powers of Tau (one-time)
wget https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_12.ptau

# Generate proving key
snarkjs groth16 setup build/receipt_simple.r1cs powersOfTau28_hez_final_12.ptau build/receipt_simple_0000.zkey

# Contribute to ceremony (adds randomness)
snarkjs zkey contribute build/receipt_simple_0000.zkey build/receipt_simple_final.zkey --name="AITBC Contribution" -v

# Export verification key
snarkjs zkey export verificationkey build/receipt_simple_final.zkey build/verification_key.json
```

## Step 4: Generate Proof

### JavaScript

```javascript
const snarkjs = require('snarkjs');
const fs = require('fs');

async function generateProof(receipt) {
  // Prepare inputs
  const input = {
    receipt_id: BigInt(receipt.receipt_id),
    job_id: BigInt(receipt.job_id),
    provider: BigInt(receipt.provider),
    client: BigInt(receipt.client),
    units: BigInt(Math.floor(receipt.units * 1000)),
    price: BigInt(Math.floor(receipt.price * 1000)),
    salt: BigInt(receipt.salt),
    receipt_hash: BigInt(receipt.hash),
    min_units: BigInt(1000) // Prove units >= 1.0
  };
  
  // Generate proof
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(
    input,
    'build/receipt_simple_js/receipt_simple.wasm',
    'build/receipt_simple_final.zkey'
  );
  
  return { proof, publicSignals };
}

// Usage
const receipt = {
  receipt_id: '12345',
  job_id: '67890',
  provider: '0x1234...',
  client: '0x5678...',
  units: 2.5,
  price: 5.0,
  salt: '0xabcd...',
  hash: '0x9876...'
};

const { proof, publicSignals } = await generateProof(receipt);
console.log('Proof generated:', proof);
```

### Python

```python
import subprocess
import json

def generate_proof(receipt: dict) -> dict:
    # Write input file
    input_data = {
        "receipt_id": str(receipt["receipt_id"]),
        "job_id": str(receipt["job_id"]),
        "provider": str(int(receipt["provider"], 16)),
        "client": str(int(receipt["client"], 16)),
        "units": str(int(receipt["units"] * 1000)),
        "price": str(int(receipt["price"] * 1000)),
        "salt": str(int(receipt["salt"], 16)),
        "receipt_hash": str(int(receipt["hash"], 16)),
        "min_units": "1000"
    }
    
    with open("input.json", "w") as f:
        json.dump(input_data, f)
    
    # Generate witness
    subprocess.run([
        "node", "build/receipt_simple_js/generate_witness.js",
        "build/receipt_simple_js/receipt_simple.wasm",
        "input.json", "witness.wtns"
    ], check=True)
    
    # Generate proof
    subprocess.run([
        "snarkjs", "groth16", "prove",
        "build/receipt_simple_final.zkey",
        "witness.wtns", "proof.json", "public.json"
    ], check=True)
    
    with open("proof.json") as f:
        proof = json.load(f)
    with open("public.json") as f:
        public_signals = json.load(f)
    
    return {"proof": proof, "publicSignals": public_signals}
```

## Step 5: Verify Proof

### Off-Chain (JavaScript)

```javascript
const snarkjs = require('snarkjs');

async function verifyProof(proof, publicSignals) {
  const vKey = JSON.parse(fs.readFileSync('build/verification_key.json'));
  
  const isValid = await snarkjs.groth16.verify(vKey, publicSignals, proof);
  
  return isValid;
}

const isValid = await verifyProof(proof, publicSignals);
console.log('Proof valid:', isValid);
```

### On-Chain (Solidity)

The `ZKReceiptVerifier.sol` contract verifies proofs on-chain:

```solidity
// contracts/ZKReceiptVerifier.sol
function verifyProof(
    uint[2] calldata a,
    uint[2][2] calldata b,
    uint[2] calldata c,
    uint[2] calldata publicSignals
) external view returns (bool valid);
```

Call from JavaScript:

```javascript
const contract = new ethers.Contract(verifierAddress, abi, signer);

// Format proof for Solidity
const a = [proof.pi_a[0], proof.pi_a[1]];
const b = [[proof.pi_b[0][1], proof.pi_b[0][0]], [proof.pi_b[1][1], proof.pi_b[1][0]]];
const c = [proof.pi_c[0], proof.pi_c[1]];

const isValid = await contract.verifyProof(a, b, c, publicSignals);
```

## Use Cases

### Private Receipt Attestation

Prove you completed a job worth at least X tokens without revealing exact amount:

```javascript
// Prove receipt has units >= 10
const { proof } = await generateProof({
  ...receipt,
  min_units: 10000 // 10.0 units
});

// Verifier only sees: receipt_hash and min_units
// Cannot see: actual units, price, provider, client
```

### Identity Commitment

Create a commitment to your identity:

```javascript
const commitment = poseidon([address, secret]);
// Share commitment publicly
// Later prove you know the preimage without revealing address
```

### Stealth Addresses

Generate one-time addresses for private payments:

```javascript
// Sender generates ephemeral keypair
const ephemeral = generateKeypair();

// Compute shared secret
const sharedSecret = ecdh(ephemeral.private, recipientPublic);

// Derive stealth address
const stealthAddress = deriveAddress(recipientAddress, sharedSecret);

// Send to stealth address
await sendPayment(stealthAddress, amount);
```

## Best Practices

1. **Never reuse salts** - Each proof should use a unique salt
2. **Validate inputs** - Check ranges before proving
3. **Use trusted setup** - Don't skip the ceremony
4. **Test thoroughly** - Verify proofs before deploying
5. **Keep secrets secret** - Private inputs must stay private

## Troubleshooting

### "Constraint not satisfied"
- Check input values are within expected ranges
- Verify all required inputs are provided
- Ensure BigInt conversion is correct

### "Invalid proof"
- Verify using same verification key as proving key
- Check public signals match between prover and verifier
- Ensure proof format is correct for verifier

## Next Steps

- [ZK Applications Reference](../../reference/components/zk-applications.md)
- [ZK Receipt Attestation](../../reference/zk-receipt-attestation.md)
- [SDK Examples](sdk-examples.md)
