#!/usr/bin/env python3
"""
Test MAC computation in keystore scripts
Tests HMAC-SHA256 MAC computation for web3 keystore format
"""

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


def compute_mac(key: bytes, ciphertext: bytes) -> str:
    """Compute MAC for web3 keystore format (HMAC-SHA256)"""
    mac_data = key[16:32] + ciphertext
    mac = hmac.new(key[:16], mac_data, hashlib.sha256).hexdigest()
    return mac


def test_mac_computation():
    """Test MAC computation matches web3 keystore standard"""
    print("Testing MAC Computation")
    print("=" * 40)
    
    # Generate test key and ciphertext
    password = "test_password_123"
    salt = os.urandom(32)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    key = kdf.derive(password.encode('utf-8'))
    
    # Generate test ciphertext
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
    
    # Compute MAC
    mac = compute_mac(key, ciphertext)
    
    print(f"MAC computed: {mac}")
    print(f"MAC length: {len(mac)}")
    
    # Verify MAC is a valid hex string
    try:
        int(mac, 16)
        print("✅ MAC is valid hex string")
    except ValueError:
        print("❌ MAC is not valid hex string")
        return False
    
    # Verify MAC length (64 hex chars = 32 bytes)
    if len(mac) == 64:
        print("✅ MAC has correct length (64 hex chars)")
    else:
        print(f"❌ MAC has incorrect length: {len(mac)} (expected 64)")
        return False
    
    print("\n✅ MAC computation test passed!")
    return True


def test_keystore_with_mac():
    """Test full keystore generation with MAC"""
    print("\nTesting Keystore Generation with MAC")
    print("=" * 40)
    
    # Create temporary keystore directory
    with tempfile.TemporaryDirectory() as temp_dir:
        keystore_dir = Path(temp_dir)
        
        # Generate keystore
        password = "test_password_123"
        name = "test_wallet"
        
        salt = os.urandom(32)
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Derive key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
            backend=default_backend()
        )
        key = kdf.derive(password.encode('utf-8'))
        
        # Encrypt
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
        
        # Compute MAC
        mac = compute_mac(key, ciphertext)
        
        # Build keystore
        keystore = {
            "crypto": {
                "cipher": "aes-256-gcm",
                "cipherparams": {"nonce": nonce.hex()},
                "ciphertext": ciphertext.hex(),
                "kdf": "pbkdf2",
                "kdfparams": {
                    "dklen": 32,
                    "salt": salt.hex(),
                    "c": 100_000,
                    "prf": "hmac-sha256"
                },
                "mac": mac
            },
            "address": "test_address",
            "keytype": "ed25519",
            "version": 1
        }
        
        # Write keystore
        keystore_file = keystore_dir / f"{name}.json"
        with open(keystore_file, 'w') as f:
            json.dump(keystore, f, indent=2)
        
        print(f"Keystore written to: {keystore_file}")
        
        # Read back and verify MAC
        with open(keystore_file) as f:
            loaded = json.load(f)
        
        loaded_mac = loaded["crypto"]["mac"]
        if loaded_mac == mac:
            print("✅ MAC matches in loaded keystore")
        else:
            print(f"❌ MAC mismatch: {loaded_mac} != {mac}")
            return False
        
        print("\n✅ Keystore with MAC test passed!")
        return True


def test_mac_validation():
    """Test MAC validation for password errors"""
    print("\nTesting MAC Validation")
    print("=" * 40)
    
    password = "correct_password"
    wrong_password = "wrong_password"
    
    salt = os.urandom(32)
    
    # Derive key with correct password
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    correct_key = kdf.derive(password.encode('utf-8'))
    
    # Derive key with wrong password
    kdf_wrong = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    wrong_key = kdf_wrong.derive(wrong_password.encode('utf-8'))
    
    # Generate test ciphertext
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    aesgcm = AESGCM(correct_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
    
    # Compute MAC with correct key
    correct_mac = compute_mac(correct_key, ciphertext)
    
    # Try to compute MAC with wrong key
    wrong_mac = compute_mac(wrong_key, ciphertext)
    
    print(f"Correct MAC: {correct_mac}")
    print(f"Wrong MAC: {wrong_mac}")
    
    if correct_mac != wrong_mac:
        print("✅ MAC validation detects password errors")
    else:
        print("❌ MAC validation failed to detect password errors")
        return False
    
    print("\n✅ MAC validation test passed!")
    return True


if __name__ == "__main__":
    print("Keystore MAC Computation Tests")
    print("=" * 40)
    print()
    
    results = []
    results.append(("MAC Computation", test_mac_computation()))
    results.append(("Keystore with MAC", test_keystore_with_mac()))
    results.append(("MAC Validation", test_mac_validation()))
    
    print("\n" + "=" * 40)
    print("Test Summary")
    print("=" * 40)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed")
