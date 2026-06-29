#!/usr/bin/env python3
"""
Generate development validator keys for testing purposes.
This script creates temporary test keys that should NOT be used in production.
"""

import json
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_key_pair() -> tuple[str, str]:
    """Generate an RSA key pair and return PEM-formatted private and public keys."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    return private_pem, public_pem


def main():
    """Generate development validator keys."""
    dev_dir = Path(__file__).parent.parent / "dev"
    dev_dir.mkdir(exist_ok=True)

    # Generate a test validator address and key pair
    validator_address = "0x1234567890123456789012345678901234567890"
    private_pem, public_pem = generate_key_pair()

    keys_data = {
        validator_address: {
            "private_key_pem": private_pem,
            "public_key_pem": public_pem,
            "created_at": datetime.now().timestamp(),
            "last_rotated": datetime.now().timestamp(),
        }
    }

    output_file = dev_dir / "validator_keys.json"
    with open(output_file, "w") as f:
        json.dump(keys_data, f, indent=2)

    print(f"Generated development validator keys at {output_file}")
    print("WARNING: These are development keys only. DO NOT use in production!")


if __name__ == "__main__":
    main()
