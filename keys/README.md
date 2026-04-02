# AITBC Keys Directory

## 🔐 Purpose
Secure storage for blockchain cryptographic keys and keystore files.

## 📁 Contents

### Validator Keys
- **`validator_keys.json`** - Validator key pairs for PoA consensus
- **`.password`** - Keystore password (secure, restricted permissions)
- **`README.md`** - This documentation file

## 🔑 Key Types

### Validator Keys
```json
{
  "0x1234567890123456789012345678901234567890": {
    "private_key_pem": "RSA private key (PEM format)",
    "public_key_pem": "RSA public key (PEM format)",
    "created_at": 1775124393.78119,
    "last_rotated": 1775124393.7813215
  }
}
```

### Keystore Password
- **File**: `.password`
- **Purpose**: Password for encrypted keystore operations
- **Permissions**: 600 (root read/write only)
- **Format**: Plain text password

## 🛡️ Security

### File Permissions
- **validator_keys.json**: 600 (root read/write only)
- **.password**: 600 (root read/write only)
- **Directory**: 700 (root read/write/execute only)

### Key Management
- **Rotation**: Supports automatic key rotation
- **Encryption**: PEM format for standard compatibility
- **Backup**: Regular backups recommended

## 🔧 Usage

### Loading Validator Keys
```python
import json
with open('/opt/aitbc/keys/validator_keys.json', 'r') as f:
    keys = json.load(f)
```

### Keystore Password
```bash
# Read keystore password
cat /opt/aitbc/keys/.password
```

## 📋 Integration

### Blockchain Services
- **PoA Consensus**: Validator key authentication
- **Block Signing**: Cryptographic block validation
- **Transaction Verification**: Digital signature verification

### AITBC Components
- **Consensus Layer**: Multi-validator PoA mechanism
- **Security Layer**: Key rotation and management
- **Network Layer**: Validator identity and trust

## ⚠️ Security Notes

1. **Access Control**: Only root should access these files
2. **Backup Strategy**: Secure, encrypted backups required
3. **Rotation Schedule**: Regular key rotation recommended
4. **Audit Trail**: Monitor key access and usage

## 🔄 Migration

Previously located at `/var/lib/aitbc/keystore/` - moved to `/opt/aitbc/keys/` for centralized key management.
