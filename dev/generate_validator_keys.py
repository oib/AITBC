#!/usr/bin/env python3
"""Generate validator keys for development."""

import json
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem.decode(), public_pem.decode()


def main():
    import time

    private_pem, public_pem = generate_key_pair()

    # Generate a placeholder address (in real implementation, this would be derived from the key)
    placeholder_address = "0x" + "0" * 40

    timestamp = time.time()

    keys = {
        placeholder_address: {
            "private_key_pem": private_pem,
            "public_key_pem": public_pem,
            "created_at": timestamp,
            "last_rotated": timestamp,
        }
    }

    output_path = Path("dev/validator_keys.json")
    with open(output_path, "w") as f:
        json.dump(keys, f, indent=2)

    print(f"Generated keys at {output_path}")


if __name__ == "__main__":
    main()
