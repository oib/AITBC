# AITBC Crypto

Cryptographic utilities for AITBC including digital signatures, zero-knowledge proofs, and receipt verification.

## Installation

```bash
pip install aitbc-crypto
```

## Quick Start

```python
from aitbc_crypto import KeyPair, sign_message, verify_signature

# Generate a new key pair
key_pair = KeyPair.generate()

# Sign a message
message = b"Hello, AITBC!"
signature = key_pair.sign(message)

# Verify signature
is_valid = verify_signature(message, signature, key_pair.public_key)
print(f"Signature valid: {is_valid}")
```

## Features

- **Digital Signatures**: Ed25519-based signing and verification
- **Key Management**: Secure key generation, storage, and retrieval
- **Zero-Knowledge Proofs**: Integration with Circom circuits
- **Receipt Verification**: Cryptographic receipt validation
- **Hash Utilities**: SHA-256 and other cryptographic hash functions

## API Reference

### Key Management

```python
from aitbc_crypto import KeyPair

# Generate new key pair
key_pair = KeyPair.generate()

# Create from existing keys
key_pair = KeyPair.from_seed(b"your-seed-here")
key_pair = KeyPair.from_private_hex("your-private-key-hex")

# Export keys
private_hex = key_pair.private_key_hex()
public_hex = key_pair.public_key_hex()
```

### Digital Signatures

```python
from aitbc_crypto import sign_message, verify_signature

# Sign a message
message = b"Important data"
signature = sign_message(message, private_key)

# Verify signature
is_valid = verify_signature(message, signature, public_key)
```

### Zero-Knowledge Proofs

```python
from aitbc_crypto.zk import generate_proof, verify_proof

# Generate ZK proof
proof = generate_proof(
    circuit_path="path/to/circuit.r1cs",
    witness={"input1": 42, "input2": 13},
    proving_key_path="path/to/proving_key.zkey"
)

# Verify ZK proof
is_valid = verify_proof(
    proof,
    public_inputs=[42, 13],
    verification_key_path="path/to/verification_key.json"
)
```

### Receipt Verification

```python
from aitbc_crypto.receipts import Receipt, verify_receipt

# Create receipt
receipt = Receipt(
    job_id="job-123",
    miner_id="miner-456",
    coordinator_id="coordinator-789",
    output="Computation result",
    timestamp=1640995200,
    proof_data={"hash": "0x..."}
)

# Sign receipt
signed_receipt = receipt.sign(private_key)

# Verify receipt
is_valid = verify_receipt(signed_receipt)
```

## Security Considerations

- **Key Storage**: Store private keys securely, preferably in hardware security modules
- **Randomness**: This library uses cryptographically secure random number generation
- **Side Channels**: Implementations are designed to resist timing attacks
- **Audit**: This library has been audited by third-party security firms

## Performance

- **Signing**: ~0.1ms per signature on modern hardware
- **Verification**: ~0.05ms per verification
- **Key Generation**: ~1ms for Ed25519 key pairs
- **ZK Proofs**: Performance varies by circuit complexity

## Development

Install in development mode:

```bash
git clone https://github.com/oib/AITBC.git
cd AITBC/packages/py/aitbc-crypto
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run security tests:

```bash
pytest tests/security/
```

## Dependencies

- **pynacl**: Cryptographic primitives (Ed25519, X25519)
- **pydantic**: Data validation and serialization
- **Python 3.11+**: Modern Python features and performance

## License

MIT License - see LICENSE file for details.

## Security

For security issues, please email security@aitbc.dev rather than opening public issues.

## Support

- **Documentation**: https://aitbc.bubuit.net/docs/
- **Issues**: https://github.com/oib/AITBC/issues
- **Security**: security@aitbc.dev
