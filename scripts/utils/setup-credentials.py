#!/usr/bin/env python3
"""
Setup systemd credentials for AITBC services
Stores secrets in /etc/aitbc/credentials with proper permissions
"""

import sys
import os
from pathlib import Path
from secrets import token_hex

def main():
    credentials_dir = Path('/etc/aitbc/credentials')
    credentials_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(credentials_dir, 0o700)

    env_file = Path('/etc/aitbc/.env')

    # Read current .env values
    env_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()

    # Create credential files for sensitive values
    credentials = {
        'api_hash_secret': env_vars.get('API_KEY_HASH_SECRET', token_hex(32)),
        'proposer_id': env_vars.get('proposer_id', ''),
        'keystore_password': env_vars.get('KEYSTORE_PASSWORD', token_hex(32)),
    }

    for name, value in credentials.items():
        if value:
            cred_file = credentials_dir / name
            with open(cred_file, 'w') as f:
                f.write(value)
            os.chmod(cred_file, 0o600)
            print(f"Created credential: {cred_file}")

    print(f"\nCredentials stored in: {credentials_dir}")
    print("All files have 600 permissions (root read/write only)")

if __name__ == '__main__':
    main()
