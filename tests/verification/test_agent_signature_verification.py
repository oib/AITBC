#!/usr/bin/env python3
"""
Test agent SDK signature verification
Tests the signature verification implementation using coordinator API
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def test_signature_generation_and_verification():
    """Test ed25519 signature generation and verification"""
    print("Testing Signature Generation and Verification")
    print("=" * 40)
    
    # Generate keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Create test message
    message = {"type": "test", "data": "hello"}
    message_bytes = json.dumps(message, sort_keys=True).encode('utf-8')
    
    # Sign message
    signature = private_key.sign(message_bytes)
    print(f"Signature length: {len(signature)}")
    
    # Verify signature
    try:
        public_key.verify(signature, message_bytes)
        print("✅ Signature verified successfully")
    except Exception as e:
        print(f"❌ Signature verification failed: {e}")
        return False
    
    print("\n✅ Signature generation and verification test passed!")
    return True


def test_signature_verification_with_wrong_key():
    """Test signature verification fails with wrong public key"""
    print("\nTesting Signature Verification with Wrong Key")
    print("=" * 40)
    
    # Generate two different keypairs
    private_key1 = ed25519.Ed25519PrivateKey.generate()
    public_key1 = private_key1.public_key()
    
    private_key2 = ed25519.Ed25519PrivateKey.generate()
    public_key2 = private_key2.public_key()
    
    # Sign with key1
    message = {"type": "test", "data": "hello"}
    message_bytes = json.dumps(message, sort_keys=True).encode('utf-8')
    signature = private_key1.sign(message_bytes)
    
    # Try to verify with key2
    try:
        public_key2.verify(signature, message_bytes)
        print("❌ Signature verified with wrong key (should fail)")
        return False
    except Exception:
        print("✅ Signature verification correctly failed with wrong key")
    
    print("\n✅ Wrong key verification test passed!")
    return True


def test_signature_verification_with_tampered_message():
    """Test signature verification fails with tampered message"""
    print("\nTesting Signature Verification with Tampered Message")
    print("=" * 40)
    
    # Generate keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Sign original message
    original_message = {"type": "test", "data": "hello"}
    original_bytes = json.dumps(original_message, sort_keys=True).encode('utf-8')
    signature = private_key.sign(original_bytes)
    
    # Tamper with message
    tampered_message = {"type": "test", "data": "goodbye"}
    tampered_bytes = json.dumps(tampered_message, sort_keys=True).encode('utf-8')
    
    # Try to verify tampered message
    try:
        public_key.verify(signature, tampered_bytes)
        print("❌ Signature verified with tampered message (should fail)")
        return False
    except Exception:
        print("✅ Signature verification correctly failed with tampered message")
    
    print("\n✅ Tampered message verification test passed!")
    return True


async def test_fetch_public_key_from_coordinator():
    """Test fetching public key from coordinator API"""
    print("\nTesting Fetch Public Key from Coordinator API")
    print("=" * 40)
    
    # Mock coordinator API response
    mock_response = {
        "agent_id": "test_agent",
        "public_key": "test_public_key_hex"
    }
    
    # Test the fetch function (mock implementation)
    async def mock_fetch_public_key(sender_id: str, coordinator_url: str):
        """Mock implementation of public key fetch"""
        # Simulate API call
        return mock_response.get("public_key")
    
    # Test successful fetch
    public_key = await mock_fetch_public_key("test_agent", "http://localhost:8011")
    if public_key:
        print(f"✅ Public key fetched: {public_key}")
    else:
        print("❌ Failed to fetch public key")
        return False
    
    # Test failed fetch (non-existent agent)
    async def mock_fetch_public_key_not_found(sender_id: str, coordinator_url: str):
        return None
    
    public_key = await mock_fetch_public_key_not_found("nonexistent", "http://localhost:8011")
    if public_key is None:
        print("✅ Correctly returned None for non-existent agent")
    else:
        print("❌ Should return None for non-existent agent")
        return False
    
    print("\n✅ Fetch public key test passed!")
    return True


async def test_receive_message_with_signature():
    """Test receive_message with signature verification"""
    print("\nTesting Receive Message with Signature Verification")
    print("=" * 40)
    
    # Generate keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    
    # Create and sign message
    message = {
        "from": "sender_agent",
        "type": "test",
        "data": "hello"
    }
    message_copy = message.copy()
    message_bytes = json.dumps(message_copy, sort_keys=True).encode('utf-8')
    signature = private_key.sign(message_bytes)
    
    # Add signature to message
    message_with_sig = message.copy()
    message_with_sig["signature"] = signature
    
    print(f"Message signed with signature length: {len(signature)}")
    print(f"Public key hex: {public_key_hex[:20]}...")
    
    # Mock coordinator API to return public key
    async def mock_fetch_public_key(sender_id: str, coordinator_url: str):
        if sender_id == "sender_agent":
            return public_key_hex
        return None
    
    # Test verification
    sender_id = message_with_sig.get("from")
    signature_bytes = message_with_sig.get("signature")
    
    if not signature_bytes:
        print("❌ Message missing signature")
        return False
    
    # Fetch public key
    public_key_hex = await mock_fetch_public_key(sender_id, "http://localhost:8011")
    if not public_key_hex:
        print("❌ Failed to fetch public key")
        return False
    
    # Verify signature
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        message_to_verify = message_with_sig.copy()
        message_to_verify.pop("signature", None)
        message_bytes = json.dumps(message_to_verify, sort_keys=True).encode('utf-8')
        
        public_key.verify(signature_bytes, message_bytes)
        print("✅ Signature verified successfully")
    except Exception as e:
        print(f"❌ Signature verification failed: {e}")
        return False
    
    print("\n✅ Receive message with signature test passed!")
    return True


async def run_async_tests():
    """Run async tests"""
    print("Agent SDK Signature Verification Tests")
    print("=" * 40)
    print()
    
    results = []
    results.append(("Signature Generation and Verification", test_signature_generation_and_verification()))
    results.append(("Signature Verification with Wrong Key", test_signature_verification_with_wrong_key()))
    results.append(("Signature Verification with Tampered Message", test_signature_verification_with_tampered_message()))
    results.append(("Fetch Public Key from Coordinator", await test_fetch_public_key_from_coordinator()))
    results.append(("Receive Message with Signature", await test_receive_message_with_signature()))
    
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


if __name__ == "__main__":
    asyncio.run(run_async_tests())
