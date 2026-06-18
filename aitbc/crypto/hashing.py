"""
Hashing and HMAC utilities
"""

import hashlib
import hmac
import secrets


def generate_hmac(data: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature"""
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(data: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    computed = generate_hmac(data, secret)
    return secrets.compare_digest(computed, signature)
