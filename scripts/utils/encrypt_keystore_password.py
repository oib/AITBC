#!/usr/bin/env python3
"""
Encrypt keystore password file using AES-GCM encryption
Uses the existing encryption suite from the wallet service
"""

import sys
import os
from pathlib import Path

# Add wallet service to path
sys.path.insert(0, '/opt/aitbc/apps/wallet/src')

from app.crypto.encryption import EncryptionSuite
from secrets import token_bytes

def main():
    keystore_dir = Path('/var/lib/aitbc/keystore')
    password_file = keystore_dir / '.password'
    encrypted_file = keystore_dir / 'passwords' / 'keystore_password.enc'

    # Ensure passwords directory exists
    encrypted_file.parent.mkdir(parents=True, exist_ok=True)

    # Read existing password if it exists
    if password_file.exists():
        with open(password_file, 'r') as f:
            password = f.read().strip()
    else:
        # Generate new secure password if none exists
        password = token_bytes(32).hex()
        with open(password_file, 'w') as f:
            f.write(password)
        os.chmod(password_file, 0o600)

    # Get encryption password from environment or prompt
    enc_password = os.environ.get('KEYSTORE_ENCRYPTION_PASSWORD')
    if not enc_password:
        print("Error: KEYSTORE_ENCRYPTION_PASSWORD environment variable not set")
        print("Set it with: export KEYSTORE_ENCRYPTION_PASSWORD=<secure-password>")
        sys.exit(1)

    # Encrypt the password
    encryption = EncryptionSuite()
    salt = token_bytes(encryption.salt_bytes)
    nonce = token_bytes(encryption.nonce_bytes)
    ciphertext = encryption.encrypt(password=enc_password, plaintext=password.encode(), salt=salt, nonce=nonce)

    # Write encrypted file with salt and nonce
    with open(encrypted_file, 'wb') as f:
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)

    os.chmod(encrypted_file, 0o600)

    print(f"Encrypted keystore password saved to: {encrypted_file}")
    print(f"Original password file: {password_file} (will be removed)")
    print(f"WARNING: Keep KEYSTORE_ENCRYPTION_PASSWORD secure - it's needed to decrypt")

    # Remove clear text password file
    if password_file.exists():
        password_file.unlink()
        print(f"Removed clear text password file: {password_file}")

if __name__ == '__main__':
    main()
