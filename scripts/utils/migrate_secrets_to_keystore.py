#!/usr/bin/env python3
"""
Migrate secrets from .env to encrypted keystore storage
"""

import sys
import os
from pathlib import Path
from secrets import token_bytes

# Add wallet service to path
sys.path.insert(0, '/opt/aitbc/apps/wallet/src')

from app.crypto.encryption import EncryptionSuite

def encrypt_secret(plaintext: str, encryption_password: str) -> bytes:
    """Encrypt a secret using AES-GCM"""
    encryption = EncryptionSuite()
    salt = token_bytes(encryption.salt_bytes)
    nonce = token_bytes(encryption.nonce_bytes)
    ciphertext = encryption.encrypt(password=encryption_password, plaintext=plaintext.encode(), salt=salt, nonce=nonce)
    return salt + nonce + ciphertext

def main():
    env_file = Path('/etc/aitbc/.env')
    keystore_config_dir = Path('/var/lib/aitbc/keystore/config')
    keystore_passwords_dir = Path('/var/lib/aitbc/keystore/passwords')

    # Get encryption password from environment
    enc_password = os.environ.get('KEYSTORE_ENCRYPTION_PASSWORD')
    if not enc_password:
        print("Error: KEYSTORE_ENCRYPTION_PASSWORD environment variable not set")
        print("Set it with: export KEYSTORE_ENCRYPTION_PASSWORD=<secure-password>")
        sys.exit(1)

    # Read .env file
    env_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    # Migrate API_KEY_HASH_SECRET
    if 'API_KEY_HASH_SECRET' in env_vars:
        api_secret = env_vars['API_KEY_HASH_SECRET']
        encrypted = encrypt_secret(api_secret, enc_password)
        output_file = keystore_config_dir / 'api_hash_secret.enc'
        with open(output_file, 'wb') as f:
            f.write(encrypted)
        os.chmod(output_file, 0o600)
        print(f"Migrated API_KEY_HASH_SECRET to: {output_file}")
    else:
        print("API_KEY_HASH_SECRET not found in .env")

    # Migrate proposer_id
    if 'proposer_id' in env_vars:
        proposer_id = env_vars['proposer_id']
        encrypted = encrypt_secret(proposer_id, enc_password)
        output_file = keystore_config_dir / 'proposer_key.enc'
        with open(output_file, 'wb') as f:
            f.write(encrypted)
        os.chmod(output_file, 0o600)
        print(f"Migrated proposer_id to: {output_file}")
    else:
        print("proposer_id not found in .env")

    # Update .env to remove migrated secrets
    new_env_lines = []
    with open(env_file, 'r') as f:
        for line in f:
            if line.strip().startswith('API_KEY_HASH_SECRET='):
                new_env_lines.append('# API_KEY_HASH_SECRET migrated to keystore/config/api_hash_secret.enc\n')
            elif line.strip().startswith('proposer_id='):
                new_env_lines.append('# proposer_id migrated to keystore/config/proposer_key.enc\n')
            else:
                new_env_lines.append(line)

    with open(env_file, 'w') as f:
        f.writelines(new_env_lines)

    print(f"Updated {env_file} to remove migrated secrets")
    print("\nWARNING: Keep KEYSTORE_ENCRYPTION_PASSWORD secure - it's needed to decrypt")

if __name__ == '__main__':
    main()
