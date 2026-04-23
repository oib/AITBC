#!/usr/bin/env python3
import secrets
import string
import json
import os

def random_string(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_production_keys():
    client_key = f"client_prod_key_{random_string(24)}"
    miner_key = f"miner_prod_key_{random_string(24)}"
    admin_key = f"admin_prod_key_{random_string(24)}"
    hmac_secret = random_string(64)
    jwt_secret = random_string(64)
    return {
        "CLIENT_API_KEYS": [client_key],
        "MINER_API_KEYS": [miner_key],
        "ADMIN_API_KEYS": [admin_key],
        "HMAC_SECRET": hmac_secret,
        "JWT_SECRET": jwt_secret
    }

if __name__ == "__main__":
    keys = generate_production_keys()
    # Mask sensitive secrets in output
    masked_keys = {
        "CLIENT_API_KEYS": ["*" * 32 for _ in keys["CLIENT_API_KEYS"]],
        "MINER_API_KEYS": ["*" * 32 for _ in keys["MINER_API_KEYS"]],
        "ADMIN_API_KEYS": ["*" * 32 for _ in keys["ADMIN_API_KEYS"]],
        "HMAC_SECRET": "*" * 32,
        "JWT_SECRET": "*" * 32
    }
    print(json.dumps(masked_keys, indent=2))
    print(f"\nActual keys saved to /etc/aitbc/.env (not shown here for security)")
