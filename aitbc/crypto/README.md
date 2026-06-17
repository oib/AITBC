# aitbc.crypto

Cryptographic utilities for AITBC applications.

## Submodules

- `aitbc.crypto.crypto` - Core crypto (hashing, signing, addresses)
- `aitbc.crypto.security` - Security utilities (tokens, passwords, HMAC)

## Exports

### Core Crypto
- `derive_ethereum_address`, `validate_ethereum_address`
- `sign_transaction_hash`, `verify_signature`
- `keccak256_hash`, `sha256_hash`
- `encrypt_private_key`, `decrypt_private_key`

### Security
- `generate_token`, `validate_token_format`
- `hash_password`, `verify_password`
- `generate_hmac`, `verify_hmac`

## Usage

```python
from aitbc.crypto import derive_ethereum_address
from aitbc.crypto.security import hash_password
```
