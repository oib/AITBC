# AITBC ZK Circuits

Zero-knowledge circuits for privacy-preserving receipt attestation in the AITBC network.

## Overview

This project implements zk-SNARK circuits to enable privacy-preserving settlement flows while maintaining verifiability of receipts.

## Quick Start

### Prerequisites

- Node.js 16+
- npm or yarn

### Installation

```bash
cd apps/zk-circuits
npm install
```

### Compile Circuit

```bash
npm run compile
```

### Generate Trusted Setup

```bash
# Start phase 1 setup
npm run setup

# Contribute to setup (run multiple times with different participants)
npm run contribute

# Prepare phase 2
npm run prepare

# Generate proving key
npm run generate-zkey

# Contribute to zkey (optional)
npm run contribute-zkey

# Export verification key
npm run export-verification-key
```

### Generate and Verify Proof

```bash
# Generate proof
npm run generate-proof

# Verify proof
npm run verify

# Run tests
npm test
```

## Circuit Design

### Current Implementation

The initial circuit (`receipt.circom`) implements a simple hash preimage proof:

- **Public Inputs**: Receipt hash
- **Private Inputs**: Receipt data (job ID, miner ID, result, pricing)
- **Proof**: Demonstrates knowledge of receipt data without revealing it

### Future Enhancements

1. **Full Receipt Attestation**: Complete validation of receipt structure
2. **Signature Verification**: ECDSA signature validation
3. **Arithmetic Validation**: Pricing and reward calculations
4. **Range Proofs**: Confidential transaction amounts

## Development

### Circuit Structure

```
receipt.circom          # Main circuit file
├── ReceiptHashPreimage # Simple hash preimage proof
├── ReceiptAttestation  # Full receipt validation (WIP)
└── ECDSAVerify        # Signature verification (WIP)
```

### Testing

```bash
# Run all tests
npm test

# Run specific test
npx mocha test.js
```

### Integration

The circuits integrate with:

1. **Coordinator API**: Proof generation service
2. **Settlement Layer**: On-chain verification contracts
3. **Pool Hub**: Privacy options for miners

## Security

### Trusted Setup

The Groth16 setup requires a trusted setup ceremony:

1. Multi-party participation (>100 recommended)
2. Public documentation
3. Destruction of toxic waste

### Audits

- Circuit formal verification
- Third-party security review
- Public disclosure of circuits

## Performance

| Metric | Value |
|--------|-------|
| Proof Size | ~200 bytes |
| Prover Time | 5-15 seconds |
| Verifier Time | 3ms |
| Gas Cost | ~200k |

## Troubleshooting

### Common Issues

1. **Circuit compilation fails**: Check circom version and syntax
2. **Setup fails**: Ensure sufficient disk space and memory
3. **Proof generation slow**: Consider using faster hardware or PLONK

### Debug Commands

```bash
# Check circuit constraints
circom receipt.circom --r1cs --inspect

# View witness
snarkjs wtns check witness.wtns receipt.wasm input.json

# Debug proof generation
DEBUG=snarkjs npm run generate-proof
```

## Resources

- [Circom Documentation](https://docs.circom.io/)
- [snarkjs Documentation](https://github.com/iden3/snarkjs)
- [ZK Whitepaper](https://eprint.iacr.org/2016/260)

## Contributing

1. Fork the repository
2. Create feature branch
3. Submit pull request with tests

## License

MIT
